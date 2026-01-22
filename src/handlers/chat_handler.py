"""
Chat Handler
Main Lambda handler for processing chat messages.
Orchestrates all services: tenant config, language detection, slot extraction, AI responses, and booking.
"""

import json
from typing import Any, Optional

from config.settings import BOOKING_STATES, BOOKING_CONFIG, API_CONFIG
from config.prompts import BOOKING_MESSAGES
from src.utils.logger import get_logger
from src.utils.language_detector import detect_language
from src.utils.slot_extractor import get_slot_extractor
from src.services.dynamo_service import get_dynamo_service
from src.services.openai_service import get_openai_service
from src.services.booking_service import get_booking_service

# Initialize logger
logger = get_logger(__name__)

# Booking flow states from config
BOOKING_STATE_NONE = BOOKING_STATES["none"]
BOOKING_STATE_AWAITING_DAY_SELECTION = BOOKING_STATES["awaiting_day_selection"]
BOOKING_STATE_SHOWING_SLOTS = BOOKING_STATES["showing_slots"]
BOOKING_STATE_AWAITING_SELECTION = BOOKING_STATES["awaiting_selection"]
BOOKING_STATE_CONFIRMED = BOOKING_STATES["confirmed"]


def lambda_handler(event: dict, context: Any) -> dict:
    """
    Main Lambda entry point for chat requests.
    Args:
        event: API Gateway event containing request data
        context: Lambda context object
    Returns:
        API Gateway response dictionary
    """
    logger.info("Chat handler invoked", event_keys=list(event.keys()))
    
    try:
        # Parse request
        request_data = _parse_request(event)
        
        if not request_data:
            return _error_response(400, "Invalid request body")
        
        tenant_id = request_data.get('tenant_id')
        session_id = request_data.get('session_id')
        user_message = request_data.get('message', '').strip()
        
        # Validate required fields
        if not tenant_id:
            return _error_response(400, "tenant_id is required")
        
        if not user_message:
            return _error_response(400, "message is required")
        
        # Set logging context
        logger.set_context(tenant_id=tenant_id, session_id=session_id or 'new')
        
        logger.info(
            "Processing chat request",
            user_message_length=len(user_message),
            has_session=bool(session_id)
        )
        
        # Process the message
        result = process_message(
            tenant_id=tenant_id,
            session_id=session_id,
            user_message=user_message
        )
        
        return _success_response(result)
        
    except ValueError as e:
        logger.error("Validation error", error=str(e))
        return _error_response(400, str(e))
        
    except Exception as e:
        logger.error("Unexpected error in chat handler", error=str(e), exc_info=True)
        return _error_response(500, "Internal server error")
    
    finally:
        logger.clear_context()


def process_message(
    tenant_id: str,
    session_id: Optional[str],
    user_message: str
) -> dict:
    """
    Process a user message and generate a response.
    Args:
        tenant_id: The tenant identifier
        session_id: Existing session ID or None for new session
        user_message: The user's message
    Returns:
        Response dictionary with assistant message and metadata
    """
    # Initialize services
    dynamo = get_dynamo_service()
    openai_service = get_openai_service()
    slot_extractor = get_slot_extractor()
    
    # Load tenant configuration
    tenant = dynamo.get_tenant(tenant_id)
    
    if not tenant:
        raise ValueError(f"Tenant not found: {tenant_id}")
    
    if not tenant.get('active', False):
        raise ValueError(f"Tenant is not active: {tenant_id}")
    
    logger.info(
        "Tenant loaded",
        tenant_name=tenant.get('name'),
        supported_languages=tenant.get('supported_languages')
    )
    
    # Create or retrieve session
    is_new_session = False
    if not session_id:
        session_id = dynamo.create_session(tenant_id)
        is_new_session = True
        logger.info("New session created", session_id=session_id)
    
    # Update logging context with session
    logger.set_context(tenant_id=tenant_id, session_id=session_id)
    
    # Get conversation history
    conversation_history = dynamo.get_conversation_history(session_id)

    logger.debug(
        "Conversation history loaded",
        message_count=len(conversation_history)
    )

    # Get current slot data and booking state
    session_metadata = dynamo.get_session_metadata(session_id)

    # Detect language - use session's established language if available
    session_language = session_metadata.get('detected_language')
    current_message_language = detect_language(user_message, session_id)

    # Persist language: once established, only change if strong evidence of switch
    if session_language:
        # Keep session language unless current message has strong indicators
        # Short messages (< 3 words) shouldn't trigger language change
        word_count = len(user_message.split())
        if word_count < 3:
            detected_language = session_language
            logger.debug(
                "Keeping session language for short message",
                session_language=session_language,
                word_count=word_count
            )
        else:
            # For longer messages, use the detected language
            detected_language = current_message_language
            if detected_language != session_language:
                logger.info(
                    "Language changed",
                    from_language=session_language,
                    to_language=detected_language
                )
    else:
        # First message - establish session language
        detected_language = current_message_language
        logger.info("Session language established", detected_language=detected_language)
    current_slots = session_metadata.get('slot_data', {})
    booking_state = session_metadata.get('booking_state', BOOKING_STATE_NONE)
    available_slots = session_metadata.get('available_slots', [])
    available_days = session_metadata.get('available_days', [])
    selected_date = session_metadata.get('selected_date', None)

    logger.info(
        "Current session state",
        collected_fields=list(current_slots.keys()),
        booking_state=booking_state,
        available_days_count=len(available_days),
        available_slots_count=len(available_slots),
        selected_date=selected_date
    )
    
    # Save user message to history
    dynamo.save_message(
        session_id=session_id,
        role='user',
        content=user_message,
        tenant_id=tenant_id,
        metadata={'detected_language': detected_language}
    )
    
    # Add current message to history for extraction
    updated_history = conversation_history + [{
        'role': 'user',
        'content': user_message
    }]
    
    # Extract slots from conversation
    new_slots = slot_extractor.extract_all(
        conversation_history=updated_history,
        current_slots=current_slots,
        session_id=session_id
    )
    
    # Update slots if new data extracted
    if new_slots:
        current_slots = {**current_slots, **new_slots}
        dynamo.update_slot_data(session_id, current_slots)
        logger.info(
            "Slot data updated",
            new_fields=list(new_slots.keys()),
            all_fields=list(current_slots.keys())
        )
    
    # Check slot completion status
    required_fields = tenant.get('required_fields', ['name', 'email', 'phone'])
    slot_status = slot_extractor.get_collection_status(current_slots, required_fields)
    
    logger.info(
        "Slot collection status",
        progress=slot_status['progress'],
        missing=slot_status['missing'],
        is_complete=slot_status['is_complete']
    )

    # Debug: Log booking flow decision
    logger.info(
        "Booking flow check",
        is_complete=slot_status['is_complete'],
        current_booking_state=booking_state,
        should_show_days=(slot_status['is_complete'] and booking_state == BOOKING_STATE_NONE)
    )

    # Handle booking flow
    booking_result = None
    booking_context = ""
    lang = detected_language if detected_language in ['en', 'es'] else 'en'

    # Check if user is selecting a time slot (after day selection)
    if booking_state == BOOKING_STATE_AWAITING_SELECTION and available_slots:
        booking_service = get_booking_service()
        selected_slot = booking_service.parse_slot_selection(user_message, len(available_slots))

        if selected_slot:
            logger.info("User selected slot", slot_index=selected_slot)

            # Book the appointment
            booking_result = booking_service.book_appointment(
                tenant_id=tenant_id,
                session_id=session_id,
                slot_index=selected_slot,
                available_slots=available_slots,
                user_data=current_slots,
                detected_language=detected_language
            )

            if booking_result.get('success'):
                booking_state = BOOKING_STATE_CONFIRMED
                slot_info = booking_result.get('slot', {})

                booking_context = BOOKING_MESSAGES["confirmation"][lang].format(
                    display=slot_info.get('display', 'N/A'),
                    name=current_slots.get('name', 'N/A'),
                    email=current_slots.get('email', 'N/A'),
                    phone=current_slots.get('phone', 'N/A')
                )
                # Clear available slots/days after booking
                available_slots = []
                available_days = []
                selected_date = None
            else:
                error_msg = booking_result.get('error', 'Unknown error')
                booking_context = BOOKING_MESSAGES["booking_error"][lang].format(error=error_msg)

    # Check if user is selecting a day
    elif booking_state == BOOKING_STATE_AWAITING_DAY_SELECTION and available_days:
        booking_service = get_booking_service()
        selected_day_index = booking_service.parse_day_selection(user_message, len(available_days))

        if selected_day_index:
            logger.info("User selected day", day_index=selected_day_index)

            # Get the selected day info
            selected_day_info = available_days[selected_day_index - 1]
            selected_date = selected_day_info["date"]

            # Build display name for the selected day
            if lang == "es":
                selected_day_display = f"{selected_day_info['day_name_es']}, {selected_day_info['day_number']} de {selected_day_info['month_name_es']}"
            else:
                selected_day_display = f"{selected_day_info['day_name_en']}, {selected_day_info['month_name_en']} {selected_day_info['day_number']}"

            # Get slots for that specific day
            try:
                available_slots = booking_service.get_available_slots(
                    tenant_id=tenant_id,
                    specific_date=selected_date,
                    max_slots=BOOKING_CONFIG["voice_max_slots"]
                )

                if available_slots:
                    booking_state = BOOKING_STATE_AWAITING_SELECTION
                    formatted_slots = booking_service.format_slots_for_display(
                        available_slots,
                        detected_language
                    )

                    booking_context = BOOKING_MESSAGES["show_availability"][lang].format(
                        selected_day=selected_day_display,
                        formatted_slots=formatted_slots
                    )
                else:
                    booking_context = BOOKING_MESSAGES["no_slots_available"][lang]

            except Exception as e:
                logger.error("Failed to get slots for day", error=str(e), exc_info=True)
                booking_context = BOOKING_MESSAGES["no_slots_available"][lang]

    # If all user info collected and not yet showing days, get available days
    if slot_status['is_complete'] and booking_state == BOOKING_STATE_NONE:
        logger.info("All user info complete, fetching available days...")
        try:
            booking_service = get_booking_service()
            logger.info("Booking service initialized successfully")
            available_days = booking_service.get_available_days(
                tenant_id=tenant_id,
                days_ahead=BOOKING_CONFIG["days_ahead"]
            )

            if available_days:
                booking_state = BOOKING_STATE_AWAITING_DAY_SELECTION
                formatted_days = booking_service.format_days_for_display(
                    available_days,
                    detected_language
                )

                booking_context = BOOKING_MESSAGES["show_available_days"][lang].format(
                    formatted_days=formatted_days
                )
            else:
                booking_context = BOOKING_MESSAGES["no_days_available"][lang]

        except Exception as e:
            logger.error("Failed to get available days", error=str(e), exc_info=True)
            booking_context = ""

    # Update session metadata with booking state and language
    _update_booking_state(dynamo, session_id, booking_state, available_slots, available_days, selected_date, detected_language)
    
    # Build enhanced system prompt with booking context
    system_prompt = tenant.get('system_prompt', '')
    if booking_context:
        system_prompt = system_prompt + booking_context
    
    # Generate AI response
    response = openai_service.generate_response(
        user_message=user_message,
        conversation_history=conversation_history,
        system_prompt=system_prompt,
        tenant_id=tenant_id,
        session_id=session_id,
        detected_language=detected_language,
        slot_data=current_slots
    )
    
    assistant_message = response['content']
    
    # Save assistant response to history
    dynamo.save_message(
        session_id=session_id,
        role='assistant',
        content=assistant_message,
        tenant_id=tenant_id,
        metadata={
            'tokens_used': response['usage']['total_tokens'],
            'slot_status': slot_status,
            'booking_state': booking_state
        }
    )
    
    # Build response
    result = {
        'session_id': session_id,
        'message': assistant_message,
        'detected_language': detected_language,
        'slot_status': {
            'collected': slot_status['collected_values'],
            'missing': slot_status['missing'],
            'is_complete': slot_status['is_complete']
        },
        'booking_state': booking_state,
        'is_new_session': is_new_session
    }
    
    # Add booking result if appointment was made
    if booking_result and booking_result.get('success'):
        result['booking'] = {
            'confirmed': True,
            'appointment_id': booking_result.get('appointment_id'),
            'slot': booking_result.get('slot')
        }
    
    # Add welcome context for new sessions
    if is_new_session:
        result['welcome_message'] = tenant.get('welcome_message', {}).get(
            detected_language,
            tenant.get('welcome_message', {}).get('en', '')
        )
    
    logger.info(
        "Chat response generated",
        response_length=len(assistant_message),
        tokens_used=response['usage']['total_tokens'],
        booking_state=booking_state
    )
    
    return result


def _update_booking_state(
    dynamo,
    session_id: str,
    booking_state: str,
    available_slots: list,
    available_days: list = None,
    selected_date: str = None,
    detected_language: str = None
) -> None:
    """
    Update the booking state in session metadata.
    Args:
        dynamo: DynamoDB service instance
        session_id: Session ID
        booking_state: Current booking state
        available_slots: List of available slots (if showing)
        available_days: List of available days (for day selection step)
        selected_date: The selected date (ISO format YYYY-MM-DD)
        detected_language: The detected/established session language
    """
    # Get current metadata
    history = dynamo.get_conversation_history(session_id, limit=1)

    if history:
        first_msg = history[0]
        metadata = first_msg.get('metadata', {})
        metadata['booking_state'] = booking_state
        metadata['available_slots'] = available_slots
        metadata['available_days'] = available_days if available_days is not None else []
        metadata['selected_date'] = selected_date
        if detected_language:
            metadata['detected_language'] = detected_language

        dynamo.conversations_table.update_item(
            Key={
                'session_id': session_id,
                'timestamp': first_msg['timestamp']
            },
            UpdateExpression='SET metadata = :meta',
            ExpressionAttributeValues={':meta': metadata}
        )


def _parse_request(event: dict) -> dict | None:
    """
    Parse the request body from API Gateway event.
    Args:
        event: API Gateway event
    Returns:
        Parsed request dictionary or None if invalid
    """
    try:
        # Handle different event formats
        body = event.get('body', '{}')
        
        # API Gateway may pass body as string
        if isinstance(body, str):
            body = json.loads(body) if body else {}
        
        # Extract tenant_id from path parameters if present
        path_params = event.get('pathParameters', {}) or {}
        if 'tenant_id' in path_params and 'tenant_id' not in body:
            body['tenant_id'] = path_params['tenant_id']
        
        logger.debug("Request parsed", body_keys=list(body.keys()))
        
        return body
        
    except json.JSONDecodeError as e:
        logger.error("Failed to parse request body", error=str(e))
        return None


def _success_response(data: dict) -> dict:
    """
    Build a successful API Gateway response.
    Args:
        data: Response data dictionary
    Returns:
        API Gateway response format
    """
    headers = {'Content-Type': 'application/json'}
    headers.update(API_CONFIG["cors_headers"])

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps(data)
    }


def _error_response(status_code: int, error_message: str) -> dict:
    """
    Build an error API Gateway response.
    Args:
        status_code: HTTP status code
        error_message: Error message
    Returns:
        API Gateway response format
    """
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