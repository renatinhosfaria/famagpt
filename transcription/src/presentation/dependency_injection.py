"""
Dependency injection configuration for transcription service
"""

from shared.src.infrastructure.redis_client import RedisClient
from shared.src.utils.config import get_settings

from ..application.services.transcription_app_service import TranscriptionAppService
from ..application.use_cases.transcribe_audio import TranscribeAudioUseCase

from ..infrastructure.services.openai_transcription_service import OpenAITranscriptionService
from ..infrastructure.services.redis_cache_service import RedisCacheService
from ..infrastructure.services.file_service import FileService


class DependencyContainer:
    """Container for dependency injection"""
    
    def __init__(self):
        self.settings = get_settings()
        self._redis_client = None
        self._transcription_service = None
        self._cache_service = None
        self._file_service = None
        self._transcribe_use_case = None
        self._app_service = None
    
    def get_redis_client(self) -> RedisClient:
        """Get Redis client instance"""
        if self._redis_client is None:
            self._redis_client = RedisClient(self.settings.redis)
        return self._redis_client
    
    def get_transcription_service(self) -> OpenAITranscriptionService:
        """Get transcription service instance"""
        if self._transcription_service is None:
            self._transcription_service = OpenAITranscriptionService()
        return self._transcription_service
    
    def get_cache_service(self) -> RedisCacheService:
        """Get cache service instance"""
        if self._cache_service is None:
            redis_client = self.get_redis_client()
            self._cache_service = RedisCacheService(redis_client)
        return self._cache_service
    
    def get_file_service(self) -> FileService:
        """Get file service instance"""
        if self._file_service is None:
            self._file_service = FileService()
        return self._file_service
    
    def get_transcribe_use_case(self) -> TranscribeAudioUseCase:
        """Get transcribe audio use case instance"""
        if self._transcribe_use_case is None:
            self._transcribe_use_case = TranscribeAudioUseCase(
                transcription_service=self.get_transcription_service(),
                cache_service=self.get_cache_service(),
                file_service=self.get_file_service()
            )
        return self._transcribe_use_case
    
    def get_app_service(self) -> TranscriptionAppService:
        """Get application service instance"""
        if self._app_service is None:
            transcribe_use_case = self.get_transcribe_use_case()
            self._app_service = TranscriptionAppService(transcribe_use_case)
        return self._app_service
    
    async def initialize(self):
        """Initialize async dependencies"""
        redis_client = self.get_redis_client()
        await redis_client.connect()
    
    async def cleanup(self):
        """Cleanup resources"""
        if self._redis_client:
            await self._redis_client.disconnect()


# Global container instance
_container = None


def get_container() -> DependencyContainer:
    """Get global dependency container"""
    global _container
    if _container is None:
        _container = DependencyContainer()
    return _container