"""
Configuration Settings
Centralizes all configuration values for the AI Receptionist system.
Environment variables override defaults.
"""

import os

# =============================================================================
# AWS Configuration
# =============================================================================
AWS_CONFIG = {
    "region": os.getenv("AWS_REGION", "us-east-2"),
    "dynamodb_tables": {
        "tenants": os.getenv("DYNAMODB_TENANTS_TABLE", "ai-receptionist-tenants"),
        "conversations": os.getenv("DYNAMODB_CONVERSATIONS_TABLE", "ai-receptionist-conversations"),
        "appointments": os.getenv("DYNAMODB_APPOINTMENTS_TABLE", "ai-receptionist-appointments"),
    }
}

# =============================================================================
# OpenAI Configuration
# =============================================================================
OPENAI_CONFIG = {
    # Chat completion models
    "chat_model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
    "extraction_model": os.getenv("OPENAI_EXTRACTION_MODEL", "gpt-4.1-mini"),

    # Realtime API for voice
    "realtime_model": "gpt-realtime-2025-08-28",
    "voice": "marin",

    # Chat completion parameters
    "chat_temperature": 0.7,
    "chat_max_tokens": 500,

    # Extraction parameters
    "extraction_temperature": 0,
    "extraction_max_tokens": 200,

    # API endpoints
    "api_base": "https://api.openai.com/v1",
    "realtime_ws": "wss://api.openai.com/v1/realtime",
}

# =============================================================================
# Booking Configuration
# =============================================================================
BOOKING_CONFIG = {
    "days_ahead": 7,
    "max_slots": 10,
    "voice_max_slots": 5,
    "slot_duration_minutes": 30,
    "business_hours": {
        "start": 9,
        "end": 17
    },
    "default_timezone": os.getenv("TIMEZONE", "America/Mexico_City"),
}

# =============================================================================
# Voice Server Configuration
# =============================================================================
VOICE_CONFIG = {
    # Default voices per language
    "voice_spanish": "marin",
    "voice_english": "marin",

    # WebSocket parameters
    "ws_ping_interval": 20,
    "ws_ping_timeout": 10,
    "ws_close_timeout": 5,

    # Connection parameters
    "max_reconnect_attempts": 3,
    "reconnect_delay_seconds": 1,

    # Timeouts
    "api_timeout_seconds": 30,
    "hangup_timeout_seconds": 10,

    # Stale call cleanup
    "stale_call_timeout_seconds": int(os.getenv("STALE_CALL_TIMEOUT", "1800")),  # 30 minutes
    "cleanup_interval_seconds": 300,  # 5 minutes

    # Default tenant
    "default_tenant": "consulate",
}

# =============================================================================
# Email Configuration
# =============================================================================
EMAIL_CONFIG = {
    "sender_name": os.getenv("EMAIL_SENDER_NAME", "AI Receptionist"),

    # Styling colors
    "colors": {
        "primary": "#2563eb",  # Blue - headers
        "success": "#16a34a",  # Green - admin notifications
        "background": "#f8fafc",
        "border": "#e2e8f0",
        "text_primary": "#1e293b",
        "text_secondary": "#64748b",
    }
}

# =============================================================================
# API Configuration
# =============================================================================
API_CONFIG = {
    "default_timeout": 30,

    # CORS headers
    "cors_headers": {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "POST,OPTIONS"
    },

    # Microsoft Graph API
    "graph_api_base": "https://graph.microsoft.com/v1.0",
}

# =============================================================================
# Logging Configuration
# =============================================================================
LOGGING_CONFIG = {
    "default_level": os.getenv("LOG_LEVEL", "INFO").upper(),

    # Local development format
    "local_format": "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
    "local_date_format": "%Y-%m-%d %H:%M:%S",

    # Voice server format
    "voice_format": "%(asctime)s - %(levelname)s - [%(call_id)s] %(message)s",
    "voice_date_format": "%Y-%m-%d %H:%M:%S",
}

# =============================================================================
# Language Detection Configuration
# =============================================================================
LANGUAGE_INDICATORS = {
    "spanish": {
        # Greetings
        'hola', 'buenos', 'buenas', 'días', 'tardes', 'noches',
        # Pronouns
        'yo', 'tú', 'él', 'ella', 'nosotros', 'ustedes', 'ellos',
        # Common verbs
        'quiero', 'necesito', 'tengo', 'puedo', 'estoy', 'soy',
        'quisiera', 'gustaría', 'gustaria', 'hacer', 'tener', 'poder',
        # Question words
        'qué', 'cómo', 'cuándo', 'dónde', 'cuál', 'quién', 'por',
        'que', 'como', 'cuando', 'donde', 'cual', 'quien',
        # Articles and prepositions
        'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas',
        'de', 'en', 'con', 'para', 'por',
        # Common words
        'sí', 'no', 'gracias', 'favor', 'ayuda', 'información',
        'cita', 'reservar', 'agendar', 'fecha', 'hora',
        # Appointment related
        'disponibilidad', 'horario', 'calendario', 'reunión',
        'consulta', 'servicio', 'atención'
    },
    "english": {
        # Greetings
        'hello', 'hi', 'hey', 'good', 'morning', 'afternoon', 'evening',
        # Pronouns
        'i', 'you', 'he', 'she', 'we', 'they', 'my', 'your',
        # Common verbs
        'want', 'need', 'have', 'can', 'would', 'like', 'make', 'get',
        'am', 'is', 'are', 'was', 'were',
        # Question words
        'what', 'how', 'when', 'where', 'which', 'who', 'why',
        # Articles and prepositions
        'the', 'a', 'an', 'of', 'in', 'with', 'for', 'to', 'at',
        # Common words
        'yes', 'no', 'thanks', 'thank', 'please', 'help', 'information',
        'appointment', 'book', 'schedule', 'date', 'time',
        # Appointment related
        'availability', 'meeting', 'consultation', 'service'
    },
    "spanish_chars": set('áéíóúüñ¿¡'),
}

# =============================================================================
# Booking Flow States
# =============================================================================
BOOKING_STATES = {
    "none": "none",
    "awaiting_day_selection": "awaiting_day_selection",  # User selects a day
    "showing_slots": "showing_slots",
    "awaiting_selection": "awaiting_selection",  # User selects a time slot
    "confirmed": "confirmed",
}

# =============================================================================
# Day Selection Ordinals (for parsing day selection)
# =============================================================================
DAY_ORDINALS = {
    "first": 1, "primero": 1, "primera": 1, "1st": 1,
    "second": 2, "segundo": 2, "segunda": 2, "2nd": 2,
    "third": 3, "tercero": 3, "tercera": 3, "3rd": 3,
    "fourth": 4, "cuarto": 4, "cuarta": 4, "4th": 4,
    "fifth": 5, "quinto": 5, "quinta": 5, "5th": 5,
    "sixth": 6, "sexto": 6, "sexta": 6, "6th": 6,
    "seventh": 7, "séptimo": 7, "séptima": 7, "7th": 7,
}

# =============================================================================
# OAuth Configuration
# =============================================================================
OAUTH_CONFIG = {
    "token_tenant_id": "global",
    "outlook_provider": "outlook",
    "authority_url": "https://login.microsoftonline.com",
}

# =============================================================================
# Default Voice Tenant Configurations
# =============================================================================
DEFAULT_VOICE_TENANTS = {
    "consulate": {
        "name": "Consulate Services",
        "voice": "marin",
        "language_default": "es",
        "business_hours": {"start": 9, "end": 17},
    },
    "realestate": {
        "name": "Real Estate Agency",
        "voice": "marin",
        "language_default": "en",
        "business_hours": {"start": 8, "end": 20},
    }
}

# =============================================================================
# Localization - Day and Month Names
# =============================================================================
LOCALIZATION = {
    "days": {
        "es": ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"],
        "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    },
    "months": {
        "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio",
               "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
        "en": ["January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"],
    }
}

# =============================================================================
# Slot Selection Ordinals
# =============================================================================
SLOT_ORDINALS = {
    "first": 1, "primero": 1, "primera": 1, "1st": 1,
    "second": 2, "segundo": 2, "segunda": 2, "2nd": 2,
    "third": 3, "tercero": 3, "tercera": 3, "3rd": 3,
    "fourth": 4, "cuarto": 4, "cuarta": 4, "4th": 4,
    "fifth": 5, "quinto": 5, "quinta": 5, "5th": 5,
}
