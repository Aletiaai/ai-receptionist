"""
Local test script for the AI Receptionist chat handler.
Simulates Lambda invocations without deploying to AWS.
"""

import json
import sys
from dotenv import load_dotenv

# Load environment variables FIRST
load_dotenv()

from src.handlers.chat_handler import lambda_handler, process_message
from src.services.dynamo_service import get_dynamo_service
from src.utils.language_detector import detect_language
from src.utils.logger import get_logger

logger = get_logger(__name__)


def test_language_detection():
    """Test the language detection utility."""
    print("\n" + "="*60)
    print("TEST: Language Detection")
    print("="*60)
    
    test_cases = [
        ("Hello, I need to schedule an appointment", "en"),
        ("Hola, necesito programar una cita", "es"),
        ("Buenos días, ¿tienen disponibilidad?", "es"),
        ("Good morning, do you have availability?", "en"),
        ("Quisiera hacer una reservación", "es"),
        ("I would like to make a reservation", "en"),
    ]
    
    passed = 0
    for text, expected in test_cases:
        result = detect_language(text)
        status = "✅" if result == expected else "❌"
        if result == expected:
            passed += 1
        print(f"{status} '{text[:40]}...' → {result} (expected: {expected})")
    
    print(f"\nResults: {passed}/{len(test_cases)} passed")
    return passed == len(test_cases)


def test_tenant_loading():
    """Test loading tenant configuration from DynamoDB."""
    print("\n" + "="*60)
    print("TEST: Tenant Loading")
    print("="*60)
    
    dynamo = get_dynamo_service()
    
    tenants_to_test = ['consulate', 'realestate']
    passed = 0
    
    for tenant_id in tenants_to_test:
        tenant = dynamo.get_tenant(tenant_id)
        if tenant:
            print(f"✅ Loaded tenant: {tenant_id}")
            print(f"   Name: {tenant.get('name')}")
            print(f"   Languages: {tenant.get('supported_languages')}")
            print(f"   Active: {tenant.get('active')}")
            passed += 1
        else:
            print(f"❌ Failed to load tenant: {tenant_id}")
    
    print(f"\nResults: {passed}/{len(tenants_to_test)} passed")
    return passed == len(tenants_to_test)


def test_full_conversation():
    """Test a full conversation flow with the chat handler."""
    print("\n" + "="*60)
    print("TEST: Full Conversation Flow")
    print("="*60)
    
    # Simulate a conversation
    tenant_id = "consulate"
    session_id = None
    
    messages = [
        "Hola, necesito hacer una cita",
        "Me llamo Juan García López",
        "Mi correo es juan.garcia@email.com",
        "Mi teléfono es 5551234567",
    ]
    
    print(f"\nTenant: {tenant_id}")
    print("-" * 40)
    
    for i, user_message in enumerate(messages, 1):
        print(f"\n[Message {i}]")
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
            session_id = body.get('session_id')  # Keep session for next message
            
            print(f"🤖 Assistant: {body.get('message', '')[:200]}...")
            print(f"   Language: {body.get('detected_language')}")
            print(f"   Slots collected: {list(body.get('slot_status', {}).get('collected', {}).keys())}")
            print(f"   Slots missing: {body.get('slot_status', {}).get('missing', [])}")
        else:
            print(f"❌ Error: {response}")
            return False
    
    print("\n" + "-" * 40)
    print("✅ Conversation flow completed successfully!")
    return True


def test_english_conversation():
    """Test conversation in English."""
    print("\n" + "="*60)
    print("TEST: English Conversation")
    print("="*60)
    
    tenant_id = "realestate"
    session_id = None
    
    messages = [
        "Hi, I'd like to schedule a property viewing",
        "My name is John Smith",
        "You can reach me at john.smith@gmail.com",
        "My phone number is 555-987-6543",
    ]
    
    print(f"\nTenant: {tenant_id}")
    print("-" * 40)
    
    for i, user_message in enumerate(messages, 1):
        print(f"\n[Message {i}]")
        print(f"👤 User: {user_message}")
        
        event = {
            'body': json.dumps({
                'tenant_id': tenant_id,
                'session_id': session_id,
                'message': user_message
            }),
            'pathParameters': {'tenant_id': tenant_id}
        }
        
        response = lambda_handler(event, None)
        
        if response['statusCode'] == 200:
            body = json.loads(response['body'])
            session_id = body.get('session_id')
            
            print(f"🤖 Assistant: {body.get('message', '')[:200]}...")
            print(f"   Language: {body.get('detected_language')}")
            print(f"   Slots collected: {list(body.get('slot_status', {}).get('collected', {}).keys())}")
            print(f"   Slots missing: {body.get('slot_status', {}).get('missing', [])}")
        else:
            print(f"❌ Error: {response}")
            return False
    
    print("\n" + "-" * 40)
    print("✅ English conversation completed successfully!")
    return True


def test_error_handling():
    """Test error handling scenarios."""
    print("\n" + "="*60)
    print("TEST: Error Handling")
    print("="*60)
    
    test_cases = [
        (
            "Missing tenant_id",
            {'body': json.dumps({'message': 'Hello'})},
            400
        ),
        (
            "Missing message",
            {'body': json.dumps({'tenant_id': 'consulate'})},
            400
        ),
        (
            "Invalid tenant",
            {'body': json.dumps({'tenant_id': 'nonexistent', 'message': 'Hello'})},
            400
        ),
        (
            "Empty body",
            {'body': '{}'},
            400
        ),
    ]
    
    passed = 0
    for name, event, expected_status in test_cases:
        response = lambda_handler(event, None)
        status = "✅" if response['statusCode'] == expected_status else "❌"
        if response['statusCode'] == expected_status:
            passed += 1
        print(f"{status} {name}: got {response['statusCode']} (expected {expected_status})")
    
    print(f"\nResults: {passed}/{len(test_cases)} passed")
    return passed == len(test_cases)


def run_all_tests():
    """Run all tests."""
    print("\n" + "="*60)
    print("🧪 AI RECEPTIONIST - LOCAL TESTS")
    print("="*60)
    
    results = []
    
    # Run tests
    results.append(("Language Detection", test_language_detection()))
    results.append(("Tenant Loading", test_tenant_loading()))
    results.append(("Error Handling", test_error_handling()))
    results.append(("Spanish Conversation", test_full_conversation()))
    results.append(("English Conversation", test_english_conversation()))
    
    # Summary
    print("\n" + "="*60)
    print("📊 TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, r in results if r)
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\nTotal: {passed}/{len(results)} test suites passed")
    
    return passed == len(results)


def interactive_chat():
    """Run an interactive chat session for manual testing."""
    print("\n" + "="*60)
    print("💬 INTERACTIVE CHAT MODE")
    print("="*60)
    print("Type 'quit' to exit, 'reset' to start new session")
    print("Type 'switch consulate' or 'switch realestate' to change tenant")
    print("-"*60)
    
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
                print(f"\n   [Lang: {body.get('detected_language')} | "
                        f"Slots: {body.get('slot_status', {}).get('collected', {})} | "
                        f"Missing: {body.get('slot_status', {}).get('missing', [])}]")
            else:
                error_body = json.loads(response['body'])
                print(f"\n❌ Error: {error_body.get('error')}")
                
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == 'chat':
        interactive_chat()
    else:
        success = run_all_tests()
        sys.exit(0 if success else 1)