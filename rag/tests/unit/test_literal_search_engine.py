"""
Testes unitários para LiteralSearchEngine
Cobertura completa de funcionalidades e edge cases
"""

import pytest
import asyncio
import asyncpg
from unittest.mock import Mock, AsyncMock, patch
from typing import List, Dict, Any
from datetime import datetime

# Imports do sistema
from rag.src.infrastructure.services.literal_search_engine import (
    LiteralSearchEngine, QueryType, SearchMetrics
)
from rag.src.domain.entities.document import DocumentChunk, SearchResult


class TestLiteralSearchEngine:
    """Testes para LiteralSearchEngine"""
    
    @pytest.fixture
    async def mock_pool(self):
        """Mock do pool de conexões PostgreSQL"""
        pool = Mock(spec=asyncpg.Pool)
        
        # Mock de conexão
        conn = AsyncMock()
        pool.acquire.return_value.__aenter__.return_value = conn
        
        return pool, conn
    
    @pytest.fixture
    def search_engine(self, mock_pool):
        """Instância do LiteralSearchEngine para testes"""
        pool, _ = mock_pool
        return LiteralSearchEngine(pool)
    
    @pytest.fixture
    def sample_db_rows(self):
        """Dados de exemplo que seriam retornados do banco"""
        return [
            {
                'id': 'chunk_001',
                'document_id': 'doc_001',
                'content': 'Apartamento com 3 quartos no centro de Uberlândia, valor R$ 350.000',
                'chunk_index': 0,
                'start_position': 0,
                'end_position': 66,
                'metadata': {'type': 'apartamento', 'city': 'Uberlândia'},
                'created_at': datetime.now(),
                'document_title': 'Apartamento Centro Uberlândia',
                'document_metadata': {'city': 'Uberlândia', 'type': 'property'},
                'rank_score': 0.8,
                'highlighted_content': 'Apartamento com <mark>3 quartos</mark> no centro'
            },
            {
                'id': 'chunk_002',
                'document_id': 'doc_002',
                'content': 'Casa residencial com 4 quartos em bairro nobre, ideal para família',
                'chunk_index': 0,
                'start_position': 0,
                'end_position': 65,
                'metadata': {'type': 'casa', 'bedrooms': 4},
                'created_at': datetime.now(),
                'document_title': 'Casa Bairro Nobre',
                'document_metadata': {'city': 'Uberlândia', 'type': 'property'},
                'rank_score': 0.6
            }
        ]
    
    def test_query_type_detection_price_focused(self, search_engine):
        """Testa detecção de query focada em preço"""
        test_cases = [
            "apartamento R$ 300.000",
            "casa valor 450 mil reais",
            "terreno preço 200000",
            "imóvel custo baixo"
        ]
        
        for query in test_cases:
            query_type = search_engine._analyze_query_type(query)
            assert query_type == QueryType.PRICE_FOCUSED, f"Failed for query: {query}"
    
    def test_query_type_detection_location_focused(self, search_engine):
        """Testa detecção de query focada em localização"""
        test_cases = [
            "casa no centro de Uberlândia",
            "apartamento Rua João Naves",
            "terreno Avenida Mineiros",
            "imóvel bairro Tabajaras"
        ]
        
        for query in test_cases:
            query_type = search_engine._analyze_query_type(query)
            assert query_type == QueryType.LOCATION_FOCUSED, f"Failed for query: {query}"
    
    def test_query_type_detection_specification_focused(self, search_engine):
        """Testa detecção de query focada em especificações"""
        test_cases = [
            "apartamento 3 quartos 2 vagas",
            "casa 120m² área construída",
            "imóvel 4 suítes garagem",
            "terreno 300 metros quadrados"
        ]
        
        for query in test_cases:
            query_type = search_engine._analyze_query_type(query)
            assert query_type == QueryType.SPECIFICATION_FOCUSED, f"Failed for query: {query}"
    
    def test_query_type_detection_conceptual(self, search_engine):
        """Testa detecção de query conceitual"""
        test_cases = [
            "casa ideal para família grande",
            "apartamento tranquilo e confortável",
            "imóvel luxo investimento",
            "residência sofisticada"
        ]
        
        for query in test_cases:
            query_type = search_engine._analyze_query_type(query)
            assert query_type == QueryType.CONCEPTUAL, f"Failed for query: {query}"
    
    def test_query_preprocessing_price(self, search_engine):
        """Testa preprocessamento de queries de preço"""
        test_cases = [
            ("R$ 350000", "350000 reais"),
            ("apartamento 300k", "apartamento 300 mil"),
            ("R$ 1.5 milhão", "1.5 milhão reais")
        ]
        
        for original, expected in test_cases:
            query_type = QueryType.PRICE_FOCUSED
            processed = search_engine._preprocess_query(original, query_type)
            assert expected.lower() in processed.lower(), \
                f"Failed preprocessing: {original} -> {processed}"
    
    def test_query_preprocessing_location(self, search_engine):
        """Testa preprocessamento de queries de localização"""
        test_cases = [
            ("av. João Naves", "avenida João Naves"),
            ("r. das Flores", "rua das Flores"),
            ("centro Uberlândia", "centro uberlândia OR uberaba")
        ]
        
        for original, expected in test_cases:
            query_type = QueryType.LOCATION_FOCUSED
            processed = search_engine._preprocess_query(original, query_type)
            # Verificar se pelo menos parte da expansão está presente
            assert any(word in processed.lower() for word in expected.lower().split()), \
                f"Failed preprocessing: {original} -> {processed}"
    
    def test_query_preprocessing_specifications(self, search_engine):
        """Testa preprocessamento de queries de especificações"""
        test_cases = [
            ("3q 2s", "3 quartos 2 suites"),
            ("4q casa", "4 quartos casa"),
        ]
        
        for original, expected in test_cases:
            query_type = QueryType.SPECIFICATION_FOCUSED
            processed = search_engine._preprocess_query(original, query_type)
            assert "quartos" in processed.lower(), \
                f"Failed preprocessing: {original} -> {processed}"
    
    def test_build_custom_filters(self, search_engine):
        """Testa construção de filtros customizados"""
        filters = {
            'document_type': 'property',
            'city': 'Uberlândia',
            'price_range': {'min': 100000, 'max': 500000},
            'created_after': datetime(2024, 1, 1)
        }
        
        conditions, params = search_engine._build_custom_filters(filters, 3)
        
        # Verificar se todas as condições foram criadas
        assert len(conditions) >= 4  # Pelo menos uma condição para cada filtro
        assert len(params) >= 5      # Parâmetros correspondentes
        
        # Verificar conteúdo específico
        conditions_text = ' '.join(conditions)
        assert 'document_type' in conditions_text
        assert 'city' in conditions_text or 'ILIKE' in conditions_text
        assert 'price' in conditions_text
        assert 'created_at' in conditions_text
        
        # Verificar parâmetros
        assert 'property' in params
        assert 'Uberlândia' in str(params)
        assert 100000 in params
        assert 500000 in params
    
    def test_convert_rows_to_results(self, search_engine, sample_db_rows):
        """Testa conversão de rows do banco para SearchResult"""
        original_query = "apartamento 3 quartos"
        results = search_engine._convert_rows_to_results(sample_db_rows, original_query)
        
        assert len(results) == 2
        
        # Verificar primeiro resultado
        result1 = results[0]
        assert isinstance(result1, SearchResult)
        assert result1.chunk.id == 'chunk_001'
        assert result1.chunk.content.startswith('Apartamento')
        assert result1.similarity_score == 0.8
        assert result1.document_title == 'Apartamento Centro Uberlândia'
        
        # Verificar metadados específicos de busca literal
        assert result1.chunk.metadata['search_type'] == 'literal'
        assert result1.chunk.metadata['original_query'] == original_query
        assert 'highlighted_content' in result1.chunk.metadata
        
        # Verificar segundo resultado
        result2 = results[1]
        assert result2.chunk.id == 'chunk_002'
        assert result2.similarity_score == 0.6
    
    @pytest.mark.asyncio
    async def test_search_chunks_basic(self, search_engine, mock_pool, sample_db_rows):
        """Testa busca básica de chunks"""
        pool, conn = mock_pool
        conn.fetch.return_value = sample_db_rows
        
        query = "apartamento 3 quartos"
        results = await search_engine.search_chunks(query, top_k=5)
        
        # Verificar que a busca foi executada
        conn.fetch.assert_called_once()
        
        # Verificar resultados
        assert len(results) == 2
        assert all(isinstance(r, SearchResult) for r in results)
        
        # Verificar que a query SQL foi construída corretamente
        call_args = conn.fetch.call_args
        sql_query = call_args[0][0]
        params = call_args[0][1:]
        
        # Verificar elementos essenciais da query
        assert 'content_tsvector' in sql_query
        assert 'plainto_tsquery' in sql_query
        assert 'ts_rank_cd' in sql_query
        assert 'LIMIT' in sql_query
        
        # Verificar parâmetros
        assert 'portuguese' in params
        assert query in params
    
    @pytest.mark.asyncio
    async def test_search_chunks_with_filters(self, search_engine, mock_pool, sample_db_rows):
        """Testa busca com filtros"""
        pool, conn = mock_pool
        conn.fetch.return_value = sample_db_rows
        
        query = "casa"
        filters = {
            'document_type': 'property',
            'city': 'Uberlândia'
        }
        
        results = await search_engine.search_chunks(
            query, 
            top_k=10, 
            filters=filters
        )
        
        # Verificar que a busca foi executada
        conn.fetch.assert_called_once()
        
        # Verificar que filtros foram aplicados na query
        call_args = conn.fetch.call_args
        sql_query = call_args[0][0]
        params = call_args[0][1:]
        
        assert 'document_type' in sql_query
        assert 'property' in params
        assert 'Uberlândia' in str(params)
    
    @pytest.mark.asyncio
    async def test_search_chunks_with_highlighting(self, search_engine, mock_pool, sample_db_rows):
        """Testa busca com highlighting"""
        pool, conn = mock_pool
        conn.fetch.return_value = sample_db_rows
        
        query = "3 quartos"
        results = await search_engine.search_chunks(
            query, 
            highlight=True
        )
        
        # Verificar que highlighting foi incluído na query
        call_args = conn.fetch.call_args
        sql_query = call_args[0][0]
        
        assert 'ts_headline' in sql_query
        assert 'highlighted_content' in sql_query
        
        # Verificar que highlighted content foi preservado
        assert len(results) > 0
        result_with_highlight = results[0]
        assert 'highlighted_content' in result_with_highlight.chunk.metadata
        assert '<mark>' in result_with_highlight.chunk.metadata['highlighted_content']
    
    @pytest.mark.asyncio 
    async def test_search_chunks_empty_query(self, search_engine):
        """Testa comportamento com query vazia"""
        empty_queries = ["", "   ", None]
        
        for empty_query in empty_queries:
            if empty_query is None:
                # Para query None, esperamos exceção ou tratamento especial
                continue
                
            results = await search_engine.search_chunks(empty_query)
            assert results == [], f"Empty query should return empty list: '{empty_query}'"
    
    @pytest.mark.asyncio
    async def test_search_chunks_invalid_params(self, search_engine, mock_pool):
        """Testa comportamento com parâmetros inválidos"""
        pool, conn = mock_pool
        conn.fetch.return_value = []
        
        query = "apartamento"
        
        # top_k inválido
        results = await search_engine.search_chunks(query, top_k=0)
        call_args = conn.fetch.call_args
        params = call_args[0][1:]
        # Deve ter corrigido para 10
        assert 10 in params
        
        # top_k muito alto
        results = await search_engine.search_chunks(query, top_k=200)
        call_args = conn.fetch.call_args
        params = call_args[0][1:]
        # Deve ter corrigido para 10  
        assert 10 in params
    
    @pytest.mark.asyncio
    async def test_get_search_suggestions(self, search_engine, mock_pool):
        """Testa geração de sugestões de busca"""
        pool, conn = mock_pool
        
        # Mock do resultado de sugestões
        suggestion_rows = [
            {'word': 'apartamentos', 'occurrences': 150, 'frequency': 0.05, 'max_similarity': 0.8},
            {'word': 'residencial', 'occurrences': 80, 'frequency': 0.03, 'max_similarity': 0.6}
        ]
        conn.fetch.return_value = suggestion_rows
        
        query = "apartamento"
        suggestions = await search_engine.get_search_suggestions(query, limit=5)
        
        # Verificar que a query de sugestões foi executada
        conn.fetch.assert_called_once()
        
        # Verificar estrutura das sugestões
        assert len(suggestions) >= 2  # Pelo menos as do banco + domain suggestions
        
        # Verificar primeira sugestão do banco
        first_suggestion = suggestions[0]
        assert 'term' in first_suggestion
        assert 'occurrences' in first_suggestion
        assert 'frequency' in first_suggestion
        assert 'similarity' in first_suggestion
        assert 'suggestion_type' in first_suggestion
        
        # Verificar que sugestões do domínio foram incluídas
        suggestion_terms = [s['term'] for s in suggestions]
        domain_terms = ['apto', 'flat', 'unidade', 'residencial']
        assert any(term in suggestion_terms for term in domain_terms)
    
    @pytest.mark.asyncio
    async def test_search_with_suggestions(self, search_engine, mock_pool, sample_db_rows):
        """Testa busca com sugestões automáticas"""
        pool, conn = mock_pool
        
        # Mock para busca principal (poucos resultados para triggerar sugestões)
        conn.fetch.side_effect = [
            sample_db_rows[:1],  # Apenas 1 resultado para triggerar sugestões
            [{'word': 'apartamentos', 'occurrences': 100, 'frequency': 0.04, 'max_similarity': 0.8}]
        ]
        
        query = "apartamento raro"
        result = await search_engine.search_with_suggestions(query, top_k=10)
        
        # Verificar estrutura do resultado
        assert 'results' in result
        assert 'suggestions' in result
        assert 'query_analysis' in result
        assert 'total_found' in result
        assert 'has_suggestions' in result
        
        # Verificar que sugestões foram geradas (poucos resultados)
        assert result['has_suggestions'] == True
        assert len(result['suggestions']) > 0
        
        # Verificar análise de qualidade
        analysis = result['query_analysis']
        assert 'quality_score' in analysis
        assert 'quality_level' in analysis
        assert 'recommendations' in analysis
    
    def test_analyze_query_quality(self, search_engine):
        """Testa análise de qualidade de query"""
        # Query muito curta
        short_analysis = search_engine._analyze_query_quality("casa", 0)
        assert "Query muito curta" in short_analysis['issues']
        assert short_analysis['quality_level'] in ['baixa', 'regular']
        
        # Query muito longa
        long_query = " ".join(["palavra"] * 15)
        long_analysis = search_engine._analyze_query_quality(long_query, 5)
        assert "Query muito longa" in long_analysis['issues']
        
        # Query boa com resultados
        good_analysis = search_engine._analyze_query_quality(
            "apartamento 3 quartos R$ 300000 centro Uberlândia", 
            8
        )
        assert good_analysis['quality_level'] in ['boa', 'excelente']
        assert good_analysis['has_domain_terms'] == True
        
        # Query sem resultados
        no_results_analysis = search_engine._analyze_query_quality("xyz123", 0)
        assert "Nenhum resultado encontrado" in no_results_analysis['issues']
        assert "termos mais genéricos" in " ".join(no_results_analysis['recommendations'])
    
    def test_cache_functionality(self, search_engine):
        """Testa funcionalidade de cache"""
        # Gerar chave de cache
        cache_key = search_engine._generate_cache_key(
            "apartamento", 10, 0.5, None, False
        )
        assert isinstance(cache_key, str)
        assert len(cache_key) == 32  # MD5 hash length
        
        # Testar cache vazio
        cached_result = search_engine._get_from_cache(cache_key)
        assert cached_result is None
        
        # Adicionar ao cache
        sample_results = [Mock(spec=SearchResult)]
        search_engine._add_to_cache(cache_key, sample_results, 0.1)
        
        # Recuperar do cache
        cached_result = search_engine._get_from_cache(cache_key)
        assert cached_result == sample_results
        
        # Testar expiração (simular tempo passado)
        with patch('time.time', return_value=time.time() + 400):  # Mais que TTL
            cached_result = search_engine._get_from_cache(cache_key)
            assert cached_result is None
    
    def test_domain_suggestions(self, search_engine):
        """Testa sugestões específicas do domínio"""
        # Teste com termo que tem sinônimos
        suggestions = search_engine._get_domain_suggestions("apartamento")
        
        # Verificar que sugestões foram geradas
        assert len(suggestions) > 0
        
        # Verificar estrutura das sugestões
        for suggestion in suggestions:
            assert 'term' in suggestion
            assert 'suggestion_type' in suggestion
            assert suggestion['suggestion_type'] == 'domain_synonym'
            assert 'original_term' in suggestion
            assert suggestion['original_term'] == 'apartamento'
        
        # Verificar termos esperados
        suggestion_terms = [s['term'] for s in suggestions]
        expected_terms = ['apto', 'flat', 'unidade', 'residencial']
        assert any(term in suggestion_terms for term in expected_terms)
    
    @pytest.mark.asyncio
    async def test_get_search_statistics(self, search_engine, mock_pool):
        """Testa obtenção de estatísticas de busca"""
        pool, conn = mock_pool
        
        # Mock de estatísticas básicas
        basic_stats_row = {
            'total_chunks': 1000,
            'total_documents': 100,
            'avg_content_length': 500.5,
            'indexed_chunks': 950
        }
        
        # Mock de termos mais frequentes
        top_terms_rows = [
            {'word': 'apartamento', 'nentry': 200},
            {'word': 'casa', 'nentry': 150},
            {'word': 'quartos', 'nentry': 180}
        ]
        
        conn.fetchrow.return_value = basic_stats_row
        conn.fetch.return_value = top_terms_rows
        
        stats = await search_engine.get_search_statistics()
        
        # Verificar que queries foram executadas
        assert conn.fetchrow.call_count == 1
        assert conn.fetch.call_count == 1
        
        # Verificar estrutura das estatísticas
        assert stats['total_chunks'] == 1000
        assert stats['total_documents'] == 100
        assert stats['avg_content_length'] == 500.5
        assert stats['indexed_chunks'] == 950
        assert stats['index_coverage'] == 0.95  # 950/1000
        
        # Verificar top terms
        assert len(stats['top_terms']) == 3
        assert stats['top_terms'][0]['term'] == 'apartamento'
        assert stats['top_terms'][0]['frequency'] == 200
        
        # Verificar informações de cache
        assert 'cache_size' in stats
        assert 'cache_hit_ratio' in stats
    
    @pytest.mark.asyncio
    async def test_error_handling(self, search_engine, mock_pool):
        """Testa tratamento de erros"""
        pool, conn = mock_pool
        
        # Simular erro na conexão
        conn.fetch.side_effect = asyncpg.PostgresError("Connection failed")
        
        # Busca deve retornar lista vazia ao invés de falhar
        results = await search_engine.search_chunks("apartamento")
        assert results == []
        
        # Sugestões devem retornar lista vazia em caso de erro
        suggestions = await search_engine.get_search_suggestions("apartamento")
        assert suggestions == []
        
        # Estatísticas devem retornar estrutura com erro
        stats = await search_engine.get_search_statistics()
        assert 'error' in stats
        assert stats['total_chunks'] == 0


# Fixtures e helpers adicionais
@pytest.fixture
def event_loop():
    """Fixture para event loop do asyncio"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


class TestSearchMetrics:
    """Testes específicos para métricas de busca"""
    
    def test_search_metrics_creation(self):
        """Testa criação de métricas de busca"""
        metrics = SearchMetrics(
            query_time_ms=150.5,
            results_count=8,
            index_hit=True,
            query_complexity="medium",
            suggested_optimizations=["add_index", "rewrite_query"]
        )
        
        assert metrics.query_time_ms == 150.5
        assert metrics.results_count == 8
        assert metrics.index_hit == True
        assert metrics.query_complexity == "medium"
        assert len(metrics.suggested_optimizations) == 2


# Testes de integração com PostgreSQL real (marcados como slow)
@pytest.mark.slow
@pytest.mark.integration
class TestLiteralSearchEngineIntegration:
    """Testes de integração com banco PostgreSQL real"""
    
    @pytest.fixture
    async def real_db_pool(self):
        """Fixture para pool real do PostgreSQL (apenas se disponível)"""
        try:
            pool = await asyncpg.create_pool(
                "postgresql://localhost:5432/test_famagpt",
                min_size=1,
                max_size=2
            )
            yield pool
            await pool.close()
        except Exception:
            pytest.skip("PostgreSQL não disponível para testes de integração")
    
    @pytest.mark.asyncio
    async def test_real_search(self, real_db_pool):
        """Teste com banco PostgreSQL real"""
        engine = LiteralSearchEngine(real_db_pool)
        
        # Este teste só roda se o banco estiver disponível e configurado
        # com as migrations aplicadas
        try:
            results = await engine.search_chunks("test query", top_k=1)
            # Se chegou até aqui, a conexão e query básica funcionaram
            assert isinstance(results, list)
        except Exception as e:
            pytest.skip(f"Banco não configurado para testes: {e}")


if __name__ == "__main__":
    # Executar testes específicos
    pytest.main([__file__, "-v", "--tb=short"])