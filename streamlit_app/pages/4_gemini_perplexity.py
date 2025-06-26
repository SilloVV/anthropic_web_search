"""
Interface Streamlit pour le chatbot Gemini avec support PDF et recherche Perplexity
"""

import streamlit as st
import sys
import time
import asyncio
import tempfile
from pathlib import Path
from typing import List, Optional

# Configuration du path pour importer les modules
current_dir = Path(__file__).parent.absolute()  # streamlit_app/pages/
project_root = current_dir.parent.parent  # Remonte de 2 niveaux : pages -> streamlit_app -> racine
src_path = project_root / "gemini_chat" / "src"  # Pointe vers gemini_chat/src

if not src_path.exists():
    # Fallback : essayer depuis le répertoire courant
    alternative_src = Path.cwd() / "gemini_chat" / "src"
    if alternative_src.exists():
        src_path = alternative_src
    else:
        # Autre fallback : chercher src directement dans gemini_chat s'il est au même niveau
        gemini_chat_src = current_dir.parent.parent / "gemini_chat" / "src"
        if gemini_chat_src.exists():
            src_path = gemini_chat_src
        else:
            st.error("❌ Dossier 'gemini_chat/src' introuvable. Vérifiez la structure des dossiers.")
            st.info(f"📁 Recherché dans : {src_path}")
            st.info(f"📁 Répertoire actuel : {current_dir}")
            st.stop()

sys.path.insert(0, str(src_path.parent))


from src.utils.config import Config
from src.clients.gemini_client import GeminiClient, DuplicateFileError
from src.clients.perplexity_client import PerplexityClient
from src.tools.perplexity_tool import PerplexityTool
from src.models.citation import CitationManager
from src.models.message import MessageRole, ChatMessage


class StreamlitGeminiChat:
    """Interface Streamlit pour le chatbot Gemini avec Perplexity"""
    
    def __init__(self):
        self.config = Config()
        self.setup_session_state()
        self.initialize_clients()
    
    def setup_session_state(self):
        """Initialise les variables de session Streamlit"""
        if "messages" not in st.session_state:
            st.session_state.messages = []
        
        if "uploaded_files" not in st.session_state:
            st.session_state.uploaded_files = []
        
        if "citations" not in st.session_state:
            st.session_state.citations = []
        
        if "total_cost" not in st.session_state:
            st.session_state.total_cost = 0.0
        
        if "total_response_time" not in st.session_state:
            st.session_state.total_response_time = 0.0
        
        if "gemini_client" not in st.session_state:
            st.session_state.gemini_client = None
        
        if "perplexity_client" not in st.session_state:
            st.session_state.perplexity_client = None
        
        if "citation_manager" not in st.session_state:
            st.session_state.citation_manager = None
        
        if "perplexity_tool" not in st.session_state:
            st.session_state.perplexity_tool = None
    
    def initialize_clients(self):
        """Initialise les clients si pas déjà fait"""
        if st.session_state.gemini_client is None:
            st.session_state.gemini_client = GeminiClient(self.config)
            st.session_state.citation_manager = CitationManager()
            
            if self.config.has_perplexity:
                st.session_state.perplexity_client = PerplexityClient(self.config)
                st.session_state.perplexity_tool = PerplexityTool(
                    st.session_state.perplexity_client, 
                    st.session_state.citation_manager
                )
                tools = [st.session_state.perplexity_tool.get_tool_config()]
            else:
                tools = None
            
            st.session_state.gemini_client.initialize_chat(tools)
    
    def save_uploaded_file(self, uploaded_file) -> Path:
        """Sauvegarde un fichier uploadé dans un dossier temporaire"""
        temp_dir = Path(tempfile.gettempdir()) / "streamlit_gemini_uploads"
        temp_dir.mkdir(exist_ok=True)
        
        file_path = temp_dir / uploaded_file.name
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        return file_path
    
    def handle_file_uploads(self, files):
        """Traite les fichiers uploadés via chat_input"""
        if not files:
            return
        
        files_processed = 0
        for uploaded_file in files:
            # Vérifier si le fichier est déjà uploadé
            if uploaded_file.name not in [f["name"] for f in st.session_state.uploaded_files]:
                try:
                    # Sauvegarder temporairement
                    temp_path = self.save_uploaded_file(uploaded_file)
                    
                    # Upload vers Gemini
                    file_info = st.session_state.gemini_client.upload_file(temp_path)
                    
                    # Ajouter à la liste Streamlit
                    st.session_state.uploaded_files.append({
                        "name": uploaded_file.name,
                        "size": uploaded_file.size,
                        "path": str(temp_path),
                        "gemini_info": file_info
                    })
                    
                    files_processed += 1
                    
                except DuplicateFileError:
                    st.toast(f"⚠️ {uploaded_file.name} déjà uploadé", icon="⚠️")
                except Exception as e:
                    st.toast(f"❌ Erreur upload {uploaded_file.name}: {e}", icon="❌")
        
        if files_processed > 0:
            st.toast(f"✅ {files_processed} fichier(s) uploadé(s)", icon="✅")
    
    def _extract_domain(self, url: str) -> str:
        """Extrait le domaine d'une URL"""
        try:
            from urllib.parse import urlparse
            if url.startswith('http'):
                return urlparse(url).netloc
            return ""
        except:
            return ""
    
    async def stream_perplexity_for_streamlit(self, query: str, response_placeholder, current_response: str):
        """Version spéciale du streaming Perplexity pour Streamlit"""
        import json
        import httpx
        
        headers = {
            "Authorization": f"Bearer {self.config.perplexity_api_key}",
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
        input_tokens = 0
        output_tokens = 0
        last_chunk = None
        
        streaming_response = current_response + "📄 **Réponse Perplexity :**\n\n"
        
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream('POST', "https://api.perplexity.ai/chat/completions", 
                                       json=payload, headers=headers, timeout=90) as response:
                    async for line in response.aiter_lines():
                        if line.startswith('data: '):
                            data = line[6:]
                            if data != '[DONE]' and data.strip():
                                try:
                                    chunk = json.loads(data)
                                    last_chunk = chunk
                                    
                                    # Contenu du message - streaming en temps réel
                                    if chunk and 'choices' in chunk and len(chunk['choices']) > 0:
                                        delta = chunk['choices'][0].get('delta', {})
                                        if 'content' in delta:
                                            message = delta['content']
                                            full_message += message
                                            # Mettre à jour Streamlit en temps réel
                                            streaming_response_with_new_content = streaming_response + full_message + "▌"
                                            response_placeholder.markdown(streaming_response_with_new_content)
                                    
                                    # Citations
                                    if 'citations' in chunk and chunk['citations']:
                                        from src.models.citation import Citation
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
            
            # Finaliser l'affichage
            final_response = streaming_response + full_message
            response_placeholder.markdown(final_response)
            
            # Extraire les informations de coût
            if last_chunk and 'usage' in last_chunk:
                usage = last_chunk['usage']
                input_tokens = usage.get('prompt_tokens', 0)
                output_tokens = usage.get('completion_tokens', 0)
            
            # Calculer le coût total
            input_price = input_tokens * self.config.perplexity_input_price_per_token
            output_price = output_tokens * self.config.perplexity_output_price_per_token
            total_cost = self.config.perplexity_base_search_price + input_price + output_price
            
            # Créer le résultat
            from src.models.citation import SearchResult
            return SearchResult(
                content=full_message,
                citations=citations,
                query=query,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                total_cost=total_cost
            ), final_response
            
        except Exception as e:
            error_msg = f"❌ Erreur lors de la recherche: {e}"
            response_placeholder.markdown(streaming_response + error_msg)
            from src.models.citation import SearchResult
            return SearchResult(
                content=error_msg,
                citations=[],
                query=query,
                total_cost=0.0
            ), streaming_response + error_msg
    
    def process_gemini_response_stream(self, message: str, response_placeholder):
        """Traite la réponse de Gemini en streaming temps réel"""
        start_time = time.time()
        full_response = ""
        gemini_cost = 0.0
        perplexity_cost = 0.0
        
        try:
            for chunk in st.session_state.gemini_client.send_message_stream(message):
                
                # Extraire le coût Gemini
                if chunk.startswith("GEMINI_TOTAL_PRICE :"):
                    try:
                        gemini_cost = float(chunk.split(":")[1].strip().replace("$", ""))
                    except:
                        pass
                
                # Gérer les function calls
                elif chunk.startswith("FUNCTION_CALL:"):
                    parts = chunk.split(":", 2)
                    if len(parts) == 3:
                        tool_name = parts[1]
                        query = parts[2]
                        
                        if tool_name == "perplexity_direct_search":
                            # RECHERCHE DIRECTE avec streaming Perplexity
                            if st.session_state.perplexity_client:
                                # Afficher la requête de recherche
                                full_response += f"\n\n🔍 **Recherche directe sur internet**\n"
                                full_response += f"**Requête :** {query}\n\n"
                                response_placeholder.markdown(full_response + "⏳ Connexion à Perplexity...")
                                
                                # Streaming Perplexity en temps réel
                                async def run_streaming_search():
                                    search_result, updated_response = await self.stream_perplexity_for_streamlit(
                                        query, response_placeholder, full_response
                                    )
                                    return search_result, updated_response
                                
                                # Exécuter le streaming
                                try:
                                    loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(loop)
                                    search_result, full_response = loop.run_until_complete(run_streaming_search())
                                except Exception as e:
                                    try:
                                        loop = asyncio.get_event_loop()
                                        search_result, full_response = loop.run_until_complete(run_streaming_search())
                                    except:
                                        # Fallback si asyncio pose problème
                                        search_result = st.session_state.perplexity_client.search(query)
                                        full_response += f"📄 **Réponse Perplexity :**\n\n{search_result.content}"
                                        response_placeholder.markdown(full_response)
                                
                                # Ajouter aux citations et coûts
                                st.session_state.citation_manager.add_search_result(search_result)
                                st.session_state.citations = search_result.citations
                                perplexity_cost += search_result.total_cost
                                
                                # RÉAJOUT DIRECT AU CONTEXTE GEMINI (sans synthèse)
                                context_message = (
                                    f"[CONTEXTE AUTOMATIQUE] Recherche effectuée: {query}\n\n"
                                    f"Réponse complète fournie à l'utilisateur:\n{search_result.content}\n\n"
                                    f"Sources: {[c.url for c in search_result.citations]}\n\n"
                                    f"[Cette information est maintenant dans ton contexte pour les prochaines questions]"
                                )
                                # Ajout silencieux au contexte
                                st.session_state.gemini_client.send_message(context_message)
                        
                        elif tool_name == "perplexity_help_search":
                            # RECHERCHE D'AIDE avec streaming
                            if st.session_state.perplexity_client:
                                # Afficher la requête de recherche d'aide
                                full_response += f"\n\n🔍 **Recherche d'informations complémentaires**\n"
                                full_response += f"**Requête :** {query}\n\n"
                                response_placeholder.markdown(full_response + "⏳ Recherche en cours...")
                                
                                # Streaming pour la recherche d'aide
                                async def run_help_search():
                                    search_result, updated_response = await self.stream_perplexity_for_streamlit(
                                        query, response_placeholder, full_response
                                    )
                                    return search_result
                                
                                # Exécuter le streaming
                                try:
                                    loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(loop)
                                    search_result = loop.run_until_complete(run_help_search())
                                except Exception as e:
                                    try:
                                        loop = asyncio.get_event_loop()
                                        search_result = loop.run_until_complete(run_help_search())
                                    except:
                                        # Fallback
                                        search_result = st.session_state.perplexity_client.search(query)
                                
                                perplexity_cost += search_result.total_cost
                                st.session_state.citation_manager.add_search_result(search_result)
                                
                                # Ajouter au contexte Gemini
                                context_message = (
                                    f"[INFORMATIONS COMPLÉMENTAIRES] Recherche: {query}\n\n"
                                    f"Résultats trouvés:\n{search_result.content}\n\n"
                                    f"Sources: {[c.url for c in search_result.citations]}\n\n"
                                    f"[Utilise ces informations pour enrichir ta réponse initiale]"
                                )
                                st.session_state.gemini_client.send_message(context_message)
                                
                                # Afficher un message de transition
                                full_response += "\n\n🤖 **Gemini reprend la main pour synthétiser...**\n\n"
                                response_placeholder.markdown(full_response)
                                
                                # Demander une synthèse et streamer normalement
                                synthesis_prompt = "Maintenant, réponds à la question initiale en utilisant les informations complémentaires."
                                for synthesis_chunk in st.session_state.gemini_client.send_message_stream(synthesis_prompt):
                                    if synthesis_chunk.startswith("GEMINI_TOTAL_PRICE :"):
                                        try:
                                            synthesis_cost = float(synthesis_chunk.split(":")[1].strip().replace("$", ""))
                                            gemini_cost += synthesis_cost
                                        except:
                                            pass
                                    elif not synthesis_chunk.startswith(("GEMINI_", "FUNCTION_CALL:")):
                                        full_response += synthesis_chunk
                                        response_placeholder.markdown(full_response + "▌")
                                
                                # Nettoyer l'indicateur de frappe
                                response_placeholder.markdown(full_response)
                                
                                # Mettre à jour les citations
                                st.session_state.citations = search_result.citations
                
                # Contenu normal - streaming fluide (filtrer toutes les métadonnées et tokens)
                elif not any(chunk.strip().startswith(prefix) for prefix in ["GEMINI_", "FUNCTION_CALL:", "PERPLEXITY_"]) and chunk.strip():
                    full_response += chunk
                    response_placeholder.markdown(full_response + "▌")
            
            # Nettoyer l'indicateur final
            response_placeholder.markdown(full_response)
            
            # Calculer le temps de réponse
            end_time = time.time()
            response_time = end_time - start_time
            
            return full_response, gemini_cost, perplexity_cost, response_time
            
        except Exception as e:
            error_msg = f"❌ Erreur lors de la génération: {e}"
            response_placeholder.error(error_msg)
            end_time = time.time()
            response_time = end_time - start_time
            return error_msg, 0.0, 0.0, response_time
    
    def render_chat_tab(self):
        """Rendu de l'onglet conversation"""
        st.header("💬 Conversation")
        
        # Container pour les messages avec hauteur fixe
        messages_container = st.container(height=400)
        
        with messages_container:
            # Afficher les messages existants
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
                    
                    # Afficher les métriques si disponibles
                    if "cost" in message and "response_time" in message:
                        col1, col2 = st.columns(2)
                        with col1:
                            st.caption(f"💰 Coût: {message['cost']:.6f}$")
                        with col2:
                            st.caption(f"⏱️ Temps: {message['response_time']:.1f}s")
        
        # CSS pour l'input fixe
        st.markdown(
            """
            <style>
            .stChatInput {
                position: fixed !important;
                bottom: 10% !important;
                left: 50% !important;
                transform: translateX(-50%) !important;
                width: 80% !important;
                max-width: 800px !important;
                z-index: 999 !important;
                background: white !important;
                padding: 10px !important;
                border: 2px solid #e0e0e0 !important;
                border-radius: 10px !important;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1) !important;
            }
            .stChatInput > div > div > div > div {
                border: 1px solid #ccc !important;
                border-radius: 8px !important;
            }
            </style>
            """,
            unsafe_allow_html=True
        )
        
        # Input chat avec support de fichiers PDF
        user_input = st.chat_input(
            "Posez votre question (vous pouvez aussi joindre des fichiers PDF) :",
            accept_file="multiple", 
            file_type="pdf"
        )
        
        if user_input:
            # Traiter les fichiers uploadés s'il y en a
            if hasattr(user_input, 'files') and user_input.files:
                self.handle_file_uploads(user_input.files)
            
            # Récupérer le texte du message
            message_text = user_input.text if hasattr(user_input, 'text') else user_input
            
            # Ajouter le message utilisateur
            st.session_state.messages.append({"role": "user", "content": message_text})
            
            # Afficher le message utilisateur immédiatement
            with messages_container:
                with st.chat_message("user"):
                    st.markdown(message_text)
                    
                    # Afficher les fichiers PDF si uploadés
                    if hasattr(user_input, 'files') and user_input.files:
                        st.markdown("**Fichiers PDF uploadés :**")
                        for file in user_input.files:
                            st.markdown(f"- 📄 {file.name}")
            
            # Créer un placeholder pour la réponse streaming
            with messages_container:
                with st.chat_message("assistant"):
                    response_placeholder = st.empty()
                    
                    # Démarrer le streaming
                    response, gemini_cost, perplexity_cost, response_time = self.process_gemini_response_stream(
                        message_text, response_placeholder
                    )
                    total_interaction_cost = gemini_cost + perplexity_cost
                    
                    # Afficher les métriques finales
                    if total_interaction_cost > 0 or response_time > 0:
                        cost_info = f"\n\n---\n"
                        cost_info += f"💰 **Coût total: {total_interaction_cost:.6f}$** | "
                        cost_info += f"⏱️ **Temps: {response_time:.1f}s**"
                        
                        if gemini_cost > 0:
                            cost_info += f"\n- Gemini: {gemini_cost:.6f}$"
                        if perplexity_cost > 0:
                            cost_info += f"\n- Perplexity: {perplexity_cost:.6f}$"
                        
                        final_response = response + cost_info
                        response_placeholder.markdown(final_response)
                    
                    # Ajouter à l'historique
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": response,
                        "cost": total_interaction_cost,
                        "response_time": response_time
                    })
                    
                    # Mettre à jour les totaux de session
                    st.session_state.total_cost += total_interaction_cost
                    st.session_state.total_response_time += response_time
            
            # Rerun pour afficher les nouveaux messages
            st.rerun()
    
    def render_sources_tab(self):
        """Rendu de l'onglet sources"""
        st.header("📚 Sources et statistiques")
        
        # Métriques de session
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("💬 Messages", len(st.session_state.messages))
        
        with col2:
            st.metric("📄 Fichiers", len(st.session_state.uploaded_files))
        
        with col3:
            st.metric("💰 Coût total", f"{st.session_state.total_cost:.6f}$")
        
        with col4:
            st.metric("⏱️ Temps total", f"{st.session_state.total_response_time:.1f}s")
        
        # Fichiers uploadés
        if st.session_state.uploaded_files:
            st.subheader("📁 Fichiers uploadés")
            
            for i, file_info in enumerate(st.session_state.uploaded_files):
                col1, col2 = st.columns([4, 1])
                
                with col1:
                    size_mb = file_info["size"] / (1024 * 1024)
                    st.write(f"📄 **{file_info['name']}** ({size_mb:.1f} MB)")
                
                with col2:
                    if st.button("🗑️", key=f"remove_{i}", help="Supprimer"):
                        # Supprimer de Gemini
                        gemini_files = st.session_state.gemini_client.get_files_info()
                        for j, gemini_file in enumerate(gemini_files):
                            if gemini_file["name"] == file_info["name"]:
                                st.session_state.gemini_client.remove_file(j)
                                break
                        
                        # Supprimer de la liste Streamlit
                        st.session_state.uploaded_files.pop(i)
                        st.rerun()
            
            # Bouton pour tout effacer
            if st.button("🗑️ Effacer tous les fichiers"):
                st.session_state.gemini_client.clear_files()
                st.session_state.uploaded_files = []
                st.rerun()
        
        # Citations récentes
        if st.session_state.citations:
            st.subheader("🔗 Citations de la dernière recherche")
            
            for citation in st.session_state.citations:
                with st.expander(f"[{citation.number}] {citation.source or 'Source inconnue'}"):
                    st.write(f"**URL :** {citation.url}")
                    if citation.snippet:
                        st.write(f"**Extrait :** {citation.snippet}")
                    
                    # Bouton pour ouvrir la source
                    if citation.url:
                        st.link_button("🔗 Ouvrir la source", citation.url)
        
        # Historique des recherches
        if st.session_state.citation_manager:
            search_results = st.session_state.citation_manager.get_all_search_results()
            
            if search_results:
                st.subheader("📊 Historique des recherches Perplexity")
                
                total_perplexity_cost = sum(result.total_cost for result in search_results)
                st.metric("💰 Coût total Perplexity", f"{total_perplexity_cost:.6f}$")
                
                for i, result in enumerate(search_results, 1):
                    with st.expander(f"🔍 Recherche {i}: {result.query[:50]}..."):
                        st.write(f"**Requête complète :** {result.query}")
                        st.write(f"**Horodatage :** {result.timestamp.strftime('%H:%M:%S')}")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric("💰 Coût", f"{result.total_cost:.6f}$")
                        with col2:
                            st.metric("📊 Tokens", f"{result.total_tokens}")
                        
                        if result.citations:
                            st.write("**Sources utilisées :**")
                            for citation in result.citations:
                                st.write(f"- [{citation.number}] {citation.url}")
        
        # Boutons de gestion
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🗑️ Effacer la conversation"):
                st.session_state.messages = []
                st.session_state.total_cost = 0.0
                st.session_state.total_response_time = 0.0
                st.rerun()
        
        with col2:
            if st.button("🗑️ Effacer l'historique des sources"):
                if st.session_state.citation_manager:
                    st.session_state.citation_manager.clear()
                st.session_state.citations = []
                st.rerun()
    
    def run(self):
        """Lance l'application Streamlit"""
        # Configuration de la page
        st.set_page_config(
            page_title="Gemini Chat avec Perplexity",
            page_icon="🤖",
            layout="wide",
            initial_sidebar_state="collapsed"
        )
        
        # Titre principal
        st.title("🤖 Gemini Chat avec PDF et Perplexity")
        
        # Vérifier la configuration
        errors = self.config.validate()
        if any("GEMINI_API_KEY" in error for error in errors):
            st.error("❌ GEMINI_API_KEY manquante. Vérifiez votre fichier .env")
            st.stop()
        
        if not self.config.has_perplexity:
            st.warning("⚠️ Recherche Perplexity désactivée (PERPLEXITY_API_KEY manquante)")
        
        # Informations de configuration
        with st.expander("ℹ️ Configuration"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.info(f"**Modèle Gemini :** {self.config.gemini_model}")
                st.success("🤖 Gemini activé")
                
            with col2:
                if self.config.has_perplexity:
                    st.info(f"**Modèle Perplexity :** {self.config.perplexity_model}")
                    st.success("🔍 Perplexity activé")
                else:
                    st.warning("🔍 Perplexity désactivé")
        
        # Onglets principaux
        chat_tab, sources_tab = st.tabs(["💬 Chat", "📚 Sources"])
        
        with chat_tab:
            self.render_chat_tab()
        
        with sources_tab:
            self.render_sources_tab()


def main():
    """Point d'entrée principal"""
    try:
        app = StreamlitGeminiChat()
        app.run()
    except Exception as e:
        st.error(f"❌ Erreur fatale: {e}")
        st.exception(e)


if __name__ == "__main__":
    main()