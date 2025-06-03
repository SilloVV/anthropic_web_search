"""Client pour l'API Gemini"""

import asyncio
import sys
from typing import List, Optional, Generator, Any, Set
from pathlib import Path
from google.genai import types
from google import genai

from ..utils.config import Config
from ..models.message import ChatMessage, MessageRole


class DuplicateFileError(Exception):
    """Exception levée quand on tente d'uploader un fichier déjà présent"""
    def __init__(self, file_path: Path, existing_name: str):
        self.file_path = file_path
        self.existing_name = existing_name
        super().__init__(f"Le fichier '{file_path.name}' est déjà uploadé sous le nom '{existing_name}'")


class GeminiClient:
    """Client pour interagir avec l'API Gemini"""
    
    def __init__(self, config: Config):
        self.config = config
        self.client = genai.Client(api_key=config.gemini_api_key)
        self.chat = None
        self.uploaded_files: List[dict] = []
        self.files_sent_to_chat: Set[str] = set()  # Track des fichiers déjà envoyés au chat actuel
    
    def initialize_chat(self, tools: Optional[List] = None) -> None:
        """Initialise une nouvelle session de chat"""
        chat_config = types.GenerateContentConfig(
            system_instruction=(
                "Tu es un expert juridique français. Tu peux analyser des documents PDF "
                "et répondre aux questions les concernant.\n\n"
                "Tu as la capacité de faire des tableaux por présenter des informations de manière claire.\n\n"
                
                "RÈGLES DE RECHERCHE AVEC PERPLEXITY :\n"
                "1. Si la question est une simple salutation, politesse ou remerciement : réponds directement SANS outil\n\n"
                
                "2. Si la question ne concerne AUCUN document uploadé ET nécessite des informations d'internet :\n"
                "   → Utilise 'perplexity_direct_search' (l'utilisateur recevra directement la réponse complète)\n\n"
                
                "3. Si la question concerne le contenu d'articles de lois , jurisprudence ou réglementation :\n"
                "   → Utilise 'perplexity_direct_search' (tu recevras une réponse directe à l'utilisateur)\n\n"
                
                "4. Si la question concerne un document uploadé ET tu as besoin d'informations complémentaires :\n"
                "   → Utilise 'perplexity_help_search' (tu recevras des informations à intégrer dans ta synthèse)\n\n"
                
                "IMPORTANT :\n"
                "- perplexity_direct_search : réponse finale directe à l'utilisateur avec sources\n"
                "- perplexity_help_search : informations complémentaires pour enrichir TA réponse\n"
                "- Ne mentionne jamais ces outils dans tes réponses, utilise-les de manière transparente\n\n"
                
                "EXEMPLES D'USAGE :\n"
                "- 'Salut' → réponse directe\n"
                "- 'Quelle est la jurisprudence récente sur les contrats de travail ?' (sans document) → perplexity_direct_search\n"
                "- 'Que dit l'article 1234-5 du Code du travail ?' → perplexity_direct_search\n"
                "- 'Ce contrat est-il conforme à la réglementation actuelle ?' (avec document) → perplexity_help_search\n"
                "- 'Explique-moi ce document' (avec document) → réponse directe"
            ),
            max_output_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            tools=tools
        )
        
        self.chat = self.client.chats.create(
            model="gemini-2.0-flash",
            config=chat_config
        )
        
        # Réinitialiser le tracking des fichiers envoyés pour le nouveau chat
        self.files_sent_to_chat.clear()
    
    def _is_file_already_uploaded(self, file_path: Path) -> Optional[str]:
        """
        Vérifie si un fichier est déjà uploadé en comparant les chemins absolus.
        
        Returns:
            Le nom du fichier existant si trouvé, None sinon
        """
        absolute_path = file_path.resolve()
        
        for file_info in self.uploaded_files:
            existing_path = Path(file_info['path']).resolve()
            if absolute_path == existing_path:
                return file_info['name']
        
        return None
    
    def get_uploaded_file_paths(self) -> List[str]:
        """Retourne la liste des chemins absolus des fichiers uploadés (pour debug)"""
        return [str(Path(file_info['path']).resolve()) for file_info in self.uploaded_files]
    
    def upload_file(self, file_path: Path) -> Optional[dict]:
        """Upload un fichier vers Gemini avec vérification des doublons"""
        try:
            if not file_path.exists():
                raise FileNotFoundError(f"Le fichier {file_path} n'existe pas")
            
            if file_path.suffix.lower() != '.pdf':
                raise ValueError("Seuls les fichiers PDF sont supportés")
            
            # Vérifier les doublons
            existing_name = self._is_file_already_uploaded(file_path)
            if existing_name:
                raise DuplicateFileError(file_path, existing_name)
            
            uploaded_file = self.client.files.upload(file=file_path)
            
            # Utiliser le chemin absolu comme identifiant unique
            absolute_path = file_path.resolve()
            
            file_info = {
                'file': uploaded_file,
                'name': file_path.name,
                'path': str(absolute_path),  # Stocker le chemin absolu
                'size': file_path.stat().st_size,
                'id': str(absolute_path)  # Identifiant basé sur le chemin absolu
            }
            
            self.uploaded_files.append(file_info)
            return file_info
            
        except Exception as e:
            # Re-lever les exceptions personnalisées sans modification
            if isinstance(e, DuplicateFileError):
                raise
            raise Exception(f"Erreur lors de l'upload: {e}")
    
    def remove_file(self, index: int) -> bool:
        """Supprime un fichier uploadé de la liste des fichiers uploadés"""
        if 0 <= index < len(self.uploaded_files):
            file_info = self.uploaded_files.pop(index)
            # Retirer aussi du tracking si présent
            self.files_sent_to_chat.discard(file_info.get('id'))
            return True
        return False
    
    def clear_files(self) -> None:
        """Efface tous les fichiers uploadés"""
        self.uploaded_files.clear()
        self.files_sent_to_chat.clear()
    
    def get_files_info(self) -> List[dict]:
        """Retourne les informations des fichiers uploadés"""
        return self.uploaded_files.copy()
    
    def get_new_files(self) -> List[dict]:
        """Retourne les fichiers qui n'ont pas encore été envoyés au chat"""
        return [
            file_info for file_info in self.uploaded_files 
            if file_info.get('id') not in self.files_sent_to_chat
        ]
    
    def mark_files_as_sent(self, file_infos: List[dict]) -> None:
        """Marque les fichiers comme envoyés au chat"""
        for file_info in file_infos:
            self.files_sent_to_chat.add(file_info.get('id'))
    
    def reset_file_tracking(self) -> None:
        """Remet à zéro le tracking des fichiers (pour forcer leur re-envoi)"""
        self.files_sent_to_chat.clear()
    
    def send_message_stream(self, message: str, force_include_all_files: bool = False) -> Generator[str, None, None]:
        """
        Envoie un message et retourne un générateur de réponse avec gestion améliorée des function calls.
        
        Args:
            message: Le message à envoyer
            force_include_all_files: Si True, inclut tous les fichiers même s'ils ont déjà été envoyés
        """
        if not self.chat:
            raise RuntimeError("Chat non initialisé")
        
        # Préparer le contenu
        content_parts = [message]
        
        # Déterminer quels fichiers ajouter
        if force_include_all_files:
            files_to_send = self.uploaded_files.copy()
        else:
            # Inclure automatiquement seulement les nouveaux fichiers
            files_to_send = self.get_new_files()
        
        # Ajouter les fichiers déterminés
        for file_info in files_to_send:
            content_parts.append(file_info['file'])
        
        # Marquer les fichiers comme envoyés
        if files_to_send:
            self.mark_files_as_sent(files_to_send)
            print(f"📎 {len(files_to_send)} fichier(s) ajouté(s) au contexte: {[f['name'] for f in files_to_send]}")
        
        # Envoyer et streamer la réponse
        response_stream = self.chat.send_message_stream(content_parts)
        
        # Variables pour collecter les function calls
        collected_function_calls: List[Any] = []
        has_text_content = False
        
        # Variables pour compter les tokens de cette interaction
        interaction_total_prompt_tokens = 0
        interaction_total_output_tokens = 0
        prompt_tokens_counted = False

        # Traiter le streaming
        for chunk in response_stream:
            # Compter les tokens à partir des métadonnées d'utilisation
            if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
                # Tokens d'entrée (prompt)
                if hasattr(chunk.usage_metadata, 'prompt_token_count'):
                    prompt_tokens_value_from_chunk = chunk.usage_metadata.prompt_token_count
                    if not prompt_tokens_counted:
                        interaction_total_prompt_tokens = prompt_tokens_value_from_chunk if prompt_tokens_value_from_chunk is not None else 0
                        prompt_tokens_counted = True
                
                # Tokens de sortie (candidates/générés)
                if hasattr(chunk.usage_metadata, 'candidates_token_count'):
                    output_tokens_value_from_chunk = chunk.usage_metadata.candidates_token_count
                    if output_tokens_value_from_chunk is not None:
                        interaction_total_output_tokens += output_tokens_value_from_chunk
            
            # Collecter les "function calls"
            try:
                if hasattr(chunk, 'candidates') and chunk.candidates:
                    candidate = chunk.candidates[0]
                    if hasattr(candidate, 'content') and candidate.content and hasattr(candidate.content, 'parts'):
                        for part in candidate.content.parts:
                            if hasattr(part, 'function_call') and part.function_call:
                                collected_function_calls.append(part.function_call)
            except Exception as e:
                print(f"AVERTISSEMENT: Erreur lors du parsing d'un function call: {e}", file=sys.stderr)
                pass
            
            # Vérifier s'il y a du contenu texte
            if hasattr(chunk, 'text') and chunk.text:
                has_text_content = True
            
            # Afficher le texte en streaming seulement s'il n'y a pas de function calls
            if not collected_function_calls and has_text_content and hasattr(chunk, 'text') and chunk.text:
                yield chunk.text
        
        # Traitement des function calls collectés
        if collected_function_calls:
            for function_call in collected_function_calls:
                function_name = getattr(function_call, 'name', '')
                args = getattr(function_call, 'args', {})
                query = args.get("query", "") if hasattr(args, 'get') else ""
                
                if function_name == "perplexity_direct_search":
                    # Recherche directe - réponse immédiate à l'utilisateur
                    yield f"FUNCTION_CALL:perplexity_direct_search:{query}"
                    
                elif function_name == "perplexity_help_search":
                    # Recherche d'aide - informations pour Gemini
                    yield f"FUNCTION_CALL:perplexity_help_search:{query}"
                    
                else:
                    # Function call non reconnu
                    yield f"FUNCTION_CALL_UNKNOWN:{function_name}:{query}"

        # Yield les comptes totaux de tokens
        yield f"\nGEMINI_PROMPT_TOKENS : {interaction_total_prompt_tokens}\n"
        yield f"GEMINI_OUTPUT_TOKENS : {interaction_total_output_tokens}\n"
        
        # Prix
        input_price = (interaction_total_prompt_tokens * self.config.gemini_input_price_per_token) 
        output_price = (interaction_total_output_tokens * self.config.gemini_output_price_per_token)
        yield f"GEMINI_TOTAL_INPUT_PRICE : {input_price:.10f}$\n"
        yield f"GEMINI_TOTAL_OUTPUT_PRICE : {output_price:.10f}$\n"
        yield f"GEMINI_TOTAL_PRICE : {(input_price + output_price):.10f}$\n"

    def send_message(self, message: str, force_include_all_files: bool = False) -> str:
        """
        Envoie un message et retourne la réponse complète
        
        Args:
            message: Le message à envoyer
            force_include_all_files: Si True, inclut tous les fichiers même s'ils ont déjà été envoyés
        """
        if not self.chat:
            raise RuntimeError("Chat non initialisé")
        
        content = [message]
        
        # Déterminer quels fichiers ajouter
        if force_include_all_files:
            files_to_send = self.uploaded_files.copy()
        else:
            # Inclure automatiquement seulement les nouveaux fichiers
            files_to_send = self.get_new_files()
        
        # Ajouter les fichiers déterminés
        for file_info in files_to_send:
            content.append(file_info['file'])
        
        # Marquer les fichiers comme envoyés
        if files_to_send:
            self.mark_files_as_sent(files_to_send)
            print(f"📎 {len(files_to_send)} fichier(s) ajouté(s) au contexte: {[f['name'] for f in files_to_send]}")
        
        response = self.chat.send_message(content)
        return response.text if hasattr(response, 'text') else str(response)