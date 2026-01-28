-- Phase 4: Create chat_messages table for storing conversation history
-- This table stores all chat messages between users and the AI assistant

-- ============================================
-- CHAT_MESSAGES TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS chat_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE NOT NULL,
  user_id UUID NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
  content TEXT NOT NULL,
  sources JSONB,  -- Array of source chunks used to generate the response
  model TEXT,  -- AI model used (e.g., 'gpt-4o')
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_chat_messages_project_id ON chat_messages(project_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id ON chat_messages(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON chat_messages(created_at);

-- Comments for documentation
COMMENT ON TABLE chat_messages IS 'Chat conversation history for RAG Q&A interface';
COMMENT ON COLUMN chat_messages.role IS 'Message sender: user, assistant, or system';
COMMENT ON COLUMN chat_messages.sources IS 'JSON array of document chunks used as context for AI response';
