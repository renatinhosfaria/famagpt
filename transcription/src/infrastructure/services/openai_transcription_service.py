"""
OpenAI Whisper transcription service implementation
"""

import asyncio
from typing import Optional
import time
from openai import AsyncOpenAI

from shared.src.utils.logging import get_logger
from shared.src.utils.config import get_settings

from ...domain.entities.transcription import Transcription, TranscriptionRequest
from ...domain.protocols.transcription_service import TranscriptionServiceProtocol


logger = get_logger("transcription.openai_service")
settings = get_settings()


class OpenAITranscriptionService(TranscriptionServiceProtocol):
    """OpenAI Whisper transcription service implementation"""
    
    def __init__(self):
        # Use nested AI settings for API key
        self.client = AsyncOpenAI(api_key=settings.ai.openai_api_key)
        self.model = "whisper-1"
        self.supported_formats = [
            "audio/mpeg",
            "audio/mp3", 
            "audio/wav",
            "audio/m4a",
            "audio/ogg",
            "audio/webm"
        ]
        self.max_file_size_mb = 25
    
    async def transcribe_audio(
        self,
        request: TranscriptionRequest,
        temp_file_path: str
    ) -> Transcription:
        """
        Transcribe audio using OpenAI Whisper
        
        Args:
            request: Transcription request
            temp_file_path: Path to temporary audio file
            
        Returns:
            Transcription result
        """
        start_time = time.time()
        
        try:
            logger.info(f"Starting OpenAI Whisper transcription for: {request.audio_file.filename}")
            
            # Open audio file
            with open(temp_file_path, "rb") as audio_file:
                # Call OpenAI Whisper API
                response = await self.client.audio.transcriptions.create(
                    model=self.model,
                    file=audio_file,
                    language=request.language,
                    response_format="verbose_json",  # Get detailed response with confidence
                    temperature=0.0  # Deterministic output
                )
            
            # Extract transcription details
            transcription_text = response.text
            language = getattr(response, 'language', request.language or 'pt')
            
            # Calculate confidence (Whisper doesn't always provide this)
            # We'll use a heuristic based on response quality
            confidence = self._estimate_confidence(response, transcription_text)
            
            processing_time = time.time() - start_time
            
            logger.info(
                f"OpenAI transcription completed. "
                f"Text length: {len(transcription_text)} chars, "
                f"Language: {language}, "
                f"Processing time: {processing_time:.2f}s"
            )
            
            return Transcription(
                text=transcription_text,
                language=language,
                confidence=confidence,
                processing_time_seconds=processing_time,
                model_used=self.model
            )
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(
                f"OpenAI transcription failed for {request.audio_file.filename}: {str(e)}. "
                f"Processing time: {processing_time:.2f}s"
            )
            raise RuntimeError(f"OpenAI transcription failed: {str(e)}") from e
    
    def _estimate_confidence(self, response, text: str) -> float:
        """
        Estimate confidence score based on response characteristics
        
        Args:
            response: OpenAI API response
            text: Transcribed text
            
        Returns:
            Confidence score between 0 and 1
        """
        try:
            # If response has segments with confidence scores, use average
            if hasattr(response, 'segments') and response.segments:
                confidences = []
                for segment in response.segments:
                    if hasattr(segment, 'avg_logprob'):
                        # Convert log probability to confidence (approximate)
                        conf = max(0.0, min(1.0, (segment.avg_logprob + 1) / 1))
                        confidences.append(conf)
                
                if confidences:
                    return sum(confidences) / len(confidences)
            
            # Fallback heuristic based on text characteristics
            if not text or len(text.strip()) == 0:
                return 0.0
            
            # Simple heuristics for text quality
            base_confidence = 0.85
            
            # Penalize very short transcriptions
            if len(text.strip()) < 10:
                base_confidence -= 0.2
            
            # Penalize texts with many repeated characters (sign of poor quality)
            if self._has_repeated_patterns(text):
                base_confidence -= 0.1
            
            # Bonus for proper Portuguese text patterns
            if self._looks_like_portuguese(text):
                base_confidence += 0.1
            
            return max(0.1, min(1.0, base_confidence))
            
        except Exception as e:
            logger.warning(f"Error estimating confidence: {e}")
            return 0.8  # Default reasonable confidence
    
    def _has_repeated_patterns(self, text: str) -> bool:
        """Check if text has suspicious repeated patterns"""
        if len(text) < 20:
            return False
        
        # Check for repeated substrings
        for i in range(len(text) - 10):
            substr = text[i:i+5]
            if text.count(substr) > 3:
                return True
        
        return False
    
    def _looks_like_portuguese(self, text: str) -> bool:
        """Simple heuristic to check if text looks like Portuguese"""
        portuguese_words = [
            'que', 'não', 'uma', 'com', 'para', 'por', 'são', 'mais',
            'como', 'mas', 'foi', 'ele', 'das', 'tem', 'à', 'seu', 
            'sua', 'ou', 'ser', 'quando', 'muito', 'há', 'nos', 'já',
            'está', 'eu', 'também', 'só', 'pelo', 'pela', 'até', 'isso'
        ]
        
        words = text.lower().split()
        portuguese_count = sum(1 for word in words if word in portuguese_words)
        
        if len(words) == 0:
            return False
            
        return (portuguese_count / len(words)) > 0.1
    
    async def get_supported_formats(self) -> list[str]:
        """Get list of supported audio formats"""
        return self.supported_formats.copy()
    
    async def get_max_file_size_mb(self) -> int:
        """Get maximum file size in MB"""
        return self.max_file_size_mb
