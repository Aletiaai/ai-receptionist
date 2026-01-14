"""
Slot Extractor Utility
Extracts user information (name, email, phone) from conversation using LLM.
Uses OpenAI for robust, context-aware extraction.
"""

import json
import os
from typing import Optional
from openai import OpenAI
from src.utils.logger import get_logger

# Initialize logger
logger = get_logger(__name__)


# Extraction prompt template
EXTRACTION_PROMPT = """You are a data extraction assistant. Analyze the conversation and extract user information.

EXTRACTION RULES:

1. **Phone Number:**
    - Extract as 10-12 digits including country code
    - Format: +[country code][number] (e.g., +1234567890 or +521234567890)
    - If no country code provided, assume +1 (US)
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


class SlotExtractor:
    """Extracts structured information from conversations using LLM."""
    
    def __init__(self):
        """Initialize the slot extractor with OpenAI client."""
        logger.info("Initializing LLM-based slot extractor")
        
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.error("OPENAI_API_KEY not set for slot extractor")
            raise ValueError("OPENAI_API_KEY is required")
        
        self.client = OpenAI(api_key=api_key)
        self.model = os.getenv('OPENAI_EXTRACTION_MODEL', 'gpt-4.1-mini')
        
        logger.info("Slot extractor initialized", model=self.model)
    
    def extract_all(
        self,
        conversation_history: list,
        current_slots: Optional[dict] = None,
        session_id: Optional[str] = None
    ) -> dict:
        """
        Extract all slot values from the conversation using LLM.
        Args:
            conversation_history: List of conversation messages
            current_slots: Currently collected slot data (to avoid re-extracting)
            session_id: Optional session ID for logging
        Returns:
            Dictionary with extracted values (only new extractions)
        """
        current_slots = current_slots or {}
        
        # Check which fields we still need
        missing_fields = self.get_missing_slots(
            current_slots, 
            ['name', 'email', 'phone']
        )
        
        if not missing_fields:
            logger.debug(
                "All slots already collected, skipping extraction",
                session_id=session_id
            )
            return {}
        
        logger.info(
            "Extracting slots via LLM",
            session_id=session_id,
            missing_fields=missing_fields,
            message_count=len(conversation_history)
        )
        
        # Build conversation text for extraction
        conversation_text = self._build_conversation_text(conversation_history)
        
        if not conversation_text.strip():
            logger.debug("No conversation content to extract from", session_id=session_id)
            return {}
        
        try:
            # Call OpenAI for extraction
            extracted = self._call_extraction_api(
                conversation_text=conversation_text,
                session_id=session_id
            )
            
            # Filter to only return newly extracted values (not already collected)
            new_extractions = {}
            for field in missing_fields:
                if extracted.get(field):
                    new_extractions[field] = extracted[field]
            
            if new_extractions:
                logger.info(
                    "New slots extracted",
                    session_id=session_id,
                    extracted_fields=list(new_extractions.keys())
                )
            else:
                logger.debug(
                    "No new slots found in conversation",
                    session_id=session_id
                )
            
            return new_extractions
            
        except Exception as e:
            logger.error(
                "Slot extraction failed",
                session_id=session_id,
                error=str(e),
                exc_info=True
            )
            return {}
    
    def _build_conversation_text(self, conversation_history: list) -> str:
        """
        Build a text representation of the conversation for extraction.
        Args:
            conversation_history: List of message dictionaries
        Returns:
            Formatted conversation string
        """
        lines = []
        
        for msg in conversation_history:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            
            # Skip system messages
            if role == 'system':
                continue
            
            # Format role label
            role_label = 'USER' if role == 'user' else 'ASSISTANT'
            lines.append(f"{role_label}: {content}")
        
        return "\n".join(lines)
    
    def _call_extraction_api(
        self,
        conversation_text: str,
        session_id: Optional[str] = None
    ) -> dict:
        """
        Call OpenAI API to extract slot values.
        Args:
            conversation_text: Formatted conversation string
            session_id: Session ID for logging
        Returns:
            Dictionary with extracted values
        """
        logger.debug(
            "Calling OpenAI for extraction",
            session_id=session_id,
            text_length=len(conversation_text)
        )
        
        messages = [
            {"role": "system", "content": EXTRACTION_PROMPT},
            {"role": "user", "content": f"Extract information from this conversation:\n\n{conversation_text}"}
        ]
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0,  # Deterministic extraction
            max_tokens=200,
            response_format={"type": "json_object"}
        )
        
        result_text = response.choices[0].message.content
        
        logger.debug(
            "Extraction API response received",
            session_id=session_id,
            tokens_used=response.usage.total_tokens,
            raw_response=result_text
        )
        
        # Parse JSON response
        try:
            result = json.loads(result_text)
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse extraction response as JSON",
                session_id=session_id,
                raw_response=result_text,
                error=str(e)
            )
            return {}
        
        # Clean up null values
        cleaned = {}
        for field in ['name', 'email', 'phone']:
            value = result.get(field)
            if value and value != 'null' and str(value).lower() != 'null':
                cleaned[field] = self._clean_value(field, value)
        
        return cleaned
    
    def _clean_value(self, field: str, value: str) -> str:
        """
        Clean and validate extracted value.
        Args:
            field: Field name (name, email, phone)
            value: Extracted value
        Returns:
            Cleaned value
        """
        value = str(value).strip()
        
        if field == 'phone':
            # Ensure phone starts with + and contains only digits after
            digits = ''.join(c for c in value if c.isdigit())
            if not value.startswith('+'):
                # Add +1 as default country code if not present
                if len(digits) == 10:
                    return f"+1{digits}"
                return f"+{digits}"
            return f"+{digits}"
        
        elif field == 'email':
            return value.lower()
        
        elif field == 'name':
            # Proper capitalization
            return ' '.join(word.capitalize() for word in value.split())
        
        return value
    
    def get_missing_slots(self, current_slots: dict, required_fields: list) -> list:
        """
        Get list of required fields that are still missing.
        Args:
            current_slots: Currently collected slot data
            required_fields: List of required field names
        Returns:
            List of missing field names
        """
        missing = [
            field for field in required_fields
            if not current_slots.get(field)
        ]
        return missing
    
    def is_complete(self, current_slots: dict, required_fields: list) -> bool:
        """
        Check if all required slots have been collected.
        Args:
            current_slots: Currently collected slot data
            required_fields: List of required field names
        Returns:
            True if all required fields are collected
        """
        return len(self.get_missing_slots(current_slots, required_fields)) == 0
    
    def get_collection_status(
        self,
        current_slots: dict,
        required_fields: list
    ) -> dict:
        """
        Get detailed status of slot collection.
        Args:
            current_slots: Currently collected slot data
            required_fields: List of required field names
        Returns:
            Status dictionary with collected, missing, and completion info
        """
        missing = self.get_missing_slots(current_slots, required_fields)
        collected = [f for f in required_fields if current_slots.get(f)]
        
        return {
            'collected': collected,
            'collected_values': {f: current_slots.get(f) for f in collected},
            'missing': missing,
            'is_complete': len(missing) == 0,
            'progress': f"{len(collected)}/{len(required_fields)}"
        }


# Singleton instance
_slot_extractor = None


def get_slot_extractor() -> SlotExtractor:
    """Get or create the slot extractor singleton."""
    global _slot_extractor
    if _slot_extractor is None:
        logger.debug("Creating new LLM-based slot extractor instance")
        _slot_extractor = SlotExtractor()
    return _slot_extractor