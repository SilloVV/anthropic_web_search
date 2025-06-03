"""Client pour l'API Perplexity avec calcul de coût"""

import json
import httpx
from typing import Optional, Generator
from urllib.parse import urlparse

from ..utils.config import Config
from ..models.citation import Citation, SearchResult


class PerplexityClient:
    """Client pour l'API Perplexity"""
    
    def __init__(self, config: Config):
        self.config = config
        self.api_key = config.perplexity_api_key
        self.base_url = "https://api.perplexity.ai/chat/completions"
    
    def _extract_domain(self, url: str) -> str:
        """Extrait le domaine d'une URL"""
        try:
            if url.startswith('http'):
                return urlparse(url).netloc
            return ""
        except:
            return ""
    
    async def search_stream_async(self, query: str):
        """Effectue une recherche avec streaming asynchrone et calcul de coût"""
        if not self.api_key:
            raise ValueError("PERPLEXITY_API_KEY manquante")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "temperature": 0.2,
            "top_p": 0.9,
            "return_images": False,
            "return_related_questions": False,
            "top_k": 0,
            "stream": True,
            "presence_penalty": 0,
            "frequency_penalty": 1,
            "web_search_options": {"search_context_size": "medium"},
            "model": self.config.perplexity_model,
            "messages": [
                {
                    "content": "Tu es un expert juridique français. Donne une réponse précise et complète avec les références légales appropriées.",
                    "role": "system"
                },
                {
                    "role": "user",
                    "content": query
                }
            ],
            "max_tokens": self.config.perplexity_max_tokens,
            "search_domain_filter": self.config.allowed_domains
        }
        
        citations = []
        full_message = ""
        
        # Variables pour les coûts
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0
        
        # Import ici pour éviter les dépendances circulaires
        from rich.console import Console
        console = Console()
        
        try:
            console.print("🌐 Recherche Perplexity en cours...", style="cyan")
            last_chunk = None
            async with httpx.AsyncClient() as client:
                async with client.stream('POST', self.base_url, json=payload, headers=headers) as response:
                    async for line in response.aiter_lines():
                        if line.startswith('data: '):
                            data = line[6:]
                            if data != '[DONE]' and data.strip():
                                try:
                                    chunk = json.loads(data)
                                    last_chunk = chunk  # Mémoriser le dernier chunk pour les citations
                                    
                                    # Contenu du message - afficher en BLANC (pas de style)
                                    if chunk and 'choices' in chunk and len(chunk['choices']) > 0:
                                        delta = chunk['choices'][0].get('delta', {})
                                        if 'content' in delta:
                                            message = delta['content']
                                            full_message += message
                                            # Afficher le chunk en temps réel EN BLANC
                                            console.print(message, end="")
                                    
                                    # Citations - collecter sans afficher
                                    if 'citations' in chunk and chunk['citations']:
                                        raw_citations = chunk['citations']
                                        citations = []
                                        for i, citation_url in enumerate(raw_citations, 1):
                                            citation = Citation(
                                                number=i,
                                                title=f"Source {i}",
                                                url=citation_url,
                                                snippet="",
                                                source=self._extract_domain(citation_url)
                                            )
                                            citations.append(citation)
                                            
                                            
                                except json.JSONDecodeError:
                                    continue
            
            console.print("\n")  # Nouvelle ligne à la fin
            
            # Extraire les informations de coût
            if last_chunk and 'usage' in last_chunk:
                usage = last_chunk['usage']
                input_tokens = usage.get('prompt_tokens', 0)
                output_tokens = usage.get('completion_tokens', 0)
                total_tokens = usage.get('total_tokens', 0)
            
            # Calculer le coût total
            input_price = input_tokens * self.config.perplexity_input_price_per_token
            output_price = output_tokens * self.config.perplexity_output_price_per_token
            total_cost = self.config.perplexity_base_search_price + input_price + output_price
            
            # Afficher les informations de coût (comme avant)
            print("PERPLEXITY_INPUT TOKENS :", input_tokens)
            print("PERPLEXITY_OUTPUT TOKENS :", output_tokens)
            print("PERPLEXITY_TOTAL TOKENS :", total_tokens)
            print(f"PERPLEXITY_TOTAL_PRICE : {total_cost:.6f} $\n")
            
            return SearchResult(
                content=full_message,
                citations=citations,
                query=query,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                total_cost=total_cost
            )
            
        except Exception as e:
            console.print(f"\n❌ Erreur lors de la recherche: {e}", style="red")
            raise Exception(f"Erreur lors de la recherche: {e}")

    def search(self, query: str) -> SearchResult:
        """Recherche synchrone qui retourne le résultat complet"""
        import asyncio
        
        # Exécuter la recherche asynchrone
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(self.search_stream_async(query))
            return result
        except Exception as e:
            return SearchResult(
                content=f"Erreur lors de la recherche: {e}",
                citations=[],
                query=query,
                total_cost=0.0
            )