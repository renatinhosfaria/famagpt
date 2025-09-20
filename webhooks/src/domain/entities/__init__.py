"""
Domain entities for webhooks service
"""

from .message import (
    WhatsAppMessage,
    OutgoingMessage,
    Contact,
    MediaInfo,
    MessageType,
    MessageStatus
)

__all__ = [
    "WhatsAppMessage",
    "OutgoingMessage", 
    "Contact",
    "MediaInfo",
    "MessageType",
    "MessageStatus"
]