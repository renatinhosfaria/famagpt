"""
Domain entities for RAG service - Document management
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum
import hashlib


class DocumentType(Enum):
    """Document types"""
    TEXT = "text"
    PDF = "pdf"
    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"


class DocumentStatus(Enum):
    """Document processing status"""
    PENDING = "pending"
    PROCESSING = "processing" 
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


@dataclass
class DocumentChunk:
    """Document chunk for RAG processing"""
    id: Optional[str] = None
    document_id: Optional[str] = None
    content: Optional[str] = None
    chunk_index: Optional[int] = None
    start_position: Optional[int] = None
    end_position: Optional[int] = None
    embedding: Optional[List[float]] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.created_at is None:
            self.created_at = datetime.utcnow()
    
    def generate_id(self) -> str:
        """Generate unique ID for chunk"""
        if self.document_id and self.chunk_index is not None:
            content_hash = hashlib.md5(
                f"{self.document_id}:{self.chunk_index}:{self.content or ''}".encode()
            ).hexdigest()
            return f"chunk_{content_hash[:8]}"
        return None
    
    def is_valid(self) -> bool:
        """Check if chunk is valid"""
        return (
            self.content is not None and
            len(self.content.strip()) > 0 and
            self.document_id is not None
        )


@dataclass  
class Document:
    """Document entity for RAG system"""
    id: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    document_type: Optional[DocumentType] = DocumentType.TEXT
    source_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    chunks: Optional[List[DocumentChunk]] = None
    status: DocumentStatus = DocumentStatus.PENDING
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.chunks is None:
            self.chunks = []
        if self.created_at is None:
            self.created_at = datetime.utcnow()
    
    def generate_id(self) -> str:
        """Generate unique ID for document"""
        if self.title and self.content:
            content_hash = hashlib.md5(
                f"{self.title}:{self.content[:100]}".encode()
            ).hexdigest()
            return f"doc_{content_hash[:12]}"
        return None
    
    def is_valid(self) -> bool:
        """Check if document is valid"""
        return (
            self.title is not None and 
            len(self.title.strip()) > 0 and
            self.content is not None and
            len(self.content.strip()) > 0
        )
    
    def get_chunk_count(self) -> int:
        """Get number of chunks"""
        return len(self.chunks) if self.chunks else 0
    
    def add_chunk(self, chunk: DocumentChunk) -> None:
        """Add chunk to document"""
        if self.chunks is None:
            self.chunks = []
        chunk.document_id = self.id
        self.chunks.append(chunk)
    
    def get_total_content_length(self) -> int:
        """Get total length of content"""
        return len(self.content) if self.content else 0


@dataclass
class SearchQuery:
    """Search query for RAG retrieval"""
    query: str
    top_k: int = 5
    min_similarity: float = 0.7
    filters: Optional[Dict[str, Any]] = None
    include_metadata: bool = True
    rerank: bool = True
    
    def __post_init__(self):
        if self.filters is None:
            self.filters = {}
    
    def is_valid(self) -> bool:
        """Check if query is valid"""
        return (
            self.query is not None and
            len(self.query.strip()) > 0 and
            self.top_k > 0 and
            0 <= self.min_similarity <= 1
        )


@dataclass
class SearchResult:
    """Search result with relevance scoring"""
    chunk: DocumentChunk
    similarity_score: float
    rerank_score: Optional[float] = None
    document_title: Optional[str] = None
    document_metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.document_metadata is None:
            self.document_metadata = {}
    
    def get_final_score(self) -> float:
        """Get final relevance score"""
        return self.rerank_score if self.rerank_score is not None else self.similarity_score


@dataclass
class RAGResponse:
    """RAG generation response"""
    query: str
    generated_response: str
    retrieved_chunks: List[SearchResult]
    total_retrieved: int
    processing_time_seconds: Optional[float] = None
    model_used: Optional[str] = None
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
    
    def get_source_documents(self) -> List[str]:
        """Get list of source document titles"""
        sources = set()
        for result in self.retrieved_chunks:
            if result.document_title:
                sources.add(result.document_title)
        return list(sources)
    
    def get_average_similarity(self) -> float:
        """Get average similarity score"""
        if not self.retrieved_chunks:
            return 0.0
        
        scores = [result.get_final_score() for result in self.retrieved_chunks]
        return sum(scores) / len(scores)


@dataclass
class DocumentIngestRequest:
    """Request for document ingestion"""
    title: str
    content: str
    document_type: DocumentType = DocumentType.TEXT
    source_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    chunk_size: int = 1000
    chunk_overlap: int = 200
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def is_valid(self) -> bool:
        """Validate ingestion request"""
        return (
            self.title is not None and len(self.title.strip()) > 0 and
            self.content is not None and len(self.content.strip()) > 0 and
            self.chunk_size > 0 and
            self.chunk_overlap >= 0 and
            self.chunk_overlap < self.chunk_size
        )