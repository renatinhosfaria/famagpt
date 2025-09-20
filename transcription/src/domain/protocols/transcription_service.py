"""
Domain protocols for transcription service
"""

from abc import ABC, abstractmethod
from typing import Optional

from ..entities.transcription import AudioFile, Transcription, TranscriptionRequest


class TranscriptionServiceProtocol(ABC):
    """Protocol for transcription services"""
    
    @abstractmethod
    async def transcribe_audio(
        self,
        request: TranscriptionRequest,
        temp_file_path: str
    ) -> Transcription:
        """
        Transcribe audio file to text
        
        Args:
            request: Transcription request with audio file info
            temp_file_path: Path to temporary audio file
            
        Returns:
            Transcription result
        """
        pass
    
    @abstractmethod
    async def get_supported_formats(self) -> list[str]:
        """Get list of supported audio formats"""
        pass
    
    @abstractmethod
    async def get_max_file_size_mb(self) -> int:
        """Get maximum file size in MB"""
        pass


class CacheServiceProtocol(ABC):
    """Protocol for caching transcription results"""
    
    @abstractmethod
    async def get_cached_transcription(
        self, 
        cache_key: str
    ) -> Optional[Transcription]:
        """Get cached transcription result"""
        pass
    
    @abstractmethod
    async def cache_transcription(
        self,
        cache_key: str,
        transcription: Transcription,
        ttl_seconds: int = 3600
    ) -> None:
        """Cache transcription result"""
        pass
    
    @abstractmethod
    async def invalidate_cache(self, cache_key: str) -> None:
        """Invalidate cached transcription"""
        pass


class FileServiceProtocol(ABC):
    """Protocol for file handling operations"""
    
    @abstractmethod
    async def save_temp_file(
        self, 
        content: bytes, 
        filename: str
    ) -> str:
        """Save uploaded file to temporary location"""
        pass
    
    @abstractmethod
    async def cleanup_temp_file(self, file_path: str) -> None:
        """Clean up temporary file"""
        pass
    
    @abstractmethod
    async def get_file_info(self, file_path: str) -> dict:
        """Get file information (size, duration, etc.)"""
        pass