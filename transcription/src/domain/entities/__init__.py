"""
Domain entities for transcription service
"""

from .transcription import AudioFile, Transcription, TranscriptionRequest

__all__ = [
    "AudioFile",
    "Transcription", 
    "TranscriptionRequest"
]