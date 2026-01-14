"""
Test script for the deployed AI Receptionist API.
Tests the live API Gateway endpoint.
"""

import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API Configuration
API_BASE_URL = os.getenv("API_GATEWAY_URL", "https://x33x9hc3td.execute-api.us-east-2.amazonaws.com")


def test_consulate_spanish():
    """Test Spanish conversation with Consulate tenant."""
    print("\n" + "="*60)
    print("TEST: Consulate (Spanish)")
    print("="*60)
    
    endpoint = f"{API_BASE_URL}/chat/consulate"
    session_id = None
    
    messages = [
        "Hola, necesito hacer una cita por favor",
        "Me llamo María González",
        "Mi correo es maria.gonzalez@email.com y mi teléfono es 5551234567",
    ]
    
    for i, message in enumerate(messages, 1):
        print(f"\n[Message {i}]")
        print(f"👤 User: {message}")
        
        payload = {
            "message": message,
            "session_id": session_id
        }
        
        try:
            response = requests.post(endpoint, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                session_id = data.get("session_id")
                
                print(f"🤖 Assistant: {data.get('message', '')[:200]}...")
                print(f"   Language: {data.get('detected_language')}")
                print(f"   Slots: {data.get('slot_status', {}).get('collected', {})}")
                print(f"   Missing: {data.get('slot_status', {}).get('missing', [])}")
            else:
                print(f"❌ Error {response.status_code}: {response.text}")
                return False
                
        except requests.exceptions.Timeout:
            print("❌ Request timed out")
            return False
        except Exception as e:
            print(f"❌ Request failed: {str(e)}")
            return False
    
    print("\n✅ Consulate Spanish test passed!")
    return True


def test_realestate_english():
    """Test English conversation with Real Estate tenant."""
    print("\n" + "="*60)
    print("TEST: Real Estate (English)")
    print("="*60)
    
    endpoint = f"{API_BASE_URL}/chat/realestate"
    session_id = None
    
    messages = [
        "Hi, I'd like to schedule a property viewing",
        "My name is John Smith",
        "My email is john.smith@gmail.com and my phone is 555-987-6543",
    ]
    
    for i, message in enumerate(messages, 1):
        print(f"\n[Message {i}]")
        print(f"👤 User: {message}")
        
        payload = {
            "message": message,
            "session_id": session_id
        }
        
        try:
            response = requests.post(endpoint, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                session_id = data.get("session_id")
                
                print(f"🤖 Assistant: {data.get('message', '')[:200]}...")
                print(f"   Language: {data.get('detected_language')}")
                print(f"   Slots: {data.get('slot_status', {}).get('collected', {})}")
                print(f"   Missing: {data.get('slot_status', {}).get('missing', [])}")
            else:
                print(f"❌ Error {response.status_code}: {response.text}")
                return False
                
        except requests.exceptions.Timeout:
            print("❌ Request timed out")
            return False
        except Exception as e:
            print(f"❌ Request failed: {str(e)}")
            return False
    
    print("\n✅ Real Estate English test passed!")
    return True


def test_invalid_tenant():
    """Test error handling for invalid tenant."""
    print("\n" + "="*60)
    print("TEST: Invalid Tenant (Error Handling)")
    print("="*60)
    
    endpoint = f"{API_BASE_URL}/chat/invalid_tenant"
    
    payload = {
        "message": "Hello"
    }
    
    try:
        response = requests.post(endpoint, json=payload, timeout=30)
        
        if response.status_code == 400:
            print(f"✅ Correctly returned 400 for invalid tenant")
            print(f"   Response: {response.json()}")
            return True
        else:
            print(f"❌ Expected 400, got {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Request failed: {str(e)}")
        return False


def test_missing_message():
    """Test error handling for missing message."""
    print("\n" + "="*60)
    print("TEST: Missing Message (Error Handling)")
    print("="*60)
    
    endpoint = f"{API_BASE_URL}/chat/consulate"
    
    payload = {}  # No message
    
    try:
        response = requests.post(endpoint, json=payload, timeout=30)
        
        if response.status_code == 400:
            print(f"✅ Correctly returned 400 for missing message")
            print(f"   Response: {response.json()}")
            return True
        else:
            print(f"❌ Expected 400, got {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Request failed: {str(e)}")
        return False

def test_full_booking_flow():
    """Test complete booking flow via live API."""
    print("\n" + "="*60)
    print("TEST: Full Booking Flow (Live API)")
    print("="*60)
    
    endpoint = f"{API_BASE_URL}/chat/consulate"
    session_id = None
    
    messages = [
        "Hola, necesito agendar una cita",
        "Me llamo Roberto Martínez García",
        "Mi correo es roberto.martinez@test.com y mi teléfono es 5552223333",
        "Quiero hacer el tramite de visa",
        "La segunda opción por favor",
    ]
    
    for i, message in enumerate(messages, 1):
        print(f"\n[Message {i}]")
        print(f"👤 User: {message}")
        
        payload = {
            "message": message,
            "session_id": session_id
        }
        
        try:
            response = requests.post(endpoint, json=payload, timeout=60)
            
            if response.status_code == 200:
                data = response.json()
                session_id = data.get("session_id")
                
                print(f"🤖 Assistant: {data.get('message', '')[:300]}...")
                print(f"   Booking State: {data.get('booking_state', 'none')}")
                
                # Check if booking confirmed
                if data.get('booking', {}).get('confirmed'):
                    print(f"\n   🎉 APPOINTMENT BOOKED!")
                    print(f"   📅 Slot: {data['booking'].get('slot', {}).get('display')}")
                    print(f"   🆔 ID: {data['booking'].get('appointment_id')}")
            else:
                print(f"❌ Error {response.status_code}: {response.text}")
                return False
                
        except requests.exceptions.Timeout:
            print("❌ Request timed out (this may happen on cold start, try again)")
            return False
        except Exception as e:
            print(f"❌ Request failed: {str(e)}")
            return False
    
    print("\n✅ Full booking flow test passed!")
    return True

def run_all_tests():
    """Run all API tests."""
    print("\n" + "="*60)
    print("🌐 AI RECEPTIONIST - LIVE API TESTS")
    print("="*60)
    print(f"API URL: {API_BASE_URL}")
    
    results = []
    
    results.append(("Missing Message", test_missing_message()))
    results.append(("Invalid Tenant", test_invalid_tenant()))
    results.append(("Consulate Spanish", test_consulate_spanish()))
    results.append(("Real Estate English", test_realestate_english()))
    results.append(("Full Booking Flow", test_full_booking_flow()))
    
    # Summary
    print("\n" + "="*60)
    print("📊 API TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, r in results if r)
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\nTotal: {passed}/{len(results)} tests passed")
    
    return passed == len(results)


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)