"""
Algoritmos de fusão para combinar resultados de busca semântica e literal
Implementa RRF (Reciprocal Rank Fusion) e Weighted Score Fusion
"""

import math
import statistics
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum

from shared.src.utils.logging import get_logger
from ...domain.entities.document import SearchResult, DocumentChunk


logger = get_logger("rag.result_fusion")


class FusionMethod(Enum):
    """Métodos de fusão disponíveis"""
    RRF = "rrf"                    # Reciprocal Rank Fusion
    WEIGHTED = "weighted"          # Weighted Score Fusion
    ADAPTIVE = "adaptive"          # Fusão adaptativa baseada na query
    BAYESIAN = "bayesian"          # Fusão Bayesiana (experimental)


@dataclass
class FusionParams:
    """Parâmetros para algoritmos de fusão"""
    method: FusionMethod = FusionMethod.RRF
    
    # Parâmetros RRF
    rrf_k: int = 60                # Parâmetro k do RRF
    
    # Parâmetros Weighted
    semantic_weight: float = 0.6
    literal_weight: float = 0.4
    
    # Parâmetros Adaptive
    auto_adjust_weights: bool = True
    query_analysis: Optional[Dict[str, Any]] = None
    
    # Parâmetros gerais
    normalize_scores: bool = True
    boost_exact_matches: bool = True
    exact_match_boost: float = 0.1
    
    # Parâmetros de qualidade
    min_fusion_score: float = 0.0
    diversity_penalty: float = 0.0  # Penalizar resultados muito similares
    
    def __post_init__(self):
        """Validar parâmetros após inicialização"""
        if self.semantic_weight + self.literal_weight != 1.0:
            # Normalizar pesos se necessário
            total = self.semantic_weight + self.literal_weight
            if total > 0:
                self.semantic_weight /= total
                self.literal_weight /= total
            else:
                self.semantic_weight = 0.6
                self.literal_weight = 0.4
        
        # Validar limites
        self.rrf_k = max(1, min(1000, self.rrf_k))
        self.exact_match_boost = max(0.0, min(1.0, self.exact_match_boost))
        self.diversity_penalty = max(0.0, min(1.0, self.diversity_penalty))


@dataclass
class FusionResult:
    """Resultado da fusão com metadados"""
    fused_results: List[SearchResult]
    fusion_method: FusionMethod
    fusion_params: FusionParams
    fusion_metrics: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Calcular métricas básicas após criação"""
        if not self.fusion_metrics:
            self.fusion_metrics = {
                'total_results': len(self.fused_results),
                'avg_fusion_score': self._calculate_avg_score(),
                'score_distribution': self._calculate_score_distribution(),
                'diversity_score': self._calculate_diversity()
            }
    
    def _calculate_avg_score(self) -> float:
        """Calcular score médio dos resultados"""
        if not self.fused_results:
            return 0.0
        scores = [r.similarity_score for r in self.fused_results]
        return sum(scores) / len(scores)
    
    def _calculate_score_distribution(self) -> Dict[str, float]:
        """Calcular distribuição de scores"""
        if not self.fused_results:
            return {'min': 0, 'max': 0, 'std': 0}
        
        scores = [r.similarity_score for r in self.fused_results]
        return {
            'min': min(scores),
            'max': max(scores),
            'std': statistics.stdev(scores) if len(scores) > 1 else 0
        }
    
    def _calculate_diversity(self) -> float:
        """Calcular diversidade dos resultados (baseado em documentos únicos)"""
        if not self.fused_results:
            return 0.0
        
        unique_docs = set(r.chunk.document_id for r in self.fused_results)
        return len(unique_docs) / len(self.fused_results)


class HybridResultFusion:
    """Classe principal para fusão de resultados híbrida"""
    
    def __init__(self):
        self.fusion_cache: Dict[str, FusionResult] = {}
        self.cache_size_limit = 100
    
    def fuse_results(
        self,
        semantic_results: List[SearchResult],
        literal_results: List[SearchResult],
        params: Optional[FusionParams] = None
    ) -> FusionResult:
        """
        Funde resultados semânticos e literais usando método especificado
        
        Args:
            semantic_results: Resultados da busca semântica
            literal_results: Resultados da busca literal
            params: Parâmetros de fusão
            
        Returns:
            FusionResult com resultados fundidos e métricas
        """
        try:
            if params is None:
                params = FusionParams()
            
            logger.debug(
                f"Fusão iniciada: {len(semantic_results)} semânticos, "
                f"{len(literal_results)} literais, método: {params.method.value}"
            )
            
            # Verificar cache
            cache_key = self._generate_cache_key(semantic_results, literal_results, params)
            if cache_key in self.fusion_cache:
                logger.debug("Cache hit para fusão")
                return self.fusion_cache[cache_key]
            
            # Pré-processar resultados
            semantic_processed = self._preprocess_results(semantic_results, 'semantic')
            literal_processed = self._preprocess_results(literal_results, 'literal')
            
            # Escolher método de fusão
            if params.method == FusionMethod.RRF:
                fused_results = self._reciprocal_rank_fusion(
                    semantic_processed, literal_processed, params
                )
            elif params.method == FusionMethod.WEIGHTED:
                fused_results = self._weighted_score_fusion(
                    semantic_processed, literal_processed, params
                )
            elif params.method == FusionMethod.ADAPTIVE:
                fused_results = self._adaptive_fusion(
                    semantic_processed, literal_processed, params
                )
            elif params.method == FusionMethod.BAYESIAN:
                fused_results = self._bayesian_fusion(
                    semantic_processed, literal_processed, params
                )
            else:
                raise ValueError(f"Método de fusão não suportado: {params.method}")
            
            # Pós-processamento
            final_results = self._postprocess_results(fused_results, params)
            
            # Criar resultado final
            fusion_result = FusionResult(
                fused_results=final_results,
                fusion_method=params.method,
                fusion_params=params
            )
            
            # Adicionar ao cache
            self._add_to_cache(cache_key, fusion_result)
            
            logger.info(
                f"Fusão concluída: {len(final_results)} resultados finais, "
                f"score médio: {fusion_result.fusion_metrics['avg_fusion_score']:.3f}"
            )
            
            return fusion_result
            
        except Exception as e:
            logger.error(f"Erro na fusão de resultados: {str(e)}")
            # Em caso de erro, retornar resultados semânticos como fallback
            fallback_results = semantic_results[:10] if semantic_results else literal_results[:10]
            return FusionResult(
                fused_results=fallback_results,
                fusion_method=FusionMethod.RRF,
                fusion_params=params or FusionParams(),
                fusion_metrics={'error': str(e)}
            )
    
    def _reciprocal_rank_fusion(
        self,
        semantic_results: List[SearchResult],
        literal_results: List[SearchResult],
        params: FusionParams
    ) -> List[SearchResult]:
        """
        Implementa Reciprocal Rank Fusion (RRF)
        
        RRF Score = 1/(k + rank_semantic) + 1/(k + rank_literal)
        
        Args:
            semantic_results: Resultados semânticos ordenados por relevância
            literal_results: Resultados literais ordenados por relevância
            params: Parâmetros de fusão
            
        Returns:
            Lista de resultados fusionados ordenados por RRF score
        """
        logger.debug(f"Aplicando RRF com k={params.rrf_k}")
        
        # Mapear chunk_id -> resultado unificado
        unified_results = {}
        
        # Processar resultados semânticos
        for rank, result in enumerate(semantic_results):
            chunk_id = result.chunk.id
            rrf_score = 1.0 / (params.rrf_k + rank + 1)
            
            unified_results[chunk_id] = {
                'result': result,
                'semantic_rank': rank + 1,
                'semantic_score': result.similarity_score,
                'rrf_semantic': rrf_score,
                'rrf_total': rrf_score,
                'literal_rank': None,
                'literal_score': 0.0,
                'rrf_literal': 0.0,
                'source_types': {'semantic'}
            }
        
        # Processar resultados literais
        for rank, result in enumerate(literal_results):
            chunk_id = result.chunk.id
            rrf_score = 1.0 / (params.rrf_k + rank + 1)
            
            if chunk_id in unified_results:
                # Combinar com resultado semântico existente
                unified_results[chunk_id]['rrf_total'] += rrf_score
                unified_results[chunk_id]['literal_rank'] = rank + 1
                unified_results[chunk_id]['literal_score'] = result.similarity_score
                unified_results[chunk_id]['rrf_literal'] = rrf_score
                unified_results[chunk_id]['source_types'].add('literal')
                
                # Usar o resultado com melhor score original
                if result.similarity_score > unified_results[chunk_id]['result'].similarity_score:
                    unified_results[chunk_id]['result'] = result
            else:
                # Novo resultado apenas literal
                unified_results[chunk_id] = {
                    'result': result,
                    'semantic_rank': None,
                    'semantic_score': 0.0,
                    'rrf_semantic': 0.0,
                    'literal_rank': rank + 1,
                    'literal_score': result.similarity_score,
                    'rrf_literal': rrf_score,
                    'rrf_total': rrf_score,
                    'source_types': {'literal'}
                }
        
        # Aplicar boost para matches exatos se configurado
        if params.boost_exact_matches:
            self._apply_exact_match_boost(unified_results, params)
        
        # Ordenar por RRF score combinado
        sorted_items = sorted(
            unified_results.values(),
            key=lambda x: x['rrf_total'],
            reverse=True
        )
        
        # Atualizar scores nos resultados finais
        final_results = []
        for item in sorted_items:
            result = item['result']
            
            # Atualizar similarity_score com RRF score
            result.similarity_score = item['rrf_total']
            
            # Adicionar metadados de fusão
            result.chunk.metadata.update({
                'fusion_method': 'rrf',
                'rrf_score': item['rrf_total'],
                'semantic_rank': item['semantic_rank'],
                'literal_rank': item['literal_rank'],
                'source_types': list(item['source_types'])
            })
            
            final_results.append(result)
        
        logger.debug(f"RRF produzir {len(final_results)} resultados fusionados")
        return final_results
    
    def _weighted_score_fusion(
        self,
        semantic_results: List[SearchResult],
        literal_results: List[SearchResult],
        params: FusionParams
    ) -> List[SearchResult]:
        """
        Implementa fusão por pesos ponderados
        
        Score = semantic_weight * semantic_score + literal_weight * literal_score
        """
        logger.debug(
            f"Aplicando fusão weighted: sem={params.semantic_weight:.2f}, "
            f"lit={params.literal_weight:.2f}"
        )
        
        # Normalizar scores se solicitado
        if params.normalize_scores:
            semantic_results = self._normalize_result_scores(semantic_results, 'semantic')
            literal_results = self._normalize_result_scores(literal_results, 'literal')
        
        unified_results = {}
        
        # Adicionar resultados semânticos
        for result in semantic_results:
            chunk_id = result.chunk.id
            weighted_score = params.semantic_weight * result.similarity_score
            
            unified_results[chunk_id] = {
                'result': result,
                'semantic_score': result.similarity_score,
                'literal_score': 0.0,
                'weighted_score': weighted_score,
                'source_types': {'semantic'}
            }
        
        # Adicionar/combinar resultados literais
        for result in literal_results:
            chunk_id = result.chunk.id
            literal_contribution = params.literal_weight * result.similarity_score
            
            if chunk_id in unified_results:
                # Combinar scores
                unified_results[chunk_id]['weighted_score'] += literal_contribution
                unified_results[chunk_id]['literal_score'] = result.similarity_score
                unified_results[chunk_id]['source_types'].add('literal')
                
                # Usar resultado com contexto mais rico (preferencialmente híbrido)
                current_result = unified_results[chunk_id]['result']
                if len(result.chunk.metadata) > len(current_result.chunk.metadata):
                    unified_results[chunk_id]['result'] = result
            else:
                # Resultado apenas literal
                unified_results[chunk_id] = {
                    'result': result,
                    'semantic_score': 0.0,
                    'literal_score': result.similarity_score,
                    'weighted_score': literal_contribution,
                    'source_types': {'literal'}
                }
        
        # Aplicar boosts se configurado
        if params.boost_exact_matches:
            self._apply_exact_match_boost_weighted(unified_results, params)
        
        # Ordenar por score ponderado
        sorted_items = sorted(
            unified_results.values(),
            key=lambda x: x['weighted_score'],
            reverse=True
        )
        
        # Construir resultados finais
        final_results = []
        for item in sorted_items:
            result = item['result']
            
            # Atualizar similarity_score
            result.similarity_score = item['weighted_score']
            
            # Adicionar metadados
            result.chunk.metadata.update({
                'fusion_method': 'weighted',
                'weighted_score': item['weighted_score'],
                'semantic_contribution': item['semantic_score'] * params.semantic_weight,
                'literal_contribution': item['literal_score'] * params.literal_weight,
                'source_types': list(item['source_types'])
            })
            
            final_results.append(result)
        
        logger.debug(f"Weighted fusion produziu {len(final_results)} resultados")
        return final_results
    
    def _adaptive_fusion(
        self,
        semantic_results: List[SearchResult],
        literal_results: List[SearchResult],
        params: FusionParams
    ) -> List[SearchResult]:
        """
        Fusão adaptativa que ajusta método baseado na query
        """
        logger.debug("Aplicando fusão adaptativa")
        
        # Analisar características da query para decidir estratégia
        if params.query_analysis:
            analysis = params.query_analysis
            
            # Se query tem termos específicos, priorizar literal
            if analysis.get('has_specific_terms', False):
                adapted_params = FusionParams(
                    method=FusionMethod.WEIGHTED,
                    semantic_weight=0.3,
                    literal_weight=0.7,
                    normalize_scores=params.normalize_scores,
                    boost_exact_matches=True
                )
                return self._weighted_score_fusion(semantic_results, literal_results, adapted_params)
            
            # Se query é conceitual, priorizar semântica
            elif analysis.get('is_conceptual', False):
                adapted_params = FusionParams(
                    method=FusionMethod.WEIGHTED,
                    semantic_weight=0.8,
                    literal_weight=0.2,
                    normalize_scores=params.normalize_scores
                )
                return self._weighted_score_fusion(semantic_results, literal_results, adapted_params)
        
        # Default: usar RRF balanceado
        return self._reciprocal_rank_fusion(semantic_results, literal_results, params)
    
    def _bayesian_fusion(
        self,
        semantic_results: List[SearchResult],
        literal_results: List[SearchResult],
        params: FusionParams
    ) -> List[SearchResult]:
        """
        Fusão Bayesiana experimental baseada em evidências
        
        Combina scores usando probabilidades condicionais
        """
        logger.debug("Aplicando fusão Bayesiana (experimental)")
        
        # Implementação simplificada - em produção seria mais sofisticada
        unified_results = {}
        
        # Prior baseado na distribuição de resultados
        semantic_prior = len(semantic_results) / (len(semantic_results) + len(literal_results))
        literal_prior = 1 - semantic_prior
        
        # Processar resultados semânticos
        for result in semantic_results:
            chunk_id = result.chunk.id
            # Likelihood baseado no score normalizado
            likelihood = result.similarity_score
            posterior = semantic_prior * likelihood
            
            unified_results[chunk_id] = {
                'result': result,
                'bayesian_score': posterior,
                'semantic_evidence': likelihood,
                'literal_evidence': 0.0,
                'source_types': {'semantic'}
            }
        
        # Processar resultados literais
        for result in literal_results:
            chunk_id = result.chunk.id
            likelihood = result.similarity_score
            
            if chunk_id in unified_results:
                # Combinar evidências
                literal_posterior = literal_prior * likelihood
                unified_results[chunk_id]['bayesian_score'] += literal_posterior
                unified_results[chunk_id]['literal_evidence'] = likelihood
                unified_results[chunk_id]['source_types'].add('literal')
            else:
                # Apenas literal
                posterior = literal_prior * likelihood
                unified_results[chunk_id] = {
                    'result': result,
                    'bayesian_score': posterior,
                    'semantic_evidence': 0.0,
                    'literal_evidence': likelihood,
                    'source_types': {'literal'}
                }
        
        # Ordenar por score Bayesiano
        sorted_items = sorted(
            unified_results.values(),
            key=lambda x: x['bayesian_score'],
            reverse=True
        )
        
        # Construir resultados finais
        final_results = []
        for item in sorted_items:
            result = item['result']
            result.similarity_score = item['bayesian_score']
            
            result.chunk.metadata.update({
                'fusion_method': 'bayesian',
                'bayesian_score': item['bayesian_score'],
                'semantic_evidence': item['semantic_evidence'],
                'literal_evidence': item['literal_evidence'],
                'source_types': list(item['source_types'])
            })
            
            final_results.append(result)
        
        logger.debug(f"Bayesian fusion produziu {len(final_results)} resultados")
        return final_results
    
    def _preprocess_results(
        self, 
        results: List[SearchResult], 
        result_type: str
    ) -> List[SearchResult]:
        """Pré-processa resultados antes da fusão"""
        if not results:
            return []
        
        # Adicionar tipo de busca aos metadados
        for result in results:
            result.chunk.metadata['original_search_type'] = result_type
        
        # Ordenar por score para garantir ranking correto
        sorted_results = sorted(results, key=lambda r: r.similarity_score, reverse=True)
        
        # Limitar número de resultados por tipo para performance
        max_per_type = 50
        return sorted_results[:max_per_type]
    
    def _postprocess_results(
        self, 
        results: List[SearchResult], 
        params: FusionParams
    ) -> List[SearchResult]:
        """Pós-processa resultados após fusão"""
        if not results:
            return []
        
        # Aplicar filtro de score mínimo
        if params.min_fusion_score > 0:
            results = [r for r in results if r.similarity_score >= params.min_fusion_score]
        
        # Aplicar penalidade de diversidade se configurado
        if params.diversity_penalty > 0:
            results = self._apply_diversity_penalty(results, params.diversity_penalty)
        
        # Limitar número final de resultados
        max_results = 20
        final_results = results[:max_results]
        
        # Adicionar rank final aos metadados
        for i, result in enumerate(final_results):
            result.chunk.metadata['final_rank'] = i + 1
        
        return final_results
    
    def _normalize_result_scores(
        self, 
        results: List[SearchResult], 
        result_type: str
    ) -> List[SearchResult]:
        """Normaliza scores dos resultados para escala 0-1"""
        if not results:
            return results
        
        scores = [r.similarity_score for r in results]
        max_score = max(scores)
        min_score = min(scores)
        
        # Evitar divisão por zero
        if max_score == min_score:
            # Se todos os scores são iguais, manter como está
            return results
        
        # Normalizar para escala 0-1
        normalized_results = []
        for result in results:
            normalized_score = (result.similarity_score - min_score) / (max_score - min_score)
            result.similarity_score = normalized_score
            
            # Adicionar informação sobre normalização
            result.chunk.metadata[f'{result_type}_original_score'] = result.similarity_score
            result.chunk.metadata[f'{result_type}_normalized'] = True
            
            normalized_results.append(result)
        
        return normalized_results
    
    def _apply_exact_match_boost(
        self, 
        unified_results: Dict[str, Dict], 
        params: FusionParams
    ):
        """Aplica boost para matches exatos no RRF"""
        for chunk_id, data in unified_results.items():
            content = data['result'].chunk.content.lower()
            
            # Verificar se há matches exatos (simplificado)
            # Em implementação completa, usaria a query original
            has_exact_match = any([
                'semantic' in data['source_types'] and 'literal' in data['source_types'],
                data.get('literal_score', 0) > 0.9  # Score literal muito alto
            ])
            
            if has_exact_match:
                data['rrf_total'] += params.exact_match_boost
    
    def _apply_exact_match_boost_weighted(
        self, 
        unified_results: Dict[str, Dict], 
        params: FusionParams
    ):
        """Aplica boost para matches exatos na fusão weighted"""
        for chunk_id, data in unified_results.items():
            # Boost para resultados que aparecem em ambas as buscas
            if 'semantic' in data['source_types'] and 'literal' in data['source_types']:
                data['weighted_score'] += params.exact_match_boost
    
    def _apply_diversity_penalty(
        self, 
        results: List[SearchResult], 
        penalty: float
    ) -> List[SearchResult]:
        """Aplica penalidade para reduzir duplicatas e aumentar diversidade"""
        if penalty <= 0 or not results:
            return results
        
        seen_documents = set()
        penalized_results = []
        
        for result in results:
            doc_id = result.chunk.document_id
            
            if doc_id in seen_documents:
                # Aplicar penalidade
                result.similarity_score *= (1 - penalty)
                result.chunk.metadata['diversity_penalty_applied'] = True
            else:
                seen_documents.add(doc_id)
            
            penalized_results.append(result)
        
        # Re-ordenar após aplicar penalidades
        return sorted(penalized_results, key=lambda r: r.similarity_score, reverse=True)
    
    def _generate_cache_key(
        self, 
        semantic_results: List[SearchResult],
        literal_results: List[SearchResult], 
        params: FusionParams
    ) -> str:
        """Gera chave para cache de fusão"""
        import hashlib
        
        # Criar hash baseado nos IDs dos resultados e parâmetros
        semantic_ids = [r.chunk.id for r in semantic_results[:10]]  # Primeiros 10
        literal_ids = [r.chunk.id for r in literal_results[:10]]
        
        cache_data = {
            'semantic_ids': semantic_ids,
            'literal_ids': literal_ids,
            'method': params.method.value,
            'semantic_weight': params.semantic_weight,
            'literal_weight': params.literal_weight,
            'rrf_k': params.rrf_k
        }
        
        cache_str = str(cache_data)
        return hashlib.md5(cache_str.encode()).hexdigest()
    
    def _add_to_cache(self, cache_key: str, result: FusionResult):
        """Adiciona resultado ao cache"""
        if len(self.fusion_cache) >= self.cache_size_limit:
            # Remover entrada mais antiga (FIFO simples)
            oldest_key = next(iter(self.fusion_cache))
            del self.fusion_cache[oldest_key]
        
        self.fusion_cache[cache_key] = result
    
    def get_fusion_statistics(self) -> Dict[str, Any]:
        """Obtém estatísticas do sistema de fusão"""
        return {
            'cache_size': len(self.fusion_cache),
            'cache_limit': self.cache_size_limit,
            'supported_methods': [method.value for method in FusionMethod],
            'cache_keys': list(self.fusion_cache.keys())
        }
    
    def clear_cache(self):
        """Limpa cache de fusão"""
        self.fusion_cache.clear()
        logger.info("Cache de fusão limpo")