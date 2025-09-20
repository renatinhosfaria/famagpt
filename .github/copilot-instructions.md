# Instruções Copilot para FamaGPT

Propósito: Orientar agentes de código a atuar com produtividade e segurança neste sistema multi‑serviço orquestrado por LangGraph. Respostas concisas, focadas em edits concretos, seguindo padrões existentes fielmente.

## 0. Regras de Linguagem
- Sempre responder em português do Brasil (pt-BR).
- Identificadores de código (funções, variáveis, classes, commits) permanecem em inglês quando semanticamente claros.
- Comentários de código e mensagens de commit: pt-BR, curtos, objetivos e descritivos do "porquê".
- Logs/erros colados em inglês devem ser explicados em pt-BR mantendo termos técnicos originais quando necessário.

## 1. Modelo Mental da Arquitetura
- Microservices (FastAPI) + núcleo compartilhado. Serviços: orchestrator (LangGraph, /api/v1/health), webhooks, transcription, web_search, memory, rag, database, specialist.
- Código compartilhado em `shared/` (models, logging, health, middleware, metrics) NÃO deve ser duplicado; sempre importar.
- Cada serviço segue Clean Architecture: `domain/` (entidades/interfaces), `application/` (casos de uso), `infrastructure/` (adapters externos), `presentation/` (rotas FastAPI + main.py).
- Comunicação: HTTP interno (DNS docker), Redis (streams/cache). Schemas Pydantic centralizados asseguram consistência.
- Orchestrator coordena fluxos LangGraph; schemas em `orchestrator/src/presentation/schemas.py`.

## 2. Convenções Essenciais
- Logging: usar `shared.logging.structured_logger.get_logger`; jamais `print()`. Incluir contexto de correlação quando possível.
- Health: endpoint `/health` (orchestrator adicional `/api/v1/health`) via `HealthChecker`.
- Métricas: expor `/metrics` usando `metrics_endpoint`; medir operações com `track_duration` e incrementar counters específicos (mensagens, tokens, etc.).
- Backpressure/rate limit: reutilizar `shared/middleware/backpressure.py` em vez de lógica ad-hoc.
- Enums/modelos: importar de `shared/src/domain/models.py` (ex.: `Priority`, `MessageType`).
- Comentários e docstrings em pt-BR claros; manter nomes de funções enxutos.

## 3. Nova Feature ou Alteração
1. Regras de negócio → `application/` (função ou classe de caso de uso).
2. Nova dependência externa → definir interface em `domain/`.
3. Adapter concreto → `infrastructure/` reutilizando libs utilitárias compartilhadas.
4. Exposição HTTP ou nó LangGraph → camada `presentation/` com schema Pydantic.
5. Adicionar logs estruturados + métricas e, se aplicável, health check.
6. Editar `docker-compose.yml` somente se precisar de novo serviço/porta/env.

## 4. Padrões de Execução/Workflow
- Fluxo mensagem: webhook → orchestrator → seleção de workflow → nós LangGraph → chamadas HTTP a specialist/memory/rag/web_search.
- Prioridade: campo `priority` (`Priority` enum) em `ExecuteWorkflowRequest` não deve ser renomeado.
- Redis Streams: principal `messages:stream`; DLQ com sufixo `:dlq`.
- Backpressure: basear-se em profundidade de fila e pendências; ajustar thresholds via inicialização de middleware, não hard-code por requisição.

## 5. Testes
- Testes de integração principais em `tests/` raiz; específicos em `service/tests/`.
- Usar `httpx.AsyncClient` para endpoints async.
- Novo endpoint → adicionar teste de status e campos essenciais da resposta.
- Evitar mocks de camadas compartilhadas para cobrir fluxo real.

## 6. Observabilidade (Exemplos)
```python
from shared.logging.structured_logger import get_logger
logger = get_logger("memory.service")
logger.info("Armazenando memória", memory_id=str(mem.id), priority=mem.priority)

from shared.monitoring.metrics import track_duration
@track_duration("rag", operation="embed_documents", workflow="ingest")
async def embed_docs(docs): ...
```

## 7. Snippet Health & Métricas
```python
from fastapi import FastAPI
from shared.health.health_check import HealthChecker
from shared.monitoring.metrics import metrics_endpoint
app = FastAPI()
checker = HealthChecker("memory")
@app.get("/health")
async def health():
  return await checker.run_all_checks({"redis_url": REDIS_URL, "database_url": DB_URL})
@app.get("/metrics")
async def metrics():
  return await metrics_endpoint()
```

## 8. Ambiente / Variáveis
- Usar variáveis exportadas via docker-compose; acessar uma vez no startup e validar.
- Orchestrator: requer OPENAI_API_KEY + LANGCHAIN_* (tracing). Webhooks: EVOLUTION_API_*.

## 9. Performance & Segurança
- Preferir I/O assíncrona (aiohttp, redis.asyncio); evitar blocos síncronos em handlers.
- Não implementar sleeps para controle de carga; confiar no middleware existente.
- Validar payload externo com Pydantic; usar `extract_context_from_webhook_data` para normalizar webhooks.

## 10. Higiene de PR / Patches
- Minimizar diff: alterar somente o necessário.
- Manter imports reutilizados; evitar reorganização irrelevante.
- Docstrings pt-BR e consistentes.
- Adicionar/atualizar testes se API pública mudar.

## 11. Anti‑Padrões (Evitar)
- Duplicar enums/modelos compartilhados.
- `print()` ao invés de logger.
- Lógica de infraestrutura embutida em casos de uso.
- Chamadas HTTP síncronas em código async.
- Circular dependency referenciando `presentation` em `domain`.

## 12. Referência Rápida
- Shared core: `shared/`
- Schemas orchestrator: `orchestrator/src/presentation/schemas.py`
- Domain models: `shared/src/domain/models.py`
- Métricas: `shared/monitoring/metrics.py`
- Backpressure: `shared/middleware/backpressure.py`
- Logging: `shared/logging/structured_logger.py`
- Health: `shared/health/health_check.py`

Atualize este arquivo quando padrões evoluírem; manter enxuto e específico.
