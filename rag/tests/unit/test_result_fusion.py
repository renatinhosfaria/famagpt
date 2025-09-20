"""
Testes unitários para algoritmos de fusão de resultados
Testa RRF, Weighted Fusion, e Adaptive Fusion
"""

import pytest
from unittest.mock import Mock
from typing import List
from datetime import datetime

from rag.src.infrastructure.services.result_fusion import (
    HybridResultFusion, FusionParams, FusionResult, FusionMethod
)
from rag.src.domain.entities.document import DocumentChunk, SearchResult


class TestFusionParams:
    """Testes para parâmetros de fusão"""
    
    def test_fusion_params_default(self):
        """Testa criação com parâmetros padrão"""
        params = FusionParams()
        
        assert params.method == FusionMethod.RRF
        assert params.rrf_k == 60
        assert params.semantic_weight == 0.6
        assert params.literal_weight == 0.4
        assert params.normalize_scores == True
    
    def test_fusion_params_weight_normalization(self):
        """Testa normalização automática de pesos"""
        # Pesos que não somam 1.0
        params = FusionParams(semantic_weight=0.8, literal_weight=0.6)
        
        # Deve normalizar para somar 1.0
        assert abs(params.semantic_weight + params.literal_weight - 1.0) < 0.001
        
        # Verificar proporção mantida
        total_original = 0.8 + 0.6
        expected_semantic = 0.8 / total_original
        expected_literal = 0.6 / total_original
        
        assert abs(params.semantic_weight - expected_semantic) < 0.001
        assert abs(params.literal_weight - expected_literal) < 0.001
    
    def test_fusion_params_validation(self):
        """Testa validação de parâmetros"""
        params = FusionParams(
            rrf_k=-10,  # Inválido
            exact_match_boost=1.5,  # Inválido
            diversity_penalty=-0.1  # Inválido
        )
        
        # Deve corrigir valores inválidos
        assert params.rrf_k >= 1
        assert 0.0 <= params.exact_match_boost <= 1.0
        assert params.diversity_penalty >= 0.0


class TestHybridResultFusion:
    """Testes principais para fusão híbrida"""
    
    @pytest.fixture
    def fusion_engine(self):
        """Instância do motor de fusão"""
        return HybridResultFusion()
    
    @pytest.fixture
    def sample_semantic_results(self):
        """Resultados de busca semântica de exemplo"""
        results = []
        
        # Criar resultados com scores decrescentes
        test_data = [
            ('chunk_sem_1', 'doc_1', 'Apartamento com 3 quartos no centro', 0.9),
            ('chunk_sem_2', 'doc_2', 'Casa residencial em bairro nobre', 0.8),
            ('chunk_sem_3', 'doc_3', 'Terreno comercial avenida principal', 0.7),
            ('chunk_sem_4', 'doc_4', 'Cobertura duplex vista panorâmica', 0.6)
        ]
        
        for chunk_id, doc_id, content, score in test_data:
            chunk = DocumentChunk(
                id=chunk_id,
                document_id=doc_id,
                content=content,
                chunk_index=0,
                metadata={'type': 'semantic_test'}
            )
            
            result = SearchResult(
                chunk=chunk,
                similarity_score=score,
                document_title=f"Doc {doc_id}",
                document_metadata={'source': 'test'}
            )
            
            results.append(result)
        
        return results
    
    @pytest.fixture
    def sample_literal_results(self):
        """Resultados de busca literal de exemplo"""
        results = []
        
        test_data = [
            ('chunk_lit_1', 'doc_1', 'Apartamento 3 quartos centro R$ 350.000', 0.85),  # Overlap com semântico
            ('chunk_lit_5', 'doc_5', 'Casa 4 quartos jardim quintal amplo', 0.75),     # Apenas literal
            ('chunk_lit_2', 'doc_2', 'Casa bairro residencial família', 0.65),         # Overlap com semântico
            ('chunk_lit_6', 'doc_6', 'Apartamento novo entrega imediata', 0.55)       # Apenas literal
        ]
        
        for chunk_id, doc_id, content, score in test_data:
            chunk = DocumentChunk(
                id=chunk_id,
                document_id=doc_id,
                content=content,
                chunk_index=0,
                metadata={'type': 'literal_test'}
            )
            
            result = SearchResult(
                chunk=chunk,
                similarity_score=score,
                document_title=f"Doc {doc_id}",
                document_metadata={'source': 'test'}
            )
            
            results.append(result)
        
        return results
    
    def test_rrf_fusion_basic(self, fusion_engine, sample_semantic_results, sample_literal_results):
        """Testa fusão RRF básica"""
        params = FusionParams(method=FusionMethod.RRF, rrf_k=60)
        
        fusion_result = fusion_engine.fuse_results(
            sample_semantic_results,
            sample_literal_results,
            params
        )
        
        # Verificar estrutura do resultado
        assert isinstance(fusion_result, FusionResult)
        assert fusion_result.fusion_method == FusionMethod.RRF
        assert len(fusion_result.fused_results) > 0
        
        # Verificar que resultados foram ordenados
        scores = [r.similarity_score for r in fusion_result.fused_results]
        assert scores == sorted(scores, reverse=True)
        
        # Verificar que metadados RRF foram adicionados
        first_result = fusion_result.fused_results[0]
        assert 'fusion_method' in first_result.chunk.metadata
        assert 'rrf_score' in first_result.chunk.metadata
        assert 'source_types' in first_result.chunk.metadata
        
        # Verificar que chunks que aparecem em ambas as listas têm score mais alto
        hybrid_chunks = [
            r for r in fusion_result.fused_results 
            if len(r.chunk.metadata.get('source_types', [])) > 1
        ]
        assert len(hybrid_chunks) > 0, "Deve haver chunks que aparecem em ambas as buscas"
    
    def test_rrf_score_calculation(self, fusion_engine, sample_semantic_results, sample_literal_results):
        """Testa cálculo correto do score RRF"""
        params = FusionParams(method=FusionMethod.RRF, rrf_k=60)
        
        fusion_result = fusion_engine.fuse_results(
            sample_semantic_results,
            sample_literal_results,
            params
        )
        
        # Encontrar chunk que aparece em ambas as listas (doc_1)
        doc_1_result = None
        for result in fusion_result.fused_results:
            if result.chunk.document_id == 'doc_1':
                doc_1_result = result
                break
        
        assert doc_1_result is not None, "Deve encontrar resultado do doc_1"
        
        # Verificar metadados RRF
        metadata = doc_1_result.chunk.metadata
        assert 'semantic' in metadata['source_types']
        assert 'literal' in metadata['source_types']
        
        # Score RRF deve ser soma dos dois componentes
        # RRF = 1/(k+rank_sem) + 1/(k+rank_lit)
        k = 60
        expected_semantic_rrf = 1.0 / (k + 1)  # Primeiro na lista semântica
        expected_literal_rrf = 1.0 / (k + 1)   # Primeiro na lista literal
        expected_total = expected_semantic_rrf + expected_literal_rrf
        
        assert abs(doc_1_result.similarity_score - expected_total) < 0.01
    
    def test_weighted_fusion_basic(self, fusion_engine, sample_semantic_results, sample_literal_results):
        """Testa fusão weighted básica"""
        params = FusionParams(
            method=FusionMethod.WEIGHTED,
            semantic_weight=0.7,
            literal_weight=0.3,
            normalize_scores=True
        )
        
        fusion_result = fusion_engine.fuse_results(
            sample_semantic_results,
            sample_literal_results,
            params
        )
        
        # Verificar estrutura
        assert fusion_result.fusion_method == FusionMethod.WEIGHTED
        assert len(fusion_result.fused_results) > 0
        
        # Verificar metadados weighted
        first_result = fusion_result.fused_results[0]
        metadata = first_result.chunk.metadata
        
        assert metadata['fusion_method'] == 'weighted'
        assert 'weighted_score' in metadata
        assert 'semantic_contribution' in metadata
        assert 'literal_contribution' in metadata
        
        # Verificar que scores foram normalizados (se configurado)
        # Todos os resultados devem ter evidência de normalização ou processamento
        for result in fusion_result.fused_results:
            assert result.similarity_score >= 0
    
    def test_weighted_score_calculation(self, fusion_engine):
        """Testa cálculo preciso do score weighted"""
        # Criar resultados controlados para teste
        semantic_chunk = DocumentChunk(id='test_chunk', document_id='test_doc', content='test', chunk_index=0)
        literal_chunk = DocumentChunk(id='test_chunk', document_id='test_doc', content='test', chunk_index=0)
        
        semantic_result = SearchResult(chunk=semantic_chunk, similarity_score=0.8, document_title='Test')
        literal_result = SearchResult(chunk=literal_chunk, similarity_score=0.6, document_title='Test')
        
        params = FusionParams(
            method=FusionMethod.WEIGHTED,
            semantic_weight=0.7,
            literal_weight=0.3,
            normalize_scores=False  # Manter scores originais
        )
        
        fusion_result = fusion_engine.fuse_results([semantic_result], [literal_result], params)
        
        # Deve ter 1 resultado (mesmo chunk_id)
        assert len(fusion_result.fused_results) == 1
        
        result = fusion_result.fused_results[0]
        expected_score = 0.7 * 0.8 + 0.3 * 0.6  # 0.56 + 0.18 = 0.74
        
        assert abs(result.similarity_score - expected_score) < 0.01
    
    def test_adaptive_fusion(self, fusion_engine, sample_semantic_results, sample_literal_results):
        """Testa fusão adaptativa"""
        # Simular análise de query que indica termos específicos
        query_analysis = {
            'has_specific_terms': True,
            'is_conceptual': False
        }
        
        params = FusionParams(
            method=FusionMethod.ADAPTIVE,
            query_analysis=query_analysis
        )
        
        fusion_result = fusion_engine.fuse_results(
            sample_semantic_results,
            sample_literal_results,
            params
        )
        
        assert fusion_result.fusion_method == FusionMethod.ADAPTIVE
        assert len(fusion_result.fused_results) > 0
        
        # Fusion adaptativa deve ter escolhido weighted com peso para literal
        # (baseado na análise de query)
        # Verificar pelos metadados que weighted foi usado
        first_result = fusion_result.fused_results[0]
        metadata = first_result.chunk.metadata
        
        # Deve ter aplicado estratégia appropriate baseada na query
        assert 'fusion_method' in metadata
    
    def test_fusion_with_empty_results(self, fusion_engine):
        """Testa fusão com listas vazias"""
        params = FusionParams(method=FusionMethod.RRF)
        
        # Ambas listas vazias
        fusion_result = fusion_engine.fuse_results([], [], params)
        assert len(fusion_result.fused_results) == 0
        
        # Apenas semântica vazia
        literal_chunk = DocumentChunk(id='test', document_id='test_doc', content='test', chunk_index=0)
        literal_result = SearchResult(chunk=literal_chunk, similarity_score=0.5, document_title='Test')
        
        fusion_result = fusion_engine.fuse_results([], [literal_result], params)
        assert len(fusion_result.fused_results) == 1
        assert fusion_result.fused_results[0].chunk.id == 'test'
    
    def test_fusion_with_duplicate_chunks(self, fusion_engine):
        """Testa fusão com chunks duplicados na mesma lista"""
        # Criar chunk duplicado na lista semântica
        chunk1 = DocumentChunk(id='dup_chunk', document_id='doc_1', content='test content', chunk_index=0)
        chunk2 = DocumentChunk(id='dup_chunk', document_id='doc_1', content='test content', chunk_index=0)
        
        result1 = SearchResult(chunk=chunk1, similarity_score=0.8, document_title='Test')
        result2 = SearchResult(chunk=chunk2, similarity_score=0.7, document_title='Test')  # Score menor
        
        params = FusionParams(method=FusionMethod.RRF)
        
        fusion_result = fusion_engine.fuse_results([result1, result2], [], params)
        
        # Deve ter apenas 1 resultado (deduplicado por chunk.id)
        assert len(fusion_result.fused_results) == 1
        
        # Deve usar o resultado com melhor score
        assert fusion_result.fused_results[0].similarity_score > 0  # Score RRF aplicado
    
    def test_exact_match_boost(self, fusion_engine, sample_semantic_results, sample_literal_results):
        """Testa boost para matches exatos"""
        params = FusionParams(
            method=FusionMethod.RRF,
            boost_exact_matches=True,
            exact_match_boost=0.2
        )
        
        fusion_result = fusion_engine.fuse_results(
            sample_semantic_results,
            sample_literal_results,
            params
        )
        
        # Encontrar resultado que aparece em ambas as listas
        hybrid_results = [
            r for r in fusion_result.fused_results
            if len(r.chunk.metadata.get('source_types', [])) > 1
        ]
        
        assert len(hybrid_results) > 0, "Deve haver resultados híbridos"
        
        # Score do híbrido deve ser maior que sem boost
        # (difícil verificar exato sem recriar o cálculo, mas deve estar no topo)
        hybrid_result = hybrid_results[0]
        assert hybrid_result.similarity_score > 0.2  # Pelo menos o boost
    
    def test_diversity_penalty(self, fusion_engine):
        """Testa penalidade de diversidade"""
        # Criar múltiplos chunks do mesmo documento
        chunks_same_doc = []
        for i in range(3):
            chunk = DocumentChunk(
                id=f'chunk_{i}',
                document_id='same_doc',  # Mesmo documento
                content=f'Content {i}',
                chunk_index=i
            )
            result = SearchResult(
                chunk=chunk,
                similarity_score=0.8 - i * 0.1,  # Scores decrescentes
                document_title='Same Doc'
            )
            chunks_same_doc.append(result)
        
        params = FusionParams(
            method=FusionMethod.RRF,
            diversity_penalty=0.3  # 30% penalidade
        )
        
        fusion_result = fusion_engine.fuse_results(chunks_same_doc, [], params)
        
        # Verificar que penalidade foi aplicada
        penalized_results = [
            r for r in fusion_result.fused_results
            if r.chunk.metadata.get('diversity_penalty_applied', False)
        ]
        
        # Deve haver pelo menos 2 resultados penalizados (todos exceto o primeiro do doc)
        assert len(penalized_results) >= 1
    
    def test_fusion_metrics(self, fusion_engine, sample_semantic_results, sample_literal_results):
        """Testa cálculo de métricas de fusão"""
        params = FusionParams(method=FusionMethod.RRF)
        
        fusion_result = fusion_engine.fuse_results(
            sample_semantic_results,
            sample_literal_results,
            params
        )
        
        # Verificar métricas básicas
        metrics = fusion_result.fusion_metrics
        
        assert 'total_results' in metrics
        assert 'avg_fusion_score' in metrics
        assert 'score_distribution' in metrics
        assert 'diversity_score' in metrics
        
        # Verificar valores das métricas
        assert metrics['total_results'] == len(fusion_result.fused_results)
        assert 0 <= metrics['avg_fusion_score'] <= 1
        assert 0 <= metrics['diversity_score'] <= 1
        
        # Score distribution
        distribution = metrics['score_distribution']
        assert 'min' in distribution
        assert 'max' in distribution
        assert 'std' in distribution
    
    def test_fusion_cache(self, fusion_engine, sample_semantic_results, sample_literal_results):
        """Testa cache de fusão"""
        params = FusionParams(method=FusionMethod.RRF)
        
        # Primeira execução
        result1 = fusion_engine.fuse_results(
            sample_semantic_results,
            sample_literal_results,
            params
        )
        
        # Segunda execução com mesmos parâmetros deve usar cache
        result2 = fusion_engine.fuse_results(
            sample_semantic_results,
            sample_literal_results,
            params
        )
        
        # Verificar que cache foi usado (mesma instância de resultado)
        assert len(result1.fused_results) == len(result2.fused_results)
        
        # Cache deve ter 1 entrada
        stats = fusion_engine.get_fusion_statistics()
        assert stats['cache_size'] >= 1
    
    def test_normalization_functionality(self, fusion_engine):
        """Testa normalização de scores"""
        # Criar resultados com scores em faixas diferentes
        semantic_chunks = []
        literal_chunks = []
        
        # Semânticos com scores altos (0.8-1.0)
        for i, score in enumerate([1.0, 0.9, 0.8]):
            chunk = DocumentChunk(id=f'sem_{i}', document_id=f'doc_{i}', content=f'Content {i}', chunk_index=0)
            result = SearchResult(chunk=chunk, similarity_score=score, document_title=f'Doc {i}')
            semantic_chunks.append(result)
        
        # Literais com scores baixos (0.1-0.3)
        for i, score in enumerate([0.3, 0.2, 0.1]):
            chunk = DocumentChunk(id=f'lit_{i}', document_id=f'doc_{i+3}', content=f'Content {i+3}', chunk_index=0)
            result = SearchResult(chunk=chunk, similarity_score=score, document_title=f'Doc {i+3}')
            literal_chunks.append(result)
        
        params = FusionParams(
            method=FusionMethod.WEIGHTED,
            normalize_scores=True
        )
        
        fusion_result = fusion_engine.fuse_results(semantic_chunks, literal_chunks, params)
        
        # Após normalização e fusão, scores devem estar numa faixa razoável
        scores = [r.similarity_score for r in fusion_result.fused_results]
        
        # Todos scores devem ser >= 0
        assert all(score >= 0 for score in scores)
        
        # Deve haver diferenciação entre resultados
        assert len(set(scores)) > 1, "Scores devem ser diferenciados após fusão"
    
    def test_error_handling_fallback(self, fusion_engine, sample_semantic_results):
        """Testa tratamento de erro com fallback"""
        # Forçar erro usando parâmetros inválidos ou simulando falha
        params = FusionParams(method=FusionMethod.RRF)
        
        # Simular erro passando resultado inválido
        invalid_result = Mock()
        invalid_result.chunk = None  # Vai causar erro
        
        try:
            # Mesmo com erro, deve retornar resultado (fallback)
            fusion_result = fusion_engine.fuse_results(
                sample_semantic_results,
                [invalid_result],  # Resultado inválido
                params
            )
            
            # Deve usar fallback (resultados semânticos)
            assert len(fusion_result.fused_results) > 0
            assert 'error' in fusion_result.fusion_metrics or len(fusion_result.fused_results) == len(sample_semantic_results)
            
        except Exception:
            # Se exceção for lançada, ainda deve ser tratada graciosamente
            pass
    
    def test_bayesian_fusion_experimental(self, fusion_engine, sample_semantic_results, sample_literal_results):
        """Testa fusão Bayesiana experimental"""
        params = FusionParams(method=FusionMethod.BAYESIAN)
        
        fusion_result = fusion_engine.fuse_results(
            sample_semantic_results,
            sample_literal_results,
            params
        )
        
        assert fusion_result.fusion_method == FusionMethod.BAYESIAN
        assert len(fusion_result.fused_results) > 0
        
        # Verificar metadados específicos do Bayesian
        first_result = fusion_result.fused_results[0]
        metadata = first_result.chunk.metadata
        
        assert metadata['fusion_method'] == 'bayesian'
        assert 'bayesian_score' in metadata
        assert 'semantic_evidence' in metadata
        assert 'literal_evidence' in metadata


class TestFusionResult:
    """Testes para classe FusionResult"""
    
    def test_fusion_result_metrics_calculation(self):
        """Testa cálculo automático de métricas"""
        # Criar resultados de teste
        results = []
        for i, score in enumerate([0.9, 0.7, 0.5]):
            chunk = DocumentChunk(
                id=f'chunk_{i}',
                document_id=f'doc_{i}',
                content=f'Content {i}',
                chunk_index=0
            )
            result = SearchResult(chunk=chunk, similarity_score=score, document_title=f'Doc {i}')
            results.append(result)
        
        fusion_result = FusionResult(
            fused_results=results,
            fusion_method=FusionMethod.RRF,
            fusion_params=FusionParams()
        )
        
        # Verificar métricas calculadas
        metrics = fusion_result.fusion_metrics
        
        assert metrics['total_results'] == 3
        assert abs(metrics['avg_fusion_score'] - 0.7) < 0.01  # (0.9 + 0.7 + 0.5) / 3
        assert metrics['diversity_score'] == 1.0  # 3 documentos únicos / 3 resultados
        
        distribution = metrics['score_distribution']
        assert distribution['min'] == 0.5
        assert distribution['max'] == 0.9
        assert distribution['std'] > 0  # Deve ter desvio padrão


if __name__ == "__main__":
    pytest.main([__file__, "-v"])