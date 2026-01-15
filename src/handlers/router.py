"""
Request Router
Routes incoming Lambda requests to the appropriate handler.
"""

from typing import Any

from src.utils.logger import get_logger

logger = get_logger(__name__)


def route_request(event: dict, context: Any) -> dict:
    """
    Main Lambda entry point that routes to appropriate handler.
    
    Args:
        event: API Gateway event
        context: Lambda context
    
    Returns:
        API Gateway response
    """
    # Get the request path
    path = event.get('rawPath', '') or event.get('path', '')
    
    logger.info("Routing request", path=path)
    
    # Route based on path
    if '/voice/get-slots' in path:
        from src.handlers.voice_handler import voice_get_slots_handler
        return voice_get_slots_handler(event, context)
    
    elif '/voice/book' in path:
        from src.handlers.voice_handler import voice_book_handler
        return voice_book_handler(event, context)
    
    elif '/chat/' in path:
        from src.handlers.chat_handler import lambda_handler
        return lambda_handler(event, context)
    
    else:
        # Default to chat handler for backwards compatibility
        from src.handlers.chat_handler import lambda_handler
        return lambda_handler(event, context)