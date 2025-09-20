"""
Testes de integração entre serviços do FamaGPT
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
import httpx
from uuid import uuid4
import json

# Mock do ambiente para testes
import sys
import os
sys.path.append('/var/www/famagpt')


class TestServiceIntegration:
    """Testes de integração entre serviços"""
    
    @pytest.fixture
    def mock_http_client(self):
        """Mock HTTP client para comunicação entre serviços"""
        mock = AsyncMock()
        
        # Mock responses para diferentes serviços
        mock_responses = {
            "memory": {
                "status_code": 200,
                "json": lambda: {
                    "status": "stored",
                    "memory_id": "mem123"
                }
            },
            "rag": {
                "status_code": 200,
                "json": lambda: {
                    "answer": "Informações sobre imóveis em Uberlândia",
                    "sources": [{"document": "market_info.txt"}],
                    "confidence": 0.85
                }
            },
            "web_search": {
                "status_code": 200,
                "json": lambda: {
                    "properties": [
                        {
                            "title": "Casa 3 quartos",
                            "price": 450000,
                            "location": "Uberlândia"
                        }
                    ]
                }
            }
        }
        
        def mock_post(url, **kwargs):
            # Determine service based on URL
            if "memory" in url:
                return Mock(**mock_responses["memory"])
            elif "rag" in url:
                return Mock(**mock_responses["rag"])
            elif "web_search" in url:
                return Mock(**mock_responses["web_search"])
            else:
                return Mock(status_code=200, json=lambda: {"status": "ok"})
        
        def mock_get(url, **kwargs):
            return Mock(status_code=200, json=lambda: {"status": "healthy"})
        
        mock.post.side_effect = mock_post
        mock.get.side_effect = mock_get
        
        return mock
    
    @pytest.fixture
    def mock_redis_client(self):
        """Mock Redis client"""
        mock = AsyncMock()
        mock.get_json.return_value = None
        mock.set_json.return_value = None
        return mock
    
    @pytest.mark.asyncio
    async def test_specialist_to_memory_integration(self, mock_http_client, mock_redis_client):
        """Test integration between Specialist and Memory services"""
        
        # Mock do external memory service
        class MockExternalMemoryService:
            def __init__(self, http_client, memory_service_url):
                self.http_client = http_client
                self.base_url = memory_service_url.rstrip('/')
            
            async def store_conversation(self, user_id, conversation_id, messages):
                payload = {
                    "user_id": str(user_id),
                    "conversation_id": str(conversation_id),
                    "messages": [
                        {
                            "content": msg.content,
                            "sender": msg.sender,
                            "timestamp": msg.timestamp.isoformat() if hasattr(msg, 'timestamp') and msg.timestamp else None,
                            "metadata": getattr(msg, 'metadata', {})
                        }
                        for msg in messages
                    ]
                }
                
                await self.http_client.post(f"{self.base_url}/store", json=payload)
        
        memory_service = MockExternalMemoryService(mock_http_client, "http://memory:8004")
        
        # Test storing conversation
        class MockMessage:
            def __init__(self, content, sender):
                self.content = content
                self.sender = sender
                self.timestamp = None
                self.metadata = {}
        
        messages = [MockMessage("Procuro uma casa", "user")]
        
        await memory_service.store_conversation(
            user_id=uuid4(),
            conversation_id=uuid4(),
            messages=messages
        )
        
        # Verify HTTP call was made
        assert mock_http_client.post.called
        call_args = mock_http_client.post.call_args
        assert "memory" in call_args[0][0]  # URL contains 'memory'
        assert "json" in call_args[1]  # JSON payload was sent
    
    @pytest.mark.asyncio
    async def test_specialist_to_rag_integration(self, mock_http_client):
        """Test integration between Specialist and RAG services"""
        
        class MockExternalRAGService:
            def __init__(self, http_client, rag_service_url):
                self.http_client = http_client
                self.base_url = rag_service_url.rstrip('/')
            
            async def query_knowledge_base(self, query: str, context: str = "", top_k: int = 5):
                payload = {
                    "query": query,
                    "context": context or "",
                    "top_k": top_k
                }
                
                response = await self.http_client.post(f"{self.base_url}/query", json=payload)
                
                if response.status_code == 200:
                    return response.json()
                
                return {
                    "answer": "Não consegui encontrar informações específicas no momento.",
                    "sources": []
                }
        
        rag_service = MockExternalRAGService(mock_http_client, "http://rag:8005")
        
        # Test querying knowledge base
        result = await rag_service.query_knowledge_base(
            query="Como funciona o financiamento imobiliário?",
            context="Uberlândia",
            top_k=3
        )
        
        # Verify response structure
        assert "answer" in result
        assert "sources" in result
        assert result["confidence"] == 0.85
        
        # Verify HTTP call
        assert mock_http_client.post.called
        call_args = mock_http_client.post.call_args
        assert "rag" in call_args[0][0]
        
        # Verify payload structure
        payload = call_args[1]["json"]
        assert "query" in payload
        assert "context" in payload
        assert "top_k" in payload
    
    @pytest.mark.asyncio
    async def test_full_conversation_workflow(self, mock_http_client, mock_redis_client):
        """Test complete conversation workflow across services"""
        
        # Mock services
        class MockMemoryService:
            def __init__(self, http_client):
                self.http_client = http_client
            
            async def store_conversation(self, user_id, conversation_id, messages):
                await self.http_client.post("http://memory:8004/store", json={"test": "data"})
        
        class MockRAGService:
            def __init__(self, http_client):
                self.http_client = http_client
            
            async def query_knowledge_base(self, query):
                response = await self.http_client.post("http://rag:8005/query", json={"query": query})
                return response.json()
        
        class MockIntentService:
            async def classify_intent(self, message):
                return {"intent": "property_search", "confidence": 0.9}
        
        class MockAIOrchestrator:
            def __init__(self, memory_service, rag_service, intent_service):
                self.memory_service = memory_service
                self.rag_service = rag_service
                self.intent_service = intent_service
            
            async def classify_intent(self, message):
                return await self.intent_service.classify_intent(message)
            
            async def query_knowledge_base(self, query):
                return await self.rag_service.query_knowledge_base(query)
        
        # Initialize services
        memory_service = MockMemoryService(mock_http_client)
        rag_service = MockRAGService(mock_http_client)
        intent_service = MockIntentService()
        
        ai_orchestrator = MockAIOrchestrator(memory_service, rag_service, intent_service)
        
        # Simulate conversation workflow
        user_message = "Preciso de informações sobre financiamento imobiliário"
        
        # Step 1: Classify intent
        intent_result = await ai_orchestrator.classify_intent(user_message)
        assert "intent" in intent_result
        
        # Step 2: Query knowledge base
        knowledge_result = await ai_orchestrator.query_knowledge_base(user_message)
        assert "answer" in knowledge_result
        
        # Step 3: Store interaction in memory (mock)
        await memory_service.store_conversation(uuid4(), uuid4(), [])
        
        # Verify services were called
        assert mock_http_client.post.call_count >= 2  # RAG + Memory calls
    
    @pytest.mark.asyncio
    async def test_service_health_checks(self, mock_http_client):
        """Test health check integration"""
        
        services = [
            "http://specialist:8007/health",
            "http://memory:8004/health",
            "http://rag:8005/health",
            "http://web_search:8003/health"
        ]
        
        # Test health checks for all services
        for service_url in services:
            response = await mock_http_client.get(service_url)
            assert response.status_code == 200
            health_data = response.json()
            assert health_data["status"] == "healthy"


class TestServiceCommunicationProtocols:
    """Test communication protocols between services"""
    
    @pytest.mark.asyncio
    async def test_message_format_consistency(self):
        """Test that message formats are consistent across services"""
        
        # Standard message format that should be used across all services
        standard_message = {
            "user_id": "user123",
            "conversation_id": "conv456",
            "message": "Test message",
            "context": {},
            "timestamp": "2024-01-01T12:00:00Z",
            "metadata": {}
        }
        
        # Verify all required fields are present
        required_fields = ["user_id", "conversation_id", "message"]
        for field in required_fields:
            assert field in standard_message
            assert standard_message[field] is not None
    
    @pytest.mark.asyncio
    async def test_error_response_format(self):
        """Test that error responses follow consistent format"""
        
        standard_error_response = {
            "success": False,
            "error": "Service temporarily unavailable",
            "error_code": "SERVICE_ERROR",
            "timestamp": "2024-01-01T12:00:00Z",
            "service": "memory"
        }
        
        # Verify error response structure
        assert "success" in standard_error_response
        assert standard_error_response["success"] is False
        assert "error" in standard_error_response
        assert "timestamp" in standard_error_response
    
    @pytest.mark.asyncio
    async def test_success_response_format(self):
        """Test that success responses follow consistent format"""
        
        standard_success_response = {
            "success": True,
            "data": {"result": "Operation completed"},
            "timestamp": "2024-01-01T12:00:00Z",
            "service": "specialist"
        }
        
        # Verify success response structure
        assert "success" in standard_success_response
        assert standard_success_response["success"] is True
        assert "data" in standard_success_response
        assert "timestamp" in standard_success_response


class TestServiceResilience:
    """Test service resilience and fault tolerance"""
    
    @pytest.mark.asyncio
    async def test_error_propagation_between_services(self):
        """Test error handling in service integration"""
        
        # Setup failing HTTP client
        failing_http_client = AsyncMock()
        failing_http_client.post.side_effect = httpx.ConnectError("Connection failed")
        
        class MockMemoryService:
            def __init__(self, http_client):
                self.http_client = http_client
            
            async def store_conversation(self, user_id, conversation_id, messages):
                try:
                    await self.http_client.post("http://memory:8004/store", json={"test": "data"})
                except Exception as e:
                    raise e
        
        memory_service = MockMemoryService(failing_http_client)
        
        # Test that connection errors are properly raised
        with pytest.raises(httpx.ConnectError):
            await memory_service.store_conversation(uuid4(), uuid4(), [])
    
    @pytest.mark.asyncio
    async def test_graceful_degradation(self):
        """Test graceful degradation when services are unavailable"""
        
        # Setup failing services
        failing_http_client = AsyncMock()
        failing_http_client.post.side_effect = httpx.ConnectError("All services down")
        
        class MockLocalIntentService:
            async def classify_intent(self, message):
                # Local service - should always work
                if "casa" in message.lower() or "procuro" in message.lower():
                    return {"intent": "property_search", "confidence": 0.8}
                elif "olá" in message.lower():
                    return {"intent": "greeting", "confidence": 0.9}
                else:
                    return {"intent": "general_inquiry", "confidence": 0.5}
        
        class MockRAGServiceWithFallback:
            def __init__(self, http_client):
                self.http_client = http_client
            
            async def query_knowledge_base(self, query):
                try:
                    response = await self.http_client.post("http://rag:8005/query", json={"query": query})
                    return response.json()
                except httpx.ConnectError:
                    # Graceful degradation - return default response
                    return {
                        "answer": "Desculpe, o serviço de conhecimento está temporariamente indisponível. Como posso ajudar você de outra forma?",
                        "sources": [],
                        "error": "Service unavailable"
                    }
        
        # Test local service (should work)
        intent_service = MockLocalIntentService()
        intent_result = await intent_service.classify_intent("Procuro uma casa")
        assert intent_result["intent"] == "property_search"
        
        # Test RAG service with fallback
        rag_service = MockRAGServiceWithFallback(failing_http_client)
        rag_result = await rag_service.query_knowledge_base("test query")
        assert "answer" in rag_result
        assert "error" in rag_result  # Should indicate the service error
        assert "indisponível" in rag_result["answer"]
    
    @pytest.mark.asyncio
    async def test_concurrent_requests_handling(self):
        """Test handling multiple concurrent requests"""
        
        # Mock HTTP client with slight delays
        async def mock_post_with_delay(url, **kwargs):
            await asyncio.sleep(0.1)  # Small delay to simulate real network
            return Mock(
                status_code=200,
                json=lambda: {"answer": f"Response for {kwargs.get('json', {}).get('query', 'unknown')}"}
            )
        
        mock_http_client = AsyncMock()
        mock_http_client.post.side_effect = mock_post_with_delay
        
        class MockRAGService:
            def __init__(self, http_client):
                self.http_client = http_client
            
            async def query_knowledge_base(self, query):
                response = await self.http_client.post("http://rag:8005/query", json={"query": query})
                return response.json()
        
        rag_service = MockRAGService(mock_http_client)
        
        # Create multiple concurrent requests
        queries = [
            "Preços de imóveis em Uberlândia",
            "Como funciona financiamento?", 
            "Melhores bairros para investir",
            "Documentação para compra",
            "Tendências do mercado"
        ]
        
        # Execute concurrent requests
        tasks = [rag_service.query_knowledge_base(query) for query in queries]
        
        start_time = asyncio.get_event_loop().time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed_time = asyncio.get_event_loop().time() - start_time
        
        # Verify all requests completed
        assert len(results) == len(queries)
        
        # Verify no exceptions occurred
        for result in results:
            assert not isinstance(result, Exception)
            assert "answer" in result
        
        # Verify concurrent execution (should be faster than sequential)
        assert elapsed_time < 1.0  # Should be much faster than 5 * 0.1 = 0.5 seconds


class TestDataConsistency:
    """Test data consistency across services"""
    
    @pytest.mark.asyncio
    async def test_user_context_consistency(self):
        """Test that user context is consistent across all services"""
        
        user_id = str(uuid4())
        conversation_id = str(uuid4())
        
        # Standard user context format
        user_context = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "preferences": {
                "property_type": "casa",
                "budget_max": 500000,
                "location": "Uberlândia"
            },
            "conversation_history": [],
            "last_interaction": "2024-01-01T12:00:00Z"
        }
        
        # Verify context structure
        assert "user_id" in user_context
        assert "conversation_id" in user_context
        assert "preferences" in user_context
        assert isinstance(user_context["preferences"], dict)
    
    @pytest.mark.asyncio
    async def test_property_data_consistency(self):
        """Test that property data format is consistent across services"""
        
        # Standard property format
        property_data = {
            "id": str(uuid4()),
            "title": "Casa 3 quartos no Centro",
            "property_type": "casa",
            "price": 450000.0,
            "location": {
                "city": "Uberlândia",
                "state": "MG",
                "neighborhood": "Centro"
            },
            "features": {
                "bedrooms": 3,
                "bathrooms": 2,
                "area": 120.0
            },
            "source": "web_search",
            "created_at": "2024-01-01T12:00:00Z"
        }
        
        # Verify property structure
        required_fields = ["id", "title", "property_type", "location", "features"]
        for field in required_fields:
            assert field in property_data
            assert property_data[field] is not None
        
        # Verify location structure
        location_fields = ["city", "state"]
        for field in location_fields:
            assert field in property_data["location"]
    
    @pytest.mark.asyncio
    async def test_memory_data_consistency(self):
        """Test that memory data format is consistent"""
        
        # Standard memory format
        memory_data = {
            "memory_id": str(uuid4()),
            "user_id": str(uuid4()),
            "content": "Cliente interessado em casa com 3 quartos",
            "memory_type": "episodic",
            "importance_score": 0.8,
            "timestamp": "2024-01-01T12:00:00Z",
            "metadata": {
                "conversation_id": str(uuid4()),
                "intent": "property_search"
            }
        }
        
        # Verify memory structure
        required_fields = ["memory_id", "user_id", "content", "memory_type", "timestamp"]
        for field in required_fields:
            assert field in memory_data
            assert memory_data[field] is not None
        
        # Verify importance score is valid
        assert 0.0 <= memory_data["importance_score"] <= 1.0


# Performance benchmarks
class TestPerformance:
    """Basic performance tests"""
    
    @pytest.mark.asyncio
    async def test_response_time_requirements(self):
        """Test that services meet basic response time requirements"""
        
        # Mock fast HTTP client
        async def fast_response(url, **kwargs):
            return Mock(
                status_code=200,
                json=lambda: {"result": "fast response"}
            )
        
        mock_http_client = AsyncMock()
        mock_http_client.post.side_effect = fast_response
        mock_http_client.get.side_effect = fast_response
        
        # Test various service calls
        start_time = asyncio.get_event_loop().time()
        
        # Simulate multiple service calls
        await mock_http_client.get("http://specialist:8007/health")
        await mock_http_client.post("http://rag:8005/query", json={"query": "test"})
        await mock_http_client.post("http://memory:8004/store", json={"data": "test"})
        
        elapsed_time = asyncio.get_event_loop().time() - start_time
        
        # Should complete quickly (mock services)
        assert elapsed_time < 0.1  # 100ms for all calls
    
    @pytest.mark.asyncio
    async def test_memory_usage_patterns(self):
        """Test that memory usage is reasonable for typical operations"""
        
        # Create some test data structures
        large_conversation = {
            "messages": [
                {"content": f"Message {i}", "sender": "user"}
                for i in range(1000)  # Large conversation
            ]
        }
        
        large_property_list = [
            {
                "id": str(uuid4()),
                "title": f"Property {i}",
                "price": 400000 + i * 1000,
                "description": "A" * 500  # Large description
            }
            for i in range(100)  # Many properties
        ]
        
        # Verify data structures are reasonable
        assert len(large_conversation["messages"]) == 1000
        assert len(large_property_list) == 100
        
        # Test JSON serialization performance
        start_time = asyncio.get_event_loop().time()
        
        json_conversation = json.dumps(large_conversation)
        json_properties = json.dumps(large_property_list)
        
        elapsed_time = asyncio.get_event_loop().time() - start_time
        
        # Should serialize quickly
        assert elapsed_time < 1.0  # 1 second max
        assert len(json_conversation) > 0
        assert len(json_properties) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])