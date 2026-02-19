# AI Receptionist

A production-ready, **multi-agent** AI system that schedules appointments through natural conversation **via text chat or phone call** in English and Spanish.
Built with Python and **deployed on AWS** (Lambda, Fargate, DynamoDB), this system integrates OpenAI's Realtime API for voice, Microsoft Azure AD and Outlook Calendar for availability and booking, and SendGrid for email confirmations. It supports multiple business tenants from a single deployment, making it reusable and scalable across different use cases.

Designed and built as a freelance project demonstrating end-to-end GenAI application development: from architecture and prompt engineering to cloud deployment and real-world integrations.

## Features

- **Text Chat API** - RESTful API for web/mobile chat integrations
- **Voice Calls** - Phone-based appointment booking via OpenAI Realtime API
- **Multi-Tenant** - Support multiple businesses with custom configurations
- **Outlook Calendar Integration** - Automatic availability checking and booking via Microsoft Graph API
- **Two-Step Booking Flow** - User selects a day, then a time slot
- **Email Notifications** - Confirmation emails to users and admin notifications via SendGrid
- **Bilingual Support** - Automatic English/Spanish detection and responses

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AI Receptionist                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Text Chat Flow:                                                           │
│   ┌──────────┐    ┌─────────────┐    ┌──────────────┐    ┌───────────────┐  │
│   │  Client  │───>│ API Gateway │───>│    Lambda    │───>│    OpenAI     │  │
│   │ (Web/App)│<───│  (REST API) │<───│(chat_handler)│<───│  GPT-4.1-mini │  │
│   └──────────┘    └─────────────┘    └──────┬───────┘    └───────────────┘  │
│                                             │                               │
│   Voice Call Flow:                          │                               │
│   ┌──────────┐    ┌─────────────┐    ┌──────┴───────┐                       │
│   │  Phone   │───>│   OpenAI    │───>│Voice Server  │                       │
│   │  (SIP)   │<───│Realtime API │<───│  (Fargate)   │                       │
│   └──────────┘    └─────────────┘    └──────┬───────┘                       │
│                                             │                               │
│   Shared Services:                          ▼                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                         AWS DynamoDB                                │   │
│   │  ┌─────────────┐  ┌──────────────────┐  ┌─────────────────────┐     │   │
│   │  │   Tenants   │  │  Conversations   │  │    Appointments     │     │   │
│   │  └─────────────┘  └──────────────────┘  └─────────────────────┘     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                             │                               │
│   ┌─────────────────────────────────────────┴───────────────────────────┐   │
│   │                      External Services                              │   │
│   │  ┌─────────────────┐                    ┌─────────────────────┐     │   │
│   │  │ Outlook Calendar│                    │      SendGrid       │     │   │
│   │  │(Microsoft Graph)│                    │   (Email Service)   │     │   │
│   │  └─────────────────┘                    └─────────────────────┘     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
ai-receptionist/
├── config/                    # Shared configuration
│   ├── settings.py           # All system settings (booking, voice, API, etc.)
│   └── prompts.py            # AI prompts and message templates
│
├── src/
│   ├── handlers/             # Lambda entry points
│   │   ├── router.py         # Routes requests to appropriate handler
│   │   ├── chat_handler.py   # Text chat logic with slot extraction
│   │   └── voice_handler.py  # Voice endpoints for booking operations
│   │
│   ├── services/             # Business logic (singleton pattern)
│   │   ├── dynamo_service.py # DynamoDB operations
│   │   ├── openai_service.py # Chat completions
│   │   ├── booking_service.py# Appointment booking orchestration
│   │   ├── outlook_calendar_service.py # Microsoft Graph API
│   │   └── email_service.py  # SendGrid email notifications
│   │
│   └── utils/
│       ├── logger.py         # Structured logging
│       ├── language_detector.py # Auto-detect English/Spanish
│       └── slot_extractor.py # Extract user info from conversation
│
├── voice-server/             # Standalone FastAPI server for voice
│   ├── server.py             # Main voice server with WebSocket handling
│   ├── config/               # Synced config from main project
│   ├── Dockerfile            # Container configuration
│   └── requirements.txt      # Voice server dependencies
│
├── deploy.py                 # Lambda deployment script
├── auth_outlook.py           # OAuth setup for Outlook calendar
├── requirements.txt          # Main project dependencies
└── test_*.py                 # Test files
```

---

## Prerequisites

- **Python 3.12+**
- **Docker** (for Lambda deployment and voice server)
- **AWS Account** with:
  - Lambda
  - API Gateway
  - DynamoDB
  - ECR (for voice server container)
  - ECS/Fargate (for voice server)
- **OpenAI Account** with API access and Realtime API access
- **Microsoft Azure AD App** (for Outlook calendar)
- **SendGrid Account** (for email notifications)
- **Phone Number Provider** (Twilio or OpenAI SIP)

---

## Setup

### 1. Clone and Install Dependencies

```bash
git clone <repository-url>
cd ai-receptionist

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```bash
# AWS Configuration
AWS_REGION=us-east-2
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key

# OpenAI
OPENAI_API_KEY=sk-proj-...

# DynamoDB Tables
DYNAMODB_TENANTS_TABLE=ai-receptionist-tenants
DYNAMODB_CONVERSATIONS_TABLE=ai-receptionist-conversations
DYNAMODB_APPOINTMENTS_TABLE=ai-receptionist-appointments

# Microsoft Azure (Outlook Calendar)
AZURE_CLIENT_ID=your_azure_client_id
AZURE_TENANT_ID=your_azure_tenant_id
AZURE_CLIENT_SECRET=your_azure_client_secret

# SendGrid (Email)
SENDGRID_API_KEY=your_sendgrid_api_key
SENDGRID_FROM_EMAIL=noreply@yourdomain.com

# API Gateway (after deployment)
API_GATEWAY_URL=https://xxx.execute-api.us-east-2.amazonaws.com

# Timezone
TIMEZONE=America/Mexico_City

# OpenAI Models
OPENAI_MODEL=gpt-4.1-mini
OPENAI_EXTRACTION_MODEL=gpt-4.1-mini
```

### 3. Create AWS Resources

#### DynamoDB Tables

Create three DynamoDB tables:

1. **ai-receptionist-tenants**
   - Partition key: `tenant_id` (String)

2. **ai-receptionist-conversations**
   - Partition key: `session_id` (String)
   - Sort key: `timestamp` (String)

3. **ai-receptionist-appointments**
   - Partition key: `appointment_id` (String)

#### Lambda Function

Create a Lambda function:
- Name: `ai-receptionist-chat-handler`
- Runtime: Python 3.12
- Handler: `lambda_function.handler`
- Memory: 512 MB
- Timeout: 30 seconds

#### API Gateway

Create an HTTP API with routes:
- `POST /chat/{tenant_id}` → Lambda function
- `POST /voice/get-days` → Lambda function
- `POST /voice/get-slots` → Lambda function
- `POST /voice/book` → Lambda function

### 4. Configure Microsoft Azure (Outlook Calendar)

1. Go to [Azure Portal](https://portal.azure.com) → Azure Active Directory → App registrations
2. Create a new registration:
   - Name: "AI Receptionist"
   - Supported account types: "Accounts in this organizational directory only"
   - Redirect URI: `http://localhost:8000/callback` (Web)
3. Note the **Application (client) ID** and **Directory (tenant) ID**
4. Go to Certificates & secrets → New client secret
5. Note the **secret value**
6. Go to API permissions → Add permission → Microsoft Graph:
   - `Calendars.ReadWrite`
   - `User.Read`
7. Grant admin consent

### 5. Authorize Outlook Calendar

Run the authorization script to connect your Outlook calendar:

```bash
python auth_outlook.py
```

This will:
1. Open a browser for Microsoft login
2. Request calendar permissions
3. Store the refresh token in DynamoDB

### 6. Seed Tenant Data

Create your tenant configuration in DynamoDB:

```bash
python seed_database.py
```

Or manually add a tenant to the `ai-receptionist-tenants` table:

```json
{
  "tenant_id": "consulate",
  "name": "Consulate Services",
  "active": true,
  "supported_languages": ["en", "es"],
  "required_fields": ["name", "email", "phone"],
  "admin_email": "admin@yourdomain.com",
  "system_prompt": "You are a helpful receptionist for the consulate...",
  "welcome_message": {
    "en": "Welcome! How can I help you today?",
    "es": "¡Bienvenido! ¿En qué puedo ayudarle?"
  }
}
```

---

## Deployment

### Deploy Lambda Function

The deployment script packages code with dependencies and uploads to AWS:

```bash
python deploy.py
```

This will:
1. Install dependencies in a Lambda-compatible Docker container
2. Package source code and dependencies into a ZIP file
3. Upload to AWS Lambda
4. Update environment variables and configuration

### Deploy Voice Server

The voice server runs as a Docker container on AWS Fargate.

#### 1. Build the Docker Image

```bash
cd voice-server

# Copy config files from main project
cp -r ../config/* config/

# Build image
docker build -t ai-receptionist-voice .
```

#### 2. Push to Amazon ECR

```bash
# Create ECR repository (first time only)
aws ecr create-repository --repository-name ai-receptionist-voice

# Login to ECR
aws ecr get-login-password --region us-east-2 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-2.amazonaws.com

# Tag and push
docker tag ai-receptionist-voice:latest <account-id>.dkr.ecr.us-east-2.amazonaws.com/ai-receptionist-voice:latest
docker push <account-id>.dkr.ecr.us-east-2.amazonaws.com/ai-receptionist-voice:latest
```

#### 3. Create Fargate Service

Create an ECS cluster and Fargate service with:
- Image: Your ECR image
- Port: 8080
- Environment variables:
  ```
  OPENAI_API_KEY=sk-proj-...
  BOOKING_WEBHOOK_URL=https://your-api-gateway-url
  OPENAI_WEBHOOK_SECRET=whsec_... (optional)
  ```

#### 4. Configure OpenAI Realtime API

In your OpenAI dashboard, configure the Realtime API webhook to point to your Fargate service URL:
```
https://your-fargate-service.amazonaws.com/webhook
```

---

## API Reference

### Text Chat API

#### POST `/chat/{tenant_id}`

Send a message and receive an AI response.

**Request:**
```json
{
  "session_id": "optional-existing-session-id",
  "message": "Hello, I'd like to schedule an appointment"
}
```

**Response:**
```json
{
  "session_id": "abc123",
  "message": "I'd be happy to help you schedule an appointment...",
  "detected_language": "en",
  "slot_status": {
    "collected": {"name": "John"},
    "missing": ["email", "phone"],
    "is_complete": false
  },
  "booking_state": "none",
  "is_new_session": true
}
```

### Voice Endpoints (Internal)

These endpoints are called by the voice server during phone calls:

#### POST `/voice/get-days`
Get available days for booking.

#### POST `/voice/get-slots`
Get time slots for a specific day.

#### POST `/voice/book`
Book an appointment.

---

## Configuration

### Business Hours

Edit `config/settings.py`:

```python
BOOKING_CONFIG = {
    "days_ahead": 7,              # Days to look ahead for availability
    "max_slots": 10,              # Max slots for chat
    "voice_max_slots": 5,         # Max slots for voice (shorter list)
    "slot_duration_minutes": 30,  # Appointment duration
    "business_hours": {
        "start": 9,               # 9 AM
        "end": 17                 # 5 PM
    },
    "default_timezone": "America/Mexico_City",
}
```

### Voice Settings

```python
VOICE_CONFIG = {
    "voice_spanish": "marin",     # OpenAI voice for Spanish
    "voice_english": "marin",     # OpenAI voice for English
    "default_tenant": "consulate",
}
```

### Adding New Tenants

Add tenant configurations in `config/settings.py`:

```python
DEFAULT_VOICE_TENANTS = {
    "consulate": {
        "name": "Consulate Services",
        "voice": "marin",
        "language_default": "es",
    },
    "realestate": {
        "name": "Real Estate Agency",
        "voice": "marin",
        "language_default": "en",
    }
}
```

And create the tenant record in DynamoDB with the full configuration.

---

## Booking Flow

### Chat Flow

```
1. User sends message
2. AI collects: name, email, phone
3. System fetches available DAYS (next 7 work days)
4. User selects a day (e.g., "1" or "Monday")
5. System fetches time SLOTS for that day
6. User selects a time slot (e.g., "2")
7. System books appointment and sends confirmation email
```

### Voice Flow

```
1. Call received → OpenAI Realtime API
2. AI greets and collects: name, email, phone
3. AI calls get_available_days function
4. User says preferred day
5. AI calls get_available_slots function
6. User says preferred time
7. AI calls book_appointment function
8. AI confirms booking and ends call
```

---

## Testing

### Run All Tests

```bash
pytest
```

### Run Specific Tests

```bash
# Test chat handler
pytest test_local.py -v

# Test calendar integration
pytest test_calendar.py -v

# Test booking flow
pytest test_booking_flow.py -v

# Test voice endpoints
pytest test_voice_endpoints.py -v

# Test email service
pytest test_email.py -v
```

### Test Chat Locally

```python
from src.handlers.chat_handler import process_message

result = process_message(
    tenant_id="consulate",
    session_id=None,
    user_message="Hola, quiero agendar una cita"
)
print(result["message"])
```

### Test Voice Server Locally

```bash
cd voice-server
uvicorn server:app --reload --port 8080

# Check health
curl http://localhost:8080/health
```

---

## Troubleshooting

### Lambda Deployment Issues

**Error: "Function not found"**
- Ensure the Lambda function exists with name `ai-receptionist-chat-handler`
- Check AWS credentials in `.env`

**Error: "Package too large"**
- The deployment uses Docker for Linux-compatible packages
- Ensure Docker is running

### Calendar Issues

**Error: "OAuth token not found"**
- Run `python auth_outlook.py` to authorize

**Error: "Token refresh failed"**
- The refresh token may have expired
- Re-run `python auth_outlook.py`

**No slots available**
- Check business hours in `config/settings.py`
- Verify the calendar isn't fully booked
- Check timezone configuration

### Voice Server Issues

**Calls not connecting**
- Verify `BOOKING_WEBHOOK_URL` points to your API Gateway
- Check Fargate task is running
- Verify OpenAI webhook is configured correctly

**Calls hang up unexpectedly**
- Check CloudWatch logs for errors
- Verify OpenAI API key has Realtime API access

### DynamoDB Issues

**Error: "Tenant not found"**
- Run `python seed_database.py` to create default tenants
- Verify table names match `.env` configuration

---

## Monitoring

### CloudWatch Logs

- **Lambda**: Check `/aws/lambda/ai-receptionist-chat-handler`
- **Voice Server**: Check ECS task logs

### Log Format

Logs include structured context:
```
2024-01-15 10:30:45 | INFO | chat_handler | process_message:95 | Processing chat request | tenant_id=consulate session_id=abc123
```

Voice server logs include call_id:
```
2024-01-15 10:30:45 - INFO - [call_abc123] User said: Hello, I need an appointment
```

---
