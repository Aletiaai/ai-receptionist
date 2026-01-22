"""
Email Service
Sends emails via Microsoft Graph API using the same OAuth token as calendar.
"""

import os
from typing import Optional
import requests
from dotenv import load_dotenv
import msal

from config.settings import EMAIL_CONFIG, API_CONFIG, OAUTH_CONFIG
from config.prompts import EMAIL_TEMPLATES
from src.utils.logger import get_logger
from src.services.dynamo_service import get_dynamo_service

# Load environment variables
load_dotenv()

# Initialize logger
logger = get_logger(__name__)

# Configuration from environment
CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
TENANT_ID = os.getenv("AZURE_TENANT_ID")
AUTHORITY = f"{OAUTH_CONFIG['authority_url']}/{TENANT_ID}"
GRAPH_API_BASE = API_CONFIG["graph_api_base"]

# Token storage configuration
TOKEN_TENANT_ID = OAUTH_CONFIG["token_tenant_id"]
TOKEN_PROVIDER = OAUTH_CONFIG["outlook_provider"]

# Email sender (the M365 account we authorized)
DEFAULT_SENDER_NAME = EMAIL_CONFIG["sender_name"]


class EmailService:
    """Service class for sending emails via Microsoft Graph API."""
    
    def __init__(self):
        """Initialize the Email service."""
        logger.info("Initializing Email service")
        
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
        
        logger.info("Email service initialized")
    
    def _load_and_refresh_token(self) -> None:
        """Load token from DynamoDB and refresh if needed."""
        logger.debug("Loading OAuth token from DynamoDB for email")
        
        token_data = self.dynamo_service.get_oauth_token(TOKEN_TENANT_ID, TOKEN_PROVIDER)
        
        if not token_data:
            logger.error("No OAuth token found in DynamoDB")
            raise ValueError("OAuth token not found. Run auth_outlook.py first.")
        
        refresh_token = token_data.get("refresh_token")
        
        if not refresh_token:
            logger.error("No refresh token in token data")
            raise ValueError("No refresh token. Run auth_outlook.py again.")
        
        # Use refresh token to get new access token
        logger.debug("Refreshing access token for email")
        
        result = self.app.acquire_token_by_refresh_token(
            refresh_token,
            scopes=["Mail.Send", "User.Read"]
        )
        
        if "access_token" in result:
            self.access_token = result["access_token"]
            
            # Update stored tokens in DynamoDB
            token_data["access_token"] = result["access_token"]
            if "refresh_token" in result:
                token_data["refresh_token"] = result["refresh_token"]
            
            self.dynamo_service.save_oauth_token(TOKEN_TENANT_ID, TOKEN_PROVIDER, token_data)
            
            logger.info("Access token refreshed for email service")
        else:
            logger.error(f"Token refresh failed: {result.get('error_description')}")
            raise ValueError("Failed to refresh token. Run auth_outlook.py again.")
    
    def _get_headers(self) -> dict:
        """Get headers for Graph API requests."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
    
    def send_email(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        body_html: str,
        body_text: Optional[str] = None
    ) -> dict:
        """
        Send an email via Microsoft Graph API.
        Args:
            to_email: Recipient email address
            to_name: Recipient name
            subject: Email subject
            body_html: HTML body content
            body_text: Plain text body (optional fallback)
        
        Returns:
            Result dictionary with success status
        """
        logger.info(
            "Sending email",
            to_email=to_email,
            subject=subject[:50]
        )
        
        url = f"{GRAPH_API_BASE}/me/sendMail"
        
        email_data = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": body_html
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": to_email,
                            "name": to_name
                        }
                    }
                ]
            },
            "saveToSentItems": "true"
        }
        
        try:
            response = requests.post(url, headers=self._get_headers(), json=email_data)
            
            if response.status_code == 202:
                logger.info(
                    "Email sent successfully",
                    to_email=to_email,
                    subject=subject[:50]
                )
                return {
                    "success": True,
                    "message": "Email sent successfully"
                }
            else:
                error_msg = response.json().get("error", {}).get("message", "Unknown error")
                logger.error(
                    "Failed to send email",
                    to_email=to_email,
                    status_code=response.status_code,
                    error=error_msg
                )
                return {
                    "success": False,
                    "error": error_msg
                }
                
        except Exception as e:
            logger.error(
                "Email sending failed with exception",
                to_email=to_email,
                error=str(e),
                exc_info=True
            )
            return {
                "success": False,
                "error": str(e)
            }
    
    def send_appointment_confirmation(
        self,
        to_email: str,
        to_name: str,
        appointment_date: str,
        appointment_time: str,
        tenant_name: str,
        language: str = "en"
    ) -> dict:
        """
        Send appointment confirmation email to user.
        Args:
            to_email: User's email
            to_name: User's name
            appointment_date: Formatted date string
            appointment_time: Formatted time string
            tenant_name: Name of the business/tenant
            language: 'en' or 'es'
        Returns:
            Result dictionary
        """
        logger.info(
            "Sending appointment confirmation",
            to_email=to_email,
            tenant=tenant_name,
            language=language
        )

        # Get template for language
        template = EMAIL_TEMPLATES["user_confirmation"].get(language, EMAIL_TEMPLATES["user_confirmation"]["en"])
        colors = EMAIL_CONFIG["colors"]

        subject = template["subject"].format(tenant_name=tenant_name)
        body_html = template["body"].format(
            primary_color=colors["primary"],
            bg_color=colors["background"],
            border_color=colors["border"],
            text_primary=colors["text_primary"],
            text_secondary=colors["text_secondary"],
            to_name=to_name,
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            tenant_name=tenant_name
        )

        return self.send_email(
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            body_html=body_html
        )
    
    def send_admin_notification(
        self,
        admin_email: str,
        user_name: str,
        user_email: str,
        user_phone: str,
        appointment_date: str,
        appointment_time: str,
        tenant_name: str
    ) -> dict:
        """
        Send notification email to admin about new appointment.
        Args:
            admin_email: Admin's email address
            user_name: Customer's name
            user_email: Customer's email
            user_phone: Customer's phone
            appointment_date: Formatted date string
            appointment_time: Formatted time string
            tenant_name: Name of the business/tenant
        Returns:
            Result dictionary
        """
        logger.info(
            "Sending admin notification",
            admin_email=admin_email,
            tenant=tenant_name,
            user_name=user_name
        )

        # Get template and colors from config
        template = EMAIL_TEMPLATES["admin_notification"]
        colors = EMAIL_CONFIG["colors"]

        subject = template["subject"].format(user_name=user_name)
        body_html = template["body"].format(
            success_color=colors["success"],
            bg_color=colors["background"],
            border_color=colors["border"],
            text_primary=colors["text_primary"],
            text_secondary=colors["text_secondary"],
            user_name=user_name,
            user_email=user_email,
            user_phone=user_phone,
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            tenant_name=tenant_name
        )

        return self.send_email(
            to_email=admin_email,
            to_name="Admin",
            subject=subject,
            body_html=body_html
        )


# Singleton instance
_email_service = None


def get_email_service() -> EmailService:
    """Get or create the Email service singleton."""
    global _email_service
    if _email_service is None:
        logger.debug("Creating new Email service instance")
        _email_service = EmailService()
    return _email_service