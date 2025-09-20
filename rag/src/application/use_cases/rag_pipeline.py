"""
RAG pipeline use case - orchestrates document retrieval and generation
"""

import time
from typing import Optional, Dict, Any

from shared.src.utils.logging import get_logger

from ...domain.entities.document import (
    DocumentIngestRequest, Document, SearchQuery, RAGResponse
)
from ...domain.protocols.rag_service import (
    DocumentProcessorProtocol,
    EmbeddingServiceProtocol, 
    VectorStoreProtocol,
    GenerationServiceProtocol,
    CacheServiceProtocol
)


logger = get_logger("rag.pipeline")


class RAGPipelineUseCase:
    """RAG pipeline orchestration use case"""
    
    def __init__(
        self,
        document_processor: DocumentProcessorProtocol,
        embedding_service: EmbeddingServiceProtocol,
        vector_store: VectorStoreProtocol,
        generation_service: GenerationServiceProtocol,
        cache_service: Optional[CacheServiceProtocol] = None
    ):
        self.document_processor = document_processor
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.generation_service = generation_service
        self.cache_service = cache_service
    
    async def ingest_document(self, request: DocumentIngestRequest) -> Document:
        """
        Ingest and process a document for RAG
        
        Args:
            request: Document ingestion request
            
        Returns:
            Processed document with embeddings
            
        Raises:
            ValueError: If request is invalid
            RuntimeError: If ingestion fails
        """
        try:
            # Validate request
            if not request.is_valid():
                raise ValueError("Invalid document ingestion request")
            
            logger.info(f"Starting document ingestion: {request.title}")
            start_time = time.time()
            
            # Process and chunk document
            document = await self.document_processor.process_document(request)
            
            if not document.chunks:
                raise RuntimeError("Document processing produced no chunks")
            
            # Generate embeddings for chunks
            chunk_texts = [chunk.content for chunk in document.chunks]
            embeddings = await self.embedding_service.generate_embeddings_batch(chunk_texts)
            
            # Add embeddings to chunks
            for chunk, embedding in zip(document.chunks, embeddings):
                chunk.embedding = embedding
            
            # Store in vector database
            await self.vector_store.store_document(document)
            
            processing_time = time.time() - start_time
            
            logger.info(
                f"Document ingestion completed: {request.title}. "
                f"Created {len(document.chunks)} chunks with embeddings "
                f"in {processing_time:.2f}s"
            )
            
            return document
            
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Document ingestion failed for {request.title}: {str(e)}")
            raise RuntimeError(f"Document ingestion failed: {str(e)}") from e
    
    async def query_documents(
        self,
        query: str,
        top_k: int = 5,
        min_similarity: float = 0.7,
        filters: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7
    ) -> RAGResponse:
        """
        Query documents and generate response using RAG
        
        Args:
            query: User query
            top_k: Number of chunks to retrieve
            min_similarity: Minimum similarity threshold
            filters: Additional filters for search
            use_cache: Whether to use cache
            system_prompt: Custom system prompt
            temperature: Generation temperature
            
        Returns:
            RAG response with generated text and sources
            
        Raises:
            ValueError: If query is invalid
            RuntimeError: If RAG pipeline fails
        """
        try:
            # Validate query
            if not query or len(query.strip()) == 0:
                raise ValueError("Query cannot be empty")
            
            if top_k <= 0 or top_k > 50:
                raise ValueError("top_k must be between 1 and 50")
            
            if not (0 <= min_similarity <= 1):
                raise ValueError("min_similarity must be between 0 and 1")
            
            logger.info(f"Starting RAG query: {query[:100]}...")
            start_time = time.time()
            
            # Check cache first
            if use_cache and self.cache_service:
                query_hash = self.cache_service.generate_query_hash(
                    query, 
                    top_k=top_k, 
                    min_similarity=min_similarity, 
                    filters=filters or {}
                )
                cached_response = await self.cache_service.get_cached_response(query_hash)
                if cached_response:
                    logger.info(f"Cache hit for RAG query: {query[:50]}...")
                    return cached_response
            
            # Generate query embedding
            query_embedding = await self.embedding_service.generate_embedding(query)
            
            # Search for similar chunks
            search_results = await self.vector_store.search_similar_chunks(
                query_embedding=query_embedding,
                top_k=top_k,
                min_similarity=min_similarity,
                filters=filters
            )
            
            if not search_results:
                logger.info(f"No relevant documents found for query: {query[:50]}...")
                # Return response with no context
                response = RAGResponse(
                    query=query,
                    generated_response="Não encontrei informações relevantes nos documentos disponíveis para responder à sua pergunta.",
                    retrieved_chunks=[],
                    total_retrieved=0,
                    processing_time_seconds=time.time() - start_time,
                    model_used=getattr(self.generation_service, 'model', 'unknown')
                )
            else:
                # Generate response using retrieved context
                generated_text = await self.generation_service.generate_response(
                    query=query,
                    retrieved_chunks=search_results,
                    system_prompt=system_prompt,
                    temperature=temperature
                )
                
                processing_time = time.time() - start_time
                
                response = RAGResponse(
                    query=query,
                    generated_response=generated_text,
                    retrieved_chunks=search_results,
                    total_retrieved=len(search_results),
                    processing_time_seconds=processing_time,
                    model_used=getattr(self.generation_service, 'model', 'unknown')
                )
                
                logger.info(
                    f"RAG query completed: {query[:50]}... "
                    f"Retrieved {len(search_results)} chunks, "
                    f"generated {len(generated_text)} chars "
                    f"in {processing_time:.2f}s"
                )
            
            # Cache the response
            if use_cache and self.cache_service:
                query_hash = self.cache_service.generate_query_hash(
                    query,
                    top_k=top_k,
                    min_similarity=min_similarity,
                    filters=filters or {}
                )
                await self.cache_service.cache_response(query_hash, response)
            
            return response
            
        except ValueError:
            raise
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(
                f"RAG query failed: {query[:50]}... Error: {str(e)}. "
                f"Processing time: {processing_time:.2f}s"
            )
            raise RuntimeError(f"RAG query failed: {str(e)}") from e
    
    async def search_documents(
        self,
        query: str,
        top_k: int = 10,
        min_similarity: float = 0.5,
        filters: Optional[Dict[str, Any]] = None
    ) -> list:
        """
        Search documents without generation (retrieval only)
        
        Args:
            query: Search query
            top_k: Number of results to return
            min_similarity: Minimum similarity threshold
            filters: Additional filters
            
        Returns:
            List of search results
        """
        try:
            logger.info(f"Document search: {query[:100]}...")
            
            # Generate query embedding
            query_embedding = await self.embedding_service.generate_embedding(query)
            
            # Search for similar chunks
            search_results = await self.vector_store.search_similar_chunks(
                query_embedding=query_embedding,
                top_k=top_k,
                min_similarity=min_similarity,
                filters=filters
            )
            
            logger.info(f"Document search completed: found {len(search_results)} results")
            return search_results
            
        except Exception as e:
            logger.error(f"Document search failed: {str(e)}")
            raise RuntimeError(f"Document search failed: {str(e)}") from e
    
    async def delete_document(self, document_id: str) -> None:
        """
        Delete a document from the RAG system
        
        Args:
            document_id: ID of document to delete
        """
        try:
            await self.vector_store.delete_document(document_id)
            logger.info(f"Deleted document: {document_id}")
            
        except Exception as e:
            logger.error(f"Failed to delete document {document_id}: {str(e)}")
            raise RuntimeError(f"Document deletion failed: {str(e)}") from e
    
    async def get_system_stats(self) -> Dict[str, Any]:
        """Get RAG system statistics"""
        try:
            vector_stats = await self.vector_store.get_document_stats()
            
            stats = {
                "rag_system": "operational",
                "embedding_dimension": self.embedding_service.get_embedding_dimension(),
                "generation_model": getattr(self.generation_service, 'model', 'unknown'),
                "cache_enabled": self.cache_service is not None,
                **vector_stats
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting system stats: {str(e)}")
            return {
                "rag_system": "error",
                "error": str(e)
            }