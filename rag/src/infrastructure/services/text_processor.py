"""
Text processing and document chunking service
"""

import re
from typing import List
from datetime import datetime

from shared.src.utils.logging import get_logger

from ...domain.entities.document import Document, DocumentChunk, DocumentIngestRequest, DocumentStatus, DocumentType
from ...domain.protocols.rag_service import DocumentProcessorProtocol


logger = get_logger("rag.text_processor")


class TextProcessor(DocumentProcessorProtocol):
    """Text processing and chunking service"""
    
    def __init__(self):
        pass
    
    async def process_document(self, request: DocumentIngestRequest) -> Document:
        """Process and chunk a document for RAG"""
        try:
            logger.info(f"Processing document: {request.title}")
            
            # Convert document_type string to enum if needed
            doc_type = request.document_type
            if isinstance(doc_type, str):
                try:
                    doc_type = DocumentType(doc_type.upper())
                except ValueError:
                    doc_type = DocumentType.TEXT  # Default fallback
                    logger.warning(f"Unknown document type '{request.document_type}', using TEXT as default")
            
            # Create document entity
            document = Document(
                title=request.title,
                content=request.content,
                document_type=doc_type,
                source_url=request.source_url,
                metadata=request.metadata or {},
                status=DocumentStatus.PROCESSING
            )
            
            # Generate document ID
            document.id = document.generate_id()
            
            # Clean and preprocess content
            cleaned_content = self._clean_text(request.content)
            document.content = cleaned_content
            
            # Create chunks
            chunk_texts = await self.chunk_text(
                cleaned_content,
                request.chunk_size,
                request.chunk_overlap
            )
            
            # Create chunk entities
            chunks = []
            for i, chunk_text in enumerate(chunk_texts):
                chunk = DocumentChunk(
                    document_id=document.id,
                    content=chunk_text,
                    chunk_index=i,
                    start_position=self._calculate_start_position(chunk_texts, i, request.chunk_overlap),
                    end_position=self._calculate_end_position(chunk_texts, i, request.chunk_overlap),
                    metadata={
                        "chunk_size": len(chunk_text),
                        "document_title": request.title,
                        "document_type": request.document_type.value,
                        **request.metadata
                    }
                )
                chunk.id = chunk.generate_id()
                chunks.append(chunk)
            
            document.chunks = chunks
            document.status = DocumentStatus.COMPLETED
            document.processed_at = datetime.utcnow()
            
            logger.info(
                f"Document processed successfully: {request.title}. "
                f"Created {len(chunks)} chunks from {len(cleaned_content)} characters"
            )
            
            return document
            
        except Exception as e:
            logger.error(f"Error processing document {request.title}: {str(e)}")
            raise RuntimeError(f"Document processing failed: {str(e)}") from e
    
    async def chunk_text(
        self, 
        text: str, 
        chunk_size: int = 1000, 
        chunk_overlap: int = 200
    ) -> List[str]:
        """Split text into overlapping chunks"""
        try:
            if not text or len(text.strip()) == 0:
                return []
            
            # Split by paragraphs first for better chunk boundaries
            paragraphs = self._split_by_paragraphs(text)
            
            chunks = []
            current_chunk = ""
            
            for paragraph in paragraphs:
                # If adding this paragraph would exceed chunk size
                if len(current_chunk) + len(paragraph) > chunk_size:
                    # If current chunk is not empty, save it
                    if current_chunk.strip():
                        chunks.append(current_chunk.strip())
                        
                        # Start new chunk with overlap from previous chunk
                        if chunk_overlap > 0 and len(current_chunk) > chunk_overlap:
                            overlap_text = current_chunk[-chunk_overlap:]
                            # Find word boundary for cleaner overlap
                            word_boundary = overlap_text.rfind(' ')
                            if word_boundary > 0:
                                overlap_text = overlap_text[word_boundary:].strip()
                            current_chunk = overlap_text + " " + paragraph
                        else:
                            current_chunk = paragraph
                    else:
                        # If paragraph itself is too long, split it
                        if len(paragraph) > chunk_size:
                            paragraph_chunks = self._split_long_paragraph(paragraph, chunk_size)
                            chunks.extend(paragraph_chunks[:-1])  # Add all but last
                            current_chunk = paragraph_chunks[-1] if paragraph_chunks else ""
                        else:
                            current_chunk = paragraph
                else:
                    # Add paragraph to current chunk
                    if current_chunk:
                        current_chunk += "\n\n" + paragraph
                    else:
                        current_chunk = paragraph
            
            # Add the last chunk if it's not empty
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            
            # Filter out very small chunks (less than 10% of chunk_size)
            min_chunk_size = max(50, chunk_size // 10)
            filtered_chunks = [chunk for chunk in chunks if len(chunk) >= min_chunk_size]
            
            logger.debug(
                f"Text chunking completed: {len(text)} chars -> {len(filtered_chunks)} chunks "
                f"(avg size: {sum(len(c) for c in filtered_chunks) // len(filtered_chunks) if filtered_chunks else 0})"
            )
            
            return filtered_chunks
            
        except Exception as e:
            logger.error(f"Error chunking text: {str(e)}")
            raise RuntimeError(f"Text chunking failed: {str(e)}") from e
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        if not text:
            return ""
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove excessive line breaks (more than 2 consecutive)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Clean up common markdown/html artifacts
        text = re.sub(r'\[.*?\]\(.*?\)', '', text)  # Remove markdown links
        text = re.sub(r'<.*?>', '', text)  # Remove HTML tags
        
        # Simple quote normalization
        text = text.replace('"', '"').replace('"', '"').replace('"', '"')
        text = text.replace(''', "'").replace(''', "'")
        
        # Remove extra spaces around punctuation
        text = re.sub(r'\s+([,.!?;:])', r'\1', text)
        
        return text.strip()
    
    def _split_by_paragraphs(self, text: str) -> List[str]:
        """Split text into paragraphs"""
        # Split by double line breaks (paragraph boundaries)
        paragraphs = re.split(r'\n\s*\n', text)
        
        # Clean up each paragraph
        cleaned_paragraphs = []
        for para in paragraphs:
            para = para.strip()
            if para:
                cleaned_paragraphs.append(para)
        
        return cleaned_paragraphs
    
    def _split_long_paragraph(self, paragraph: str, max_size: int) -> List[str]:
        """Split a long paragraph into smaller chunks at sentence boundaries"""
        if len(paragraph) <= max_size:
            return [paragraph]
        
        # Split by sentences
        sentences = re.split(r'(?<=[.!?])\s+', paragraph)
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) <= max_size:
                if current_chunk:
                    current_chunk += " " + sentence
                else:
                    current_chunk = sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                
                # If single sentence is too long, split by words
                if len(sentence) > max_size:
                    word_chunks = self._split_by_words(sentence, max_size)
                    chunks.extend(word_chunks[:-1])
                    current_chunk = word_chunks[-1] if word_chunks else ""
                else:
                    current_chunk = sentence
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    def _split_by_words(self, text: str, max_size: int) -> List[str]:
        """Split text by words when sentences are too long"""
        words = text.split()
        chunks = []
        current_chunk = ""
        
        for word in words:
            if len(current_chunk) + len(word) + 1 <= max_size:
                if current_chunk:
                    current_chunk += " " + word
                else:
                    current_chunk = word
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = word
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    def _calculate_start_position(self, chunks: List[str], index: int, overlap: int) -> int:
        """Calculate start position of chunk in original document"""
        if index == 0:
            return 0
        
        position = 0
        for i in range(index):
            position += len(chunks[i])
            if i > 0:  # Account for overlap reduction
                position -= overlap
        
        return max(0, position)
    
    def _calculate_end_position(self, chunks: List[str], index: int, overlap: int) -> int:
        """Calculate end position of chunk in original document"""
        start_pos = self._calculate_start_position(chunks, index, overlap)
        return start_pos + len(chunks[index])