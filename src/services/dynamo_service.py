"""
DynamoDB Service
Handles all database operations for tenants, conversations, and appointments.
"""

import boto3
from datetime import datetime, timezone
from typing import Optional
import uuid

from config.settings import AWS_CONFIG
from src.utils.logger import get_logger

# Initialize logger
logger = get_logger(__name__)


class DynamoService:
    """Service class for DynamoDB operations."""
    
    def __init__(self):
        """Initialize DynamoDB resource and tables."""
        logger.info("Initializing DynamoDB service")

        self.dynamodb = boto3.resource(
            'dynamodb',
            region_name=AWS_CONFIG["region"]
        )

        tables = AWS_CONFIG["dynamodb_tables"]
        self.tenants_table = self.dynamodb.Table(tables["tenants"])
        self.conversations_table = self.dynamodb.Table(tables["conversations"])
        self.appointments_table = self.dynamodb.Table(tables["appointments"])

        logger.info(
            "DynamoDB service initialized",
            tables={
                'tenants': self.tenants_table.table_name,
                'conversations': self.conversations_table.table_name,
                'appointments': self.appointments_table.table_name
            }
        )
    
    # ==================== TENANT OPERATIONS ====================
    
    def get_tenant(self, tenant_id: str) -> Optional[dict]:
        """
        Retrieve tenant configuration by ID.
        Args:
            tenant_id: The unique tenant identifier (e.g., 'consulate', 'realestate')
        Returns:
            Tenant configuration dict or None if not found
        """
        logger.debug("Fetching tenant configuration", tenant_id=tenant_id)
        
        try:
            response = self.tenants_table.get_item(Key={'tenant_id': tenant_id})
            tenant = response.get('Item')
            
            if tenant:
                logger.info(
                    "Tenant configuration loaded",
                    tenant_id=tenant_id,
                    tenant_name=tenant.get('name'),
                    active=tenant.get('active')
                )
            else:
                logger.warning("Tenant not found", tenant_id=tenant_id)
            
            return tenant
            
        except Exception as e:
            logger.error(
                "Failed to fetch tenant configuration",
                tenant_id=tenant_id,
                error=str(e),
                exc_info=True
            )
            return None
    
    # ==================== CONVERSATION OPERATIONS ====================
    
    def create_session(self, tenant_id: str) -> str:
        """
        Create a new conversation session.
        Args:
            tenant_id: The tenant this session belongs to
        Returns:
            The new session_id
        """
        session_id = f"{tenant_id}_{uuid.uuid4().hex[:12]}"
        timestamp = datetime.now(timezone.utc).isoformat()
        
        logger.info(
            "Creating new conversation session",
            tenant_id=tenant_id,
            session_id=session_id
        )
        
        try:
            # Store session initialization message
            self.conversations_table.put_item(Item={
                'session_id': session_id,
                'timestamp': timestamp,
                'tenant_id': tenant_id,
                'role': 'system',
                'content': 'Session started',
                'metadata': {
                    'created_at': timestamp,
                    'slot_data': {}  # Will store name, email, phone as collected
                }
            })
            
            logger.info(
                "Conversation session created successfully",
                session_id=session_id,
                tenant_id=tenant_id
            )
            
            return session_id
            
        except Exception as e:
            logger.error(
                "Failed to create conversation session",
                tenant_id=tenant_id,
                error=str(e),
                exc_info=True
            )
            raise
    
    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tenant_id: str,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Save a message to the conversation history.
        Args:
            session_id: The conversation session ID
            role: Message role ('user', 'assistant', 'system')
            content: The message content
            tenant_id: The tenant ID
            metadata: Optional additional data
        Returns:
            The saved message item
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        
        logger.debug(
            "Saving message to conversation",
            session_id=session_id,
            role=role,
            content_length=len(content),
            tenant_id=tenant_id
        )
        
        item = {
            'session_id': session_id,
            'timestamp': timestamp,
            'tenant_id': tenant_id,
            'role': role,
            'content': content
        }
        
        if metadata:
            item['metadata'] = metadata
        
        try:
            self.conversations_table.put_item(Item=item)
            
            logger.info(
                "Message saved successfully",
                session_id=session_id,
                role=role,
                timestamp=timestamp
            )
            
            return item
            
        except Exception as e:
            logger.error(
                "Failed to save message",
                session_id=session_id,
                role=role,
                error=str(e),
                exc_info=True
            )
            raise
    
    def get_conversation_history(self, session_id: str, limit: int = 20) -> list:
        """
        Retrieve conversation history for a session.
        Args:
            session_id: The conversation session ID
            limit: Maximum number of messages to retrieve
        Returns:
            List of messages ordered by timestamp
        """
        logger.debug(
            "Fetching conversation history",
            session_id=session_id,
            limit=limit
        )
        
        try:
            response = self.conversations_table.query(
                KeyConditionExpression='session_id = :sid',
                ExpressionAttributeValues={':sid': session_id},
                ScanIndexForward=True,  # Ascending order (oldest first)
                Limit=limit
            )
            
            messages = response.get('Items', [])
            logger.info(
                "Conversation history retrieved",
                session_id=session_id,
                message_count=len(messages)
            )
            
            return messages
            
        except Exception as e:
            logger.error(
                "Failed to fetch conversation history",
                session_id=session_id,
                error=str(e),
                exc_info=True
            )
            return []
    
    def get_session_metadata(self, session_id: str) -> dict:
        """
        Get the metadata (slot data) for a session.
        Args:
            session_id: The conversation session ID
        Returns:
            The session metadata including collected slot data
        """
        logger.debug("Fetching session metadata", session_id=session_id)
        
        history = self.get_conversation_history(session_id, limit=1)
        
        if history and 'metadata' in history[0]:
            metadata = history[0]['metadata']
            logger.debug(
                "Session metadata retrieved",
                session_id=session_id,
                slot_data_keys=list(metadata.get('slot_data', {}).keys())
            )
            return metadata
        
        logger.debug("No metadata found for session", session_id=session_id)
        return {'slot_data': {}}
    
    def update_slot_data(self, session_id: str, slot_data: dict) -> None:
        """
        Update the collected slot data (name, email, phone) for a session.
        Args:
            session_id: The conversation session ID
            slot_data: Dictionary with collected user information
        """
        logger.info(
            "Updating slot data",
            session_id=session_id,
            new_fields=list(slot_data.keys())
        )
        
        try:
            # Get the first message (session init) to update its metadata
            history = self.get_conversation_history(session_id, limit=1)
            
            if history:
                first_msg = history[0]
                metadata = first_msg.get('metadata', {})
                metadata['slot_data'] = {**metadata.get('slot_data', {}), **slot_data}
                
                self.conversations_table.update_item(
                    Key={
                        'session_id': session_id,
                        'timestamp': first_msg['timestamp']
                    },
                    UpdateExpression='SET metadata = :meta',
                    ExpressionAttributeValues={':meta': metadata}
                )
                
                logger.info(
                    "Slot data updated successfully",
                    session_id=session_id,
                    all_slot_fields=list(metadata['slot_data'].keys())
                )
            else:
                logger.warning(
                    "Cannot update slot data - no session found",
                    session_id=session_id
                )
                
        except Exception as e:
            logger.error(
                "Failed to update slot data",
                session_id=session_id,
                error=str(e),
                exc_info=True
            )
            raise
    
    # ==================== APPOINTMENT OPERATIONS ====================
    
    def create_appointment(
        self,
        tenant_id: str,
        session_id: str,
        user_data: dict,
        appointment_time: str
    ) -> dict:
        """
        Create a new appointment record.
        Args:
            tenant_id: The tenant ID
            session_id: The conversation session that created this appointment
            user_data: User information (name, email, phone)
            appointment_time: ISO format datetime string
        Returns:
            The created appointment record
        """
        appointment_id = f"apt_{uuid.uuid4().hex[:12]}"
        timestamp = datetime.now(timezone.utc).isoformat()
        
        logger.info(
            "Creating appointment",
            tenant_id=tenant_id,
            session_id=session_id,
            appointment_id=appointment_id,
            appointment_time=appointment_time,
            user_email=user_data.get('email', 'N/A')
        )
        
        item = {
            'tenant_id': tenant_id,
            'appointment_id': appointment_id,
            'session_id': session_id,
            'user_name': user_data.get('name', ''),
            'user_email': user_data.get('email', ''),
            'user_phone': user_data.get('phone', ''),
            'appointment_time': appointment_time,
            'status': 'confirmed',
            'created_at': timestamp
        }
        
        try:
            self.appointments_table.put_item(Item=item)
            
            logger.info(
                "Appointment created successfully",
                appointment_id=appointment_id,
                tenant_id=tenant_id,
                status='confirmed'
            )
            
            return item
            
        except Exception as e:
            logger.error(
                "Failed to create appointment",
                tenant_id=tenant_id,
                session_id=session_id,
                error=str(e),
                exc_info=True
            )
            raise

# ==================== TOKEN OPERATIONS ====================
       
    def save_oauth_token(self, tenant_id: str, provider: str, token_data: dict) -> None:
        """
        Save OAuth token for a tenant.
        Args:
            tenant_id: The tenant ID (use 'global' for shared tokens)
            provider: The OAuth provider ('outlook', 'google')
            token_data: Token dictionary containing access_token, refresh_token, etc.
        """
        logger.info(
            "Saving OAuth token",
            tenant_id=tenant_id,
            provider=provider
        )
        
        try:
            # Store token under a provider-specific key
            token_key = f"oauth_token_{provider}"
            
            self.tenants_table.update_item(
                Key={'tenant_id': tenant_id},
                UpdateExpression=f'SET {token_key} = :token, updated_at = :updated',
                ExpressionAttributeValues={
                    ':token': token_data,
                    ':updated': datetime.now(timezone.utc).isoformat()
                }
            )
            
            logger.info(
                "OAuth token saved successfully",
                tenant_id=tenant_id,
                provider=provider
            )
            
        except Exception as e:
            logger.error(
                "Failed to save OAuth token",
                tenant_id=tenant_id,
                provider=provider,
                error=str(e),
                exc_info=True
            )
            raise
       
    def get_oauth_token(self, tenant_id: str, provider: str) -> Optional[dict]:
        """
        Retrieve OAuth token for a tenant.
        Args:
            tenant_id: The tenant ID (use 'global' for shared tokens)
            provider: The OAuth provider ('outlook', 'google')
        Returns:
            Token dictionary or None if not found
        """
        logger.debug(
            "Fetching OAuth token",
            tenant_id=tenant_id,
            provider=provider
        )
        
        try:
            response = self.tenants_table.get_item(Key={'tenant_id': tenant_id})
            item = response.get('Item')
            
            if not item:
                logger.warning("Tenant not found for token retrieval", tenant_id=tenant_id)
                return None
            
            token_key = f"oauth_token_{provider}"
            token_data = item.get(token_key)
            
            if token_data:
                logger.debug(
                    "OAuth token retrieved",
                    tenant_id=tenant_id,
                    provider=provider,
                    has_refresh_token=bool(token_data.get('refresh_token'))
                )
            else:
                logger.warning(
                    "No OAuth token found for provider",
                    tenant_id=tenant_id,
                    provider=provider
                )
            
            return token_data
            
        except Exception as e:
            logger.error(
                "Failed to retrieve OAuth token",
                tenant_id=tenant_id,
                provider=provider,
                error=str(e),
                exc_info=True
            )
            return None

# Singleton instance for Lambda reuse
_dynamo_service = None


def get_dynamo_service() -> DynamoService:
    """Get or create the DynamoDB service singleton."""
    global _dynamo_service
    if _dynamo_service is None:
        logger.debug("Creating new DynamoDB service instance")
        _dynamo_service = DynamoService()
    return _dynamo_service