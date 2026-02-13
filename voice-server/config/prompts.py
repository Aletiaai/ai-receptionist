"""
Prompts and Templates
Centralizes all system prompts, user messages, and email templates.
All messages support bilingual format with 'en' and 'es' keys.
"""

# =============================================================================
# Slot Extraction Prompt
# =============================================================================
SLOT_EXTRACTION_PROMPT = """You are a data extraction assistant. Analyze the conversation and extract user information.

EXTRACTION RULES:

1. **Phone Number:**
    - Extract as 10-12 digits including country code
    - Format: +[country code][number] (e.g., +1234567890 or +521234567890)
    - If no country code provided, ask if it is a mexican number. If it is then append the prefix +52. If it is not then; ask if it is from The US. if it is then append the prefix +1.
    - If user spells out numbers ("five five five"), convert to digits
    - Return null if no valid phone found

2. **Email:**
    - Standard email format: word@domain.extension
    - Must contain @ and at least one dot after @
    - Return null if no valid email found

3. **Full Name:**
    - For English speakers: First name + Last name (e.g., "John Smith")
    - For Spanish speakers: Can be Name(s) + Paternal surname + Maternal surname (e.g., "María García López" or "Juan Carlos Rodríguez Pérez")
    - Capitalize properly
    - Return null if no valid name found

IMPORTANT:
- Only extract information explicitly provided by the USER (not the assistant)
- If information seems incomplete or unclear, return null for that field
- Do not guess or make up information

Respond ONLY with a JSON object in this exact format:
{
    "name": "extracted name or null",
    "email": "extracted email or null",
    "phone": "extracted phone or null"
}
"""

# =============================================================================
# Data Collection Status Messages (for OpenAI system prompt)
# =============================================================================
DATA_COLLECTION_MESSAGES = {
    "status_header": "\n\n--- DATA COLLECTION STATUS ---",
    "status_footer": "\n--- END STATUS ---",

    "collected_info": {
        "en": "\nCollected information:\n",
        "es": "\nInformación recopilada:\n",
    },

    "still_needed": {
        "en": "\nStill needed: {fields}\nNaturally ask for this information during the conversation. Ask for all fields at once.",
        "es": "\nAún se necesita: {fields}\nPide esta información de forma natural durante la conversación. Pide todos los campos a la vez.",
    },

    "all_collected": {
        "en": "\nAll required information collected! You can now help the user schedule an appointment.",
        "es": "\nToda la información requerida ha sido recopilada. Ahora puedes ayudar al usuario a agendar una cita.",
    },

    "none_collected": {
        "en": "\nNo user information collected yet. Begin by greeting the user, then naturally collect: name, email, phone. Collect all information at once.",
        "es": "\nAún no se ha recopilado información del usuario. Comienza saludando al usuario, luego recopila de forma natural: nombre, email, teléfono. Recopila toda la información a la vez.",
    },

    "language_instruction": {
        "en": "\n\nIMPORTANT: The user is communicating in {language}. You MUST respond in {language}.",
        "es": "\n\nIMPORTANTE: El usuario está comunicándose en {language}. DEBES responder en {language}.",
    },
}

# =============================================================================
# Booking Messages
# =============================================================================
BOOKING_MESSAGES = {
    "confirmation": {
        "en": """
--- APPOINTMENT CONFIRMED ---
The appointment has been successfully booked:
- Date and time: {display}
- Name: {name}
- Email: {email}
- Phone: {phone}

The user will receive a calendar invitation via email.
Please confirm the appointment to the user and ask if the user has another question or if the user needs any other information.
--- END ---
""",
        "es": """
--- CITA CONFIRMADA ---
La cita ha sido reservada exitosamente:
- Fecha y hora: {display}
- Nombre: {name}
- Email: {email}
- Teléfono: {phone}

El usuario recibirá una invitación de calendario por correo electrónico.
Por favor confirma la cita al usuario y preguntale si tiene otra pregunta o si necesita alguna otra información.
--- FIN ---
"""
    },

    "show_available_days": {
        "en": """
--- SHOW AVAILABLE DAYS ---
All user information has been collected. Now show the available days for booking.

{formatted_days}

Ask the user to select a day by number (1, 2, 3, etc.) to see the available time slots for that day.
--- END ---
""",
        "es": """
--- MOSTRAR DÍAS DISPONIBLES ---
Toda la información del usuario ha sido recopilada. Ahora muestra los días disponibles para agendar.

{formatted_days}

Pide al usuario que seleccione un día usando el número (1, 2, 3, etc.) para ver los horarios disponibles de ese día.
--- FIN ---
"""
    },

    "show_availability": {
        "en": """
--- SHOW AVAILABILITY ---
The user selected {selected_day}. Now show the available time slots for that day.

{formatted_slots}

Ask the user to select a time slot by number (1, 2, 3, etc.)
--- END ---
""",
        "es": """
--- MOSTRAR DISPONIBILIDAD ---
El usuario seleccionó {selected_day}. Ahora muestra los horarios disponibles para ese día.

{formatted_slots}

Pide al usuario que seleccione un horario usando el número (1, 2, 3, etc.)
--- FIN ---
"""
    },

    "booking_error": {
        "en": "\n\n[Error booking appointment: {error}. Please try again.]\n",
        "es": "\n\n[Error al reservar la cita: {error}. Por favor intenta de nuevo.]\n",
    },

    "no_slots_available": {
        "en": "\n\n[No available slots this week. Apologize to the user and suggest they call directly.]\n",
        "es": "\n\n[No hay horarios disponibles esta semana. Disculpa al usuario y sugiere que llame directamente.]\n",
    },

    "no_days_available": {
        "en": "\n\n[No available days in the next 7 work days. Apologize to the user and suggest they call directly.]\n",
        "es": "\n\n[No hay días disponibles en los próximos 7 días hábiles. Disculpa al usuario y sugiere que llame directamente.]\n",
    },

    "days_header": {
        "en": "Available days:\n",
        "es": "Días disponibles:\n",
    },

    "slots_header": {
        "en": "Available time slots:\n",
        "es": "Horarios disponibles:\n",
    },

    "no_slots_message": {
        "en": "No available slots in the coming days.",
        "es": "No hay horarios disponibles en los próximos días.",
    },

    "no_days_message": {
        "en": "No available days in the coming week.",
        "es": "No hay días disponibles en la próxima semana.",
    },
}

# =============================================================================
# Voice Instructions (for OpenAI Realtime API)
# =============================================================================
VOICE_INSTRUCTIONS = {
    "consulate": """You are a friendly and professional Mexican virtual receptionist for the Consulate.

Your primary goal is to help callers schedule appointments. You speak both Spanish from Mexico and English fluently.

IMPORTANT RULES:
1. Start by greeting the caller warmly in Spanish first, then in English with the following message: 'Thank you for calling the Consulate of Mexico. I am an automated assistant and can provide you with support and information such as 'passport information,' 'visas,' or help you schedule appointments with the consulate. Tell me, how may I assist you?'
2. Detect which language they prefer based on their response and continue in that language
3. Confirm the help the caller needs and start collecting information ONE piece at a time in this order:
    - Full name (ask them to spell it if unclear)
    - Email address (spell it back to confirm)
    - Phone number (repeat it back to confirm). Ask if it is a mexican number. If it is then append the prefix +52. If it is not then; ask if it is from The US. if it is then append the prefix +1.
4. Once you have all three pieces of information, let the user know that you will look for available days, then call the get_available_days function
5. Present the available DAYS clearly (e.g., "Option 1 is Monday January 13th, Option 2 is Tuesday January 14th")
6. When they choose a day, call the get_available_slots function with that day number
7. Present the available TIME SLOTS for that day clearly (e.g., "Option 1 is 9 AM, Option 2 is 10:30 AM")
8. When they choose a time slot, call the book_appointment function
9. Confirm the booking details and ask if the caller has another question or if the caller needs other information.

Keep responses SHORT and conversational - this is a phone call.
Be patient if they need to repeat information.
If you don't understand something, politely ask them to repeat.""",

    "realestate": """You are a friendly and enthusiastic Mexican virtual assistant for a Real Estate Agency.

Your primary goal is to help callers schedule property viewings. You speak both English and Spanish from Mexico fluently.

IMPORTANT RULES:
1. Start by greeting the caller warmly in English first, then briefly in Spanish with the following message: 'Thank you for calling the Consulate of Mexico. I am an automated assistant and can provide you with support and information such as 'passport information,' 'visas,' or help you schedule appointments with the consulate. Tell me, how may I assist you?'
2. Detect which language they prefer based on their response and continue in that language
3. Confirm the help the caller needs and start collecting information ONE piece at a time in this order:
    - Full name (ask them to spell it if unclear)
    - Email address (spell it back to confirm)
    - Phone number (repeat it back to confirm). Ask if it is a mexican number. If it is then append the prefix +52. If it is not then; ask if it is from The US. if it is then append the prefix +1.
4. Once you have all three pieces of information, let the user know that you will look for available days, then call the get_available_days function
5. Present the available DAYS clearly (e.g., "Option 1 is Monday January 13th, Option 2 is Tuesday January 14th")
6. When they choose a day, call the get_available_slots function with that day number
7. Present the available TIME SLOTS for that day clearly (e.g., "Option 1 is 9 AM, Option 2 is 10:30 AM")
8. When they choose a time slot, call the book_appointment function
9. Confirm the booking details and ask if the caller has another question or if the caller needs other information.

Keep responses SHORT and conversational - this is a phone call.
Be energetic but professional.
If you don't understand something, politely ask them to repeat.""",

    "initial_greeting": "Greet the caller warmly in Spanish from Mexico first, then in English with the following message 'Thank you for calling the Consulate of Mexico. I am an automated assistant and can provide you with support and information such as 'passport information,' 'visas,' or help you schedule appointments with the consulate. Tell me, how may I assist you?'",
}

# =============================================================================
# Voice Error Messages
# =============================================================================
VOICE_ERROR_MESSAGES = {
    "missing_user_data": {
        "en": "I still need your {fields} before I can check availability.",
        "es": "Todavía necesito tu {fields} antes de poder verificar la disponibilidad.",
    },

    "missing_contact_info": {
        "en": "I don't have your contact information. Let me get your name and email first.",
        "es": "No tengo tu información de contacto. Proporcioname tu nombre y correo primero, por favor.",
    },

    "invalid_slot_number": {
        "en": "Please choose a slot between 1 and {max_slots}.",
        "es": "Por favor elige un horario entre 1 y {max_slots}.",
    },

    "no_slots_provided": {
        "en": "No available slots provided. Please get available slots first.",
        "es": "No hay horarios disponibles. Por favor obtén los horarios disponibles primero.",
    },

    "slot_conflict": {
        "en": "I'm sorry, that time slot was just booked by someone else. Would you like to choose a different time?",
        "es": "Lo siento, ese horario acaba de ser reservado por alguien más. ¿Te gustaría elegir otro horario?",
    },

    "booking_system_unavailable": {
        "en": "I'm sorry, the booking system is not configured. Please call back later.",
        "es": "Lo siento, el sistema de reservas no está configurado. Por favor llama más tarde.",
    },

    "service_unavailable": {
        "en": "I'm sorry, the scheduling service is currently unavailable.",
        "es": "Lo siento, el servicio de citas no está disponible por el momento.",
    },

    "service_issues": {
        "en": "I'm sorry, the scheduling service is experiencing issues. Please try again later.",
        "es": "Lo siento, el servicio de citas está experimentando problemas. Por favor intenta más tarde.",
    },

    "timeout": {
        "en": "I'm sorry, the request timed out. Please try again in a moment.",
        "es": "Lo siento, la solicitud excedió el tiempo de espera. Por favor intenta en un momento.",
    },

    "connection_error": {
        "en": "I'm sorry, I couldn't connect to the scheduling service. Please try again later.",
        "es": "Lo siento, no pude conectar con el servicio de citas. Por favor intenta más tarde.",
    },

    "network_error": {
        "en": "I'm sorry, there was a network issue. Please try again.",
        "es": "Lo siento, hubo un problema de red. Por favor intenta de nuevo.",
    },

    "generic_error": {
        "en": "I'm sorry, something went wrong. Please try again later or call back.",
        "es": "Lo siento, algo salió mal. Por favor intenta más tarde o llama de nuevo.",
    },

    "unexpected_response": {
        "en": "I'm sorry, I received an unexpected response. Please try again.",
        "es": "Lo siento, recibí una respuesta inesperada. Por favor intenta de nuevo.",
    },

    "booking_confirmation": {
        "en": "Your appointment has been booked for {slot_display}. You will receive a confirmation email at {user_email}. Thanks for using the scheduling appointment service.",
        "es": "Tu cita ha sido reservada para {slot_display}. Recibirás un correo de confirmación en {user_email}. Gracias por usar el servicio de citas",
    },

    "booking_failed": {
        "en": "I'm sorry, I couldn't complete the booking. {error}",
        "es": "Lo siento, no pude completar la reserva. {error}",
    },

    "slots_available": {
        "en": "I have the following time slots available: {slot_descriptions}. Which option would you prefer?",
        "es": "Tengo los siguientes horarios disponibles: {slot_descriptions}. ¿Cuál opción prefieres?",
    },

    "no_slots_week": {
        "en": "I'm sorry, there are no available slots in the next 7 days. Would you like me to check further out?",
        "es": "Lo siento, no hay horarios disponibles en los próximos 7 días. ¿Te gustaría que revisara más adelante?",
    },

    "days_available": {
        "en": "I have availability on the following days: {day_descriptions}. Which day would you prefer?",
        "es": "Tengo disponibilidad en los siguientes días: {day_descriptions}. ¿Qué día prefieres?",
    },

    "no_days_week": {
        "en": "I'm sorry, there are no available days in the next 7 days. Would you like me to check further out?",
        "es": "Lo siento, no hay días disponibles en los próximos 7 días. ¿Te gustaría que revisara más adelante?",
    },

    "invalid_day_number": {
        "en": "Please choose a day between 1 and {max_days}.",
        "es": "Por favor elige un día entre 1 y {max_days}.",
    },

    "day_selected": {
        "en": "Great, you selected {day_display}. Let me check the available times for that day.",
        "es": "Perfecto, seleccionaste {day_display}. Déjame revisar los horarios disponibles para ese día.",
    },
}

# =============================================================================
# Email Templates
# =============================================================================
EMAIL_TEMPLATES = {
    "user_confirmation": {
        "en": {
            "subject": "Appointment Confirmation - {tenant_name}",
            "body": """
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background-color: {primary_color}; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
                    .content {{ background-color: {bg_color}; padding: 30px; border-radius: 0 0 8px 8px; }}
                    .appointment-box {{ background-color: white; border: 1px solid {border_color}; border-radius: 8px; padding: 20px; margin: 20px 0; }}
                    .label {{ color: {text_secondary}; font-size: 12px; text-transform: uppercase; margin-bottom: 5px; }}
                    .value {{ font-size: 18px; font-weight: bold; color: {text_primary}; }}
                    .footer {{ text-align: center; color: {text_secondary}; font-size: 12px; margin-top: 20px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>Appointment Confirmed</h1>
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
        },
        "es": {
            "subject": "Confirmación de Cita - {tenant_name}",
            "body": """
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background-color: {primary_color}; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
                    .content {{ background-color: {bg_color}; padding: 30px; border-radius: 0 0 8px 8px; }}
                    .appointment-box {{ background-color: white; border: 1px solid {border_color}; border-radius: 8px; padding: 20px; margin: 20px 0; }}
                    .label {{ color: {text_secondary}; font-size: 12px; text-transform: uppercase; margin-bottom: 5px; }}
                    .value {{ font-size: 18px; font-weight: bold; color: {text_primary}; }}
                    .footer {{ text-align: center; color: {text_secondary}; font-size: 12px; margin-top: 20px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>Cita Confirmada</h1>
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
        }
    },

    "admin_notification": {
        "subject": "Nueva Cita Agendada - {user_name}",
        "body": """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: {success_color}; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ background-color: {bg_color}; padding: 30px; border-radius: 0 0 8px 8px; }}
                .info-box {{ background-color: white; border: 1px solid {border_color}; border-radius: 8px; padding: 20px; margin: 20px 0; }}
                .row {{ display: flex; margin-bottom: 10px; }}
                .label {{ color: {text_secondary}; width: 120px; font-weight: bold; }}
                .value {{ color: {text_primary}; }}
                .footer {{ text-align: center; color: {text_secondary}; font-size: 12px; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Nueva Cita Agendada</h1>
                </div>
                <div class="content">
                    <p>Se ha agendado una nueva cita a través del Asistente Virtual.</p>

                    <div class="info-box">
                        <h3 style="margin-top: 0; color: {text_primary};">Información del Cliente</h3>
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
                        <h3 style="margin-top: 0; color: {text_primary};">Detalles de la Cita</h3>
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
    }
}
