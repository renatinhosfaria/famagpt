"""
Endpoints de administração de Dead Letter Queue (DLQ)
Interface REST para gerenciamento de mensagens falhadas
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
import os

from shared.queue.dlq_manager import DLQManager
from shared.logging.structured_logger import get_logger

logger = get_logger(__name__)
security = HTTPBearer()

# Pydantic models
class DLQMessage(BaseModel):
    """DLQ message response model"""
    id: str
    message: dict
    error: str
    failed_at: str
    retry_count: int
    original_queue: str
    original_message_id: str
    message_type: str
    source: str

class DLQStats(BaseModel):
    """DLQ statistics response model"""
    queue: str
    total_failed: int
    current_size: int
    reprocessed: int
    purged: int
    oldest_message: Optional[str]
    newest_message: Optional[str]
    error_categories: dict

class ReprocessRequest(BaseModel):
    """Reprocess request model"""
    message_ids: List[str] = Field(..., description="List of message IDs to reprocess")
    target_queue: Optional[str] = Field(None, description="Target queue (defaults to original)")
    reset_retry_count: bool = Field(True, description="Whether to reset retry count")

class BulkOperationResponse(BaseModel):
    """Bulk operation response model"""
    success_count: int
    failure_count: int
    results: dict

def verify_admin_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify admin authorization token"""
    expected_token = os.getenv("DLQ_ADMIN_TOKEN")
    if not expected_token:
        raise HTTPException(
            status_code=501, 
            detail="DLQ admin functionality not configured"
        )
    
    if credentials.credentials != expected_token:
        raise HTTPException(
            status_code=403,
            detail="Invalid admin token"
        )
    
    return credentials

# Initialize DLQ manager
dlq_manager = DLQManager(os.getenv("REDIS_URL", "redis://localhost:6379"))

# Create router
router = APIRouter(
    prefix="/admin/dlq",
    tags=["DLQ Administration"],
    dependencies=[Depends(verify_admin_token)]
)

@router.get("/queues")
async def list_dlq_queues():
    """List all available DLQ queues"""
    try:
        # This would need to be implemented in DLQManager
        # For now, return known queues
        known_queues = ["messages:stream", "transcription:stream", "processing:stream"]
        
        queue_info = []
        for queue_name in known_queues:
            try:
                stats = await dlq_manager.get_dlq_stats(queue_name)
                if stats.get("current_size", 0) > 0 or stats.get("total_failed", 0) > 0:
                    queue_info.append(stats)
            except Exception as e:
                logger.error(f"Error getting stats for queue {queue_name}: {e}")
        
        return {
            "queues": queue_info,
            "total_queues": len(queue_info)
        }
        
    except Exception as e:
        logger.error(f"Error listing DLQ queues: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/messages/{queue_name}", response_model=List[DLQMessage])
async def get_dlq_messages(
    queue_name: str,
    limit: int = Query(100, le=1000, description="Maximum messages to return"),
    start_time: Optional[datetime] = Query(None, description="Filter by start time"),
    end_time: Optional[datetime] = Query(None, description="Filter by end time"),
    message_type: Optional[str] = Query(None, description="Filter by message type"),
    error_category: Optional[str] = Query(None, description="Filter by error category")
):
    """Get messages from DLQ with filtering options"""
    try:
        messages = await dlq_manager.get_dlq_messages(
            queue_name=queue_name,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
            message_type=message_type,
            error_category=error_category
        )
        
        logger.info(
            f"Retrieved {len(messages)} DLQ messages",
            queue_name=queue_name,
            filters={
                "limit": limit,
                "start_time": start_time,
                "end_time": end_time,
                "message_type": message_type,
                "error_category": error_category
            }
        )
        
        return messages
        
    except Exception as e:
        logger.error(f"Error getting DLQ messages for {queue_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reprocess/{queue_name}/{message_id}")
async def reprocess_single_message(
    queue_name: str,
    message_id: str,
    target_queue: Optional[str] = Query(None, description="Target queue"),
    reset_retry_count: bool = Query(True, description="Reset retry count")
):
    """Reprocess a single message from DLQ"""
    try:
        success = await dlq_manager.reprocess_dlq_message(
            queue_name=queue_name,
            message_id=message_id,
            target_queue=target_queue,
            reset_retry_count=reset_retry_count
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Message not found")
        
        logger.info(
            "Message reprocessed from DLQ",
            queue_name=queue_name,
            message_id=message_id,
            target_queue=target_queue
        )
        
        return {
            "status": "success",
            "message": "Message reprocessed successfully",
            "queue_name": queue_name,
            "message_id": message_id,
            "target_queue": target_queue or queue_name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error reprocessing message {message_id} from {queue_name}: {e}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reprocess/{queue_name}/bulk", response_model=BulkOperationResponse)
async def reprocess_bulk_messages(
    queue_name: str,
    request: ReprocessRequest
):
    """Reprocess multiple messages from DLQ"""
    try:
        results = await dlq_manager.bulk_reprocess(
            queue_name=queue_name,
            message_ids=request.message_ids,
            target_queue=request.target_queue
        )
        
        success_count = sum(1 for success in results.values() if success)
        failure_count = len(results) - success_count
        
        logger.info(
            f"Bulk reprocess completed",
            queue_name=queue_name,
            total_messages=len(request.message_ids),
            success_count=success_count,
            failure_count=failure_count
        )
        
        return BulkOperationResponse(
            success_count=success_count,
            failure_count=failure_count,
            results=results
        )
        
    except Exception as e:
        logger.error(f"Error bulk reprocessing messages from {queue_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/purge/{queue_name}")
async def purge_old_messages(
    queue_name: str,
    older_than_days: int = Query(7, ge=1, le=365, description="Purge messages older than N days")
):
    """Purge old messages from DLQ"""
    try:
        count = await dlq_manager.purge_old_dlq_messages(
            queue_name=queue_name,
            older_than_days=older_than_days
        )
        
        logger.info(
            f"Purged {count} old messages from DLQ",
            queue_name=queue_name,
            older_than_days=older_than_days
        )
        
        return {
            "status": "success",
            "message": f"Purged {count} messages older than {older_than_days} days",
            "queue_name": queue_name,
            "purged_count": count
        }
        
    except Exception as e:
        logger.error(f"Error purging old messages from {queue_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats/{queue_name}", response_model=DLQStats)
async def get_dlq_stats(queue_name: str):
    """Get comprehensive DLQ statistics"""
    try:
        stats = await dlq_manager.get_dlq_stats(queue_name)
        
        if "error" in stats:
            raise HTTPException(status_code=500, detail=stats["error"])
        
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting DLQ stats for {queue_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analysis/{queue_name}")
async def get_failure_analysis(
    queue_name: str,
    hours_back: int = Query(24, ge=1, le=168, description="Analysis period in hours")
):
    """Get failure pattern analysis for DLQ"""
    try:
        analysis = await dlq_manager.analyze_failure_patterns(
            queue_name=queue_name,
            hours_back=hours_back
        )
        
        logger.info(
            f"Generated failure analysis for {queue_name}",
            hours_back=hours_back,
            total_failures=analysis.get("total_failures", 0)
        )
        
        return analysis
        
    except Exception as e:
        logger.error(f"Error analyzing failures for {queue_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/search/{queue_name}")
async def search_dlq_messages(
    queue_name: str,
    search_term: str = Query(..., description="Search term"),
    limit: int = Query(100, le=1000)
):
    """Search messages in DLQ by content or error"""
    try:
        # Get recent messages
        messages = await dlq_manager.get_dlq_messages(queue_name, limit=limit * 2)
        
        # Filter by search term
        search_lower = search_term.lower()
        matching_messages = []
        
        for msg in messages:
            # Search in message content
            if search_lower in str(msg.get("message", {})).lower():
                matching_messages.append(msg)
                continue
            
            # Search in error message
            if search_lower in msg.get("error", "").lower():
                matching_messages.append(msg)
                continue
            
            if len(matching_messages) >= limit:
                break
        
        logger.info(
            f"DLQ search completed",
            queue_name=queue_name,
            search_term=search_term,
            results_count=len(matching_messages)
        )
        
        return {
            "search_term": search_term,
            "results_count": len(matching_messages),
            "messages": matching_messages[:limit]
        }
        
    except Exception as e:
        logger.error(f"Error searching DLQ messages in {queue_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def dlq_health_check():
    """Health check for DLQ system"""
    try:
        health = await dlq_manager.health_check()
        return health
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

# Export router
__all__ = ['router']