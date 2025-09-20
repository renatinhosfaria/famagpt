"""
Evolution API webhook parser implementation
"""

import hashlib
import hmac
from typing import Optional, Dict, Any
from datetime import datetime

from ...domain.protocols import WebhookParserProtocol
from ...domain.entities import (
    WhatsAppMessage, Contact, MediaInfo,
    MessageType, MessageStatus
)

# Shared modules
from shared.src.utils.logging import get_logger


class EvolutionWebhookParser(WebhookParserProtocol):
    """Parser for Evolution API webhooks"""
    
    def __init__(self):
        self.logger = get_logger("evolution_parser")
    
    async def parse_incoming_message(
        self,
        webhook_data: Dict[str, Any]
    ) -> Optional[WhatsAppMessage]:
        """
        Parse Evolution API webhook data into WhatsAppMessage
        
        Args:
            webhook_data: Raw webhook data from Evolution API
            
        Returns:
            Parsed WhatsAppMessage or None if parsing fails
        """
        try:
            # Minimal, privacy-safe log
            instance_id = webhook_data.get("instance", "")
            has_data = bool(webhook_data.get("data"))
            self.logger.info("Parsing webhook data", instance_id=instance_id, has_data=has_data)
            
            # Log webhook structure (top level keys only for debugging)
            self.logger.info("Webhook structure", webhook_keys=list(webhook_data.keys()))
            
            # Extract basic webhook info
            instance_id = webhook_data.get("instance", "")
            data = webhook_data.get("data", {})
            
            if not data:
                self.logger.warning("No data field in webhook")
                return None
            
            # Log data structure
            self.logger.info("Data structure", data_keys=list(data.keys()) if data else [])
            
            # Check if it's a message event
            if not self._is_message_event(data):
                # Log estrutura dos dados para debugging (sem dados sensíveis)
                self.logger.info("Not a message event, skipping", 
                               event_type=data.get("event"), 
                               status=data.get("status"), 
                               has_message=bool(data.get("message")),
                               has_key=bool(data.get("key")),
                               data_keys=list(data.keys())[:10])  # Limit to avoid huge logs
                
                
                return None
            
            # Extract message info
            message_info = data.get("message", {})
            key_info = data.get("key", {})
            
            message_id = key_info.get("id", "")
            phone_number = key_info.get("remoteJid", "").replace("@s.whatsapp.net", "")
            
            if not message_id or not phone_number:
                self.logger.warning("Missing message ID or phone number")
                return None
            
            # Extract contact info
            contact = self._extract_contact_info(data)
            
            # Extract message content and type
            message_type, content, media_info = self._extract_message_content(message_info)
            
            # Extract WhatsApp message ID for idempotency
            wa_message_id = self.extract_wa_message_id(data)
            
            if not wa_message_id:
                self.logger.warning("Message sem wa_message_id, pulando")
                return None
            
            # Parse timestamp
            timestamp = self._parse_timestamp(message_info.get("messageTimestamp"))
            
            # Check if it's a reply
            reply_to = None
            if "contextInfo" in message_info and "quotedMessage" in message_info["contextInfo"]:
                reply_to = message_info["contextInfo"].get("stanzaId")
            
            # Check if forwarded
            forwarded = message_info.get("contextInfo", {}).get("isForwarded", False)
            
            return WhatsAppMessage(
                message_id=message_id,
                instance_id=instance_id,
                phone_number=phone_number,
                contact=contact,
                message_type=message_type,
                content=content,
                timestamp=timestamp,
                status=MessageStatus.RECEIVED,
                media_info=media_info,
                raw_data=webhook_data,
                reply_to=reply_to,
                forwarded=forwarded,
                wa_message_id=wa_message_id
            )
            
        except Exception as e:
            self.logger.error(f"Error parsing webhook data: {str(e)}")
            return None
    
    def extract_wa_message_id(self, data: Dict[str, Any]) -> Optional[str]:
        """Extract WhatsApp message ID para idempotência"""
        return data.get("key", {}).get("id")

    def validate_webhook_signature(
        self,
        payload: str,
        signature: str,
        secret: str
    ) -> bool:
        """
        Validate webhook signature using HMAC
        
        Args:
            payload: Raw webhook payload
            signature: Webhook signature from header
            secret: Webhook secret key
            
        Returns:
            True if signature is valid
        """
        try:
            # Create expected signature
            expected_signature = hmac.new(
                secret.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # Remove 'sha256=' prefix if present
            if signature.startswith('sha256='):
                signature = signature[7:]
            
            # Compare signatures
            return hmac.compare_digest(expected_signature, signature)
            
        except Exception as e:
            self.logger.error(f"Error validating signature: {str(e)}")
            return False
    
    def _is_message_event(self, data: Dict[str, Any]) -> bool:
        """Check if webhook data contains a message event"""
        # Check if it's a message event (not just delivery acknowledgment)
        has_message = "message" in data
        has_key = "key" in data
        
        # Skip delivery acknowledgments, unless it contains actual message content
        status = data.get("status", "")
        is_delivery_ack = status in ["DELIVERY_ACK", "READ_ACK", "PLAYED_ACK"]
        
        # TEMPORARY FIX: Check if message has actual content even in DELIVERY_ACK
        has_message_content = False
        if has_message and data.get("message"):
            message_data = data.get("message", {})
            
            # DEBUG: Print message structure 
            print(f"WEBHOOK DEBUG - MESSAGE STRUCTURE: {list(message_data.keys())}")
            if message_data:
                for key, value in message_data.items():
                    if isinstance(value, dict):
                        print(f"WEBHOOK DEBUG - {key}: {list(value.keys())}")
                    else:
                        print(f"WEBHOOK DEBUG - {key}: {type(value)}")
            
            # Check for any actual message content
            has_message_content = any([
                message_data.get("conversation"),
                message_data.get("extendedTextMessage"),
                message_data.get("imageMessage"),
                message_data.get("videoMessage"), 
                message_data.get("audioMessage"),
                message_data.get("documentMessage"),
                message_data.get("stickerMessage"),
                message_data.get("locationMessage"),
                message_data.get("contactMessage")
            ])
            
            print(f"WEBHOOK DEBUG - HAS_MESSAGE_CONTENT: {has_message_content}")
        
        # Message event validation logging
        should_process = has_message and has_key and (not is_delivery_ack or has_message_content)
        if not should_process:
            self.logger.info("Message event validation", 
                           has_message=has_message, 
                           has_key=has_key, 
                           status=status, 
                           is_delivery_ack=is_delivery_ack,
                           has_message_content=has_message_content)
        
        # Process if it has valid message structure and content
        return should_process
    
    def _extract_contact_info(self, data: Dict[str, Any]) -> Contact:
        """Extract contact information from webhook data"""
        key = data.get("key", {})
        
        phone = key.get("remoteJid", "").replace("@s.whatsapp.net", "")
        push_name = data.get("pushName", "")
        
        return Contact(
            phone=phone,
            name=push_name,
            push_name=push_name
        )
    
    def _extract_message_content(
        self,
        message_info: Dict[str, Any]
    ) -> tuple[MessageType, str, Optional[MediaInfo]]:
        """Extract message content and type"""
        
        # Text message
        if "conversation" in message_info:
            return MessageType.TEXT, message_info["conversation"], None
        
        # Extended text message
        if "extendedTextMessage" in message_info:
            text_msg = message_info["extendedTextMessage"]
            return MessageType.TEXT, text_msg.get("text", ""), None
        
        # Image message
        if "imageMessage" in message_info:
            img_msg = message_info["imageMessage"]
            media_info = MediaInfo(
                mime_type=img_msg.get("mimetype"),
                file_size=img_msg.get("fileLength"),
                caption=img_msg.get("caption", ""),
                url=img_msg.get("url")
            )
            return MessageType.IMAGE, img_msg.get("caption", ""), media_info
        
        # Video message
        if "videoMessage" in message_info:
            vid_msg = message_info["videoMessage"]
            media_info = MediaInfo(
                mime_type=vid_msg.get("mimetype"),
                file_size=vid_msg.get("fileLength"),
                caption=vid_msg.get("caption", ""),
                url=vid_msg.get("url")
            )
            return MessageType.VIDEO, vid_msg.get("caption", ""), media_info
        
        # Audio message
        if "audioMessage" in message_info:
            audio_msg = message_info["audioMessage"]
            media_info = MediaInfo(
                mime_type=audio_msg.get("mimetype"),
                file_size=audio_msg.get("fileLength"),
                url=audio_msg.get("url")
            )
            return MessageType.AUDIO, "[Áudio]", media_info
        
        # Voice message
        if "ptt" in message_info.get("audioMessage", {}):
            audio_msg = message_info["audioMessage"]
            media_info = MediaInfo(
                mime_type=audio_msg.get("mimetype"),
                file_size=audio_msg.get("fileLength"),
                url=audio_msg.get("url")
            )
            return MessageType.VOICE, "[Mensagem de voz]", media_info
        
        # Document message
        if "documentMessage" in message_info:
            doc_msg = message_info["documentMessage"]
            media_info = MediaInfo(
                mime_type=doc_msg.get("mimetype"),
                file_size=doc_msg.get("fileLength"),
                file_name=doc_msg.get("fileName"),
                url=doc_msg.get("url")
            )
            return MessageType.DOCUMENT, doc_msg.get("fileName", "[Documento]"), media_info
        
        # Sticker message
        if "stickerMessage" in message_info:
            return MessageType.STICKER, "[Figurinha]", None
        
        # Location message
        if "locationMessage" in message_info:
            loc_msg = message_info["locationMessage"]
            lat = loc_msg.get("degreesLatitude", 0)
            lng = loc_msg.get("degreesLongitude", 0)
            return MessageType.LOCATION, f"📍 Localização: {lat}, {lng}", None
        
        # Contact message
        if "contactMessage" in message_info:
            contact_msg = message_info["contactMessage"]
            return MessageType.CONTACT, f"📞 Contato: {contact_msg.get('displayName', 'Desconhecido')}", None
        
        # Unknown message type
        self.logger.warning("Unknown message type", keys=list(message_info.keys()))
        return MessageType.UNKNOWN, "[Tipo de mensagem não suportado]", None
    
    def _parse_timestamp(self, timestamp: Any) -> datetime:
        """Parse message timestamp"""
        try:
            if isinstance(timestamp, (int, float)):
                return datetime.fromtimestamp(timestamp)
            elif isinstance(timestamp, str):
                # Try parsing as ISO format
                return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            else:
                return datetime.utcnow()
        except Exception:
            return datetime.utcnow()
