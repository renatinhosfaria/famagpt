-- Adicionar colunas para idempotência de mensagens WhatsApp
ALTER TABLE messages ADD COLUMN wa_message_id TEXT;
ALTER TABLE messages ADD COLUMN processing_status VARCHAR(20) DEFAULT 'pending';
ALTER TABLE messages ADD COLUMN processed_at TIMESTAMP;
ALTER TABLE messages ADD COLUMN retry_count INTEGER DEFAULT 0;

-- Criar índices para performance
CREATE UNIQUE INDEX ux_messages_wa ON messages(wa_message_id) WHERE wa_message_id IS NOT NULL;
CREATE INDEX idx_messages_status ON messages(processing_status, created_at);