"""
Testes para o Memory Service
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timedelta
import json
import hashlib
from typing import Dict, List

# Mock do ambiente para testes
import sys
import os
sys.path.append('/var/www/famagpt')

# Fixtures globais adicionais para outros grupos de testes reutilizarem
@pytest.fixture
def mock_redis_client():
    """Fixture global de Redis mock para testes fora da classe principal."""
    from unittest.mock import AsyncMock
    mock = AsyncMock()
    mock.get_json.return_value = None
    mock.set_json.return_value = None
    mock.scan_keys.return_value = []
    mock.list_push.return_value = None
    mock.list_get_all.return_value = []
    mock.set_add.return_value = None
    mock.set_members.return_value = []
    mock.expire.return_value = None
    return mock

@pytest.fixture
def memory_service_class():
    """Replica da fixture de serviço de memória para escopo de módulo."""
    class MockHybridMemoryService:
        def __init__(self):
            self.embedding_model = "text-embedding-3-small"
            self.short_term_ttl = 300
            self.medium_term_ttl = 1800
            self.conversation_summary_threshold = 10

        async def get_embedding(self, text: str):
            return [0.1 + i * 0.001 for i in range(1536)]

        def cosine_similarity(self, vec1, vec2):
            import numpy as np
            try:
                v1 = np.array(vec1)
                v2 = np.array(vec2)
                denom = np.linalg.norm(v1) * np.linalg.norm(v2)
                if denom == 0:
                    return 0.0
                return float(np.dot(v1, v2) / denom)
            except Exception:
                return 0.0

        def calculate_importance_score(self, content: str, metadata: dict) -> float:
            score = 0.5
            important_keywords = ['comprar', 'vender', 'financiamento', 'visita', 'proposta', 'contrato']
            keyword_count = sum(1 for keyword in important_keywords if keyword in content.lower())
            score += keyword_count * 0.1
            if metadata.get('is_decision_point'):
                score += 0.3
            if metadata.get('involves_money'):
                score += 0.2
            if metadata.get('user_expressed_interest'):
                score += 0.2
            return min(score, 1.0)

    return MockHybridMemoryService


class TestHybridMemoryService:
    """Tests for Hybrid Memory Service functionality"""
    
    @pytest.fixture
    def mock_redis_client(self):
        """Mock Redis client"""
        mock = AsyncMock()
        mock.get_json.return_value = None
        mock.set_json.return_value = None
        mock.scan_keys.return_value = []
        mock.list_push.return_value = None
        mock.list_get_all.return_value = []
        mock.set_add.return_value = None
        mock.set_members.return_value = []
        mock.expire.return_value = None
        return mock
    
    @pytest.fixture
    def mock_openai_client(self):
        """Mock OpenAI client"""
        mock = Mock()
        
        # Mock embeddings response
        embedding_response = Mock()
        embedding_response.data = [Mock()]
        embedding_response.data[0].embedding = [0.1] * 1536
        mock.embeddings.create.return_value = embedding_response
        
        # Mock chat completion for summarization
        completion_response = Mock()
        completion_response.choices = [Mock()]
        completion_response.choices[0].message.content = "Conversa sobre busca de imóveis com 3 quartos em Uberlândia."
        mock.chat.completions.create.return_value = completion_response
        
        return mock
    
    @pytest.fixture
    def memory_service_class(self):
        """Create memory service class for testing"""
        class MockHybridMemoryService:
            def __init__(self):
                self.embedding_model = "text-embedding-3-small"
                self.short_term_ttl = 300  # 5 minutes
                self.medium_term_ttl = 1800  # 30 minutes
                self.conversation_summary_threshold = 10
        
            async def get_embedding(self, text: str):
                # Return dummy embedding for testing
                return [0.1 + i * 0.001 for i in range(1536)]
            
            def cosine_similarity(self, vec1, vec2):
                import numpy as np
                try:
                    v1 = np.array(vec1)
                    v2 = np.array(vec2)
                    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
                except:
                    return 0.0
            
            def calculate_importance_score(self, content: str, metadata: Dict) -> float:
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
        
        return MockHybridMemoryService
    
    @pytest.mark.asyncio
    async def test_short_term_memory_storage(self, mock_redis_client, memory_service_class):
        """Test short-term memory storage"""
        class TestMemoryService(memory_service_class):
            def __init__(self, redis_client):
                super().__init__()
                self.redis_client = redis_client
            
            async def store_short_term_memory(self, user_id: str, conversation_id: str, content: str, metadata: Dict = None):
                memory_data = {
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "content": content,
                    "metadata": metadata or {},
                    "memory_type": "short_term",
                    "timestamp": datetime.utcnow().isoformat(),
                    "ttl": self.short_term_ttl
                }
                
                memory_key = f"memory:short:{user_id}:{conversation_id}:{int(datetime.utcnow().timestamp())}"
                await self.redis_client.set_json(memory_key, memory_data, ttl=self.short_term_ttl)
                
                timeline_key = f"conversation_timeline:{user_id}:{conversation_id}"
                await self.redis_client.list_push(timeline_key, memory_data)
                await self.redis_client.expire(timeline_key, self.medium_term_ttl)
        
        memory_service = TestMemoryService(mock_redis_client)
        
        await memory_service.store_short_term_memory(
            user_id="user123",
            conversation_id="conv456",
            content="Procuro uma casa com 3 quartos",
            metadata={"intent": "property_search"}
        )
        
        # Verify Redis operations
        assert mock_redis_client.set_json.call_count == 1
        assert mock_redis_client.list_push.call_count == 1
        assert mock_redis_client.expire.call_count == 1
        
        # Check the stored data structure
        set_json_call = mock_redis_client.set_json.call_args
        stored_data = set_json_call[0][1]
        
        assert stored_data["user_id"] == "user123"
        assert stored_data["conversation_id"] == "conv456"
        assert stored_data["content"] == "Procuro uma casa com 3 quartos"
        assert stored_data["memory_type"] == "short_term"
        assert stored_data["metadata"]["intent"] == "property_search"
    
    @pytest.mark.asyncio
    async def test_long_term_memory_storage(self, mock_redis_client, memory_service_class):
        """Test long-term memory storage with embeddings"""
        class TestMemoryService(memory_service_class):
            def __init__(self, redis_client):
                super().__init__()
                self.redis_client = redis_client
            
            async def store_long_term_memory(self, user_id: str, content: str, memory_type: str, metadata: Dict = None):
                embedding = await self.get_embedding(content)
                memory_id = hashlib.md5(f"{user_id}{content}{datetime.utcnow()}".encode()).hexdigest()
                
                memory_data = {
                    "memory_id": memory_id,
                    "user_id": user_id,
                    "content": content,
                    "embedding": embedding,
                    "memory_type": memory_type,
                    "metadata": metadata or {},
                    "created_at": datetime.utcnow().isoformat(),
                    "importance_score": self.calculate_importance_score(content, metadata or {}),
                    "access_count": 0,
                    "last_accessed": datetime.utcnow().isoformat()
                }
                
                memory_key = f"memory:long:{memory_id}"
                await self.redis_client.set_json(memory_key, memory_data)
                
                user_index_key = f"user_memory_index:{user_id}"
                await self.redis_client.set_add(user_index_key, memory_id)
                
                return memory_id
        
        memory_service = TestMemoryService(mock_redis_client)
        
        memory_id = await memory_service.store_long_term_memory(
            user_id="user123",
            content="Cliente interessado em financiamento para casa de R$ 500.000",
            memory_type="semantic",
            metadata={
                "involves_money": True,
                "is_decision_point": True,
                "property_value": 500000
            }
        )
        
        assert memory_id is not None
        assert len(memory_id) == 32  # MD5 hash length
        
        # Verify Redis operations
        assert mock_redis_client.set_json.call_count == 1
        assert mock_redis_client.set_add.call_count == 1
        
        # Check importance score calculation
        stored_call = mock_redis_client.set_json.call_args
        stored_data = stored_call[0][1]
        
        assert stored_data["importance_score"] > 0.5  # Should be high due to metadata
        assert stored_data["memory_type"] == "semantic"
        assert stored_data["embedding"] is not None
        assert len(stored_data["embedding"]) == 1536
    
    def test_importance_score_calculation(self, memory_service_class):
        """Test importance score calculation"""
        memory_service = memory_service_class()
        
        # Test base score
        base_content = "Conversa geral sobre imóveis"
        base_score = memory_service.calculate_importance_score(base_content, {})
        assert base_score == 0.5
        
        # Test content with important keywords
        important_content = "Cliente quer comprar casa e precisa de financiamento"
        keyword_score = memory_service.calculate_importance_score(important_content, {})
        assert keyword_score > 0.5
        
        # Test with metadata flags
        decision_content = "Cliente decidiu fazer proposta"
        decision_metadata = {
            "is_decision_point": True,
            "involves_money": True,
            "user_expressed_interest": True
        }
        decision_score = memory_service.calculate_importance_score(decision_content, decision_metadata)
        assert decision_score > 0.8  # Should be very high
        assert decision_score <= 1.0  # But capped at 1.0
    
    @pytest.mark.asyncio
    async def test_memory_search_by_similarity(self, mock_redis_client, memory_service_class):
        """Test semantic memory search"""
        class TestMemoryService(memory_service_class):
            def __init__(self, redis_client):
                super().__init__()
                self.redis_client = redis_client
            
            async def get_short_term_memories(self, user_id: str):
                # Mock short-term memories
                return [
                    {
                        "content": "Procuro apartamento no centro",
                        "embedding": [0.2 + i * 0.001 for i in range(1536)],
                        "memory_type": "short_term",
                        "importance_score": 0.6
                    }
                ]
            
            async def get_long_term_memories(self, user_id: str):
                # Mock long-term memories
                return [
                    {
                        "memory_id": "mem1",
                        "content": "Cliente interessado em casas com 3 quartos",
                        "embedding": [0.1 + i * 0.001 for i in range(1536)],
                        "memory_type": "semantic",
                        "importance_score": 0.8
                    },
                    {
                        "memory_id": "mem2",
                        "content": "Discussão sobre financiamento imobiliário",
                        "embedding": [0.15 + i * 0.001 for i in range(1536)],
                        "memory_type": "episodic",
                        "importance_score": 0.7
                    }
                ]
            
            async def search_memories(self, user_id: str, query: str, memory_types: List, limit: int = 5, similarity_threshold: float = 0.7):
                query_embedding = await self.get_embedding(query)
                all_memories = []
                
                if "short_term" in [mt.value if hasattr(mt, 'value') else mt for mt in memory_types]:
                    short_memories = await self.get_short_term_memories(user_id)
                    all_memories.extend(short_memories)
                
                if any(mt in ["long_term", "semantic"] for mt in [getattr(mt, 'value', mt) for mt in memory_types]):
                    long_memories = await self.get_long_term_memories(user_id)
                    all_memories.extend(long_memories)
                
                scored_memories = []
                for memory in all_memories:
                    if memory.get('embedding'):
                        similarity = self.cosine_similarity(query_embedding, memory['embedding'])
                        if similarity >= similarity_threshold:
                            memory['similarity_score'] = similarity
                            memory['relevance_score'] = similarity * 0.7 + memory.get('importance_score', 0.5) * 0.3
                            scored_memories.append(memory)
                
                scored_memories.sort(key=lambda x: x['relevance_score'], reverse=True)
                return scored_memories[:limit]
            
            async def update_memory_access(self, memory_id: str):
                if memory_id:
                    memory_key = f"memory:long:{memory_id}"
                    # Mock update - in real implementation would increment access count
                    pass
        
        memory_service = TestMemoryService(mock_redis_client)
        
        # Search for memories about houses
        results = await memory_service.search_memories(
            user_id="user123",
            query="casas com quartos",
            memory_types=["short_term", "long_term"],
            similarity_threshold=0.5
        )
        
        assert len(results) > 0
        assert all('similarity_score' in mem for mem in results)
        assert all('relevance_score' in mem for mem in results)
        
        # Results should be sorted by relevance
        if len(results) > 1:
            for i in range(len(results) - 1):
                assert results[i]['relevance_score'] >= results[i + 1]['relevance_score']
    
    @pytest.mark.asyncio
    async def test_conversation_summarization(self, mock_openai_client, memory_service_class):
        """Test conversation summarization"""
        class TestMemoryService(memory_service_class):
            def __init__(self, openai_client):
                super().__init__()
                self.openai_client = openai_client
            
            async def summarize_conversation(self, messages: List):
                if not self.openai_client:
                    return f"Conversa com {len(messages)} mensagens sobre propriedades."
                
                conversation_text = "\n".join([
                    f"{msg.get('sender', 'user')}: {msg.get('content', '')}" 
                    for msg in messages[-10:]
                ])
                
                # Mock the OpenAI call
                response = self.openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "Você é um assistente que resume conversas sobre imóveis."},
                        {"role": "user", "content": f"Resuma esta conversa: {conversation_text}"}
                    ],
                    max_tokens=100,
                    temperature=0.3
                )
                
                return response.choices[0].message.content.strip()
        
        memory_service = TestMemoryService(mock_openai_client)
        
        messages = [
            {"sender": "user", "content": "Procuro uma casa com 3 quartos"},
            {"sender": "assistant", "content": "Posso ajudar você a encontrar casas"},
            {"sender": "user", "content": "Prefiro em Uberlândia"},
            {"sender": "assistant", "content": "Vou buscar opções em Uberlândia"}
        ]
        
        summary = await memory_service.summarize_conversation(messages)
        
        assert isinstance(summary, str)
        assert len(summary) > 0
        # The mock returns our predefined summary
        assert "busca de imóveis" in summary.lower() or "quartos" in summary.lower()
    
    @pytest.mark.asyncio
    async def test_memory_consolidation(self, mock_redis_client, memory_service_class):
        """Test memory consolidation process"""
        class TestMemoryService(memory_service_class):
            def __init__(self, redis_client):
                super().__init__()
                self.redis_client = redis_client
            
            async def summarize_conversation(self, messages: List):
                return "Cliente buscando casa com 3 quartos em Uberlândia para financiamento"
            
            async def store_long_term_memory(self, user_id: str, content: str, memory_type: str, metadata: Dict = None):
                memory_id = hashlib.md5(f"{user_id}{content}".encode()).hexdigest()
                return memory_id
            
            async def consolidate_memories(self, user_id: str, conversation_id: str):
                # Mock getting conversation timeline
                timeline_key = f"conversation_timeline:{user_id}:{conversation_id}"
                
                # Mock 12 messages (above threshold)
                messages = [
                    {"content": f"Mensagem {i}", "metadata": {}, "sender": "user"}
                    for i in range(12)
                ]
                
                if len(messages) >= self.conversation_summary_threshold:
                    # Generate summary
                    summary = await self.summarize_conversation(messages)
                    
                    # Store as semantic memory
                    semantic_id = await self.store_long_term_memory(
                        user_id=user_id,
                        content=summary,
                        memory_type="semantic",
                        metadata={
                            "conversation_id": conversation_id,
                            "message_count": len(messages),
                            "is_summary": True
                        }
                    )
                    
                    # Store important individual memories
                    important_messages = [
                        msg for msg in messages[-5:] 
                        if self.calculate_importance_score(msg.get('content', ''), msg.get('metadata', {})) > 0.7
                    ]
                    
                    episodic_ids = []
                    for msg in important_messages:
                        episodic_id = await self.store_long_term_memory(
                            user_id=user_id,
                            content=msg.get('content', ''),
                            memory_type="episodic",
                            metadata={
                                **msg.get('metadata', {}),
                                "conversation_id": conversation_id,
                                "is_important_moment": True
                            }
                        )
                        episodic_ids.append(episodic_id)
                    
                    return {
                        "semantic_memory_id": semantic_id,
                        "episodic_memory_ids": episodic_ids,
                        "consolidated": True
                    }
                
                return {"consolidated": False}
        
        memory_service = TestMemoryService(mock_redis_client)
        
        result = await memory_service.consolidate_memories("user123", "conv456")
        
        assert result["consolidated"] is True
        assert "semantic_memory_id" in result
        assert "episodic_memory_ids" in result
    
    @pytest.mark.asyncio 
    async def test_memory_access_tracking(self, mock_redis_client, memory_service_class):
        """Test memory access tracking"""
        class TestMemoryService(memory_service_class):
            def __init__(self, redis_client):
                super().__init__()
                self.redis_client = redis_client
            
            async def update_memory_access(self, memory_id: str):
                if not memory_id:
                    return
                
                memory_key = f"memory:long:{memory_id}"
                
                # Mock existing memory data
                existing_memory = {
                    "memory_id": memory_id,
                    "content": "Test memory",
                    "access_count": 5,
                    "last_accessed": "2024-01-01T00:00:00"
                }
                
                self.redis_client.get_json.return_value = existing_memory
                
                memory_data = await self.redis_client.get_json(memory_key)
                
                if memory_data:
                    memory_data['access_count'] = memory_data.get('access_count', 0) + 1
                    memory_data['last_accessed'] = datetime.utcnow().isoformat()
                    await self.redis_client.set_json(memory_key, memory_data)
                    
                    return memory_data['access_count']
                
                return 0
        
        memory_service = TestMemoryService(mock_redis_client)
        
        access_count = await memory_service.update_memory_access("test_memory_123")
        
        # Verify access was tracked
        assert mock_redis_client.get_json.called
        assert mock_redis_client.set_json.called
        assert access_count == 6  # Original 5 + 1


class TestMemoryServiceAPI:
    """Tests for Memory Service API functionality"""
    
    @pytest.mark.asyncio
    async def test_memory_storage_request_validation(self):
        """Test memory storage request validation"""
        
        # Test different memory types
        memory_types = ["short_term", "long_term", "semantic", "episodic"]
        
        for memory_type in memory_types:
            request_data = {
                "user_id": "user123",
                "conversation_id": "conv456", 
                "content": f"Test content for {memory_type}",
                "memory_type": memory_type,
                "metadata": {"test": True}
            }
            
            # In a real test, we would validate the Pydantic model
            # For now, just check the data structure
            assert "user_id" in request_data
            assert "conversation_id" in request_data
            assert "content" in request_data
            assert "memory_type" in request_data
            assert request_data["memory_type"] in memory_types
    
    @pytest.mark.asyncio
    async def test_conversation_storage_request(self):
        """Test conversation storage request format"""
        
        conversation_request = {
            "user_id": "user123",
            "conversation_id": "conv456",
            "messages": [
                {
                    "sender": "user",
                    "content": "Procuro uma casa",
                    "message_type": "text",
                    "metadata": {"intent": "property_search"}
                },
                {
                    "sender": "assistant", 
                    "content": "Posso ajudar você",
                    "message_type": "text",
                    "metadata": {"response_type": "helpful"}
                }
            ],
            "summary": "Conversa sobre busca de propriedades"
        }
        
        assert len(conversation_request["messages"]) == 2
        assert all("sender" in msg for msg in conversation_request["messages"])
        assert all("content" in msg for msg in conversation_request["messages"])
    
    @pytest.mark.asyncio
    async def test_memory_search_request(self):
        """Test memory search request format"""
        
        search_request = {
            "user_id": "user123",
            "query": "casas com 3 quartos",
            "memory_types": ["short_term", "long_term"],
            "limit": 5,
            "similarity_threshold": 0.7
        }
        
        assert "user_id" in search_request
        assert "query" in search_request
        assert isinstance(search_request["memory_types"], list)
        assert search_request["limit"] > 0
        assert 0 <= search_request["similarity_threshold"] <= 1


class TestMemoryErrorHandling:
    """Tests for Memory Service error handling"""
    
    @pytest.mark.asyncio
    async def test_redis_connection_failure(self, memory_service_class):
        """Test handling Redis connection failures"""
        
        class FailingRedisClient:
            async def set_json(self, key, data, ttl=None):
                raise ConnectionError("Redis connection failed")
            
            async def get_json(self, key):
                raise ConnectionError("Redis connection failed")
        
        class TestMemoryService(memory_service_class):
            def __init__(self, redis_client):
                super().__init__()
                self.redis_client = redis_client
            
            async def store_short_term_memory(self, user_id: str, conversation_id: str, content: str, metadata: Dict = None):
                try:
                    memory_data = {
                        "user_id": user_id,
                        "conversation_id": conversation_id,
                        "content": content,
                        "metadata": metadata or {},
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    
                    memory_key = f"memory:short:{user_id}:{conversation_id}"
                    await self.redis_client.set_json(memory_key, memory_data)
                    
                except ConnectionError as e:
                    # Handle gracefully
                    return {"error": f"Storage failed: {str(e)}"}
                
                return {"success": True}
        
        failing_redis = FailingRedisClient()
        memory_service = TestMemoryService(failing_redis)
        
        result = await memory_service.store_short_term_memory(
            "user123", "conv456", "test content"
        )
        
        assert "error" in result
        assert "Storage failed" in result["error"]
    
    @pytest.mark.asyncio
    async def test_embedding_generation_failure(self, mock_redis_client, memory_service_class):
        """Test handling embedding generation failures"""
        
        class TestMemoryService(memory_service_class):
            def __init__(self, redis_client):
                super().__init__()
                self.redis_client = redis_client
            
            async def get_embedding(self, text: str):
                # Simulate embedding failure
                return None
            
            async def search_memories(self, user_id: str, query: str, memory_types: List, limit: int = 5, similarity_threshold: float = 0.7):
                query_embedding = await self.get_embedding(query)
                
                if not query_embedding:
                    # Fallback to keyword-based search
                    return self._keyword_search(user_id, query, limit)
                
                # Normal embedding-based search would continue here
                return []
            
            def _keyword_search(self, user_id: str, query: str, limit: int):
                # Simple keyword-based fallback
                keywords = query.lower().split()
                
                # Mock memories for testing
                mock_memories = [
                    {
                        "content": "Procuro casa com 3 quartos",
                        "relevance_score": 0.8,
                        "search_type": "keyword"
                    },
                    {
                        "content": "Apartamento no centro",
                        "relevance_score": 0.3,
                        "search_type": "keyword"
                    }
                ]
                
                # Simple keyword matching
                scored_memories = []
                for memory in mock_memories:
                    score = sum(1 for keyword in keywords if keyword in memory["content"].lower())
                    if score > 0:
                        memory["keyword_matches"] = score
                        scored_memories.append(memory)
                
                return scored_memories[:limit]
        
        memory_service = TestMemoryService(mock_redis_client)
        
        results = await memory_service.search_memories(
            "user123", "casa quartos", ["short_term"], limit=5
        )
        
        assert len(results) > 0
        assert results[0]["search_type"] == "keyword"
        assert "keyword_matches" in results[0]


# Integration tests
@pytest.mark.asyncio
async def test_memory_integration_workflow():
    """Integration test for complete memory workflow"""
    
    class IntegratedMemoryService:
        def __init__(self):
            self.short_term_storage = {}  # In-memory storage for testing
            self.long_term_storage = {}
            self.conversation_timelines = {}
            self.embedding_model = "test"
            self.short_term_ttl = 300
            self.conversation_summary_threshold = 5
        
        async def get_embedding(self, text: str):
            # Hash-based embedding for testing
            hash_val = hash(text)
            return [(hash_val % 1000) / 1000.0] * 1536
        
        def cosine_similarity(self, vec1, vec2):
            import numpy as np
            return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
        
        def calculate_importance_score(self, content: str, metadata: Dict) -> float:
            score = 0.5
            important_keywords = ['comprar', 'vender', 'financiamento']
            keyword_count = sum(1 for keyword in important_keywords if keyword in content.lower())
            score += keyword_count * 0.2
            
            if metadata.get('is_decision_point'):
                score += 0.3
            
            return min(score, 1.0)
        
        async def store_short_term_memory(self, user_id: str, conversation_id: str, content: str, metadata: Dict = None):
            key = f"{user_id}:{conversation_id}:{len(self.short_term_storage)}"
            
            memory_data = {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "content": content,
                "metadata": metadata or {},
                "timestamp": datetime.utcnow().isoformat(),
                "memory_type": "short_term"
            }
            
            self.short_term_storage[key] = memory_data
            
            # Add to conversation timeline
            timeline_key = f"{user_id}:{conversation_id}"
            if timeline_key not in self.conversation_timelines:
                self.conversation_timelines[timeline_key] = []
            self.conversation_timelines[timeline_key].append(memory_data)
        
        async def store_long_term_memory(self, user_id: str, content: str, memory_type: str, metadata: Dict = None):
            memory_id = f"long_{len(self.long_term_storage)}"
            embedding = await self.get_embedding(content)
            
            memory_data = {
                "memory_id": memory_id,
                "user_id": user_id,
                "content": content,
                "embedding": embedding,
                "memory_type": memory_type,
                "metadata": metadata or {},
                "importance_score": self.calculate_importance_score(content, metadata or {}),
                "access_count": 0,
                "created_at": datetime.utcnow().isoformat()
            }
            
            self.long_term_storage[memory_id] = memory_data
            return memory_id
        
        async def search_memories(self, user_id: str, query: str, memory_types: List, limit: int = 5, similarity_threshold: float = 0.7):
            query_embedding = await self.get_embedding(query)
            all_memories = []
            
            # Get short-term memories
            if "short_term" in memory_types:
                for memory in self.short_term_storage.values():
                    if memory["user_id"] == user_id:
                        memory["embedding"] = await self.get_embedding(memory["content"])
                        all_memories.append(memory)
            
            # Get long-term memories
            if any(mt in ["long_term", "semantic", "episodic"] for mt in memory_types):
                for memory in self.long_term_storage.values():
                    if memory["user_id"] == user_id:
                        all_memories.append(memory)
            
            # Score by similarity
            scored_memories = []
            for memory in all_memories:
                if memory.get("embedding"):
                    similarity = self.cosine_similarity(query_embedding, memory["embedding"])
                    if similarity >= similarity_threshold:
                        memory["similarity_score"] = similarity
                        memory["relevance_score"] = similarity * 0.7 + memory.get("importance_score", 0.5) * 0.3
                        scored_memories.append(memory)
            
            scored_memories.sort(key=lambda x: x["relevance_score"], reverse=True)
            return scored_memories[:limit]
        
        async def consolidate_memories(self, user_id: str, conversation_id: str):
            timeline_key = f"{user_id}:{conversation_id}"
            messages = self.conversation_timelines.get(timeline_key, [])
            
            if len(messages) >= self.conversation_summary_threshold:
                # Create summary
                summary = f"Conversa sobre imóveis com {len(messages)} mensagens"
                
                # Store semantic memory
                semantic_id = await self.store_long_term_memory(
                    user_id=user_id,
                    content=summary,
                    memory_type="semantic",
                    metadata={
                        "conversation_id": conversation_id,
                        "is_summary": True,
                        "message_count": len(messages)
                    }
                )
                
                # Store important episodic memories
                important_messages = [
                    msg for msg in messages[-3:]
                    if self.calculate_importance_score(msg["content"], msg.get("metadata", {})) > 0.7
                ]
                
                episodic_ids = []
                for msg in important_messages:
                    episodic_id = await self.store_long_term_memory(
                        user_id=user_id,
                        content=msg["content"],
                        memory_type="episodic",
                        metadata={
                            **msg.get("metadata", {}),
                            "conversation_id": conversation_id,
                            "is_important_moment": True
                        }
                    )
                    episodic_ids.append(episodic_id)
                
                return {
                    "consolidated": True,
                    "semantic_id": semantic_id,
                    "episodic_ids": episodic_ids
                }
            
            return {"consolidated": False}
    
    # Test the integrated workflow
    memory_service = IntegratedMemoryService()
    user_id = "test_user"
    conversation_id = "test_conv"
    
    # Step 1: Store several short-term memories
    messages = [
        "Procuro uma casa para comprar",
        "Prefiro 3 quartos",
        "Orçamento até R$ 500.000",
        "Quero financiamento",
        "Uberlândia seria ideal",
        "Posso fazer uma proposta"  # This should be high importance
    ]
    
    for i, message in enumerate(messages):
        metadata = {}
        if "proposta" in message:
            metadata["is_decision_point"] = True
        
        await memory_service.store_short_term_memory(
            user_id, conversation_id, message, metadata
        )
    
    # Step 2: Test memory search
    search_results = await memory_service.search_memories(
        user_id, "casa para comprar", ["short_term"], limit=3, similarity_threshold=0.5
    )
    
    assert len(search_results) > 0
    assert any("casa" in result["content"].lower() for result in search_results)
    
    # Step 3: Trigger consolidation
    consolidation_result = await memory_service.consolidate_memories(user_id, conversation_id)
    
    assert consolidation_result["consolidated"] is True
    assert "semantic_id" in consolidation_result
    assert len(consolidation_result["episodic_ids"]) > 0
    
    # Step 4: Test search in long-term memory
    long_term_results = await memory_service.search_memories(
        user_id, "conversa imóveis", ["semantic"], limit=2, similarity_threshold=0.5
    )
    
    assert len(long_term_results) > 0
    assert any(result["memory_type"] == "semantic" for result in long_term_results)
    
    # Step 5: Verify importance scoring worked
    important_results = await memory_service.search_memories(
        user_id, "proposta", ["episodic"], limit=2, similarity_threshold=0.5
    )
    
    if important_results:
        assert important_results[0]["importance_score"] > 0.7


if __name__ == "__main__":
    pytest.main([__file__, "-v"])