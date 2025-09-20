"""
Database client for RAG service to integrate with central database service.
"""
import json
from typing import Dict, Any, Optional, List
from datetime import datetime

from shared.src.infrastructure.http_client import ServiceClient
from shared.src.utils.logging import get_logger

from ...domain.entities.document import Document, DocumentStatus, DocumentType


class DatabaseClient:
    """HTTP client for central Database service integration."""
    
    def __init__(self, database_service_url: str):
        self.client = ServiceClient("rag", database_service_url)
        self.logger = get_logger("rag_database_client")
    
    async def __aenter__(self):
        await self.client.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.close()
    
    async def store_document_metadata(self, document: Document) -> bool:
        """Store document metadata in central database."""
        try:
            document_data = {
                "title": document.title,
                "content": document.content[:5000],  # Truncate for metadata
                "source": document.source_url or "rag_service",
                "document_type": "knowledge_base",
                "metadata": {
                    **document.metadata,
                    "rag_document_id": document.id,
                    "document_type": document.document_type.value if document.document_type else "text",
                    "status": document.status.value if document.status else "pending",
                    "chunk_count": len(document.chunks) if document.chunks else 0,
                    "created_via": "rag_service",
                    "processed_at": document.processed_at.isoformat() if document.processed_at else None
                }
            }
            
            response = await self.client.post("/documents", json_data=document_data)
            
            if response.get("status") == "success":
                self.logger.info(f"Document metadata stored: {document.id}")
                return True
            else:
                self.logger.warning(f"Failed to store document metadata: {response}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error storing document metadata {document.id}: {str(e)}")
            return False
    
    async def search_documents(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search documents in central database."""
        try:
            search_data = {
                "query": query,
                "document_type": "knowledge_base",
                "limit": limit
            }
            
            response = await self.client.post("/documents/search", json_data=search_data)
            
            if response.get("status") == "success":
                return response.get("documents", [])
            else:
                self.logger.warning(f"Document search failed: {response}")
                return []
                
        except Exception as e:
            self.logger.error(f"Error searching documents: {str(e)}")
            return []
    
    async def update_document_status(self, document_id: str, status: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Update document processing status."""
        try:
            update_data = {
                "metadata": {
                    "status": status,
                    "updated_at": datetime.utcnow().isoformat(),
                    **(metadata or {})
                }
            }
            
            # Find document by RAG document ID in metadata
            search_response = await self.client.post("/documents/search", json_data={
                "query": document_id,
                "document_type": "knowledge_base",
                "limit": 1,
                "metadata_filter": {"rag_document_id": document_id}
            })
            
            if search_response.get("status") == "success":
                documents = search_response.get("documents", [])
                if documents:
                    doc_id = documents[0].get("id")
                    response = await self.client.patch(f"/documents/{doc_id}", json_data=update_data)
                    return response.get("status") == "success"
            
            return False
                
        except Exception as e:
            self.logger.error(f"Error updating document status {document_id}: {str(e)}")
            return False
    
    async def delete_document_metadata(self, document_id: str) -> bool:
        """Delete document metadata from central database."""
        try:
            # Find and delete by RAG document ID
            search_response = await self.client.post("/documents/search", json_data={
                "query": document_id,
                "document_type": "knowledge_base", 
                "limit": 1,
                "metadata_filter": {"rag_document_id": document_id}
            })
            
            if search_response.get("status") == "success":
                documents = search_response.get("documents", [])
                if documents:
                    doc_id = documents[0].get("id")
                    response = await self.client.delete(f"/documents/{doc_id}")
                    return response.get("status") == "success"
            
            return False
                
        except Exception as e:
            self.logger.error(f"Error deleting document metadata {document_id}: {str(e)}")
            return False
    
    async def get_document_stats(self) -> Dict[str, Any]:
        """Get RAG document statistics from central database."""
        try:
            response = await self.client.get("/documents/stats", params={
                "document_type": "knowledge_base",
                "source": "rag_service"
            })
            
            if response.get("status") == "success":
                return response.get("stats", {})
            else:
                return {"error": "Failed to get stats from database"}
                
        except Exception as e:
            self.logger.error(f"Error getting document stats: {str(e)}")
            return {"error": str(e)}