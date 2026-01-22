"""
Logging Utility
Centralized logging configuration for the AI Receptionist Agent.
Outputs structured JSON logs for easy parsing in CloudWatch.
"""

import logging
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Optional

from config.settings import LOGGING_CONFIG


class JSONFormatter(logging.Formatter):
    """
    Custom formatter that outputs logs as JSON.
    This format is ideal for CloudWatch Logs Insights queries.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        # Add extra fields if present
        if hasattr(record, 'extra_data') and record.extra_data:
            log_entry['data'] = record.extra_data
        
        return json.dumps(log_entry)


class ContextLogger:
    """
    Logger wrapper that supports structured logging with context.
    Allows adding contextual data to log messages.
    """
    
    def __init__(self, name: str):
        """
        Initialize the logger.
        Args:
            name: Logger name (typically module name)
        """
        self.logger = logging.getLogger(name)
        self._setup_logger()
        self.context: dict = {}
    
    def _setup_logger(self) -> None:
        """Configure the logger with appropriate handlers."""
        # Avoid duplicate handlers
        if self.logger.handlers:
            return

        # Set log level from config
        log_level = LOGGING_CONFIG["default_level"]
        self.logger.setLevel(getattr(logging, log_level, logging.INFO))

        # Create handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(self.logger.level)

        # Use JSON formatter for production, simple format for local dev
        if os.getenv('AWS_LAMBDA_FUNCTION_NAME'):
            # Running in Lambda - use JSON format
            handler.setFormatter(JSONFormatter())
        else:
            # Local development - use readable format
            formatter = logging.Formatter(
                LOGGING_CONFIG["local_format"],
                datefmt=LOGGING_CONFIG["local_date_format"]
            )
            handler.setFormatter(formatter)

        self.logger.addHandler(handler)
    
    def set_context(self, **kwargs) -> 'ContextLogger':
        """
        Set persistent context that will be included in all subsequent logs.
        Args:
            **kwargs: Key-value pairs to add to context
        Returns:
            self for chaining
        """
        self.context.update(kwargs)
        return self
    
    def clear_context(self) -> None:
        """Clear all context data."""
        self.context = {}
    
    def _log(
        self,
        level: int,
        message: str,
        data: Optional[dict] = None,
        exc_info: bool = False
    ) -> None:
        """
        Internal logging method.
        
        Args:
            level: Logging level
            message: Log message
            data: Additional structured data
            exc_info: Whether to include exception info
        """
        extra_data = {**self.context}
        if data:
            extra_data.update(data)
        
        # Use standard logging with extra data attached
        extra = {'extra_data': extra_data} if extra_data else {}
        
        self.logger.log(
            level,
            message,
            exc_info=exc_info if exc_info else None,
            extra=extra
        )
    
    def debug(self, message: str, **data) -> None:
        """Log debug message."""
        self._log(logging.DEBUG, message, data if data else None)
    
    def info(self, message: str, **data) -> None:
        """Log info message."""
        self._log(logging.INFO, message, data if data else None)
    
    def warning(self, message: str, **data) -> None:
        """Log warning message."""
        self._log(logging.WARNING, message, data if data else None)
    
    def error(self, message: str, exc_info: bool = False, **data) -> None:
        """
        Log error message.
        Args:
            message: Error message
            exc_info: If True, include exception traceback
            **data: Additional structured data
        """
        self._log(logging.ERROR, message, data if data else None, exc_info=exc_info)
    
    def critical(self, message: str, exc_info: bool = False, **data) -> None:
        """Log critical message."""
        self._log(logging.CRITICAL, message, data if data else None, exc_info=exc_info)


def get_logger(name: str) -> ContextLogger:
    """
    Get a configured logger instance.
    Args:
        name: Logger name (use __name__ for module name)
    Returns:
        Configured ContextLogger instance
    Example:
        logger = get_logger(__name__)
        logger.set_context(tenant_id='consulate', session_id='abc123')
        logger.info("Processing message", user_message="Hello")
    """
    return ContextLogger(name)