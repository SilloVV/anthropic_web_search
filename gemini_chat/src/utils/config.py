"""Configuration et variables d'environnement"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv


class Config:
    """Gestionnaire de configuration centralisé"""
    
    def __init__(self):
        # Charger les variables d'environnement
        load_dotenv()
        
        #  Modèle 
        self.gemini_model = "gemini-2.5-flash-preview-05-20"
        self.perplexity_model = "sonar"
        
        # Clés API
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.perplexity_api_key = os.getenv("PERPLEXITY_API_KEY")
        
        # Configuration du chat
        self.max_tokens = 3000
        self.temperature = 0.3
        self.max_history_length = 100
        
        # prix gemini
        self.gemini_input_price_per_token = 0.0000001 
        self.gemini_output_price_per_token = 0.000004
        
        # prix perplexity
        self.perplexity_input_price_per_token = 0.000001
        self.perplexity_output_price_per_token = 0.000001
        self.perplexity_base_search_price = 0.008
    
        # Configuration Perplexity
        self.perplexity_timeout = 90
        self.perplexity_max_tokens = 3000
        
        #domaines 
        self.allowed_domains = ["legifrance.gouv.fr", "service-public.fr", "economie.gouv.fr" ]
        
        # Dossiers
        self.data_dir = Path("data")
        self.uploads_dir = self.data_dir / "uploads"
        self.history_dir = self.data_dir / "history"
        
        # Créer les dossiers si nécessaire
        self._create_directories()
    
    def _create_directories(self):
        """Crée les dossiers nécessaires"""
        for directory in [self.data_dir, self.uploads_dir, self.history_dir]:
            directory.mkdir(exist_ok=True)
    
    def validate(self) -> list[str]:
        """Valide la configuration et retourne les erreurs"""
        errors = []
        
        if not self.gemini_api_key:
            errors.append("GEMINI_API_KEY manquante")
        
        if not self.perplexity_api_key:
            errors.append("PERPLEXITY_API_KEY manquante (recherche désactivée)")
        
        return errors
    
    @property
    def has_perplexity(self) -> bool:
        """Vérifie si Perplexity est configuré"""
        return bool(self.perplexity_api_key)