"""
LangGraph workflow engine implementation.
"""
import asyncio
from typing import Dict, Any, List, Optional, TypedDict
from uuid import UUID
import time

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage
from langchain_openai import ChatOpenAI

from shared.src.utils.logging import get_logger
from shared.src.utils.config import get_settings
from shared.src.utils.helpers import generate_correlation_id

from ..domain.interfaces import WorkflowEngine, AgentService
from ..domain.models import (
    WorkflowDefinition, 
    WorkflowExecution, 
    WorkflowStatus,
    NodeExecution,
    NodeStatus
)


logger = get_logger(__name__)


class WorkflowState(TypedDict):
    """State structure for LangGraph workflows."""
    messages: List[Dict[str, Any]]
    current_step: str
    user_id: str
    conversation_id: str
    context: Dict[str, Any]
    results: Dict[str, Any]
    error: Optional[str]


class LangGraphWorkflowEngine(WorkflowEngine):
    """LangGraph-based workflow engine."""
    
    def __init__(self, agent_service: AgentService, memory_client=None):
        self.agent_service = agent_service
        self.memory_client = memory_client
        self.workflows: Dict[str, StateGraph] = {}

        settings = get_settings()

        # Dev fallback LLM (no external calls)
        class _DevLLM:
            async def ainvoke(self, messages):
                class _Resp:
                    def __init__(self, content: str):
                        self.content = content

                # Basic echo-style response suitable for prompts used
                text = ""
                try:
                    last = messages[-1] if messages else None
                    text = getattr(last, "content", "") if last else ""
                except Exception:
                    text = ""
                return _Resp(content=f"[dev] {text[:400]}")

        if settings.environment == "development" or not settings.ai.openai_api_key:
            logger.info("Using dev fallback LLM (no OpenAI key found or development environment)")
            self.llm = _DevLLM()
        else:
            # Optionally make model configurable via env OPENAI_MODEL; default remains gpt-4
            import os
            model_name = os.getenv("OPENAI_MODEL", "gpt-4")
            self.llm = ChatOpenAI(model=model_name, temperature=0.1)

        self._initialize_workflows()
    
    def _initialize_workflows(self):
        """Initialize all workflow definitions."""
        
        # Audio Processing Workflow
        self.workflows["audio_processing_workflow"] = self._create_audio_processing_workflow()
        
        # Property Search Workflow
        self.workflows["property_search_workflow"] = self._create_property_search_workflow()
        
        # Greeting Workflow
        self.workflows["greeting_workflow"] = self._create_greeting_workflow()
        
        # Question Answering Workflow
        self.workflows["question_answering_workflow"] = self._create_question_answering_workflow()
        
        # General Conversation Workflow
        self.workflows["general_conversation_workflow"] = self._create_general_conversation_workflow()
        
        logger.info("Initialized workflows", count=len(self.workflows))
    
    def _create_audio_processing_workflow(self) -> StateGraph:
        """Create audio processing workflow."""
        
        workflow = StateGraph(WorkflowState)
        
        async def transcribe_audio(state: WorkflowState) -> WorkflowState:
            """Transcribe audio message."""
            logger.info("Transcribing audio", conversation_id=state["conversation_id"])
            
            try:
                # Call transcription service using URL-based endpoint
                payload = {
                    "audio_url": state["context"].get("audio_url") or state["context"].get("file_url"),
                    "content_type": state["context"].get("content_type"),
                    "language": state["context"].get("language", "pt"),
                    "use_cache": True,
                }
                result = await self.agent_service.execute_task("transcription", payload)
                
                state["results"]["transcription"] = result
                # API returns 'text' for successful transcription
                state["context"]["transcribed_text"] = result.get("text", "")
                state["current_step"] = "transcribed"
                
                logger.info("Audio transcribed successfully", conversation_id=state["conversation_id"])
                
            except Exception as e:
                logger.error("Transcription failed", error=str(e), conversation_id=state["conversation_id"])
                state["error"] = f"Transcription failed: {str(e)}"
            
            return state
        
        async def process_transcribed_text(state: WorkflowState) -> WorkflowState:
            """Process transcribed text."""
            
            transcribed_text = state["context"].get("transcribed_text", "")
            
            if transcribed_text:
                # Re-route based on transcribed content
                # This would trigger another workflow
                state["results"]["next_workflow"] = "property_search_workflow"
                state["results"]["processed_content"] = transcribed_text
            
            state["current_step"] = "completed"
            return state
        
        # Build workflow graph
        workflow.add_node("transcribe", transcribe_audio)
        workflow.add_node("process_text", process_transcribed_text)
        
        workflow.set_entry_point("transcribe")
        workflow.add_edge("transcribe", "process_text")
        workflow.add_edge("process_text", END)
        
        return workflow.compile()
    
    def _create_property_search_workflow(self) -> StateGraph:
        """Create property search workflow."""
        
        workflow = StateGraph(WorkflowState)
        
        async def extract_search_criteria(state: WorkflowState) -> WorkflowState:
            """Extract search criteria from message."""
            
            message_content = state["context"].get("message_content", "")
            
            # Use LLM to extract search criteria
            prompt = f"""
            Extract property search criteria from this message: "{message_content}"
            
            Extract:
            - Property type (casa, apartamento, terreno, etc.)
            - Location (city, neighborhood, address)
            - Price range (min/max)
            - Number of bedrooms
            - Number of bathrooms
            - Area (square meters)
            - Special features
            
            Return as JSON.
            """
            
            try:
                response = await self.llm.ainvoke([HumanMessage(content=prompt)])
                # Parse LLM response to extract criteria
                criteria = {
                    "property_type": None,
                    "location": None,
                    "price_min": None,
                    "price_max": None,
                    "bedrooms": None,
                    "bathrooms": None,
                    "area_min": None,
                    "area_max": None,
                    "features": []
                }
                
                state["results"]["search_criteria"] = criteria
                state["current_step"] = "criteria_extracted"
                
            except Exception as e:
                logger.error("Failed to extract criteria", error=str(e))
                state["error"] = f"Failed to extract search criteria: {str(e)}"
            
            return state
        
        async def search_properties(state: WorkflowState) -> WorkflowState:
            """Search for properties."""
            
            criteria = state["results"].get("search_criteria", {})
            
            try:
                # Call web search service
                result = await self.agent_service.execute_task(
                    "web_search",
                    {
                        "search_type": "property_search",
                        "criteria": criteria
                    }
                )
                
                # Accept both {properties: [...]} and {results: [...]} shapes
                props = result.get("properties") if isinstance(result, dict) else None
                if props is None and isinstance(result, dict):
                    props = result.get("results")
                state["results"]["properties"] = props or []
                state["current_step"] = "properties_found"
                
            except Exception as e:
                logger.error("Property search failed", error=str(e))
                state["error"] = f"Property search failed: {str(e)}"
            
            return state
        
        async def format_response(state: WorkflowState) -> WorkflowState:
            """Format property search response."""
            
            properties = state["results"].get("properties", [])
            search_criteria = state["results"].get("search_criteria", {})
            
            if properties:
                # Format properties for presentation
                formatted_response = f"Encontrei {len(properties)} imóveis que podem te interessar:\n\n"
                
                for i, prop in enumerate(properties[:5], 1):  # Show top 5
                    formatted_response += f"{i}. {prop.get('title', 'Imóvel')}\n"
                    formatted_response += f"   💰 {prop.get('price', 'Preço não informado')}\n"
                    formatted_response += f"   📍 {prop.get('location', 'Localização não informada')}\n"
                    formatted_response += f"   🏠 {prop.get('bedrooms', '?')} quartos, {prop.get('bathrooms', '?')} banheiros\n\n"
                
                formatted_response += "Gostaria de mais detalhes sobre algum destes imóveis?"
                
                # Store successful search in long-term memory
                if self.memory_client:
                    search_summary = f"Busca por {search_criteria.get('property_type', 'imóvel')} em {search_criteria.get('location', 'localização não especificada')}. Encontrados {len(properties)} resultados."
                    
                    await self.memory_client.store_message(
                        user_id=state["user_id"],
                        conversation_id=state["conversation_id"],
                        content=search_summary,
                        sender="system",
                        message_type="search_result",
                        metadata={
                            "workflow": "property_search",
                            "criteria": search_criteria,
                            "results_count": len(properties),
                            "success": True,
                            "importance_score": 0.8,  # High importance for successful searches
                            "timestamp": time.time()
                        }
                    )
            else:
                formatted_response = "Não encontrei imóveis com os critérios informados. Pode tentar uma busca diferente?"
                
                # Store unsuccessful search with lower importance
                if self.memory_client:
                    search_summary = f"Busca sem resultados: {search_criteria.get('property_type', 'imóvel')} em {search_criteria.get('location', 'localização não especificada')}"
                    
                    await self.memory_client.store_message(
                        user_id=state["user_id"],
                        conversation_id=state["conversation_id"],
                        content=search_summary,
                        sender="system",
                        message_type="search_result",
                        metadata={
                            "workflow": "property_search",
                            "criteria": search_criteria,
                            "results_count": 0,
                            "success": False,
                            "importance_score": 0.4,
                            "timestamp": time.time()
                        }
                    )
            
            # Store the formatted response
            if self.memory_client:
                await self.memory_client.store_message(
                    user_id=state["user_id"],
                    conversation_id=state["conversation_id"],
                    content=formatted_response,
                    sender="assistant",
                    message_type="text",
                    metadata={
                        "workflow": "property_search",
                        "is_response": True,
                        "timestamp": time.time()
                    }
                )
            
            state["results"]["formatted_response"] = formatted_response
            state["current_step"] = "completed"
            
            return state
        
        # Build workflow graph
        workflow.add_node("extract_criteria", extract_search_criteria)
        workflow.add_node("search_properties", search_properties)
        workflow.add_node("format_response", format_response)
        
        workflow.set_entry_point("extract_criteria")
        workflow.add_edge("extract_criteria", "search_properties")
        workflow.add_edge("search_properties", "format_response")
        workflow.add_edge("format_response", END)
        
        return workflow.compile()
    
    def _create_greeting_workflow(self) -> StateGraph:
        """Create greeting workflow."""
        
        workflow = StateGraph(WorkflowState)
        
        async def generate_greeting(state: WorkflowState) -> WorkflowState:
            """Generate personalized greeting."""
            
            # Get user context from memory (fallback to provided context)
            try:
                user_context = {}
                
                # Try to get context from memory service first
                if self.memory_client:
                    user_context = await self.memory_client.get_user_context(state["user_id"])
                
                # Fallback to context from workflow input
                if not user_context and state["context"].get("user_context"):
                    user_context = state["context"]["user_context"]
                
                # Extract user information from context
                recent_memories = user_context.get("recent_memories", [])
                important_memories = user_context.get("important_memories", [])
                
                # Check if user has property search history
                has_search_history = any(
                    "busca" in mem.get("content", "").lower() or 
                    "imóvel" in mem.get("content", "").lower() or
                    "propriedade" in mem.get("content", "").lower()
                    for mem in recent_memories + important_memories
                )
                
                # Generate personalized greeting
                if has_search_history:
                    greeting = "Olá novamente! 👋\n\n"
                    greeting += "Vejo que você já conversou comigo antes sobre imóveis. "
                    greeting += "Como posso te ajudar hoje? Quer continuar uma busca anterior ou começar uma nova?\n\n"
                else:
                    greeting = "Olá! 👋\n\n"
                    greeting += "Sou o assistente da FamaGPT, especialista em imóveis de Uberlândia e região.\n\n"
                    greeting += "Como posso te ajudar hoje? Posso:\n"
                    greeting += "• 🏠 Buscar imóveis para compra ou aluguel\n"
                    greeting += "• 💰 Avaliar o valor de um imóvel\n"
                    greeting += "• 📋 Tirar dúvidas sobre documentação\n"
                    greeting += "• 📞 Conectar você com nossos corretores\n\n"
                
                greeting += "O que você gostaria de fazer?"
                
                state["results"]["greeting"] = greeting
                state["current_step"] = "completed"
                
                # Store the greeting response in memory
                if self.memory_client:
                    await self.memory_client.store_message(
                        user_id=state["user_id"],
                        conversation_id=state["conversation_id"],
                        content=greeting,
                        sender="assistant",
                        message_type="text",
                        metadata={
                            "workflow": "greeting",
                            "personalized": has_search_history,
                            "timestamp": time.time()
                        }
                    )
                
            except Exception as e:
                logger.error("Failed to generate greeting", error=str(e))
                fallback_greeting = "Olá! Como posso te ajudar hoje?"
                state["results"]["greeting"] = fallback_greeting
                state["current_step"] = "completed"
                
                # Store fallback greeting in memory
                if self.memory_client:
                    try:
                        await self.memory_client.store_message(
                            user_id=state["user_id"],
                            conversation_id=state["conversation_id"],
                            content=fallback_greeting,
                            sender="assistant",
                            message_type="text",
                            metadata={"workflow": "greeting", "fallback": True}
                        )
                    except:
                        pass  # Don't fail if memory storage fails
            
            return state
        
        workflow.add_node("generate_greeting", generate_greeting)
        workflow.set_entry_point("generate_greeting")
        workflow.add_edge("generate_greeting", END)
        
        return workflow.compile()
    
    def _create_question_answering_workflow(self) -> StateGraph:
        """Create question answering workflow."""
        
        workflow = StateGraph(WorkflowState)
        
        async def retrieve_knowledge(state: WorkflowState) -> WorkflowState:
            """Retrieve relevant knowledge."""
            
            question = state["context"].get("message_content", "")
            
            try:
                # Search user's memory for relevant past conversations
                memory_results = []
                if self.memory_client:
                    memory_results = await self.memory_client.search_memories(
                        user_id=state["user_id"],
                        query=question,
                        memory_types=["short_term", "long_term"],
                        limit=3,
                        similarity_threshold=0.6
                    )
                
                # Call RAG service for domain knowledge
                result = await self.agent_service.execute_task(
                    "rag",
                    {
                        "query": question,
                        "context_type": "real_estate"
                    }
                )
                
                # Combine RAG and memory results
                state["results"]["rag_response"] = result
                state["results"]["retrieved_docs"] = result.get("sources", [])
                state["results"]["sources"] = result.get("sources", [])
                state["results"]["memory_context"] = memory_results
                state["current_step"] = "knowledge_retrieved"
                
            except Exception as e:
                logger.error("Knowledge retrieval failed", error=str(e))
                state["error"] = f"Knowledge retrieval failed: {str(e)}"
            
            return state
        
        async def generate_answer(state: WorkflowState) -> WorkflowState:
            """Generate answer using retrieved knowledge."""
            
            question = state["context"].get("message_content", "")
            rag_result = state["results"].get("rag_response", {})
            memory_context = state["results"].get("memory_context", [])

            # Prefer answer from RAG service, enhance with memory context
            try:
                generated = rag_result.get("generated_response") if isinstance(rag_result, dict) else None
                sources = state["results"].get("sources", [])
                
                if generated:
                    # Build formatted response including sources if present
                    formatted = generated
                    
                    # Add relevant memory context if available
                    if memory_context:
                        relevant_memories = [mem for mem in memory_context if mem.get('similarity_score', 0) > 0.7]
                        if relevant_memories:
                            formatted += "\n\n📋 Com base em nossas conversas anteriores:\n"
                            for mem in relevant_memories[:2]:  # Top 2 relevant memories
                                content = mem.get('content', '')[:200] + '...' if len(mem.get('content', '')) > 200 else mem.get('content', '')
                                formatted += f"• {content}\n"
                    
                    if sources:
                        formatted += "\n\nFontes:\n"
                        for src in sources[:3]:
                            title = src.get("document_title") or src.get("chunk_id", "fonte")
                            score = src.get("similarity_score")
                            if score is not None:
                                formatted += f"- {title} (similaridade {score:.2f})\n"
                            else:
                                formatted += f"- {title}\n"
                    
                    state["results"]["answer"] = generated
                    state["results"]["formatted_response"] = formatted
                    state["current_step"] = "completed"
                else:
                    # Fallback to LLM with combined context
                    docs = state["results"].get("retrieved_docs", [])
                    context = "\n".join([doc.get("content", "") for doc in docs])
                    
                    # Add memory context
                    if memory_context:
                        memory_text = "\n".join([mem.get("content", "") for mem in memory_context[:3]])
                        context += f"\n\nContexto das conversas anteriores:\n{memory_text}"
                    
                    prompt = f"""
                    Baseado no contexto abaixo, responda a pergunta sobre imóveis:
                    
                    Contexto:
                    {context}
                    
                    Pergunta: {question}
                    
                    Responda de forma clara e útil, focando em informações sobre o mercado imobiliário de Uberlândia/MG.
                    Se houver informações das conversas anteriores, use-as para personalizar a resposta.
                    """
                    response = await self.llm.ainvoke([HumanMessage(content=prompt)])
                    state["results"]["answer"] = response.content
                    state["results"]["formatted_response"] = response.content
                    state["current_step"] = "completed"
                
                # Store the Q&A interaction in memory
                if self.memory_client:
                    qa_summary = f"Pergunta: {question[:200]}... Respondido com base em {len(sources)} fontes e {len(memory_context)} memórias."
                    
                    await self.memory_client.store_message(
                        user_id=state["user_id"],
                        conversation_id=state["conversation_id"],
                        content=qa_summary,
                        sender="system",
                        message_type="qa_interaction",
                        metadata={
                            "workflow": "question_answering",
                            "sources_count": len(sources),
                            "memory_context_count": len(memory_context),
                            "question": question,
                            "importance_score": 0.6,
                            "timestamp": time.time()
                        }
                    )
                    
                    # Store the actual response
                    await self.memory_client.store_message(
                        user_id=state["user_id"],
                        conversation_id=state["conversation_id"],
                        content=state["results"]["formatted_response"],
                        sender="assistant",
                        message_type="text",
                        metadata={
                            "workflow": "question_answering",
                            "is_response": True,
                            "timestamp": time.time()
                        }
                    )
                    
            except Exception as e:
                logger.error("Answer generation failed", error=str(e))
                fallback_answer = "Desculpe, não consegui processar sua pergunta no momento."
                state["results"]["answer"] = fallback_answer
                state["results"]["formatted_response"] = fallback_answer
                state["current_step"] = "completed"
                
                # Store error in memory
                if self.memory_client:
                    try:
                        await self.memory_client.store_message(
                            user_id=state["user_id"],
                            conversation_id=state["conversation_id"],
                            content=fallback_answer,
                            sender="assistant",
                            message_type="text",
                            metadata={
                                "workflow": "question_answering",
                                "error": True,
                                "timestamp": time.time()
                            }
                        )
                    except:
                        pass
            
            return state
        
        workflow.add_node("retrieve_knowledge", retrieve_knowledge)
        workflow.add_node("generate_answer", generate_answer)
        
        workflow.set_entry_point("retrieve_knowledge")
        workflow.add_edge("retrieve_knowledge", "generate_answer")
        workflow.add_edge("generate_answer", END)
        
        return workflow.compile()
    
    def _create_general_conversation_workflow(self) -> StateGraph:
        """Create general conversation workflow."""
        
        workflow = StateGraph(WorkflowState)
        
        async def generate_response(state: WorkflowState) -> WorkflowState:
            """Generate general response."""
            
            message = state["context"].get("message_content", "")
            
            prompt = f"""
            Você é um assistente especializado em imóveis de Uberlândia/MG.
            Responda de forma amigável e tente direcionar a conversa para como você pode ajudar com imóveis.
            
            Mensagem do usuário: {message}
            """
            
            try:
                response = await self.llm.ainvoke([HumanMessage(content=prompt)])
                state["results"]["response"] = response.content
                state["current_step"] = "completed"
                
            except Exception as e:
                logger.error("Response generation failed", error=str(e))
                state["results"]["response"] = "Como posso te ajudar com imóveis hoje?"
                state["current_step"] = "completed"
            
            return state
        
        workflow.add_node("generate_response", generate_response)
        workflow.set_entry_point("generate_response")
        workflow.add_edge("generate_response", END)
        
        return workflow.compile()
    
    async def execute_workflow(
        self,
        workflow_name: str,
        input_data: Dict[str, Any],
        conversation_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None
    ) -> WorkflowExecution:
        """Execute workflow using LangGraph."""
        
        if workflow_name not in self.workflows:
            raise ValueError(f"Workflow '{workflow_name}' not found")
        
        # Create workflow execution record
        execution = WorkflowExecution(
            workflow_name=workflow_name,
            conversation_id=conversation_id,
            user_id=user_id,
            input_data=input_data,
            status=WorkflowStatus.RUNNING
        )
        
        # Prepare initial state
        initial_state: WorkflowState = {
            "messages": [],
            "current_step": "start",
            "user_id": str(user_id) if user_id else "",
            "conversation_id": str(conversation_id) if conversation_id else "",
            "context": input_data,
            "results": {},
            "error": None
        }
        
        try:
            # Execute workflow
            workflow_graph = self.workflows[workflow_name]
            
            start_time = time.time()
            final_state = await workflow_graph.ainvoke(initial_state)
            execution_time = int((time.time() - start_time) * 1000)
            
            # Update execution with results
            execution.output_data = final_state["results"]
            execution.current_node = final_state["current_step"]
            
            if final_state.get("error"):
                execution.status = WorkflowStatus.FAILED
                execution.error_message = final_state["error"]
            else:
                execution.status = WorkflowStatus.COMPLETED
            
            logger.info(
                "Workflow executed",
                workflow_name=workflow_name,
                execution_id=execution.id,
                status=execution.status,
                execution_time_ms=execution_time
            )
            
        except Exception as e:
            execution.status = WorkflowStatus.FAILED
            execution.error_message = str(e)
            
            logger.error(
                "Workflow execution failed",
                workflow_name=workflow_name,
                execution_id=execution.id,
                error=str(e)
            )
        
        return execution
    
    async def get_workflow_definition(self, workflow_name: str) -> Optional[WorkflowDefinition]:
        """Get workflow definition."""
        
        if workflow_name not in self.workflows:
            return None
        
        # For now, return a basic definition
        # In a full implementation, this would return detailed node/edge information
        return WorkflowDefinition(
            name=workflow_name,
            description=f"LangGraph workflow: {workflow_name}",
            nodes=[],
            edges=[],
            entry_point="start"
        )
