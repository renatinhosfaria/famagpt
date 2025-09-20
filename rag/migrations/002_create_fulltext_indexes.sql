-- Migration 002: Criar índices otimizados para busca full-text
-- Data: 2024-01-XX
-- Descrição: Cria índices GIN otimizados para performance de busca híbrida

-- Começar transação
BEGIN;

-- 1. Verificar se migration anterior foi aplicada
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='rag_document_chunks' AND column_name='content_tsvector'
    ) THEN
        RAISE EXCEPTION 'Migration 001 deve ser aplicada antes desta migration';
    END IF;
END
$$;

-- 2. Índice GIN principal para busca full-text
-- CONCURRENTLY para não bloquear tabela em produção
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_rag_chunks_fulltext 
ON rag_document_chunks 
USING gin(content_tsvector);

-- 3. Índice específico para documentos do tipo imobiliário
-- Útil para queries filtradas por tipo de documento
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_rag_chunks_property_terms 
ON rag_document_chunks 
USING gin(content_tsvector)
WHERE metadata->>'document_type' IN ('property', 'listing', 'real_estate', 'imovel');

-- 4. Índice composto para queries híbridas frequentes
-- Inclui colunas mais usadas em busca híbrida
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_rag_chunks_hybrid_search 
ON rag_document_chunks 
(document_id, chunk_index)
INCLUDE (content, metadata, created_at);

-- 5. Índice para busca por localização (comum em imóveis)
-- Combina informações de endereço para busca geográfica
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_rag_chunks_location_search 
ON rag_document_chunks 
USING gin(to_tsvector('portuguese', 
    coalesce(metadata->>'address', '') || ' ' || 
    coalesce(metadata->>'neighborhood', '') || ' ' || 
    coalesce(metadata->>'city', '') || ' ' ||
    coalesce(metadata->>'district', '') || ' ' ||
    coalesce(metadata->>'state', '')
))
WHERE 
    metadata->>'address' IS NOT NULL 
    OR metadata->>'neighborhood' IS NOT NULL 
    OR metadata->>'city' IS NOT NULL;

-- 6. Índice para busca por preços (específico para imóveis)
-- Usa expressão trigram para capturar variações de formato de preço
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_rag_chunks_price_search 
ON rag_document_chunks 
USING gin(content gin_trgm_ops)
WHERE content ~* 'R\$|reais|\d+.*mil|\d+.*milhão|\d+.*milhões|valor|preço';

-- 7. Índice para características técnicas de imóveis
-- Captura especificações como quartos, vagas, área
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_rag_chunks_specifications 
ON rag_document_chunks 
USING gin(to_tsvector('portuguese', content))
WHERE content ~* '\d+\s*(quartos?|suítes?|vagas?|m²|metros?|área)';

-- 8. Índice otimizado para documento + similaridade (para ranking híbrido)
-- Útil para ordenação por relevância em busca híbrida
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_rag_chunks_document_relevance 
ON rag_document_chunks 
(document_id, chunk_index, created_at DESC);

-- 9. Estatísticas dos índices criados
CREATE OR REPLACE FUNCTION get_fulltext_indexes_stats()
RETURNS TABLE(
    index_name text,
    table_name text,
    index_size text,
    is_valid boolean,
    definition text
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        i.indexname::text,
        i.tablename::text,
        pg_size_pretty(pg_relation_size(i.indexname::regclass))::text as index_size,
        idx.indisvalid as is_valid,
        i.indexdef::text
    FROM pg_indexes i
    JOIN pg_class c ON c.relname = i.indexname
    JOIN pg_index idx ON idx.indexrelid = c.oid
    WHERE i.tablename = 'rag_document_chunks'
    AND i.indexname LIKE 'idx_rag_chunks_%'
    ORDER BY i.indexname;
END;
$$ LANGUAGE plpgsql;

-- 10. Função para análise de performance de queries
CREATE OR REPLACE FUNCTION analyze_fulltext_performance()
RETURNS TABLE(
    query_type text,
    avg_execution_time numeric,
    index_usage_ratio numeric,
    recommendation text
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        'full_text_search'::text,
        0.0::numeric, -- Será populado com dados reais de uso
        0.0::numeric,
        'Execute ANALYZE após popular dados para estatísticas precisas'::text;
END;
$$ LANGUAGE plpgsql;

-- 11. Atualizar estatísticas das tabelas
ANALYZE rag_document_chunks;
ANALYZE rag_documents;

-- 12. Verificar criação dos índices
SELECT * FROM get_fulltext_indexes_stats();

-- 13. Registrar migration
INSERT INTO schema_migrations (version, description) 
VALUES ('002', 'Criar índices otimizados para busca full-text')
ON CONFLICT (version) DO UPDATE SET applied_at = CURRENT_TIMESTAMP;

COMMIT;

-- Mensagens finais
\echo 'Migration 002 aplicada com sucesso!'
\echo 'Índices criados:'
\echo '  - idx_rag_chunks_fulltext (GIN principal)'
\echo '  - idx_rag_chunks_property_terms (filtro por tipo)'
\echo '  - idx_rag_chunks_hybrid_search (busca híbrida)'
\echo '  - idx_rag_chunks_location_search (localização)'
\echo '  - idx_rag_chunks_price_search (preços)'
\echo '  - idx_rag_chunks_specifications (especificações técnicas)'
\echo ''
\echo 'Próximo passo: executar 003_create_sync_triggers.sql'

-- Dica para monitoramento
\echo ''
\echo 'Para monitorar uso dos índices:'
\echo 'SELECT * FROM get_fulltext_indexes_stats();'