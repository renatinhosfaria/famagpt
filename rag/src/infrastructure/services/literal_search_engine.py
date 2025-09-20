"""
Motor de busca literal usando PostgreSQL Full-Text Search
Implementação otimizada para domínio imobiliário em português
"""

import asyncio
import time
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import asyncpg
from shared.src.utils.logging import get_logger

from ...domain.entities.document import SearchResult, DocumentChunk


logger = get_logger("rag.literal_search")


class QueryType(Enum):
    """Tipos de query para otimização específica"""
    GENERIC = "generic"
    PRICE_FOCUSED = "price_focused"
    LOCATION_FOCUSED = "location_focused"
    SPECIFICATION_FOCUSED = "specification_focused"
    CONCEPTUAL = "conceptual"


@dataclass
class SearchMetrics:
    """Métricas de uma busca literal"""
    query_time_ms: float
    results_count: int
    index_hit: bool
    query_complexity: str
    suggested_optimizations: List[str]


class LiteralSearchEngine:
    """Motor de busca literal usando PostgreSQL Full-Text"""
    
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self.search_config = 'portuguese'
        
        # Patterns para domínio imobiliário
        self.price_patterns = re.compile(
            r'R\$|reais|\d+\s*(mil|milhão|milhões)|valor|preço|custo',
            re.IGNORECASE
        )
        self.location_patterns = re.compile(
            r'rua|avenida|av\.|r\.|bairro|centro|uberlândia|mg|setor|quadra|lote',
            re.IGNORECASE
        )
        self.spec_patterns = re.compile(
            r'\d+\s*(quartos?|suítes?|vagas?|m²|metros?|área|construída)',
            re.IGNORECASE
        )
        
        # Cache de queries frequentes (simples em memória)
        self._query_cache: Dict[str, Tuple[List[SearchResult], float]] = {}
        self._cache_max_size = 100
        self._cache_ttl_seconds = 300  # 5 minutos
        
    async def search_chunks(
        self,
        query: str,
        top_k: int = 10,
        min_rank: float = 0.1,
        filters: Optional[Dict[str, Any]] = None,
        highlight: bool = False,
        explain_query: bool = False
    ) -> List[SearchResult]:
        """
        Busca literal em chunks usando full-text search
        
        Args:
            query: Texto de busca
            top_k: Número máximo de resultados
            min_rank: Ranking mínimo (0.0 a 1.0)
            filters: Filtros adicionais
            highlight: Se deve destacar termos encontrados
            explain_query: Se deve incluir explicação da query
            
        Returns:
            Lista de resultados ordenados por relevância
        """
        try:
            # Validar parâmetros
            if not query or len(query.strip()) == 0:
                logger.warning("Query vazia fornecida para busca literal")
                return []
            
            if top_k <= 0 or top_k > 100:
                logger.warning(f"top_k inválido: {top_k}, usando 10")
                top_k = 10
                
            # Verificar cache
            cache_key = self._generate_cache_key(query, top_k, min_rank, filters, highlight)
            cached_result = self._get_from_cache(cache_key)
            if cached_result:
                logger.debug(f"Cache hit para query: {query[:50]}...")
                return cached_result
            
            start_time = time.time()
            
            # Analisar tipo de query para otimização
            query_type = self._analyze_query_type(query)
            logger.debug(f"Query type detected: {query_type.value}")
            
            # Processar e limpar query
            processed_query = self._preprocess_query(query, query_type)
            
            # Construir query SQL otimizada
            sql_query, params = self._build_optimized_query(
                processed_query, query_type, top_k, min_rank, filters, highlight
            )
            
            # Executar busca
            async with self.pool.acquire() as conn:
                if explain_query:
                    # Para debug - mostrar plano de execução
                    explain_result = await conn.fetchval(f"EXPLAIN ANALYZE {sql_query}", *params)
                    logger.debug(f"Query plan: {explain_result}")
                
                rows = await conn.fetch(sql_query, *params)
            
            # Converter para SearchResult
            results = self._convert_rows_to_results(rows, query)
            
            # Métricas de performance
            query_time = time.time() - start_time
            self._log_search_metrics(query, query_type, query_time, len(results), len(rows))
            
            # Adicionar ao cache
            self._add_to_cache(cache_key, results, query_time)
            
            logger.debug(
                f"Literal search completed: {len(results)} results "
                f"for '{query[:50]}...' in {query_time:.3f}s"
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Error in literal search: {str(e)}")
            # Em caso de erro, retornar lista vazia ao invés de falhar
            return []
    
    async def search_with_suggestions(
        self,
        query: str,
        top_k: int = 10,
        suggestion_limit: int = 5
    ) -> Dict[str, Any]:
        """
        Busca com sugestões de termos alternativos
        
        Returns:
            Dict com results, suggestions, e metrics
        """
        try:
            # Busca principal
            results = await self.search_chunks(query, top_k)
            
            # Gerar sugestões se poucos resultados
            suggestions = []
            if len(results) < top_k // 2:
                suggestions = await self.get_search_suggestions(query, suggestion_limit)
            
            # Análise de qualidade da query
            query_analysis = self._analyze_query_quality(query, len(results))
            
            return {
                'results': results,
                'suggestions': suggestions,
                'query_analysis': query_analysis,
                'total_found': len(results),
                'has_suggestions': len(suggestions) > 0
            }
            
        except Exception as e:
            logger.error(f"Error in search with suggestions: {str(e)}")
            return {
                'results': [],
                'suggestions': [],
                'query_analysis': {'quality': 'error', 'message': str(e)},
                'total_found': 0,
                'has_suggestions': False
            }
    
    async def get_search_suggestions(
        self, 
        partial_query: str, 
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Sugestões de busca baseadas em conteúdo existente"""
        try:
            # Preparar query de sugestão
            suggestion_query = """
                WITH query_terms AS (
                    SELECT unnest(string_to_array(lower(trim($1)), ' ')) as term
                ),
                term_stats AS (
                    SELECT 
                        word,
                        nentry,
                        nentry::float / (SELECT sum(nentry) FROM ts_stat($$
                            SELECT content_tsvector FROM rag_document_chunks 
                            WHERE content_tsvector IS NOT NULL
                        $$))::float as frequency
                    FROM ts_stat($$
                        SELECT content_tsvector FROM rag_document_chunks 
                        WHERE content_tsvector IS NOT NULL
                    $$)
                    WHERE char_length(word) > 2
                ),
                similar_terms AS (
                    SELECT 
                        ts.word,
                        ts.nentry,
                        ts.frequency,
                        similarity(ts.word, qt.term) as similarity_score
                    FROM term_stats ts, query_terms qt
                    WHERE similarity(ts.word, qt.term) > 0.3
                    AND ts.word != qt.term
                )
                SELECT 
                    word,
                    nentry as occurrences,
                    round(frequency::numeric, 6) as frequency,
                    round(max(similarity_score)::numeric, 3) as max_similarity
                FROM similar_terms
                GROUP BY word, nentry, frequency
                ORDER BY max_similarity DESC, nentry DESC
                LIMIT $2
            """
            
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(suggestion_query, partial_query, limit)
            
            suggestions = []
            for row in rows:
                suggestions.append({
                    'term': row['word'],
                    'occurrences': row['occurrences'],
                    'frequency': float(row['frequency']),
                    'similarity': float(row['max_similarity']),
                    'suggestion_type': 'similar_term'
                })
            
            # Adicionar sugestões específicas do domínio imobiliário
            domain_suggestions = self._get_domain_suggestions(partial_query)
            suggestions.extend(domain_suggestions)
            
            return suggestions[:limit]
            
        except Exception as e:
            logger.warning(f"Error getting search suggestions: {str(e)}")
            return []
    
    def _analyze_query_type(self, query: str) -> QueryType:
        """Analisa o tipo da query para otimização"""
        query_lower = query.lower()
        
        # Detectar queries focadas em preço
        if self.price_patterns.search(query):
            return QueryType.PRICE_FOCUSED
        
        # Detectar queries focadas em localização
        if self.location_patterns.search(query):
            return QueryType.LOCATION_FOCUSED
        
        # Detectar queries focadas em especificações
        if self.spec_patterns.search(query):
            return QueryType.SPECIFICATION_FOCUSED
        
        # Detectar queries conceituais
        conceptual_terms = ['família', 'tranquilo', 'investimento', 'luxo', 'confortável']
        if any(term in query_lower for term in conceptual_terms):
            return QueryType.CONCEPTUAL
        
        return QueryType.GENERIC
    
    def _preprocess_query(self, query: str, query_type: QueryType) -> str:
        """Processa e otimiza a query baseada no tipo"""
        # Limpar query básica
        query = re.sub(r'\s+', ' ', query.strip())
        
        # Expansões específicas por tipo
        if query_type == QueryType.PRICE_FOCUSED:
            # Normalizar formatos de preço
            query = re.sub(r'R\$\s*(\d+)', r'\1 reais', query)
            query = re.sub(r'(\d+)k', r'\1 mil', query)
        
        elif query_type == QueryType.LOCATION_FOCUSED:
            # Expandir abreviações de localização
            query = re.sub(r'\bav\.\b', 'avenida', query, flags=re.IGNORECASE)
            query = re.sub(r'\br\.\b', 'rua', query, flags=re.IGNORECASE)
            query = re.sub(r'\buberlândia\b', 'uberlândia OR uberaba', query, flags=re.IGNORECASE)
        
        elif query_type == QueryType.SPECIFICATION_FOCUSED:
            # Expandir especificações técnicas
            query = re.sub(r'(\d+)\s*q', r'\1 quartos', query, flags=re.IGNORECASE)
            query = re.sub(r'(\d+)\s*s', r'\1 suites', query, flags=re.IGNORECASE)
            
        return query
    
    def _build_optimized_query(
        self,
        query: str,
        query_type: QueryType,
        top_k: int,
        min_rank: float,
        filters: Optional[Dict[str, Any]],
        highlight: bool
    ) -> Tuple[str, List[Any]]:
        """Constrói query SQL otimizada baseada no tipo"""
        
        # Base da query com joins otimizados
        base_select = """
            SELECT 
                c.id,
                c.document_id,
                c.content,
                c.chunk_index,
                c.start_position,
                c.end_position,
                c.metadata,
                c.created_at,
                d.title as document_title,
                d.metadata as document_metadata,
                ts_rank_cd(
                    c.content_tsvector, 
                    plainto_tsquery($1, $2),
                    32  -- length normalization
                ) as rank_score
        """
        
        # Adicionar highlighting se solicitado
        if highlight:
            base_select += """,
                ts_headline($1, c.content, 
                    plainto_tsquery($1, $2),
                    'MaxWords=30, MinWords=10, ShortWord=3, 
                     HighlightAll=false, StartSel=<mark>, StopSel=</mark>'
                ) as highlighted_content"""
        
        base_from = """
            FROM rag_document_chunks c
            JOIN rag_documents d ON c.document_id = d.id
        """
        
        # WHERE clause com otimizações por tipo
        where_conditions = [
            "c.content_tsvector @@ plainto_tsquery($1, $2)",
            f"ts_rank_cd(c.content_tsvector, plainto_tsquery($1, $2), 32) >= ${len(['config', 'query']) + 1}"
        ]
        
        params = [self.search_config, query, min_rank]
        param_count = 3
        
        # Adicionar filtros específicos por tipo de query
        if query_type == QueryType.PRICE_FOCUSED:
            # Priorizar documentos que mencionam preço
            base_select += ", CASE WHEN c.content ~* 'R\\$|reais|\\d+.*mil' THEN 0.2 ELSE 0.0 END as price_boost"
            
        elif query_type == QueryType.LOCATION_FOCUSED:
            # Usar índice de localização se disponível
            where_conditions.append(f"""
                (c.metadata->>'city' IS NOT NULL 
                 OR c.metadata->>'neighborhood' IS NOT NULL
                 OR c.content ~* 'uberlândia|centro|bairro')
            """)
            
        elif query_type == QueryType.SPECIFICATION_FOCUSED:
            # Priorizar documentos com especificações técnicas
            where_conditions.append(f"c.content ~* '\\d+\\s*(quartos?|suítes?|vagas?|m²)'")
        
        # Adicionar filtros customizados
        if filters:
            filter_conditions, filter_params = self._build_custom_filters(filters, param_count)
            where_conditions.extend(filter_conditions)
            params.extend(filter_params)
            param_count += len(filter_params)
        
        # ORDER BY otimizado por tipo
        order_by = "ORDER BY rank_score DESC"
        if query_type == QueryType.PRICE_FOCUSED:
            order_by = "ORDER BY (rank_score + COALESCE(price_boost, 0)) DESC"
        
        order_by += f", c.created_at DESC LIMIT ${param_count + 1}"
        params.append(top_k)
        
        # Montar query final
        final_query = f"""
            {base_select}
            {base_from}
            WHERE {' AND '.join(where_conditions)}
            {order_by}
        """
        
        return final_query, params
    
    def _build_custom_filters(
        self, 
        filters: Dict[str, Any], 
        param_start: int
    ) -> Tuple[List[str], List[Any]]:
        """Constrói filtros customizados"""
        conditions = []
        params = []
        param_idx = param_start + 1
        
        # Filtro por tipo de documento
        if 'document_type' in filters:
            conditions.append(f"d.document_type = ${param_idx}")
            params.append(filters['document_type'])
            param_idx += 1
        
        # Filtro por documento específico
        if 'document_id' in filters:
            conditions.append(f"c.document_id = ${param_idx}")
            params.append(filters['document_id'])
            param_idx += 1
        
        # Filtro por cidade
        if 'city' in filters:
            conditions.append(f"(c.metadata->>'city' ILIKE ${param_idx} OR d.metadata->>'city' ILIKE ${param_idx})")
            params.append(f"%{filters['city']}%")
            param_idx += 1
        
        # Filtro por faixa de preço
        if 'price_range' in filters:
            price_range = filters['price_range']
            if 'min' in price_range:
                conditions.append(f"(c.metadata->>'price')::numeric >= ${param_idx}")
                params.append(price_range['min'])
                param_idx += 1
            if 'max' in price_range:
                conditions.append(f"(c.metadata->>'price')::numeric <= ${param_idx}")
                params.append(price_range['max'])
                param_idx += 1
        
        # Filtro por data
        if 'created_after' in filters:
            conditions.append(f"c.created_at >= ${param_idx}")
            params.append(filters['created_after'])
            param_idx += 1
        
        return conditions, params
    
    def _convert_rows_to_results(self, rows, original_query: str) -> List[SearchResult]:
        """Converte rows do banco para SearchResult"""
        results = []
        
        for row in rows:
            # Criar chunk
            chunk = DocumentChunk(
                id=row['id'],
                document_id=row['document_id'],
                content=row['content'],
                chunk_index=row['chunk_index'],
                start_position=row['start_position'],
                end_position=row['end_position'],
                metadata=dict(row['metadata'] or {}),
                created_at=row['created_at']
            )
            
            # Adicionar conteúdo destacado se disponível
            if 'highlighted_content' in row and row['highlighted_content']:
                chunk.metadata['highlighted_content'] = row['highlighted_content']
            
            # Criar resultado
            result = SearchResult(
                chunk=chunk,
                similarity_score=float(row['rank_score']),
                document_title=row['document_title'],
                document_metadata=dict(row['document_metadata'] or {})
            )
            
            # Adicionar metadados específicos de busca literal
            result.chunk.metadata.update({
                'search_type': 'literal',
                'original_query': original_query,
                'rank_score': float(row['rank_score'])
            })
            
            results.append(result)
        
        return results
    
    def _get_domain_suggestions(self, query: str) -> List[Dict[str, Any]]:
        """Gera sugestões específicas do domínio imobiliário"""
        suggestions = []
        query_lower = query.lower()
        
        # Sugestões para termos comuns de imóveis
        domain_terms = {
            'apartamento': ['apto', 'flat', 'unidade', 'residencial'],
            'casa': ['residência', 'moradia', 'sobrado'],
            'quarto': ['dormitório', 'suíte', 'aposento'],
            'garagem': ['vaga', 'estacionamento', 'box'],
            'piscina': ['área aquática', 'lazer'],
            'centro': ['região central', 'downtown'],
            'bairro': ['setor', 'região', 'área']
        }
        
        for term, synonyms in domain_terms.items():
            if term in query_lower:
                for synonym in synonyms:
                    suggestions.append({
                        'term': synonym,
                        'suggestion_type': 'domain_synonym',
                        'original_term': term,
                        'occurrences': 0,  # Seria calculado em implementação completa
                        'frequency': 0.0,
                        'similarity': 1.0
                    })
        
        return suggestions
    
    def _analyze_query_quality(self, query: str, results_count: int) -> Dict[str, Any]:
        """Analisa qualidade da query e resultados"""
        quality_score = 0.0
        issues = []
        recommendations = []
        
        # Analisar comprimento da query
        word_count = len(query.split())
        if word_count < 2:
            issues.append("Query muito curta")
            recommendations.append("Use mais palavras-chave específicas")
            quality_score -= 0.3
        elif word_count > 10:
            issues.append("Query muito longa")
            recommendations.append("Tente ser mais específico e conciso")
            quality_score -= 0.2
        else:
            quality_score += 0.3
        
        # Analisar número de resultados
        if results_count == 0:
            issues.append("Nenhum resultado encontrado")
            recommendations.append("Tente termos mais genéricos ou sinônimos")
            quality_score -= 0.5
        elif results_count < 3:
            issues.append("Poucos resultados")
            recommendations.append("Considere expandir a busca")
            quality_score -= 0.2
        else:
            quality_score += 0.4
        
        # Analisar presença de termos específicos
        if self.price_patterns.search(query):
            quality_score += 0.1
        if self.location_patterns.search(query):
            quality_score += 0.1
        if self.spec_patterns.search(query):
            quality_score += 0.1
        
        # Normalizar score
        quality_score = max(0.0, min(1.0, quality_score + 0.5))
        
        # Determinar nível de qualidade
        if quality_score >= 0.8:
            quality_level = "excelente"
        elif quality_score >= 0.6:
            quality_level = "boa"
        elif quality_score >= 0.4:
            quality_level = "regular"
        else:
            quality_level = "baixa"
        
        return {
            'quality_score': round(quality_score, 2),
            'quality_level': quality_level,
            'word_count': word_count,
            'results_count': results_count,
            'issues': issues,
            'recommendations': recommendations,
            'has_domain_terms': any([
                self.price_patterns.search(query),
                self.location_patterns.search(query), 
                self.spec_patterns.search(query)
            ])
        }
    
    # Métodos de cache
    def _generate_cache_key(self, query: str, top_k: int, min_rank: float, 
                          filters: Optional[Dict], highlight: bool) -> str:
        """Gera chave de cache para a query"""
        import hashlib
        
        cache_data = f"{query}:{top_k}:{min_rank}:{str(filters)}:{highlight}"
        return hashlib.md5(cache_data.encode()).hexdigest()
    
    def _get_from_cache(self, cache_key: str) -> Optional[List[SearchResult]]:
        """Recupera resultado do cache se válido"""
        if cache_key in self._query_cache:
            results, timestamp = self._query_cache[cache_key]
            if time.time() - timestamp < self._cache_ttl_seconds:
                return results
            else:
                # Remove entrada expirada
                del self._query_cache[cache_key]
        return None
    
    def _add_to_cache(self, cache_key: str, results: List[SearchResult], query_time: float):
        """Adiciona resultado ao cache"""
        # Limitar tamanho do cache
        if len(self._query_cache) >= self._cache_max_size:
            # Remove entrada mais antiga
            oldest_key = min(self._query_cache.keys(), 
                           key=lambda k: self._query_cache[k][1])
            del self._query_cache[oldest_key]
        
        self._query_cache[cache_key] = (results, time.time())
    
    def _log_search_metrics(self, query: str, query_type: QueryType, 
                          query_time: float, results_count: int, raw_rows: int):
        """Log métricas de busca para monitoramento"""
        logger.info(
            f"Literal search metrics - Query: '{query[:50]}...', "
            f"Type: {query_type.value}, Time: {query_time:.3f}s, "
            f"Results: {results_count}, Raw rows: {raw_rows}"
        )
        
        # Em produção, aqui seria enviado para sistema de métricas
        # como Prometheus, DataDog, etc.
    
    async def get_search_statistics(self) -> Dict[str, Any]:
        """Obtém estatísticas gerais do sistema de busca"""
        try:
            async with self.pool.acquire() as conn:
                # Estatísticas básicas
                stats_query = """
                    SELECT 
                        count(*) as total_chunks,
                        count(DISTINCT document_id) as total_documents,
                        avg(length(content)) as avg_content_length,
                        count(CASE WHEN content_tsvector IS NOT NULL THEN 1 END) as indexed_chunks
                    FROM rag_document_chunks
                """
                
                basic_stats = await conn.fetchrow(stats_query)
                
                # Top termos mais buscados (simulado - seria implementado com log real)
                # Por ora, usar termos mais frequentes no índice
                top_terms_query = """
                    SELECT word, nentry
                    FROM ts_stat($$
                        SELECT content_tsvector FROM rag_document_chunks 
                        WHERE content_tsvector IS NOT NULL
                    $$)
                    WHERE char_length(word) > 3
                    ORDER BY nentry DESC
                    LIMIT 10
                """
                
                top_terms = await conn.fetch(top_terms_query)
                
                return {
                    'total_chunks': basic_stats['total_chunks'],
                    'total_documents': basic_stats['total_documents'],
                    'avg_content_length': float(basic_stats['avg_content_length'] or 0),
                    'indexed_chunks': basic_stats['indexed_chunks'],
                    'index_coverage': (
                        basic_stats['indexed_chunks'] / basic_stats['total_chunks'] 
                        if basic_stats['total_chunks'] > 0 else 0
                    ),
                    'top_terms': [
                        {'term': row['word'], 'frequency': row['nentry']} 
                        for row in top_terms
                    ],
                    'cache_size': len(self._query_cache),
                    'cache_hit_ratio': 0.0  # Seria calculado com métricas reais
                }
                
        except Exception as e:
            logger.error(f"Error getting search statistics: {str(e)}")
            return {
                'error': str(e),
                'total_chunks': 0,
                'total_documents': 0
            }