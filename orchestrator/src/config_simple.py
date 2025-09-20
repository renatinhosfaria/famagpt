"""
Configuração simples temporária para debug
"""
import os

class SimpleSettings:
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
        self.redis_url = os.getenv('REDIS_URL', 'redis://redis:6379')
        self.service_name = os.getenv('SERVICE_NAME', 'orchestrator')
        self.port = int(os.getenv('PORT', 8000))
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        
        print(f"DEBUG - DATABASE_URL: {self.database_url}")
        print(f"DEBUG - REDIS_URL: {self.redis_url}")
        print(f"DEBUG - SERVICE_NAME: {self.service_name}")
        print(f"DEBUG - PORT: {self.port}")
        print(f"DEBUG - OPENAI_API_KEY: {self.openai_api_key[:20] if self.openai_api_key else None}...")

settings = SimpleSettings()