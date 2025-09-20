"""
Teste mínimo para verificar endpoint /api/v1/transcribe
"""

from fastapi import FastAPI
import uvicorn

# Criar app mínimo
app = FastAPI(title="Test Transcription Service")

# Endpoint que deve funcionar
@app.post("/api/v1/transcribe")
async def transcribe_test(request: dict):
    """Test endpoint for /api/v1/transcribe"""
    audio_data = request.get("audio_data", "")
    return {
        "text": f"Transcrição teste: {audio_data[:50]}...",
        "confidence": 0.95,
        "duration": 2.5,
        "status": "completed"
    }

@app.get("/")
async def root():
    return {"service": "test_transcription", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run("main_test:app", host="0.0.0.0", port=8002, reload=True)