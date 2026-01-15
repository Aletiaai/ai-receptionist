"""
Test script for voice endpoints.
"""

import requests
import json

API_BASE_URL = "https://x33x9hc3td.execute-api.us-east-2.amazonaws.com"


def test_get_slots():
    """Test getting available slots via voice endpoint."""
    print("\n" + "="*60)
    print("TEST: Voice Get Slots")
    print("="*60)
    
    url = f"{API_BASE_URL}/voice/get-slots"
    payload = {
        "tenant_id": "consulate",
        "user_data": {
            "name": "Maria Garcia",
            "email": "maria@test.com",
            "phone": "+1234567890"
        }
    }
    
    print(f"POST {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        print(f"\nStatus: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Slots: {len(data.get('slots', []))}")
            print(f"Message: {data.get('message', '')[:100]}...")
            return True, data.get('slots', [])
        else:
            print(f"Error: {response.text}")
            return False, []
            
    except Exception as e:
        print(f"Error: {e}")
        return False, []


def test_book_appointment(available_slots):
    """Test booking via voice endpoint."""
    print("\n" + "="*60)
    print("TEST: Voice Book Appointment")
    print("="*60)
    
    if not available_slots:
        print("⚠️ No slots available, skipping booking test")
        return True
    
    url = f"{API_BASE_URL}/voice/book"
    payload = {
        "tenant_id": "consulate",
        "user_data": {
            "name": "Maria Garcia",
            "email": "maria@test.com",
            "phone": "+1234567890"
        },
        "slot_number": 1,
        "available_slots": available_slots
    }
    
    print(f"POST {url}")
    print(f"Booking slot #1: {available_slots[0].get('display', 'N/A')}")
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        print(f"\nStatus: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Success: {data.get('success')}")
            print(f"Message: {data.get('message', '')[:100]}...")
            
            if data.get('appointment'):
                print(f"Appointment ID: {data['appointment'].get('appointment_id')}")
            
            return data.get('success', False)
        else:
            print(f"Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"Error: {e}")
        return False


def run_all_tests():
    """Run all voice endpoint tests."""
    print("\n" + "="*60)
    print("📞 VOICE ENDPOINT TESTS")
    print("="*60)
    
    results = []
    
    # Test 1: Get slots
    success, slots = test_get_slots()
    results.append(("Get Slots", success))
    
    # Test 2: Book appointment
    success = test_book_appointment(slots)
    results.append(("Book Appointment", success))
    
    # Summary
    print("\n" + "="*60)
    print("📊 VOICE ENDPOINT TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, r in results if r)
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\nTotal: {passed}/{len(results)} tests passed")
    
    return passed == len(results)


if __name__ == "__main__":
    run_all_tests()