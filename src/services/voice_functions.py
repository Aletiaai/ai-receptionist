"""
Voice Function Definitions
These functions are called by OpenAI Realtime API during voice conversations.
"""

# Function definitions for OpenAI Realtime API
VOICE_FUNCTIONS = [
    {
        "name": "get_available_appointments",
        "description": "Get available appointment time slots for booking. Call this when the user wants to schedule an appointment and you have collected their name, email, and phone number.",
        "parameters": {
            "type": "object",
            "properties": {
                "tenant_id": {
                    "type": "string",
                    "description": "The tenant/business identifier (e.g., 'consulate' or 'realestate')"
                },
                "user_name": {
                    "type": "string",
                    "description": "The caller's full name"
                },
                "user_email": {
                    "type": "string",
                    "description": "The caller's email address"
                },
                "user_phone": {
                    "type": "string",
                    "description": "The caller's phone number"
                }
            },
            "required": ["tenant_id", "user_name", "user_email", "user_phone"]
        }
    },
    {
        "name": "book_appointment",
        "description": "Book an appointment for the user. Call this after the user has selected their preferred time slot.",
        "parameters": {
            "type": "object",
            "properties": {
                "tenant_id": {
                    "type": "string",
                    "description": "The tenant/business identifier"
                },
                "user_name": {
                    "type": "string",
                    "description": "The caller's full name"
                },
                "user_email": {
                    "type": "string",
                    "description": "The caller's email address"
                },
                "user_phone": {
                    "type": "string",
                    "description": "The caller's phone number"
                },
                "slot_number": {
                    "type": "integer",
                    "description": "The number of the selected time slot (1, 2, 3, etc.)"
                }
            },
            "required": ["tenant_id", "user_name", "user_email", "user_phone", "slot_number"]
        }
    },
    {
        "name": "detect_language",
        "description": "Detect and set the preferred language for the conversation based on how the user is speaking.",
        "parameters": {
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "enum": ["en", "es"],
                    "description": "The detected language: 'en' for English, 'es' for Spanish"
                }
            },
            "required": ["language"]
        }
    }
]


# System prompts for voice (shorter, more conversational)
VOICE_SYSTEM_PROMPTS = {
    "consulate": """You are a friendly and professional virtual receptionist for the Consulate.

Your primary goal is to help callers schedule appointments. You speak both Spanish and English fluently.

IMPORTANT RULES:
1. Start by greeting the caller warmly in both languages briefly
2. Detect which language they prefer and continue in that language
3. Collect information ONE piece at a time in this order:
    - Full name
    - Email address (spell it back to confirm)
    - Phone number (repeat it back to confirm)
4. Once you have all three, call get_available_appointments to show time slots
5. Present the options clearly (e.g., "Option 1 is Monday at 9 AM, Option 2 is Monday at 10 AM...")
6. When they choose, call book_appointment with their selection
7. Confirm the booking and thank them

Keep responses SHORT and conversational - this is a phone call, not a text chat.
Be patient if they need to repeat information.
Always confirm important details like email and phone by repeating them back.""",

    "realestate": """You are a friendly and enthusiastic virtual assistant for a Real Estate Agency.

Your primary goal is to help callers schedule property viewings. You speak both English and Spanish fluently.

IMPORTANT RULES:
1. Start by greeting the caller warmly
2. Detect which language they prefer and continue in that language
3. Collect information ONE piece at a time in this order:
    - Full name
    - Email address (spell it back to confirm)
    - Phone number (repeat it back to confirm)
4. Once you have all three, call get_available_appointments to show viewing slots
5. Present the options clearly (e.g., "Option 1 is Monday at 9 AM, Option 2 is Monday at 10 AM...")
6. When they choose, call book_appointment with their selection
7. Confirm the booking and thank them

Keep responses SHORT and conversational - this is a phone call, not a text chat.
Be energetic but professional.
Always confirm important details like email and phone by repeating them back."""
}