"""
Domain protocols for transcription service
"""

from .transcription_service import (
    TranscriptionServiceProtocol,
    CacheServiceProtocol,
    FileServiceProtocol
)

__all__ = [
    "TranscriptionServiceProtocol",
    "CacheServiceProtocol", 
    "FileServiceProtocol"
]