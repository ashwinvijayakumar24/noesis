from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class ChatMessage(BaseModel):
    id: str
    project_id: str
    user_id: str
    role: str  # 'user' or 'assistant'
    content: str
    sources: Optional[List[Dict[str, Any]]] = None
    model: Optional[str] = None
    created_at: datetime

class ChatMessageCreate(BaseModel):
    project_id: str
    role: str
    content: str
    sources: Optional[List[Dict[str, Any]]] = None
    model: Optional[str] = None
