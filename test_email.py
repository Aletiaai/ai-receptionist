"""
Test script for Email Service.
Tests sending emails via Microsoft Graph API.
"""

import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src.services.email_service import get_email_service
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ⚠️ CHANGE THIS to your email address for testing
TEST_EMAIL = "bogowild@gmail.com"


def test_email_connection():
    """Test basic email service connection."""
    print("\n" + "="*60)
    print("TEST: Email Service Connection")
    print("="*60)
    
    try:
        service = get_email_service()
        print("✅ Email service initialized successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to initialize email service: {str(e)}")
        return False


def test_send_simple_email():
    """Test sending a simple email."""
    print("\n" + "="*60)
    print("TEST: Send Simple Email")
    print("="*60)
    
    if TEST_EMAIL == "your_email@example.com":
        print("⚠️  Please update TEST_EMAIL in test_email.py with your real email")
        return False
    
    try:
        service = get_email_service()
        
        result = service.send_email(
            to_email=TEST_EMAIL,
            to_name="Test User",
            subject="🧪 AI Receptionist - Test Email",
            body_html="""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <h1 style="color: #2563eb;">✅ Email Test Successful!</h1>
                <p>If you're reading this, the email service is working correctly.</p>
                <p>This is a test email from the AI Receptionist system.</p>
                <hr>
                <p style="color: #64748b; font-size: 12px;">Automated test message</p>
            </body>
            </html>
            """
        )
        
        if result.get("success"):
            print(f"✅ Email sent successfully to {TEST_EMAIL}")
            print("   📧 Check your inbox (and spam folder)")
            return True
        else:
            print(f"❌ Failed to send email: {result.get('error')}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def test_appointment_confirmation_email():
    """Test sending appointment confirmation email."""
    print("\n" + "="*60)
    print("TEST: Appointment Confirmation Email")
    print("="*60)
    
    if TEST_EMAIL == "your_email@example.com":
        print("⚠️  Please update TEST_EMAIL in test_email.py with your real email")
        return False
    
    try:
        service = get_email_service()
        
        result = service.send_appointment_confirmation(
            to_email=TEST_EMAIL,
            to_name="María García López",
            appointment_date="Jueves, 9 de Enero de 2026",
            appointment_time="10:00 AM",
            tenant_name="Consulado",
            language="es"
        )
        
        if result.get("success"):
            print(f"✅ Confirmation email (Spanish) sent to {TEST_EMAIL}")
            return True
        else:
            print(f"❌ Failed: {result.get('error')}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def test_admin_notification_email():
    """Test sending admin notification email."""
    print("\n" + "="*60)
    print("TEST: Admin Notification Email")
    print("="*60)
    
    if TEST_EMAIL == "your_email@example.com":
        print("⚠️  Please update TEST_EMAIL in test_email.py with your real email")
        return False
    
    try:
        service = get_email_service()
        
        result = service.send_admin_notification(
            admin_email=TEST_EMAIL,
            user_name="John Smith",
            user_email="john.smith@example.com",
            user_phone="+1 (555) 123-4567",
            appointment_date="Thursday, January 9, 2026",
            appointment_time="2:00 PM",
            tenant_name="Real Estate Agency"
        )
        
        if result.get("success"):
            print(f"✅ Admin notification email sent to {TEST_EMAIL}")
            return True
        else:
            print(f"❌ Failed: {result.get('error')}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def run_all_tests():
    """Run all email tests."""
    print("\n" + "="*60)
    print("📧 EMAIL SERVICE TESTS")
    print("="*60)
    print(f"Test recipient: {TEST_EMAIL}")
    
    if TEST_EMAIL == "your_email@example.com":
        print("\n⚠️  ERROR: Please edit test_email.py and set TEST_EMAIL to your real email address")
        return False
    
    results = []
    
    # Test 1: Connection
    results.append(("Email Connection", test_email_connection()))
    
    if not results[-1][1]:
        print("\n❌ Cannot proceed without email connection")
        return False
    
    # Test 2: Simple email
    results.append(("Simple Email", test_send_simple_email()))
    
    # Test 3: Appointment confirmation
    results.append(("Appointment Confirmation", test_appointment_confirmation_email()))
    
    # Test 4: Admin notification
    results.append(("Admin Notification", test_admin_notification_email()))
    
    # Summary
    print("\n" + "="*60)
    print("📊 EMAIL TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, r in results if r)
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\nTotal: {passed}/{len(results)} tests passed")
    print("\n📧 Check your inbox for the test emails!")
    
    return passed == len(results)


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)