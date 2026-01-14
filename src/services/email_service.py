"""
Email Service
Sends emails via Microsoft Graph API using the same OAuth token as calendar.
"""

import os
from typing import Optional
import requests
from dotenv import load_dotenv

from src.utils.logger import get_logger
from src.services.dynamo_service import get_dynamo_service
import msal

# Load environment variables
load_dotenv()

# Initialize logger
logger = get_logger(__name__)

# Configuration
CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
TENANT_ID = os.getenv("AZURE_TENANT_ID")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"

# Token storage configuration
TOKEN_TENANT_ID = "global"
TOKEN_PROVIDER = "outlook"

# Email sender (the M365 account we authorized)
DEFAULT_SENDER_NAME = os.getenv("EMAIL_SENDER_NAME", "AI Receptionist")


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
        
        if language == "es":
            subject = f"Confirmación de Cita - {tenant_name}"
            body_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background-color: #2563eb; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
                    .content {{ background-color: #f8fafc; padding: 30px; border-radius: 0 0 8px 8px; }}
                    .appointment-box {{ background-color: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin: 20px 0; }}
                    .label {{ color: #64748b; font-size: 12px; text-transform: uppercase; margin-bottom: 5px; }}
                    .value {{ font-size: 18px; font-weight: bold; color: #1e293b; }}
                    .footer {{ text-align: center; color: #64748b; font-size: 12px; margin-top: 20px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>✅ Cita Confirmada</h1>
                    </div>
                    <div class="content">
                        <p>Hola <strong>{to_name}</strong>,</p>
                        <p>Su cita ha sido confirmada exitosamente. A continuación los detalles:</p>
                        
                        <div class="appointment-box">
                            <div class="label">Fecha</div>
                            <div class="value">{appointment_date}</div>
                            <br>
                            <div class="label">Hora</div>
                            <div class="value">{appointment_time}</div>
                            <br>
                            <div class="label">Lugar</div>
                            <div class="value">{tenant_name}</div>
                        </div>
                        
                        <p>También recibirá una invitación de calendario.</p>
                        <p>Si necesita reprogramar o cancelar, por favor contáctenos.</p>
                        
                        <div class="footer">
                            <p>Este es un correo automático enviado por el Asistente Virtual de {tenant_name}</p>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
        else:
            subject = f"Appointment Confirmation - {tenant_name}"
            body_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background-color: #2563eb; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
                    .content {{ background-color: #f8fafc; padding: 30px; border-radius: 0 0 8px 8px; }}
                    .appointment-box {{ background-color: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin: 20px 0; }}
                    .label {{ color: #64748b; font-size: 12px; text-transform: uppercase; margin-bottom: 5px; }}
                    .value {{ font-size: 18px; font-weight: bold; color: #1e293b; }}
                    .footer {{ text-align: center; color: #64748b; font-size: 12px; margin-top: 20px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>✅ Appointment Confirmed</h1>
                    </div>
                    <div class="content">
                        <p>Hello <strong>{to_name}</strong>,</p>
                        <p>Your appointment has been successfully confirmed. Here are the details:</p>
                        
                        <div class="appointment-box">
                            <div class="label">Date</div>
                            <div class="value">{appointment_date}</div>
                            <br>
                            <div class="label">Time</div>
                            <div class="value">{appointment_time}</div>
                            <br>
                            <div class="label">Location</div>
                            <div class="value">{tenant_name}</div>
                        </div>
                        
                        <p>You will also receive a calendar invitation.</p>
                        <p>If you need to reschedule or cancel, please contact us.</p>
                        
                        <div class="footer">
                            <p>This is an automated message from {tenant_name}'s Virtual Assistant</p>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
        
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
        
        subject = f"📅 Nueva Cita Agendada - {user_name}"
        
        body_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #16a34a; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ background-color: #f8fafc; padding: 30px; border-radius: 0 0 8px 8px; }}
                .info-box {{ background-color: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin: 20px 0; }}
                .row {{ display: flex; margin-bottom: 10px; }}
                .label {{ color: #64748b; width: 120px; font-weight: bold; }}
                .value {{ color: #1e293b; }}
                .footer {{ text-align: center; color: #64748b; font-size: 12px; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📅 Nueva Cita Agendada</h1>
                </div>
                <div class="content">
                    <p>Se ha agendado una nueva cita a través del Asistente Virtual.</p>
                    
                    <div class="info-box">
                        <h3 style="margin-top: 0; color: #1e293b;">Información del Cliente</h3>
                        <div class="row">
                            <span class="label">Nombre:</span>
                            <span class="value">{user_name}</span>
                        </div>
                        <div class="row">
                            <span class="label">Email:</span>
                            <span class="value">{user_email}</span>
                        </div>
                        <div class="row">
                            <span class="label">Teléfono:</span>
                            <span class="value">{user_phone}</span>
                        </div>
                    </div>
                    
                    <div class="info-box">
                        <h3 style="margin-top: 0; color: #1e293b;">Detalles de la Cita</h3>
                        <div class="row">
                            <span class="label">Fecha:</span>
                            <span class="value">{appointment_date}</span>
                        </div>
                        <div class="row">
                            <span class="label">Hora:</span>
                            <span class="value">{appointment_time}</span>
                        </div>
                        <div class="row">
                            <span class="label">Servicio:</span>
                            <span class="value">{tenant_name}</span>
                        </div>
                    </div>
                    
                    <div class="footer">
                        <p>Mensaje automático del Asistente Virtual de {tenant_name}</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
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