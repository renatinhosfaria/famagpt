"""
Centralized configuration management.
"""
import os
from typing import Optional, List, Dict, Any
from functools import lru_cache


class DatabaseSettings:
    """Database configuration."""
    
    def __init__(self):
        self.url = os.environ.get("DATABASE_URL", "")
        self.host = os.environ.get("PGHOST", "localhost")
        self.port = int(os.environ.get("PGPORT", "5432"))
        self.database = os.environ.get("PGDATABASE", "famagpt")
        self.username = os.environ.get("PGUSER", "postgres")
        self.password = os.environ.get("PGPASSWORD", "")
        
        # Connection pool settings
        self.pool_size = int(os.environ.get("DB_POOL_SIZE", "10"))
        self.max_overflow = int(os.environ.get("DB_MAX_OVERFLOW", "20"))
        self.pool_timeout = int(os.environ.get("DB_POOL_TIMEOUT", "30"))


class RedisSettings:
    """Redis configuration."""
    
    def __init__(self):
        self.url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        self.password = os.environ.get("REDIS_PASSWORD")
        self.db = int(os.environ.get("REDIS_DB", "0"))
        
        # Connection settings
        self.max_connections = int(os.environ.get("REDIS_MAX_CONNECTIONS", "100"))
        self.retry_on_timeout = os.environ.get("REDIS_RETRY_ON_TIMEOUT", "true").lower() == "true"


class AISettings:
    """AI services configuration."""
    
    def __init__(self):
        self.openai_api_key = os.environ.get("OPENAI_API_KEY")
        self.embedding_model = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
        self.whisper_model = os.environ.get("WHISPER_MODEL", "base")
        
        # LangSmith configuration
        self.langchain_api_key = os.environ.get("LANGCHAIN_API_KEY")
        self.langchain_tracing_v2 = os.environ.get("LANGCHAIN_TRACING_V2", "false").lower() == "true"
        self.langchain_project = os.environ.get("LANGCHAIN_PROJECT", "famagpt-system")


class WhatsAppSettings:
    """WhatsApp/Evolution API configuration."""
    
    def __init__(self):
        self.evolution_api_url = os.environ.get("EVOLUTION_API_URL", "")
        self.evolution_api_key = os.environ.get("EVOLUTION_API_KEY", "")
        self.webhook_secret = os.environ.get("WEBHOOK_SECRET", "")
        self.instance_name = os.environ.get("EVOLUTION_INSTANCE_NAME", "famagpt")


class SecuritySettings:
    """Security configuration."""
    
    def __init__(self):
        self.jwt_secret_key = os.environ.get("JWT_SECRET_KEY", "")
        self.jwt_algorithm = os.environ.get("JWT_ALGORITHM", "HS256")
        self.jwt_access_token_expire_minutes = int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))


class CacheSettings:
    """Cache configuration."""
    
    def __init__(self):
        self.ttl_short = int(os.environ.get("CACHE_TTL_SHORT", "300"))  # 5 minutes
        self.ttl_medium = int(os.environ.get("CACHE_TTL_MEDIUM", "1800"))  # 30 minutes
        self.ttl_long = int(os.environ.get("CACHE_TTL_LONG", "86400"))  # 24 hours


class RateLimitSettings:
    """Rate limiting configuration."""
    
    def __init__(self):
        self.per_minute = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "60"))
        self.per_hour = int(os.environ.get("RATE_LIMIT_PER_HOUR", "1000"))
        self.per_day = int(os.environ.get("RATE_LIMIT_PER_DAY", "10000"))


class FileSettings:
    """File handling configuration."""
    
    def __init__(self):
        self.max_file_size_mb = int(os.environ.get("MAX_FILE_SIZE_MB", "50"))
        audio_formats = os.environ.get("ALLOWED_AUDIO_FORMATS", "mp3,wav,ogg,m4a")
        self.allowed_audio_formats = [fmt.strip() for fmt in audio_formats.split(',')]
        self.temp_dir = os.environ.get("TEMP_DIR", "/tmp/famagpt")


class BusinessSettings:
    """Business logic configuration."""
    
    def __init__(self):
        self.default_city = os.environ.get("DEFAULT_CITY", "Uberlândia")
        self.default_state = os.environ.get("DEFAULT_STATE", "MG")
        self.property_search_radius_km = int(os.environ.get("PROPERTY_SEARCH_RADIUS_KM", "50"))


class ServiceSettings:
    """Individual service configuration."""
    
    def __init__(self):
        self.name = os.environ.get("SERVICE_NAME", "")
        self.port = int(os.environ.get("PORT", "8000"))
        self.host = os.environ.get("HOST", "0.0.0.0")
        
        # Service URLs
        self.orchestrator_url = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8000")
        self.webhooks_url = os.environ.get("WEBHOOKS_URL", "http://webhooks:8001")
        self.transcription_url = os.environ.get("TRANSCRIPTION_URL", "http://transcription:8002")
        self.web_search_url = os.environ.get("WEB_SEARCH_URL", "http://web_search:8003")
        self.memory_url = os.environ.get("MEMORY_URL", "http://memory:8004")
        self.rag_url = os.environ.get("RAG_URL", "http://rag:8005")
        self.database_url = os.environ.get("DATABASE_SERVICE_URL", "http://database:8006")
        self.specialist_url = os.environ.get("SPECIALIST_URL", "http://specialist:8007")


class AppSettings:
    """Main application configuration."""
    
    def __init__(self):
        self.environment = os.environ.get("ENVIRONMENT", "development")
        self.debug = os.environ.get("DEBUG", "false").lower() == "true"
        log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
        
        # Validate log level
        allowed_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if log_level not in allowed_levels:
            log_level = "INFO"
        self.log_level = log_level
        
        # Sub-configurations
        self.database = DatabaseSettings()
        self.redis = RedisSettings()
        self.ai = AISettings()
        self.whatsapp = WhatsAppSettings()
        self.security = SecuritySettings()
        self.cache = CacheSettings()
        self.rate_limit = RateLimitSettings()
        self.file = FileSettings()
        self.business = BusinessSettings()
        self.service = ServiceSettings()


@lru_cache()
def get_settings() -> AppSettings:
    """Get cached application settings."""
    return AppSettings()