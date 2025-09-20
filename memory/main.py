"""
Memory Service - Hybrid Memory System
Handles short-term and long-term memory for conversations
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
from pydantic import BaseModel
import uvicorn

from shared.src.infrastructure.redis_client import RedisClient
from shared.src.infrastructure.http_client import ServiceClient
from shared.src.utils.config import get_settings
from shared.src.utils.logging import setup_logging, get_logger
import openai
from openai import OpenAI
from typing import Dict, List, Any, Optional
import json
import asyncio
from datetime import datetime, timedelta
import hashlib
import numpy as np
from enum import Enum

# Configuration
settings = get_settings()
setup_logging(service_name=settings.service.name, log_level=settings.log_level)
logger = get_logger("memory")

# Initialize clients
redis_client = RedisClient(settings.redis)
database_client = ServiceClient("memory", settings.service.database_url)
openai_client = OpenAI(api_key=settings.ai.openai_api_key) if settings.ai.openai_api_key else None

# FastAPI app
app = FastAPI(
    title="FamaGPT Memory Service",
    description="Hybrid memory system for conversations",
    version="1.0.0"
)

# CORS middleware
origins_env = os.environ.get("ALLOWED_ORIGINS", "*")
allow_origins = ["*"] if origins_env.strip() == "*" else [o.strip() for o in origins_env.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class MemoryType(str, Enum):
    """Memory types"""
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    SEMANTIC = "semantic"
    EPISODIC = "episodic"

class MemoryRequest(BaseModel):
    """Memory request model"""
    user_id: str
    conversation_id: str
    content: str
    memory_type: MemoryType = MemoryType.SHORT_TERM
    metadata: Dict[str, Any] = {}

class ConversationMessage(BaseModel):
    """Conversation message model"""
    user_id: str
    conversation_id: str
    messages: List[Dict[str, Any]]
    summary: Optional[str] = None

class MemorySearchRequest(BaseModel):
    """Memory search request"""
    user_id: str
    query: str
    memory_types: List[MemoryType] = [MemoryType.SHORT_TERM, MemoryType.LONG_TERM]
    limit: int = 5
    similarity_threshold: float = 0.7


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    timestamp: str


# Hybrid Memory System Implementation
class HybridMemoryService:
    """Hybrid memory system with short-term, long-term and semantic memory"""
    
    def __init__(self):
        self.embedding_model = settings.ai.embedding_model
        self.short_term_ttl = settings.cache.ttl_short  # 5 minutes
        self.medium_term_ttl = settings.cache.ttl_medium  # 30 minutes
        self.conversation_summary_threshold = 10  # messages
        
    async def get_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for text"""
        if not openai_client:
            logger.warning("OpenAI client not available, using dummy embedding")
            # Return dummy embedding for development
            return [0.0] * 1536
        
        try:
            response = openai_client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            return None
    
    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between vectors"""
        try:
            v1 = np.array(vec1)
            v2 = np.array(vec2)
            return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
        except:
            return 0.0
    
    async def store_short_term_memory(self, user_id: str, conversation_id: str, content: str, metadata: Dict[str, Any] = None) -> None:
        """Store memory in short-term cache (Redis)"""
        try:
            memory_data = {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "content": content,
                "metadata": metadata or {},
                "memory_type": MemoryType.SHORT_TERM.value,
                "timestamp": datetime.utcnow().isoformat(),
                "ttl": self.short_term_ttl
            }
            
            # Store in Redis with TTL
            memory_key = f"memory:short:{user_id}:{conversation_id}:{int(datetime.utcnow().timestamp())}"
            await redis_client.set_json(memory_key, memory_data, ttl=self.short_term_ttl)
            
            # Also add to conversation timeline
            timeline_key = f"conversation_timeline:{user_id}:{conversation_id}"
            await redis_client.lpush(timeline_key, json.dumps(memory_data, default=str))
            await redis_client.expire(timeline_key, self.medium_term_ttl)
            
            logger.debug(f"Short-term memory stored for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error storing short-term memory: {str(e)}")
            raise
    
    async def store_long_term_memory(self, user_id: str, content: str, memory_type: MemoryType, metadata: Dict[str, Any] = None) -> str:
        """Store memory in long-term storage with embeddings"""
        try:
            # Generate embedding for semantic search
            embedding = await self.get_embedding(content)
            
            memory_id = hashlib.md5(f"{user_id}{content}{datetime.utcnow()}".encode()).hexdigest()
            importance_score = self.calculate_importance_score(content, metadata or {})
            
            memory_data = {
                "memory_id": memory_id,
                "user_id": user_id,
                "content": content,
                "embedding": embedding,
                "memory_type": memory_type.value,
                "metadata": metadata or {},
                "created_at": datetime.utcnow().isoformat(),
                "importance_score": importance_score,
                "access_count": 0,
                "last_accessed": datetime.utcnow().isoformat()
            }
            
            # Store in Redis for fast access (without TTL)
            memory_key = f"memory:long:{memory_id}"
            await redis_client.set_json(memory_key, memory_data)
            
            # Add to user's memory index
            user_index_key = f"user_memory_index:{user_id}"
            await redis_client.set_add(user_index_key, memory_id)
            
            # Persist to Database for long-term storage
            await self._persist_memory_to_database(memory_data, user_id, embedding)
            
            logger.debug(f"Long-term memory stored: {memory_id}")
            return memory_id
            
        except Exception as e:
            logger.error(f"Error storing long-term memory: {str(e)}")
            raise
    
    def calculate_importance_score(self, content: str, metadata: Dict[str, Any]) -> float:
        """Calculate importance score for memory prioritization"""
        score = 0.5  # Base score
        
        # Content-based scoring
        important_keywords = ['comprar', 'vender', 'financiamento', 'visita', 'proposta', 'contrato']
        keyword_count = sum(1 for keyword in important_keywords if keyword in content.lower())
        score += keyword_count * 0.1
        
        # Metadata-based scoring
        if metadata.get('is_decision_point'):
            score += 0.3
        if metadata.get('involves_money'):
            score += 0.2
        if metadata.get('user_expressed_interest'):
            score += 0.2
        
        return min(score, 1.0)
    
    async def search_memories(self, user_id: str, query: str, memory_types: List[MemoryType], limit: int = 5, similarity_threshold: float = 0.7) -> List[Dict[str, Any]]:
        """Search memories using semantic similarity"""
        try:
            # Generate query embedding
            query_embedding = await self.get_embedding(query)
            if not query_embedding:
                return []
            
            all_memories = []
            
            # Search short-term memories
            if MemoryType.SHORT_TERM in memory_types:
                short_term_memories = await self.get_short_term_memories(user_id)
                all_memories.extend(short_term_memories)
            
            # Search long-term memories
            if MemoryType.LONG_TERM in memory_types or MemoryType.SEMANTIC in memory_types:
                long_term_memories = await self.get_long_term_memories(user_id)
                all_memories.extend(long_term_memories)
            
            # Calculate similarities and score
            scored_memories = []
            for memory in all_memories:
                if memory.get('embedding'):
                    similarity = self.cosine_similarity(query_embedding, memory['embedding'])
                    if similarity >= similarity_threshold:
                        memory['similarity_score'] = similarity
                        # Combine similarity with importance
                        memory['relevance_score'] = similarity * 0.7 + memory.get('importance_score', 0.5) * 0.3
                        scored_memories.append(memory)
            
            # Sort by relevance and return top results
            scored_memories.sort(key=lambda x: x['relevance_score'], reverse=True)
            
            # Update access count for returned memories
            for memory in scored_memories[:limit]:
                await self.update_memory_access(memory.get('memory_id'))
            
            return scored_memories[:limit]
            
        except Exception as e:
            logger.error(f"Error searching memories: {str(e)}")
            return []
    
    async def get_short_term_memories(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all short-term memories for user"""
        try:
            pattern = f"memory:short:{user_id}:*"
            memory_keys = await redis_client.scan_keys(pattern)
            
            memories = []
            for key in memory_keys:
                memory_data = await redis_client.get_json(key)
                if memory_data:
                    # Add embedding for consistency
                    if 'embedding' not in memory_data:
                        memory_data['embedding'] = await self.get_embedding(memory_data['content'])
                    memories.append(memory_data)
            
            return memories
            
        except Exception as e:
            logger.error(f"Error getting short-term memories: {str(e)}")
            return []
    
    async def get_long_term_memories(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all long-term memories for user"""
        try:
            # Get user's memory index
            user_index_key = f"user_memory_index:{user_id}"
            memory_ids = await redis_client.set_members(user_index_key)
            
            memories = []
            for memory_id in memory_ids:
                memory_key = f"memory:long:{memory_id}"
                memory_data = await redis_client.get_json(memory_key)
                if memory_data:
                    memories.append(memory_data)
            
            return memories
            
        except Exception as e:
            logger.error(f"Error getting long-term memories: {str(e)}")
            return []
    
    async def update_memory_access(self, memory_id: str) -> None:
        """Update memory access statistics"""
        if not memory_id:
            return
            
        try:
            memory_key = f"memory:long:{memory_id}"
            memory_data = await redis_client.get_json(memory_key)
            
            if memory_data:
                memory_data['access_count'] = memory_data.get('access_count', 0) + 1
                memory_data['last_accessed'] = datetime.utcnow().isoformat()
                await redis_client.set_json(memory_key, memory_data)
                
        except Exception as e:
            logger.error(f"Error updating memory access: {str(e)}")
    
    async def summarize_conversation(self, messages: List[Dict[str, Any]]) -> str:
        """Generate conversation summary using LLM"""
        if not openai_client:
            # Fallback summary
            return f"Conversa com {len(messages)} mensagens sobre propriedades."
        
        try:
            # Combine messages into context
            conversation_text = "\n".join([
                f"{msg.get('sender', 'user')}: {msg.get('content', '')}" 
                for msg in messages[-10:]  # Last 10 messages
            ])
            
            prompt = f"""Resuma esta conversa sobre imóveis em até 2 frases, destacando:
1. O que o cliente está procurando
2. Principais preferências ou decisões

Conversa:
{conversation_text}

Resumo:"""
            
            response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Você é um assistente que resume conversas sobre imóveis."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=100,
                temperature=0.3
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            return f"Conversa com {len(messages)} mensagens sobre propriedades."
    
    async def consolidate_memories(self, user_id: str, conversation_id: str) -> None:
        """Consolidate short-term memories into long-term storage"""
        try:
            # Get conversation timeline
            timeline_key = f"conversation_timeline:{user_id}:{conversation_id}"
            messages = await redis_client.list_get_all(timeline_key)
            
            if len(messages) >= self.conversation_summary_threshold:
                # Generate summary
                summary = await self.summarize_conversation(messages)
                
                # Store as long-term semantic memory
                await self.store_long_term_memory(
                    user_id=user_id,
                    content=summary,
                    memory_type=MemoryType.SEMANTIC,
                    metadata={
                        "conversation_id": conversation_id,
                        "message_count": len(messages),
                        "is_summary": True,
                        "involves_property_search": True
                    }
                )
                
                # Extract important individual memories
                important_messages = [
                    msg for msg in messages[-5:] 
                    if self.calculate_importance_score(msg.get('content', ''), msg.get('metadata', {})) > 0.7
                ]
                
                for msg in important_messages:
                    await self.store_long_term_memory(
                        user_id=user_id,
                        content=msg.get('content', ''),
                        memory_type=MemoryType.EPISODIC,
                        metadata={
                            **msg.get('metadata', {}),
                            "conversation_id": conversation_id,
                            "is_important_moment": True
                        }
                    )
                
                logger.info(f"Consolidated memories for conversation {conversation_id}")
            
        except Exception as e:
            logger.error(f"Error consolidating memories: {str(e)}")
    
    async def _persist_memory_to_database(self, memory_data: Dict[str, Any], user_id: str, embedding: List[float]) -> None:
        """Persist memory entry to database via HTTP service"""
        try:
            await database_client.start()
            
            # Prepare data for database service
            memory_payload = {
                "user_id": user_id,
                "content": memory_data['content'],
                "memory_type": memory_data['memory_type'],
                "importance_score": memory_data['importance_score'],
                "access_count": memory_data['access_count'],
                "tags": memory_data.get('metadata', {}).get('tags', []),
                "metadata": memory_data['metadata']
            }
            
            response = await database_client.post("/memories", json_data=memory_payload)
            
            if response.get("status") == "success":
                logger.debug(f"Memory persisted to database: {memory_data['memory_id']}")
            else:
                logger.warning(f"Failed to persist memory to database: {response}")
            
        except Exception as e:
            logger.warning(f"Failed to persist memory to database: {str(e)}")
            # Continue without failing if database persistence fails
        finally:
            await database_client.close()
    
    async def load_memories_from_database(self, user_id: str) -> List[Dict[str, Any]]:
        """Load user memories from database via HTTP service"""
        try:
            await database_client.start()
            
            response = await database_client.get(f"/memories/user/{user_id}")
            
            if response.get("status") == "success":
                memories_data = response.get("memories", [])
                
                memories = []
                for mem in memories_data:
                    memory_data = {
                        "user_id": user_id,
                        "content": mem.get('content', ''),
                        "memory_type": mem.get('content_type', 'long_term'),
                        "importance_score": float(mem.get('importance_score', 0.0)),
                        "access_count": mem.get('access_count', 0),
                        "tags": mem.get('tags', []),
                        "metadata": mem.get('metadata', {}),
                        "created_at": mem.get('created_at', ''),
                        "last_accessed": mem.get('updated_at', ''),
                        "embedding": None  # Will be generated on demand
                    }
                    memories.append(memory_data)
                
                logger.info(f"Loaded {len(memories)} memories from database for user {user_id}")
                return memories
            else:
                logger.warning(f"Failed to load memories from database: {response}")
                return []
            
        except Exception as e:
            logger.error(f"Failed to load memories from database: {str(e)}")
            return []
        finally:
            await database_client.close()

# Initialize hybrid memory service
hybrid_memory = HybridMemoryService()

@app.on_event("startup")
async def startup_event():
    """Startup event handler"""
    logger.info("Starting Memory Service...")
    await redis_client.connect()
    logger.info("Memory Service started successfully")


@app.on_event("shutdown") 
async def shutdown_event():
    """Shutdown event handler"""
    logger.info("Shutting down Memory Service...")
    await redis_client.disconnect()
    await database_client.close()
    logger.info("Memory Service shutdown complete")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    import datetime
    return HealthResponse(
        status="healthy",
        service="memory",
        timestamp=datetime.datetime.utcnow().isoformat()
    )


@app.post("/store")
async def store_memory(request: MemoryRequest):
    """Store memory"""
    try:
        logger.info(f"Storing {request.memory_type.value} memory for user {request.user_id}")
        
        if request.memory_type == MemoryType.SHORT_TERM:
            await hybrid_memory.store_short_term_memory(
                request.user_id,
                request.conversation_id,
                request.content,
                request.metadata
            )
            
            return {
                "status": "stored",
                "memory_type": request.memory_type.value,
                "storage": "short_term"
            }
        
        else:
            memory_id = await hybrid_memory.store_long_term_memory(
                request.user_id,
                request.content,
                request.memory_type,
                request.metadata
            )
            
            return {
                "status": "stored",
                "memory_id": memory_id,
                "memory_type": request.memory_type.value,
                "storage": "long_term"
            }
        
    except Exception as e:
        logger.error(f"Error storing memory: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Memory storage failed: {str(e)}")

@app.post("/store_conversation")
async def store_conversation(request: ConversationMessage):
    """Store conversation messages"""
    try:
        logger.info(f"Storing conversation for user {request.user_id}")
        
        # Store each message in short-term memory
        for message in request.messages:
            await hybrid_memory.store_short_term_memory(
                request.user_id,
                request.conversation_id,
                message.get('content', ''),
                {
                    **message.get('metadata', {}),
                    'sender': message.get('sender'),
                    'message_type': message.get('message_type', 'text')
                }
            )
        
        # Trigger consolidation if needed
        await hybrid_memory.consolidate_memories(request.user_id, request.conversation_id)
        
        return {
            "status": "stored",
            "messages_count": len(request.messages),
            "consolidation_triggered": len(request.messages) >= hybrid_memory.conversation_summary_threshold
        }
        
    except Exception as e:
        logger.error(f"Error storing conversation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Conversation storage failed: {str(e)}")


@app.post("/retrieve")
async def retrieve_memory(request: dict):
    """Retrieve memories - simplified interface for testing compatibility"""
    try:
        user_id = request.get("user_id")
        query = request.get("query", "")
        limit = request.get("limit", 5)
        
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")
        
        logger.info(f"Retrieving memories for user {user_id}")
        
        # If query provided, use semantic search
        if query:
            memories = await hybrid_memory.search_memories(
                user_id=user_id,
                query=query,
                memory_types=[MemoryType.SHORT_TERM, MemoryType.LONG_TERM],
                limit=limit,
                similarity_threshold=0.5
            )
        else:
            # Return recent memories
            short_memories = await hybrid_memory.get_short_term_memories(user_id)
            long_memories = await hybrid_memory.get_long_term_memories(user_id)
            
            all_memories = short_memories + long_memories
            all_memories.sort(key=lambda x: x.get('timestamp', x.get('created_at', '')), reverse=True)
            memories = all_memories[:limit]
        
        # Format response for compatibility
        formatted_memories = []
        for mem in memories:
            formatted_memories.append({
                "content": mem.get("content", ""),
                "user_id": mem.get("user_id", user_id),
                "memory_type": mem.get("memory_type", "short_term"),
                "timestamp": mem.get("timestamp", mem.get("created_at", "")),
                "importance_score": mem.get("importance_score", 0.5),
                "metadata": mem.get("metadata", {})
            })
        
        return {
            "status": "success",
            "memories": formatted_memories,
            "total_count": len(formatted_memories),
            "user_id": user_id
        }
        
    except Exception as e:
        logger.error(f"Error retrieving memory: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Memory retrieval failed: {str(e)}")

@app.get("/recall/{user_id}/{conversation_id}")
async def recall_memory(user_id: str, conversation_id: str, memory_type: str = "both"):
    """Recall memory for specific conversation"""
    try:
        logger.info(f"Recalling memory for user {user_id}, conversation {conversation_id}")
        
        memories = []
        
        if memory_type in ["both", "short_term"]:
            short_term_memories = await hybrid_memory.get_short_term_memories(user_id)
            # Filter by conversation
            conversation_memories = [
                mem for mem in short_term_memories 
                if mem.get('conversation_id') == conversation_id
            ]
            memories.extend(conversation_memories)
        
        if memory_type in ["both", "long_term"]:
            long_term_memories = await hybrid_memory.get_long_term_memories(user_id)
            # Filter by conversation if metadata contains it
            conversation_memories = [
                mem for mem in long_term_memories 
                if mem.get('metadata', {}).get('conversation_id') == conversation_id
            ]
            memories.extend(conversation_memories)
        
        return {
            "memories": memories,
            "total_count": len(memories),
            "conversation_id": conversation_id
        }
        
    except Exception as e:
        logger.error(f"Error recalling memory: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Memory recall failed: {str(e)}")

@app.post("/search")
async def search_memories(request: MemorySearchRequest):
    """Search memories using semantic similarity"""
    try:
        logger.info(f"Searching memories for user {request.user_id}, query: {request.query[:50]}...")
        
        memories = await hybrid_memory.search_memories(
            request.user_id,
            request.query,
            request.memory_types,
            request.limit,
            request.similarity_threshold
        )
        
        return {
            "memories": memories,
            "total_found": len(memories),
            "query": request.query,
            "similarity_threshold": request.similarity_threshold
        }
        
    except Exception as e:
        logger.error(f"Error searching memories: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Memory search failed: {str(e)}")

@app.get("/user/{user_id}/context")
async def get_user_context(user_id: str, limit: int = 10):
    """Get user context from all memories"""
    try:
        logger.info(f"Getting context for user {user_id}")
        
        # Get recent short-term memories
        short_term_memories = await hybrid_memory.get_short_term_memories(user_id)
        short_term_memories.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        # Get important long-term memories
        long_term_memories = await hybrid_memory.get_long_term_memories(user_id)
        important_memories = [
            mem for mem in long_term_memories 
            if mem.get('importance_score', 0) > 0.7
        ]
        important_memories.sort(key=lambda x: x.get('importance_score', 0), reverse=True)
        
        return {
            "user_id": user_id,
            "recent_memories": short_term_memories[:limit//2],
            "important_memories": important_memories[:limit//2],
            "total_memories": len(short_term_memories) + len(long_term_memories)
        }
        
    except Exception as e:
        logger.error(f"Error getting user context: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Context retrieval failed: {str(e)}")

@app.post("/consolidate/{user_id}/{conversation_id}")
async def consolidate_conversation(user_id: str, conversation_id: str):
    """Manually trigger memory consolidation"""
    try:
        logger.info(f"Consolidating memories for conversation {conversation_id}")
        
        await hybrid_memory.consolidate_memories(user_id, conversation_id)
        
        return {
            "status": "consolidated",
            "user_id": user_id,
            "conversation_id": conversation_id
        }
        
    except Exception as e:
        logger.error(f"Error consolidating memories: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Memory consolidation failed: {str(e)}")

@app.get("/stats/{user_id}")
async def get_memory_stats(user_id: str):
    """Get memory statistics for user"""
    try:
        short_term_memories = await hybrid_memory.get_short_term_memories(user_id)
        long_term_memories = await hybrid_memory.get_long_term_memories(user_id)
        
        # Calculate statistics
        stats = {
            "user_id": user_id,
            "short_term_count": len(short_term_memories),
            "long_term_count": len(long_term_memories),
            "total_memories": len(short_term_memories) + len(long_term_memories),
            "avg_importance": 0.0,
            "memory_types": {},
            "recent_activity": datetime.utcnow().isoformat()
        }
        
        if long_term_memories:
            importance_scores = [mem.get('importance_score', 0) for mem in long_term_memories]
            stats["avg_importance"] = sum(importance_scores) / len(importance_scores)
            
            # Count by memory types
            for mem in long_term_memories:
                mem_type = mem.get('memory_type', 'unknown')
                stats["memory_types"][mem_type] = stats["memory_types"].get(mem_type, 0) + 1
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting memory stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Stats retrieval failed: {str(e)}")

@app.post("/load_from_database/{user_id}")
async def load_memories_from_database(user_id: str):
    """Load user memories from database (backup/recovery)"""
    try:
        logger.info(f"Loading memories from database for user {user_id}")
        
        memories = await hybrid_memory.load_memories_from_database(user_id)
        
        # Load into Redis for fast access
        loaded_count = 0
        for memory in memories:
            if memory.get('memory_type') in ['long_term', 'semantic', 'episodic']:
                # Generate new memory ID
                memory_id = hashlib.md5(f"{user_id}{memory['content']}{memory['created_at']}".encode()).hexdigest()
                memory['memory_id'] = memory_id
                
                # Store in Redis
                memory_key = f"memory:long:{memory_id}"
                await redis_client.set_json(memory_key, memory)
                
                # Add to user index
                user_index_key = f"user_memory_index:{user_id}"
                await redis_client.set_add(user_index_key, memory_id)
                
                loaded_count += 1
        
        return {
            "status": "loaded",
            "user_id": user_id,
            "total_from_database": len(memories),
            "loaded_to_cache": loaded_count
        }
        
    except Exception as e:
        logger.error(f"Error loading memories from database: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database load failed: {str(e)}")

@app.get("/health_extended")
async def health_check_extended():
    """Extended health check with dependencies"""
    try:
        # Check Redis
        redis_status = "healthy"
        try:
            await redis_client.client.ping()
        except Exception:
            redis_status = "unhealthy"
        
        # Check Database Service
        database_status = "healthy"
        try:
            await database_client.start()
            response = await database_client.get("/health")
            if not response or response.get("status") != "healthy":
                database_status = "unhealthy"
        except Exception:
            database_status = "unhealthy"
        finally:
            await database_client.close()
        
        # Check OpenAI
        openai_status = "configured" if openai_client else "not_configured"
        
        return {
            "status": "healthy",
            "service": "memory",
            "timestamp": datetime.utcnow().isoformat(),
            "dependencies": {
                "redis": redis_status,
                "database": database_status,
                "openai": openai_status
            }
        }
        
    except Exception as e:
        logger.error(f"Health check error: {str(e)}")
        raise HTTPException(status_code=500, detail="Health check failed")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0", 
        port=8004,
        reload=True
    )
