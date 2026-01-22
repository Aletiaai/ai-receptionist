"""
OpenAI Service
Handles all interactions with the OpenAI API for chat completions.
"""

import os
from typing import Optional
from openai import OpenAI

from config.settings import OPENAI_CONFIG
from config.prompts import DATA_COLLECTION_MESSAGES
from src.utils.logger import get_logger

# Initialize logger
logger = get_logger(__name__)


class OpenAIService:
    """Service class for OpenAI API operations."""
    
    def __init__(self):
        """Initialize OpenAI client."""
        logger.info("Initializing OpenAI service")

        api_key = os.getenv('OPENAI_API_KEY')

        if not api_key:
            logger.error("OPENAI_API_KEY environment variable not set")
            raise ValueError("OPENAI_API_KEY is required")

        self.client = OpenAI(api_key=api_key)
        self.default_model = OPENAI_CONFIG["chat_model"]

        logger.info(
            "OpenAI service initialized",
            model=self.default_model
        )
    
    def generate_response(
        self,
        user_message: str,
        conversation_history: list,
        system_prompt: str,
        tenant_id: str,
        session_id: str,
        detected_language: Optional[str] = None,
        slot_data: Optional[dict] = None,
        model: Optional[str] = None
    ) -> dict:
        """
        Generate a chat response using OpenAI.
        Args:
            user_message: The user's current message
            conversation_history: Previous messages in the conversation
            system_prompt: The tenant-specific system prompt
            tenant_id: Current tenant ID (for logging)
            session_id: Current session ID (for logging)
            detected_language: The detected language ('es' or 'en')
            slot_data: Currently collected user data
            model: Override the default model
        Returns:
            Dictionary with 'content' (response text) and 'usage' (token counts)
        """
        logger.info(
            "Generating OpenAI response",
            tenant_id=tenant_id,
            session_id=session_id,
            user_message_length=len(user_message),
            history_length=len(conversation_history),
            detected_language=detected_language
        )
        
        # Build the enhanced system prompt
        enhanced_system_prompt = self._build_system_prompt(
            base_prompt=system_prompt,
            detected_language=detected_language,
            slot_data=slot_data
        )
        
        # Build messages array for OpenAI
        messages = self._build_messages(
            system_prompt=enhanced_system_prompt,
            conversation_history=conversation_history,
            user_message=user_message
        )
        
        logger.debug(
            "Prepared messages for OpenAI",
            message_count=len(messages),
            system_prompt_length=len(enhanced_system_prompt)
        )
        
        try:
            response = self.client.chat.completions.create(
                model=model or self.default_model,
                messages=messages,
                temperature=OPENAI_CONFIG["chat_temperature"],
                max_tokens=OPENAI_CONFIG["chat_max_tokens"]
            )
            
            assistant_message = response.choices[0].message.content
            usage = {
                'prompt_tokens': response.usage.prompt_tokens,
                'completion_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens
            }
            
            logger.info(
                "OpenAI response generated successfully",
                tenant_id=tenant_id,
                session_id=session_id,
                response_length=len(assistant_message),
                tokens_used=usage['total_tokens']
            )
            
            logger.debug(
                "Token usage details",
                prompt_tokens=usage['prompt_tokens'],
                completion_tokens=usage['completion_tokens']
            )
            
            return {
                'content': assistant_message,
                'usage': usage
            }
            
        except Exception as e:
            logger.error(
                "OpenAI API call failed",
                tenant_id=tenant_id,
                session_id=session_id,
                error=str(e),
                exc_info=True
            )
            raise
    
    def _build_system_prompt(
        self,
        base_prompt: str,
        detected_language: Optional[str] = None,
        slot_data: Optional[dict] = None
    ) -> str:
        """
        Enhance the base system prompt with context.
        Args:
            base_prompt: The tenant's base system prompt
            detected_language: Detected user language
            slot_data: Currently collected slot data
        Returns:
            Enhanced system prompt
        """
        prompt_parts = [base_prompt]
        lang = detected_language or 'en'

        # Add language instruction
        if detected_language:
            language_name = 'Spanish' if detected_language == 'es' else 'English'
            prompt_parts.append(
                DATA_COLLECTION_MESSAGES["language_instruction"][lang].format(language=language_name)
            )

        # Add slot filling context
        prompt_parts.append(DATA_COLLECTION_MESSAGES["status_header"])

        if slot_data:
            collected = []
            missing = []

            for field in ['name', 'email', 'phone']:
                if slot_data.get(field):
                    collected.append(f"{field}: {slot_data[field]}")
                else:
                    missing.append(field)

            if collected:
                prompt_parts.append(
                    DATA_COLLECTION_MESSAGES["collected_info"][lang] +
                    "\n".join(f"- {c}" for c in collected)
                )

            if missing:
                prompt_parts.append(
                    DATA_COLLECTION_MESSAGES["still_needed"][lang].format(fields=', '.join(missing))
                )
            else:
                prompt_parts.append(DATA_COLLECTION_MESSAGES["all_collected"][lang])
        else:
            prompt_parts.append(DATA_COLLECTION_MESSAGES["none_collected"][lang])

        prompt_parts.append(DATA_COLLECTION_MESSAGES["status_footer"])

        return "".join(prompt_parts)
    
    def _build_messages(
        self,
        system_prompt: str,
        conversation_history: list,
        user_message: str
    ) -> list:
        """
        Build the messages array for OpenAI API.
        Args:
            system_prompt: The system prompt
            conversation_history: Previous conversation messages
            user_message: Current user message
        Returns:
            List of message dictionaries for OpenAI
        """
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add conversation history (skip system messages from our DB)
        for msg in conversation_history:
            if msg.get('role') in ['user', 'assistant']:
                messages.append({
                    "role": msg['role'],
                    "content": msg['content']
                })
        
        # Add current user message
        messages.append({"role": "user", "content": user_message})
        
        return messages


# Singleton instance for Lambda reuse
_openai_service = None


def get_openai_service() -> OpenAIService:
    """Get or create the OpenAI service singleton."""
    global _openai_service
    if _openai_service is None:
        logger.debug("Creating new OpenAI service instance")
        _openai_service = OpenAIService()
    return _openai_service