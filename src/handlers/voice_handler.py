"""
Voice Handler
Lambda handlers for voice-related endpoints.
Called by the voice server (Fargate) during phone calls.
"""

import json
from typing import Any

from config.settings import BOOKING_CONFIG, API_CONFIG
from config.prompts import VOICE_ERROR_MESSAGES
from src.utils.logger import get_logger
from src.services.dynamo_service import get_dynamo_service
from src.services.booking_service import get_booking_service

# Initialize logger
logger = get_logger(__name__)


def voice_get_days_handler(event: dict, context: Any) -> dict:
    """
    Get available days for voice booking.
    Called by the voice server when user provides their information.

    Args:
        event: API Gateway event
        context: Lambda context

    Returns:
        API Gateway response with available days
    """
    logger.info("Voice get days handler invoked")

    try:
        # Parse request
        body = _parse_body(event)

        tenant_id = body.get('tenant_id', 'consulate')
        user_data = body.get('user_data', {})

        logger.info(
            "Getting days for voice",
            tenant_id=tenant_id,
            user_name=user_data.get('name')
        )

        # Get booking service
        booking_service = get_booking_service()

        # Get available days
        days = booking_service.get_available_days(
            tenant_id=tenant_id,
            days_ahead=BOOKING_CONFIG["days_ahead"]
        )

        # Format days for voice
        formatted_days = []
        for i, day in enumerate(days, 1):
            formatted_days.append({
                "number": i,
                "date": day.get('date', ''),
                "display_en": f"{day.get('day_name_en', '')} {day.get('month_name_en', '')} {day.get('day_number', '')}",
                "display_es": f"{day.get('day_name_es', '')} {day.get('day_number', '')} de {day.get('month_name_es', '')}",
                "slot_count": day.get('slot_count', 0)
            })

        # Build response message
        if formatted_days:
            day_descriptions = ". ".join([f"Option {d['number']} is {d['display_en']}" for d in formatted_days])
            message = VOICE_ERROR_MESSAGES["days_available"]["en"].format(day_descriptions=day_descriptions)
        else:
            message = VOICE_ERROR_MESSAGES["no_days_week"]["en"]

        return _success_response({
            "days": formatted_days,
            "message": message
        })

    except Exception as e:
        logger.error("Error in voice get days", error=str(e), exc_info=True)
        return _error_response(500, str(e))


def voice_get_slots_handler(event: dict, context: Any) -> dict:
    """
    Get available appointment slots for voice booking.
    Called by the voice server after user selects a day.

    Args:
        event: API Gateway event
        context: Lambda context

    Returns:
        API Gateway response with available slots
    """
    logger.info("Voice get slots handler invoked")

    try:
        # Parse request
        body = _parse_body(event)

        tenant_id = body.get('tenant_id', 'consulate')
        user_data = body.get('user_data', {})
        preferred_date = body.get('preferred_date')  # Optional: specific date to query

        logger.info(
            "Getting slots for voice",
            tenant_id=tenant_id,
            user_name=user_data.get('name'),
            preferred_date=preferred_date
        )

        # Get booking service
        booking_service = get_booking_service()

        # Get available slots (for specific date if provided)
        slots = booking_service.get_available_slots(
            tenant_id=tenant_id,
            days_ahead=BOOKING_CONFIG["days_ahead"],
            max_slots=BOOKING_CONFIG["voice_max_slots"],
            specific_date=preferred_date
        )

        # Format slots for voice
        formatted_slots = []
        for i, slot in enumerate(slots, 1):
            formatted_slots.append({
                "number": i,
                "display": slot.get('display', ''),
                "start": slot.get('start', ''),
                "end": slot.get('end', '')
            })

        # Build response message
        if formatted_slots:
            slot_descriptions = ". ".join([f"Option {s['number']} is {s['display']}" for s in formatted_slots])
            message = VOICE_ERROR_MESSAGES["slots_available"]["en"].format(slot_descriptions=slot_descriptions)
        else:
            message = VOICE_ERROR_MESSAGES["no_slots_week"]["en"]

        return _success_response({
            "slots": formatted_slots,
            "message": message
        })

    except Exception as e:
        logger.error("Error in voice get slots", error=str(e), exc_info=True)
        return _error_response(500, str(e))


def voice_book_handler(event: dict, context: Any) -> dict:
    """
    Book an appointment via voice.
    Called by the voice server when user selects a slot.
    
    Args:
        event: API Gateway event
        context: Lambda context
    
    Returns:
        API Gateway response with booking result
    """
    logger.info("Voice book handler invoked")
    
    try:
        # Parse request
        body = _parse_body(event)
        
        tenant_id = body.get('tenant_id', 'consulate')
        user_data = body.get('user_data', {})
        slot_number = body.get('slot_number', 1)
        available_slots = body.get('available_slots', [])
        
        logger.info(
            "Booking via voice",
            tenant_id=tenant_id,
            user_name=user_data.get('name'),
            slot_number=slot_number
        )
        
        # Validate slot selection
        if not available_slots:
            return _success_response({
                "success": False,
                "message": VOICE_ERROR_MESSAGES["no_slots_provided"]["en"]
            })

        if slot_number < 1 or slot_number > len(available_slots):
            return _success_response({
                "success": False,
                "message": VOICE_ERROR_MESSAGES["invalid_slot_number"]["en"].format(max_slots=len(available_slots))
            })
        
        # Get the selected slot
        selected_slot = available_slots[slot_number - 1]
        
        # Convert to format expected by booking service
        formatted_slots = []
        for slot in available_slots:
            formatted_slots.append({
                "start": slot.get('start', ''),
                "end": slot.get('end', ''),
                "display": slot.get('display', '')
            })
        
        # Create a session for this booking
        dynamo = get_dynamo_service()
        session_id = dynamo.create_session(tenant_id)
        
        # Detect language (default based on tenant)
        detected_language = 'es' if tenant_id == 'consulate' else 'en'
        
        # Book the appointment
        booking_service = get_booking_service()
        
        result = booking_service.book_appointment(
            tenant_id=tenant_id,
            session_id=session_id,
            slot_index=slot_number,
            available_slots=formatted_slots,
            user_data={
                'name': user_data.get('name', ''),
                'email': user_data.get('email', ''),
                'phone': user_data.get('phone', '')
            },
            detected_language=detected_language
        )
        
        if result.get('success'):
            slot_display = selected_slot.get('display', 'your selected time')
            user_email = user_data.get('email', 'your email address')

            message = VOICE_ERROR_MESSAGES["booking_confirmation"]["en"].format(
                slot_display=slot_display,
                user_email=user_email
            )

            return _success_response({
                "success": True,
                "message": message,
                "appointment": {
                    "slot": slot_display,
                    "user": user_data,
                    "appointment_id": result.get('appointment_id')
                }
            })
        else:
            error_msg = result.get('error', 'Please try again.')
            return _success_response({
                "success": False,
                "message": VOICE_ERROR_MESSAGES["booking_failed"]["en"].format(error=error_msg)
            })
        
    except Exception as e:
        logger.error("Error in voice book", error=str(e), exc_info=True)
        return _error_response(500, str(e))


# ==================== Helper Functions ====================

def _parse_body(event: dict) -> dict:
    """Parse request body from API Gateway event."""
    body = event.get('body', '{}')
    if isinstance(body, str):
        return json.loads(body) if body else {}
    return body


def _success_response(data: dict) -> dict:
    """Build a successful API Gateway response."""
    headers = {'Content-Type': 'application/json'}
    headers.update(API_CONFIG["cors_headers"])

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps(data)
    }


def _error_response(status_code: int, error_message: str) -> dict:
    """Build an error API Gateway response."""
    logger.warning(
        "Returning error response",
        status_code=status_code,
        error_detail=error_message
    )

    headers = {'Content-Type': 'application/json'}
    headers.update(API_CONFIG["cors_headers"])

    return {
        'statusCode': status_code,
        'headers': headers,
        'body': json.dumps({
            'error': error_message,
            'status_code': status_code
        })
    }