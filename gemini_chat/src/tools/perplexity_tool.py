"""Outil Google pour intégrer Perplexity à Gemini avec gestion des coûts"""

from google.genai import types
from typing import Dict, Any

from ..clients.perplexity_client import PerplexityClient
from ..models.citation import CitationManager


class PerplexityTool:
    """Outil pour intégrer Perplexity comme fonction Google avec gestion des coûts"""
    
    def __init__(self, perplexity_client: PerplexityClient, citation_manager: CitationManager):
        self.perplexity_client = perplexity_client
        self.citation_manager = citation_manager
        self.last_search_cost = 0.0  # Stockage du dernier coût
    
    def get_direct_search_function_declaration(self) -> types.FunctionDeclaration:
        """
        Outil de recherche directe - Réponse immédiate à l'utilisateur
        Correspond au "Perplexity Search direct" du schéma
        """
        return types.FunctionDeclaration(
            name="perplexity_direct_search",
            description=(
                "Recherche directe sur internet avec Perplexity pour donner une réponse complète "
                "immédiatement à l'utilisateur. Utilise tous les domaines disponibles. "
                "À utiliser quand la question ne concerne AUCUN document uploadé et nécessite "
                "des informations actualisées d'internet."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "query": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "Requête de recherche optimisée pour obtenir une réponse complète "
                            "et actuelle à présenter directement à l'utilisateur"
                        )
                    )
                },
                required=["query"]
            )
        )
    
    def get_help_search_function_declaration(self) -> types.FunctionDeclaration:
        """
        Outil de recherche d'aide - Informations pour Gemini
        Correspond au "Perplexity Search aide Gemini" du schéma
        """
        return types.FunctionDeclaration(
            name="perplexity_help_search",
            description=(
                "Recherche d'informations complémentaires sur des sources fiables "
                "(legifrance, service-public, etc.) pour t'aider à analyser et répondre "
                "sur des documents uploadés. Les résultats sont intégrés à ton contexte "
                "pour une synthèse complète."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "query": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "Requête de recherche ciblée pour obtenir des informations "
                            "légales/officielles complémentaires à intégrer dans ta réponse"
                        )
                    )
                },
                required=["query"]
            )
        )
    
    def execute_direct_search(self, query: str) -> str:
        """
        Exécute une recherche directe (réponse immédiate utilisateur)
        Utilise tous les domaines disponibles
        """
        try:
            # Recherche avec tous les domaines pour une réponse complète
            result = self.perplexity_client.search(query)
            self.citation_manager.add_search_result(result)
            
            # Stocker le coût de cette recherche
            self.last_search_cost = result.total_cost
            
            return result.content
            
        except Exception as e:
            self.last_search_cost = 0.0
            return f"Erreur lors de la recherche directe: {e}"
    
    def execute_help_search(self, query: str) -> str:
        """
        Exécute une recherche d'aide (informations pour Gemini)
        Limitée aux domaines fiables (legifrance, service-public, etc.)
        """
        try:
            # Recherche limitée aux domaines officiels pour information fiable
            result = self.perplexity_client.search(query)
            self.citation_manager.add_search_result(result)
            
            # Stocker le coût de cette recherche
            self.last_search_cost = result.total_cost
            
            return result.content
            
        except Exception as e:
            self.last_search_cost = 0.0
            return f"Erreur lors de la recherche d'aide: {e}"
    
    def get_last_search_cost(self) -> float:
        """Retourne le coût de la dernière recherche effectuée"""
        return self.last_search_cost
    
    def reset_cost_tracking(self) -> None:
        """Remet à zéro le tracking des coûts"""
        self.last_search_cost = 0.0
    
    def get_tool_config(self) -> types.Tool:
        """Retourne la configuration des deux outils pour Gemini"""
        return types.Tool(function_declarations=[
            self.get_direct_search_function_declaration(),
            self.get_help_search_function_declaration()
        ])
    
    def get_function_mapping(self) -> Dict[str, callable]:
        """Retourne le mapping des noms de fonctions vers leurs implémentations"""
        return {
            "perplexity_direct_search": self.execute_direct_search,
            "perplexity_help_search": self.execute_help_search
        }