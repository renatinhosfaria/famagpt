"""
Testes para o Specialist Service
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
from datetime import datetime

# Mock do ambiente shared para testes
import sys
import os
sys.path.append('/var/www/famagpt')

from specialist.src.domain.entities.property import Property, PropertyType, PropertyStatus, PropertyCondition, Address, PropertyFeatures, PropertyFinancial
from specialist.src.domain.entities.user import ConversationContext, ConversationStatus, UserProfile, UserType
from specialist.src.application.use_cases.process_user_query import ProcessUserQueryUseCase
from specialist.src.application.services.conversation_service import ConversationService
from specialist.src.application.services.property_service import PropertyService
from specialist.src.application.services.ai_orchestrator import AIOrchestrator
from specialist.src.infrastructure.clients.external_services import LocalIntentClassificationService, LocalResponseGenerationService


@pytest.fixture
def mock_redis_client():
    """Mock Redis client"""
    mock = AsyncMock()
    mock.get_json.return_value = None
    mock.set_json.return_value = None
    mock.scan_keys.return_value = []
    return mock


@pytest.fixture
def mock_http_client():
    """Mock HTTP client"""
    mock = AsyncMock()
    mock.post.return_value = Mock(status_code=200, json=lambda: {"success": True})
    mock.get.return_value = Mock(status_code=200, json=lambda: {"data": []})
    return mock


@pytest.fixture
def mock_memory_service():
    """Mock memory service"""
    mock = AsyncMock()
    mock.store_conversation.return_value = None
    mock.get_conversation_context.return_value = None
    mock.update_user_context.return_value = None
    mock.get_relevant_memories.return_value = []
    return mock


@pytest.fixture
def mock_rag_service():
    """Mock RAG service"""
    mock = AsyncMock()
    mock.query_knowledge_base.return_value = {
        "answer": "Informações sobre imóveis em Uberlândia",
        "sources": []
    }
    return mock


@pytest.fixture
def sample_property():
    """Sample property for testing"""
    return Property(
        id=uuid4(),
        title="Casa 3 quartos no Centro",
        description="Linda casa no centro da cidade",
        property_type=PropertyType.CASA,
        status=PropertyStatus.VENDA,
        condition=PropertyCondition.USADO,
        address=Address(
            street="Rua Principal",
            number="123",
            neighborhood="Centro",
            city="Uberlândia",
            state="MG",
            zip_code="38400-000"
        ),
        features=PropertyFeatures(
            bedrooms=3,
            bathrooms=2,
            area_built=120.0
        ),
        financial=PropertyFinancial(
            price=450000.0
        )
    )


@pytest.fixture
def conversation_context():
    """Sample conversation context"""
    return ConversationContext(
        id=uuid4(),
        user_id=uuid4(),
        status=ConversationStatus.ACTIVE,
        current_intent="property_search",
        search_criteria={"city": "Uberlândia", "bedrooms": 3},
        created_at=datetime.utcnow()
    )


class TestIntentClassification:
    """Tests for intent classification service"""
    
    def setUp(self):
        self.intent_service = LocalIntentClassificationService()
    
    @pytest.mark.asyncio
    async def test_property_search_intent(self):
        """Test property search intent classification"""
        self.setUp()
        
        message = "Procuro uma casa com 3 quartos para comprar em Uberlândia"
        result = await self.intent_service.classify_intent(message)
        
        assert result["intent"] == "property_search"
        assert result["confidence"] > 0
    
    @pytest.mark.asyncio
    async def test_greeting_intent(self):
        """Test greeting intent classification"""
        self.setUp()
        
        message = "Olá, bom dia!"
        result = await self.intent_service.classify_intent(message)
        
        assert result["intent"] == "greeting"
        assert result["confidence"] > 0
    
    @pytest.mark.asyncio
    async def test_entity_extraction(self):
        """Test entity extraction from message"""
        self.setUp()
        
        message = "Quero um apartamento com 2 quartos por até R$ 300.000"
        result = await self.intent_service.extract_entities(message)
        
        entities = result["entities"]
        assert entities["property_type"] == "apartamento"
        assert entities["bedrooms"] == 2
        assert "price_range" in entities


class TestConversationService:
    """Tests for conversation service"""
    
    @pytest.mark.asyncio
    async def test_create_new_context(self, mock_redis_client, mock_memory_service):
        """Test creating new conversation context"""
        conversation_service = ConversationService(mock_redis_client, mock_memory_service)
        
        user_id = uuid4()
        conversation_id = uuid4()
        
        # Mock no existing context
        mock_redis_client.get_json.return_value = None
        mock_memory_service.get_conversation_context.return_value = None
        
        context = await conversation_service.get_or_create_context(user_id, conversation_id)
        
        assert context.user_id == user_id
        assert context.id == conversation_id
        assert context.status == ConversationStatus.ACTIVE
        
        # Verify caching was called
        mock_redis_client.set_json.assert_called()
    
    @pytest.mark.asyncio
    async def test_update_context(self, mock_redis_client, mock_memory_service):
        """Test updating conversation context"""
        conversation_service = ConversationService(mock_redis_client, mock_memory_service)
        
        conversation_id = uuid4()
        
        # Mock existing context in cache
        mock_redis_client.scan_keys.return_value = [f"conversation_context:user:{conversation_id}"]
        mock_redis_client.get_json.return_value = {
            "id": str(conversation_id),
            "user_id": str(uuid4()),
            "status": "active"
        }
        
        updates = {"current_intent": "property_search"}
        await conversation_service.update_context(conversation_id, updates)
        
        # Verify update was called
        mock_redis_client.set_json.assert_called()
    
    @pytest.mark.asyncio
    async def test_store_interaction(self, mock_redis_client, mock_memory_service):
        """Test storing user interaction"""
        conversation_service = ConversationService(mock_redis_client, mock_memory_service)
        
        user_id = uuid4()
        conversation_id = uuid4()
        user_message = "Procuro uma casa"
        assistant_response = "Posso ajudar você a encontrar uma casa"
        
        await conversation_service.store_interaction(
            user_id, conversation_id, user_message, assistant_response
        )
        
        # Verify memory service was called
        mock_memory_service.store_conversation.assert_called_once()
        
        # Check that 2 messages were stored (user + assistant)
        args = mock_memory_service.store_conversation.call_args[0]
        messages = args[2]
        assert len(messages) == 2
        assert messages[0].sender == "user"
        assert messages[1].sender == "assistant"


class TestPropertyService:
    """Tests for property service"""
    
    @pytest.mark.asyncio
    async def test_search_properties(self, sample_property):
        """Test property search functionality"""
        # Mock dependencies
        mock_repo = AsyncMock()
        mock_web_search = AsyncMock()
        mock_analysis = AsyncMock()
        mock_recommendation = AsyncMock()
        
        mock_repo.search.return_value = [sample_property]
        
        property_service = PropertyService(
            mock_repo, mock_web_search, mock_analysis, mock_recommendation
        )
        
        criteria = {"city": "Uberlândia", "bedrooms": 3}
        results = await property_service.search_properties(criteria, limit=5)
        
        assert len(results) == 1
        assert results[0].title == sample_property.title
        assert results[0].features.bedrooms == 3
        
        # Verify repository was called with correct criteria
        mock_repo.search.assert_called_once_with(criteria, 5)
    
    @pytest.mark.asyncio
    async def test_get_property_details(self, sample_property):
        """Test getting property details"""
        mock_repo = AsyncMock()
        mock_web_search = AsyncMock()
        mock_analysis = AsyncMock()
        mock_recommendation = AsyncMock()
        
        mock_repo.find_by_id.return_value = sample_property
        
        property_service = PropertyService(
            mock_repo, mock_web_search, mock_analysis, mock_recommendation
        )
        
        result = await property_service.get_property_details(sample_property.id)
        
        assert result is not None
        assert result.id == sample_property.id
        assert result.title == sample_property.title
    
    @pytest.mark.asyncio
    async def test_property_not_found(self):
        """Test handling when property is not found"""
        mock_repo = AsyncMock()
        mock_web_search = AsyncMock()
        mock_analysis = AsyncMock()
        mock_recommendation = AsyncMock()
        
        mock_repo.find_by_id.return_value = None
        
        property_service = PropertyService(
            mock_repo, mock_web_search, mock_analysis, mock_recommendation
        )
        
        result = await property_service.get_property_details(uuid4())
        
        assert result is None


class TestAIOrchestrator:
    """Tests for AI orchestrator"""
    
    @pytest.mark.asyncio
    async def test_classify_intent(self, mock_memory_service, mock_rag_service):
        """Test intent classification orchestration"""
        intent_service = LocalIntentClassificationService()
        response_service = LocalResponseGenerationService()
        
        orchestrator = AIOrchestrator(
            mock_memory_service, mock_rag_service, intent_service, response_service
        )
        
        message = "Quero comprar uma casa"
        result = await orchestrator.classify_intent(message)
        
        assert "intent" in result
        assert "entities" in result
        assert result["intent"] == "property_search"
    
    @pytest.mark.asyncio
    async def test_extract_search_criteria(self, mock_memory_service, mock_rag_service):
        """Test search criteria extraction"""
        intent_service = LocalIntentClassificationService()
        response_service = LocalResponseGenerationService()
        
        orchestrator = AIOrchestrator(
            mock_memory_service, mock_rag_service, intent_service, response_service
        )
        
        message = "Procuro um apartamento com 2 quartos em Uberlândia"
        entities = {"property_type": "apartamento", "bedrooms": 2}
        
        criteria = await orchestrator.extract_search_criteria(message, entities)
        
        assert criteria["property_type"] == "apartamento"
        assert criteria["bedrooms"] == 2
        assert criteria["city"] == "Uberlândia"  # Default city
    
    @pytest.mark.asyncio
    async def test_query_knowledge_base(self, mock_memory_service):
        """Test knowledge base querying"""
        mock_rag_service = AsyncMock()
        mock_rag_service.query_knowledge_base.return_value = {
            "answer": "Informações sobre financiamento imobiliário",
            "sources": [{"document": "financing_guide.txt"}]
        }
        
        intent_service = LocalIntentClassificationService()
        response_service = LocalResponseGenerationService()
        
        orchestrator = AIOrchestrator(
            mock_memory_service, mock_rag_service, intent_service, response_service
        )
        
        query = "Como funciona o financiamento imobiliário?"
        result = await orchestrator.query_knowledge_base(query)
        
        assert "answer" in result
        assert "sources" in result
        assert len(result["sources"]) > 0
        
        # Verify RAG service was called
        mock_rag_service.query_knowledge_base.assert_called_once_with(
            query, context=None, top_k=5
        )


class TestProcessUserQueryUseCase:
    """Tests for main use case"""
    
    @pytest.mark.asyncio
    async def test_property_search_workflow(
        self, 
        mock_redis_client, 
        mock_memory_service,
        mock_rag_service,
        conversation_context,
        sample_property
    ):
        """Test complete property search workflow"""
        # Setup services
        conversation_service = ConversationService(mock_redis_client, mock_memory_service)
        
        # Mock property service
        mock_prop_repo = AsyncMock()
        mock_web_search = AsyncMock()
        mock_analysis = AsyncMock()
        mock_recommendation = AsyncMock()
        
        mock_prop_repo.search.return_value = [sample_property]
        
        property_service = PropertyService(
            mock_prop_repo, mock_web_search, mock_analysis, mock_recommendation
        )
        
        # Setup AI orchestrator
        intent_service = LocalIntentClassificationService()
        response_service = LocalResponseGenerationService()
        
        ai_orchestrator = AIOrchestrator(
            mock_memory_service, mock_rag_service, intent_service, response_service
        )
        
        # Mock conversation context retrieval
        mock_redis_client.get_json.return_value = None
        mock_memory_service.get_conversation_context.return_value = None
        
        # Setup use case
        use_case = ProcessUserQueryUseCase(
            conversation_service, property_service, ai_orchestrator
        )
        
        # Execute use case
        user_message = "Procuro uma casa com 3 quartos em Uberlândia"
        result = await use_case.execute(
            user_id=str(uuid4()),
            conversation_id=str(uuid4()),
            message=user_message
        )
        
        # Verify results
        assert result["success"] is True
        assert result["intent"] == "property_search"
        assert len(result["properties"]) == 1
        assert result["properties"][0]["title"] == sample_property.title
        assert "suggestions" in result
        assert len(result["suggestions"]) > 0
    
    @pytest.mark.asyncio
    async def test_greeting_workflow(
        self,
        mock_redis_client,
        mock_memory_service,
        mock_rag_service
    ):
        """Test greeting workflow"""
        # Setup services
        conversation_service = ConversationService(mock_redis_client, mock_memory_service)
        
        # Mock property service (not used in greeting)
        property_service = Mock()
        
        # Setup AI orchestrator
        intent_service = LocalIntentClassificationService()
        response_service = LocalResponseGenerationService()
        
        ai_orchestrator = AIOrchestrator(
            mock_memory_service, mock_rag_service, intent_service, response_service
        )
        
        # Mock context creation
        mock_redis_client.get_json.return_value = None
        mock_memory_service.get_conversation_context.return_value = None
        
        # Setup use case
        use_case = ProcessUserQueryUseCase(
            conversation_service, property_service, ai_orchestrator
        )
        
        # Execute use case
        result = await use_case.execute(
            user_id=str(uuid4()),
            conversation_id=str(uuid4()),
            message="Olá, bom dia!"
        )
        
        # Verify results
        assert result["success"] is True
        assert result["intent"] == "greeting"
        assert "response" in result
        assert "suggestions" in result
    
    @pytest.mark.asyncio
    async def test_error_handling(
        self,
        mock_redis_client,
        mock_memory_service,
        mock_rag_service
    ):
        """Test error handling in use case"""
        # Setup services with failing conversation service
        mock_redis_client.get_json.side_effect = Exception("Redis error")
        
        conversation_service = ConversationService(mock_redis_client, mock_memory_service)
        property_service = Mock()
        
        intent_service = LocalIntentClassificationService()
        response_service = LocalResponseGenerationService()
        
        ai_orchestrator = AIOrchestrator(
            mock_memory_service, mock_rag_service, intent_service, response_service
        )
        
        # Setup use case
        use_case = ProcessUserQueryUseCase(
            conversation_service, property_service, ai_orchestrator
        )
        
        # Execute use case
        result = await use_case.execute(
            user_id=str(uuid4()),
            conversation_id=str(uuid4()),
            message="Test message"
        )
        
        # Verify error handling
        assert result["success"] is False
        assert "error" in result
        assert result["response_type"] == "error"


class TestPropertyEntity:
    """Tests for property entity"""
    
    def test_property_creation(self):
        """Test property entity creation"""
        property_id = uuid4()
        
        property = Property(
            id=property_id,
            title="Test Property",
            description="Test description",
            property_type=PropertyType.CASA,
            status=PropertyStatus.VENDA,
            condition=PropertyCondition.NOVO,
            address=Address(
                street="Test Street",
                number="123",
                neighborhood="Test Neighborhood",
                city="Uberlândia",
                state="MG",
                zip_code="38400-000"
            ),
            features=PropertyFeatures(
                bedrooms=3,
                bathrooms=2,
                area_built=120.0
            ),
            financial=PropertyFinancial(
                price=500000.0
            )
        )
        
        assert property.id == property_id
        assert property.title == "Test Property"
        assert property.property_type == PropertyType.CASA
        assert property.address.city == "Uberlândia"
        assert property.features.bedrooms == 3
        assert property.financial.price == 500000.0
    
    def test_property_to_dict(self):
        """Test property to dict conversion"""
        property = Property(
            id=uuid4(),
            title="Test Property",
            description="Test description",
            property_type=PropertyType.APARTAMENTO,
            status=PropertyStatus.ALUGUEL,
            condition=PropertyCondition.USADO,
            address=Address(
                street="Test Street",
                number="456",
                neighborhood="Centro",
                city="Uberlândia",
                state="MG",
                zip_code="38400-100"
            ),
            features=PropertyFeatures(
                bedrooms=2,
                bathrooms=1,
                area_built=80.0
            ),
            financial=PropertyFinancial(
                rental_price=2000.0
            )
        )
        
        property_dict = property.to_dict()
        
        assert property_dict["title"] == "Test Property"
        assert property_dict["property_type"] == "apartamento"
        assert property_dict["status"] == "aluguel"
        assert property_dict["address"]["neighborhood"] == "Centro"
        assert property_dict["features"]["bedrooms"] == 2
        assert property_dict["financial"]["rental_price"] == 2000.0


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])