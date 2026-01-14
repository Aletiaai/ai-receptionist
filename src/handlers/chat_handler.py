"""
Chat Handler
Main Lambda handler for processing chat messages.
Orchestrates all services: tenant config, language detection, slot extraction, AI responses, and booking.
"""

import json
import os
from typing import Any, Optional

from src.utils.logger import get_logger
from src.utils.language_detector import detect_language
from src.utils.slot_extractor import get_slot_extractor
from src.services.dynamo_service import get_dynamo_service
from src.services.openai_service import get_openai_service
from src.services.booking_service import get_booking_service

# Initialize logger
logger = get_logger(__name__)

# Booking flow states
BOOKING_STATE_NONE = "none"
BOOKING_STATE_SHOWING_SLOTS = "showing_slots"
BOOKING_STATE_AWAITING_SELECTION = "awaiting_selection"
BOOKING_STATE_CONFIRMED = "confirmed"


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
    
    # Detect language
    detected_language = detect_language(user_message, session_id)
    
    # Get current slot data and booking state
    session_metadata = dynamo.get_session_metadata(session_id)
    current_slots = session_metadata.get('slot_data', {})
    booking_state = session_metadata.get('booking_state', BOOKING_STATE_NONE)
    available_slots = session_metadata.get('available_slots', [])
    
    logger.debug(
        "Current session state",
        collected_fields=list(current_slots.keys()),
        booking_state=booking_state
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
        should_show_slots=(slot_status['is_complete'] and booking_state == BOOKING_STATE_NONE)
    )
    
    # Handle booking flow
    booking_result = None
    booking_context = ""
    
    # Check if user is selecting a slot
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
                
                if detected_language == 'es':
                    booking_context = f"""

--- CITA CONFIRMADA ---
La cita ha sido reservada exitosamente:
- Fecha y hora: {slot_info.get('display', 'N/A')}
- Nombre: {current_slots.get('name', 'N/A')}
- Email: {current_slots.get('email', 'N/A')}
- Teléfono: {current_slots.get('phone', 'N/A')}

El usuario recibirá una invitación de calendario por correo electrónico.
Por favor confirma la cita al usuario y pregunta si necesita algo más.
--- FIN ---
"""
                else:
                    booking_context = f"""

--- APPOINTMENT CONFIRMED ---
The appointment has been successfully booked:
- Date and time: {slot_info.get('display', 'N/A')}
- Name: {current_slots.get('name', 'N/A')}
- Email: {current_slots.get('email', 'N/A')}
- Phone: {current_slots.get('phone', 'N/A')}

The user will receive a calendar invitation via email.
Please confirm the appointment to the user and ask if they need anything else.
--- END ---
"""
                # Clear available slots after booking
                available_slots = []
            else:
                error_msg = booking_result.get('error', 'Unknown error')
                if detected_language == 'es':
                    booking_context = f"\n\n[Error al reservar la cita: {error_msg}. Por favor intenta de nuevo.]\n"
                else:
                    booking_context = f"\n\n[Error booking appointment: {error_msg}. Please try again.]\n"
    
    # If all slots collected and not yet showing availability, get available slots
    if slot_status['is_complete'] and booking_state == BOOKING_STATE_NONE:
        logger.info("All slots complete, fetching availability...")
        try:
            booking_service = get_booking_service()
            logger.info("Booking service initialized successfully")
            available_slots = booking_service.get_available_slots(
                tenant_id=tenant_id,
                days_ahead=7,
                max_slots=5
            )
            
            if available_slots:
                booking_state = BOOKING_STATE_AWAITING_SELECTION
                formatted_slots = booking_service.format_slots_for_display(
                    available_slots,
                    detected_language
                )
                
                if detected_language == 'es':
                    booking_context = f"""

--- MOSTRAR DISPONIBILIDAD ---
Toda la información del usuario ha sido recopilada. Ahora muestra los horarios disponibles.

{formatted_slots}

Pide al usuario que seleccione un horario usando el número (1, 2, 3, etc.)
--- FIN ---
"""
                else:
                    booking_context = f"""

--- SHOW AVAILABILITY ---
All user information has been collected. Now show the available time slots.

{formatted_slots}

Ask the user to select a time slot by number (1, 2, 3, etc.)
--- END ---
"""
            else:
                if detected_language == 'es':
                    booking_context = "\n\n[No hay horarios disponibles esta semana. Disculpa al usuario y sugiere que llame directamente.]\n"
                else:
                    booking_context = "\n\n[No available slots this week. Apologize to the user and suggest they call directly.]\n"
                    
        except Exception as e:
            logger.error("Failed to get availability", error=str(e), exc_info=True)
            booking_context = ""
    
    # Update session metadata with booking state
    _update_booking_state(dynamo, session_id, booking_state, available_slots)
    
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
    available_slots: list
) -> None:
    """
    Update the booking state in session metadata.
    Args:
        dynamo: DynamoDB service instance
        session_id: Session ID
        booking_state: Current booking state
        available_slots: List of available slots (if showing)
    """
    # Get current metadata
    history = dynamo.get_conversation_history(session_id, limit=1)
    
    if history:
        first_msg = history[0]
        metadata = first_msg.get('metadata', {})
        metadata['booking_state'] = booking_state
        metadata['available_slots'] = available_slots
        
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
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'POST,OPTIONS'
        },
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
    
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'POST,OPTIONS'
        },
        'body': json.dumps({
            'error': error_message,
            'status_code': status_code
        })
    }