"""
Agent service implementation for inter-service communication.
"""
from typing import Dict, Any
import asyncio

from shared.src.infrastructure.http_client import ServiceClient
from shared.src.infrastructure.redis_client import RedisClient, PubSubManager
from shared.src.utils.logging import get_logger
from shared.src.utils.config import ServiceSettings
from shared.src.utils.helpers import retry_async

from ..domain.interfaces import AgentService


logger = get_logger(__name__)


class HTTPAgentService(AgentService):
    """HTTP-based agent service implementation."""
    
    def __init__(
        self,
        service_settings: ServiceSettings,
        redis_client: RedisClient
    ):
        self.settings = service_settings
        self.redis = redis_client
        self.pubsub = PubSubManager(redis_client)
        
        # Initialize service clients
        self.clients = {
            "webhooks": ServiceClient(
                "webhooks",
                self.settings.webhooks_url,
                timeout=30
            ),
            "transcription": ServiceClient(
                "transcription", 
                self.settings.transcription_url,
                timeout=60
            ),
            "web_search": ServiceClient(
                "web_search",
                self.settings.web_search_url,
                timeout=45
            ),
            "memory": ServiceClient(
                "memory",
                self.settings.memory_url,
                timeout=30
            ),
            "rag": ServiceClient(
                "rag",
                self.settings.rag_url,
                timeout=30
            ),
            "database": ServiceClient(
                "database",
                self.settings.database_url,
                timeout=30
            ),
            "specialist": ServiceClient(
                "specialist",
                self.settings.specialist_url,
                timeout=45
            )
        }
    
    async def start(self):
        """Start all service clients."""
        for name, client in self.clients.items():
            try:
                await client.start()
                logger.info("Started service client", service=name, url=client.base_url)
            except Exception as e:
                logger.error("Failed to start service client", service=name, error=str(e))
    
    async def stop(self):
        """Stop all service clients."""
        for name, client in self.clients.items():
            try:
                await client.close()
                logger.info("Stopped service client", service=name)
            except Exception as e:
                logger.error("Failed to stop service client", service=name, error=str(e))
    
    async def execute_task(
        self,
        agent_type: str,
        task_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute task on specific agent."""
        
        if agent_type not in self.clients:
            raise ValueError(f"Unknown agent type: {agent_type}")
        
        client = self.clients[agent_type]
        
        logger.info(
            "Executing task on agent",
            agent_type=agent_type,
            task_type=task_data.get("task_type", "unknown")
        )
        
        try:
            # Build request per agent type
            async def make_request():
                # Transcription: prefer URL-based transcription to avoid multipart
                if agent_type == "transcription":
                    audio_url = task_data.get("audio_url") or task_data.get("file_url")
                    if not audio_url:
                        return {
                            "success": False,
                            "error": "Missing audio_url for transcription"
                        }
                    payload = {
                        "audio_url": audio_url,
                        "content_type": task_data.get("content_type"),
                        "language": task_data.get("language"),
                        "use_cache": task_data.get("use_cache", True),
                    }
                    return await client.post("/transcription/transcribe_url", json_data=payload)

                # RAG query
                if agent_type == "rag":
                    payload = {
                        "query": task_data.get("query", ""),
                        "top_k": task_data.get("top_k", 5),
                        "min_similarity": task_data.get("min_similarity", 0.5),
                        "filters": {},
                        "use_cache": task_data.get("use_cache", True),
                        "system_prompt": task_data.get("system_prompt"),
                        "temperature": task_data.get("temperature", 0.7),
                    }
                    if task_data.get("context_type"):
                        payload["filters"]["document_type"] = task_data["context_type"]
                    return await client.post("/api/v1/rag/query", json_data=payload)

                # Memory operations
                if agent_type == "memory":
                    action = task_data.get("action")
                    if action == "get_user_context":
                        user_id = task_data.get("user_id")
                        if not user_id:
                            return {"success": False, "error": "Missing user_id"}
                        return await client.get(f"/user/{user_id}/context")
                    if action == "store":
                        payload = {
                            "user_id": task_data.get("user_id"),
                            "conversation_id": task_data.get("conversation_id"),
                            "content": task_data.get("content", ""),
                            "memory_type": task_data.get("memory_type", "short_term"),
                            "metadata": task_data.get("metadata", {}),
                        }
                        return await client.post("/store", json_data=payload)
                    if action == "search":
                        payload = {
                            "user_id": task_data.get("user_id"),
                            "query": task_data.get("query", ""),
                            "memory_types": task_data.get("memory_types", ["short_term", "long_term"]),
                            "limit": task_data.get("limit", 5),
                            "similarity_threshold": task_data.get("similarity_threshold", 0.7),
                        }
                        return await client.post("/search", json_data=payload)
                    # Unknown memory action
                    return {"success": False, "error": "Unknown memory action"}

                # Web search
                if agent_type == "web_search":
                    criteria = task_data.get("criteria", {})
                    payload = {
                        "query": criteria.get("query") or task_data.get("query", ""),
                        "city": criteria.get("city") or task_data.get("city", "Uberlândia"),
                        "state": criteria.get("state") or task_data.get("state", "MG"),
                        "property_type": criteria.get("property_type") or task_data.get("property_type", "any"),
                        "max_price": criteria.get("price_max") or task_data.get("max_price"),
                        "min_price": criteria.get("price_min") or task_data.get("min_price"),
                    }
                    return await client.post("/search", json_data=payload)

                # Fallback: generic execute endpoint if supported by the service
                return await client.post("/execute", json_data={
                    "task_type": task_data.get("task_type", "default"),
                    "data": task_data
                })
            
            result = await retry_async(
                make_request,
                max_retries=3,
                delay=1.0,
                backoff_factor=2.0
            )
            
            logger.info(
                "Task executed successfully",
                agent_type=agent_type,
                task_type=task_data.get("task_type", "unknown")
            )
            
            return result
            
        except Exception as e:
            logger.error(
                "Task execution failed",
                agent_type=agent_type,
                task_type=task_data.get("task_type", "unknown"),
                error=str(e)
            )
            
            # Return error response
            return {
                "success": False,
                "error": str(e),
                "agent_type": agent_type
            }
    
    async def health_check(self, agent_type: str) -> bool:
        """Check agent health."""
        
        if agent_type not in self.clients:
            logger.warning("Unknown agent type for health check", agent_type=agent_type)
            return False
        
        client = self.clients[agent_type]
        
        try:
            return await client.health_check()
        except Exception as e:
            logger.error("Health check failed", agent_type=agent_type, error=str(e))
            return False
    
    async def health_check_all(self) -> Dict[str, bool]:
        """Check health of all agents."""
        
        results = {}
        
        # Run health checks in parallel
        tasks = [
            self.health_check(agent_type) 
            for agent_type in self.clients.keys()
        ]
        
        health_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for agent_type, result in zip(self.clients.keys(), health_results):
            if isinstance(result, Exception):
                results[agent_type] = False
                logger.error("Health check exception", agent_type=agent_type, error=str(result))
            else:
                results[agent_type] = result
        
        logger.info("Health check completed", results=results)
        return results
    
    async def broadcast_message(self, channel: str, message: Dict[str, Any]) -> int:
        """Broadcast message to all agents via Redis pub/sub."""
        
        try:
            return await self.pubsub.publish(channel, message)
        except Exception as e:
            logger.error("Failed to broadcast message", channel=channel, error=str(e))
            return 0
    
    async def send_to_agent(
        self,
        agent_type: str,
        message: Dict[str, Any],
        timeout: int = 30
    ) -> Dict[str, Any]:
        """Send direct message to specific agent."""
        
        # Use Redis queue for async messaging
        queue_key = f"agent_queue:{agent_type}"
        
        try:
            # Add to agent's queue
            await self.redis.lpush(queue_key, str(message))
            
            # Wait for response (with timeout)
            response_key = f"agent_response:{message.get('id', 'unknown')}"
            
            for _ in range(timeout):
                response = await self.redis.get(response_key)
                if response:
                    await self.redis.delete(response_key)
                    return {"success": True, "response": response}
                
                await asyncio.sleep(1)
            
            # Timeout
            return {"success": False, "error": "Timeout waiting for agent response"}
            
        except Exception as e:
            logger.error("Failed to send message to agent", agent_type=agent_type, error=str(e))
            return {"success": False, "error": str(e)}


class LocalAgentService(AgentService):
    """Local agent service for testing/development."""
    
    def __init__(self):
        self.agents = {}
    
    async def execute_task(
        self,
        agent_type: str,
        task_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute task locally (mock implementation)."""
        
        logger.info("Executing task locally", agent_type=agent_type)
        
        # Mock responses for testing
        mock_responses = {
            "transcription": {
                "text": "Olá, estou procurando uma casa de 3 quartos em Uberlândia",
                "confidence": 0.95,
                "language": "pt-BR"
            },
            "web_search": {
                "properties": [
                    {
                        "title": "Casa 3 quartos - Bairro Santa Mônica",
                        "price": "R$ 450.000",
                        "location": "Santa Mônica, Uberlândia/MG",
                        "bedrooms": 3,
                        "bathrooms": 2,
                        "url": "https://example.com/property/1"
                    }
                ]
            },
            "memory": {
                "user_context": {
                    "name": "João",
                    "preferences": {
                        "property_type": "casa",
                        "budget_max": 500000
                    }
                }
            },
            "rag": {
                "documents": [
                    {
                        "content": "Informações sobre documentação para compra de imóveis...",
                        "source": "guia_documentacao.pdf",
                        "relevance": 0.85
                    }
                ]
            }
        }
        
        return mock_responses.get(agent_type, {"success": True, "data": "mock_response"})
    
    async def health_check(self, agent_type: str) -> bool:
        """Always return healthy for local service."""
        return True
