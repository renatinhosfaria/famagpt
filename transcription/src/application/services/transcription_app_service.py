"""
Application service for transcription operations
"""

from typing import Optional

from shared.src.utils.logging import get_logger

from ...domain.entities.transcription import Transcription
from ..use_cases.transcribe_audio import TranscribeAudioUseCase


logger = get_logger("transcription.app_service")


class TranscriptionAppService:
    """Application service for transcription operations"""
    
    def __init__(self, transcribe_audio_use_case: TranscribeAudioUseCase):
        self.transcribe_audio_use_case = transcribe_audio_use_case
    
    async def transcribe_audio_file(
        self,
        file_content: bytes,
        filename: str,
        content_type: str,
        language: Optional[str] = None,
        use_cache: bool = True
    ) -> Transcription:
        """
        Transcribe audio file to text
        
        Args:
            file_content: Audio file bytes
            filename: Original filename  
            content_type: MIME content type
            language: Target language (optional, defaults to auto-detect)
            use_cache: Whether to use cache (default: True)
            
        Returns:
            Transcription result
            
        Raises:
            ValueError: If input parameters are invalid
            RuntimeError: If transcription fails
        """
        # Input validation
        if not file_content:
            raise ValueError("File content cannot be empty")
        
        if not filename:
            raise ValueError("Filename cannot be empty")
        
        if not content_type:
            raise ValueError("Content type cannot be empty")
        
        # Set default language
        if not language:
            language = "pt"  # Portuguese by default for Brazilian market
        
        logger.info(f"Processing transcription request for {filename}")
        
        # Execute use case
        result = await self.transcribe_audio_use_case.execute(
            file_content=file_content,
            filename=filename,
            content_type=content_type,
            language=language,
            use_cache=use_cache
        )
        
        return result
    
    async def get_service_info(self) -> dict:
        """Get transcription service information"""
        supported_formats = await self.transcribe_audio_use_case.transcription_service.get_supported_formats()
        max_file_size = await self.transcribe_audio_use_case.transcription_service.get_max_file_size_mb()
        
        return {
            "service": "transcription",
            "supported_formats": supported_formats,
            "max_file_size_mb": max_file_size,
            "default_language": "pt",
            "cache_enabled": True,
            "cache_ttl_seconds": 3600
        }