-- Migration 003: Criar triggers de sincronização para tsvector
-- Data: 2024-01-XX
-- Descrição: Implementa triggers para manter content_tsvector sincronizado automaticamente

-- Começar transação
BEGIN;

-- 1. Verificar se migrations anteriores foram aplicadas
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='rag_document_chunks' AND column_name='content_tsvector'
    ) THEN
        RAISE EXCEPTION 'Migration 001 deve ser aplicada antes desta migration';
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE tablename='rag_document_chunks' AND indexname='idx_rag_chunks_fulltext'
    ) THEN
        RAISE EXCEPTION 'Migration 002 deve ser aplicada antes desta migration';
    END IF;
END
$$;

-- 2. Função principal para sincronizar tsvector
CREATE OR REPLACE FUNCTION sync_content_tsvector()
RETURNS trigger AS $$
DECLARE
    search_config text := 'portuguese';
BEGIN
    -- Log para debug (apenas em desenvolvimento)
    -- RAISE NOTICE 'Atualizando tsvector para chunk_id: %', COALESCE(NEW.id, 'NEW');
    
    -- Atualizar tsvector quando content mudar
    IF NEW.content IS NOT NULL THEN
        NEW.content_tsvector := to_tsvector(search_config, NEW.content);
        
        -- Manter content_clean sincronizado
        NEW.content_clean := NEW.content;
    ELSE
        -- Se content for NULL, definir tsvector vazio
        NEW.content_tsvector := to_tsvector(search_config, '');
        NEW.content_clean := '';
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 3. Trigger para INSERT/UPDATE
DROP TRIGGER IF EXISTS trigger_sync_content_tsvector ON rag_document_chunks;

CREATE TRIGGER trigger_sync_content_tsvector
    BEFORE INSERT OR UPDATE OF content 
    ON rag_document_chunks
    FOR EACH ROW
    EXECUTE FUNCTION sync_content_tsvector();

-- 4. Função para reprocessar todos os chunks (útil para manutenção)
CREATE OR REPLACE FUNCTION reprocess_all_tsvectors()
RETURNS TABLE(
    processed_count bigint,
    error_count bigint,
    processing_time interval
) AS $$
DECLARE
    start_time timestamp := clock_timestamp();
    total_processed bigint := 0;
    total_errors bigint := 0;
BEGIN
    -- Atualizar todos os chunks em lotes
    UPDATE rag_document_chunks 
    SET content_tsvector = to_tsvector('portuguese', COALESCE(content, '')),
        content_clean = COALESCE(content, '');
    
    GET DIAGNOSTICS total_processed = ROW_COUNT;
    
    -- Retornar estatísticas
    RETURN QUERY 
    SELECT 
        total_processed,
        total_errors,
        clock_timestamp() - start_time;
END;
$$ LANGUAGE plpgsql;

-- 5. Função para validar sincronização
CREATE OR REPLACE FUNCTION validate_tsvector_sync()
RETURNS TABLE(
    total_chunks bigint,
    synced_chunks bigint,
    unsynced_chunks bigint,
    sync_percentage numeric,
    sample_unsynced_ids text[]
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        (SELECT count(*) FROM rag_document_chunks) as total_chunks,
        (SELECT count(*) FROM rag_document_chunks 
         WHERE content_tsvector = to_tsvector('portuguese', COALESCE(content, ''))) as synced_chunks,
        (SELECT count(*) FROM rag_document_chunks 
         WHERE content_tsvector != to_tsvector('portuguese', COALESCE(content, '')) 
         OR content_tsvector IS NULL) as unsynced_chunks,
        CASE 
            WHEN (SELECT count(*) FROM rag_document_chunks) = 0 THEN 0
            ELSE round(
                (SELECT count(*) FROM rag_document_chunks 
                 WHERE content_tsvector = to_tsvector('portuguese', COALESCE(content, ''))) * 100.0 / 
                (SELECT count(*) FROM rag_document_chunks), 2
            )
        END as sync_percentage,
        (SELECT array_agg(id ORDER BY id LIMIT 5) FROM rag_document_chunks 
         WHERE content_tsvector != to_tsvector('portuguese', COALESCE(content, '')) 
         OR content_tsvector IS NULL) as sample_unsynced_ids;
END;
$$ LANGUAGE plpgsql;

-- 6. Função para estatísticas de texto completas
CREATE OR REPLACE FUNCTION get_fulltext_stats()
RETURNS TABLE(
    total_documents bigint,
    total_chunks bigint,
    avg_tokens_per_chunk numeric,
    avg_chars_per_chunk numeric,
    most_common_terms text[],
    search_config text
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        (SELECT count(*) FROM rag_documents) as total_documents,
        (SELECT count(*) FROM rag_document_chunks) as total_chunks,
        COALESCE(
            (SELECT avg(array_length(string_to_array(content_clean, ' '), 1)) 
             FROM rag_document_chunks WHERE content_clean IS NOT NULL), 0
        )::numeric(10,2) as avg_tokens_per_chunk,
        COALESCE(
            (SELECT avg(length(content_clean)) 
             FROM rag_document_chunks WHERE content_clean IS NOT NULL), 0
        )::numeric(10,2) as avg_chars_per_chunk,
        COALESCE((
            SELECT array_agg(word ORDER BY nentry DESC LIMIT 10) 
            FROM ts_stat($$
                SELECT content_tsvector FROM rag_document_chunks 
                WHERE content_tsvector IS NOT NULL
            $$)
        ), ARRAY[]::text[]) as most_common_terms,
        current_setting('default_text_search_config') as search_config;
END;
$$ LANGUAGE plpgsql;

-- 7. Função para testar performance de busca
CREATE OR REPLACE FUNCTION test_search_performance(
    test_query text DEFAULT 'apartamento 3 quartos',
    sample_size integer DEFAULT 100
)
RETURNS TABLE(
    query_text text,
    semantic_time_ms numeric,
    literal_time_ms numeric,
    semantic_results integer,
    literal_results integer,
    performance_ratio numeric
) AS $$
DECLARE
    start_time timestamp;
    semantic_duration numeric;
    literal_duration numeric;
    semantic_count integer;
    literal_count integer;
BEGIN
    -- Teste busca semântica (simulada - só contagem)
    start_time := clock_timestamp();
    SELECT count(*) INTO semantic_count 
    FROM rag_document_chunks 
    WHERE embedding IS NOT NULL
    LIMIT sample_size;
    semantic_duration := EXTRACT(EPOCH FROM (clock_timestamp() - start_time)) * 1000;
    
    -- Teste busca literal
    start_time := clock_timestamp();
    SELECT count(*) INTO literal_count 
    FROM rag_document_chunks 
    WHERE content_tsvector @@ plainto_tsquery('portuguese', test_query)
    LIMIT sample_size;
    literal_duration := EXTRACT(EPOCH FROM (clock_timestamp() - start_time)) * 1000;
    
    RETURN QUERY
    SELECT 
        test_query,
        semantic_duration,
        literal_duration,
        semantic_count,
        literal_count,
        CASE 
            WHEN literal_duration > 0 THEN round(semantic_duration / literal_duration, 2)
            ELSE 0
        END;
END;
$$ LANGUAGE plpgsql;

-- 8. Validar que triggers foram criados corretamente
DO $$
DECLARE
    trigger_count integer;
BEGIN
    SELECT count(*) INTO trigger_count
    FROM information_schema.triggers
    WHERE trigger_name = 'trigger_sync_content_tsvector'
    AND event_object_table = 'rag_document_chunks';
    
    IF trigger_count = 0 THEN
        RAISE EXCEPTION 'Trigger não foi criado corretamente';
    ELSE
        RAISE NOTICE 'Trigger criado com sucesso: trigger_sync_content_tsvector';
    END IF;
END
$$;

-- 9. Executar validação inicial
SELECT * FROM validate_tsvector_sync();

-- 10. Registrar migration
INSERT INTO schema_migrations (version, description) 
VALUES ('003', 'Criar triggers de sincronização para tsvector')
ON CONFLICT (version) DO UPDATE SET applied_at = CURRENT_TIMESTAMP;

COMMIT;

-- Mensagens informativas
\echo 'Migration 003 aplicada com sucesso!'
\echo ''
\echo 'Triggers criados:'
\echo '  - trigger_sync_content_tsvector (automático em INSERT/UPDATE)'
\echo ''
\echo 'Funções utilitárias disponíveis:'
\echo '  - sync_content_tsvector() - função do trigger'
\echo '  - reprocess_all_tsvectors() - reprocessar todos os chunks'
\echo '  - validate_tsvector_sync() - validar sincronização'
\echo '  - get_fulltext_stats() - estatísticas completas'
\echo '  - test_search_performance() - testar performance'
\echo ''
\echo 'Para validar o sistema:'
\echo 'SELECT * FROM validate_tsvector_sync();'
\echo 'SELECT * FROM get_fulltext_stats();'