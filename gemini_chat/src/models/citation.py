"""Modèles pour les citations et résultats de recherche avec coût"""

from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime


@dataclass
class Citation:
    """Citation d'une source"""
    number: int
    title: str = ""
    url: str = ""
    snippet: str = ""
    source: str = ""
    
    def __str__(self) -> str:
        return f"[{self.number}] {self.title}: {self.url}"


@dataclass
class SearchResult:
    """Résultat de recherche avec citations et coût"""
    content: str
    citations: List[Citation]
    query: str
    timestamp: datetime = None
    # Nouveaux champs pour le coût
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class CitationManager:
    """Gestionnaire des citations par interaction"""
    
    def __init__(self):
        self._search_results: List[SearchResult] = []
    
    def add_search_result(self, result: SearchResult) -> None:
        """Ajoute un résultat de recherche"""
        self._search_results.append(result)
    
    def get_latest_citations(self) -> List[Citation]:
        """Retourne les citations de la dernière recherche"""
        if not self._search_results:
            return []
        return self._search_results[-1].citations
    
    def get_latest_search_cost(self) -> float:
        """Retourne le coût de la dernière recherche"""
        if not self._search_results:
            return 0.0
        return self._search_results[-1].total_cost
    
    def get_all_search_results(self) -> List[SearchResult]:
        """Retourne tous les résultats de recherche"""
        return self._search_results.copy()
    
    def clear(self) -> None:
        """Efface toutes les citations"""
        self._search_results.clear()
    
    def format_citations_by_interaction(self) -> str:
        """Formate les citations par interaction"""
        if not self._search_results:
            return "Aucune citation disponible."
        
        lines = ["📚 Citations par interaction:\n"]
        
        for i, search_result in enumerate(self._search_results, 1):
            lines.append(f"🔍 Interaction {i}: {search_result.query}")
            lines.append(f"📅 {search_result.timestamp.strftime('%H:%M:%S')}")
            lines.append(f"💰 Coût: {search_result.total_cost:.6f}$")
            
            if search_result.citations:
                for citation in search_result.citations:
                    lines.append(f"  {citation}")
            else:
                lines.append("  Aucune source trouvée")
            lines.append("")  # Ligne vide entre interactions
        
        return "\n".join(lines)