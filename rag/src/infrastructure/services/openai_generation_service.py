"""
OpenAI text generation service for RAG
"""

from typing import List, Optional
import time

from openai import AsyncOpenAI

from shared.src.utils.logging import get_logger
from shared.src.utils.config import get_settings

from ...domain.entities.document import SearchResult
from ...domain.protocols.rag_service import GenerationServiceProtocol


logger = get_logger("rag.openai_generation")
settings = get_settings()


class OpenAIGenerationService(GenerationServiceProtocol):
    """OpenAI text generation service for RAG"""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.ai.openai_api_key)
        self.model = "gpt-3.5-turbo"
        self.max_context_length = 4000  # Conservative limit for context
        self.max_tokens = 1000
    
    async def generate_response(
        self,
        query: str,
        retrieved_chunks: List[SearchResult],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7
    ) -> str:
        """Generate response using retrieved context"""
        try:
            start_time = time.time()
            
            # Build context from retrieved chunks
            context = self._build_context_from_chunks(retrieved_chunks)
            
            # Create system prompt
            if system_prompt is None:
                system_prompt = self._get_default_system_prompt()
            
            # Create user message with context and query
            user_message = self._create_user_message(query, context)
            
            # Generate response
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=self.max_tokens,
                temperature=temperature,
                top_p=0.9,
                frequency_penalty=0.1,
                presence_penalty=0.1
            )
            
            generated_text = response.choices[0].message.content
            processing_time = time.time() - start_time
            
            logger.info(
                f"Generated response for query in {processing_time:.3f}s. "
                f"Used {len(retrieved_chunks)} chunks, "
                f"response length: {len(generated_text)} chars"
            )
            
            return generated_text
            
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            raise RuntimeError(f"Text generation failed: {str(e)}") from e
    
    def _build_context_from_chunks(self, chunks: List[SearchResult]) -> str:
        """Build context text from retrieved chunks"""
        if not chunks:
            return ""
        
        context_parts = []
        current_length = 0
        
        for i, result in enumerate(chunks):
            chunk_text = result.chunk.content
            doc_title = result.document_title or "Unknown Document"
            similarity = result.get_final_score()
            
            # Format chunk with metadata
            chunk_content = f"[Documento: {doc_title} | Relevância: {similarity:.2f}]\n{chunk_text}"
            
            # Check if adding this chunk would exceed context length
            if current_length + len(chunk_content) > self.max_context_length:
                if i == 0:  # Always include at least the first chunk
                    truncated_content = chunk_content[:self.max_context_length]
                    context_parts.append(truncated_content)
                break
            
            context_parts.append(chunk_content)
            current_length += len(chunk_content)
        
        context = "\n\n---\n\n".join(context_parts)
        
        logger.debug(f"Built context from {len(context_parts)} chunks, total length: {len(context)} chars")
        
        return context
    
    def _get_default_system_prompt(self) -> str:
        """Get default system prompt for RAG generation"""
        return """Você é um assistente especialista em imóveis em Uberlândia/MG. 

Instruções:
1. Use APENAS as informações fornecidas no contexto para responder
2. Se a informação não estiver no contexto, diga "Não encontrei essa informação nos documentos disponíveis"
3. Seja específico e cite as fontes quando possível
4. Mantenha um tom profissional e útil
5. Foque em informações relevantes para o mercado imobiliário de Uberlândia/MG
6. Se necessário, sugira outras fontes ou próximos passos

Responda sempre em português brasileiro."""
    
    def _create_user_message(self, query: str, context: str) -> str:
        """Create user message with context and query"""
        if not context:
            return f"Pergunta: {query}\n\nContexto: Nenhum contexto relevante encontrado."
        
        return f"""Contexto dos documentos:

{context}

---

Pergunta: {query}

Por favor, responda com base nas informações do contexto fornecido."""
    
    def get_model_name(self) -> str:
        """Get the model name being used"""
        return self.model
    
    def set_model(self, model_name: str) -> None:
        """Set the model to use for generation"""
        self.model = model_name
        
        # Adjust context length based on model
        if "gpt-4" in model_name:
            self.max_context_length = 6000
            self.max_tokens = 1500
        elif "gpt-3.5-turbo-16k" in model_name:
            self.max_context_length = 8000
            self.max_tokens = 2000
        else:
            self.max_context_length = 4000
            self.max_tokens = 1000