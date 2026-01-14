"""
Outlook Calendar Service
Handles calendar operations via Microsoft Graph API.
Tokens are stored and retrieved from DynamoDB.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo
import requests
import msal
from dotenv import load_dotenv

from src.utils.logger import get_logger
from src.services.dynamo_service import get_dynamo_service

# Load environment variables
load_dotenv()

# Initialize logger
logger = get_logger(__name__)

# Configuration
CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
TENANT_ID = os.getenv("AZURE_TENANT_ID")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["https://graph.microsoft.com/.default"]
GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"

DEFAULT_TIMEZONE = os.getenv("TIMEZONE", "America/Mexico_City")

# Token storage configuration
TOKEN_TENANT_ID = "global"
TOKEN_PROVIDER = "outlook"


class OutlookCalendarService:
    """Service class for Outlook Calendar operations via Microsoft Graph API."""
    
    def __init__(self):
        """Initialize the Outlook Calendar service."""
        logger.info("Initializing Outlook Calendar service")
        
        if not all([CLIENT_ID, CLIENT_SECRET, TENANT_ID]):
            logger.error("Missing Azure credentials")
            raise ValueError("Azure credentials not configured")
        
        self.app = msal.ConfidentialClientApplication(
            CLIENT_ID,
            authority=AUTHORITY,
            client_credential=CLIENT_SECRET
        )
        
        self.dynamo_service = get_dynamo_service()
        self.access_token = None
        self._load_and_refresh_token()
        
        logger.info("Outlook Calendar service initialized")
    
    def _load_and_refresh_token(self) -> None:
        """Load token from DynamoDB and refresh if needed."""
        logger.debug("Loading OAuth token from DynamoDB")
        
        token_data = self.dynamo_service.get_oauth_token(TOKEN_TENANT_ID, TOKEN_PROVIDER)
        
        if not token_data:
            logger.error("No OAuth token found in DynamoDB")
            raise ValueError("OAuth token not found. Run auth_outlook.py first.")
        
        refresh_token = token_data.get("refresh_token")
        
        if not refresh_token:
            logger.error("No refresh token in token data")
            raise ValueError("No refresh token. Run auth_outlook.py again.")
        
        # Use refresh token to get new access token
        logger.debug("Refreshing access token")
        
        result = self.app.acquire_token_by_refresh_token(
            refresh_token,
            scopes=["Calendars.ReadWrite", "User.Read"]
        )
        
        if "access_token" in result:
            self.access_token = result["access_token"]
            
            # Update stored tokens in DynamoDB
            token_data["access_token"] = result["access_token"]
            if "refresh_token" in result:
                token_data["refresh_token"] = result["refresh_token"]
            
            self.dynamo_service.save_oauth_token(TOKEN_TENANT_ID, TOKEN_PROVIDER, token_data)
            
            logger.info("Access token refreshed and saved to DynamoDB")
        else:
            logger.error(f"Token refresh failed: {result.get('error_description')}")
            raise ValueError("Failed to refresh token. Run auth_outlook.py again.")
    
    def _get_headers(self) -> dict:
        """Get headers for Graph API requests."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
    
    def get_calendars(self) -> list:
        """
        Get list of available calendars.
        
        Returns:
            List of calendar objects
        """
        logger.debug("Fetching calendars")
        
        url = f"{GRAPH_API_BASE}/me/calendars"
        response = requests.get(url, headers=self._get_headers())
        
        if response.status_code == 200:
            calendars = response.json().get("value", [])
            logger.info(f"Found {len(calendars)} calendars")
            return calendars
        else:
            logger.error(f"Failed to fetch calendars: {response.status_code} - {response.text}")
            return []
    
    def get_availability(
        self,
        calendar_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        slot_duration_minutes: int = 30
    ) -> list:
        """
        Get available time slots for booking.
        
        Args:
            calendar_id: Calendar ID (None for primary calendar)
            start_date: Start of date range (default: today)
            end_date: End of date range (default: 7 days from now)
            slot_duration_minutes: Duration of each slot in minutes
        
        Returns:
            List of available time slots
        """
        if start_date is None:
            start_date = datetime.now(timezone.utc)
        
        if end_date is None:
            end_date = start_date + timedelta(days=7)
        
        logger.info(
            "Checking calendar availability",
            calendar_id=calendar_id or "primary",
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat()
        )
        
        # Get existing events
        events = self._get_events(calendar_id, start_date, end_date)
        
        # Generate available slots
        available_slots = self._calculate_available_slots(
            events=events,
            start_date=start_date,
            end_date=end_date,
            slot_duration_minutes=slot_duration_minutes
        )
        
        logger.info(f"Found {len(available_slots)} available slots")
        
        return available_slots
    
    def _get_events(
        self,
        calendar_id: Optional[str],
        start_date: datetime,
        end_date: datetime
    ) -> list:
        """
        Get events from calendar within date range.
        
        Args:
            calendar_id: Calendar ID (None for primary)
            start_date: Start of range
            end_date: End of range
        
        Returns:
            List of event objects
        """
        if calendar_id:
            url = f"{GRAPH_API_BASE}/me/calendars/{calendar_id}/events"
        else:
            url = f"{GRAPH_API_BASE}/me/events"
        
        params = {
            "$filter": f"start/dateTime ge '{start_date.isoformat()}' and end/dateTime le '{end_date.isoformat()}'",
            "$orderby": "start/dateTime",
            "$select": "subject,start,end,isCancelled"
        }
        
        response = requests.get(url, headers=self._get_headers(), params=params)
        
        if response.status_code == 200:
            events = response.json().get("value", [])
            logger.debug(f"Found {len(events)} existing events")
            return events
        else:
            logger.error(f"Failed to fetch events: {response.status_code} - {response.text}")
            return []
    
    def _calculate_available_slots(
        self,
        events: list,
        start_date: datetime,
        end_date: datetime,
        slot_duration_minutes: int = 30,
        business_hours_start: int = 9,
        business_hours_end: int = 17
    ) -> list:
        """
        Calculate available time slots based on existing events.
        
        Args:
            events: List of existing events
            start_date: Start of date range
            end_date: End of date range
            slot_duration_minutes: Duration of each slot
            business_hours_start: Start of business hours (hour in local timezone)
            business_hours_end: End of business hours (hour in local timezone)
        
        Returns:
            List of available slot dictionaries
        """
        available_slots = []
        local_tz = ZoneInfo(DEFAULT_TIMEZONE)
        
        # Parse existing events into busy times (convert to local timezone)
        busy_times = []
        for event in events:
            if event.get("isCancelled"):
                continue
            
            # Parse event times
            event_start_str = event["start"]["dateTime"]
            event_end_str = event["end"]["dateTime"]
            
            # Handle different datetime formats from Microsoft Graph
            if event_start_str.endswith("Z"):
                event_start = datetime.fromisoformat(event_start_str.replace("Z", "+00:00"))
            elif "+" in event_start_str or event_start_str.count("-") > 2:
                event_start = datetime.fromisoformat(event_start_str)
            else:
                event_start = datetime.fromisoformat(event_start_str).replace(tzinfo=timezone.utc)
            
            if event_end_str.endswith("Z"):
                event_end = datetime.fromisoformat(event_end_str.replace("Z", "+00:00"))
            elif "+" in event_end_str or event_end_str.count("-") > 2:
                event_end = datetime.fromisoformat(event_end_str)
            else:
                event_end = datetime.fromisoformat(event_end_str).replace(tzinfo=timezone.utc)
            
            busy_times.append((event_start, event_end))
        
        # Get current time in local timezone
        now_local = datetime.now(local_tz)
        
        # Start from today in local timezone
        current_date = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Calculate end date in local timezone
        end_date_local = current_date + timedelta(days=7)
        
        while current_date < end_date_local:
            # Skip weekends
            if current_date.weekday() < 5:  # Monday = 0, Friday = 4
                # Generate slots for business hours in LOCAL timezone
                slot_time = current_date.replace(hour=business_hours_start, minute=0)
                day_end = current_date.replace(hour=business_hours_end, minute=0)
                
                while slot_time + timedelta(minutes=slot_duration_minutes) <= day_end:
                    slot_end = slot_time + timedelta(minutes=slot_duration_minutes)
                    
                    # Check if slot conflicts with any busy time
                    is_available = True
                    for busy_start, busy_end in busy_times:
                        # Convert busy times to local for comparison
                        busy_start_local = busy_start.astimezone(local_tz)
                        busy_end_local = busy_end.astimezone(local_tz)
                        
                        if not (slot_end <= busy_start_local or slot_time >= busy_end_local):
                            is_available = False
                            break
                    
                    # Only include future slots
                    if is_available and slot_time > now_local:
                        # Store times in ISO format with timezone info
                        available_slots.append({
                            "start": slot_time.isoformat(),
                            "end": slot_end.isoformat(),
                            "date": slot_time.strftime("%Y-%m-%d"),
                            "time": slot_time.strftime("%H:%M"),
                            "display": slot_time.strftime("%A, %B %d at %I:%M %p"),
                            "timezone": DEFAULT_TIMEZONE
                        })
                    
                    slot_time = slot_end
            
            current_date += timedelta(days=1)
        
        return available_slots
    
    def create_appointment(
        self,
        subject: str,
        start_time: datetime,
        end_time: datetime,
        attendee_email: str,
        attendee_name: str,
        description: Optional[str] = None,
        calendar_id: Optional[str] = None
    ) -> dict:
        """
        Create a new calendar appointment.
        
        Args:
            subject: Appointment subject/title
            start_time: Start datetime
            end_time: End datetime
            attendee_email: Email of the attendee
            attendee_name: Name of the attendee
            description: Optional description/notes
            calendar_id: Calendar ID (None for primary)
        
        Returns:
            Created event object or error dict
        """
        logger.info(
            "Creating appointment",
            subject=subject,
            start_time=start_time.isoformat(),
            attendee_email=attendee_email
        )
        
        if calendar_id:
            url = f"{GRAPH_API_BASE}/me/calendars/{calendar_id}/events"
        else:
            url = f"{GRAPH_API_BASE}/me/events"
        
        event_data = {
            "subject": subject,
            "start": {
                "dateTime": start_time.strftime("%Y-%m-%dT%H:%M:%S"),
                "timeZone": DEFAULT_TIMEZONE
            },
            "end": {
                "dateTime": end_time.strftime("%Y-%m-%dT%H:%M:%S"),
                "timeZone": DEFAULT_TIMEZONE
            },
            "attendees": [
                {
                    "emailAddress": {
                        "address": attendee_email,
                        "name": attendee_name
                    },
                    "type": "required"
                }
            ],
            "isOnlineMeeting": False
        }
        
        if description:
            event_data["body"] = {
                "contentType": "text",
                "content": description
            }
        
        response = requests.post(url, headers=self._get_headers(), json=event_data)
        
        if response.status_code == 201:
            event = response.json()
            logger.info(
                "Appointment created successfully",
                event_id=event.get("id"),
                subject=subject
            )
            return {
                "success": True,
                "event_id": event.get("id"),
                "web_link": event.get("webLink"),
                "subject": subject,
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            }
        else:
            logger.error(f"Failed to create appointment: {response.status_code} - {response.text}")
            return {
                "success": False,
                "error": response.json().get("error", {}).get("message", "Unknown error")
            }
    
    def cancel_appointment(self, event_id: str, calendar_id: Optional[str] = None) -> bool:
        """
        Cancel an existing appointment.
        
        Args:
            event_id: The event ID to cancel
            calendar_id: Calendar ID (None for primary)
        
        Returns:
            True if successful, False otherwise
        """
        logger.info("Cancelling appointment", event_id=event_id)
        
        if calendar_id:
            url = f"{GRAPH_API_BASE}/me/calendars/{calendar_id}/events/{event_id}"
        else:
            url = f"{GRAPH_API_BASE}/me/events/{event_id}"
        
        response = requests.delete(url, headers=self._get_headers())
        
        if response.status_code == 204:
            logger.info("Appointment cancelled successfully", event_id=event_id)
            return True
        else:
            logger.error(f"Failed to cancel appointment: {response.status_code} - {response.text}")
            return False


# Singleton instance
_outlook_calendar_service = None


def get_outlook_calendar_service() -> OutlookCalendarService:
    """Get or create the Outlook Calendar service singleton."""
    global _outlook_calendar_service
    if _outlook_calendar_service is None:
        logger.debug("Creating new Outlook Calendar service instance")
        _outlook_calendar_service = OutlookCalendarService()
    return _outlook_calendar_service