"""
Language Detector Utility
Detects whether user messages are in Spanish or English.
Uses a combination of keyword detection and character analysis for speed.
Falls back to OpenAI for ambiguous cases if needed.
"""

import re
from typing import Optional

from config.settings import LANGUAGE_INDICATORS
from src.utils.logger import get_logger

# Initialize logger
logger = get_logger(__name__)

# Load language indicators from config
SPANISH_INDICATORS = LANGUAGE_INDICATORS["spanish"]
ENGLISH_INDICATORS = LANGUAGE_INDICATORS["english"]
SPANISH_CHARS = LANGUAGE_INDICATORS["spanish_chars"]


class LanguageDetector:
    """Detects language from text input."""
    
    def __init__(self):
        """Initialize the language detector."""
        logger.info("Initializing language detector")
    
    def detect(self, text: str, session_id: Optional[str] = None) -> str:
        """
        Detect the language of the given text.
        Args:
            text: The text to analyze
            session_id: Optional session ID for logging context
        Returns:
            'es' for Spanish, 'en' for English
        """
        if not text or not text.strip():
            logger.warning(
                "Empty text provided for language detection",
                session_id=session_id
            )
            return 'en'  # Default to English
        
        # Normalize text for analysis
        normalized = text.lower().strip()
        words = set(re.findall(r'\b\w+\b', normalized))
        
        logger.debug(
            "Analyzing text for language detection",
            session_id=session_id,
            text_length=len(text),
            word_count=len(words)
        )
        
        # Check for Spanish-specific characters
        spanish_char_count = sum(1 for char in normalized if char in SPANISH_CHARS)
        
        # Count indicator matches
        spanish_matches = words.intersection(SPANISH_INDICATORS)
        english_matches = words.intersection(ENGLISH_INDICATORS)
        
        spanish_score = len(spanish_matches) + (spanish_char_count * 2)  # Weight special chars
        english_score = len(english_matches)
        
        logger.debug(
            "Language detection scores",
            session_id=session_id,
            spanish_score=spanish_score,
            english_score=english_score,
            spanish_matches=list(spanish_matches)[:5],  # Log first 5 matches
            english_matches=list(english_matches)[:5],
            spanish_chars_found=spanish_char_count
        )
        
        # Determine language
        if spanish_score > english_score:
            detected = 'es'
        elif english_score > spanish_score:
            detected = 'en'
        else:
            # Tie or no matches - check for Spanish characters as tiebreaker
            if spanish_char_count > 0:
                detected = 'es'
            else:
                detected = 'en'  # Default to English
        
        logger.info(
            "Language detected",
            session_id=session_id,
            detected_language=detected,
            language_name='Spanish' if detected == 'es' else 'English',
            confidence='high' if abs(spanish_score - english_score) > 2 else 'medium'
        )
        
        return detected
    
    def get_language_name(self, code: str) -> str:
        """
        Get the full language name from code.
        Args:
            code: Language code ('es' or 'en')
        Returns:
            Full language name
        """
        return 'Spanish' if code == 'es' else 'English'

# Singleton instance
_language_detector = None


def get_language_detector() -> LanguageDetector:
    """Get or create the language detector singleton."""
    global _language_detector
    if _language_detector is None:
        logger.debug("Creating new language detector instance")
        _language_detector = LanguageDetector()
    return _language_detector


def detect_language(text: str, session_id: Optional[str] = None) -> str:
    """
    Convenience function to detect language.
    Args:
        text: Text to analyze
        session_id: Optional session ID for logging
    Returns:
        'es' for Spanish, 'en' for English
    """
    detector = get_language_detector()
    return detector.detect(text, session_id)