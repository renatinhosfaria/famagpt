-- Script de configuração PostgreSQL para busca em português
-- Arquivo: configure_postgresql_portuguese.sql
-- Descrição: Configura PostgreSQL para otimizar busca full-text em português

-- 1. Verificar configurações atuais
\echo 'Configurações atuais do PostgreSQL para busca em texto:'
SELECT name, setting, source, sourcefile 
FROM pg_settings 
WHERE name IN (
    'default_text_search_config',
    'shared_preload_libraries'
);

-- 2. Verificar se configuração portuguesa está disponível
\echo ''
\echo 'Configurações de texto disponíveis:'
SELECT cfgname, cfgowner::regrole 
FROM pg_ts_config 
WHERE cfgname LIKE '%portuguese%' OR cfgname LIKE '%pt%';

-- 3. Configurar português como padrão para a sessão atual
SET default_text_search_config = 'pg_catalog.portuguese';

\echo ''
\echo 'Configuração portuguesa ativada para a sessão atual.'

-- 4. Verificar dicionários disponíveis para português
\echo ''
\echo 'Dicionários disponíveis para português:'
SELECT dictname, dictowner::regrole, dicttemplate::regclass
FROM pg_ts_dict 
WHERE dictname LIKE '%portuguese%' OR dictname LIKE '%pt%';

-- 5. Testar configuração com exemplos do domínio imobiliário
\echo ''
\echo 'Testando busca com termos imobiliários em português:'

-- Teste 1: Termos básicos
SELECT 
    'apartamento casa terreno' as termo_original,
    to_tsvector('portuguese', 'apartamento casa terreno') as tsvector_resultado,
    array_agg(lexeme ORDER BY positions) as lexemas_normalizados
FROM unnest(to_tsvector('portuguese', 'apartamento casa terreno')) as lexeme;

-- Teste 2: Plurais e variações
SELECT 
    'quartos suítes vagas' as termo_original,
    to_tsvector('portuguese', 'quartos suítes vagas') as tsvector_resultado;

-- Teste 3: Query de busca
SELECT 
    'casa com 3 quartos' as query_original,
    plainto_tsquery('portuguese', 'casa com 3 quartos') as query_processada,
    to_tsquery('portuguese', 'casa & quartos') as query_manual;

-- 6. Função para testar qualidade de busca em português
CREATE OR REPLACE FUNCTION test_portuguese_search_quality()
RETURNS TABLE(
    test_case text,
    original_term text,
    processed_query tsquery,
    stemming_quality text,
    recommendation text
) AS $$
DECLARE
    test_cases text[][] := ARRAY[
        ARRAY['Imóveis básicos', 'apartamento casa terreno'],
        ARRAY['Características', 'quartos suítes vagas garagem'],
        ARRAY['Localização', 'centro bairro rua avenida'],
        ARRAY['Valores', 'preço valor custo investimento'],
        ARRAY['Condições', 'novo usado reformado construção'],
        ARRAY['Tamanhos', 'grande pequeno amplo compacto'],
        ARRAY['Qualidade', 'luxo padrão simples sofisticado']
    ];
    test_case_data text[];
    original text;
    processed tsquery;
    quality text;
    rec text;
BEGIN
    FOREACH test_case_data SLICE 1 IN ARRAY test_cases
    LOOP
        original := test_case_data[2];
        processed := plainto_tsquery('portuguese', original);
        
        -- Analisar qualidade do stemming
        IF length(processed::text) < length(original) * 0.5 THEN
            quality := 'Boa - stemming agressivo';
            rec := 'Usar português padrão';
        ELSIF length(processed::text) > length(original) * 0.9 THEN
            quality := 'Baixa - pouco processamento';
            rec := 'Verificar configuração';
        ELSE
            quality := 'Adequada';
            rec := 'Configuração OK';
        END IF;
        
        RETURN QUERY SELECT 
            test_case_data[1], 
            original, 
            processed, 
            quality, 
            rec;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Executar teste de qualidade
\echo ''
\echo 'Análise de qualidade da busca em português:'
SELECT * FROM test_portuguese_search_quality();

-- 7. Criar configuração personalizada para imóveis (opcional)
DO $$
BEGIN
    -- Verificar se configuração customizada já existe
    IF NOT EXISTS (
        SELECT 1 FROM pg_ts_config WHERE cfgname = 'real_estate_portuguese'
    ) THEN
        -- Criar configuração baseada no português padrão
        CREATE TEXT SEARCH CONFIGURATION real_estate_portuguese 
        (COPY = pg_catalog.portuguese);
        
        -- Adicionar dicionário personalizado para termos imobiliários seria aqui
        -- Por ora, usar configuração padrão portuguesa
        
        RAISE NOTICE 'Configuração real_estate_portuguese criada';
    ELSE
        RAISE NOTICE 'Configuração real_estate_portuguese já existe';
    END IF;
EXCEPTION
    WHEN insufficient_privilege THEN
        RAISE NOTICE 'Sem privilégios para criar configuração customizada. Usando português padrão.';
END;
$$;

-- 8. Função para comparar configurações
CREATE OR REPLACE FUNCTION compare_text_search_configs(
    test_text text DEFAULT 'apartamento com 3 quartos e 2 vagas no centro da cidade'
)
RETURNS TABLE(
    config_name text,
    processed_vector tsvector,
    query_simple tsquery,
    token_count integer,
    unique_tokens integer
) AS $$
DECLARE
    configs text[] := ARRAY['pg_catalog.portuguese', 'pg_catalog.simple', 'pg_catalog.english'];
    config_name_var text;
    vector_result tsvector;
    query_result tsquery;
    token_cnt integer;
    unique_cnt integer;
BEGIN
    FOREACH config_name_var IN ARRAY configs
    LOOP
        -- Processar com configuração específica
        EXECUTE format('SELECT to_tsvector(%L, %L)', config_name_var, test_text) 
        INTO vector_result;
        
        EXECUTE format('SELECT plainto_tsquery(%L, %L)', config_name_var, 'apartamento quartos') 
        INTO query_result;
        
        -- Contar tokens
        SELECT array_length(string_to_array(vector_result::text, ' '), 1) INTO token_cnt;
        
        -- Contar tokens únicos
        SELECT count(DISTINCT lexeme) 
        FROM unnest(vector_result) 
        INTO unique_cnt;
        
        RETURN QUERY SELECT 
            config_name_var,
            vector_result,
            query_result,
            COALESCE(token_cnt, 0),
            COALESCE(unique_cnt, 0);
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Comparar configurações
\echo ''
\echo 'Comparação de configurações de busca:'
SELECT * FROM compare_text_search_configs();

-- 9. Estatísticas finais
\echo ''
\echo 'Configuração finalizada!'
\echo 'Configuração ativa:' 
SELECT current_setting('default_text_search_config') as config_ativa;

\echo ''
\echo 'Para aplicar permanentemente no banco de dados:'
\echo 'ALTER DATABASE famagpt_rag SET default_text_search_config = ''pg_catalog.portuguese'';'
\echo ''
\echo 'Para aplicar no postgresql.conf:'
\echo 'default_text_search_config = ''pg_catalog.portuguese'''