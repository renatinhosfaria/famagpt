"""
Orchestrator FastAPI application - Versão Simplificada para Debug
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="FamaGPT Orchestrator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "orchestrator",
        "database_url_configured": bool(os.getenv('DATABASE_URL')),
        "openai_api_configured": bool(os.getenv('OPENAI_API_KEY')),
        "env_vars": {
            "SERVICE_NAME": os.getenv('SERVICE_NAME'),
            "PORT": os.getenv('PORT'),
            "DATABASE_URL": os.getenv('DATABASE_URL')[:50] if os.getenv('DATABASE_URL') else None,
            "REDIS_URL": os.getenv('REDIS_URL'),
        }
    }

@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "FamaGPT Orchestrator - Debug Version", "status": "running"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv('PORT', 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)