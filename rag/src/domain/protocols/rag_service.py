"""
Domain protocols for RAG service
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

from ..entities.document import (
    Document, DocumentChunk, SearchQuery, SearchResult, RAGResponse, DocumentIngestRequest
)


class DocumentProcessorProtocol(ABC):
    """Protocol for document processing and chunking"""
    
    @abstractmethod
    async def process_document(self, request: DocumentIngestRequest) -> Document:
        """
        Process and chunk a document for RAG
        
        Args:
            request: Document ingestion request
            
        Returns:
            Processed document with chunks
        """
        pass
    
    @abstractmethod
    async def chunk_text(
        self, 
        text: str, 
        chunk_size: int = 1000, 
        chunk_overlap: int = 200
    ) -> List[str]:
        """
        Split text into chunks
        
        Args:
            text: Text to chunk
            chunk_size: Maximum chunk size in characters
            chunk_overlap: Overlap between chunks
            
        Returns:
            List of text chunks
        """
        pass


class EmbeddingServiceProtocol(ABC):
    """Protocol for text embeddings"""
    
    @abstractmethod
    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for text
        
        Args:
            text: Text to embed
            
        Returns:
            Vector embedding
        """
        pass
    
    @abstractmethod
    async def generate_embeddings_batch(
        self, 
        texts: List[str]
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of vector embeddings
        """
        pass
    
    @abstractmethod
    def get_embedding_dimension(self) -> int:
        """Get dimension of embeddings"""
        pass


class VectorStoreProtocol(ABC):
    """Protocol for vector storage and retrieval"""
    
    @abstractmethod
    async def store_document(self, document: Document) -> None:
        """
        Store document and its chunks in vector database
        
        Args:
            document: Document with embedded chunks
        """
        pass
    
    @abstractmethod
    async def search_similar_chunks(
        self, 
        query_embedding: List[float], 
        top_k: int = 5,
        min_similarity: float = 0.7,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """
        Search for similar chunks using vector similarity
        
        Args:
            query_embedding: Query embedding vector
            top_k: Number of results to return
            min_similarity: Minimum similarity threshold
            filters: Additional filters
            
        Returns:
            List of search results with similarity scores
        """
        pass
    
    @abstractmethod
    async def delete_document(self, document_id: str) -> None:
        """
        Delete document and all its chunks
        
        Args:
            document_id: ID of document to delete
        """
        pass
    
    @abstractmethod
    async def get_document_stats(self) -> Dict[str, Any]:
        """Get statistics about stored documents"""
        pass


class GenerationServiceProtocol(ABC):
    """Protocol for text generation with RAG"""
    
    @abstractmethod
    async def generate_response(
        self,
        query: str,
        retrieved_chunks: List[SearchResult],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7
    ) -> str:
        """
        Generate response using retrieved context
        
        Args:
            query: User query
            retrieved_chunks: Retrieved relevant chunks
            system_prompt: System prompt for generation
            temperature: Generation temperature
            
        Returns:
            Generated response
        """
        pass


class RerankingServiceProtocol(ABC):
    """Protocol for reranking search results"""
    
    @abstractmethod
    async def rerank_results(
        self,
        query: str,
        results: List[SearchResult]
    ) -> List[SearchResult]:
        """
        Rerank search results for better relevance
        
        Args:
            query: Original query
            results: Initial search results
            
        Returns:
            Reranked results with updated scores
        """
        pass


class CacheServiceProtocol(ABC):
    """Protocol for caching RAG results"""
    
    @abstractmethod
    async def get_cached_response(self, query_hash: str) -> Optional[RAGResponse]:
        """Get cached RAG response"""
        pass
    
    @abstractmethod
    async def cache_response(
        self,
        query_hash: str,
        response: RAGResponse,
        ttl_seconds: int = 3600
    ) -> None:
        """Cache RAG response"""
        pass
    
    @abstractmethod
    async def get_cached_embeddings(
        self, 
        text_hash: str
    ) -> Optional[List[float]]:
        """Get cached text embeddings"""
        pass
    
    @abstractmethod
    async def cache_embeddings(
        self,
        text_hash: str,
        embeddings: List[float],
        ttl_seconds: int = 86400
    ) -> None:
        """Cache text embeddings"""
        pass