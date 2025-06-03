import streamlit as st
import time
from dotenv import load_dotenv
import os
import base64
import tempfile
import re
from datetime import datetime

# Import Gemini
from google import genai

# Configuration de la page Streamlit
st.set_page_config(
    page_title="Assistant Juridique IA - Gemini 2.0 Flash",
    page_icon="⚖️",
    layout="wide"
)

# Chargement des variables d'environnement
load_dotenv()

# ==================== FONCTIONS UTILITAIRES ====================

def encode_pdf_to_base64(uploaded_files):
    """Encode un ou plusieurs fichiers PDF téléchargés en base64."""
    if uploaded_files is not None and len(uploaded_files) > 0:
        base64_pdf = ""
        for file in uploaded_files:
            pdf_bytes = file.getvalue()
            base64_pdf += base64.b64encode(pdf_bytes).decode('utf-8')
        return base64_pdf
    return None

def process_gemini_query(prompt, message_history, gemini_key, max_tokens, temperature, pdf_data=None):
    """Traite une requête avec Google Gemini 2.0 Flash et web search."""
    try:
        # Configuration de Gemini
        client = genai.Client(api_key=gemini_key)
        
        start_time = time.time()
        
        # Préparer le contexte système pour le droit français
        system_context = """Tu es un assistant IA français spécialisé dans le droit français. 
        Tu réponds toujours en français et de manière précise.
        Pour les questions juridiques, effectue une recherche web pour trouver les informations les plus récentes.
        Privilégie les sources officielles françaises comme legifrance.gouv.fr, service-public.fr, etc.
        Cite tes sources de manière claire avec les URLs.
        Pour toute question relative à la date, la date d'aujourd'hui est le """ + time.strftime("%d/%m/%Y") + "."
        
        # Préparer l'historique de conversation
        conversation_context = ""
        for msg in message_history[-6:]:  # Limiter aux 6 derniers messages
            if msg["role"] == "user":
                content = msg["content"]
                if isinstance(content, list):
                    content = next((item.get("text", "") for item in content 
                                   if isinstance(item, dict) and item.get("type") == "text"), "")
                conversation_context += f"User: {content[:200]}{'...' if len(content) > 200 else ''}\n"
            elif msg["role"] == "assistant":
                content = msg["content"]
                if isinstance(content, str) and content:
                    # Tronquer les réponses longues
                    truncated_content = content[:300] + "..." if len(content) > 300 else content
                    conversation_context += f"Assistant: {truncated_content}\n"
        
        # Construire le prompt complet
        full_prompt = f"{system_context}\n\n"
        if conversation_context:
            full_prompt += f"Contexte de conversation récent:\n{conversation_context}\n"
        full_prompt += f"Nouvelle question: {prompt}"
        
        # Préparer les contenus pour la requête
        contents = [full_prompt]
        
        # Gérer le PDF si présent
        if pdf_data:
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
                    pdf_bytes = base64.b64decode(pdf_data)
                    temp_file.write(pdf_bytes)
                    temp_path = temp_file.name
                
                contents.append(f"[Document PDF joint - taille: {len(pdf_bytes)} bytes]")
                os.unlink(temp_path)
                
            except Exception as e:
                print(f"Erreur traitement PDF: {e}")
        
        # Envoyer la requête avec web search
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=contents
        )
        
        response_time = round(time.time() - start_time, 2)
        
        # Extraire le contenu
        content = response.text if hasattr(response, 'text') and response.text else "Pas de réponse générée."
        
        # Estimer les recherches web
        web_searches = 1 if any(url_indicator in content.lower() 
                               for url_indicator in ['http', 'www.', '.fr', '.com', 'source']) else 0
        
        # Estimation des tokens
        input_tokens = len(full_prompt) // 4
        output_tokens = len(content) // 4
        
        # Calculer les coûts pour Gemini 2.0 Flash
        input_cost = (input_tokens / 1000000) * 0.1   # $0.1 per 1M input tokens
        output_cost = (output_tokens / 1000000) * 0.4  # $0.4 per 1M output tokens
        search_cost = web_searches * 0.005  # Estimation web search
        
        # Coût PDF
        pdf_cost = 0
        if pdf_data:
            pdf_size_mb = len(pdf_data) / (1024 * 1024)
            pdf_cost = pdf_size_mb * 0.01
        
        total_cost = input_cost + output_cost + search_cost + pdf_cost
        
        # Extraire les sources/URLs du contenu
        sources = []
        urls = re.findall(r'https?://[^\s\)\]]+', content)
        for i, url in enumerate(urls[:5]):  # Limiter à 5 sources
            sources.append({
                "title": f"Source {i+1}",
                "url": url.rstrip('.,)'),
                "text": ""
            })
        
        # Chercher des mentions de sources dans le texte
        source_patterns = [
            r'(?:selon|d\'après|source\s*:\s*)([^.]+)',
            r'(?:legifrance|service-public|conseil-etat|conseil-constitutionnel)',
            r'(?:article\s+\d+|code\s+\w+)'
        ]
        
        for pattern in source_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches[:3]:
                if isinstance(match, str) and len(match) > 10:
                    sources.append({
                        "title": f"Référence juridique",
                        "url": "",
                        "text": match.strip()[:200]
                    })
        
        stats = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "web_searches": web_searches,
            "response_time": response_time,
            "model": "Google Gemini 2.0 Flash",
            "sources": sources,
            "entry_cost": input_cost,
            "output_cost": output_cost,
            "search_cost": search_cost,
            "total_cost": total_cost
        }
        
        return content, stats, None
        
    except Exception as e:
        error_msg = f"Erreur avec Gemini: {str(e)}"
        return None, None, error_msg

# ==================== INITIALISATION ====================

if 'messages' not in st.session_state:
    st.session_state.messages = []

# CSS personnalisé
st.markdown("""
<style>
:root {
    --bg-primary: #ffffff;
    --bg-secondary: #f8f9fa;
    --text-primary: #333333;
    --border-color: #e0e0e0;
    --accent-color: #4285f4;
}

@media (prefers-color-scheme: dark) {
    :root {
        --bg-primary: #1e1e1e;
        --bg-secondary: #2d2d2d;
        --text-primary: #ffffff;
        --border-color: #404040;
        --accent-color: #66b3ff;
    }
}

.gemini-panel {
    padding: 20px;
    border-radius: 12px;
    margin: 15px 0;
    background: linear-gradient(135deg, rgba(66, 133, 244, 0.1), rgba(66, 133, 244, 0.05));
    border-left: 4px solid var(--accent-color);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.stats-container {
    background-color: var(--bg-secondary);
    padding: 15px;
    border-radius: 8px;
    margin: 10px 0;
    border: 1px solid var(--border-color);
}

.sources-container {
    background: linear-gradient(135deg, rgba(52, 168, 83, 0.1), rgba(52, 168, 83, 0.05));
    padding: 15px;
    border-radius: 8px;
    margin: 15px 0;
    border-left: 3px solid #34a853;
    border: 1px solid var(--border-color);
    max-height: 400px;
    overflow-y: auto;
}

.source-item {
    background-color: var(--bg-primary);
    margin: 10px 0;
    padding: 12px;
    border-radius: 6px;
    border: 1px solid var(--border-color);
}

.source-item a {
    color: var(--accent-color);
    text-decoration: none;
    font-weight: 500;
}

.source-item a:hover {
    text-decoration: underline;
}

.header-container {
    text-align: center;
    padding: 20px;
    background: linear-gradient(135deg, var(--accent-color), #34a853);
    border-radius: 12px;
    margin-bottom: 30px;
    color: white;
}

.upload-zone {
    background-color: var(--bg-secondary);
    padding: 20px;
    border-radius: 8px;
    border: 2px dashed var(--border-color);
    text-align: center;
    margin: 15px 0;
}
</style>
""", unsafe_allow_html=True)

# ==================== INTERFACE PRINCIPALE ====================

# Header
st.markdown("""
<div class="header-container">
    <h1>🤖 Assistant Juridique IA</h1>
    <p>Powered by Google Gemini 2.0 Flash avec recherche web intégrée</p>
</div>
""", unsafe_allow_html=True)

# Sidebar Configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Vérification de la clé API
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_key:
        st.success("✅ Clé Gemini chargée")
    else:
        st.error("❌ Clé GEMINI_API_KEY manquante")
        gemini_key = st.text_input("Clé API Gemini:", type="password")
    
    st.subheader("🎛️ Paramètres")
    temperature = st.slider("Temperature", 0.0, 1.0, 0.3, 0.1)
    max_tokens = st.slider("Tokens max", 500, 4000, 3500, 100)
    
    st.subheader("📊 Statistiques de session")
    if st.session_state.messages:
        user_messages = [m for m in st.session_state.messages if m["role"] == "user"]
        assistant_messages = [m for m in st.session_state.messages if m["role"] == "assistant"]
        
        st.metric("Questions posées", len(user_messages))
        st.metric("Réponses générées", len(assistant_messages))
        
        # Calcul du coût total
        total_cost = 0
        total_time = 0
        for msg in assistant_messages:
            if msg.get("stats"):
                total_cost += msg["stats"].get("total_cost", 0)
                total_time += msg["stats"].get("response_time", 0)
        
        st.metric("Coût total", f"${total_cost:.4f}")
        st.metric("Temps total", f"{total_time:.1f}s")
    
    st.subheader("🧹 Actions")
    if st.button("Vider l'historique"):
        st.session_state.messages = []
        st.rerun()
    
    # Informations sur Gemini
    st.subheader("ℹ️ À propos")
    st.info("""
    **Gemini 2.0 Flash** dispose de :
    - 🌐 Recherche web native
    - 📄 Support PDF complet  
    - 🇫🇷 Expertise droit français
    - 💰 Coûts optimisés
    - ⚡ Réponses rapides
    """)

# Zone d'upload
st.subheader("📎 Upload de documents (optionnel)")
uploaded_files = st.file_uploader(
    "Glissez-déposez vos fichiers PDF ici",
    type=["pdf"],
    accept_multiple_files=True,
    help="Téléchargez des documents PDF pour enrichir l'analyse"
)

pdf_data = None
if uploaded_files:
    pdf_data = encode_pdf_to_base64(uploaded_files)
    st.success(f"✅ {len(uploaded_files)} fichier(s) PDF chargé(s)")
    
    # Affichage des fichiers
    with st.expander("📋 Fichiers chargés", expanded=False):
        for file in uploaded_files:
            st.write(f"📄 **{file.name}** - {file.size / 1024:.1f} KB")

# Affichage de l'historique des messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
            st.markdown('<div class="gemini-panel">', unsafe_allow_html=True)
        
        # Affichage du contenu
        if isinstance(message["content"], list):
            text_content = next((item.get("text", "") for item in message["content"] 
                               if isinstance(item, dict) and item.get("type") == "text"), "")
            st.markdown(text_content)
            if any(item.get("type") == "document" for item in message["content"] if isinstance(item, dict)):
                st.info("📎 Document PDF analysé")
        else:
            st.markdown(message["content"])
        
        # Affichage des statistiques
        if message.get("stats"):
            stats = message["stats"]
            st.markdown(f"""
            <div class="stats-container">
                <strong>📊 Statistiques:</strong><br>
                🤖 {stats['model']} | ⏱️ {stats['response_time']}s | 
                🔤 Tokens: {stats['input_tokens']}→{stats['output_tokens']} | 
                🔍 {stats['web_searches']} recherche(s) | 💲 ${stats['total_cost']:.4f}
            </div>
            """, unsafe_allow_html=True)
            
            # Affichage des sources
            if stats.get('sources'):
                st.markdown('<div class="sources-container">', unsafe_allow_html=True)
                st.markdown("### 📚 Sources consultées:")
                
                for i, source in enumerate(stats['sources']):
                    title = source.get('title', 'Source inconnue')
                    url = source.get('url', '')
                    text = source.get('text', '')
                    
                    source_html = f'<div class="source-item">'
                    source_html += f'<strong>{title}</strong><br>'
                    
                    if url:
                        source_html += f'<a href="{url}" target="_blank">🔗 {url}</a><br>'
                    
                    if text:
                        source_html += f'<em>"{text}"</em>'
                    
                    source_html += '</div>'
                    st.markdown(source_html, unsafe_allow_html=True)
                
                st.markdown('</div>', unsafe_allow_html=True)
        
        if message["role"] == "assistant":
            st.markdown('</div>', unsafe_allow_html=True)

# Chat input
if prompt := st.chat_input("Posez votre question juridique..."):
    if not gemini_key:
        st.error("❌ Veuillez configurer votre clé API Gemini dans la sidebar")
        st.stop()
    
    # Créer le contenu du message
    if pdf_data:
        message_content = [
            {"type": "text", "text": prompt},
            {
                "type": "document", 
                "source": {
                    "type": "base64", 
                    "media_type": "application/pdf", 
                    "data": pdf_data
                }
            }
        ]
    else:
        message_content = prompt
    
    # Ajouter le message utilisateur
    st.session_state.messages.append({"role": "user", "content": message_content})
    
    # Afficher le message utilisateur
    with st.chat_message("user"):
        st.markdown(prompt)
        if pdf_data:
            st.info(f"📎 {len(uploaded_files)} document(s) PDF joint(s)")
    
    # Traiter la réponse
    with st.chat_message("assistant"):
        with st.spinner("🤔 Gemini réfléchit et recherche..."):
            content, stats, error = process_gemini_query(
                prompt, 
                st.session_state.messages[:-1],  # Exclure le nouveau message
                gemini_key, 
                max_tokens, 
                temperature, 
                pdf_data
            )
            
            if error:
                st.error(f"❌ {error}")
            elif content:
                st.markdown('<div class="gemini-panel">', unsafe_allow_html=True)
                st.markdown(content)
                
                if stats:
                    st.markdown(f"""
                    <div class="stats-container">
                        <strong>📊 Statistiques:</strong><br>
                        🤖 {stats['model']} | ⏱️ {stats['response_time']}s | 
                        🔤 Tokens: {stats['input_tokens']}→{stats['output_tokens']} | 
                        🔍 {stats['web_searches']} recherche(s) | 💲 ${stats['total_cost']:.4f}
                        {"| 📄 PDF analysé" if pdf_data else ""}
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Affichage des sources
                    if stats.get('sources'):
                        st.markdown('<div class="sources-container">', unsafe_allow_html=True)
                        st.markdown("### 📚 Sources consultées:")
                        
                        for i, source in enumerate(stats['sources']):
                            title = source.get('title', 'Source inconnue')
                            url = source.get('url', '')
                            text = source.get('text', '')
                            
                            source_html = f'<div class="source-item">'
                            source_html += f'<strong>{title}</strong><br>'
                            
                            if url:
                                source_html += f'<a href="{url}" target="_blank">🔗 {url}</a><br>'
                            
                            if text:
                                source_html += f'<em>"{text}"</em>'
                            
                            source_html += '</div>'
                            st.markdown(source_html, unsafe_allow_html=True)
                        
                        st.markdown('</div>', unsafe_allow_html=True)
                
                st.markdown('</div>', unsafe_allow_html=True)
                
                # Ajouter à l'historique
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": content,
                    "stats": stats
                })
            else:
                st.error("❌ Aucune réponse générée")

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; font-size: 0.9em;'>
    <p>🤖 Propulsé par Google Gemini 2.0 Flash | 🌐 Recherche web native | 📄 Support PDF complet</p>
    <p>⚖️ Spécialisé en droit français | 💬 Historique de conversation conservé</p>
</div>
""", unsafe_allow_html=True)