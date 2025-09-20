"""
Use case for transcribing audio files
"""

from typing import Optional
import time
from datetime import datetime

from shared.src.utils.logging import get_logger

from ...domain.entities.transcription import AudioFile, Transcription, TranscriptionRequest
from ...domain.protocols.transcription_service import (
    TranscriptionServiceProtocol,
    CacheServiceProtocol,
    FileServiceProtocol
)


logger = get_logger("transcription.use_cases")


class TranscribeAudioUseCase:
    """Use case for transcribing audio files"""
    
    def __init__(
        self,
        transcription_service: TranscriptionServiceProtocol,
        cache_service: CacheServiceProtocol,
        file_service: FileServiceProtocol
    ):
        self.transcription_service = transcription_service
        self.cache_service = cache_service
        self.file_service = file_service
    
    async def execute(
        self,
        file_content: bytes,
        filename: str,
        content_type: str,
        language: Optional[str] = None,
        use_cache: bool = True
    ) -> Transcription:
        """
        Execute audio transcription
        
        Args:
            file_content: Audio file bytes
            filename: Original filename
            content_type: MIME content type
            language: Target language (optional)
            use_cache: Whether to use cache
            
        Returns:
            Transcription result
            
        Raises:
            ValueError: If audio file is invalid
            RuntimeError: If transcription fails
        """
        start_time = time.time()
        
        try:
            # Create audio file entity
            audio_file = AudioFile(
                filename=filename,
                content_type=content_type,
                size_bytes=len(file_content)
            )
            
            # Validate audio file
            if not audio_file.is_valid_audio():
                raise ValueError(f"Unsupported audio format: {content_type}")
            
            if audio_file.is_too_large():
                raise ValueError("Audio file too large (max 25MB)")
            
            # Create transcription request
            request = TranscriptionRequest(
                audio_file=audio_file,
                language=language
            )
            
            cache_key = request.generate_cache_key()
            
            # Check cache first
            if use_cache:
                cached_result = await self.cache_service.get_cached_transcription(cache_key)
                if cached_result:
                    logger.info(f"Cache hit for transcription: {filename}")
                    return cached_result
            
            # Save temporary file
            temp_file_path = await self.file_service.save_temp_file(
                file_content, 
                filename
            )
            
            try:
                # Get file info (duration, etc.)
                file_info = await self.file_service.get_file_info(temp_file_path)
                audio_file.duration_seconds = file_info.get("duration")
                
                # Perform transcription
                logger.info(f"Starting transcription for: {filename}")
                transcription = await self.transcription_service.transcribe_audio(
                    request,
                    temp_file_path
                )
                
                # Set processing metadata
                processing_time = time.time() - start_time
                transcription.processing_time_seconds = processing_time
                transcription.created_at = datetime.utcnow()
                transcription.audio_filename = filename
                transcription.duration_seconds = audio_file.duration_seconds
                
                # Cache successful result
                if use_cache and transcription.is_valid():
                    await self.cache_service.cache_transcription(
                        cache_key,
                        transcription,
                        ttl_seconds=3600
                    )
                
                logger.info(
                    f"Transcription completed for {filename}. "
                    f"Length: {len(transcription.text or '')} chars, "
                    f"Confidence: {transcription.confidence}, "
                    f"Processing time: {processing_time:.2f}s"
                )
                
                return transcription
                
            finally:
                # Always cleanup temp file
                await self.file_service.cleanup_temp_file(temp_file_path)
                
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(
                f"Transcription failed for {filename}: {str(e)}. "
                f"Processing time: {processing_time:.2f}s"
            )
            raise RuntimeError(f"Transcription failed: {str(e)}") from e