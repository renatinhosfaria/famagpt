"""
PostgreSQL with PGVector implementation for vector storage
"""

import json
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime

import asyncpg
from shared.src.utils.logging import get_logger
from shared.src.utils.config import get_settings

from ...domain.entities.document import Document, DocumentChunk, SearchResult
from ...domain.protocols.rag_service import VectorStoreProtocol


logger = get_logger("rag.pgvector_store")
settings = get_settings()


class PGVectorStore(VectorStoreProtocol):
    """PostgreSQL with PGVector implementation for vector storage"""
    
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self.embedding_dimension = 1536  # OpenAI ada-002 dimension
    
    async def initialize(self):
        """Initialize the database connection and create tables"""
        try:
            self.pool = await asyncpg.create_pool(
                settings.database.url,
                min_size=1,
                max_size=10,
                command_timeout=60
            )
            
            # Create tables and extensions
            async with self.pool.acquire() as conn:
                # Enable pgvector extension
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                
                # Create documents table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS rag_documents (
                        id VARCHAR PRIMARY KEY,
                        title TEXT NOT NULL,
                        content TEXT NOT NULL,
                        document_type VARCHAR(50) NOT NULL,
                        source_url TEXT,
                        metadata JSONB DEFAULT '{}',
                        status VARCHAR(20) DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        processed_at TIMESTAMP
                    )
                """)
                
                # Create chunks table with vector column
                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS rag_document_chunks (
                        id VARCHAR PRIMARY KEY,
                        document_id VARCHAR REFERENCES rag_documents(id) ON DELETE CASCADE,
                        content TEXT NOT NULL,
                        chunk_index INTEGER NOT NULL,
                        start_position INTEGER,
                        end_position INTEGER,
                        embedding vector({self.embedding_dimension}),
                        metadata JSONB DEFAULT '{{}}',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create indexes for better performance
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_rag_chunks_document_id 
                    ON rag_document_chunks(document_id)
                """)
                
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding 
                    ON rag_document_chunks USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 100)
                """)
                
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_rag_documents_status 
                    ON rag_documents(status)
                """)
                
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_rag_documents_created_at 
                    ON rag_documents(created_at DESC)
                """)
            
            logger.info("PGVector store initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize PGVector store: {str(e)}")
            raise RuntimeError(f"PGVector initialization failed: {str(e)}") from e
    
    async def cleanup(self):
        """Clean up database connections"""
        if self.pool:
            await self.pool.close()
    
    async def store_document(self, document: Document) -> None:
        """Store document and its chunks in vector database"""
        try:
            if not self.pool:
                await self.initialize()
            
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Insert document
                    await conn.execute("""
                        INSERT INTO rag_documents 
                        (id, title, content, document_type, source_url, metadata, status, created_at, processed_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        ON CONFLICT (id) DO UPDATE SET
                            title = EXCLUDED.title,
                            content = EXCLUDED.content,
                            metadata = EXCLUDED.metadata,
                            status = EXCLUDED.status,
                            updated_at = CURRENT_TIMESTAMP,
                            processed_at = EXCLUDED.processed_at
                    """, 
                        document.id,
                        document.title,
                        document.content,
                        document.document_type.value if document.document_type else 'text',
                        document.source_url,
                        json.dumps(document.metadata or {}),
                        document.status.value if document.status else 'pending',
                        document.created_at or datetime.utcnow(),
                        document.processed_at
                    )
                    
                    # Insert chunks with embeddings
                    if document.chunks:
                        for chunk in document.chunks:
                            if chunk.embedding:
                                # Convert embedding to pgvector literal (e.g., "[0.1,0.2,...]")
                                emb_literal = self._to_pgvector_literal(chunk.embedding)
                                await conn.execute(
                                    """
                                    INSERT INTO rag_document_chunks 
                                    (id, document_id, content, chunk_index, start_position, end_position, embedding, metadata, created_at)
                                    VALUES ($1, $2, $3, $4, $5, $6, $7::vector, $8, $9)
                                    ON CONFLICT (id) DO UPDATE SET
                                        content = EXCLUDED.content,
                                        embedding = EXCLUDED.embedding,
                                        metadata = EXCLUDED.metadata
                                    """,
                                    chunk.id,
                                    chunk.document_id,
                                    chunk.content,
                                    chunk.chunk_index,
                                    chunk.start_position,
                                    chunk.end_position,
                                    emb_literal,
                                    json.dumps(chunk.metadata or {}),
                                    chunk.created_at or datetime.utcnow(),
                                )
                            else:
                                logger.warning(f"Chunk {chunk.id} has no embedding, skipping vector storage")
            
            logger.info(f"Stored document {document.id} with {len(document.chunks or [])} chunks")
            
        except Exception as e:
            logger.error(f"Error storing document {document.id}: {str(e)}")
            raise RuntimeError(f"Failed to store document: {str(e)}") from e
    
    async def search_similar_chunks(
        self, 
        query_embedding: List[float], 
        top_k: int = 5,
        min_similarity: float = 0.7,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """Search for similar chunks using vector similarity"""
        try:
            if not self.pool:
                await self.initialize()
            
            # Build query with optional filters
            base_query = """
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
                    1 - (c.embedding <=> $1::vector) as similarity_score
                FROM rag_document_chunks c
                JOIN rag_documents d ON c.document_id = d.id
                WHERE 1 - (c.embedding <=> $1::vector) >= $2
            """
            
            # Convert query embedding to pgvector literal
            emb_literal = self._to_pgvector_literal(query_embedding)
            params = [emb_literal, min_similarity]
            param_idx = 3
            
            # Add filters if provided
            if filters:
                if 'document_type' in filters:
                    base_query += f" AND d.document_type = ${param_idx}"
                    params.append(filters['document_type'])
                    param_idx += 1
                
                if 'document_id' in filters:
                    base_query += f" AND c.document_id = ${param_idx}"
                    params.append(filters['document_id'])
                    param_idx += 1
            
            # Add ordering and limit
            base_query += f" ORDER BY similarity_score DESC LIMIT ${param_idx}"
            params.append(top_k)
            
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(base_query, *params)
            
            # Convert to SearchResult objects
            results = []
            for row in rows:
                chunk = DocumentChunk(
                    id=row['id'],
                    document_id=row['document_id'],
                    content=row['content'],
                    chunk_index=row['chunk_index'],
                    start_position=row['start_position'],
                    end_position=row['end_position'],
                    metadata=row['metadata'] or {},
                    created_at=row['created_at']
                )
                
                result = SearchResult(
                    chunk=chunk,
                    similarity_score=float(row['similarity_score']),
                    document_title=row['document_title'],
                    document_metadata=row['document_metadata'] or {}
                )
                results.append(result)
            
            logger.debug(f"Found {len(results)} similar chunks with similarity >= {min_similarity}")
            return results
            
        except Exception as e:
            logger.error(f"Error searching similar chunks: {str(e)}")
            raise RuntimeError(f"Vector search failed: {str(e)}") from e
    
    async def delete_document(self, document_id: str) -> None:
        """Delete document and all its chunks"""
        try:
            if not self.pool:
                await self.initialize()
            
            async with self.pool.acquire() as conn:
                # Delete document (chunks will be deleted by CASCADE)
                result = await conn.execute(
                    "DELETE FROM rag_documents WHERE id = $1",
                    document_id
                )
                
                deleted_count = int(result.split()[-1])
                
                if deleted_count > 0:
                    logger.info(f"Deleted document {document_id}")
                else:
                    logger.warning(f"Document {document_id} not found for deletion")
            
        except Exception as e:
            logger.error(f"Error deleting document {document_id}: {str(e)}")
            raise RuntimeError(f"Failed to delete document: {str(e)}") from e
    
    async def get_document_stats(self) -> Dict[str, Any]:
        """Get statistics about stored documents"""
        try:
            if not self.pool:
                await self.initialize()
            
            async with self.pool.acquire() as conn:
                # Get document counts by status
                doc_stats = await conn.fetch("""
                    SELECT status, COUNT(*) as count 
                    FROM rag_documents 
                    GROUP BY status
                """)
                
                # Get total chunk count
                chunk_count = await conn.fetchval("""
                    SELECT COUNT(*) FROM rag_document_chunks
                """)
                
                # Get average chunks per document
                avg_chunks = await conn.fetchval("""
                    SELECT AVG(chunk_count) FROM (
                        SELECT COUNT(*) as chunk_count 
                        FROM rag_document_chunks 
                        GROUP BY document_id
                    ) as subq
                """)
                
                # Get recent document count (last 7 days)
                recent_docs = await conn.fetchval("""
                    SELECT COUNT(*) 
                    FROM rag_documents 
                    WHERE created_at > CURRENT_TIMESTAMP - INTERVAL '7 days'
                """)
                
                # Get storage size estimate
                storage_info = await conn.fetchrow("""
                    SELECT 
                        pg_total_relation_size('rag_documents') + 
                        pg_total_relation_size('rag_document_chunks') as total_size_bytes
                """)
            
            stats = {
                "total_documents": sum(row['count'] for row in doc_stats),
                "total_chunks": chunk_count or 0,
                "avg_chunks_per_document": float(avg_chunks) if avg_chunks else 0.0,
                "recent_documents_7_days": recent_docs or 0,
                "storage_size_bytes": int(storage_info['total_size_bytes']) if storage_info else 0,
                "documents_by_status": {row['status']: row['count'] for row in doc_stats},
                "embedding_dimension": self.embedding_dimension
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting document stats: {str(e)}")
            return {
                "error": str(e),
                "total_documents": 0,
                "total_chunks": 0
            }

    def _to_pgvector_literal(self, embedding: List[float]) -> str:
        """Convert a list of floats to pgvector text literal, e.g., "[0.1,0.2]"."""
        # Ensure floats and reasonable precision
        vals = ",".join(f"{float(x):.6f}" for x in embedding)
        return f"[{vals}]"
    
    # === MÉTODOS HÍBRIDOS ADICIONADOS ===
    
    async def hybrid_search_chunks(
        self,
        query: str,
        query_embedding: List[float],
        semantic_weight: float = 0.6,
        literal_weight: float = 0.4,
        top_k: int = 10,
        min_similarity: float = 0.5,
        filters: Optional[Dict[str, Any]] = None,
        fusion_method: str = "rrf"
    ) -> List[SearchResult]:
        """
        Busca híbrida combinando busca semântica + literal
        
        Args:
            query: Texto da query para busca literal
            query_embedding: Embedding para busca semântica
            semantic_weight: Peso da busca semântica (0.0-1.0)
            literal_weight: Peso da busca literal (0.0-1.0)  
            top_k: Número de resultados finais
            min_similarity: Similaridade mínima
            filters: Filtros adicionais
            fusion_method: Método de fusão ("rrf" ou "weighted")
            
        Returns:
            Lista de SearchResult fusionados
        """
        try:
            if not self.pool:
                await self.initialize()
            
            logger.debug(
                f"Hybrid search: query='{query[:50]}...', method={fusion_method}, "
                f"weights=({semantic_weight:.2f}, {literal_weight:.2f})"
            )
            
            # Importar componentes de busca híbrida
            from .literal_search_engine import LiteralSearchEngine
            from .result_fusion import HybridResultFusion, FusionParams, FusionMethod
            
            # Executar buscas em paralelo
            import asyncio
            
            # Busca semântica (existente)
            semantic_task = asyncio.create_task(
                self.search_similar_chunks(
                    query_embedding, 
                    top_k=top_k * 2,  # Buscar mais para fusão
                    min_similarity=min_similarity,
                    filters=filters
                )
            )
            
            # Busca literal (nova)
            literal_engine = LiteralSearchEngine(self.pool)
            literal_task = asyncio.create_task(
                literal_engine.search_chunks(
                    query,
                    top_k=top_k * 2,
                    min_rank=min_similarity,
                    filters=filters
                )
            )
            
            # Aguardar ambas as buscas
            semantic_results, literal_results = await asyncio.gather(
                semantic_task, literal_task
            )
            
            logger.debug(
                f"Retrieved {len(semantic_results)} semantic + {len(literal_results)} literal results"
            )
            
            # Fusão dos resultados
            fusion_engine = HybridResultFusion()
            
            # Configurar parâmetros de fusão
            fusion_params = FusionParams(
                method=FusionMethod.RRF if fusion_method == "rrf" else FusionMethod.WEIGHTED,
                semantic_weight=semantic_weight,
                literal_weight=literal_weight,
                rrf_k=60,
                normalize_scores=True,
                boost_exact_matches=True
            )
            
            # Executar fusão
            fusion_result = fusion_engine.fuse_results(
                semantic_results,
                literal_results, 
                fusion_params
            )
            
            # Limitar aos top_k finais
            final_results = fusion_result.fused_results[:top_k]
            
            logger.info(
                f"Hybrid search completed: {len(final_results)} results, "
                f"avg_score={fusion_result.fusion_metrics['avg_fusion_score']:.3f}"
            )
            
            return final_results
            
        except Exception as e:
            logger.error(f"Error in hybrid search: {str(e)}")
            # Fallback para busca semântica apenas
            return await self.search_similar_chunks(
                query_embedding, top_k, min_similarity, filters
            )
    
    async def literal_search_chunks(
        self,
        query: str,
        top_k: int = 10,
        min_rank: float = 0.1,
        filters: Optional[Dict[str, Any]] = None,
        highlight: bool = False
    ) -> List[SearchResult]:
        """
        Busca literal apenas (sem semântica)
        
        Args:
            query: Texto da busca
            top_k: Número de resultados
            min_rank: Rank mínimo
            filters: Filtros adicionais
            highlight: Se deve destacar termos
            
        Returns:
            Lista de SearchResult da busca literal
        """
        try:
            if not self.pool:
                await self.initialize()
            
            from .literal_search_engine import LiteralSearchEngine
            
            literal_engine = LiteralSearchEngine(self.pool)
            results = await literal_engine.search_chunks(
                query, top_k, min_rank, filters, highlight
            )
            
            logger.debug(f"Literal search returned {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"Error in literal search: {str(e)}")
            return []
    
    async def get_hybrid_search_statistics(self) -> Dict[str, Any]:
        """Obtém estatísticas específicas para busca híbrida"""
        try:
            if not self.pool:
                await self.initialize()
            
            async with self.pool.acquire() as conn:
                # Estatísticas de full-text search
                fulltext_stats = await conn.fetchrow("""
                    SELECT 
                        count(*) as total_chunks,
                        count(CASE WHEN content_tsvector IS NOT NULL THEN 1 END) as indexed_chunks,
                        count(CASE WHEN content_tsvector IS NOT NULL AND embedding IS NOT NULL THEN 1 END) as hybrid_ready_chunks
                    FROM rag_document_chunks
                """)
                
                # Top termos do índice full-text
                try:
                    top_terms = await conn.fetch("""
                        SELECT word, nentry
                        FROM ts_stat($$
                            SELECT content_tsvector FROM rag_document_chunks 
                            WHERE content_tsvector IS NOT NULL
                        $$)
                        WHERE char_length(word) > 2
                        ORDER BY nentry DESC
                        LIMIT 20
                    """)
                except:
                    top_terms = []
                
                # Estatísticas de índices
                index_stats = await conn.fetch("""
                    SELECT 
                        schemaname,
                        tablename,
                        indexname,
                        idx_tup_read,
                        idx_tup_fetch
                    FROM pg_stat_user_indexes 
                    WHERE tablename = 'rag_document_chunks'
                    AND indexname LIKE 'idx_rag_chunks_%'
                """)
                
                base_stats = await self.get_document_stats()
                
                hybrid_stats = {
                    **base_stats,
                    'fulltext_indexed_chunks': fulltext_stats['indexed_chunks'],
                    'hybrid_ready_chunks': fulltext_stats['hybrid_ready_chunks'],
                    'hybrid_coverage': (
                        fulltext_stats['hybrid_ready_chunks'] / fulltext_stats['total_chunks']
                        if fulltext_stats['total_chunks'] > 0 else 0
                    ),
                    'top_fulltext_terms': [
                        {'term': row['word'], 'frequency': row['nentry']}
                        for row in top_terms
                    ],
                    'index_usage': [
                        {
                            'index_name': row['indexname'],
                            'reads': row['idx_tup_read'],
                            'fetches': row['idx_tup_fetch']
                        }
                        for row in index_stats
                    ]
                }
                
                return hybrid_stats
                
        except Exception as e:
            logger.error(f"Error getting hybrid statistics: {str(e)}")
            return {
                'error': str(e),
                'total_chunks': 0,
                'hybrid_ready_chunks': 0,
                'hybrid_coverage': 0
            }
    
    async def test_hybrid_performance(
        self,
        test_queries: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Testa performance da busca híbrida vs individual
        
        Args:
            test_queries: Queries de teste (usa padrão se None)
            
        Returns:
            Relatório de performance comparativa
        """
        if test_queries is None:
            test_queries = [
                "apartamento 3 quartos centro Uberlândia",
                "casa bairro nobre família",
                "terreno comercial investimento",
                "R$ 350.000 valor apartamento",
                "imóvel tranquilo confortável"
            ]
        
        results = {
            'test_queries': test_queries,
            'performance_data': [],
            'summary': {}
        }
        
        try:
            if not self.pool:
                await self.initialize()
            
            from .literal_search_engine import LiteralSearchEngine
            import time
            
            literal_engine = LiteralSearchEngine(self.pool)
            
            for query in test_queries:
                query_results = {'query': query}
                
                # Gerar embedding dummy para teste (em produção viria do embedding service)
                dummy_embedding = [0.1] * self.embedding_dimension
                
                # Teste busca semântica
                start_time = time.time()
                try:
                    semantic_results = await self.search_similar_chunks(
                        dummy_embedding, top_k=5, min_similarity=0.1
                    )
                    semantic_time = time.time() - start_time
                    query_results['semantic'] = {
                        'time_ms': round(semantic_time * 1000, 2),
                        'results_count': len(semantic_results),
                        'avg_score': (
                            sum(r.similarity_score for r in semantic_results) / len(semantic_results)
                            if semantic_results else 0
                        )
                    }
                except Exception as e:
                    query_results['semantic'] = {'error': str(e), 'time_ms': 0, 'results_count': 0}
                
                # Teste busca literal
                start_time = time.time()
                try:
                    literal_results = await literal_engine.search_chunks(query, top_k=5)
                    literal_time = time.time() - start_time
                    query_results['literal'] = {
                        'time_ms': round(literal_time * 1000, 2),
                        'results_count': len(literal_results),
                        'avg_score': (
                            sum(r.similarity_score for r in literal_results) / len(literal_results)
                            if literal_results else 0
                        )
                    }
                except Exception as e:
                    query_results['literal'] = {'error': str(e), 'time_ms': 0, 'results_count': 0}
                
                # Teste busca híbrida
                start_time = time.time()
                try:
                    hybrid_results = await self.hybrid_search_chunks(
                        query, dummy_embedding, top_k=5, fusion_method="rrf"
                    )
                    hybrid_time = time.time() - start_time
                    query_results['hybrid'] = {
                        'time_ms': round(hybrid_time * 1000, 2),
                        'results_count': len(hybrid_results),
                        'avg_score': (
                            sum(r.similarity_score for r in hybrid_results) / len(hybrid_results)
                            if hybrid_results else 0
                        )
                    }
                except Exception as e:
                    query_results['hybrid'] = {'error': str(e), 'time_ms': 0, 'results_count': 0}
                
                results['performance_data'].append(query_results)
            
            # Calcular resumo
            semantic_times = [q['semantic']['time_ms'] for q in results['performance_data'] if 'error' not in q['semantic']]
            literal_times = [q['literal']['time_ms'] for q in results['performance_data'] if 'error' not in q['literal']]
            hybrid_times = [q['hybrid']['time_ms'] for q in results['performance_data'] if 'error' not in q['hybrid']]
            
            results['summary'] = {
                'avg_semantic_time_ms': sum(semantic_times) / len(semantic_times) if semantic_times else 0,
                'avg_literal_time_ms': sum(literal_times) / len(literal_times) if literal_times else 0,
                'avg_hybrid_time_ms': sum(hybrid_times) / len(hybrid_times) if hybrid_times else 0,
                'successful_tests': len([q for q in results['performance_data'] if 'error' not in q.get('hybrid', {})]),
                'total_tests': len(test_queries)
            }
            
        except Exception as e:
            results['error'] = str(e)
        
        return results
