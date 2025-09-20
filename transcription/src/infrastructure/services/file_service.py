"""
File handling service for audio files
"""

import tempfile
import os
import asyncio
from typing import dict
import subprocess
import shutil

from shared.src.utils.logging import get_logger

from ...domain.protocols.transcription_service import FileServiceProtocol


logger = get_logger("transcription.file_service")


class FileService(FileServiceProtocol):
    """File handling service implementation"""
    
    def __init__(self):
        self.temp_dir = tempfile.gettempdir()
        self.supported_extensions = ['.mp3', '.wav', '.m4a', '.ogg', '.webm']
    
    async def save_temp_file(
        self, 
        content: bytes, 
        filename: str
    ) -> str:
        """
        Save uploaded file to temporary location
        
        Args:
            content: File content bytes
            filename: Original filename
            
        Returns:
            Path to temporary file
        """
        try:
            # Create temp file with proper extension
            file_ext = self._get_file_extension(filename)
            
            # Create temporary file
            temp_fd, temp_path = tempfile.mkstemp(
                suffix=file_ext,
                prefix="transcription_",
                dir=self.temp_dir
            )
            
            # Write content to temp file
            with os.fdopen(temp_fd, 'wb') as temp_file:
                temp_file.write(content)
            
            logger.debug(f"Saved temp file: {temp_path} ({len(content)} bytes)")
            return temp_path
            
        except Exception as e:
            logger.error(f"Error saving temp file: {str(e)}")
            raise RuntimeError(f"Failed to save temporary file: {str(e)}") from e
    
    async def cleanup_temp_file(self, file_path: str) -> None:
        """
        Clean up temporary file
        
        Args:
            file_path: Path to temporary file to delete
        """
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
                logger.debug(f"Cleaned up temp file: {file_path}")
            else:
                logger.debug(f"Temp file already deleted: {file_path}")
                
        except Exception as e:
            logger.warning(f"Error cleaning up temp file {file_path}: {str(e)}")
    
    async def get_file_info(self, file_path: str) -> dict:
        """
        Get file information (size, duration, etc.)
        
        Args:
            file_path: Path to audio file
            
        Returns:
            Dictionary with file information
        """
        try:
            info = {
                "size_bytes": 0,
                "duration_seconds": None,
                "format": None,
                "sample_rate": None,
                "channels": None
            }
            
            # Get file size
            if os.path.exists(file_path):
                info["size_bytes"] = os.path.getsize(file_path)
            
            # Get audio metadata using ffprobe if available
            try:
                duration = await self._get_audio_duration(file_path)
                info["duration_seconds"] = duration
            except Exception as e:
                logger.debug(f"Could not get audio duration: {e}")
            
            return info
            
        except Exception as e:
            logger.warning(f"Error getting file info for {file_path}: {str(e)}")
            return {"size_bytes": 0, "duration_seconds": None}
    
    async def _get_audio_duration(self, file_path: str) -> float:
        """
        Get audio file duration using ffprobe
        
        Args:
            file_path: Path to audio file
            
        Returns:
            Duration in seconds
        """
        try:
            # Check if ffprobe is available
            if not shutil.which("ffprobe"):
                logger.debug("ffprobe not available, skipping duration detection")
                return None
            
            # Run ffprobe to get duration
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                file_path
            ]
            
            # Run command asynchronously
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.debug(f"ffprobe failed: {stderr.decode()}")
                return None
            
            # Parse JSON output
            import json
            probe_data = json.loads(stdout.decode())
            
            if "format" in probe_data and "duration" in probe_data["format"]:
                duration = float(probe_data["format"]["duration"])
                return duration
            
            return None
            
        except Exception as e:
            logger.debug(f"Error getting audio duration: {e}")
            return None
    
    def _get_file_extension(self, filename: str) -> str:
        """
        Get file extension from filename
        
        Args:
            filename: Original filename
            
        Returns:
            File extension (e.g., '.mp3')
        """
        _, ext = os.path.splitext(filename.lower())
        
        # Map common audio MIME types to extensions
        if not ext:
            return '.wav'  # Default extension
        
        if ext in self.supported_extensions:
            return ext
        
        # Default to .wav for unknown extensions
        return '.wav'