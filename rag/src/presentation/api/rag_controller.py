"""
RAG API Controller - FastAPI endpoints for RAG operations
"""

from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field

from shared.src.utils.logging import get_logger

from ...application.services.rag_service import RAGService
from ...domain.entities.document import RAGResponse


logger = get_logger("rag.controller")


# Pydantic Models for API
class DocumentIngestDTO(BaseModel):
    """DTO for document ingestion"""
    title: str = Field(..., description="Document title", min_length=1, max_length=500)
    content: str = Field(..., description="Document content", min_length=1)
    document_type: str = Field(default="text", description="Type of document")
    source_url: Optional[str] = Field(default=None, description="Source URL if applicable")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class RAGQueryDTO(BaseModel):
    """DTO for RAG queries"""
    query: str = Field(..., description="User query", min_length=1, max_length=1000)
    top_k: int = Field(default=5, description="Number of chunks to retrieve", ge=1, le=50)
    min_similarity: float = Field(default=0.7, description="Minimum similarity threshold", ge=0.0, le=1.0)
    filters: Dict[str, Any] = Field(default_factory=dict, description="Additional filters")
    use_cache: bool = Field(default=True, description="Whether to use cache")
    system_prompt: Optional[str] = Field(default=None, description="Custom system prompt")
    temperature: float = Field(default=0.7, description="Generation temperature", ge=0.0, le=2.0)


class DocumentSearchDTO(BaseModel):
    """DTO for document search"""
    query: str = Field(..., description="Search query", min_length=1, max_length=1000)
    top_k: int = Field(default=10, description="Number of results", ge=1, le=50)
    min_similarity: float = Field(default=0.5, description="Minimum similarity threshold", ge=0.0, le=1.0)
    filters: Dict[str, Any] = Field(default_factory=dict, description="Additional filters")


class RAGResponseDTO(BaseModel):
    """DTO for RAG responses"""
    query: str
    generated_response: str
    total_retrieved: int
    processing_time_seconds: float
    model_used: str
    sources: List[Dict[str, Any]]
    # TestSprite compatibility fields
    results: Optional[List[Dict[str, Any]]] = None  # Alias for sources
    documents: Optional[List[Dict[str, Any]]] = None  # Alias for sources
    created_at: datetime
    
    # Note: results and documents fields are set programmatically for TestSprite compatibility


def get_rag_service() -> RAGService:
    """Dependency injection for RAG service - to be configured in main.py"""
    # This will be set up in main.py with proper dependency injection
    pass


def create_rag_router(rag_service_factory) -> APIRouter:
    """Create RAG router with injected dependencies"""
    
    router = APIRouter(prefix="/api/v1/rag", tags=["rag"])
    
    @router.post("/ingest", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
    async def ingest_document(request: DocumentIngestDTO):
        """
        Ingest a document into the RAG system
        
        Args:
            request: Document ingestion request
            
        Returns:
            Document ingestion result
        """
        try:
            rag_service = rag_service_factory()
            document = await rag_service.ingest_document(
                title=request.title,
                content=request.content,
                document_type=request.document_type,
                source_url=request.source_url,
                metadata=request.metadata
            )
            
            return {
                "message": "Document ingested successfully",
                "document_id": document.id,
                "title": document.title,
                "chunks_created": len(document.chunks or []),
                "status": document.status.value if document.status else "processed",
                "created_at": document.created_at.isoformat() if document.created_at else None
            }
            
        except ValueError as e:
            logger.warning(f"Invalid document ingestion request: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid request: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Document ingestion failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Document ingestion failed: {str(e)}"
            )
    
    @router.post("/query", response_model=Dict[str, Any])
    async def query_rag(request: RAGQueryDTO):
        """
        Query the RAG system for information
        
        Args:
            request: RAG query request
            
        Returns:
            RAG response with generated text and sources
        """
        try:
            rag_service = rag_service_factory()
            response = await rag_service.query_rag(
                query=request.query,
                top_k=request.top_k,
                min_similarity=request.min_similarity,
                filters=request.filters,
                use_cache=request.use_cache,
                system_prompt=request.system_prompt,
                temperature=request.temperature
            )
            
            # Convert to DTO format
            sources = []
            for chunk_result in response.retrieved_chunks:
                sources.append({
                    "chunk_id": chunk_result.chunk.id,
                    "document_id": chunk_result.chunk.document_id,
                    "document_title": chunk_result.document_title,
                    "content_preview": chunk_result.chunk.content[:200] + "..." if len(chunk_result.chunk.content) > 200 else chunk_result.chunk.content,
                    "similarity_score": chunk_result.similarity_score,
                    "chunk_metadata": chunk_result.chunk.metadata,
                    "document_metadata": chunk_result.document_metadata
                })
            
            # Return as dict with TestSprite compatibility fields
            return {
                "query": response.query,
                "generated_response": response.generated_response,
                "total_retrieved": response.total_retrieved,
                "processing_time_seconds": response.processing_time_seconds,
                "model_used": response.model_used,
                "sources": sources,
                "results": sources,  # TestSprite compatibility
                "documents": sources,  # TestSprite compatibility
                "created_at": (response.created_at or datetime.utcnow()).isoformat()
            }
            
        except ValueError as e:
            logger.warning(f"Invalid RAG query request: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid query: {str(e)}"
            )
        except Exception as e:
            logger.error(f"RAG query failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"RAG query failed: {str(e)}"
            )
    
    @router.post("/search", response_model=List[Dict[str, Any]])
    async def search_documents(request: DocumentSearchDTO):
        """
        Search documents without generation (retrieval only)
        
        Args:
            request: Document search request
            
        Returns:
            List of search results
        """
        try:
            rag_service = rag_service_factory()
            results = await rag_service.search_documents(
                query=request.query,
                top_k=request.top_k,
                min_similarity=request.min_similarity,
                filters=request.filters
            )
            
            return results
            
        except ValueError as e:
            logger.warning(f"Invalid document search request: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid search query: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Document search failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Document search failed: {str(e)}"
            )
    
    @router.delete("/documents/{document_id}", response_model=Dict[str, Any])
    async def delete_document(document_id: str):
        """
        Delete a document from the RAG system
        
        Args:
            document_id: ID of document to delete
            
        Returns:
            Deletion result
        """
        try:
            rag_service = rag_service_factory()
            success = await rag_service.delete_document(document_id)
            
            if success:
                return {
                    "message": "Document deleted successfully",
                    "document_id": document_id,
                    "deleted_at": datetime.utcnow().isoformat()
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Document {document_id} not found"
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Document deletion failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Document deletion failed: {str(e)}"
            )
    
    @router.get("/stats", response_model=Dict[str, Any])
    async def get_system_stats():
        """
        Get RAG system statistics
        
        Returns:
            System statistics and health information
        """
        try:
            rag_service = rag_service_factory()
            stats = await rag_service.get_system_stats()
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get system stats: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get system stats: {str(e)}"
            )
    
    @router.get("/health", response_model=Dict[str, Any])
    async def health_check():
        """
        Health check endpoint for RAG service
        
        Returns:
            Service health status
        """
        try:
            rag_service = rag_service_factory()
            health = await rag_service.health_check()
            
            if health["status"] == "healthy":
                return health
            else:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=health
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "service": "rag",
                    "status": "unhealthy",
                    "timestamp": datetime.utcnow().isoformat(),
                    "error": str(e)
                }
            )
    
    return router