"""
Orchestrator FastAPI application - Versão Corrigida
"""
import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

# Configuração manual para evitar problemas do Pydantic
class DatabaseConfig:
    def __init__(self):
        self.url = os.getenv('DATABASE_URL')
        self.host = os.getenv('PGHOST', 'localhost')
        self.port = int(os.getenv('PGPORT', 5432))
        self.database = os.getenv('PGDATABASE', 'famagpt')
        self.username = os.getenv('PGUSER', 'postgres')
        self.password = os.getenv('PGPASSWORD', '')

class RedisConfig:
    def __init__(self):
        self.url = os.getenv('REDIS_URL', 'redis://redis:6379')
        self.password = os.getenv('REDIS_PASSWORD')
        self.db = int(os.getenv('REDIS_DB', 0))

class AppConfig:
    def __init__(self):
        self.service_name = os.getenv('SERVICE_NAME', 'orchestrator')
        self.port = int(os.getenv('PORT', 8000))
        self.database_url = os.getenv('DATABASE_URL')
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        self.database = DatabaseConfig()
        self.redis = RedisConfig()

# Global config
config = AppConfig()

# Global application state
app_state = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    
    print(f"🚀 Starting Orchestrator service on port {config.port}")
    print(f"Database URL configured: {bool(config.database_url)}")
    print(f"OpenAI API Key configured: {bool(config.openai_api_key)}")
    
    try:
        # For now, just initialize basic state without full database connection
        # to confirm the service can start
        app_state["config"] = config
        app_state["status"] = "running"
        
        print("✅ Orchestrator service started successfully")
        yield
        
    except Exception as e:
        print(f"❌ Error starting Orchestrator: {e}")
        raise
    finally:
        print("🛑 Orchestrator service stopped")

# Create FastAPI app
app = FastAPI(
    title="FamaGPT Orchestrator",
    description="LangGraph-based workflow orchestration service",
    version="1.0.0",
    lifespan=lifespan
)

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "orchestrator",
        "version": "1.0.0",
        "database_configured": bool(config.database_url),
        "openai_configured": bool(config.openai_api_key),
        "state": app_state.get("status", "unknown")
    }

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "FamaGPT Orchestrator Service", 
        "status": "running",
        "version": "1.0.0"
    }

@app.get("/config")
async def get_config():
    """Get service configuration (debug endpoint)."""
    return {
        "service_name": config.service_name,
        "port": config.port,
        "database_configured": bool(config.database_url),
        "redis_configured": bool(config.redis.url),
        "openai_configured": bool(config.openai_api_key),
    }