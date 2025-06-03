"""Interface de chat avec gestion des entrées et interruptions"""

from pathlib import Path
import sys
import signal
import asyncio
from typing import Optional, Callable, Any
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.markdown import Markdown

from ..utils.config import Config
from ..clients.gemini_client import GeminiClient, DuplicateFileError
from ..clients.perplexity_client import PerplexityClient
from ..tools.perplexity_tool import PerplexityTool
from ..models.citation import CitationManager
from ..models.message import MessageRole
from ..utils.history import ChatHistory
from ..ui.file_manager import FileManager


class ChatInterface:
    """Interface de chat avec gestion avancée des entrées et des coûts"""
    
    def __init__(self, config: Config):
        self.config = config
        self.console = Console()
        self.interrupted = False
        
        # Clients et outils
        self.gemini_client = GeminiClient(config)
        self.perplexity_client = PerplexityClient(config) if config.has_perplexity else None
        self.citation_manager = CitationManager()
        self.history = ChatHistory(config)
        self.file_manager = FileManager()
        
        # Stocker perplexity_tool comme attribut d'instance
        self.perplexity_tool = None
        
        # Configuration de l'interruption
        self._setup_signal_handlers()
        
        # Initialiser le chat
        self._initialize_chat()
    
    def _setup_signal_handlers(self):
        """Configure les gestionnaires de signaux pour l'interruption"""
        def signal_handler(sig, frame):
            self.interrupted = True
            self.console.print("\n🛑 Interruption détectée...", style="yellow")
        
        signal.signal(signal.SIGINT, signal_handler)
    
    def _initialize_chat(self):
        """Initialise le chat Gemini avec les outils"""
        tools = None
        if self.perplexity_client:
            self.perplexity_tool = PerplexityTool(self.perplexity_client, self.citation_manager)
            tools = [self.perplexity_tool.get_tool_config()]
        
        self.gemini_client.initialize_chat(tools)
    

    def _simple_input(self) -> Optional[str]:
        """Entrée simple avec une seule ligne"""
        try:
            return Prompt.ask("💬 Votre message")
        except KeyboardInterrupt:
            self.interrupted = True
            return None
    
    def _display_message(self, content: str, role: str = "assistant"):
        """Affiche un message formaté"""
        style = "blue" if role == "user" else "green"
        emoji = "👤" if role == "user" else "🤖"
        
        panel = Panel(
            Markdown(content),
            title=f"{emoji} {role.title()}",
            border_style=style
        )
        self.console.print(panel)
    
    def _stream_response(self, message: str) -> str:
        """Affiche une réponse en streaming avec calcul du coût total"""
        full_response = ""
        direct_search_completed = False
        
        # Variables pour tracking des coûts
        gemini_cost = 0.0
        perplexity_total_cost = 0.0
        
        # Réinitialiser le tracking des coûts de Perplexity
        if self.perplexity_tool:
            self.perplexity_tool.reset_cost_tracking()
        
        try:
            self.console.print("🤖 Gemini:", style="green bold")
            
            for chunk in self.gemini_client.send_message_stream(message):
                if self.interrupted:
                    self.console.print("\n🛑 Réponse interrompue", style="yellow")
                    break
                
                # Extraire le coût Gemini
                if chunk.startswith("GEMINI_TOTAL_PRICE :"):
                    try:
                        gemini_cost = float(chunk.split(":")[1].strip().replace("$", ""))
                    except:
                        pass
                
                # Vérifier si c'est un function call
                if chunk.startswith("FUNCTION_CALL:"):
                    parts = chunk.split(":", 2)
                    if len(parts) == 3:
                        tool_name = parts[1]
                        query = parts[2]
                        
                        if tool_name == "perplexity_direct_search":
                            # RECHERCHE DIRECTE - Réponse finale à l'utilisateur
                            if self.perplexity_client and self.perplexity_tool:
                                try:
                                    self.console.print(f"\n🔍 Recherche directe : {query}", style="cyan bold")
                                    search_result = self.perplexity_client.search(query)
                                    self.citation_manager.add_search_result(search_result)
                                    
                                    # Ajouter le coût de cette recherche
                                    perplexity_total_cost += search_result.total_cost
                                    
                                    # Afficher les citations
                                    if search_result.citations:
                                        self.console.print("\n📚 Sources :", style="cyan bold")
                                        for citation in search_result.citations:
                                            self.console.print(f"  {citation}", style="cyan")
                                    
                                    # Ajouter le contenu complet au contexte Gemini
                                    context_message = (
                                        f"[RECHERCHE DIRECTE] Question de l'utilisateur: {query}\n\n"
                                        f"Réponse Perplexity fournie à l'utilisateur:\n{search_result.content}\n\n"
                                        f"Sources utilisées: {[c.url for c in search_result.citations]}\n\n"
                                        f"[Cette information complète est maintenant disponible dans ton contexte "
                                        f"pour enrichir tes prochaines réponses et répondre aux questions de suivi]"
                                    )
                                    self.gemini_client.send_message(context_message)
                                    
                                    full_response = f"[Recherche directe: {query}]\n{search_result.content}"
                                    direct_search_completed = True
                                    
                                    # Arrêter le streaming car la réponse finale est donnée
                                    break
                                    
                                except Exception as e:
                                    error_msg = f"❌ Erreur lors de la recherche directe: {e}"
                                    self.console.print(error_msg, style="red")
                                    full_response += error_msg
                        
                        elif tool_name == "perplexity_help_search":
                            # RECHERCHE D'AIDE - Informations pour Gemini
                            if self.perplexity_client and self.perplexity_tool:
                                try:
                                    self.console.print(f"\n🔍 Recherche d'informations complémentaires : {query}", style="cyan")
                                    search_result = self.perplexity_client.search(query)
                                    self.citation_manager.add_search_result(search_result)
                                    
                                    # Ajouter le coût de cette recherche
                                    perplexity_total_cost += search_result.total_cost
                                    
                                    # Ajouter au contexte Gemini SILENCIEUSEMENT
                                    context_message = (
                                        f"[INFORMATIONS COMPLÉMENTAIRES] Recherche: {query}\n\n"
                                        f"Résultats trouvés:\n{search_result.content}\n\n"
                                        f"Sources: {[c.url for c in search_result.citations]}\n\n"
                                        f"[Utilise ces informations pour enrichir ta réponse initiale]"
                                    )
                                    self.gemini_client.send_message(context_message)
                                    
                                    self.console.print(f"✅ Informations ajoutées au contexte", style="green")
                                    full_response += f"[Recherche d'aide effectuée: {query}]"
                                    
                                    # Relancer le streaming pour que Gemini synthétise
                                    self.console.print("\n🤖 Synthèse avec les informations trouvées :", style="green bold")
                                    
                                    synthesis_prompt = "Maintenant, réponds à la question initiale en utilisant les informations complémentaires."
                                    
                                    for synthesis_chunk in self.gemini_client.send_message_stream(synthesis_prompt):
                                        if self.interrupted:
                                            break
                                        
                                        # Extraire le coût Gemini de la synthèse aussi
                                        if synthesis_chunk.startswith("GEMINI_TOTAL_PRICE :"):
                                            try:
                                                synthesis_cost = float(synthesis_chunk.split(":")[1].strip().replace("$", ""))
                                                gemini_cost += synthesis_cost
                                            except:
                                                pass
                                        
                                        # Ignorer les métadonnées pour la synthèse
                                        if not synthesis_chunk.startswith(("GEMINI_", "FUNCTION_CALL:")):
                                            self.console.print(synthesis_chunk, end="")
                                            full_response += synthesis_chunk
                                    
                                except Exception as e:
                                    error_msg = f"❌ Erreur lors de la recherche d'aide: {e}"
                                    self.console.print(error_msg, style="red")
                                    full_response += error_msg
                        
                        elif tool_name == "FUNCTION_CALL_UNKNOWN":
                            # Function call non reconnu
                            self.console.print(f"⚠️ Outil non reconnu: {query}", style="yellow")
                            
                else:
                    # Gestion de l'affichage des informations de tokens et prix
                    if chunk.startswith("GEMINI_PROMPT_TOKENS"):
                        self.console.print(f"\n{chunk.strip()}", style="dim")
                    elif chunk.startswith("GEMINI_OUTPUT_TOKENS"):
                        self.console.print(f"{chunk.strip()}", style="dim")
                    elif chunk.startswith("GEMINI_TOTAL_INPUT_PRICE"):
                        self.console.print(f"{chunk.strip()}", style="dim")
                    elif chunk.startswith("GEMINI_TOTAL_OUTPUT_PRICE"):
                        self.console.print(f"{chunk.strip()}", style="dim")
                    elif chunk.startswith("GEMINI_TOTAL_PRICE"):
                        self.console.print(f"{chunk.strip()}", style="cyan bold")
                    else:
                        # Affichage normal du streaming (seulement si pas de recherche directe)
                        if not direct_search_completed and chunk and not chunk.startswith(("GEMINI_", "FUNCTION_CALL:")):
                            self.console.print(chunk, end="")
                            full_response += chunk
            
            # Nouvelle ligne à la fin si streaming normal
            if not direct_search_completed and not full_response.startswith("[Recherche"):
                self.console.print()
            
            # Afficher les citations de help_search après la réponse de Gemini
            if not direct_search_completed and "[Recherche d'aide effectuée:" in full_response:
                latest_citations = self.citation_manager.get_latest_citations()
                if latest_citations:
                    self.console.print("\n📚 Sources utilisées :", style="cyan bold")
                    for citation in latest_citations:
                        self.console.print(f"  {citation}", style="cyan")
            
            # AFFICHER LE COÛT TOTAL COMBINÉ
            total_cost = gemini_cost + perplexity_total_cost
            if total_cost > 0:
                self.console.print("\n" + "="*50, style="cyan")
                self.console.print("💰 COÛT TOTAL DE L'INTERACTION", style="cyan bold")
                self.console.print("="*50, style="cyan")
                if gemini_cost > 0:
                    self.console.print(f"🤖 Gemini: {gemini_cost:.6f}$", style="cyan")
                if perplexity_total_cost > 0:
                    self.console.print(f"🔍 Perplexity: {perplexity_total_cost:.6f}$", style="cyan")
                self.console.print(f"📊 TOTAL: {total_cost:.6f}$", style="cyan bold")
                self.console.print("="*50, style="cyan")
            
            return full_response
            
        except Exception as e:
            error_msg = f"❌ Erreur lors de la génération: {e}"
            self.console.print(error_msg, style="red")
            return error_msg
                
    def _handle_command(self, command: str) -> bool:
        """Gère les commandes spéciales. Retourne True si c'est une commande."""
        if not command.startswith("/"):
            return False
        
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        try:
            if cmd == "/upload":
                self._handle_upload_command(args)
            elif cmd == "/list":
                self._handle_list_command()
            elif cmd == "/remove":
                self._handle_remove_command(args)
            elif cmd == "/clear":
                self._handle_clear_command()
            elif cmd == "/history":
                self._handle_history_command(args)
            elif cmd == "/search":
                self._handle_search_command(args)
            elif cmd == "/citations":
                self._handle_citations_command()
            elif cmd == "/costs":  # Nouvelle commande pour voir l'historique des coûts
                self._handle_costs_command()
            elif cmd == "/help":
                self._handle_help_command()
            elif cmd in ["/quit", "/exit", "/q"]:
                return self._handle_quit_command()
            else:
                self.console.print(f"❓ Commande inconnue: {cmd}", style="yellow")
                self.console.print("Tapez /help pour voir les commandes disponibles")
        
        except Exception as e:
            self.console.print(f"❌ Erreur lors de l'exécution de la commande: {e}", style="red")
        
        return True
    
    def _handle_upload_command(self, args: str):
        """Gère la commande /upload avec gestion des doublons"""
        if args:
            # Upload direct par chemin
            file_path = Path(args)
            if self.file_manager.validate_pdf_file(file_path):
                try:
                    file_info = self.gemini_client.upload_file(file_path)
                    self.console.print(f"✅ Fichier '{file_info['name']}' uploadé", style="green")
                except DuplicateFileError as e:
                    self.console.print(f"⚠️ {e}", style="yellow")
                    self.console.print("💡 Utilisez /list pour voir les fichiers déjà uploadés", style="cyan")
                except Exception as e:
                    self.console.print(f"❌ Erreur lors de l'upload: {e}", style="red")
            else:
                self.console.print(f"❌ Fichier invalide: {file_path}", style="red")
        else:
            # Sélection graphique
            try:
                file_path = self.file_manager.select_single_file()
                if file_path:
                    try:
                        file_info = self.gemini_client.upload_file(file_path)
                        self.console.print(f"✅ Fichier '{file_info['name']}' uploadé", style="green")
                    except DuplicateFileError as e:
                        self.console.print(f"⚠️ {e}", style="yellow")
                        self.console.print("💡 Utilisez /list pour voir les fichiers déjà uploadés", style="cyan")
                else:
                    self.console.print("Aucun fichier sélectionné", style="yellow")
            except Exception as e:
                self.console.print(f"❌ Erreur lors de la sélection: {e}", style="red")
    
    def _handle_list_command(self):
        """Gère la commande /list avec affichage des chemins"""
        files = self.gemini_client.get_files_info()
        if not files:
            self.console.print("📋 Aucun fichier uploadé", style="yellow")
            return
        
        self.console.print("📋 Fichiers uploadés:", style="cyan bold")
        for i, file_info in enumerate(files, 1):
            size_mb = file_info['size'] / (1024 * 1024)
            # Afficher le chemin pour aider l'utilisateur à identifier les fichiers
            self.console.print(f"  {i}. {file_info['name']} ({size_mb:.1f} MB)")
            self.console.print(f"     📁 {file_info['path']}", style="dim")
    
    def _handle_remove_command(self, args: str):
        """Gère la commande /remove"""
        if not args:
            self.console.print("Usage: /remove <index>", style="yellow")
            return
        
        try:
            index = int(args) - 1
            if self.gemini_client.remove_file(index):
                self.console.print(f"✅ Fichier #{index + 1} supprimé", style="green")
            else:
                self.console.print(f"❌ Index invalide: {index + 1}", style="red")
        except ValueError:
            self.console.print("❌ Index invalide (doit être un nombre)", style="red")
    
    def _handle_clear_command(self):
        """Gère la commande /clear"""
        self.gemini_client.clear_files()
        self.console.print("🗑️ Tous les fichiers ont été supprimés", style="green")
    
    def _handle_history_command(self, args: str):
        """Gère la commande /history"""
        if not args:
            history_text = self.history.format_for_display()
            self.console.print(history_text)
        elif args == "clear":
            self.history.clear()
            self.console.print("🗑️ Historique effacé", style="green")
        elif args.startswith("save"):
            filename = args.split(maxsplit=1)[1] if " " in args else None
            result = self.history.save_to_file(filename)
            self.console.print(result)
        elif args.isdigit():
            limit = int(args)
            history_text = self.history.format_for_display(limit)
            self.console.print(history_text)
        else:
            self.console.print("Usage: /history [clear|save [filename]|<number>]", style="yellow")
    
    def _handle_search_command(self, args: str):
        """Gère la commande /search"""
        if not self.perplexity_client:
            self.console.print("❌ Recherche non disponible (PERPLEXITY_API_KEY manquante)", style="red")
            return
        
        if not args:
            query = Prompt.ask("🔍 Requête de recherche")
        else:
            query = args
        
        if query:
            try:
                self.console.print(f"🔍 Recherche: {query}", style="cyan")
                result = self.perplexity_client.search(query)
                
                # Ajouter aux citations
                self.citation_manager.add_search_result(result)
                
                # Afficher les sources UNE SEULE FOIS
                if result.citations:
                    self.console.print("📚 Sources:", style="cyan bold")
                    for citation in result.citations:
                        self.console.print(f"  {citation}")
                
                # Ajouter au contexte Gemini silencieusement
                context_message = f"[CONTEXTE INTERNE] Recherche manuelle effectuée: {query}\n\nRésultats:\n{result.content}\n\n[Ces informations sont maintenant disponibles pour tes prochaines réponses]"
                self.gemini_client.send_message(context_message)
                
                self.console.print(f"\n✅ Recherche ajoutée au contexte Gemini", style="green")
                
            except Exception as e:
                self.console.print(f"❌ Erreur lors de la recherche: {e}", style="red")

    def _handle_costs_command(self):
        """Gère la commande /costs - affiche l'historique des coûts par recherche"""
        search_results = self.citation_manager.get_all_search_results()
        if not search_results:
            self.console.print("💰 Aucun coût de recherche enregistré", style="yellow")
            return
        
        total_cost = sum(result.total_cost for result in search_results)
        
        self.console.print("💰 Historique des coûts de recherche Perplexity:", style="cyan bold")
        self.console.print("="*60, style="cyan")
        
        for i, result in enumerate(search_results, 1):
            self.console.print(f"{i}. {result.query[:50]}{'...' if len(result.query) > 50 else ''}")
            self.console.print(f"   📅 {result.timestamp.strftime('%H:%M:%S')} | 💰 {result.total_cost:.6f}$")
            self.console.print(f"   📊 Tokens: {result.input_tokens}→{result.output_tokens} ({result.total_tokens} total)")
            self.console.print()
        
        self.console.print("="*60, style="cyan")
        self.console.print(f"💰 TOTAL PERPLEXITY: {total_cost:.6f}$", style="cyan bold")
        self.console.print("="*60, style="cyan")

    def _handle_citations_command(self):
        """Gère la commande /citations - affiche par interaction avec coûts"""
        citations_text = self.citation_manager.format_citations_by_interaction()
        self.console.print(citations_text)

    def _handle_help_command(self):
        """Affiche l'aide"""
        help_text = """
📚 Commandes disponibles:
  /upload [chemin]    - Upload un fichier PDF
  /list              - Liste les fichiers uploadés
  /remove <index>    - Supprime un fichier
  /clear             - Supprime tous les fichiers
  /history           - Affiche l'historique
  /history clear     - Efface l'historique
  /history save      - Sauvegarde l'historique
  /search <requête>  - Recherche avec Perplexity
  /citations         - Affiche les citations avec coûts
  /costs             - Affiche l'historique des coûts Perplexity
  /help              - Affiche cette aide
  /quit, /exit, /q   - Quitter

💡 Conseils:
  - Utilisez Ctrl+C pour interrompre une réponse
  - Les PDFs uploadés restent en contexte
  - L'historique est sauvegardé automatiquement
  - Le coût total (Gemini + Perplexity) s'affiche après chaque interaction
  
🔍 Recherche automatique:
  - Questions sans document → Recherche directe
  - Questions sur document → Recherche d'aide pour enrichir l'analyse
        """
        self.console.print(Panel(help_text, title="Aide", border_style="blue"))
    
    def _handle_quit_command(self) -> bool:
        """Gère la commande /quit"""
        self.console.print("👋 Au revoir !", style="cyan")
        return True
    
    def run(self):
        """Lance l'interface de chat"""
        # Vérifier la configuration
        errors = self.config.validate()
        if any("GEMINI_API_KEY" in error for error in errors):
            self.console.print("❌ GEMINI_API_KEY manquante", style="red")
            return
        
        if not self.config.has_perplexity:
            self.console.print("⚠️ Recherche Perplexity désactivée (clé API manquante)", style="yellow")
        
        # Message de bienvenue
        welcome_panel = Panel(
            "🤖 Chat Gemini avec support PDF et recherche Perplexity\n"
            "Tapez /help pour voir les commandes disponibles\n"
            "Utilisez Ctrl+C pour interrompre une réponse\n\n"
            "🔍 Recherche intelligente:\n"
            "• Questions générales → Recherche directe Perplexity\n"
            "• Questions sur documents → Recherche d'aide + analyse Gemini\n\n"
            "💰 Le coût total (Gemini + Perplexity) s'affiche après chaque interaction",
            title="Bienvenue",
            border_style="green"
        )
        self.console.print(welcome_panel)
        
        # Boucle principale
        while not self.interrupted:
            try:
                # Réinitialiser l'état d'interruption
                self.interrupted = False
                
                # Obtenir l'entrée utilisateur
                user_input = self._simple_input()
                
                if user_input is None or self.interrupted:
                    continue
                
                user_input = user_input.strip()
                if not user_input:
                    continue
                
                # Vérifier si c'est une commande
                if self._handle_command(user_input):
                    if user_input.lower() in ["/quit", "/exit", "/q"]:
                        break
                    continue
                
                # Ajouter à l'historique
                self.history.add_message(MessageRole.USER, user_input)
                
                # Traiter le message
                response = self._stream_response(user_input)
                
                if response and not self.interrupted:
                    # Ajouter à l'historique
                    self.history.add_message(MessageRole.ASSISTANT, response)
                    
            
            except KeyboardInterrupt:
                self.interrupted = True
                self.console.print("\n🛑 Utilisation interrompue", style="yellow")
                
                try:
                    choice = Prompt.ask("Voulez-vous quitter ? (o/N)", default="N")
                    if choice.lower() in ['o', 'oui', 'y', 'yes']:
                        break
                except KeyboardInterrupt:
                    break
            
            except Exception as e:
                self.console.print(f"❌ Erreur inattendue: {e}", style="red")