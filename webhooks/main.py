"""
Webhooks Service - WhatsApp Evolution API Integration
Main application entry point using Clean Architecture
"""

import uvicorn
import sys

# Add shared path
sys.path.append('/app/shared')

from src.presentation.api.webhooks_api import app

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info"
    )