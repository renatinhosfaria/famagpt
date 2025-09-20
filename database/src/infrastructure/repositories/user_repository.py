"""
PostgreSQL implementation of UserRepository
"""

from typing import Optional, List
from uuid import UUID
import asyncpg

from ...domain.interfaces import UserRepository
from shared.src.domain.models import User

# Import shared modules
import sys
sys.path.append('/app/shared')
from shared.utils.logger import setup_logger


class PostgreSQLUserRepository(UserRepository):
    """PostgreSQL implementation of UserRepository"""
    
    def __init__(self, connection_pool: asyncpg.Pool):
        self.pool = connection_pool
        self.logger = setup_logger("user_repository")
    
    async def create(self, user: User) -> User:
        """Create a new user"""
        try:
            query = """
                INSERT INTO users (
                    id, phone_number, name, push_name, profile_pic_url,
                    preferences, created_at, updated_at, is_active
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING *
            """
            
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(
                    query,
                    user.id,
                    user.phone_number,
                    user.name,
                    user.push_name,
                    user.preferences,
                    user.created_at,
                    user.updated_at,
                    user.is_active
                )
                
                if row:
                    self.logger.info(f"User created successfully: {user.id}")
                    return User(**dict(row))
                else:
                    raise Exception("Failed to create user")
                    
        except Exception as e:
            self.logger.error(f"Error creating user: {str(e)}")
            raise
    
    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        """Get user by ID"""
        try:
            query = "SELECT * FROM users WHERE id = $1 AND is_active = true"
            
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(query, user_id)
                
                if row:
                    return User(**dict(row))
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting user by ID: {str(e)}")
            raise
    
    async def get_by_phone(self, phone: str) -> Optional[User]:
        """Get user by phone number"""
        try:
            query = "SELECT * FROM users WHERE phone_number = $1 AND is_active = true"
            
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(query, phone)
                
                if row:
                    return User(**dict(row))
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting user by phone: {str(e)}")
            raise
    
    async def update(self, user: User) -> User:
        """Update user"""
        try:
            query = """
                UPDATE users SET
                    name = $2,
                    push_name = $3,
                    profile_pic_url = $4,
                    preferences = $5,
                    updated_at = $6,
                    is_active = $7
                WHERE id = $1
                RETURNING *
            """
            
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(
                    query,
                    user.id,
                    user.name,
                    user.push_name,
                    user.profile_pic_url,
                    user.preferences,
                    user.updated_at,
                    user.is_active
                )
                
                if row:
                    self.logger.info(f"User updated successfully: {user.id}")
                    return User(**dict(row))
                else:
                    raise Exception("Failed to update user")
                    
        except Exception as e:
            self.logger.error(f"Error updating user: {str(e)}")
            raise
    
    async def delete(self, user_id: UUID) -> None:
        """Soft delete user"""
        try:
            query = """
                UPDATE users SET 
                    is_active = false,
                    updated_at = NOW()
                WHERE id = $1
            """
            
            async with self.pool.acquire() as connection:
                result = await connection.execute(query, user_id)
                
                if result == "UPDATE 1":
                    self.logger.info(f"User deleted successfully: {user_id}")
                else:
                    raise Exception("User not found or already deleted")
                    
        except Exception as e:
            self.logger.error(f"Error deleting user: {str(e)}")
            raise
    
    async def get_all_active_users(self) -> List[User]:
        """Get all active users"""
        try:
            query = "SELECT * FROM users WHERE is_active = true ORDER BY created_at DESC"
            
            async with self.pool.acquire() as connection:
                rows = await connection.fetch(query)
                
                return [User(**dict(row)) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Error getting all active users: {str(e)}")
            raise
    
    async def search_by_name(self, name: str) -> List[User]:
        """Search users by name"""
        try:
            query = """
                SELECT * FROM users 
                WHERE (name ILIKE $1 OR push_name ILIKE $1) 
                AND is_active = true 
                ORDER BY created_at DESC
            """
            
            search_pattern = f"%{name}%"
            
            async with self.pool.acquire() as connection:
                rows = await connection.fetch(query, search_pattern)
                
                return [User(**dict(row)) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Error searching users by name: {str(e)}")
            raise