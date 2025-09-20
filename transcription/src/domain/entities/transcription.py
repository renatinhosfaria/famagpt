"""
Domain entities for transcription service
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class AudioFile:
    """Audio file entity"""
    filename: str
    content_type: str
    size_bytes: int
    duration_seconds: Optional[float] = None
    
    def is_valid_audio(self) -> bool:
        """Check if file is valid audio format"""
        valid_types = [
            "audio/mpeg",
            "audio/wav", 
            "audio/ogg",
            "audio/m4a",
            "audio/mp3",
            "audio/webm"
        ]
        return self.content_type in valid_types
    
    def is_too_large(self, max_size_mb: int = 25) -> bool:
        """Check if file exceeds size limit"""
        max_bytes = max_size_mb * 1024 * 1024
        return self.size_bytes > max_bytes


@dataclass  
class Transcription:
    """Transcription result entity"""
    id: Optional[str] = None
    audio_filename: Optional[str] = None
    text: Optional[str] = None
    language: Optional[str] = None
    confidence: Optional[float] = None
    duration_seconds: Optional[float] = None
    processing_time_seconds: Optional[float] = None
    model_used: Optional[str] = None
    created_at: Optional[datetime] = None
    
    def is_high_confidence(self, threshold: float = 0.8) -> bool:
        """Check if transcription has high confidence"""
        return self.confidence is not None and self.confidence >= threshold
    
    def is_valid(self) -> bool:
        """Check if transcription result is valid"""
        return (
            self.text is not None and 
            len(self.text.strip()) > 0 and
            self.confidence is not None and
            self.confidence > 0
        )


@dataclass
class TranscriptionRequest:
    """Request for audio transcription"""
    audio_file: AudioFile
    language: Optional[str] = None
    model: Optional[str] = None
    cache_key: Optional[str] = None
    
    def generate_cache_key(self) -> str:
        """Generate cache key for this request"""
        if self.cache_key:
            return self.cache_key
        
        import hashlib
        key_parts = [
            self.audio_file.filename,
            str(self.audio_file.size_bytes),
            self.language or "auto",
            self.model or "whisper-1"
        ]
        key_string = "|".join(key_parts)
        hash_key = hashlib.md5(key_string.encode()).hexdigest()
        return f"transcription:{hash_key}"