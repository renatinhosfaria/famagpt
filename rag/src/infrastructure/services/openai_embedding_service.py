"""
OpenAI embedding service for RAG
"""

import asyncio
import hashlib
from typing import List
import time

from openai import AsyncOpenAI

from shared.src.utils.logging import get_logger
from shared.src.utils.config import get_settings

from ...domain.protocols.rag_service import EmbeddingServiceProtocol, CacheServiceProtocol


logger = get_logger("rag.openai_embeddings")
settings = get_settings()


class OpenAIEmbeddingService(EmbeddingServiceProtocol):
    """OpenAI embedding service implementation"""
    
    def __init__(self, cache_service: CacheServiceProtocol = None):
        self.client = AsyncOpenAI(api_key=settings.ai.openai_api_key)
        self.model = settings.ai.embedding_model or "text-embedding-ada-002"
        self.dimension = 1536
        self.cache_service = cache_service
        self.max_batch_size = 100  # OpenAI limit
        self.rate_limit_delay = 0.1  # Delay between requests
    
    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for single text"""
        try:
            # Check cache first
            if self.cache_service:
                text_hash = self._generate_text_hash(text)
                cached_embedding = await self.cache_service.get_cached_embeddings(text_hash)
                if cached_embedding:
                    logger.debug(f"Cache hit for embedding: {text[:50]}...")
                    return cached_embedding
            
            # Clean and truncate text if too long
            cleaned_text = self._clean_text_for_embedding(text)
            
            start_time = time.time()
            
            response = await self.client.embeddings.create(
                model=self.model,
                input=cleaned_text,
                encoding_format="float"
            )
            
            processing_time = time.time() - start_time
            embedding = response.data[0].embedding
            
            # Cache the result
            if self.cache_service:
                text_hash = self._generate_text_hash(text)
                await self.cache_service.cache_embeddings(
                    text_hash, 
                    embedding, 
                    ttl_seconds=86400  # 24 hours
                )
            
            logger.debug(
                f"Generated embedding for text ({len(text)} chars) "
                f"in {processing_time:.3f}s"
            )
            
            return embedding
            
        except Exception as e:
            logger.error(f"Error generating embedding for text: {str(e)}")
            raise RuntimeError(f"Embedding generation failed: {str(e)}") from e
    
    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts"""
        try:
            if not texts:
                return []
            
            all_embeddings = []
            
            # Process in batches to respect API limits
            for i in range(0, len(texts), self.max_batch_size):
                batch = texts[i:i + self.max_batch_size]
                batch_embeddings = await self._process_batch(batch)
                all_embeddings.extend(batch_embeddings)
                
                # Rate limiting
                if i + self.max_batch_size < len(texts):
                    await asyncio.sleep(self.rate_limit_delay)
            
            logger.info(f"Generated embeddings for {len(texts)} texts")
            return all_embeddings
            
        except Exception as e:
            logger.error(f"Error generating batch embeddings: {str(e)}")
            raise RuntimeError(f"Batch embedding generation failed: {str(e)}") from e
    
    async def _process_batch(self, texts: List[str]) -> List[List[float]]:
        """Process a single batch of texts"""
        try:
            # Check cache for each text
            cached_embeddings = []
            texts_to_process = []
            cache_indices = {}
            
            if self.cache_service:
                for i, text in enumerate(texts):
                    text_hash = self._generate_text_hash(text)
                    cached = await self.cache_service.get_cached_embeddings(text_hash)
                    if cached:
                        cached_embeddings.append((i, cached))
                    else:
                        texts_to_process.append(text)
                        cache_indices[len(texts_to_process) - 1] = (i, text_hash)
            else:
                texts_to_process = texts
            
            # Process uncached texts
            new_embeddings = []
            if texts_to_process:
                cleaned_texts = [
                    self._clean_text_for_embedding(text) 
                    for text in texts_to_process
                ]
                
                start_time = time.time()
                response = await self.client.embeddings.create(
                    model=self.model,
                    input=cleaned_texts,
                    encoding_format="float"
                )
                processing_time = time.time() - start_time
                
                new_embeddings = [data.embedding for data in response.data]
                
                # Cache new embeddings
                if self.cache_service:
                    for j, embedding in enumerate(new_embeddings):
                        if j in cache_indices:
                            _, text_hash = cache_indices[j]
                            await self.cache_service.cache_embeddings(
                                text_hash,
                                embedding,
                                ttl_seconds=86400
                            )
                
                logger.debug(
                    f"Generated {len(new_embeddings)} new embeddings "
                    f"in {processing_time:.3f}s"
                )
            
            # Combine cached and new embeddings in correct order
            final_embeddings = [None] * len(texts)
            
            # Place cached embeddings
            for i, cached in cached_embeddings:
                final_embeddings[i] = cached
            
            # Place new embeddings
            new_idx = 0
            for i in range(len(texts)):
                if final_embeddings[i] is None:
                    final_embeddings[i] = new_embeddings[new_idx]
                    new_idx += 1
            
            return final_embeddings
            
        except Exception as e:
            logger.error(f"Error processing embedding batch: {str(e)}")
            raise
    
    def get_embedding_dimension(self) -> int:
        """Get dimension of embeddings"""
        return self.dimension
    
    def _clean_text_for_embedding(self, text: str) -> str:
        """Clean and prepare text for embedding"""
        if not text:
            return ""
        
        # Truncate if too long (OpenAI limit is ~8191 tokens)
        max_chars = 30000  # Conservative estimate
        if len(text) > max_chars:
            text = text[:max_chars]
            logger.debug(f"Truncated text for embedding: {len(text)} chars")
        
        # Basic cleaning
        text = text.strip()
        
        # Replace multiple whitespace with single space
        import re
        text = re.sub(r'\s+', ' ', text)
        
        return text
    
    def _generate_text_hash(self, text: str) -> str:
        """Generate hash for text caching"""
        return hashlib.md5(f"{self.model}:{text}".encode()).hexdigest()