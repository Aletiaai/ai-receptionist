"""
Voice Server for AI Receptionist
Handles OpenAI Realtime API webhooks for SIP calls.
"""

import os
import sys
import json
import asyncio
import hashlib
import hmac
import re
import time
import logging
from datetime import datetime, timezone
from typing import Optional
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
import websockets
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add current directory to path for config imports (works both locally and in Docker)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Also add parent directory for local development
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import (
    OPENAI_CONFIG, VOICE_CONFIG, LOGGING_CONFIG,
    DEFAULT_VOICE_TENANTS, BOOKING_CONFIG
)
from config.prompts import VOICE_INSTRUCTIONS, VOICE_ERROR_MESSAGES

# Configure logging with call_id filter on root logger
class CallContextFilter(logging.Filter):
    """Add call_id to log records."""
    def filter(self, record):
        if not hasattr(record, 'call_id'):
            record.call_id = 'no-call'
        return True


# Add filter to root logger so all loggers (including httpx) have call_id
root_logger = logging.getLogger()
root_logger.addFilter(CallContextFilter())

logging.basicConfig(
    level=logging.INFO,
    format=LOGGING_CONFIG["voice_format"],
    datefmt=LOGGING_CONFIG["voice_date_format"]
)
logger = logging.getLogger(__name__)

# Configuration from environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_WEBHOOK_SECRET = os.getenv("OPENAI_WEBHOOK_SECRET", "")
BOOKING_WEBHOOK_URL = os.getenv("BOOKING_WEBHOOK_URL", "")

# Stale call timeout (seconds) - from config
STALE_CALL_TIMEOUT = VOICE_CONFIG["stale_call_timeout_seconds"]

# OpenAI API endpoints from config
OPENAI_API_BASE = OPENAI_CONFIG["api_base"]
OPENAI_REALTIME_WS = OPENAI_CONFIG["realtime_ws"]

# Build tenant configurations from config
TENANTS = {}
for tenant_id, tenant_config in DEFAULT_VOICE_TENANTS.items():
    TENANTS[tenant_id] = {
        **tenant_config,
        "instructions": VOICE_INSTRUCTIONS.get(tenant_id, VOICE_INSTRUCTIONS.get("consulate"))
    }

# Default tenant from config
DEFAULT_TENANT = VOICE_CONFIG["default_tenant"]


def validate_configuration():
    """Validate required configuration on startup."""
    errors = []

    if not OPENAI_API_KEY:
        errors.append("OPENAI_API_KEY is required but not set")

    if not BOOKING_WEBHOOK_URL:
        logger.warning("BOOKING_WEBHOOK_URL not configured - booking features will fail")

    if errors:
        for error in errors:
            logger.error(error)
        raise RuntimeError(f"Configuration errors: {'; '.join(errors)}")


async def cleanup_stale_calls():
    """Background task to clean up stale calls that weren't properly closed."""
    while True:
        try:
            await asyncio.sleep(VOICE_CONFIG["cleanup_interval_seconds"])
            now = datetime.now(timezone.utc)
            stale_call_ids = []

            for call_id, call_state in list(active_calls.items()):
                started_at_str = call_state.get("started_at")
                if started_at_str:
                    started_at = datetime.fromisoformat(started_at_str)
                    age_seconds = (now - started_at).total_seconds()
                    if age_seconds > STALE_CALL_TIMEOUT:
                        stale_call_ids.append(call_id)

            for call_id in stale_call_ids:
                logger.warning(f"Cleaning up stale call", extra={'call_id': call_id})
                del active_calls[call_id]

            if stale_call_ids:
                logger.info(f"Cleaned up {len(stale_call_ids)} stale calls")

        except Exception as e:
            logger.error(f"Error in stale call cleanup: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    validate_configuration()
    logger.info("Voice server starting up")

    # Start background cleanup task
    cleanup_task = asyncio.create_task(cleanup_stale_calls())

    yield

    # Shutdown
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    logger.info("Voice server shutting down")

# Tools/Functions for the Realtime API
TOOLS = [
    {
        "type": "function",
        "name": "get_available_days",
        "description": "Get available days for booking. Call this after collecting the caller's name, email, and phone number.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_name": {
                    "type": "string",
                    "description": "The caller's full name"
                },
                "user_email": {
                    "type": "string",
                    "description": "The caller's email address"
                },
                "user_phone": {
                    "type": "string",
                    "description": "The caller's phone number"
                }
            },
            "required": ["user_name", "user_email", "user_phone"]
        }
    },
    {
        "type": "function",
        "name": "get_available_slots",
        "description": "Get available time slots for a specific day. Call this after the caller selects a day from the available days list.",
        "parameters": {
            "type": "object",
            "properties": {
                "day_number": {
                    "type": "integer",
                    "description": "The number of the selected day (1, 2, 3, etc.) from the available days list"
                }
            },
            "required": ["day_number"]
        }
    },
    {
        "type": "function",
        "name": "book_appointment",
        "description": "Book an appointment for the caller. Call this after they select a time slot.",
        "parameters": {
            "type": "object",
            "properties": {
                "slot_number": {
                    "type": "integer",
                    "description": "The number of the selected time slot (1, 2, 3, etc.)"
                }
            },
            "required": ["slot_number"]
        }
    }
]

app = FastAPI(title="AI Receptionist Voice Server", lifespan=lifespan)

# Store active calls (call_id -> call_state dict)
# Thread-safe for async operations within a single process
active_calls = {}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions and return a proper error response."""
    logger.error(f"Unhandled exception on {request.url.path}: {type(exc).__name__}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "detail": "An internal error occurred",
            "type": type(exc).__name__
        }
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    # Check configuration
    config_ok = bool(OPENAI_API_KEY)

    return {
        "status": "healthy" if config_ok else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "active_calls": len(active_calls),
        "config": {
            "openai_configured": bool(OPENAI_API_KEY),
            "booking_url_configured": bool(BOOKING_WEBHOOK_URL),
            "webhook_secret_configured": bool(OPENAI_WEBHOOK_SECRET)
        }
    }


@app.post("/webhook")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Handle incoming webhooks from OpenAI.
    """
    body = await request.body()
    headers = request.headers

    # Verify webhook signature (if secret is configured)
    if OPENAI_WEBHOOK_SECRET:
        signature = headers.get("webhook-signature", "")
        timestamp = headers.get("webhook-timestamp", "")

        if not verify_webhook_signature(body, signature, timestamp):
            logger.warning("Invalid webhook signature received")
            raise HTTPException(status_code=400, detail="Invalid signature")

    # Parse the event
    try:
        event = json.loads(body)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in webhook body: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = event.get("type")
    event_id = event.get("id")

    logger.info(f"Webhook received: {event_type} (ID: {event_id})")

    if event_type == "realtime.call.incoming":
        # Handle incoming call
        call_data = event.get("data", {})
        call_id = call_data.get("call_id")

        # Validate call_id is present
        if not call_id:
            logger.error("Incoming call webhook missing call_id")
            raise HTTPException(status_code=400, detail="Missing call_id in webhook data")

        # Check for duplicate webhook (race condition protection)
        if call_id in active_calls:
            logger.warning(f"Duplicate webhook for call, ignoring", extra={'call_id': call_id})
            return JSONResponse(
                status_code=200,
                content={"status": "already_processing"},
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"}
            )

        sip_headers = call_data.get("sip_headers", [])

        # Extract caller info from SIP headers
        from_number = None
        for header in sip_headers:
            if header.get("name") == "From":
                from_number = header.get("value")
                break

        logger.info(f"Incoming call from {from_number or 'unknown'}", extra={'call_id': call_id})

        # Determine tenant based on called number (for now, use default)
        tenant_id = DEFAULT_TENANT
        tenant = TENANTS.get(tenant_id)

        if not tenant:
            logger.error(f"Unknown tenant: {tenant_id}", extra={'call_id': call_id})
            raise HTTPException(status_code=500, detail=f"Unknown tenant configuration: {tenant_id}")

        # Store call state immediately to prevent duplicate processing
        active_calls[call_id] = {
            "tenant_id": tenant_id,
            "from_number": from_number,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "user_data": {},
            "available_days": [],
            "selected_date": None,
            "available_slots": [],
            "booking_complete": False,
            "status": "accepting"  # Track call lifecycle
        }

        accept_payload = {
            "type": "realtime",
            "model": OPENAI_CONFIG["realtime_model"],
            "audio": {
                "output": { "voice": tenant["voice"] }
            },
            "instructions": tenant["instructions"],
            "tools": TOOLS
        }

        try:
            async with httpx.AsyncClient() as client:
                accept_url = f"{OPENAI_API_BASE}/realtime/calls/{call_id}/accept"
                response = await client.post(
                    accept_url,
                    headers={
                        "Authorization": f"Bearer {OPENAI_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json=accept_payload,
                    timeout=float(VOICE_CONFIG["api_timeout_seconds"])
                )

                if response.status_code != 200:
                    logger.error(
                        f"Failed to accept call: {response.status_code} - {response.text}",
                        extra={'call_id': call_id}
                    )
                    if call_id in active_calls:
                        del active_calls[call_id]
                    return JSONResponse(status_code=500, content={"status": "error", "detail": "Failed to accept call"})

        except httpx.TimeoutException:
            logger.error("Timeout while accepting call with OpenAI", extra={'call_id': call_id})
            if call_id in active_calls:
                del active_calls[call_id]
            return JSONResponse(status_code=504, content={"status": "error", "detail": "Timeout accepting call"})

        except httpx.ConnectError as e:
            logger.error(f"Connection error accepting call: {e}", extra={'call_id': call_id})
            if call_id in active_calls:
                del active_calls[call_id]
            return JSONResponse(status_code=502, content={"status": "error", "detail": "Connection error"})

        except httpx.HTTPError as e:
            logger.error(f"HTTP error accepting call: {e}", extra={'call_id': call_id})
            if call_id in active_calls:
                del active_calls[call_id]
            return JSONResponse(status_code=502, content={"status": "error", "detail": "HTTP error"})

        # Update call status
        active_calls[call_id]["status"] = "active"
        logger.info("Call accepted successfully", extra={'call_id': call_id})

        # Start monitoring in background
        background_tasks.add_task(monitor_call, call_id, tenant_id)

        # Return response with required Authorization header
        return JSONResponse(
            status_code=200,
            content={"status": "accepted"},
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"}
        )

    return JSONResponse(status_code=200, content={"status": "ignored"})


def verify_webhook_signature(body: bytes, signature: str, timestamp: str) -> bool:
    """Verify OpenAI webhook signature."""
    if not OPENAI_WEBHOOK_SECRET:
        return True

    try:
        ts = int(timestamp)
        # Reject timestamps older than 5 minutes
        if abs(time.time() - ts) > 300:
            logger.warning("Webhook timestamp too old or in future")
            return False

        signed_payload = f"{timestamp}.{body.decode()}"
        expected_sig = hmac.new(
            OPENAI_WEBHOOK_SECRET.encode(),
            signed_payload.encode(),
            hashlib.sha256
        ).hexdigest()

        if signature.startswith("v1,"):
            actual_sig = signature[3:]
            return hmac.compare_digest(expected_sig, actual_sig)

        logger.warning("Webhook signature format not recognized")
        return False

    except ValueError as e:
        logger.warning(f"Invalid webhook timestamp: {e}")
        return False
    except Exception as e:
        logger.error(f"Signature verification error: {type(e).__name__}: {e}")
        return False


async def monitor_call(call_id: str, tenant_id: str):
    """Monitor call events via WebSocket."""
    ws_url = f"{OPENAI_REALTIME_WS}?call_id={call_id}"
    log_extra = {'call_id': call_id}
    _ = tenant_id  # Available in call_state, kept in signature for potential future use

    # Track reconnection attempts
    max_reconnect_attempts = VOICE_CONFIG["max_reconnect_attempts"]
    reconnect_attempt = 0

    while reconnect_attempt < max_reconnect_attempts:
        try:
            async with websockets.connect(
                ws_url,
                extra_headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                ping_interval=VOICE_CONFIG["ws_ping_interval"],
                ping_timeout=VOICE_CONFIG["ws_ping_timeout"],
                close_timeout=VOICE_CONFIG["ws_close_timeout"]
            ) as ws:
                logger.info("WebSocket connected", extra=log_extra)
                reconnect_attempt = 0  # Reset on successful connection

                # Send initial greeting prompt
                initial_response = {
                    "type": "response.create",
                    "response": {
                        "instructions": VOICE_INSTRUCTIONS["initial_greeting"]
                    }
                }
                try:
                    await ws.send(json.dumps(initial_response))
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("Connection closed while sending initial greeting", extra=log_extra)
                    break

                # Listen for events
                async for message in ws:
                    # Parse message with error handling
                    try:
                        event = json.loads(message)
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON in WebSocket message: {e}", extra=log_extra)
                        continue  # Skip malformed messages

                    event_type = event.get("type")

                    # Get current call state
                    call_state = active_calls.get(call_id, {})

                    # Debug: Log all events after booking is complete
                    if call_state.get("booking_complete"):
                        logger.info(f"[POST-BOOKING] Event: {event_type}", extra=log_extra)

                    # Log transcriptions
                    if event_type == "conversation.item.input_audio_transcription.completed":
                        transcript = event.get("transcript", "")
                        logger.info(f"User said: {transcript[:100]}{'...' if len(transcript) > 100 else ''}", extra=log_extra)

                    elif event_type == "response.output_audio_transcript.done":
                        # This fires when transcript is complete (but audio may still be playing!)
                        transcript = event.get("transcript", "")
                        logger.info(f"Assistant said: {transcript[:100]}{'...' if len(transcript) > 100 else ''}", extra=log_extra)

                    # Audio buffer stopped = audio actually finished playing to caller
                    elif event_type == "output_audio_buffer.stopped":
                        logger.info("Audio playback finished (output_audio_buffer.stopped)", extra=log_extra)
                        if call_state.get("booking_complete"):
                            # Cancel any existing timer first
                            hangup_task = call_state.get("hangup_task")
                            if hangup_task and not hangup_task.done():
                                hangup_task.cancel()

                            # Start silence timer (3 seconds of silence = hang up)
                            logger.info("AI audio finished playing, starting silence timer", extra=log_extra)
                            hangup_task = asyncio.create_task(
                                silence_hangup(call_id, silence_seconds=3)
                            )
                            call_state["hangup_task"] = hangup_task
                            active_calls[call_id] = call_state

                    # Track when user starts speaking - cancel any pending hangup
                    elif event_type == "input_audio_buffer.speech_started":
                        logger.debug(f"Event: input_audio_buffer.speech_started (booking_complete={call_state.get('booking_complete')})", extra=log_extra)
                        if call_state.get("booking_complete"):
                            # User is speaking after booking - cancel pending hangup
                            hangup_task = call_state.get("hangup_task")
                            if hangup_task and not hangup_task.done():
                                hangup_task.cancel()
                                logger.info("User speaking, cancelled pending hangup", extra=log_extra)
                            call_state["hangup_task"] = None
                            active_calls[call_id] = call_state

                    # Track when AI finishes generating a response (note: audio may still be playing)
                    elif event_type == "response.done":
                        logger.info(f"Event: response.done (booking_complete={call_state.get('booking_complete')}) - response generated, audio still playing", extra=log_extra)
                        # Don't start timer here - wait for response.audio_transcript.done instead

                    elif event_type == "response.function_call_arguments.done":
                        # Handle function calls with error handling
                        try:
                            await handle_function_call(ws, call_id, event)
                        except websockets.exceptions.ConnectionClosed:
                            logger.warning("Connection closed during function call handling", extra=log_extra)
                            break
                        except Exception as e:
                            logger.error(f"Error handling function call: {e}", extra=log_extra)
                            # Try to send error response back to OpenAI
                            try:
                                await send_function_error(ws, event.get("call_id"), str(e))
                            except Exception:
                                pass

                    elif event_type == "error":
                        error_info = event.get("error", {})
                        error_code = error_info.get("code", "unknown")
                        error_message = error_info.get("message", "Unknown error")
                        logger.error(f"OpenAI Error [{error_code}]: {error_message}", extra=log_extra)

                        # Handle specific error types
                        if error_code in ["session_expired", "invalid_session"]:
                            logger.warning("Session expired, cannot reconnect", extra=log_extra)
                            return

                    elif event_type == "session.closed":
                        logger.info("Session closed by OpenAI", extra=log_extra)
                        return  # Normal closure, don't reconnect

                # If we exit the loop normally, don't reconnect
                return

        except websockets.exceptions.InvalidStatusCode as e:
            logger.error(f"WebSocket connection rejected with status {e.status_code}", extra=log_extra)
            break  # Don't retry on auth/invalid errors

        except websockets.exceptions.ConnectionClosed as e:
            reconnect_attempt += 1
            logger.warning(
                f"WebSocket disconnected (code={e.code}), attempt {reconnect_attempt}/{max_reconnect_attempts}",
                extra=log_extra
            )
            if reconnect_attempt < max_reconnect_attempts:
                await asyncio.sleep(VOICE_CONFIG["reconnect_delay_seconds"])

        except asyncio.CancelledError:
            logger.info("Call monitoring cancelled", extra=log_extra)
            break

        except Exception as e:
            logger.error(f"Unexpected WebSocket error: {type(e).__name__}: {e}", extra=log_extra)
            break

    # Cleanup
    if call_id in active_calls:
        del active_calls[call_id]
    logger.info("Call monitoring ended", extra=log_extra)


async def send_function_error(ws, call_item_id: str, error_message: str):
    """Send an error response for a failed function call."""
    error_output = {
        "type": "conversation.item.create",
        "item": {
            "type": "function_call_output",
            "call_id": call_item_id,
            "output": json.dumps({
                "error": True,
                "message": f"An error occurred: {error_message}. Please try again."
            })
        }
    }
    await ws.send(json.dumps(error_output))
    await ws.send(json.dumps({"type": "response.create"}))


def validate_email(email: str) -> bool:
    """Basic email validation."""
    if not email:
        return False
    # Basic email pattern
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_slot_number(slot_number, available_slots: list) -> tuple[bool, str]:
    """Validate slot number is within valid range."""
    if slot_number is None:
        return False, "No slot number provided"

    try:
        slot_num = int(slot_number)
    except (ValueError, TypeError):
        return False, f"Invalid slot number format: {slot_number}"

    if not available_slots:
        return False, "No available slots to select from"

    if slot_num < 1 or slot_num > len(available_slots):
        return False, f"Please choose a slot between 1 and {len(available_slots)}"

    return True, ""


def validate_day_number(day_number, available_days: list) -> tuple[bool, str]:
    """Validate day number is within valid range."""
    if day_number is None:
        return False, "No day number provided"

    try:
        day_num = int(day_number)
    except (ValueError, TypeError):
        return False, f"Invalid day number format: {day_number}"

    if not available_days:
        return False, "No available days to select from. Please get available days first."

    if day_num < 1 or day_num > len(available_days):
        return False, VOICE_ERROR_MESSAGES["invalid_day_number"]["en"].format(max_days=len(available_days))

    return True, ""


async def handle_function_call(ws, call_id: str, event: dict):
    """Handle function calls from the Realtime API."""
    log_extra = {'call_id': call_id}

    function_name = event.get("name")
    call_item_id = event.get("call_id")
    arguments_str = event.get("arguments", "{}")

    # Validate call_item_id exists
    if not call_item_id:
        logger.error("Function call missing call_id field", extra=log_extra)
        return

    # Parse arguments with error handling
    try:
        arguments = json.loads(arguments_str) if arguments_str else {}
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in function arguments: {e}", extra=log_extra)
        await send_function_error(ws, call_item_id, "Invalid function arguments")
        return

    logger.info(f"Function call: {function_name}", extra=log_extra)
    logger.debug(f"Arguments: {arguments}", extra=log_extra)

    call_state = active_calls.get(call_id, {})
    if not call_state:
        logger.warning("Call state not found for function call", extra=log_extra)
        await send_function_error(ws, call_item_id, "Call session not found")
        return

    tenant_id = call_state.get("tenant_id", DEFAULT_TENANT)
    result = None

    if function_name == "get_available_days":
        # Validate and extract user data
        user_name = str(arguments.get("user_name", "")).strip()
        user_email = str(arguments.get("user_email", "")).strip()
        user_phone = str(arguments.get("user_phone", "")).strip()

        # Validate required fields
        validation_errors = []
        if not user_name:
            validation_errors.append("name")
        if not user_email:
            validation_errors.append("email")
        elif not validate_email(user_email):
            logger.warning(f"Invalid email format: {user_email}", extra=log_extra)
            # Allow it but log - AI might have transcribed incorrectly
        if not user_phone:
            validation_errors.append("phone number")

        if validation_errors:
            missing = ", ".join(validation_errors)
            result = {
                "error": True,
                "message": VOICE_ERROR_MESSAGES["missing_user_data"]["en"].format(fields=missing)
            }
        else:
            # Store user data in call state
            call_state["user_data"] = {
                "name": user_name,
                "email": user_email,
                "phone": user_phone
            }
            active_calls[call_id] = call_state

            # Call the booking API to get available days
            result = await get_available_days_from_api(tenant_id, call_state["user_data"])

            # Store days in call state for slot lookup later
            call_state["available_days"] = result.get("days", [])
            active_calls[call_id] = call_state

            logger.info(f"Got {len(result.get('days', []))} days from API", extra=log_extra)

    elif function_name == "get_available_slots":
        day_number = arguments.get("day_number")
        available_days = call_state.get("available_days", [])

        # Validate day number
        is_valid, error_msg = validate_day_number(day_number, available_days)
        if not is_valid:
            logger.warning(f"Invalid day selection: {error_msg}", extra=log_extra)
            result = {
                "error": True,
                "message": error_msg
            }
        else:
            # Get the selected day's date
            selected_day = available_days[int(day_number) - 1]
            selected_date = selected_day.get("date")
            call_state["selected_date"] = selected_date
            active_calls[call_id] = call_state

            logger.info(f"User selected day {day_number}: {selected_date}", extra=log_extra)

            # Call the booking API to get slots for that specific day
            result = await get_available_slots_from_api(tenant_id, call_state["user_data"], selected_date)

            # Store slots in call state for booking later
            call_state["available_slots"] = result.get("slots", [])
            active_calls[call_id] = call_state

            logger.info(f"Got {len(result.get('slots', []))} slots for {selected_date}", extra=log_extra)

    elif function_name == "book_appointment":
        slot_number = arguments.get("slot_number")
        available_slots = call_state.get("available_slots", [])

        # Validate slot number
        is_valid, error_msg = validate_slot_number(slot_number, available_slots)
        if not is_valid:
            logger.warning(f"Invalid slot selection: {error_msg}", extra=log_extra)
            result = {
                "success": False,
                "message": error_msg
            }
        else:
            # Get user data from call state
            user_data = call_state.get("user_data", {})

            # Validate we have user data
            if not user_data.get("name") or not user_data.get("email"):
                result = {
                    "success": False,
                    "message": VOICE_ERROR_MESSAGES["missing_contact_info"]["en"]
                }
            else:
                # Call the booking API to actually book
                result = await book_appointment_via_api(tenant_id, user_data, int(slot_number), available_slots)

                logger.info(f"Booking result: {result.get('success', False)}", extra=log_extra)

                # If booking successful, mark for silence-based hangup
                if result.get("success"):
                    call_state["booking_complete"] = True
                    call_state["hangup_task"] = None  # Will be set when AI finishes speaking
                    active_calls[call_id] = call_state
                    logger.info("Booking complete, will hang up after AI finishes and silence detected", extra=log_extra)

    else:
        logger.warning(f"Unknown function: {function_name}", extra=log_extra)
        result = {
            "error": True,
            "message": f"I don't recognize that function: {function_name}"
        }

    # Send function result back to OpenAI
    if result:
        function_output = {
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_item_id,
                "output": json.dumps(result)
            }
        }
        await ws.send(json.dumps(function_output))

        # Trigger response generation
        await ws.send(json.dumps({"type": "response.create"}))


async def get_available_days_from_api(tenant_id: str, user_data: dict) -> dict:
    """Get available days from the booking API."""
    logger.info(f"Calling booking API for days - tenant: {tenant_id}")

    if not BOOKING_WEBHOOK_URL:
        logger.error("BOOKING_WEBHOOK_URL not configured")
        return {
            "days": [],
            "message": VOICE_ERROR_MESSAGES["booking_system_unavailable"]["en"]
        }

    url = f"{BOOKING_WEBHOOK_URL}/voice/get-days"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json={
                    "tenant_id": tenant_id,
                    "user_data": user_data
                },
                timeout=float(VOICE_CONFIG["api_timeout_seconds"])
            )

            logger.info(f"Get-days API response: {response.status_code}")

            if response.status_code == 200:
                try:
                    data = response.json()
                    day_count = len(data.get('days', []))
                    logger.info(f"Got {day_count} days from API")
                    return data
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON response from get-days API: {e}")
                    return {
                        "days": [],
                        "message": VOICE_ERROR_MESSAGES["unexpected_response"]["en"]
                    }
            elif response.status_code == 404:
                logger.error(f"Booking API endpoint not found: {url}")
                return {
                    "days": [],
                    "message": VOICE_ERROR_MESSAGES["service_unavailable"]["en"]
                }
            elif response.status_code >= 500:
                logger.error(f"Booking API server error: {response.status_code}")
                return {
                    "days": [],
                    "message": VOICE_ERROR_MESSAGES["service_issues"]["en"]
                }
            else:
                logger.error(f"Booking API error: {response.status_code} - {response.text[:200]}")
                return {
                    "days": [],
                    "message": VOICE_ERROR_MESSAGES["generic_error"]["en"]
                }

    except httpx.TimeoutException:
        logger.error(f"Timeout calling get-days API: {url}")
        return {
            "days": [],
            "message": VOICE_ERROR_MESSAGES["timeout"]["en"]
        }

    except httpx.ConnectError as e:
        logger.error(f"Connection error calling get-days API: {e}")
        return {
            "days": [],
            "message": VOICE_ERROR_MESSAGES["connection_error"]["en"]
        }

    except httpx.HTTPError as e:
        logger.error(f"HTTP error calling get-days API: {type(e).__name__}: {e}")
        return {
            "days": [],
            "message": VOICE_ERROR_MESSAGES["network_error"]["en"]
        }

    except Exception as e:
        logger.error(f"Unexpected error calling get-days API: {type(e).__name__}: {e}")
        return {
            "days": [],
            "message": VOICE_ERROR_MESSAGES["generic_error"]["en"]
        }


async def get_available_slots_from_api(tenant_id: str, user_data: dict, preferred_date: str = None) -> dict:
    """Get available appointment slots from the booking API."""
    logger.info(f"Calling booking API for slots - tenant: {tenant_id}, date: {preferred_date}")

    if not BOOKING_WEBHOOK_URL:
        logger.error("BOOKING_WEBHOOK_URL not configured")
        return {
            "slots": [],
            "message": VOICE_ERROR_MESSAGES["booking_system_unavailable"]["en"]
        }

    url = f"{BOOKING_WEBHOOK_URL}/voice/get-slots"

    try:
        request_body = {
            "tenant_id": tenant_id,
            "user_data": user_data
        }
        # Add preferred_date if provided
        if preferred_date:
            request_body["preferred_date"] = preferred_date

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=request_body,
                timeout=float(VOICE_CONFIG["api_timeout_seconds"])
            )

            logger.info(f"Get-slots API response: {response.status_code}")

            if response.status_code == 200:
                try:
                    data = response.json()
                    slot_count = len(data.get('slots', []))
                    logger.info(f"Got {slot_count} slots from API")
                    return data
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON response from get-slots API: {e}")
                    return {
                        "slots": [],
                        "message": VOICE_ERROR_MESSAGES["unexpected_response"]["en"]
                    }
            elif response.status_code == 404:
                logger.error(f"Booking API endpoint not found: {url}")
                return {
                    "slots": [],
                    "message": VOICE_ERROR_MESSAGES["service_unavailable"]["en"]
                }
            elif response.status_code >= 500:
                logger.error(f"Booking API server error: {response.status_code}")
                return {
                    "slots": [],
                    "message": VOICE_ERROR_MESSAGES["service_issues"]["en"]
                }
            else:
                logger.error(f"Booking API error: {response.status_code} - {response.text[:200]}")
                return {
                    "slots": [],
                    "message": VOICE_ERROR_MESSAGES["generic_error"]["en"]
                }

    except httpx.TimeoutException:
        logger.error(f"Timeout calling get-slots API: {url}")
        return {
            "slots": [],
            "message": VOICE_ERROR_MESSAGES["timeout"]["en"]
        }

    except httpx.ConnectError as e:
        logger.error(f"Connection error calling get-slots API: {e}")
        return {
            "slots": [],
            "message": VOICE_ERROR_MESSAGES["connection_error"]["en"]
        }

    except httpx.HTTPError as e:
        logger.error(f"HTTP error calling get-slots API: {type(e).__name__}: {e}")
        return {
            "slots": [],
            "message": VOICE_ERROR_MESSAGES["network_error"]["en"]
        }

    except Exception as e:
        logger.error(f"Unexpected error calling get-slots API: {type(e).__name__}: {e}")
        return {
            "slots": [],
            "message": VOICE_ERROR_MESSAGES["generic_error"]["en"]
        }


async def book_appointment_via_api(tenant_id: str, user_data: dict, slot_number: int, available_slots: list) -> dict:
    """Book an appointment via the booking API."""
    logger.info(f"Calling booking API to book slot {slot_number} - tenant: {tenant_id}")

    if not BOOKING_WEBHOOK_URL:
        logger.error("BOOKING_WEBHOOK_URL not configured")
        return {
            "success": False,
            "message": VOICE_ERROR_MESSAGES["booking_system_unavailable"]["en"]
        }

    url = f"{BOOKING_WEBHOOK_URL}/voice/book"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json={
                    "tenant_id": tenant_id,
                    "user_data": user_data,
                    "slot_number": slot_number,
                    "available_slots": available_slots
                },
                timeout=float(VOICE_CONFIG["api_timeout_seconds"])
            )

            logger.info(f"Book API response: {response.status_code}")

            if response.status_code == 200:
                try:
                    data = response.json()
                    logger.info(f"Booking success: {data.get('success', False)}")
                    return data
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON response from book API: {e}")
                    return {
                        "success": False,
                        "message": VOICE_ERROR_MESSAGES["unexpected_response"]["en"]
                    }
            elif response.status_code == 404:
                logger.error(f"Booking API endpoint not found: {url}")
                return {
                    "success": False,
                    "message": VOICE_ERROR_MESSAGES["service_unavailable"]["en"]
                }
            elif response.status_code == 409:
                # Conflict - slot might have been taken
                logger.warning("Slot conflict - may have been booked by someone else")
                return {
                    "success": False,
                    "message": VOICE_ERROR_MESSAGES["slot_conflict"]["en"]
                }
            elif response.status_code >= 500:
                logger.error(f"Booking API server error: {response.status_code}")
                return {
                    "success": False,
                    "message": VOICE_ERROR_MESSAGES["service_issues"]["en"]
                }
            else:
                logger.error(f"Booking API error: {response.status_code} - {response.text[:200]}")
                return {
                    "success": False,
                    "message": VOICE_ERROR_MESSAGES["generic_error"]["en"]
                }

    except httpx.TimeoutException:
        logger.error(f"Timeout calling book API: {url}")
        return {
            "success": False,
            "message": VOICE_ERROR_MESSAGES["timeout"]["en"]
        }

    except httpx.ConnectError as e:
        logger.error(f"Connection error calling book API: {e}")
        return {
            "success": False,
            "message": VOICE_ERROR_MESSAGES["connection_error"]["en"]
        }

    except httpx.HTTPError as e:
        logger.error(f"HTTP error calling book API: {type(e).__name__}: {e}")
        return {
            "success": False,
            "message": VOICE_ERROR_MESSAGES["network_error"]["en"]
        }

    except Exception as e:
        logger.error(f"Unexpected error calling book API: {type(e).__name__}: {e}")
        return {
            "success": False,
            "message": VOICE_ERROR_MESSAGES["generic_error"]["en"]
        }


async def silence_hangup(call_id: str, silence_seconds: int = 3):
    """Wait for silence period, then hang up the call.

    This task is started when AI finishes speaking after booking.
    It gets cancelled if user starts speaking, and restarted when AI finishes again.
    """
    log_extra = {'call_id': call_id}
    logger.info(f"Silence timer started ({silence_seconds}s)", extra=log_extra)

    try:
        await asyncio.sleep(silence_seconds)

        # Check if call is still active before hanging up
        if call_id in active_calls:
            logger.info("Silence detected, hanging up call", extra=log_extra)
            await hangup_call(call_id)
        else:
            logger.info("Call already ended, skipping hangup", extra=log_extra)

    except asyncio.CancelledError:
        logger.info("Silence timer cancelled (user spoke)", extra=log_extra)
        raise  # Re-raise to properly handle cancellation


async def hangup_call(call_id: str):
    """Hang up the call via OpenAI API."""
    log_extra = {'call_id': call_id}
    logger.info("Hanging up call", extra=log_extra)

    url = f"{OPENAI_API_BASE}/realtime/calls/{call_id}/hangup"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}"
                },
                timeout=float(VOICE_CONFIG["hangup_timeout_seconds"])
            )

            if response.status_code == 200:
                logger.info("Call hung up successfully", extra=log_extra)
            elif response.status_code == 404:
                # Call already ended - not an error
                logger.info("Call already ended (404)", extra=log_extra)
            else:
                logger.error(f"Failed to hang up: {response.status_code} - {response.text}", extra=log_extra)

    except httpx.TimeoutException:
        logger.error("Timeout hanging up call", extra=log_extra)

    except httpx.HTTPError as e:
        logger.error(f"HTTP error hanging up call: {e}", extra=log_extra)

    except Exception as e:
        logger.error(f"Error hanging up call: {type(e).__name__}: {e}", extra=log_extra)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    logger.info(f"Starting voice server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)