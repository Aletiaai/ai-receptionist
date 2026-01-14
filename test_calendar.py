#!/usr/bin/env python3
"""
Test script for Outlook Calendar Service.
Tests calendar access, availability checking, and appointment creation.
"""

import sys
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src.services.outlook_calendar_service import get_outlook_calendar_service
from src.utils.logger import get_logger

logger = get_logger(__name__)


def test_calendar_connection():
    """Test basic calendar connection."""
    print("\n" + "="*60)
    print("TEST: Calendar Connection")
    print("="*60)
    
    try:
        service = get_outlook_calendar_service()
        print("✅ Calendar service initialized successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to initialize calendar service: {str(e)}")
        return False


def test_list_calendars():
    """Test listing available calendars."""
    print("\n" + "="*60)
    print("TEST: List Calendars")
    print("="*60)
    
    try:
        service = get_outlook_calendar_service()
        calendars = service.get_calendars()
        
        if calendars:
            print(f"✅ Found {len(calendars)} calendar(s):\n")
            for cal in calendars:
                print(f"   📅 Name: {cal.get('name')}")
                print(f"      ID: {cal.get('id')[:20]}...")
                print(f"      Can Edit: {cal.get('canEdit')}")
                print()
            return True
        else:
            print("⚠️  No calendars found (this might be okay)")
            return True
            
    except Exception as e:
        print(f"❌ Failed to list calendars: {str(e)}")
        return False


def test_get_availability():
    """Test checking calendar availability."""
    print("\n" + "="*60)
    print("TEST: Get Availability")
    print("="*60)
    
    try:
        service = get_outlook_calendar_service()
        
        # Check availability for next 3 days
        start_date = datetime.now(timezone.utc)
        end_date = start_date + timedelta(days=3)
        
        print(f"   Checking availability from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}...")
        
        slots = service.get_availability(
            start_date=start_date,
            end_date=end_date,
            slot_duration_minutes=30
        )
        
        if slots:
            print(f"\n✅ Found {len(slots)} available slots:\n")
            # Show first 5 slots
            for slot in slots[:5]:
                print(f"   🕐 {slot['display']}")
            
            if len(slots) > 5:
                print(f"\n   ... and {len(slots) - 5} more slots")
            
            return True, slots
        else:
            print("⚠️  No available slots found (calendar might be fully booked)")
            return True, []
            
    except Exception as e:
        print(f"❌ Failed to get availability: {str(e)}")
        return False, []


def test_create_appointment(available_slots: list):
    """Test creating a test appointment."""
    print("\n" + "="*60)
    print("TEST: Create Appointment")
    print("="*60)
    
    if not available_slots:
        print("⚠️  Skipping - no available slots to book")
        return True, None
    
    try:
        service = get_outlook_calendar_service()
        
        # Use the first available slot
        slot = available_slots[0]
        start_time = datetime.fromisoformat(slot['start'])
        end_time = datetime.fromisoformat(slot['end'])
        
        print(f"   Creating test appointment:")
        print(f"   📅 Time: {slot['display']}")
        print(f"   👤 Attendee: test@example.com")
        
        result = service.create_appointment(
            subject="[TEST] AI Receptionist - Test Appointment",
            start_time=start_time,
            end_time=end_time,
            attendee_email="test@example.com",
            attendee_name="Test User",
            description="This is a test appointment created by the AI Receptionist system. Please delete if found."
        )
        
        if result.get("success"):
            print(f"\n✅ Appointment created successfully!")
            print(f"   Event ID: {result.get('event_id', 'N/A')[:20]}...")
            return True, result.get("event_id")
        else:
            print(f"\n❌ Failed to create appointment: {result.get('error')}")
            return False, None
            
    except Exception as e:
        print(f"❌ Failed to create appointment: {str(e)}")
        return False, None


def test_cancel_appointment(event_id: str):
    """Test cancelling the test appointment."""
    print("\n" + "="*60)
    print("TEST: Cancel Appointment")
    print("="*60)
    
    if not event_id:
        print("⚠️  Skipping - no appointment to cancel")
        return True
    
    try:
        service = get_outlook_calendar_service()
        
        print(f"   Cancelling test appointment...")
        
        success = service.cancel_appointment(event_id)
        
        if success:
            print(f"✅ Appointment cancelled successfully!")
            return True
        else:
            print(f"❌ Failed to cancel appointment")
            return False
            
    except Exception as e:
        print(f"❌ Failed to cancel appointment: {str(e)}")
        return False


def run_all_tests():
    """Run all calendar tests."""
    print("\n" + "="*60)
    print("📅 OUTLOOK CALENDAR SERVICE - TESTS")
    print("="*60)
    
    results = []
    
    # Test 1: Connection
    results.append(("Calendar Connection", test_calendar_connection()))
    
    if not results[-1][1]:
        print("\n❌ Cannot proceed without calendar connection")
        return False
    
    # Test 2: List calendars
    results.append(("List Calendars", test_list_calendars()))
    
    # Test 3: Get availability
    availability_result, slots = test_get_availability()
    results.append(("Get Availability", availability_result))
    
    # Test 4: Create appointment
    create_result, event_id = test_create_appointment(slots)
    results.append(("Create Appointment", create_result))
    
    # Test 5: Cancel appointment (cleanup)
    if event_id:
        results.append(("Cancel Appointment", test_cancel_appointment(event_id)))
    
    # Summary
    print("\n" + "="*60)
    print("📊 CALENDAR TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, r in results if r)
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\nTotal: {passed}/{len(results)} tests passed")
    
    return passed == len(results)


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)