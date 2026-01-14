"""
Booking Service
Orchestrates the appointment booking flow.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.utils.logger import get_logger
from src.services.outlook_calendar_service import get_outlook_calendar_service
from src.services.dynamo_service import get_dynamo_service
from src.services.email_service import get_email_service

# Initialize logger
logger = get_logger(__name__)


class BookingService:
    """Service class for managing appointment bookings."""
    
    def __init__(self):
        """Initialize the booking service."""
        logger.info("Initializing Booking service")
        self.calendar_service = get_outlook_calendar_service()
        self.dynamo_service = get_dynamo_service()
        logger.info("Booking service initialized")
    
    def get_available_slots(
        self,
        tenant_id: str,
        days_ahead: int = 7,
        slot_duration_minutes: int = 30,
        max_slots: int = 10
    ) -> list:
        """
        Get available appointment slots for a tenant.
        Args:
            tenant_id: The tenant ID
            days_ahead: Number of days to look ahead
            slot_duration_minutes: Duration of each slot
            max_slots: Maximum number of slots to return
        Returns:
            List of available slot dictionaries
        """
        logger.info(
            "Getting available slots",
            tenant_id=tenant_id,
            days_ahead=days_ahead
        )
        
        # Get tenant configuration
        tenant = self.dynamo_service.get_tenant(tenant_id)
        
        if not tenant:
            logger.error("Tenant not found", tenant_id=tenant_id)
            return []
        
        # Get calendar ID from tenant config (if specified)
        calendar_id = tenant.get("calendar_id")
        
        # Get availability
        start_date = datetime.now(timezone.utc)
        end_date = start_date + timedelta(days=days_ahead)
        
        slots = self.calendar_service.get_availability(
            calendar_id=calendar_id,
            start_date=start_date,
            end_date=end_date,
            slot_duration_minutes=slot_duration_minutes
        )
        
        # Limit the number of slots returned
        limited_slots = slots[:max_slots]
        
        logger.info(
            "Available slots retrieved",
            tenant_id=tenant_id,
            total_slots=len(slots),
            returned_slots=len(limited_slots)
        )
        
        return limited_slots
    
    def format_slots_for_display(
        self,
        slots: list,
        language: str = "en"
    ) -> str:
        """
        Format available slots as a readable string for the AI to present.
        Args:
            slots: List of slot dictionaries
            language: Language code ('en' or 'es')
        Returns:
            Formatted string of available slots
        """
        if not slots:
            if language == "es":
                return "No hay horarios disponibles en los próximos días."
            return "No available slots in the coming days."
        
        if language == "es":
            header = "Horarios disponibles:\n"
        else:
            header = "Available time slots:\n"
        
        lines = []
        for i, slot in enumerate(slots, 1):
            # Parse the datetime for localized formatting
            slot_time = datetime.fromisoformat(slot["start"])
            
            if language == "es":
                # Spanish format
                days_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
                months_es = ["enero", "febrero", "marzo", "abril", "mayo", "junio", 
                            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
                
                day_name = days_es[slot_time.weekday()]
                month_name = months_es[slot_time.month - 1]
                time_str = slot_time.strftime("%I:%M %p")
                
                lines.append(f"{i}. {day_name}, {slot_time.day} de {month_name} a las {time_str}")
            else:
                # English format
                lines.append(f"{i}. {slot['display']}")
        
        return header + "\n".join(lines)
    
    def book_appointment(
        self,
        tenant_id: str,
        session_id: str,
        slot_index: int,
        available_slots: list,
        user_data: dict,
        detected_language: str = "en"
    ) -> dict:
        """
        Book an appointment for a user.
        Args:
            tenant_id: The tenant ID
            session_id: The conversation session ID
            slot_index: Index of the selected slot (1-based)
            available_slots: List of available slots
            user_data: User information (name, email, phone)
        Returns:
            Booking result dictionary
        """
        logger.info(
            "Booking appointment",
            tenant_id=tenant_id,
            session_id=session_id,
            slot_index=slot_index,
            user_email=user_data.get("email")
        )
        
        # Validate slot index
        if slot_index < 1 or slot_index > len(available_slots):
            logger.warning("Invalid slot index", slot_index=slot_index, max_slots=len(available_slots))
            return {
                "success": False,
                "error": "Invalid slot selection"
            }
        
        # Get the selected slot
        slot = available_slots[slot_index - 1]
        
        # Get tenant configuration
        tenant = self.dynamo_service.get_tenant(tenant_id)
        
        if not tenant:
            logger.error("Tenant not found", tenant_id=tenant_id)
            return {
                "success": False,
                "error": "Tenant configuration not found"
            }
        
        # Parse slot times
        start_time = datetime.fromisoformat(slot["start"])
        end_time = datetime.fromisoformat(slot["end"])
        
        # Create appointment subject
        tenant_name = tenant.get("name", tenant_id.capitalize())
        subject = f"Appointment - {user_data.get('name', 'Guest')} - {tenant_name}"
        
        # Build description
        description = f"""
Appointment Details:
- Name: {user_data.get('name', 'N/A')}
- Email: {user_data.get('email', 'N/A')}
- Phone: {user_data.get('phone', 'N/A')}
- Tenant: {tenant_name}
- Booked via: AI Receptionist
- Session ID: {session_id}
        """.strip()
        
        # Create calendar event
        calendar_id = tenant.get("calendar_id")
        
        result = self.calendar_service.create_appointment(
            subject=subject,
            start_time=start_time,
            end_time=end_time,
            attendee_email=user_data.get("email", ""),
            attendee_name=user_data.get("name", "Guest"),
            description=description,
            calendar_id=calendar_id
        )
        
        if result.get("success"):
            # Save appointment to DynamoDB
            appointment = self.dynamo_service.create_appointment(
                tenant_id=tenant_id,
                session_id=session_id,
                user_data=user_data,
                appointment_time=slot["start"]
            )
            
            # Add appointment details to result
            result["appointment_id"] = appointment.get("appointment_id")
            result["slot"] = slot
            result["user_data"] = user_data
            
            logger.info(
                "Appointment booked successfully",
                tenant_id=tenant_id,
                appointment_id=appointment.get("appointment_id"),
                event_id=result.get("event_id")
            )
            
            # Send email notifications
            self._send_booking_notifications(
                tenant=tenant,
                user_data=user_data,
                slot=slot,
                detected_language=detected_language
            )
        else:
            logger.error(
                "Failed to book appointment",
                tenant_id=tenant_id,
                error=result.get("error")
            )
        
        return result
    
    def parse_slot_selection(self, user_message: str, max_slots: int) -> Optional[int]:
        """
        Parse user's slot selection from their message.
        Args:
            user_message: The user's message
            max_slots: Maximum valid slot number
        Returns:
            Slot index (1-based) or None if not found
        """
        import re
        
        # Look for number in message
        numbers = re.findall(r'\b(\d+)\b', user_message)
        
        for num_str in numbers:
            num = int(num_str)
            if 1 <= num <= max_slots:
                logger.debug(f"Parsed slot selection: {num}")
                return num
        
        # Check for ordinal words
        ordinals = {
            "first": 1, "primero": 1, "primera": 1, "1st": 1,
            "second": 2, "segundo": 2, "segunda": 2, "2nd": 2,
            "third": 3, "tercero": 3, "tercera": 3, "3rd": 3,
            "fourth": 4, "cuarto": 4, "cuarta": 4, "4th": 4,
            "fifth": 5, "quinto": 5, "quinta": 5, "5th": 5,
        }
        
        message_lower = user_message.lower()
        for word, num in ordinals.items():
            if word in message_lower and num <= max_slots:
                logger.debug(f"Parsed ordinal slot selection: {num}")
                return num
        
        return None

    def _send_booking_notifications(
        self,
        tenant: dict,
        user_data: dict,
        slot: dict,
        detected_language: str = "en"
    ) -> None:
        """
        Send email notifications after successful booking.
        Args:
            tenant: Tenant configuration
            user_data: User information (name, email, phone)
            slot: Booked slot information
            detected_language: Language for user email ('en' or 'es')
        """
        try:
            email_service = get_email_service()
            tenant_name = tenant.get("name", "Appointment")
            
            # Parse slot for display
            from datetime import datetime
            slot_time = datetime.fromisoformat(slot["start"])
            
            if detected_language == "es":
                days_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
                months_es = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
                appointment_date = f"{days_es[slot_time.weekday()]}, {slot_time.day} de {months_es[slot_time.month - 1]} de {slot_time.year}"
            else:
                appointment_date = slot_time.strftime("%A, %B %d, %Y")
            
            appointment_time = slot_time.strftime("%I:%M %p")
            
            # Send confirmation to user
            logger.info(
                "Sending confirmation email to user",
                user_email=user_data.get("email"),
                tenant=tenant_name
            )
            
            user_result = email_service.send_appointment_confirmation(
                to_email=user_data.get("email", ""),
                to_name=user_data.get("name", ""),
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                tenant_name=tenant_name,
                language=detected_language
            )
            
            if user_result.get("success"):
                logger.info("User confirmation email sent successfully")
            else:
                logger.warning(
                    "Failed to send user confirmation email",
                    error=user_result.get("error")
                )
            
            # Send notification to admin (if admin_email configured)
            admin_email = tenant.get("admin_email")
            
            if admin_email:
                logger.info(
                    "Sending notification email to admin",
                    admin_email=admin_email,
                    tenant=tenant_name
                )
                
                admin_result = email_service.send_admin_notification(
                    admin_email=admin_email,
                    user_name=user_data.get("name", ""),
                    user_email=user_data.get("email", ""),
                    user_phone=user_data.get("phone", ""),
                    appointment_date=appointment_date,
                    appointment_time=appointment_time,
                    tenant_name=tenant_name
                )
                
                if admin_result.get("success"):
                    logger.info("Admin notification email sent successfully")
                else:
                    logger.warning(
                        "Failed to send admin notification email",
                        error=admin_result.get("error")
                    )
            else:
                logger.debug("No admin email configured, skipping admin notification")
                
        except Exception as e:
            # Don't fail the booking if email fails
            logger.error(
                "Failed to send booking notifications",
                error=str(e),
                exc_info=True
            )

# Singleton instance
_booking_service = None


def get_booking_service() -> BookingService:
    """Get or create the Booking service singleton."""
    global _booking_service
    if _booking_service is None:
        logger.debug("Creating new Booking service instance")
        _booking_service = BookingService()
    return _booking_service