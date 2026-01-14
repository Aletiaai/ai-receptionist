"""
Voice Server for AI Receptionist
Handles OpenAI Realtime API webhooks for SIP calls.
"""

import os
import json
import asyncio
import hashlib
import hmac
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
import uvicorn
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
import websockets
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_WEBHOOK_SECRET = os.getenv("OPENAI_WEBHOOK_SECRET", "")
BOOKING_WEBHOOK_URL = os.getenv("BOOKING_WEBHOOK_URL", "")

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

app = FastAPI(title="AI Receptionist Voice Server")

# Store active calls
active_calls = {}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "active_calls": len(active_calls)
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
            print("❌ Invalid webhook signature")
            raise HTTPException(status_code=400, detail="Invalid signature")
    
    # Parse the event
    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    event_type = event.get("type")
    event_id = event.get("id")
    
    print(f"📥 Webhook received: {event_type} (ID: {event_id})")
    
    if event_type == "realtime.call.incoming":
        # Handle incoming call
        call_data = event.get("data", {})
        call_id = call_data.get("call_id")
        sip_headers = call_data.get("sip_headers", [])
        
        # Extract caller info from SIP headers
        from_number = None
        to_number = None
        for header in sip_headers:
            if header.get("name") == "From":
                from_number = header.get("value")
            elif header.get("name") == "To":
                to_number = header.get("value")
        
        print(f"📞 Incoming call: {call_id}")
        print(f"   From: {from_number}")
        print(f"   To: {to_number}")
        
        # Determine tenant based on called number (for now, use default)
        tenant_id = DEFAULT_TENANT
        
        # Accept the call in background
        background_tasks.add_task(accept_and_monitor_call, call_id, tenant_id, from_number)
        
        return JSONResponse(status_code=200, content={"status": "accepted"})
    
    return JSONResponse(status_code=200, content={"status": "ignored"})


def verify_webhook_signature(body: bytes, signature: str, timestamp: str) -> bool:
    """Verify OpenAI webhook signature."""
    if not OPENAI_WEBHOOK_SECRET:
        return True
    
    try:
        # Check timestamp is recent (within 5 minutes)
        ts = int(timestamp)
        if abs(time.time() - ts) > 300:
            return False
        
        # Verify signature
        signed_payload = f"{timestamp}.{body.decode()}"
        expected_sig = hmac.new(
            OPENAI_WEBHOOK_SECRET.encode(),
            signed_payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Signature format is "v1,signature"
        if signature.startswith("v1,"):
            actual_sig = signature[3:]
            return hmac.compare_digest(expected_sig, actual_sig)
        
        return False
    except Exception as e:
        print(f"Signature verification error: {e}")
        return False


async def accept_and_monitor_call(call_id: str, tenant_id: str, from_number: str):
    """Accept the call and monitor via WebSocket."""
    tenant = TENANTS.get(tenant_id, TENANTS[DEFAULT_TENANT])
    
    print(f"🎯 Accepting call {call_id} for tenant {tenant_id}")
    
    # Store call state
    active_calls[call_id] = {
        "tenant_id": tenant_id,
        "from_number": from_number,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "user_data": {},
        "available_slots": []
    }
    
    # Accept the call
    accept_url = f"{OPENAI_API_BASE}/realtime/calls/{call_id}/accept"
    accept_payload = {
        "type": "realtime",
        "model": "gpt-4o-realtime-preview-2024-12-17",
        "voice": tenant["voice"],
        "instructions": tenant["instructions"],
        "tools": TOOLS,
        "input_audio_format": "g711_ulaw",
        "output_audio_format": "g711_ulaw",
        "input_audio_transcription": {
            "model": "whisper-1"
        },
        "turn_detection": {
            "type": "server_vad",
            "threshold": 0.5,
            "prefix_padding_ms": 300,
            "silence_duration_ms": 500
        }
    }
    
    async with httpx.AsyncClient() as client:
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
            print(f"❌ Failed to accept call: {response.status_code} - {response.text}")
            del active_calls[call_id]
            return
        
        print(f"✅ Call accepted: {call_id}")
    
    # Monitor the call via WebSocket
    await monitor_call(call_id, tenant_id)


async def monitor_call(call_id: str, tenant_id: str):
    """Monitor call events via WebSocket."""
    ws_url = f"{OPENAI_REALTIME_WS}?call_id={call_id}"
    
    try:
        async with websockets.connect(
            ws_url,
            extra_headers={"Authorization": f"Bearer {OPENAI_API_KEY}"}
        ) as ws:
            print(f"🔌 WebSocket connected for call {call_id}")
            
            # Send initial response to greet the caller
            initial_response = {
                "type": "response.create",
                "response": {
                    "instructions": "Greet the caller warmly and ask how you can help them today."
                }
            }
            await ws.send(json.dumps(initial_response))
            
            # Listen for events
            async for message in ws:
                event = json.loads(message)
                event_type = event.get("type")
                
                # Log important events
                if event_type == "conversation.item.input_audio_transcription.completed":
                    transcript = event.get("transcript", "")
                    print(f"👤 User said: {transcript}")
                    
                elif event_type == "response.audio_transcript.done":
                    transcript = event.get("transcript", "")
                    print(f"🤖 Assistant said: {transcript}")
                    
                elif event_type == "response.function_call_arguments.done":
                    # Handle function calls
                    await handle_function_call(ws, call_id, event)
                    
                elif event_type == "error":
                    print(f"❌ Error: {event.get('error', {})}")
                    
                elif event_type == "session.closed":
                    print(f"📴 Session closed for call {call_id}")
                    break
                    
    except websockets.exceptions.ConnectionClosed:
        print(f"🔌 WebSocket disconnected for call {call_id}")
    except Exception as e:
        print(f"❌ WebSocket error: {e}")
    finally:
        # Cleanup
        if call_id in active_calls:
            del active_calls[call_id]
        print(f"👋 Call ended: {call_id}")


async def handle_function_call(ws, call_id: str, event: dict):
    """Handle function calls from the Realtime API."""
    function_name = event.get("name")
    call_item_id = event.get("call_id")  # This is the function call item ID
    arguments_str = event.get("arguments", "{}")
    
    try:
        arguments = json.loads(arguments_str)
    except json.JSONDecodeError:
        arguments = {}
    
    print(f"🔧 Function call: {function_name}")
    print(f"   Arguments: {arguments}")
    
    call_state = active_calls.get(call_id, {})
    tenant_id = call_state.get("tenant_id", DEFAULT_TENANT)
    
    result = None
    
    if function_name == "get_available_slots":
        # Store user data
        call_state["user_data"] = {
            "name": arguments.get("user_name"),
            "email": arguments.get("user_email"),
            "phone": arguments.get("user_phone")
        }
        
        # Call our existing booking API
        result = await get_available_slots(tenant_id, call_state["user_data"])
        call_state["available_slots"] = result.get("slots", [])
        
    elif function_name == "book_appointment":
        slot_number = arguments.get("slot_number", 1)
        user_data = {
            "name": arguments.get("user_name"),
            "email": arguments.get("user_email"),
            "phone": arguments.get("user_phone")
        }
        available_slots = call_state.get("available_slots", [])
        
        result = await book_appointment(tenant_id, user_data, slot_number, available_slots)
    
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


async def get_available_slots(tenant_id: str, user_data: dict) -> dict:
    """Get available appointment slots from booking API."""
    print(f"📅 Getting slots for tenant {tenant_id}")
    
    if BOOKING_WEBHOOK_URL:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{BOOKING_WEBHOOK_URL}/voice/get-slots",
                    json={
                        "tenant_id": tenant_id,
                        "user_data": user_data
                    },
                    timeout=30.0
                )
                if response.status_code == 200:
                    return response.json()
            except Exception as e:
                print(f"❌ Error getting slots: {e}")
    
    # Fallback: return mock slots if API not configured
    return {
        "slots": [
            {"number": 1, "display": "Monday, January 13th at 9:00 AM"},
            {"number": 2, "display": "Monday, January 13th at 10:00 AM"},
            {"number": 3, "display": "Tuesday, January 14th at 9:00 AM"},
            {"number": 4, "display": "Tuesday, January 14th at 2:00 PM"},
            {"number": 5, "display": "Wednesday, January 15th at 11:00 AM"}
        ],
        "message": "I have the following time slots available"
    }


async def book_appointment(tenant_id: str, user_data: dict, slot_number: int, available_slots: list) -> dict:
    """Book an appointment via booking API."""
    print(f"📝 Booking slot {slot_number} for tenant {tenant_id}")
    
    if BOOKING_WEBHOOK_URL:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{BOOKING_WEBHOOK_URL}/voice/book",
                    json={
                        "tenant_id": tenant_id,
                        "user_data": user_data,
                        "slot_number": slot_number,
                        "available_slots": available_slots
                    },
                    timeout=30.0
                )
                if response.status_code == 200:
                    return response.json()
            except Exception as e:
                print(f"❌ Error booking: {e}")
    
    # Fallback response
    slot_display = "your selected time"
    if available_slots and 0 < slot_number <= len(available_slots):
        slot_display = available_slots[slot_number - 1].get("display", slot_display)
    
    return {
        "success": True,
        "message": f"Your appointment has been booked for {slot_display}. You will receive a confirmation email shortly.",
        "appointment": {
            "slot": slot_display,
            "user": user_data
        }
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"🚀 Starting voice server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)