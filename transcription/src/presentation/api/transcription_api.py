"""
FastAPI routes for transcription service
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Query, Depends
from pydantic import BaseModel
from typing import Optional
import datetime
import aiohttp

from shared.src.utils.logging import get_logger

from ...application.services.transcription_app_service import TranscriptionAppService
from ...domain.entities.transcription import Transcription


logger = get_logger("transcription.api")


class TranscriptionResponse(BaseModel):
    """Response model for transcription"""
    text: str
    language: str
    confidence: float
    duration_seconds: Optional[float] = None
    processing_time_seconds: Optional[float] = None
    model_used: Optional[str] = None
    created_at: Optional[datetime.datetime] = None
    
    class Config:
        from_attributes = True


class ServiceInfoResponse(BaseModel):
    """Response model for service information"""
    service: str
    supported_formats: list[str]
    max_file_size_mb: int
    default_language: str
    cache_enabled: bool
    cache_ttl_seconds: int


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    timestamp: str
    dependencies: dict


def create_transcription_router(app_service: TranscriptionAppService) -> APIRouter:
    """Create transcription API router"""
    
    router = APIRouter(prefix="/transcription", tags=["transcription"])

    class TranscribeURLRequest(BaseModel):
        """Request model for URL-based transcription"""
        audio_url: str
        content_type: Optional[str] = None
        language: Optional[str] = None
        use_cache: bool = True
    
    @router.post("/transcribe", response_model=TranscriptionResponse)
    async def transcribe_audio(
        file: UploadFile = File(...),
        language: Optional[str] = Query(None, description="Target language (e.g., 'pt', 'en')"),
        use_cache: bool = Query(True, description="Whether to use cache")
    ):
        """
        Transcribe audio file to text
        
        Args:
            file: Audio file to transcribe
            language: Target language (optional, defaults to Portuguese)
            use_cache: Whether to use cache for results
            
        Returns:
            Transcription result with text and metadata
        """
        try:
            # Validate file
            if not file.filename:
                raise HTTPException(
                    status_code=400, 
                    detail="Filename is required"
                )
            
            if not file.content_type:
                raise HTTPException(
                    status_code=400,
                    detail="Content type is required"
                )
            
            # Read file content
            file_content = await file.read()
            
            if not file_content:
                raise HTTPException(
                    status_code=400,
                    detail="File content cannot be empty"
                )
            
            logger.info(
                f"Received transcription request: {file.filename}, "
                f"size: {len(file_content)} bytes, "
                f"type: {file.content_type}, "
                f"language: {language or 'auto'}"
            )
            
            # Process transcription
            transcription = await app_service.transcribe_audio_file(
                file_content=file_content,
                filename=file.filename,
                content_type=file.content_type,
                language=language,
                use_cache=use_cache
            )
            
            # Convert to response model
            response = TranscriptionResponse(
                text=transcription.text or "",
                language=transcription.language or "unknown",
                confidence=transcription.confidence or 0.0,
                duration_seconds=transcription.duration_seconds,
                processing_time_seconds=transcription.processing_time_seconds,
                model_used=transcription.model_used,
                created_at=transcription.created_at
            )
            
            logger.info(
                f"Transcription completed for {file.filename}: "
                f"{len(response.text)} characters, "
                f"confidence: {response.confidence:.2f}"
            )
            
            return response
            
        except ValueError as e:
            logger.warning(f"Invalid transcription request: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))
        
        except RuntimeError as e:
            logger.error(f"Transcription processing error: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
        
        except Exception as e:
            logger.error(f"Unexpected error in transcription: {str(e)}")
            raise HTTPException(
                status_code=500, 
                detail="Internal server error during transcription"
            )

    @router.post("/transcribe_url", response_model=TranscriptionResponse)
    async def transcribe_audio_url(request: TranscribeURLRequest):
        """Transcribe audio from a remote URL (no multipart upload)."""
        try:
            if not request.audio_url:
                raise HTTPException(status_code=400, detail="audio_url is required")

            logger.info(f"Fetching audio from URL: {request.audio_url}")

            # Download audio bytes
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(request.audio_url) as resp:
                    if resp.status != 200:
                        raise HTTPException(status_code=502, detail=f"Failed to fetch audio: HTTP {resp.status}")
                    content = await resp.read()
                    content_type = request.content_type or resp.headers.get("Content-Type") or "audio/mpeg"

            # Derive filename
            import os, mimetypes, urllib.parse
            path = urllib.parse.urlparse(request.audio_url).path
            name = os.path.basename(path) or "audio"
            if not os.path.splitext(name)[1]:
                ext = mimetypes.guess_extension(content_type) or ".mp3"
                name = f"{name}{ext}"

            # Process transcription
            transcription = await app_service.transcribe_audio_file(
                file_content=content,
                filename=name,
                content_type=content_type,
                language=request.language,
                use_cache=request.use_cache,
            )

            response = TranscriptionResponse(
                text=transcription.text or "",
                language=transcription.language or "unknown",
                confidence=transcription.confidence or 0.0,
                duration_seconds=transcription.duration_seconds,
                processing_time_seconds=transcription.processing_time_seconds,
                model_used=transcription.model_used,
                created_at=transcription.created_at
            )

            logger.info(
                f"URL transcription completed: {len(response.text)} chars, confidence {response.confidence:.2f}"
            )

            return response

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in URL transcription: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal server error during URL transcription")
    
    @router.get("/info", response_model=ServiceInfoResponse)
    async def get_service_info():
        """Get transcription service information and capabilities"""
        try:
            info = await app_service.get_service_info()
            return ServiceInfoResponse(**info)
            
        except Exception as e:
            logger.error(f"Error getting service info: {str(e)}")
            raise HTTPException(status_code=500, detail="Could not retrieve service info")
    
    @router.get("/health", response_model=HealthResponse)
    async def health_check():
        """Health check endpoint with dependency status"""
        try:
            # Basic health check
            health_status = {
                "status": "healthy",
                "service": "transcription",
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "dependencies": {
                    "openai_api": "unknown",  # Would need actual check
                    "redis": "unknown",       # Would need actual check
                    "file_system": "healthy"
                }
            }
            
            return HealthResponse(**health_status)
            
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            raise HTTPException(status_code=503, detail="Service unhealthy")
    
    return router
