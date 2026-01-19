"""
Voice Server for AI Receptionist
Handles OpenAI Realtime API webhooks for SIP calls.
"""

import os
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(call_id)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class CallContextFilter(logging.Filter):
    """Add call_id to log records."""
    def filter(self, record):
        if not hasattr(record, 'call_id'):
            record.call_id = 'no-call'
        return True


logger.addFilter(CallContextFilter())

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_WEBHOOK_SECRET = os.getenv("OPENAI_WEBHOOK_SECRET", "")
BOOKING_WEBHOOK_URL = os.getenv("BOOKING_WEBHOOK_URL", "")

# Stale call timeout (seconds) - calls older than this will be cleaned up
STALE_CALL_TIMEOUT = int(os.getenv("STALE_CALL_TIMEOUT", "1800"))  # 30 minutes default

# OpenAI API endpoints
OPENAI_API_BASE = "https://api.openai.com/v1"
OPENAI_REALTIME_WS = "wss://api.openai.com/v1/realtime"

# Tenant configurations
TENANTS = {
    "consulate": {
        "name": "Consulate Services",
        "voice": "alloy",  # Female voice
        "language_default": "es",
        "business_hours": {"start": 9, "end": 17},
        "instructions": """You are a friendly and professional virtual receptionist for the Consulate.

Your primary goal is to help callers schedule appointments. You speak both Spanish and English fluently.

IMPORTANT RULES:
1. Start by greeting the caller warmly in Spanish first, then briefly in English
2. Detect which language they prefer based on their response and continue in that language
3. Collect information ONE piece at a time in this order:
    - Full name (ask them to spell it if unclear)
    - Email address (spell it back to confirm)
    - Phone number (repeat it back to confirm)
4. Once you have all three pieces of information, call the get_available_slots function
5. Present the available time slots clearly (e.g., "Option 1 is Monday January 13th at 9 AM")
6. When they choose a slot, call the book_appointment function
7. Confirm the booking details and thank them

Keep responses SHORT and conversational - this is a phone call.
Be patient if they need to repeat information.
If you don't understand something, politely ask them to repeat."""
    },
    "realestate": {
        "name": "Real Estate Agency", 
        "voice": "alloy",  # Female voice
        "language_default": "en",
        "business_hours": {"start": 8, "end": 20},
        "instructions": """You are a friendly and enthusiastic virtual assistant for a Real Estate Agency.

Your primary goal is to help callers schedule property viewings. You speak both English and Spanish fluently.

IMPORTANT RULES:
1. Start by greeting the caller warmly in English first, then briefly in Spanish
2. Detect which language they prefer based on their response and continue in that language
3. Collect information ONE piece at a time in this order:
    - Full name (ask them to spell it if unclear)
    - Email address (spell it back to confirm)
    - Phone number (repeat it back to confirm)
4. Once you have all three pieces of information, call the get_available_slots function
5. Present the available viewing slots clearly (e.g., "Option 1 is Monday January 13th at 9 AM")
6. When they choose a slot, call the book_appointment function
7. Confirm the booking details and thank them

Keep responses SHORT and conversational - this is a phone call.
Be energetic but professional.
If you don't understand something, politely ask them to repeat."""
    }
}

# Default tenant (can be determined by phone number later)
DEFAULT_TENANT = "consulate"


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
            await asyncio.sleep(300)  # Check every 5 minutes
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
        "name": "get_available_slots",
        "description": "Get available appointment time slots. Call this after collecting the caller's name, email, and phone number.",
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
        "name": "book_appointment",
        "description": "Book an appointment for the caller. Call this after they select a time slot.",
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
                },
                "slot_number": {
                    "type": "integer",
                    "description": "The number of the selected time slot (1, 2, 3, etc.)"
                }
            },
            "required": ["user_name", "user_email", "user_phone", "slot_number"]
        }
    }
]

app = FastAPI(title="AI Receptionist Voice Server", lifespan=lifespan)

# Store active calls (call_id -> call_state dict)
# Thread-safe for async operations within a single process
active_calls = {}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):  # noqa: ARG001
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
            "available_slots": [],
            "status": "accepting"  # Track call lifecycle
        }

        accept_payload = {
            "type": "realtime",
            "model": "gpt-realtime-2025-08-28",
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
                    timeout=30.0
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


async def monitor_call(call_id: str, tenant_id: str):  # noqa: ARG001 (tenant_id used for logging context)
    """Monitor call events via WebSocket."""
    ws_url = f"{OPENAI_REALTIME_WS}?call_id={call_id}"
    log_extra = {'call_id': call_id}
    _ = tenant_id  # Available in call_state, kept in signature for potential future use

    # Track reconnection attempts
    max_reconnect_attempts = 3
    reconnect_attempt = 0

    while reconnect_attempt < max_reconnect_attempts:
        try:
            async with websockets.connect(
                ws_url,
                extra_headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                ping_interval=20,  # Keep connection alive
                ping_timeout=10,
                close_timeout=5
            ) as ws:
                logger.info("WebSocket connected", extra=log_extra)
                reconnect_attempt = 0  # Reset on successful connection

                # Send initial greeting prompt
                initial_response = {
                    "type": "response.create",
                    "response": {
                        "instructions": "Greet the caller warmly and ask how you can help them today."
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

                    # Log transcriptions
                    if event_type == "conversation.item.input_audio_transcription.completed":
                        transcript = event.get("transcript", "")
                        logger.info(f"User said: {transcript[:100]}{'...' if len(transcript) > 100 else ''}", extra=log_extra)

                    elif event_type == "response.audio_transcript.done":
                        transcript = event.get("transcript", "")
                        logger.info(f"Assistant said: {transcript[:100]}{'...' if len(transcript) > 100 else ''}", extra=log_extra)

                        # Check if booking is complete and assistant has finished speaking
                        call_state = active_calls.get(call_id, {})
                        if call_state.get("booking_complete"):
                            # Check if this was a goodbye/confirmation message
                            goodbye_phrases = ["goodbye", "thank you for calling", "have a great day",
                                            "adiós", "gracias por llamar", "que tenga un buen día"]
                            if any(phrase in transcript.lower() for phrase in goodbye_phrases):
                                logger.info("Booking complete, ending call", extra=log_extra)
                                # Wait a moment for the audio to finish playing
                                await asyncio.sleep(2)
                                await hangup_call(call_id)
                                return  # Exit the function completely

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
                await asyncio.sleep(1)  # Brief delay before reconnect

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

    if function_name == "get_available_slots":
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
                "message": f"I still need your {missing} before I can check availability."
            }
        else:
            # Store user data in call state
            call_state["user_data"] = {
                "name": user_name,
                "email": user_email,
                "phone": user_phone
            }
            active_calls[call_id] = call_state

            # Call the booking API to get real slots
            result = await get_available_slots_from_api(tenant_id, call_state["user_data"])

            # Store slots in call state for booking later
            call_state["available_slots"] = result.get("slots", [])
            active_calls[call_id] = call_state

            logger.info(f"Got {len(result.get('slots', []))} slots from API", extra=log_extra)

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
            # Get user data from arguments or call state
            user_data = {
                "name": arguments.get("user_name") or call_state.get("user_data", {}).get("name", ""),
                "email": arguments.get("user_email") or call_state.get("user_data", {}).get("email", ""),
                "phone": arguments.get("user_phone") or call_state.get("user_data", {}).get("phone", "")
            }

            # Validate we have user data
            if not user_data.get("name") or not user_data.get("email"):
                result = {
                    "success": False,
                    "message": "I don't have your contact information. Let me get your name and email first."
                }
            else:
                # Call the booking API to actually book
                result = await book_appointment_via_api(tenant_id, user_data, int(slot_number), available_slots)

                logger.info(f"Booking result: {result.get('success', False)}", extra=log_extra)

                # If booking successful, mark for hangup after response
                if result.get("success"):
                    call_state["booking_complete"] = True
                    active_calls[call_id] = call_state

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


async def get_available_slots_from_api(tenant_id: str, user_data: dict) -> dict:
    """Get available appointment slots from the booking API."""
    logger.info(f"Calling booking API for slots - tenant: {tenant_id}")

    if not BOOKING_WEBHOOK_URL:
        logger.error("BOOKING_WEBHOOK_URL not configured")
        return {
            "slots": [],
            "message": "I'm sorry, the booking system is not configured. Please call back later."
        }

    url = f"{BOOKING_WEBHOOK_URL}/voice/get-slots"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json={
                    "tenant_id": tenant_id,
                    "user_data": user_data
                },
                timeout=30.0
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
                        "message": "I'm sorry, I received an unexpected response. Please try again."
                    }
            elif response.status_code == 404:
                logger.error(f"Booking API endpoint not found: {url}")
                return {
                    "slots": [],
                    "message": "I'm sorry, the scheduling service is currently unavailable."
                }
            elif response.status_code >= 500:
                logger.error(f"Booking API server error: {response.status_code}")
                return {
                    "slots": [],
                    "message": "I'm sorry, the scheduling service is experiencing issues. Please try again later."
                }
            else:
                logger.error(f"Booking API error: {response.status_code} - {response.text[:200]}")
                return {
                    "slots": [],
                    "message": "I'm sorry, I couldn't retrieve the available times. Please try again."
                }

    except httpx.TimeoutException:
        logger.error(f"Timeout calling get-slots API: {url}")
        return {
            "slots": [],
            "message": "I'm sorry, the request timed out. Please try again in a moment."
        }

    except httpx.ConnectError as e:
        logger.error(f"Connection error calling get-slots API: {e}")
        return {
            "slots": [],
            "message": "I'm sorry, I couldn't connect to the scheduling service. Please try again later."
        }

    except httpx.HTTPError as e:
        logger.error(f"HTTP error calling get-slots API: {type(e).__name__}: {e}")
        return {
            "slots": [],
            "message": "I'm sorry, there was a network issue. Please try again."
        }

    except Exception as e:
        logger.error(f"Unexpected error calling get-slots API: {type(e).__name__}: {e}")
        return {
            "slots": [],
            "message": "I'm sorry, something went wrong. Please try again later or call back."
        }


async def book_appointment_via_api(tenant_id: str, user_data: dict, slot_number: int, available_slots: list) -> dict:
    """Book an appointment via the booking API."""
    logger.info(f"Calling booking API to book slot {slot_number} - tenant: {tenant_id}")

    if not BOOKING_WEBHOOK_URL:
        logger.error("BOOKING_WEBHOOK_URL not configured")
        return {
            "success": False,
            "message": "I'm sorry, the booking system is not configured. Please call back later."
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
                timeout=30.0
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
                        "message": "I'm sorry, I received an unexpected response. Please try again."
                    }
            elif response.status_code == 404:
                logger.error(f"Booking API endpoint not found: {url}")
                return {
                    "success": False,
                    "message": "I'm sorry, the booking service is currently unavailable."
                }
            elif response.status_code == 409:
                # Conflict - slot might have been taken
                logger.warning("Slot conflict - may have been booked by someone else")
                return {
                    "success": False,
                    "message": "I'm sorry, that time slot was just booked by someone else. Would you like to choose a different time?"
                }
            elif response.status_code >= 500:
                logger.error(f"Booking API server error: {response.status_code}")
                return {
                    "success": False,
                    "message": "I'm sorry, the booking service is experiencing issues. Please try again later."
                }
            else:
                logger.error(f"Booking API error: {response.status_code} - {response.text[:200]}")
                return {
                    "success": False,
                    "message": "I'm sorry, I couldn't complete the booking. Please try again."
                }

    except httpx.TimeoutException:
        logger.error(f"Timeout calling book API: {url}")
        return {
            "success": False,
            "message": "I'm sorry, the booking request timed out. Please try again in a moment."
        }

    except httpx.ConnectError as e:
        logger.error(f"Connection error calling book API: {e}")
        return {
            "success": False,
            "message": "I'm sorry, I couldn't connect to the booking service. Please try again later."
        }

    except httpx.HTTPError as e:
        logger.error(f"HTTP error calling book API: {type(e).__name__}: {e}")
        return {
            "success": False,
            "message": "I'm sorry, there was a network issue. Please try again."
        }

    except Exception as e:
        logger.error(f"Unexpected error calling book API: {type(e).__name__}: {e}")
        return {
            "success": False,
            "message": "I'm sorry, something went wrong. Please try again later or call back."
        }


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
                timeout=10.0
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