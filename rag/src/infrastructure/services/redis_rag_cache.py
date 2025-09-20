"""
Redis cache service for RAG operations
"""

from typing import Optional, List
import json
import hashlib
from datetime import datetime

from shared.src.infrastructure.redis_client import RedisClient
from shared.src.utils.logging import get_logger

from ...domain.entities.document import RAGResponse, SearchResult, DocumentChunk
from ...domain.protocols.rag_service import CacheServiceProtocol


logger = get_logger("rag.redis_cache")


class RedisRAGCache(CacheServiceProtocol):
    """Redis implementation for RAG caching"""
    
    def __init__(self, redis_client: RedisClient):
        self.redis_client = redis_client
        self.response_prefix = "rag:response:"
        self.embedding_prefix = "rag:embedding:"
    
    async def get_cached_response(self, query_hash: str) -> Optional[RAGResponse]:
        """Get cached RAG response"""
        try:
            cache_key = f"{self.response_prefix}{query_hash}"
            cached_data = await self.redis_client.get_json(cache_key)
            
            if not cached_data:
                logger.debug(f"Cache miss for RAG response: {query_hash}")
                return None
            
            logger.debug(f"Cache hit for RAG response: {query_hash}")
            
            # Reconstruct SearchResult objects
            retrieved_chunks = []
            for chunk_data in cached_data.get("retrieved_chunks", []):
                chunk = self._dict_to_document_chunk(chunk_data.get("chunk", {}))
                if chunk:
                    search_result = SearchResult(
                        chunk=chunk,
                        similarity_score=chunk_data.get("similarity_score", 0.0),
                        rerank_score=chunk_data.get("rerank_score"),
                        document_title=chunk_data.get("document_title"),
                        document_metadata=chunk_data.get("document_metadata", {})
                    )
                    retrieved_chunks.append(search_result)
            
            # Reconstruct RAGResponse
            response = RAGResponse(
                query=cached_data.get("query", ""),
                generated_response=cached_data.get("generated_response", ""),
                retrieved_chunks=retrieved_chunks,
                total_retrieved=cached_data.get("total_retrieved", 0),
                processing_time_seconds=cached_data.get("processing_time_seconds"),
                model_used=cached_data.get("model_used"),
                created_at=self._parse_datetime(cached_data.get("created_at"))
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Error getting cached RAG response: {str(e)}")
            return None
    
    async def cache_response(
        self,
        query_hash: str,
        response: RAGResponse,
        ttl_seconds: int = 3600
    ) -> None:
        """Cache RAG response"""
        try:
            cache_key = f"{self.response_prefix}{query_hash}"
            
            # Convert to cacheable format
            cache_data = {
                "query": response.query,
                "generated_response": response.generated_response,
                "retrieved_chunks": [
                    {
                        "chunk": self._document_chunk_to_dict(result.chunk),
                        "similarity_score": result.similarity_score,
                        "rerank_score": result.rerank_score,
                        "document_title": result.document_title,
                        "document_metadata": result.document_metadata
                    }
                    for result in response.retrieved_chunks
                ],
                "total_retrieved": response.total_retrieved,
                "processing_time_seconds": response.processing_time_seconds,
                "model_used": response.model_used,
                "created_at": response.created_at.isoformat() if response.created_at else None,
                "cached_at": datetime.utcnow().isoformat()
            }
            
            await self.redis_client.set_json(cache_key, cache_data, ttl=ttl_seconds)
            
            logger.debug(f"Cached RAG response: {query_hash}, TTL: {ttl_seconds}s")
            
        except Exception as e:
            logger.error(f"Error caching RAG response: {str(e)}")
    
    async def get_cached_embeddings(self, text_hash: str) -> Optional[List[float]]:
        """Get cached text embeddings"""
        try:
            cache_key = f"{self.embedding_prefix}{text_hash}"
            cached_embedding = await self.redis_client.get_json(cache_key)
            
            if cached_embedding:
                logger.debug(f"Cache hit for embedding: {text_hash}")
                return cached_embedding
            
            logger.debug(f"Cache miss for embedding: {text_hash}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting cached embeddings: {str(e)}")
            return None
    
    async def cache_embeddings(
        self,
        text_hash: str,
        embeddings: List[float],
        ttl_seconds: int = 86400
    ) -> None:
        """Cache text embeddings"""
        try:
            cache_key = f"{self.embedding_prefix}{text_hash}"
            
            await self.redis_client.set_json(
                cache_key, 
                embeddings, 
                ttl=ttl_seconds
            )
            
            logger.debug(f"Cached embeddings: {text_hash}, TTL: {ttl_seconds}s")
            
        except Exception as e:
            logger.error(f"Error caching embeddings: {str(e)}")
    
    def _document_chunk_to_dict(self, chunk: DocumentChunk) -> dict:
        """Convert DocumentChunk to dictionary"""
        return {
            "id": chunk.id,
            "document_id": chunk.document_id,
            "content": chunk.content,
            "chunk_index": chunk.chunk_index,
            "start_position": chunk.start_position,
            "end_position": chunk.end_position,
            "metadata": chunk.metadata,
            "created_at": chunk.created_at.isoformat() if chunk.created_at else None
        }
    
    def _dict_to_document_chunk(self, data: dict) -> Optional[DocumentChunk]:
        """Convert dictionary to DocumentChunk"""
        try:
            return DocumentChunk(
                id=data.get("id"),
                document_id=data.get("document_id"),
                content=data.get("content"),
                chunk_index=data.get("chunk_index"),
                start_position=data.get("start_position"),
                end_position=data.get("end_position"),
                metadata=data.get("metadata", {}),
                created_at=self._parse_datetime(data.get("created_at"))
            )
        except Exception as e:
            logger.error(f"Error converting dict to DocumentChunk: {str(e)}")
            return None
    
    def _parse_datetime(self, datetime_str: Optional[str]) -> Optional[datetime]:
        """Parse ISO datetime string"""
        if not datetime_str:
            return None
        
        try:
            return datetime.fromisoformat(datetime_str)
        except Exception:
            return None
    
    def generate_query_hash(self, query: str, **kwargs) -> str:
        """Generate hash for query caching"""
        # Include relevant parameters in hash
        hash_input = f"{query}"
        
        # Add filters to hash if provided
        if kwargs:
            sorted_kwargs = sorted(kwargs.items())
            hash_input += f"|{json.dumps(sorted_kwargs, sort_keys=True)}"
        
        return hashlib.md5(hash_input.encode()).hexdigest()