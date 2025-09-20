"""
Memory Service client for orchestrator.
"""
import aiohttp
import json
from typing import Dict, Any, List, Optional, Union
from uuid import UUID

from shared.src.utils.logging import get_logger
from shared.src.utils.config import get_settings

logger = get_logger(__name__)


class MemoryServiceClient:
    """Client for communication with Memory Service."""
    
    def __init__(self):
        # Use hardcoded port since it's defined in docker-compose
        self.base_url = "http://memory:8004"
        self.timeout = aiohttp.ClientTimeout(total=30)
    
    async def store_message(
        self, 
        user_id: str, 
        conversation_id: str, 
        content: str,
        sender: str = "user",
        message_type: str = "text",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Store a message in short-term memory."""
        try:
            payload = {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "content": content,
                "memory_type": "short_term",
                "metadata": {
                    "sender": sender,
                    "message_type": message_type,
                    **(metadata or {})
                }
            }
            
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(f"{self.base_url}/store", json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.debug("Message stored in memory", user_id=user_id[:8])
                        return result
                    else:
                        error_text = await response.text()
                        logger.error("Failed to store message", error=error_text)
                        return {"status": "error", "message": error_text}
        
        except Exception as e:
            logger.error("Memory service communication error", error=str(e))
            return {"status": "error", "message": str(e)}
    
    async def store_conversation(
        self,
        user_id: str,
        conversation_id: str,
        messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Store multiple conversation messages."""
        try:
            payload = {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "messages": messages
            }
            
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(f"{self.base_url}/store_conversation", json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.debug("Conversation stored in memory", user_id=user_id[:8])
                        return result
                    else:
                        error_text = await response.text()
                        logger.error("Failed to store conversation", error=error_text)
                        return {"status": "error", "message": error_text}
        
        except Exception as e:
            logger.error("Memory service communication error", error=str(e))
            return {"status": "error", "message": str(e)}
    
    async def get_user_context(self, user_id: str, limit: int = 10) -> Dict[str, Any]:
        """Get user context from memory."""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(f"{self.base_url}/user/{user_id}/context?limit={limit}") as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.debug("Retrieved user context", user_id=user_id[:8])
                        return result
                    else:
                        error_text = await response.text()
                        logger.warning("Failed to get user context", error=error_text)
                        return {"user_id": user_id, "recent_memories": [], "important_memories": []}
        
        except Exception as e:
            logger.warning("Memory service unavailable for context", error=str(e))
            return {"user_id": user_id, "recent_memories": [], "important_memories": []}
    
    async def search_memories(
        self,
        user_id: str,
        query: str,
        memory_types: List[str] = None,
        limit: int = 5,
        similarity_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Search memories using semantic similarity."""
        try:
            payload = {
                "user_id": user_id,
                "query": query,
                "memory_types": memory_types or ["short_term", "long_term"],
                "limit": limit,
                "similarity_threshold": similarity_threshold
            }
            
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(f"{self.base_url}/search", json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        memories = result.get("memories", [])
                        logger.debug("Found memories", count=len(memories), user_id=user_id[:8])
                        return memories
                    else:
                        error_text = await response.text()
                        logger.warning("Failed to search memories", error=error_text)
                        return []
        
        except Exception as e:
            logger.warning("Memory service unavailable for search", error=str(e))
            return []
    
    async def recall_conversation(
        self,
        user_id: str,
        conversation_id: str,
        memory_type: str = "both"
    ) -> List[Dict[str, Any]]:
        """Recall specific conversation memories."""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(
                    f"{self.base_url}/recall/{user_id}/{conversation_id}?memory_type={memory_type}"
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        memories = result.get("memories", [])
                        logger.debug("Recalled conversation", count=len(memories), conversation_id=conversation_id[:8])
                        return memories
                    else:
                        error_text = await response.text()
                        logger.warning("Failed to recall conversation", error=error_text)
                        return []
        
        except Exception as e:
            logger.warning("Memory service unavailable for recall", error=str(e))
            return []
    
    async def consolidate_memories(self, user_id: str, conversation_id: str) -> Dict[str, Any]:
        """Trigger memory consolidation."""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(f"{self.base_url}/consolidate/{user_id}/{conversation_id}") as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.debug("Memory consolidation triggered", conversation_id=conversation_id[:8])
                        return result
                    else:
                        error_text = await response.text()
                        logger.warning("Failed to consolidate memories", error=error_text)
                        return {"status": "error", "message": error_text}
        
        except Exception as e:
            logger.warning("Memory service unavailable for consolidation", error=str(e))
            return {"status": "error", "message": str(e)}
    
    async def get_memory_stats(self, user_id: str) -> Dict[str, Any]:
        """Get user memory statistics."""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(f"{self.base_url}/stats/{user_id}") as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.debug("Retrieved memory stats", user_id=user_id[:8])
                        return result
                    else:
                        error_text = await response.text()
                        logger.warning("Failed to get memory stats", error=error_text)
                        return {"user_id": user_id, "total_memories": 0}
        
        except Exception as e:
            logger.warning("Memory service unavailable for stats", error=str(e))
            return {"user_id": user_id, "total_memories": 0}