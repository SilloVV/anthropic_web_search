"""Modèles pour les messages de chat"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from enum import Enum


class MessageRole(Enum):
    """Rôles des messages"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class ChatMessage:
    """Message dans le chat"""
    role: MessageRole
    content: str
    timestamp: datetime = None
    files: List[str] = None
    citations: List = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.files is None:
            self.files = []
        if self.citations is None:
            self.citations = []
    
    def format_for_display(self) -> str:
        """Formate le message pour affichage"""
        role_emoji = "👤" if self.role == MessageRole.USER else "🤖"
        time_str = self.timestamp.strftime("%H:%M:%S")
        
        header = f"[{time_str}] {role_emoji} {self.role.value.title()}"
        if self.files:
            header += f" (avec {len(self.files)} fichier(s))"
        
        return f"{header}:\n{self.content}"