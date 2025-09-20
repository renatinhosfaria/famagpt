"""
Domain entities for webhook messages
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum


class MessageType(str, Enum):
    """Types of messages supported by WhatsApp"""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    VOICE = "voice"
    STICKER = "sticker"
    LOCATION = "location"
    CONTACT = "contact"
    UNKNOWN = "unknown"


class MessageStatus(str, Enum):
    """Status of message processing"""
    RECEIVED = "received"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"


@dataclass
class Contact:
    """WhatsApp contact information"""
    phone: str
    name: Optional[str] = None
    push_name: Optional[str] = None
    profile_pic_url: Optional[str] = None


@dataclass
class MediaInfo:
    """Media file information"""
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    file_name: Optional[str] = None
    url: Optional[str] = None
    caption: Optional[str] = None


@dataclass
class WhatsAppMessage:
    """WhatsApp message entity"""
    message_id: str
    instance_id: str
    phone_number: str
    contact: Contact
    message_type: MessageType
    content: str
    timestamp: datetime
    status: MessageStatus = MessageStatus.RECEIVED
    media_info: Optional[MediaInfo] = None
    raw_data: Optional[Dict[str, Any]] = None
    reply_to: Optional[str] = None
    forwarded: bool = False
    wa_message_id: Optional[str] = None
    
    def is_media_message(self) -> bool:
        """Check if message contains media"""
        return self.message_type in [
            MessageType.IMAGE, MessageType.VIDEO, 
            MessageType.AUDIO, MessageType.DOCUMENT, MessageType.VOICE
        ]
    
    def to_orchestrator_format(self) -> Dict[str, Any]:
        """Convert to format expected by orchestrator"""
        return {
            "message_id": self.message_id,
            "instance_id": self.instance_id,
            "phone_number": self.phone_number,
            "contact": {
                "phone": self.contact.phone,
                "name": self.contact.name,
                "push_name": self.contact.push_name
            },
            "message_type": self.message_type.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "media_info": {
                "mime_type": self.media_info.mime_type,
                "file_size": self.media_info.file_size,
                "file_name": self.media_info.file_name,
                "url": self.media_info.url,
                "caption": self.media_info.caption
            } if self.media_info else None,
            "reply_to": self.reply_to,
            "forwarded": self.forwarded
        }


@dataclass
class OutgoingMessage:
    """Message to be sent via WhatsApp"""
    instance_id: str
    phone_number: str
    content: str
    message_type: MessageType = MessageType.TEXT
    media_url: Optional[str] = None
    reply_to: Optional[str] = None
    
    def to_evolution_api_format(self) -> Dict[str, Any]:
        """Convert to Evolution API format"""
        payload = {
            "number": self.phone_number,
            "text": self.content
        }
        
        if self.message_type != MessageType.TEXT and self.media_url:
            media_key = {
                MessageType.IMAGE: "imageMessage",
                MessageType.VIDEO: "videoMessage", 
                MessageType.AUDIO: "audioMessage",
                MessageType.DOCUMENT: "documentMessage"
            }.get(self.message_type, "textMessage")
            
            payload = {
                "number": self.phone_number,
                media_key: {
                    "image" if self.message_type == MessageType.IMAGE else "media": self.media_url,
                    "caption": self.content if self.content else ""
                }
            }
        
        if self.reply_to:
            payload["quoted"] = {
                "key": {
                    "remoteJid": f"{self.phone_number}@s.whatsapp.net",
                    "fromMe": False,
                    "id": self.reply_to
                }
            }
            
        return payload