"""
Test script for the complete booking flow.
Simulates a full conversation from greeting to appointment confirmation.
"""

import json
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src.handlers.chat_handler import lambda_handler
from src.utils.logger import get_logger

logger = get_logger(__name__)


def simulate_conversation(tenant_id: str, messages: list, language: str = "en"):
    """
    Simulate a complete conversation flow.
    
    Args:
        tenant_id: The tenant to test with
        messages: List of user messages to send
        language: Expected language for display
    """
    print(f"\n{'='*70}")
    print(f"🗣️  BOOKING FLOW TEST: {tenant_id.upper()} ({language.upper()})")
    print(f"{'='*70}")
    
    session_id = None
    
    for i, user_message in enumerate(messages, 1):
        print(f"\n{'─'*70}")
        print(f"[Turn {i}]")
        print(f"👤 User: {user_message}")
        
        # Create Lambda event
        event = {
            'body': json.dumps({
                'tenant_id': tenant_id,
                'session_id': session_id,
                'message': user_message
            }),
            'pathParameters': {'tenant_id': tenant_id}
        }
        
        # Invoke handler
        response = lambda_handler(event, None)
        
        if response['statusCode'] == 200:
            body = json.loads(response['body'])
            session_id = body.get('session_id')
            
            print(f"\n🤖 Assistant: {body.get('message', '')}")
            print(f"\n   📊 Status:")
            print(f"      Language: {body.get('detected_language')}")
            print(f"      Slots: {body.get('slot_status', {}).get('collected', {})}")
            print(f"      Missing: {body.get('slot_status', {}).get('missing', [])}")
            print(f"      Booking State: {body.get('booking_state', 'none')}")
            
            # Check if booking was confirmed
            if body.get('booking'):
                print(f"\n   ✅ APPOINTMENT BOOKED!")
                print(f"      Appointment ID: {body['booking'].get('appointment_id')}")
                print(f"      Slot: {body['booking'].get('slot', {}).get('display')}")
        else:
            print(f"\n❌ Error: {response}")
            return False
    
    print(f"\n{'='*70}")
    print(f"✅ Conversation completed successfully!")
    print(f"{'='*70}\n")
    return True


def test_spanish_consulate_flow():
    """Test complete booking flow in Spanish for Consulate."""
    print("\n" + "="*70)
    print("TEST 1: Spanish Consulate - Complete Booking Flow")
    print("="*70)
    
    messages = [
        "Hola, necesito hacer una cita en el consulado",
        "Mi nombre es María García López",
        "Mi correo es maria.garcia@email.com y mi teléfono es 5551234567",
        "El primero por favor",  # Select first available slot
    ]
    
    return simulate_conversation("consulate", messages, "es")


def test_english_realestate_flow():
    """Test complete booking flow in English for Real Estate."""
    print("\n" + "="*70)
    print("TEST 2: English Real Estate - Complete Booking Flow")
    print("="*70)
    
    messages = [
        "Hi, I'd like to schedule a property viewing",
        "My name is John Smith",
        "My email is john.smith@gmail.com",
        "My phone number is 555-987-6543",
        "I'll take option 2",  # Select second available slot
    ]
    
    return simulate_conversation("realestate", messages, "en")


def test_all_info_at_once():
    """Test when user provides all information at once."""
    print("\n" + "="*70)
    print("TEST 3: All Information at Once")
    print("="*70)
    
    messages = [
        "Hola, quiero hacer una cita. Me llamo Carlos Rodríguez, mi email es carlos@test.com y mi teléfono es 5559876543",
        "3",  # Select third slot
    ]
    
    return simulate_conversation("consulate", messages, "es")


def run_all_tests():
    """Run all booking flow tests."""
    print("\n" + "="*70)
    print("📅 COMPLETE BOOKING FLOW TESTS")
    print("="*70)
    
    results = []
    
    # Test 1: Spanish Consulate
    results.append(("Spanish Consulate Flow", test_spanish_consulate_flow()))
    
    # Test 2: English Real Estate
    results.append(("English Real Estate Flow", test_english_realestate_flow()))
    
    # Test 3: All info at once
    results.append(("All Info at Once", test_all_info_at_once()))
    
    # Summary
    print("\n" + "="*70)
    print("📊 BOOKING FLOW TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, r in results if r)
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\nTotal: {passed}/{len(results)} tests passed")
    
    return passed == len(results)


def interactive_booking():
    """Run an interactive booking session."""
    print("\n" + "="*70)
    print("💬 INTERACTIVE BOOKING MODE")
    print("="*70)
    print("Commands: 'quit' to exit, 'reset' to start over")
    print("          'switch consulate' or 'switch realestate' to change tenant")
    print("─"*70)
    
    tenant_id = "consulate"
    session_id = None
    
    print(f"\nCurrent tenant: {tenant_id}")
    
    while True:
        try:
            user_input = input("\n👤 You: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() == 'quit':
                print("Goodbye!")
                break
            
            if user_input.lower() == 'reset':
                session_id = None
                print("🔄 Session reset. Starting new conversation.")
                continue
            
            if user_input.lower().startswith('switch '):
                new_tenant = user_input.split(' ', 1)[1].strip()
                if new_tenant in ['consulate', 'realestate']:
                    tenant_id = new_tenant
                    session_id = None
                    print(f"🔄 Switched to tenant: {tenant_id}")
                else:
                    print(f"❌ Unknown tenant: {new_tenant}")
                continue
            
            # Process message
            event = {
                'body': json.dumps({
                    'tenant_id': tenant_id,
                    'session_id': session_id,
                    'message': user_input
                })
            }
            
            response = lambda_handler(event, None)
            
            if response['statusCode'] == 200:
                body = json.loads(response['body'])
                session_id = body.get('session_id')
                
                print(f"\n🤖 Assistant: {body.get('message')}")
                print(f"\n   [State: {body.get('booking_state', 'none')} | "
                        f"Slots: {list(body.get('slot_status', {}).get('collected', {}).keys())} | "
                        f"Missing: {body.get('slot_status', {}).get('missing', [])}]")
                
                if body.get('booking'):
                    print(f"\n   🎉 APPOINTMENT CONFIRMED!")
                    print(f"   📅 {body['booking'].get('slot', {}).get('display')}")
            else:
                error_body = json.loads(response['body'])
                print(f"\n❌ Error: {error_body.get('error')}")
                
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == 'chat':
        interactive_booking()
    else:
        success = run_all_tests()
        sys.exit(0 if success else 1)