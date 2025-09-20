"""
Domain protocols for webhooks service
"""

from .webhook_parser import WebhookParserProtocol
from .message_sender import MessageSenderProtocol
from .orchestrator_client import OrchestratorClientProtocol
from .database_client import DatabaseClientProtocol

__all__ = [
    "WebhookParserProtocol",
    "MessageSenderProtocol", 
    "OrchestratorClientProtocol",
    "DatabaseClientProtocol"
]