"""Gestion de l'historique des conversations"""

import json
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from ..models.message import ChatMessage, MessageRole
from ..utils.config import Config


class ChatHistory:
    """Gestionnaire de l'historique des conversations"""
    
    def __init__(self, config: Config):
        self.config = config
        self.messages: List[ChatMessage] = []
    
    def add_message(self, role: MessageRole, content: str, files: Optional[List[str]] = None) -> None:
        """Ajoute un message à l'historique"""
        message = ChatMessage(
            role=role,
            content=content,
            files=files or []
        )
        self.messages.append(message)
        
        # Limiter la taille de l'historique
        if len(self.messages) > self.config.max_history_length:
            self.messages = self.messages[-self.config.max_history_length:]
    
    def get_messages(self, limit: Optional[int] = None) -> List[ChatMessage]:
        """Retourne les messages (optionnellement limités)"""
        if limit:
            return self.messages[-limit:]
        return self.messages.copy()
    
    def clear(self) -> None:
        """Efface l'historique"""
        self.messages.clear()
    
    def format_for_display(self, limit: Optional[int] = None) -> str:
        """Formate l'historique pour affichage"""
        messages = self.get_messages(limit)
        
        if not messages:
            return "📋 Aucun message dans l'historique."
        
        lines = ["📚 Historique de conversation:", "=" * 50]
        
        for i, message in enumerate(messages, 1):
            lines.append(f"\n{i}. {message.format_for_display()}")
        
        return "\n".join(lines)
    
    def save_to_file(self, filename: Optional[str] = None) -> str:
        """Sauvegarde l'historique dans un fichier"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"conversation_{timestamp}.json"
        
        file_path = self.config.history_dir / filename
        
        try:
            # Préparer les données pour la sérialisation
            data = {
                "timestamp": datetime.now().isoformat(),
                "messages": [
                    {
                        "role": msg.role.value,
                        "content": msg.content,
                        "timestamp": msg.timestamp.isoformat(),
                        "files": msg.files
                    }
                    for msg in self.messages
                ]
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            return f"✅ Historique sauvegardé dans {file_path}"
            
        except Exception as e:
            return f"❌ Erreur lors de la sauvegarde: {e}"
    
    def load_from_file(self, file_path: Path) -> str:
        """Charge l'historique depuis un fichier"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.messages.clear()
            
            for msg_data in data.get("messages", []):
                message = ChatMessage(
                    role=MessageRole(msg_data["role"]),
                    content=msg_data["content"],
                    timestamp=datetime.fromisoformat(msg_data["timestamp"]),
                    files=msg_data.get("files", [])
                )
                self.messages.append(message)
            
            return f"✅ Historique chargé depuis {file_path}"
            
        except Exception as e:
            return f"❌ Erreur lors du chargement: {e}"