"""
Database connection and utilities.
"""
import asyncio
from typing import Any, Dict, List, Optional, Union
from contextlib import asynccontextmanager
import asyncpg
from asyncpg import Connection, Pool

from ..utils.config import DatabaseSettings
from ..utils.logging import get_logger


logger = get_logger(__name__)


class DatabaseClient:
    """Async PostgreSQL client wrapper."""
    
    def __init__(self, settings: DatabaseSettings):
        self.settings = settings
        self._pool: Optional[Pool] = None
    
    async def connect(self) -> None:
        """Create connection pool."""
        try:
            # Use DATABASE_URL directly if available
            if self.settings.url:
                self._pool = await asyncpg.create_pool(
                    dsn=self.settings.url,
                    min_size=self.settings.pool_size // 2,
                    max_size=self.settings.pool_size,
                    max_inactive_connection_lifetime=self.settings.pool_timeout
                )
            else:
                # Respect environment/database configuration for SSL; do not force disable
                self._pool = await asyncpg.create_pool(
                    host=self.settings.host,
                    port=self.settings.port,
                    database=self.settings.database,
                    user=self.settings.username,
                    password=self.settings.password,
                    min_size=self.settings.pool_size // 2,
                    max_size=self.settings.pool_size,
                    max_inactive_connection_lifetime=self.settings.pool_timeout
                )
            
            # Test connection
            async with self._pool.acquire() as conn:
                await conn.execute("SELECT 1")
            
            logger.info(
                "Connected to database",
                host=self.settings.host,
                database=self.settings.database
            )
            
        except Exception as e:
            logger.error("Failed to connect to database", error=str(e))
            raise
    
    async def disconnect(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            logger.info("Disconnected from database")
    
    @property
    def pool(self) -> Pool:
        """Get connection pool."""
        if not self._pool:
            raise RuntimeError("Database client not connected")
        return self._pool
    
    @asynccontextmanager
    async def acquire_connection(self):
        """Acquire database connection from pool."""
        async with self.pool.acquire() as connection:
            yield connection
    
    async def execute(
        self,
        query: str,
        *args,
        timeout: Optional[float] = None
    ) -> str:
        """Execute query without returning results."""
        async with self.acquire_connection() as conn:
            return await conn.execute(query, *args, timeout=timeout)
    
    async def fetch_one(
        self,
        query: str,
        *args,
        timeout: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """Fetch one row."""
        async with self.acquire_connection() as conn:
            row = await conn.fetchrow(query, *args, timeout=timeout)
            return dict(row) if row else None
    
    async def fetch_all(
        self,
        query: str,
        *args,
        timeout: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """Fetch all rows."""
        async with self.acquire_connection() as conn:
            rows = await conn.fetch(query, *args, timeout=timeout)
            return [dict(row) for row in rows]
    
    async def fetch_value(
        self,
        query: str,
        *args,
        timeout: Optional[float] = None
    ) -> Any:
        """Fetch single value."""
        async with self.acquire_connection() as conn:
            return await conn.fetchval(query, *args, timeout=timeout)
    
    async def execute_many(
        self,
        query: str,
        args_list: List[tuple],
        timeout: Optional[float] = None
    ) -> None:
        """Execute query multiple times with different parameters."""
        async with self.acquire_connection() as conn:
            await conn.executemany(query, args_list, timeout=timeout)
    
    @asynccontextmanager
    async def transaction(self):
        """Database transaction context manager."""
        async with self.acquire_connection() as conn:
            async with conn.transaction():
                yield conn
    
    async def copy_to_table(
        self,
        table_name: str,
        records: List[Dict[str, Any]],
        columns: Optional[List[str]] = None
    ) -> None:
        """Bulk insert using COPY command."""
        if not records:
            return
        
        if columns is None:
            columns = list(records[0].keys())
        
        # Convert records to tuples
        data = [tuple(record.get(col) for col in columns) for record in records]
        
        async with self.acquire_connection() as conn:
            await conn.copy_records_to_table(
                table_name,
                records=data,
                columns=columns
            )
    
    async def create_tables_if_not_exists(self) -> None:
        """Create tables if they don't exist."""
        
        logger.info("Creating database tables...")
        
        # Execute SQL commands in separate chunks to avoid syntax issues
        sql_commands = [
            # Extensions
            'CREATE EXTENSION IF NOT EXISTS "uuid-ossp";',
            'CREATE EXTENSION IF NOT EXISTS "vector";',
            
            # Function first
            """
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = NOW();
                RETURN NEW;
            END;
            $$ language 'plpgsql';
            """,
            
            # Tables
            """
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                phone VARCHAR(20) UNIQUE NOT NULL,
                name VARCHAR(255),
                email VARCHAR(255),
                preferences JSONB DEFAULT '{}',
                location JSONB,
                is_active BOOLEAN DEFAULT true,
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            """,
            
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                status VARCHAR(20) DEFAULT 'active',
                context JSONB DEFAULT '{}',
                last_activity TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                agent_assignments JSONB DEFAULT '{}',
                metadata JSONB DEFAULT '{}',
                version INTEGER DEFAULT 1,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            """,
            
            """
            CREATE TABLE IF NOT EXISTS messages (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                content TEXT NOT NULL,
                message_type VARCHAR(20) NOT NULL,
                status VARCHAR(20) DEFAULT 'received',
                metadata JSONB DEFAULT '{}',
                source_message_id VARCHAR(255),
                processed_content TEXT,
                attachments JSONB DEFAULT '[]',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            """,
            
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                task_type VARCHAR(100) NOT NULL,
                agent_type VARCHAR(50) NOT NULL,
                input_data JSONB NOT NULL,
                output_data JSONB,
                status VARCHAR(20) DEFAULT 'pending',
                priority VARCHAR(20) DEFAULT 'normal',
                conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
                parent_task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
                dependencies JSONB DEFAULT '[]',
                retry_count INTEGER DEFAULT 0,
                error_message TEXT,
                started_at TIMESTAMP WITH TIME ZONE,
                completed_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            """,
            
            """
            CREATE TABLE IF NOT EXISTS properties (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                title VARCHAR(500) NOT NULL,
                description TEXT,
                price DECIMAL(15,2),
                property_type VARCHAR(100),
                location JSONB,
                bedrooms INTEGER,
                bathrooms INTEGER,
                area_sqm DECIMAL(10,2),
                features JSONB DEFAULT '[]',
                images JSONB DEFAULT '[]',
                source_url VARCHAR(1000),
                source_name VARCHAR(255),
                is_active BOOLEAN DEFAULT true,
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            """,
            
            """
            CREATE TABLE IF NOT EXISTS memory_entries (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
                content TEXT NOT NULL,
                memory_type VARCHAR(50) NOT NULL,
                importance_score DECIMAL(5,2) DEFAULT 0.0,
                access_count INTEGER DEFAULT 0,
                last_accessed TIMESTAMP WITH TIME ZONE,
                tags JSONB DEFAULT '[]',
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            """,
            
            """
            CREATE TABLE IF NOT EXISTS documents (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                title VARCHAR(500) NOT NULL,
                content TEXT NOT NULL,
                source VARCHAR(255) NOT NULL,
                document_type VARCHAR(100),
                metadata JSONB DEFAULT '{}',
                embedding vector(1536),
                chunk_id VARCHAR(255),
                parent_document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            """,
            
            """
            CREATE TABLE IF NOT EXISTS workflow_executions (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                workflow_name VARCHAR(255) NOT NULL,
                conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                status VARCHAR(20) DEFAULT 'pending',
                input_data JSONB NOT NULL,
                output_data JSONB,
                current_node VARCHAR(255),
                executed_nodes JSONB DEFAULT '[]',
                node_outputs JSONB DEFAULT '{}',
                error_message TEXT,
                priority VARCHAR(20) DEFAULT 'normal',
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            """,
            
            """
            CREATE TABLE IF NOT EXISTS node_executions (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                workflow_execution_id UUID NOT NULL REFERENCES workflow_executions(id) ON DELETE CASCADE,
                node_name VARCHAR(255) NOT NULL,
                agent_type VARCHAR(50) NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                input_data JSONB NOT NULL,
                output_data JSONB,
                error_message TEXT,
                execution_time_ms INTEGER,
                retry_count INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            """
        ]
        
        # Execute each command separately
        async with self.transaction() as conn:
            for i, command in enumerate(sql_commands):
                try:
                    await conn.execute(command.strip())
                    logger.debug(f"Executed SQL command {i+1}/{len(sql_commands)}")
                except Exception as e:
                    logger.error(f"Failed to execute SQL command {i+1}: {e}")
                    logger.error(f"Command: {command[:100]}...")
                    raise
        
        # Create indexes in a separate transaction
        await self._create_indexes()
        
        # Create triggers
        await self._create_triggers()
        
        logger.info("Database tables created/verified successfully")
    
    async def _create_indexes(self) -> None:
        """Create database indexes."""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);",
            "CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_conversations_status ON conversations(status);",
            "CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);",
            "CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_messages_type ON messages(message_type);",
            "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);",
            "CREATE INDEX IF NOT EXISTS idx_tasks_agent_type ON tasks(agent_type);",
            "CREATE INDEX IF NOT EXISTS idx_properties_type ON properties(property_type);",
            "CREATE INDEX IF NOT EXISTS idx_properties_active ON properties(is_active);",
            "CREATE INDEX IF NOT EXISTS idx_memory_user_id ON memory_entries(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_memory_type ON memory_entries(memory_type);",
            "CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source);",
            "CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(document_type);",
            "CREATE INDEX IF NOT EXISTS idx_workflow_executions_status ON workflow_executions(status);",
            "CREATE INDEX IF NOT EXISTS idx_workflow_executions_conversation_id ON workflow_executions(conversation_id);",
            "CREATE INDEX IF NOT EXISTS idx_workflow_executions_user_id ON workflow_executions(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_node_executions_workflow_id ON node_executions(workflow_execution_id);",
            "CREATE INDEX IF NOT EXISTS idx_node_executions_status ON node_executions(status);",
            "CREATE INDEX IF NOT EXISTS idx_documents_embedding ON documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);"
        ]
        
        async with self.transaction() as conn:
            for index_sql in indexes:
                try:
                    await conn.execute(index_sql)
                except Exception as e:
                    logger.warning(f"Failed to create index: {e}")
    
    async def _create_triggers(self) -> None:
        """Create database triggers."""
        triggers = [
            "CREATE TRIGGER IF NOT EXISTS update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();",
            "CREATE TRIGGER IF NOT EXISTS update_conversations_updated_at BEFORE UPDATE ON conversations FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();",
            "CREATE TRIGGER IF NOT EXISTS update_messages_updated_at BEFORE UPDATE ON messages FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();",
            "CREATE TRIGGER IF NOT EXISTS update_tasks_updated_at BEFORE UPDATE ON tasks FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();",
            "CREATE TRIGGER IF NOT EXISTS update_properties_updated_at BEFORE UPDATE ON properties FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();",
            "CREATE TRIGGER IF NOT EXISTS update_memory_entries_updated_at BEFORE UPDATE ON memory_entries FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();",
            "CREATE TRIGGER IF NOT EXISTS update_documents_updated_at BEFORE UPDATE ON documents FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();",
            "CREATE TRIGGER IF NOT EXISTS update_workflow_executions_updated_at BEFORE UPDATE ON workflow_executions FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();",
            "CREATE TRIGGER IF NOT EXISTS update_node_executions_updated_at BEFORE UPDATE ON node_executions FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();"
        ]
        
        async with self.transaction() as conn:
            for trigger_sql in triggers:
                try:
                    await conn.execute(trigger_sql)
                except Exception as e:
                    logger.warning(f"Failed to create trigger: {e}")
