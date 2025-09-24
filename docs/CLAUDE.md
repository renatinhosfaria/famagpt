# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FamaGPT is a multi-agent AI system built with microservices architecture, featuring LangGraph orchestration for real estate agents specializing in Uberlândia/MG. The system integrates WhatsApp messaging via Evolution API, voice transcription, web scraping, and hybrid memory management.

## Architecture

The system follows Clean Architecture principles with these core services:

- **orchestrator** (port 8000): LangGraph-based workflow orchestration with LangSmith observability
- **webhooks** (port 8001): WhatsApp integration via Evolution API
- **transcription** (port 8002): Whisper-based audio-to-text conversion
- **web_search** (port 8003): Playwright-powered property search and scraping
- **memory** (port 8004): Hybrid short/long-term memory system
- **rag** (port 8005): Retrieval-Augmented Generation pipeline
- **database** (port 8006): PostgreSQL integration service
- **specialist** (port 8007): Real estate domain expert agent

All services communicate via Redis and share common protocols through the `shared/` directory.

## Development Commands

### System Management
```bash
# Start entire system
./start.sh

# Start services manually
docker-compose up -d

# Start with test configuration
docker-compose -f docker-compose.test.yml up -d

# View all service logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f [service_name]

# Check service status
docker-compose ps

# Stop system
docker-compose down

# Rebuild services
docker-compose build --no-cache

# Monitor resource usage
docker stats
```

### Health Checks
```bash
# Test all service endpoints
curl http://localhost:8000/health  # orchestrator
curl http://localhost:8001/health  # webhooks
curl http://localhost:8002/health  # transcription
curl http://localhost:8003/health  # web_search
curl http://localhost:8004/health  # memory
curl http://localhost:8005/health  # rag
curl http://localhost:8006/health  # database
curl http://localhost:8007/health  # specialist
```

### Individual Service Development
```bash
# Access service container for debugging
docker-compose exec [service_name] bash

# Rebuild single service
docker-compose build [service_name]

# Restart single service
docker-compose restart [service_name]
```

## Service Structure

Each service follows Clean Architecture:
```
service_name/
├── src/
│   ├── domain/          # Business entities and interfaces
│   ├── application/     # Use cases and application services
│   ├── infrastructure/  # External integrations (DB, APIs, etc.)
│   └── presentation/    # FastAPI routes and main.py
├── tests/              # Service-specific tests
├── Dockerfile
└── requirements.txt
```

The `shared/` directory contains:
- Common domain protocols and interfaces
- Database client and Redis utilities
- Logging and configuration management
- Cross-service communication protocols

## Environment Configuration

Copy `.env.example` to `.env` and configure:

### Required API Keys
- `OPENAI_API_KEY`: For LLM operations and embeddings
- `LANGCHAIN_API_KEY`: For LangSmith observability
- `EVOLUTION_API_KEY`: For WhatsApp integration

### Database Configuration
The system uses an external PostgreSQL database with PGVector extension:
- `DATABASE_URL`: Full PostgreSQL connection string
- `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`: Individual connection parameters

### Business Configuration
- `DEFAULT_CITY=Uberlândia` and `DEFAULT_STATE=MG`: Primary market focus
- `PROPERTY_SEARCH_RADIUS_KM=50`: Search radius for property queries

## Key Workflows

1. **Message Processing**: WhatsApp → webhooks → orchestrator → LangGraph workflow → specialist agents
2. **Audio Processing**: Audio upload → transcription service → text processing
3. **Property Search**: User query → web_search service → Playwright scraping → results
4. **Memory Management**: Conversations stored in memory service with Redis caching
5. **Document RAG**: Documents processed by rag service with vector embeddings

## Inter-Service Communication

Services communicate via:
- **HTTP APIs**: Direct service-to-service REST calls
- **Redis**: Message queuing and caching
- **Shared protocols**: Common interfaces defined in `shared/src/domain/`

The orchestrator coordinates all workflows using LangGraph, with observability provided by LangSmith integration.

## Adding New Services

1. Create directory following Clean Architecture structure
2. Add service to `docker-compose.yml` with appropriate environment variables
3. Implement shared protocols from `shared/src/domain/`
4. Register service in orchestrator's workflow graph
5. Configure Redis communication and health check endpoints

## Regras do Assistente (Claude Code)

- Sempre responda em **português do Brasil (pt-BR)**.
- Mantenha **identificadores de código** (nomes de variáveis, funções, commits) em inglês quando fizer sentido, mas explique em pt-BR.
- Comentários em código e mensagens de commit: em pt-BR, claros e objetivos.
- Se eu colar trechos de log/erro em inglês, **explique em pt-BR** e mantenha as partes técnicas no idioma original quando necessário.