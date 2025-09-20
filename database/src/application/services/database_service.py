"""
Application service for database operations (minimal pool-based impl)
"""

from typing import Dict, Any, List, Optional
from uuid import UUID
import asyncpg
import json

from shared.src.utils.logging import get_logger


class DatabaseService:
    """Service for database operations using asyncpg pool directly."""

    def __init__(
        self,
        user_repo=None,
        conversation_repo=None,
        message_repo=None,
        property_repo=None,
        memory_repo=None,
        document_repo=None,
        db_pool: Optional[asyncpg.Pool] = None,
    ):
        self.pool = db_pool
        self.logger = get_logger("database_service")

    async def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new user (minimal)."""
        phone = user_data.get("phone") or user_data.get("phone_number")
        name = user_data.get("name")
        email = user_data.get("email")
        metadata = {}
        for k in ("push_name", "profile_pic_url"):
            if user_data.get(k) is not None:
                metadata[k] = user_data[k]
        async with self.pool.acquire() as conn:
            created = await conn.fetchrow(
                """
                INSERT INTO users (phone, name, email, metadata)
                VALUES ($1, $2, $3, $4)
                RETURNING *
                """,
                phone,
                name,
                email,
                json.dumps(metadata),
            )
            return dict(created)

    # User operations (minimal)
    async def get_or_create_user_by_phone(self, phone: str, **kwargs) -> Dict[str, Any]:
        """Get existing user by phone or create new one using shared schema."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE phone = $1 AND is_active = true",
                phone,
            )
            if row:
                return dict(row)

            metadata = {k: v for k, v in {
                "push_name": kwargs.get("push_name"),
                "profile_pic_url": kwargs.get("profile_pic_url"),
            }.items() if v is not None}

            created = await conn.fetchrow(
                """
                INSERT INTO users (phone, name, metadata)
                VALUES ($1, $2, $3)
                RETURNING *
                """,
                phone,
                kwargs.get("name"),
                json.dumps(metadata) if metadata else json.dumps({}),
            )
            return dict(created)

    # Conversation operations (minimal)
    async def get_or_create_conversation(
        self,
        user_id: UUID,
        instance_id: str,
        phone: str = None,
    ) -> Dict[str, Any]:
        """Get active conversation for user or create a new one.
        instance_id is stored in metadata for traceability.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM conversations WHERE user_id = $1 AND status = 'active' ORDER BY created_at DESC LIMIT 1",
                user_id,
            )
            if row:
                return dict(row)

            metadata = {"instance_id": instance_id}
            created = await conn.fetchrow(
                """
                INSERT INTO conversations (user_id, status, context, agent_assignments, metadata)
                VALUES ($1, 'active', '{}', '{}', $2)
                RETURNING *
                """,
                user_id,
                json.dumps(metadata),
            )
            return dict(created)

    # Message operations (minimal)
    async def save_message(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """Persist a message into messages table."""
        conversation_id: UUID = message_data["conversation_id"]
        async with self.pool.acquire() as conn:
            # Get user_id from conversation
            conv = await conn.fetchrow("SELECT user_id FROM conversations WHERE id = $1", conversation_id)
            user_id = conv["user_id"] if conv else None

            metadata = {k: v for k, v in {
                "sender_type": message_data.get("sender_type"),
            }.items() if v is not None}

            created = await conn.fetchrow(
                """
                INSERT INTO messages (
                    conversation_id, user_id, content, message_type,
                    status, metadata, source_message_id
                ) VALUES ($1, $2, $3, $4, 'received', $5, $6)
                RETURNING *
                """,
                conversation_id,
                user_id,
                message_data.get("content"),
                message_data.get("message_type", "text"),
                json.dumps(metadata) if metadata else json.dumps({}),
                message_data.get("whatsapp_message_id"),
            )
            return dict(created)

    # Fetch history (minimal)
    async def get_conversation_history(self, conversation_id: UUID, limit: int = 50) -> List[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM messages WHERE conversation_id = $1 ORDER BY created_at DESC LIMIT $2",
                conversation_id,
                limit,
            )
            return [dict(r) for r in rows]
