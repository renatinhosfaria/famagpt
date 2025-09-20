"""
Database client for Transcription service to integrate with central database service.
"""
import json
from typing import Dict, Any, Optional, List
from datetime import datetime

from shared.src.infrastructure.http_client import ServiceClient
from shared.src.utils.logging import get_logger


class DatabaseClient:
    """HTTP client for central Database service integration."""
    
    def __init__(self, database_service_url: str):
        self.client = ServiceClient("transcription", database_service_url)
        self.logger = get_logger("transcription_database_client")
    
    async def __aenter__(self):
        await self.client.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.close()
    
    async def save_transcription_record(
        self,
        user_id: str,
        conversation_id: Optional[str],
        audio_file_name: str,
        transcription_text: str,
        confidence_score: Optional[float] = None,
        language: Optional[str] = None,
        duration_seconds: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Save transcription record to central database."""
        try:
            # Store as a special type of message with transcription metadata
            message_data = {
                "conversation_id": conversation_id or f"audio_{user_id}",
                "user_id": user_id,
                "content": transcription_text,
                "message_type": "audio_transcription",
                "status": "processed",
                "metadata": {
                    "audio_file": audio_file_name,
                    "transcription": {
                        "confidence_score": confidence_score,
                        "language": language or "pt",
                        "duration_seconds": duration_seconds,
                        "service": "whisper",
                        "processed_at": datetime.utcnow().isoformat()
                    },
                    "source": "transcription_service",
                    **(metadata or {})
                },
                "attachments": [
                    {
                        "type": "audio",
                        "filename": audio_file_name,
                        "metadata": {
                            "duration": duration_seconds,
                            "language": language
                        }
                    }
                ]
            }
            
            response = await self.client.post("/messages", json_data=message_data)
            
            if response.get("status") == "success":
                self.logger.info(f"Transcription record saved for user {user_id}")
                return True
            else:
                self.logger.warning(f"Failed to save transcription record: {response}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error saving transcription record: {str(e)}")
            return False
    
    async def get_user_transcription_history(
        self, 
        user_id: str, 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get user transcription history."""
        try:
            # Search for transcription messages
            search_data = {
                "user_id": user_id,
                "message_type": "audio_transcription",
                "limit": limit,
                "order_by": "created_at",
                "order_direction": "desc"
            }
            
            response = await self.client.post("/messages/search", json_data=search_data)
            
            if response.get("status") == "success":
                return response.get("messages", [])
            else:
                self.logger.warning(f"Failed to get transcription history: {response}")
                return []
                
        except Exception as e:
            self.logger.error(f"Error getting transcription history for user {user_id}: {str(e)}")
            return []
    
    async def get_transcription_stats(self) -> Dict[str, Any]:
        """Get transcription service statistics."""
        try:
            # Get message stats for transcriptions
            response = await self.client.get("/messages/stats", params={
                "message_type": "audio_transcription"
            })
            
            if response.get("status") == "success":
                return response.get("stats", {})
            else:
                return {"error": "Failed to get stats from database"}
                
        except Exception as e:
            self.logger.error(f"Error getting transcription stats: {str(e)}")
            return {"error": str(e)}
    
    async def search_transcriptions_by_content(
        self, 
        query: str, 
        user_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search transcriptions by content."""
        try:
            search_data = {
                "query": query,
                "message_type": "audio_transcription",
                "limit": limit
            }
            
            if user_id:
                search_data["user_id"] = user_id
            
            response = await self.client.post("/messages/search", json_data=search_data)
            
            if response.get("status") == "success":
                return response.get("messages", [])
            else:
                self.logger.warning(f"Failed to search transcriptions: {response}")
                return []
                
        except Exception as e:
            self.logger.error(f"Error searching transcriptions: {str(e)}")
            return []
    
    async def update_transcription_confidence(
        self, 
        message_id: str, 
        confidence_score: float
    ) -> bool:
        """Update transcription confidence score."""
        try:
            update_data = {
                "metadata": {
                    "transcription": {
                        "confidence_score": confidence_score,
                        "updated_at": datetime.utcnow().isoformat()
                    }
                }
            }
            
            response = await self.client.patch(f"/messages/{message_id}", json_data=update_data)
            return response.get("status") == "success"
                
        except Exception as e:
            self.logger.error(f"Error updating transcription confidence: {str(e)}")
            return False