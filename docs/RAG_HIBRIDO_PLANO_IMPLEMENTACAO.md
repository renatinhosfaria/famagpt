# Plano de Implementação: RAG Híbrido FamaGPT

## 📋 Visão Geral do Projeto

**Objetivo**: Evoluir o RAG atual (busca semântica apenas) para um sistema híbrido que combina busca semântica + busca literal com fusão inteligente de resultados.

**Benefícios esperados**:
- 40-60% melhoria na precisão para queries específicas
- Melhor captura de termos técnicos imobiliários
- Experiência superior para busca por critérios específicos (preços, endereços, características)

**Duração Total**: 10 semanas (2,5 meses)  
**Recursos**: 1 Dev Senior + 1 Dev Pleno + 0.5 DevOps + 0.5 QA

---

## 🎯 Estrutura de Fases

### **FASE 1: Fundação e Busca Literal** *(Semanas 1-3)*

#### **Semana 1: Preparação e Schema**

##### **Dia 1-2: Análise e Preparação**
- [ ] **Tarefa 1.1**: Análise detalhada do schema atual
  - Revisar estrutura `rag_documents` e `rag_document_chunks`
  - Identificar impactos das mudanças de schema
  - Documentar dependências atuais

- [ ] **Tarefa 1.2**: Preparação do ambiente de desenvolvimento
  - Setup de branch `feature/hybrid-rag`
  - Configuração de ambiente local com PostgreSQL 15+
  - Instalação de extensões necessárias (`vector`, `pg_trgm`)

##### **Dia 3-4: Migrations Base**
- [ ] **Migration 1.1**: Adicionar suporte full-text
```sql
-- File: migrations/001_add_fulltext_support.sql
ALTER TABLE rag_document_chunks 
ADD COLUMN content_tsvector tsvector;

ALTER TABLE rag_document_chunks 
ADD COLUMN content_clean text;

-- Popular dados existentes
UPDATE rag_document_chunks 
SET content_tsvector = to_tsvector('portuguese', content),
    content_clean = content;

ALTER TABLE rag_document_chunks 
ALTER COLUMN content_tsvector SET NOT NULL;
```

- [ ] **Migration 1.2**: Criar índices otimizados
```sql
-- File: migrations/002_create_fulltext_indexes.sql
-- Índice GIN principal
CREATE INDEX CONCURRENTLY idx_rag_chunks_fulltext 
ON rag_document_chunks 
USING gin(content_tsvector);

-- Índice específico para imóveis
CREATE INDEX CONCURRENTLY idx_rag_chunks_property_terms 
ON rag_document_chunks 
USING gin(content_tsvector)
WHERE metadata->>'document_type' IN ('property', 'listing', 'real_estate');
```

##### **Dia 5: Triggers e Configuração**
- [ ] **Migration 1.3**: Implementar triggers de sincronização
```sql
-- File: migrations/003_create_sync_triggers.sql
CREATE OR REPLACE FUNCTION sync_content_tsvector()
RETURNS trigger AS $$
BEGIN
    NEW.content_tsvector := to_tsvector('portuguese', NEW.content);
    NEW.content_clean := NEW.content;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_sync_content_tsvector
    BEFORE INSERT OR UPDATE OF content 
    ON rag_document_chunks
    FOR EACH ROW
    EXECUTE FUNCTION sync_content_tsvector();
```

- [ ] **Configuração PostgreSQL**: Ajustes para português
```sql
-- Configurações específicas para busca em português
ALTER DATABASE famagpt_rag SET default_text_search_config = 'pg_catalog.portuguese';
```

- [ ] **Testes de Migration**: Validar performance com dados existentes

#### **Semana 2: Implementação Core**

##### **Dia 1-2: Engine de Busca Literal**
- [ ] **Código 2.1**: Criar `LiteralSearchEngine`
```python
# File: rag/src/infrastructure/services/literal_search_engine.py
class LiteralSearchEngine:
    """Motor de busca literal usando PostgreSQL Full-Text"""
    
    async def search_chunks(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        highlight: bool = False
    ) -> List[SearchResult]:
        # Implementação da busca literal com full-text search
        pass
```

- [ ] **Testes 2.1**: Testes unitários para `LiteralSearchEngine`
```python
# File: tests/unit/test_literal_search_engine.py
class TestLiteralSearchEngine:
    async def test_basic_literal_search(self):
        # Testar busca literal básica
        pass
    
    async def test_portuguese_stemming(self):
        # Testar stemming em português
        pass
```

##### **Dia 3-4: Algoritmos de Fusão**
- [ ] **Código 2.2**: Implementar RRF (Reciprocal Rank Fusion)
```python
# File: rag/src/infrastructure/services/result_fusion.py
class HybridResultFusion:
    @staticmethod
    def reciprocal_rank_fusion(
        semantic_results: List[SearchResult],
        literal_results: List[SearchResult],
        k: int = 60
    ) -> List[SearchResult]:
        # Implementação do algoritmo RRF
        pass
```

- [ ] **Testes 2.2**: Testes de fusão RRF
```python
# File: tests/unit/test_result_fusion.py
class TestHybridResultFusion:
    def test_rrf_fusion(self):
        # Testar algoritmo RRF com dados mock
        pass
```

##### **Dia 5: Validação e Documentação**
- [ ] **Documentação**: Documentar algoritmos implementados
- [ ] **Code Review**: Revisão de código da semana
- [ ] **Testes de Integração**: Validar integração entre componentes

#### **Semana 3: Integração e Híbrido Básico**

##### **Dia 1-2: Extensão do PGVectorStore**
- [ ] **Código 3.1**: Estender `PGVectorStore` com métodos híbridos
```python
# File: rag/src/infrastructure/services/pgvector_store.py
class PGVectorStore(VectorStoreProtocol):
    async def hybrid_search_chunks(
        self,
        query: str,
        query_embedding: List[float],
        semantic_weight: float = 0.6,
        literal_weight: float = 0.4,
        top_k: int = 10
    ) -> List[SearchResult]:
        # Implementação da busca híbrida
        pass
```

- [ ] **Código 3.2**: Atualizar protocolos do domínio
```python
# File: rag/src/domain/protocols/rag_service.py
class VectorStoreProtocol(ABC):
    @abstractmethod
    async def hybrid_search_chunks(self, ...):
        pass
```

##### **Dia 3-4: Integração com Pipeline**
- [ ] **Código 3.3**: Integrar com `RAGPipelineUseCase`
```python
# File: rag/src/application/use_cases/rag_pipeline.py
class RAGPipelineUseCase:
    async def hybrid_query_documents(
        self,
        query: str,
        search_mode: str = "hybrid",
        semantic_weight: float = 0.6,
        literal_weight: float = 0.4,
        **kwargs
    ) -> RAGResponse:
        # Implementação do pipeline híbrido
        pass
```

- [ ] **Testes 3.1**: Testes end-to-end busca híbrida
```python
# File: tests/integration/test_hybrid_pipeline.py
class TestHybridPipeline:
    async def test_hybrid_query_flow(self):
        # Teste completo do fluxo híbrido
        pass
```

##### **Dia 5: Milestone M1**
- [ ] **Validação**: Busca híbrida básica funcionando
- [ ] **Demo**: Demonstração para stakeholders
- [ ] **Documentação**: Atualizar documentação técnica

---

### **FASE 2: API e Interface** *(Semanas 4-5)*

#### **Semana 4: Endpoints e DTOs**

##### **Dia 1-2: Novos DTOs**
- [ ] **API 4.1**: Criar `HybridRAGQueryDTO`
```python
# File: rag/src/presentation/api/rag_controller.py
class HybridRAGQueryDTO(RAGQueryDTO):
    search_mode: str = Field(default="hybrid", regex="^(semantic|literal|hybrid)$")
    semantic_weight: float = Field(default=0.6, ge=0.0, le=1.0)
    literal_weight: float = Field(default=0.4, ge=0.0, le=1.0)
    fusion_method: str = Field(default="rrf", regex="^(rrf|weighted)$")
    auto_weights: bool = Field(default=True)
```

- [ ] **Testes API 4.1**: Validação de DTOs
```python
# File: tests/unit/test_hybrid_dtos.py
class TestHybridDTOs:
    def test_hybrid_query_dto_validation(self):
        # Testar validação dos novos DTOs
        pass
```

##### **Dia 3-4: Novos Endpoints**
- [ ] **API 4.2**: Implementar endpoint `/api/v1/rag/hybrid-query`
```python
@router.post("/hybrid-query", response_model=Dict[str, Any])
async def hybrid_query_rag(request: HybridRAGQueryDTO):
    """Query RAG híbrido com controle de pesos"""
    pass
```

- [ ] **API 4.3**: Atualizar endpoint existente `/query`
```python
@router.post("/query", response_model=Dict[str, Any])
async def query_rag(request: RAGQueryDTO):
    """Query RAG com suporte a modo híbrido"""
    # Adicionar parâmetro search_mode
    pass
```

##### **Dia 5: Documentação e Debug**
- [ ] **API 4.4**: Adicionar parâmetros de debug
- [ ] **Doc 4.1**: Atualizar documentação OpenAPI
- [ ] **Testes**: Testes de endpoints

#### **Semana 5: Otimizações e Cache**

##### **Dia 1-2: Cache Híbrido**
- [ ] **Cache 5.1**: Estender `RedisRAGCache` para busca híbrida
```python
# File: rag/src/infrastructure/services/redis_rag_cache.py
class RedisRAGCache(CacheServiceProtocol):
    async def get_cached_hybrid_response(
        self, 
        query_hash: str,
        search_mode: str
    ) -> Optional[RAGResponse]:
        # Cache específico para busca híbrida
        pass
```

- [ ] **Cache 5.2**: Cache específico para queries literais
```python
async def cache_literal_results(
    self,
    query_hash: str,
    results: List[SearchResult],
    ttl_seconds: int = 1800
) -> None:
    # Cache otimizado para resultados literais
    pass
```

##### **Dia 3-4: Otimizações de Performance**
- [ ] **Perf 5.1**: Otimizar queries SQL híbridas
```sql
-- Queries otimizadas para busca híbrida
-- Com explain analyze e ajustes de índices
```

- [ ] **Testes 5.1**: Testes de performance e carga
```python
# File: tests/performance/test_hybrid_performance.py
class TestHybridPerformance:
    async def test_concurrent_hybrid_queries(self):
        # Testar performance com múltiplas queries concorrentes
        pass
```

##### **Dia 5: Milestone M2**
- [ ] **Validação**: API híbrida completa e performante
- [ ] **Benchmarks**: Validar métricas de performance
- [ ] **Documentation**: Atualizar guias de uso

---

### **FASE 3: Inteligência e Otimizações** *(Semanas 6-8)*

#### **Semana 6: Query Analyzer**

##### **Dia 1-2: Análise de Queries**
- [ ] **IA 6.1**: Implementar `QueryAnalyzer`
```python
# File: rag/src/application/services/query_analyzer.py
class QueryAnalyzer:
    """Analisa queries e ajusta pesos automaticamente"""
    
    def analyze_query_type(self, query: str) -> Dict[str, float]:
        # Regras específicas para domínio imobiliário
        pass
    
    def detect_query_intent(self, query: str) -> str:
        # Detectar intenção da query (preço, localização, características)
        pass
```

- [ ] **IA 6.2**: Regras para domínio imobiliário
```python
REAL_ESTATE_PATTERNS = {
    'price_queries': r'R\$|reais|\d+\s*(mil|milhão)',
    'location_queries': r'rua|avenida|bairro \w+|centro|uberlândia',
    'specification_queries': r'\d+\s*(quartos|suítes|vagas|m²)',
    'conceptual_queries': r'família|tranquilo|investimento|rentável'
}
```

##### **Dia 3-4: Sistema de Ajuste Automático**
- [ ] **IA 6.3**: Sistema de ajuste automático de pesos
```python
class AutoWeightAdjuster:
    def adjust_weights_by_query_type(
        self, 
        query: str, 
        query_type: str
    ) -> Dict[str, float]:
        # Ajustar pesos baseado no tipo de query
        pass
```

- [ ] **Config 6.1**: Configurações para patterns imobiliários
```yaml
# config/hybrid_rag_patterns.yaml
real_estate_patterns:
  price_focused:
    semantic_weight: 0.3
    literal_weight: 0.7
  location_focused:
    semantic_weight: 0.4
    literal_weight: 0.6
```

##### **Dia 5: Dataset de Validação**
- [ ] **Testes 6.1**: Dataset de queries teste
```python
# File: tests/fixtures/real_estate_queries.py
HYBRID_TEST_QUERIES = {
    "literal_focused": [
        {
            "query": "apartamento 3 quartos R$ 350.000 Uberlândia",
            "expected_weights": {"literal": 0.7, "semantic": 0.3}
        }
    ],
    "semantic_focused": [
        {
            "query": "casa para família grande em bairro tranquilo",
            "expected_weights": {"literal": 0.3, "semantic": 0.7}
        }
    ]
}
```

#### **Semana 7: Fusão Avançada**

##### **Dia 1-2: Weighted Score Fusion**
- [ ] **Algo 7.1**: Implementar Weighted Score Fusion
```python
class HybridResultFusion:
    @staticmethod
    def weighted_score_fusion(
        semantic_results: List[SearchResult],
        literal_results: List[SearchResult],
        semantic_weight: float = 0.6,
        literal_weight: float = 0.4
    ) -> List[SearchResult]:
        # Implementação da fusão por pesos
        pass
```

- [ ] **Algo 7.2**: Sistema de normalização adaptativo
```python
def adaptive_score_normalization(
    results: List[SearchResult],
    normalization_method: str = "min_max"
) -> List[SearchResult]:
    # Normalização inteligente de scores
    pass
```

##### **Dia 3-4: Métricas de Qualidade**
- [ ] **Algo 7.3**: Métricas de qualidade dos resultados
```python
class ResultQualityMetrics:
    def calculate_relevance_score(
        self, 
        results: List[SearchResult],
        query: str
    ) -> float:
        # Calcular relevância dos resultados
        pass
    
    def calculate_diversity_score(
        self, 
        results: List[SearchResult]
    ) -> float:
        # Calcular diversidade dos resultados
        pass
```

- [ ] **ML 7.1**: Logging para futuro machine learning
```python
class HybridSearchLogger:
    async def log_search_interaction(
        self,
        query: str,
        search_mode: str,
        results: List[SearchResult],
        user_feedback: Optional[Dict] = None
    ):
        # Log estruturado para análise posterior
        pass
```

##### **Dia 5: A/B Testing Framework**
- [ ] **Testes 7.1**: Framework básico de A/B testing
```python
# File: rag/src/infrastructure/services/ab_testing.py
class ABTestingService:
    def get_search_variant(self, user_id: str) -> str:
        # Determinar variante de busca para usuário
        pass
    
    async def log_variant_result(
        self,
        user_id: str,
        variant: str,
        query: str,
        satisfaction_score: float
    ):
        # Log resultados por variante
        pass
```

#### **Semana 8: Features Avançadas**

##### **Dia 1-2: Highlighting e Faceted Search**
- [ ] **Feature 8.1**: Highlighting de termos
```python
def highlight_search_terms(
    content: str,
    query: str,
    highlight_tags: tuple = ("<mark>", "</mark>")
) -> str:
    # Destacar termos encontrados na busca literal
    pass
```

- [ ] **Feature 8.2**: Faceted search por localização e preço
```python
class FacetedSearchService:
    async def get_location_facets(
        self, 
        query: str
    ) -> Dict[str, int]:
        # Facetas por localização
        pass
    
    async def get_price_range_facets(
        self, 
        query: str
    ) -> Dict[str, int]:
        # Facetas por faixa de preço
        pass
```

##### **Dia 3-4: Expansão de Queries**
- [ ] **Feature 8.3**: Expansão com sinônimos imobiliários
```python
# File: config/real_estate_synonyms.yaml
synonyms:
  residential:
    - ["casa", "residência", "moradia", "lar"]
    - ["apartamento", "apto", "flat", "unidade"]
    - ["cobertura", "penthouse", "duplex superior"]
  features:
    - ["piscina", "área de lazer aquática"]
    - ["churrasqueira", "área gourmet", "espaço gourmet"]
```

- [ ] **Feature 8.4**: Filtros avançados para imóveis
```python
class RealEstateFilters:
    def apply_price_range_filter(
        self, 
        query: str, 
        min_price: Optional[float], 
        max_price: Optional[float]
    ) -> str:
        # Aplicar filtros de preço
        pass
    
    def apply_location_radius_filter(
        self, 
        query: str, 
        center_point: tuple, 
        radius_km: float
    ) -> str:
        # Filtro por proximidade geográfica
        pass
```

##### **Dia 5: Milestone M3**
- [ ] **Validação**: Sistema híbrido inteligente completo
- [ ] **Demo Avançada**: Demonstração de features avançadas
- [ ] **Performance Review**: Análise completa de performance

---

### **FASE 4: Monitoramento e Produção** *(Semanas 9-10)*

#### **Semana 9: Deploy e Monitoring**

##### **Dia 1-2: Preparação para Deploy**
- [ ] **Ops 9.1**: Scripts de migration para produção
```bash
#!/bin/bash
# File: scripts/production_migration.sh
echo "=== RAG Hybrid Production Migration ==="

# Backup completo antes das migrations
pg_dump famagpt_rag > backup_pre_hybrid_$(date +%Y%m%d_%H%M%S).sql

# Executar migrations com verificação
psql -d famagpt_rag -f migrations/001_add_fulltext_support.sql
psql -d famagpt_rag -f migrations/002_create_fulltext_indexes.sql
psql -d famagpt_rag -f migrations/003_create_sync_triggers.sql

# Verificar integridade pós-migration
python scripts/verify_hybrid_setup.py
```

- [ ] **Ops 9.2**: Estratégia de deploy blue-green
```bash
#!/bin/bash
# File: scripts/deploy_hybrid_rag.sh
# Deploy Blue-Green para RAG Híbrido
# Garante zero-downtime e rollback rápido
```

##### **Dia 3-4: Métricas e Dashboards**
- [ ] **Monitor 9.1**: Métricas específicas RAG híbrido
```yaml
# File: monitoring/hybrid_rag_metrics.yaml
prometheus_rules:
  - name: hybrid_rag_performance
    rules:
      - alert: HybridSearchLatencyHigh
        expr: histogram_quantile(0.95, rate(hybrid_search_duration_seconds_bucket[5m])) > 2
        for: 2m
        labels:
          severity: warning
```

- [ ] **Monitor 9.2**: Dashboards Grafana
```json
{
  "dashboard": {
    "title": "RAG Híbrido - Performance Dashboard",
    "panels": [
      {
        "title": "Search Mode Distribution",
        "type": "piechart",
        "targets": [
          {
            "expr": "increase(hybrid_search_total[1h]) by (search_mode)"
          }
        ]
      }
    ]
  }
}
```

##### **Dia 5: Alertas**
- [ ] **Alert 9.1**: Alertas para degradação de performance
```yaml
# File: alerting/hybrid_rag_alerts.yaml
groups:
  - name: hybrid_rag
    rules:
      - alert: HybridSearchErrorRateHigh
        expr: rate(hybrid_search_errors_total[5m]) / rate(hybrid_search_requests_total[5m]) > 0.01
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Taxa de erro do RAG híbrido está alta"
```

#### **Semana 10: Validação e Ajustes**

##### **Dia 1-2: Testes em Produção**
- [ ] **Test 10.1**: Testes em produção com tráfego real
```python
# File: tests/production/test_production_hybrid.py
class TestProductionHybrid:
    async def test_real_traffic_performance(self):
        # Monitorar performance com tráfego real
        pass
    
    async def test_search_quality_metrics(self):
        # Validar métricas de qualidade
        pass
```

- [ ] **Monitoring**: Monitoramento contínuo por 48h
```bash
# Script de monitoramento contínuo
while true; do
    python scripts/check_hybrid_health.py
    sleep 300  # Check every 5 minutes
done
```

##### **Dia 3-4: Otimizações Finais**
- [ ] **Perf 10.2**: Ajustes de performance baseados em dados reais
```python
# File: scripts/performance_optimizer.py
class ProductionPerformanceOptimizer:
    def analyze_slow_queries(self):
        # Analisar queries lentas em produção
        pass
    
    def optimize_index_usage(self):
        # Otimizar uso de índices baseado em padrões reais
        pass
```

- [ ] **Config Tuning**: Ajuste de configurações baseado em uso real

##### **Dia 5: Milestone M4 - Conclusão**
- [ ] **UX 10.1**: Análise de satisfação do usuário
```python
# File: analytics/user_satisfaction_analysis.py
class UserSatisfactionAnalyzer:
    def analyze_search_satisfaction(self):
        # Analisar satisfação baseada em métricas de uso
        pass
    
    def generate_improvement_recommendations(self):
        # Gerar recomendações de melhorias
        pass
```

- [ ] **Doc 10.1**: Documentação operacional completa
- [ ] **Milestone M4**: RAG Híbrido em produção estável

---

## 📊 Métricas de Sucesso e KPIs

### **Métricas Técnicas**
| Métrica | Baseline Atual | Meta RAG Híbrido | Método de Medição |
|---------|----------------|-------------------|-------------------|
| **Precision@5** | ~65% | >85% | Avaliação manual + dataset teste |
| **Recall@10** | ~70% | >90% | Queries com resultados conhecidos |
| **Response Time P95** | ~800ms | <1200ms | Monitoramento Prometheus |
| **Cache Hit Rate** | ~40% | >60% | Redis metrics |
| **Error Rate** | <0.5% | <0.5% | Logs + monitoring |

### **Métricas de Negócio**
| KPI | Baseline | Meta | Prazo |
|-----|----------|------|-------|
| **Satisfação Query** | 7.2/10 | >8.5/10 | 2 meses pós-deploy |
| **Taxa Conversão** | 12% | >15% | 3 meses pós-deploy |
| **Tempo Resolução** | 3.2 min | <2.5 min | 1 mês pós-deploy |

---

## 🗂️ Estrutura de Arquivos Criados/Modificados

### **Novos Arquivos**
```
rag/
├── src/infrastructure/services/
│   ├── literal_search_engine.py          # Motor de busca literal
│   └── result_fusion.py                  # Algoritmos de fusão
├── src/application/services/
│   ├── query_analyzer.py                 # Análise inteligente de queries
│   └── ab_testing.py                     # A/B testing framework
├── migrations/
│   ├── 001_add_fulltext_support.sql      # Schema para full-text
│   ├── 002_create_fulltext_indexes.sql   # Índices otimizados
│   └── 003_create_sync_triggers.sql      # Triggers de sincronização
├── config/
│   ├── hybrid_rag_patterns.yaml          # Padrões para imóveis
│   └── real_estate_synonyms.yaml         # Sinônimos do domínio
├── tests/
│   ├── integration/test_hybrid_rag.py    # Testes integrados
│   ├── performance/test_hybrid_performance.py # Testes de performance
│   └── fixtures/real_estate_queries.py   # Dataset de teste
├── scripts/
│   ├── deploy_hybrid_rag.sh              # Deploy blue-green
│   ├── emergency_rollback.sh             # Rollback de emergência
│   └── production_migration.sh           # Migration para produção
└── monitoring/
    ├── hybrid_rag_metrics.yaml           # Métricas Prometheus
    └── dashboards/hybrid_rag_dashboard.json # Dashboard Grafana
```

### **Arquivos Modificados**
```
rag/
├── src/domain/protocols/rag_service.py   # + HybridSearchProtocol
├── src/infrastructure/services/
│   ├── pgvector_store.py                 # + métodos híbridos
│   └── redis_rag_cache.py               # + cache híbrido
├── src/application/
│   ├── use_cases/rag_pipeline.py        # + hybrid_query_documents()
│   └── services/rag_service.py          # + interface híbrida
├── src/presentation/api/rag_controller.py # + endpoints híbridos
├── requirements.txt                       # dependências adicionais
└── main.py                               # configuração híbrida
```

---

## 🚀 Recursos Necessários

### **Equipe e Responsabilidades**
- **Desenvolvedor Senior (1.0 FTE)**:
  - Arquitetura e design do sistema híbrido
  - Implementação dos algoritmos de fusão
  - Code review e mentoria técnica

- **Desenvolvedor Pleno (1.0 FTE)**:
  - Implementação de APIs e endpoints
  - Integração com componentes existentes
  - Testes unitários e de integração

- **DevOps (0.5 FTE)**:
  - Configuração de deploy e monitoramento
  - Scripts de migration e rollback
  - Setup de métricas e alertas

- **QA (0.5 FTE)**:
  - Testes funcionais e de performance
  - Validação de datasets de teste
  - Análise de qualidade dos resultados

### **Infraestrutura Adicional**
```yaml
database:
  storage: +20GB      # Índices full-text
  cpu: +15%          # Processamento híbrido
  memory: +10%       # Cache adicional

rag_service:
  cpu_limit: "2.0"     # +0.5 cores
  memory_limit: "4Gi"  # +1GB
  replicas: 3          # Para A/B testing

monitoring:
  prometheus: +5GB     # Métricas híbridas
  grafana: +2GB        # Dashboards adicionais
```

### **Custos Estimados**
| Item | Valor | Observação |
|------|-------|------------|
| **Desenvolvimento** | 40 dias-homem | 10 semanas × 4 pessoas × eficiência |
| **Infraestrutura** | +15% custos mensais | Recursos adicionais |
| **Monitoramento** | $500 setup único | Dashboards e alertas |
| **OpenAI API** | Sem aumento | Mesmo volume de embeddings |
| **Total Estimado** | ~$25.000 + 15% opex | Investimento de 10 semanas |

---

## ⚠️ Riscos e Mitigações

### **Riscos Técnicos**
| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| **Performance degradação** | Média | Alto | Testes extensivos + monitoring + rollback |
| **Complexidade SQL** | Baixa | Médio | Code review + DBA consultation |
| **Índices PostgreSQL** | Baixa | Alto | Backup completo + teste staging |
| **Cache invalidation** | Média | Médio | TTL conservador + invalidação manual |

### **Riscos de Negócio**
| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| **Usuários preferem atual** | Baixa | Médio | A/B testing + feature flag |
| **Aumento custos** | Média | Baixo | Monitoring custos + otimização |
| **Delayed delivery** | Média | Médio | Buffer time + MVP approach |

### **Planos de Contingência**
1. **Performance Issues**: Rollback automático se P95 > 2s
2. **Migration Failures**: Restore from backup + hotfix
3. **User Dissatisfaction**: Feature flag disable + analysis
4. **Resource Constraints**: Scale infrastructure dynamically

---

## 📈 Roadmap Pós-Implementação

### **Curto Prazo (1-3 meses pós-deploy)**
- [ ] **Análise de dados de uso real**
- [ ] **Otimizações baseadas em feedback**
- [ ] **Ajuste fino de pesos automático**
- [ ] **Expansão de sinônimos imobiliários**

### **Médio Prazo (3-6 meses)**
- [ ] **Reranking com modelos cross-encoder**
- [ ] **Suporte a documentos multimodais**
- [ ] **Query expansion automática**
- [ ] **Personalização por usuário/região**

### **Longo Prazo (6-12 meses)**
- [ ] **RAG com Knowledge Graphs**
- [ ] **Fine-tuning de modelos para imóveis**
- [ ] **Integração com Elasticsearch** (se necessário)
- [ ] **Machine Learning para otimização automática**

---

## ✅ Checklist de Aprovação e Marcos

### **Pré-Implementação**
- [ ] Aprovação do plano pela equipe técnica
- [ ] Ambiente de desenvolvimento configurado
- [ ] Dataset de teste preparado e validado
- [ ] Backup completo do banco de dados
- [ ] Documentação técnica inicial revisada

### **Milestone M1: Busca Híbrida Básica** *(Semana 3)*
- [ ] Migrations executadas com sucesso
- [ ] Busca literal funcionando
- [ ] Algoritmo RRF implementado
- [ ] Testes unitários passando (>95%)
- [ ] Demo funcional para stakeholders

### **Milestone M2: API Completa** *(Semana 5)*
- [ ] Endpoints híbridos funcionando
- [ ] Cache otimizado implementado
- [ ] Testes de performance aprovados
- [ ] Documentação API atualizada
- [ ] Code review completo aprovado

### **Milestone M3: Sistema Inteligente** *(Semana 8)*
- [ ] Query analyzer funcionando
- [ ] Features avançadas implementadas
- [ ] A/B testing framework pronto
- [ ] Métricas de qualidade validadas
- [ ] Performance benchmarks atendidos

### **Milestone M4: Produção Estável** *(Semana 10)*
- [ ] Deploy em produção bem-sucedido
- [ ] Monitoramento completo ativo
- [ ] Métricas de negócio sendo coletadas
- [ ] Documentação operacional completa
- [ ] Equipe de suporte treinada

### **Critérios de Aceitação Final**
- [ ] ✅ Precision@5 > 85% em dataset de teste
- [ ] ✅ Response time P95 < 1200ms
- [ ] ✅ Error rate < 0.5%
- [ ] ✅ Cache hit rate > 60%
- [ ] ✅ Zero downtime durante deploy
- [ ] ✅ Rollback testado e documentado
- [ ] ✅ Satisfação da equipe de produto

---

## 📋 Próximos Passos

1. **Revisar e Aprovar este Plano**: Revisão com equipe técnica e product owners
2. **Setup do Ambiente**: Configurar branch e ambiente de desenvolvimento
3. **Kick-off do Projeto**: Reunião inicial da equipe para alinhamento
4. **Início da Fase 1**: Começar com as migrations e preparação de schema

**Data de Início Sugerida**: [A DEFINIR]  
**Data de Conclusão Estimada**: [INÍCIO + 10 SEMANAS]

---

*Este documento é vivo e deve ser atualizado conforme o progresso da implementação e feedback da equipe.*