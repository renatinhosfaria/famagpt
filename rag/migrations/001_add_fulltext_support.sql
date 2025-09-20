-- Migration 001: Adicionar suporte a busca full-text
-- Data: 2024-01-XX
-- Descrição: Adiciona colunas e configurações necessárias para busca literal híbrida

-- Começar transação
BEGIN;

-- 1. Verificar se extensões necessárias estão disponíveis
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 2. Adicionar coluna tsvector para busca full-text
-- Usar IF NOT EXISTS para evitar erro em re-execuções
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='rag_document_chunks' AND column_name='content_tsvector'
    ) THEN
        ALTER TABLE rag_document_chunks 
        ADD COLUMN content_tsvector tsvector;
    END IF;
END
$$;

-- 3. Adicionar coluna para conteúdo limpo (backup do original)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='rag_document_chunks' AND column_name='content_clean'
    ) THEN
        ALTER TABLE rag_document_chunks 
        ADD COLUMN content_clean text;
    END IF;
END
$$;

-- 4. Popular dados existentes com configuração portuguesa
-- Primeiro, verificar se há dados para processar
DO $$
DECLARE
    chunk_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO chunk_count FROM rag_document_chunks 
    WHERE content_tsvector IS NULL;
    
    IF chunk_count > 0 THEN
        RAISE NOTICE 'Processando % chunks existentes para busca full-text...', chunk_count;
        
        -- Atualizar em lotes para evitar lock prolongado
        UPDATE rag_document_chunks 
        SET 
            content_tsvector = to_tsvector('portuguese', content),
            content_clean = content
        WHERE content_tsvector IS NULL;
        
        RAISE NOTICE 'Processamento concluído para % chunks', chunk_count;
    ELSE
        RAISE NOTICE 'Nenhum chunk pendente para processamento';
    END IF;
END
$$;

-- 5. Tornar coluna NOT NULL após popular (apenas se não estiver já definida)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='rag_document_chunks' 
        AND column_name='content_tsvector' 
        AND is_nullable='YES'
    ) THEN
        ALTER TABLE rag_document_chunks 
        ALTER COLUMN content_tsvector SET NOT NULL;
    END IF;
END
$$;

-- 6. Configurar default text search config para português na sessão
SET default_text_search_config = 'pg_catalog.portuguese';

-- 7. Criar função de utilidade para verificar configuração
CREATE OR REPLACE FUNCTION check_fulltext_config()
RETURNS TABLE(
    config_name text,
    is_portuguese boolean,
    chunks_with_tsvector bigint,
    total_chunks bigint
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        current_setting('default_text_search_config') as config_name,
        current_setting('default_text_search_config') = 'pg_catalog.portuguese' as is_portuguese,
        (SELECT count(*) FROM rag_document_chunks WHERE content_tsvector IS NOT NULL) as chunks_with_tsvector,
        (SELECT count(*) FROM rag_document_chunks) as total_chunks;
END;
$$ LANGUAGE plpgsql;

-- 8. Executar verificação
SELECT * FROM check_fulltext_config();

-- Registrar migration
DO $$
BEGIN
    -- Criar tabela de migrations se não existir
    CREATE TABLE IF NOT EXISTS schema_migrations (
        id SERIAL PRIMARY KEY,
        version VARCHAR(50) UNIQUE NOT NULL,
        description TEXT,
        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    -- Registrar esta migration
    INSERT INTO schema_migrations (version, description) 
    VALUES ('001', 'Adicionar suporte a busca full-text')
    ON CONFLICT (version) DO NOTHING;
END
$$;

COMMIT;

-- Mensagem final
\echo 'Migration 001 aplicada com sucesso!'
\echo 'Próximo passo: executar 002_create_fulltext_indexes.sql'