"""
Domain entities for RAG service
"""

from .document import (
    Document,
    DocumentChunk,
    DocumentType,
    DocumentStatus,
    SearchQuery,
    SearchResult,
    RAGResponse,
    DocumentIngestRequest
)

__all__ = [
    "Document",
    "DocumentChunk",
    "DocumentType", 
    "DocumentStatus",
    "SearchQuery",
    "SearchResult",
    "RAGResponse",
    "DocumentIngestRequest"
]