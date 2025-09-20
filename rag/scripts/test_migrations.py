#!/usr/bin/env python3
"""
Script de teste para validar migrations do RAG Híbrido
Testa as migrations em ambiente de desenvolvimento/staging
"""

import asyncio
import asyncpg
import logging
import os
import time
from typing import Dict, List, Any, Optional
from datetime import datetime

# Setup de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MigrationTester:
    """Testa as migrations do RAG híbrido"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """Conectar ao banco de dados"""
        try:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=3,
                command_timeout=60
            )
            logger.info("Conectado ao banco de dados")
        except Exception as e:
            logger.error(f"Erro ao conectar: {e}")
            raise
    
    async def disconnect(self):
        """Desconectar do banco"""
        if self.pool:
            await self.pool.close()
            logger.info("Desconectado do banco de dados")
    
    async def check_prerequisites(self) -> Dict[str, Any]:
        """Verificar pré-requisitos para as migrations"""
        logger.info("Verificando pré-requisitos...")
        
        async with self.pool.acquire() as conn:
            # Verificar extensões
            extensions = await conn.fetch("""
                SELECT extname, extversion 
                FROM pg_extension 
                WHERE extname IN ('vector', 'pg_trgm')
            """)
            
            # Verificar tabelas existentes
            tables = await conn.fetch("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name IN ('rag_documents', 'rag_document_chunks')
            """)
            
            # Verificar se há dados existentes
            data_counts = {}
            for table in ['rag_documents', 'rag_document_chunks']:
                try:
                    count = await conn.fetchval(f"SELECT count(*) FROM {table}")
                    data_counts[table] = count
                except:
                    data_counts[table] = 0
            
            # Verificar configuração de busca
            search_config = await conn.fetchval(
                "SELECT current_setting('default_text_search_config')"
            )
            
            return {
                'extensions': {ext['extname']: ext['extversion'] for ext in extensions},
                'tables': [t['table_name'] for t in tables],
                'data_counts': data_counts,
                'search_config': search_config,
                'timestamp': datetime.now().isoformat()
            }
    
    async def create_test_data(self) -> int:
        """Criar dados de teste se não existirem"""
        logger.info("Criando dados de teste...")
        
        test_documents = [
            {
                'id': 'test_doc_001',
                'title': 'Apartamento 3 quartos Centro Uberlândia',
                'content': 'Apartamento com 3 quartos, 2 suítes, 2 vagas de garagem no centro de Uberlândia. Área construída de 120m². Valor R$ 350.000. Condomínio com piscina e área gourmet.',
                'document_type': 'property',
                'metadata': {'city': 'Uberlândia', 'type': 'apartamento', 'price': 350000}
            },
            {
                'id': 'test_doc_002', 
                'title': 'Casa residencial Bairro Tabajaras',
                'content': 'Casa residencial em bairro nobre de Uberlândia. 4 quartos sendo 2 suítes, sala ampla, cozinha gourmet, área de lazer com churrasqueira. Terreno de 300m².',
                'document_type': 'property',
                'metadata': {'city': 'Uberlândia', 'type': 'casa', 'neighborhood': 'Tabajaras'}
            },
            {
                'id': 'test_doc_003',
                'title': 'Terreno comercial Avenida João Naves',
                'content': 'Terreno comercial localizado na Avenida João Naves de Ávila, uma das principais vias de Uberlândia. Ideal para investimento comercial. Área total de 500m².',
                'document_type': 'commercial',
                'metadata': {'city': 'Uberlândia', 'type': 'terreno', 'area': 500}
            }
        ]
        
        test_chunks = []
        for doc in test_documents:
            # Simular chunks para cada documento
            content = doc['content']
            chunk_size = len(content) // 2  # Dividir em 2 chunks
            
            test_chunks.extend([
                {
                    'id': f"{doc['id']}_chunk_001",
                    'document_id': doc['id'],
                    'content': content[:chunk_size],
                    'chunk_index': 0,
                    'metadata': {**doc['metadata'], 'chunk_type': 'first_half'}
                },
                {
                    'id': f"{doc['id']}_chunk_002", 
                    'document_id': doc['id'],
                    'content': content[chunk_size:],
                    'chunk_index': 1,
                    'metadata': {**doc['metadata'], 'chunk_type': 'second_half'}
                }
            ])
        
        async with self.pool.acquire() as conn:
            # Inserir documentos de teste
            for doc in test_documents:
                await conn.execute("""
                    INSERT INTO rag_documents 
                    (id, title, content, document_type, metadata, status, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (id) DO NOTHING
                """, 
                    doc['id'], doc['title'], doc['content'], doc['document_type'],
                    doc['metadata'], 'completed', datetime.now()
                )
            
            # Inserir chunks de teste
            for chunk in test_chunks:
                await conn.execute("""
                    INSERT INTO rag_document_chunks
                    (id, document_id, content, chunk_index, metadata, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (id) DO NOTHING
                """,
                    chunk['id'], chunk['document_id'], chunk['content'],
                    chunk['chunk_index'], chunk['metadata'], datetime.now()
                )
        
        logger.info(f"Criados {len(test_documents)} documentos e {len(test_chunks)} chunks de teste")
        return len(test_chunks)
    
    async def run_migration_001(self) -> Dict[str, Any]:
        """Executar migration 001"""
        logger.info("Executando Migration 001...")
        start_time = time.time()
        
        async with self.pool.acquire() as conn:
            # Ler e executar migration 001
            with open('/var/www/famagpt/rag/migrations/001_add_fulltext_support.sql', 'r') as f:
                migration_sql = f.read()
            
            try:
                await conn.execute(migration_sql)
                execution_time = time.time() - start_time
                
                # Verificar se colunas foram criadas
                columns = await conn.fetch("""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = 'rag_document_chunks'
                    AND column_name IN ('content_tsvector', 'content_clean')
                """)
                
                # Verificar dados populados
                populated_count = await conn.fetchval("""
                    SELECT count(*) FROM rag_document_chunks 
                    WHERE content_tsvector IS NOT NULL
                """)
                
                return {
                    'success': True,
                    'execution_time': execution_time,
                    'columns_created': len(columns),
                    'populated_chunks': populated_count,
                    'columns': [dict(col) for col in columns]
                }
                
            except Exception as e:
                return {
                    'success': False,
                    'error': str(e),
                    'execution_time': time.time() - start_time
                }
    
    async def run_migration_002(self) -> Dict[str, Any]:
        """Executar migration 002"""
        logger.info("Executando Migration 002...")
        start_time = time.time()
        
        async with self.pool.acquire() as conn:
            with open('/var/www/famagpt/rag/migrations/002_create_fulltext_indexes.sql', 'r') as f:
                migration_sql = f.read()
            
            try:
                await conn.execute(migration_sql)
                execution_time = time.time() - start_time
                
                # Verificar índices criados
                indexes = await conn.fetch("""
                    SELECT indexname, tablename, indexdef
                    FROM pg_indexes
                    WHERE tablename = 'rag_document_chunks'
                    AND indexname LIKE 'idx_rag_chunks_%'
                """)
                
                return {
                    'success': True,
                    'execution_time': execution_time,
                    'indexes_created': len(indexes),
                    'indexes': [dict(idx) for idx in indexes]
                }
                
            except Exception as e:
                return {
                    'success': False,
                    'error': str(e),
                    'execution_time': time.time() - start_time
                }
    
    async def run_migration_003(self) -> Dict[str, Any]:
        """Executar migration 003"""
        logger.info("Executando Migration 003...")
        start_time = time.time()
        
        async with self.pool.acquire() as conn:
            with open('/var/www/famagpt/rag/migrations/003_create_sync_triggers.sql', 'r') as f:
                migration_sql = f.read()
            
            try:
                await conn.execute(migration_sql)
                execution_time = time.time() - start_time
                
                # Verificar triggers criados
                triggers = await conn.fetch("""
                    SELECT trigger_name, event_manipulation, event_object_table
                    FROM information_schema.triggers
                    WHERE event_object_table = 'rag_document_chunks'
                    AND trigger_name = 'trigger_sync_content_tsvector'
                """)
                
                # Verificar funções criadas
                functions = await conn.fetch("""
                    SELECT routine_name
                    FROM information_schema.routines
                    WHERE routine_type = 'FUNCTION'
                    AND routine_name LIKE '%tsvector%'
                    OR routine_name LIKE '%fulltext%'
                """)
                
                return {
                    'success': True,
                    'execution_time': execution_time,
                    'triggers_created': len(triggers),
                    'functions_created': len(functions),
                    'triggers': [dict(t) for t in triggers],
                    'functions': [dict(f) for f in functions]
                }
                
            except Exception as e:
                return {
                    'success': False,
                    'error': str(e),
                    'execution_time': time.time() - start_time
                }
    
    async def test_fulltext_search(self) -> Dict[str, Any]:
        """Testar busca full-text"""
        logger.info("Testando busca full-text...")
        
        test_queries = [
            'apartamento 3 quartos',
            'casa Tabajaras',
            'terreno comercial',
            'Uberlândia centro',
            'R$ 350.000'
        ]
        
        results = {}
        
        async with self.pool.acquire() as conn:
            for query in test_queries:
                start_time = time.time()
                
                # Busca literal
                literal_results = await conn.fetch("""
                    SELECT id, content, 
                           ts_rank_cd(content_tsvector, plainto_tsquery('portuguese', $1)) as rank
                    FROM rag_document_chunks
                    WHERE content_tsvector @@ plainto_tsquery('portuguese', $1)
                    ORDER BY rank DESC
                    LIMIT 5
                """, query)
                
                query_time = time.time() - start_time
                
                results[query] = {
                    'query_time_ms': round(query_time * 1000, 2),
                    'results_count': len(literal_results),
                    'results': [
                        {
                            'id': r['id'],
                            'content_preview': r['content'][:100] + '...',
                            'rank': float(r['rank'])
                        } for r in literal_results
                    ]
                }
        
        return results
    
    async def test_trigger_functionality(self) -> Dict[str, Any]:
        """Testar funcionalidade dos triggers"""
        logger.info("Testando triggers...")
        
        async with self.pool.acquire() as conn:
            # Inserir chunk de teste
            test_chunk_id = f'test_trigger_{int(time.time())}'
            test_content = 'Este é um teste do trigger de sincronização do tsvector'
            
            await conn.execute("""
                INSERT INTO rag_document_chunks 
                (id, document_id, content, chunk_index, created_at)
                VALUES ($1, $2, $3, $4, $5)
            """, test_chunk_id, 'test_doc_001', test_content, 999, datetime.now())
            
            # Verificar se tsvector foi criado automaticamente
            tsvector_result = await conn.fetchrow("""
                SELECT content_tsvector, content_clean
                FROM rag_document_chunks
                WHERE id = $1
            """, test_chunk_id)
            
            # Atualizar conteúdo para testar trigger de UPDATE
            new_content = 'Conteúdo atualizado para testar trigger de update'
            await conn.execute("""
                UPDATE rag_document_chunks
                SET content = $1
                WHERE id = $2
            """, new_content, test_chunk_id)
            
            # Verificar se tsvector foi atualizado
            updated_tsvector = await conn.fetchrow("""
                SELECT content_tsvector, content_clean
                FROM rag_document_chunks
                WHERE id = $1
            """, test_chunk_id)
            
            # Limpar dados de teste
            await conn.execute("DELETE FROM rag_document_chunks WHERE id = $1", test_chunk_id)
            
            return {
                'insert_trigger_worked': tsvector_result['content_tsvector'] is not None,
                'insert_tsvector_content': str(tsvector_result['content_tsvector'])[:100],
                'update_trigger_worked': updated_tsvector['content_tsvector'] is not None,
                'update_tsvector_content': str(updated_tsvector['content_tsvector'])[:100],
                'content_clean_synced': updated_tsvector['content_clean'] == new_content
            }
    
    async def run_comprehensive_test(self) -> Dict[str, Any]:
        """Executar teste completo das migrations"""
        logger.info("=== Iniciando teste completo das migrations ===")
        
        results = {
            'test_start_time': datetime.now().isoformat(),
            'prerequisites': None,
            'test_data_created': 0,
            'migrations': {},
            'fulltext_search_test': {},
            'trigger_test': {},
            'overall_success': False
        }
        
        try:
            # Verificar pré-requisitos
            results['prerequisites'] = await self.check_prerequisites()
            
            # Criar dados de teste se necessário
            if results['prerequisites']['data_counts']['rag_document_chunks'] == 0:
                results['test_data_created'] = await self.create_test_data()
            
            # Executar migrations
            results['migrations']['001'] = await self.run_migration_001()
            if results['migrations']['001']['success']:
                results['migrations']['002'] = await self.run_migration_002()
                if results['migrations']['002']['success']:
                    results['migrations']['003'] = await self.run_migration_003()
            
            # Testar funcionalidades se migrations foram bem-sucedidas
            if all(results['migrations'][m].get('success', False) for m in results['migrations']):
                results['fulltext_search_test'] = await self.test_fulltext_search()
                results['trigger_test'] = await self.test_trigger_functionality()
                results['overall_success'] = True
            
            results['test_end_time'] = datetime.now().isoformat()
            return results
            
        except Exception as e:
            logger.error(f"Erro no teste completo: {e}")
            results['error'] = str(e)
            results['test_end_time'] = datetime.now().isoformat()
            return results

async def main():
    """Função principal"""
    database_url = os.getenv('DATABASE_URL', 'postgresql://localhost:5432/famagpt')
    
    tester = MigrationTester(database_url)
    
    try:
        await tester.connect()
        results = await tester.run_comprehensive_test()
        
        # Imprimir resultados
        print("\n" + "="*60)
        print("RESULTADOS DO TESTE DE MIGRATIONS RAG HÍBRIDO")
        print("="*60)
        
        print(f"\n📋 PRÉ-REQUISITOS:")
        prereq = results['prerequisites']
        print(f"  • Extensões: {prereq['extensions']}")
        print(f"  • Tabelas: {prereq['tables']}")
        print(f"  • Dados existentes: {prereq['data_counts']}")
        print(f"  • Config busca: {prereq['search_config']}")
        
        if results['test_data_created'] > 0:
            print(f"\n📝 DADOS DE TESTE: {results['test_data_created']} chunks criados")
        
        print(f"\n🔄 MIGRATIONS:")
        for migration_num, migration_result in results['migrations'].items():
            status = "✅" if migration_result['success'] else "❌"
            print(f"  {status} Migration {migration_num}: {migration_result.get('execution_time', 0):.2f}s")
            if not migration_result['success']:
                print(f"     Erro: {migration_result.get('error', 'Desconhecido')}")
        
        if results.get('fulltext_search_test'):
            print(f"\n🔍 TESTE DE BUSCA FULL-TEXT:")
            for query, query_result in results['fulltext_search_test'].items():
                print(f"  • '{query}': {query_result['results_count']} resultados em {query_result['query_time_ms']}ms")
        
        if results.get('trigger_test'):
            print(f"\n⚙️  TESTE DE TRIGGERS:")
            trigger_result = results['trigger_test']
            print(f"  • Insert trigger: {'✅' if trigger_result['insert_trigger_worked'] else '❌'}")
            print(f"  • Update trigger: {'✅' if trigger_result['update_trigger_worked'] else '❌'}")
            print(f"  • Content sync: {'✅' if trigger_result['content_clean_synced'] else '❌'}")
        
        print(f"\n🎯 RESULTADO GERAL: {'✅ SUCESSO' if results['overall_success'] else '❌ FALHA'}")
        print("="*60)
        
    except Exception as e:
        logger.error(f"Erro na execução: {e}")
        return 1
    finally:
        await tester.disconnect()
    
    return 0 if results['overall_success'] else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)