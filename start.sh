#!/bin/bash

# ==============================================
# FamaGPT System Startup Script
# ==============================================

set -e

echo "🚀 Starting FamaGPT Multi-Agent System..."

# Check if .env file exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Copying from .env.example..."
    cp .env.example .env
    echo "📝 Please edit .env file with your credentials before running again."
    exit 1
fi

# Check Docker and Docker Compose
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p logs
mkdir -p temp
mkdir -p documents

# Set permissions
chmod 755 logs temp documents

# Pull latest images and build services
echo "🔧 Building services..."
docker-compose build --no-cache

# Start services
echo "🚀 Starting services..."
docker-compose up -d

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 10

# Health check
echo "🏥 Performing health checks..."

services=(
    "orchestrator:8000"
    "webhooks:8001"
    "transcription:8002"
    "web_search:8003"
    "memory:8004"
    "rag:8005"
    "database:8006"
    "specialist:8007"
)

for service in "${services[@]}"; do
    name=${service%:*}
    port=${service#*:}
    echo "Checking $name service..."
    
    # Wait up to 30 seconds for service to be ready
    for i in {1..30}; do
        # Orchestrator expõe /api/v1/health
        health_path="/health"
        if [ "$name" = "orchestrator" ]; then
            health_path="/api/v1/health"
        fi

        if curl -f -s "http://localhost:$port$health_path" > /dev/null 2>&1; then
            echo "✅ $name service is ready"
            break
        else
            if [ $i -eq 30 ]; then
                echo "❌ $name service failed to start"
            else
                sleep 1
            fi
        fi
    done
done

echo ""
echo "🎉 FamaGPT System is ready!"
echo ""
echo "📊 Service URLs:"
echo "  - Orchestrator: http://localhost:8000"
echo "  - Webhooks: http://localhost:8001"
echo "  - Transcription: http://localhost:8002"
echo "  - Web Search: http://localhost:8003"
echo "  - Memory: http://localhost:8004"
echo "  - RAG: http://localhost:8005"
echo "  - Database: http://localhost:8006"
echo "  - Specialist: http://localhost:8007"
echo ""
echo "📋 Useful commands:"
echo "  - View logs: docker-compose logs -f"
echo "  - Stop system: docker-compose down"
echo "  - Restart system: docker-compose restart"
echo "  - View status: docker-compose ps"
echo ""
echo "🔍 Monitor system: docker stats"
