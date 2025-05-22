import streamlit as st
import anthropic
import httpx
import json
import asyncio
import time
from dotenv import load_dotenv
import os
import base64
import traceback

# Chargement des variables d'environnement
load_dotenv()

# Configuration de la page Streamlit
st.set_page_config(
    page_title="Assistant Juridique Français - Comparaison Multi-Modèles",
    page_icon="⚖️",
    layout="wide"
)

# Fonction pour encoder un PDF en base64
def encode_pdf_to_base64(uploaded_file):
    """Encode un fichier PDF téléchargé en base64."""
    if uploaded_file is not None:
        base64_pdf = ""
        for file in uploaded_file:
            pdf_bytes = file.getvalue()
            base64_pdf += base64.b64encode(pdf_bytes).decode('utf-8')
        return base64_pdf
    return None

# Fonction pour traiter une requête Claude
def process_claude_query(model_name, messages, system_prompt, tools, api_key, max_tokens, temperature):
    """Traite une requête avec les modèles Claude."""
    try:
        client = anthropic.Anthropic(api_key=api_key)
        
        start_time = time.time()
        
        response = client.messages.create(
            model=model_name,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=messages,
            tools=tools
        )
        
        response_time = round(time.time() - start_time, 2)
        
        # Extraire le contenu de la réponse
        content = ""
        sources = []
        
        for block in response.content:
            if block.type == "text":
                content += block.text
        
        # Extraire les citations des blocs de contenu
        for block in response.content:
            if hasattr(block, 'citations') and block.citations:
                for citation in block.citations:
                    source_info = {
                        "title": citation.title if hasattr(citation, 'title') else "Source",
                        "url": citation.url if hasattr(citation, 'url') else "",
                        "text": citation.cited_text if hasattr(citation, 'cited_text') else ""
                    }
                    sources.append(source_info)
        
        # Récupérer les statistiques d'utilisation
        usage = response.usage
        input_tokens = usage.input_tokens if usage else 0
        output_tokens = usage.output_tokens if usage else 0
        web_search_requests = usage.server_tool_use.web_search_requests if usage and usage.server_tool_use else 0
        
        # Calculer les coûts selon les vrais tarifs Anthropic
        try:
            if "haiku" in model_name.lower():
                # Claude 3.5 Haiku : $0.80 input, $4 output par million
                entry_cost = (int(input_tokens) / 1000000) * 0.8
                output_cost = (int(output_tokens) / 1000000) * 4
            else:
                # Claude 3.7 Sonnet : $3 input, $15 output par million  
                entry_cost = (int(input_tokens) / 1000000) * 3
                output_cost = (int(output_tokens) / 1000000) * 15
            
            search_cost = (int(web_search_requests) / 1000) * 10  # 10$ par 1000 recherches web
            total_cost = entry_cost + output_cost + search_cost
        except:
            entry_cost = output_cost = search_cost = total_cost = 0
        
        # Statistiques
        stats = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "web_searches": web_search_requests,
            "response_time": response_time,
            "model": model_name,
            "sources": sources,
            "entry_cost": entry_cost,
            "output_cost": output_cost,
            "search_cost": search_cost,
            "total_cost": total_cost
        }
        
        return content, stats, None
        
    except Exception as e:
        error_msg = f"Erreur avec {model_name}: {str(e)}"
        return None, None, error_msg

# Fonction pour préparer les messages Perplexity avec contexte limité
def prepare_perplexity_messages(message_history, new_user_input):
    """Prépare les messages avec contexte limité aux 4 dernières interactions"""
    messages = [
        {
            "role": "system",
            "content": "Tu es un expert juridique français spécialisé dans le droit français. Tu réponds toujours en français et de manière précise."
        }
    ]
    
    # Limiter aux 4 dernières interactions (= 8 derniers messages maximum)
    recent_history = message_history[-8:] if len(message_history) > 8 else message_history
    
    # Ajouter l'historique récent
    for msg in recent_history:
        if msg["role"] in ["user", "assistant"]:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
    
    # Ajouter la nouvelle question
    messages.append({
        "role": "user",
        "content": new_user_input
    })
    
    return messages

# Fonction pour traiter une requête Perplexity
async def process_perplexity_query(user_input, api_key, message_history=None):
    """Traite une requête avec Perplexity AI."""
    url = "https://api.perplexity.ai/chat/completions"
    
    # Préparer les messages avec contexte limité
    messages = prepare_perplexity_messages(message_history or [], user_input)
    
    payload = {
        "temperature": 0.2,
        "top_p": 0.9,
        "return_images": False,
        "return_related_questions": False,
        "top_k": 0,
        "stream": False,  # Non-streaming pour simplifier
        "presence_penalty": 0,
        "frequency_penalty": 1,
        "web_search_options": {"search_context_size": "high"},
        "model": "sonar",
        "messages": messages,
        "max_tokens": 4000,
        "search_domain_filter": [
            "www.legifrance.gouv.fr",
            "www.service-public.fr",
            "annuaire-entreprises.data.gouv.fr"
        ],
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        start_time = time.time()
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code != 200:
                return None, None, f"Erreur API Perplexity: {response.status_code}"
            
            data = response.json()
            response_time = round(time.time() - start_time, 2)
            
            # Extraire le contenu
            content = data['choices'][0]['message']['content'] if 'choices' in data else ""
            
            # Extraire les statistiques
            input_tokens = data.get('usage', {}).get('prompt_tokens', 0)
            output_tokens = data.get('usage', {}).get('completion_tokens', 0)
            citations = data.get('citations', [])
            
            # Calculer les coûts Perplexity : $1 input, $1 output par million, $12 pour 1000 recherches
            try:
                entry_cost = (int(input_tokens) / 1000000) * 1
                output_cost = (int(output_tokens) / 1000000) * 1
                search_cost = (1 / 1000) * 12  # $12 pour 1000 recherches = $0.012 par recherche
                total_cost = entry_cost + output_cost + search_cost
            except:
                entry_cost = output_cost = search_cost = total_cost = 0
            
            # Statistiques
            stats = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "web_searches": 1,  # Perplexity fait toujours une recherche
                "response_time": response_time,
                "model": "Perplexity Sonar",
                "sources": [{"title": "Source Web", "url": "", "text": c} for c in citations],
                "entry_cost": entry_cost,
                "output_cost": output_cost,
                "search_cost": search_cost,
                "total_cost": total_cost
            }
            
            return content, stats, None
            
    except Exception as e:
        return None, None, f"Erreur Perplexity: {str(e)}"

# Fonction pour traiter une requête selon le modèle
async def process_model_query(model_name, prompt, message_history, anthropic_key, perplexity_key, max_tokens, temperature, pdf_data=None):
    """Traite une requête pour n'importe quel modèle"""
    
    if model_name == "Claude 3.5 Haiku":
        system_prompt = """Tu es un assistant IA français spécialisé dans le droit français. 
        Tu réponds toujours en français et de manière précise.
        Si il s'agit d'une question juridique, fais au moins une recherche internet.
        Cite tes sources de manière claire."""
        
        tools = [{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 3,
            "allowed_domains": [
                "www.legifrance.gouv.fr",
                "service-public.fr",
                "www.conseil-constitutionnel.fr",
                "www.conseil-etat.fr"
            ]
        }]
        
        # Préparer les messages pour l'API
        api_messages = []
        for m in message_history:
            if m["role"] in ["user", "assistant"]:
                api_messages.append({"role": m["role"], "content": m["content"]})
        
        # Ajouter la nouvelle question
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
            
        api_messages.append({"role": "user", "content": message_content})
        
        return process_claude_query(
            "claude-3-5-haiku-latest",
            api_messages,
            system_prompt,
            tools,
            anthropic_key,
            max_tokens,
            temperature
        )
    
    elif model_name == "Claude 3.7 Sonnet":
        system_prompt = """Tu es un assistant IA français spécialisé dans le droit français. 
        Tu réponds toujours en français et de manière précise.
        Si il s'agit d'une question juridique, fais au moins une recherche internet.
        Cite tes sources de manière claire."""
        
        tools = [{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 3,
            "allowed_domains": [
                "www.legifrance.gouv.fr",
                "service-public.fr",
                "www.conseil-constitutionnel.fr",
                "www.conseil-etat.fr"
            ]
        }]
        
        # Préparer les messages pour l'API
        api_messages = []
        for m in message_history:
            if m["role"] in ["user", "assistant"]:
                api_messages.append({"role": m["role"], "content": m["content"]})
        
        # Ajouter la nouvelle question
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
            
        api_messages.append({"role": "user", "content": message_content})
        
        return process_claude_query(
            "claude-3-7-sonnet-20250219",
            api_messages,
            system_prompt,
            tools,
            anthropic_key,
            max_tokens,
            temperature
        )
    
    elif model_name == "Perplexity AI":
        # Préparer l'historique des messages (texte seulement)
        clean_history = []
        for m in message_history:
            if isinstance(m["content"], str):
                clean_history.append({"role": m["role"], "content": m["content"]})
        
        return await process_perplexity_query(prompt, perplexity_key, clean_history)
    
    else:
        return None, None, f"Modèle {model_name} non supporté"

# Initialisation des variables de session
if 'messages_left' not in st.session_state:
    st.session_state.messages_left = []
if 'messages_right' not in st.session_state:
    st.session_state.messages_right = []
if 'uploaded_file' not in st.session_state:
    st.session_state.uploaded_file = None

# CSS personnalisé avec support dark mode
st.markdown("""
<style>
/* Variables CSS pour les couleurs */
:root {
    --bg-primary: #ffffff;
    --bg-secondary: #f8f9fa;
    --text-primary: #333333;
    --border-color: #e0e0e0;
    --shadow-color: rgba(0, 0, 0, 0.1);
}

/* Dark mode */
[data-theme="dark"] {
    --bg-primary: #1e1e1e;
    --bg-secondary: #2d2d2d;
    --text-primary: #ffffff;
    --border-color: #404040;
    --shadow-color: rgba(255, 255, 255, 0.1);
}

/* Détection automatique du dark mode */
@media (prefers-color-scheme: dark) {
    :root {
        --bg-primary: #1e1e1e;
        --bg-secondary: #2d2d2d;
        --text-primary: #ffffff;
        --border-color: #404040;
        --shadow-color: rgba(255, 255, 255, 0.1);
    }
}

.model-panel {
    padding: 15px;
    border-radius: 8px;
    margin: 10px 0;
    background-color: var(--bg-secondary);
    color: var(--text-primary);
    box-shadow: 0 2px 4px var(--shadow-color);
}

.haiku-panel {
    border-left: 4px solid #28a745;
    background-color: rgba(40, 167, 69, 0.1);
}

.sonnet-panel {
    border-left: 4px solid #007bff;
    background-color: rgba(0, 123, 255, 0.1);
}

.perplexity-panel {
    border-left: 4px solid #ff6b35;
    background-color: rgba(255, 107, 53, 0.1);
}

.stats-box {
    background-color: var(--bg-secondary);
    color: var(--text-primary);
    padding: 10px;
    border-radius: 5px;
    margin: 5px 0;
    font-size: 0.9em;
    border: 1px solid var(--border-color);
}

.sources-box {
    background-color: var(--bg-secondary);
    color: var(--text-primary);
    padding: 10px;
    border-radius: 5px;
    margin: 15px 0;
    border-left: 3px solid #007bff;
    border: 1px solid var(--border-color);
    max-height: 300px;
    overflow-y: auto;
}

.source-item {
    margin: 8px 0;
    padding: 8px;
    background-color: var(--bg-primary);
    border-radius: 4px;
    border: 1px solid var(--border-color);
}

.error-box {
    background-color: rgba(255, 235, 235, 0.8);
    padding: 10px;
    border-radius: 5px;
    margin: 5px 0;
    color: #721c24;
    border: 1px solid #f5c6cb;
}

/* Dark mode pour les erreurs */
@media (prefers-color-scheme: dark) {
    .error-box {
        background-color: rgba(139, 0, 0, 0.3);
        color: #ffb3b3;
        border-color: #8b0000;
    }
}

/* Amélioration de la lisibilité des liens */
.source-item a {
    color: #007bff;
    text-decoration: none;
}

.source-item a:hover {
    text-decoration: underline;
}

@media (prefers-color-scheme: dark) {
    .source-item a {
        color: #66b3ff;
    }
}

/* Espacement pour éviter les chevauchements */
.response-container {
    margin-bottom: 20px;
    padding-bottom: 10px;
}

.sources-container {
    margin-top: 15px;
    clear: both;
}
</style>
""", unsafe_allow_html=True)

# Titre de l'application
st.title("Assistant Juridique Français - Comparaison Multi-Modèles 🇫🇷⚖️")
st.subheader("Comparaison côte à côte des modèles IA")

# Récupération des clés API depuis les variables d'environnement (.env)
anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
perplexity_key = os.getenv("PERPLEXITY_API_KEY", "")

# Sidebar pour la configuration
with st.sidebar:
    st.header("Configuration")
    
    # Sélection des modèles pour chaque côté
    st.subheader("🤖 Choix des modèles")
    
    col_select1, col_select2 = st.columns(2)
    with col_select1:
        model_left = st.selectbox(
            "Modèle Gauche",
            ["Claude 3.5 Haiku", "Claude 3.7 Sonnet", "Perplexity AI"],
            key="model_left"
        )
    
    with col_select2:
        model_right = st.selectbox(
            "Modèle Droit", 
            ["Claude 3.5 Haiku", "Claude 3.7 Sonnet", "Perplexity AI"],
            index=1,  # Par défaut Sonnet à droite
            key="model_right"
        )
    
    # Affichage des tarifs des modèles sélectionnés
    st.subheader("💰 Tarifs des modèles sélectionnés")
    
    def get_model_pricing(model_name):
        if model_name == "Claude 3.5 Haiku":
            return "$0.80 / $4.00 / $10 (Input/Output/1K recherches)"
        elif model_name == "Claude 3.7 Sonnet":
            return "$3.00 / $15.00 / $10 (Input/Output/1K recherches)"
        else:  # Perplexity
            return "$1.00 / $1.00 / $12 (Input/Output/1K recherches)"
    
    st.write(f"**Gauche ({model_left}):** {get_model_pricing(model_left)}")
    st.write(f"**Droit ({model_right}):** {get_model_pricing(model_right)}")
    
    # Paramètres avancés
    st.subheader("Paramètres avancés")
    temperature = st.slider("Temperature", 0.0, 1.0, 0.2, 0.1)
    max_tokens = st.slider("Tokens max", 500, 4000, 1500, 100)
    
    # Téléchargement de document (seulement si au moins un Claude)
    if model_left != "Perplexity AI" or model_right != "Perplexity AI":
        st.subheader("Document de référence")
        uploaded_file = st.file_uploader("Télécharger un PDF", type=["pdf"], accept_multiple_files=True)
        
        if uploaded_file is not None:
            st.session_state.uploaded_file = uploaded_file
            st.success(f"✅ {len(uploaded_file)} document(s) chargé(s)")
    else:
        st.session_state.uploaded_file = None
        st.info("📄 Perplexity n'accepte pas les documents PDF")
    
    # Statut des clés API
    st.subheader("🔑 Statut des clés API")
    if anthropic_key:
        st.success("✅ Clé Anthropic chargée depuis .env")
    else:
        st.error("❌ Clé ANTHROPIC_API_KEY manquante dans .env")
    
    if perplexity_key:
        st.success("✅ Clé Perplexity chargée depuis .env")
    else:
        st.error("❌ Clé PERPLEXITY_API_KEY manquante dans .env")
    
    # Debug
    debug_mode = st.checkbox("Mode debug", value=False)
    
    # Bouton reset
    if st.button("🗑️ Vider l'historique"):
        st.session_state.messages_left = []
        st.session_state.messages_right = []
        st.rerun()

# Vérification des clés API nécessaires
keys_needed = set()
if model_left.startswith("Claude") or model_right.startswith("Claude"):
    keys_needed.add("anthropic")
if model_left == "Perplexity AI" or model_right == "Perplexity AI":
    keys_needed.add("perplexity")

missing_keys = []
if "anthropic" in keys_needed and not anthropic_key:
    missing_keys.append("Anthropic")
if "perplexity" in keys_needed and not perplexity_key:
    missing_keys.append("Perplexity")

if missing_keys:
    st.error(f"❌ Clés API manquantes dans le fichier .env: {', '.join(missing_keys)}")
    st.info("💡 Ajoutez vos clés dans le fichier .env :")
    st.code("""
# Fichier .env
ANTHROPIC_API_KEY=votre_clé_anthropic
PERPLEXITY_API_KEY=votre_clé_perplexity
""")
    st.stop()

# Fonction pour afficher les messages avec style
def display_messages(messages, model_name):
    for message in messages:
        with st.chat_message(message["role"]):
            # Style selon le modèle utilisé
            if "haiku" in model_name.lower():
                panel_class = "haiku-panel"
            elif "sonnet" in model_name.lower():
                panel_class = "sonnet-panel"
            elif "perplexity" in model_name.lower():
                panel_class = "perplexity-panel"
            else:
                panel_class = "model-panel"
            
            st.markdown(f'<div class="model-panel {panel_class}">', unsafe_allow_html=True)
            
            if isinstance(message["content"], list):
                # Message avec document
                text_content = next((item.get("text", "") for item in message["content"] 
                                   if isinstance(item, dict) and item.get("type") == "text"), "")
                st.markdown(f'<div class="response-container">{text_content}</div>', unsafe_allow_html=True)
                if any(item.get("type") == "document" for item in message["content"] if isinstance(item, dict)):
                    st.info("📎 Document PDF joint")
            else:
                st.markdown(f'<div class="response-container">{message["content"]}</div>', unsafe_allow_html=True)
            
            # Afficher les statistiques si disponibles
            if message.get("stats"):
                stats = message["stats"]
                st.markdown(f"""
                <div class="stats-box">
                🤖 {stats.get('model', 'Modèle')} | 
                ⏱️ {stats.get('response_time', 0)}s | 
                🔤 In: {stats.get('input_tokens', 0)} | 
                🔤 Out: {stats.get('output_tokens', 0)} | 
                🔍 Recherches: {stats.get('web_searches', 0)} | 
                💲 Coût: {stats.get('total_cost', 0):.6f}$
                </div>
                """, unsafe_allow_html=True)
                
                # Afficher les sources dans un conteneur séparé
                if stats.get('sources'):
                    st.markdown('<div class="sources-container">', unsafe_allow_html=True)
                    sources_html = '<div class="sources-box"><h4>📚 Sources consultées:</h4>'
                    for i, source in enumerate(stats['sources']):
                        title = source.get('title', 'Source inconnue')
                        url = source.get('url', '')
                        sources_html += f'<div class="source-item">'
                        sources_html += f'<strong>Source {i+1}:</strong> {title}<br>'
                        if url:
                            sources_html += f'<a href="{url}" target="_blank">🔗 {url}</a><br>'
                        if source.get('text'):
                            excerpt = source['text'][:150] + "..." if len(source['text']) > 150 else source['text']
                            sources_html += f'<em>Extrait: "{excerpt}"</em>'
                        sources_html += '</div>'
                    sources_html += '</div>'
                    st.markdown(sources_html, unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)
            
            st.markdown('</div>', unsafe_allow_html=True)

# Créer deux colonnes pour la comparaison
col1, col2 = st.columns(2)

# Affichage des historiques
with col1:
    st.header(f"🔵 {model_left}")
    display_messages(st.session_state.messages_left, model_left)

with col2:
    st.header(f"🔴 {model_right}")
    display_messages(st.session_state.messages_right, model_right)

# Zone de saisie
prompt = st.chat_input("Posez votre question juridique pour comparer les modèles...")

if prompt:
    # Préparer le contenu du message avec PDF si disponible
    pdf_data = None
    if st.session_state.uploaded_file is not None:
        pdf_data = encode_pdf_to_base64(st.session_state.uploaded_file)
    
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
    
    # Ajouter la question aux deux historiques
    st.session_state.messages_left.append({
        "role": "user", 
        "content": message_content,
        "model": model_left
    })
    st.session_state.messages_right.append({
        "role": "user", 
        "content": message_content,
        "model": model_right
    })
    
    # Afficher la question utilisateur dans les deux colonnes
    with col1:
        with st.chat_message("user"):
            st.markdown(prompt)
            if pdf_data and model_left != "Perplexity AI":
                st.info("📎 Document PDF joint")
            elif pdf_data and model_left == "Perplexity AI":
                st.warning("⚠️ PDF ignoré (Perplexity ne le supporte pas)")
    
    with col2:
        with st.chat_message("user"):
            st.markdown(prompt)
            if pdf_data and model_right != "Perplexity AI":
                st.info("📎 Document PDF joint")
            elif pdf_data and model_right == "Perplexity AI":
                st.warning("⚠️ PDF ignoré (Perplexity ne le supporte pas)")
    
    # Traitement parallèle des deux modèles
    async def process_both_models():
        # Traitement pour le modèle de gauche
        with col1:
            with st.chat_message("assistant"):
                with st.spinner(f"🤔 {model_left} réfléchit..."):
                    if debug_mode:
                        st.write(f"🔍 Debug: Envoi de la requête à {model_left}...")
                    
                    # PDF seulement si pas Perplexity
                    pdf_for_left = pdf_data if model_left != "Perplexity AI" else None
                    
                    content_left, stats_left, error_left = await process_model_query(
                        model_left, 
                        prompt, 
                        st.session_state.messages_left[:-1],  # Exclure la nouvelle question
                        anthropic_key, 
                        perplexity_key, 
                        max_tokens, 
                        temperature,
                        pdf_for_left
                    )
                    
                    if error_left:
                        st.markdown(f'<div class="error-box">❌ {error_left}</div>', unsafe_allow_html=True)
                    elif content_left:
                        # Afficher la réponse dans un conteneur séparé
                        st.markdown(f'<div class="response-container">{content_left}</div>', unsafe_allow_html=True)
                        
                        # Afficher les statistiques
                        if stats_left:
                            pdf_cost = 0
                            if pdf_for_left:
                                pdf_size_mb = len(pdf_for_left) / (1024 * 1024)
                                pdf_cost = pdf_size_mb * 0.01
                            
                            total_cost = stats_left['total_cost'] + pdf_cost
                            
                            st.markdown(f"""
                            <div class="stats-box">
                            🤖 {stats_left['model']} | 
                            ⏱️ {stats_left['response_time']}s | 
                            🔤 In: {stats_left['input_tokens']} | 
                            🔤 Out: {stats_left['output_tokens']} | 
                            🔍 Recherches: {stats_left['web_searches']} | 
                            💲 Coût: {total_cost:.6f}$
                            {"| 📄 PDF traité" if pdf_for_left else ""}
                            </div>
                            """, unsafe_allow_html=True)
                            
                            # Afficher les sources dans un conteneur séparé et collapsible
                            if stats_left.get('sources'):
                                with st.expander("📚 Sources consultées", expanded=False):
                                    st.markdown('<div class="sources-container">', unsafe_allow_html=True)
                                    sources_html = '<div class="sources-box">'
                                    for i, source in enumerate(stats_left['sources']):
                                        title = source.get('title', 'Source inconnue')
                                        url = source.get('url', '')
                                        sources_html += f'<div class="source-item">'
                                        sources_html += f'<strong>Source {i+1}:</strong> {title}<br>'
                                        if url:
                                            sources_html += f'<a href="{url}" target="_blank">🔗 {url}</a><br>'
                                        if source.get('text'):
                                            excerpt = source['text'][:150] + "..." if len(source['text']) > 150 else source['text']
                                            sources_html += f'<em>Extrait: "{excerpt}"</em>'
                                        sources_html += '</div>'
                                    sources_html += '</div>'
                                    st.markdown(sources_html, unsafe_allow_html=True)
                                    st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Ajouter à l'historique
                        st.session_state.messages_left.append({
                            "role": "assistant", 
                            "content": content_left,
                            "model": model_left,
                            "stats": stats_left
                        })
                    else:
                        st.error(f"❌ Aucune réponse reçue de {model_left}")
        
        # Traitement pour le modèle de droite
        with col2:
            with st.chat_message("assistant"):
                with st.spinner(f"🤔 {model_right} réfléchit..."):
                    if debug_mode:
                        st.write(f"🔍 Debug: Envoi de la requête à {model_right}...")
                    
                    # PDF seulement si pas Perplexity
                    pdf_for_right = pdf_data if model_right != "Perplexity AI" else None
                    
                    content_right, stats_right, error_right = await process_model_query(
                        model_right, 
                        prompt, 
                        st.session_state.messages_right[:-1],  # Exclure la nouvelle question
                        anthropic_key, 
                        perplexity_key, 
                        max_tokens, 
                        temperature,
                        pdf_for_right
                    )
                    
                    if error_right:
                        st.markdown(f'<div class="error-box">❌ {error_right}</div>', unsafe_allow_html=True)
                    elif content_right:
                        st.markdown(content_right)
                        
                        # Afficher les statistiques
                        if stats_right:
                            pdf_cost = 0
                            if pdf_for_right:
                                pdf_size_mb = len(pdf_for_right) / (1024 * 1024)
                                pdf_cost = pdf_size_mb * 0.01
                            
                            total_cost = stats_right['total_cost'] + pdf_cost
                            
                            st.markdown(f"""
                            <div class="stats-box">
                            🤖 {stats_right['model']} | 
                            ⏱️ {stats_right['response_time']}s | 
                            🔤 In: {stats_right['input_tokens']} | 
                            🔤 Out: {stats_right['output_tokens']} | 
                            🔍 Recherches: {stats_right['web_searches']} | 
                            💲 Coût: {total_cost:.6f}$
                            {"| 📄 PDF traité" if pdf_for_right else ""}
                            </div>
                            """, unsafe_allow_html=True)
                            
                            # Afficher les sources
                            if stats_right.get('sources'):
                                sources_html = '<div class="sources-box"><h4>📚 Sources consultées:</h4>'
                                for i, source in enumerate(stats_right['sources']):
                                    title = source.get('title', 'Source inconnue')
                                    url = source.get('url', '')
                                    sources_html += f'<div class="source-item">'
                                    sources_html += f'<strong>Source {i+1}:</strong> {title}<br>'
                                    if url:
                                        sources_html += f'<a href="{url}" target="_blank">🔗 {url}</a><br>'
                                    if source.get('text'):
                                        excerpt = source['text'][:200] + "..." if len(source['text']) > 200 else source['text']
                                        sources_html += f'<em>Extrait: "{excerpt}"</em>'
                                    sources_html += '</div>'
                                sources_html += '</div>'
                                st.markdown(sources_html, unsafe_allow_html=True)
                        
                        # Ajouter à l'historique
                        st.session_state.messages_right.append({
                            "role": "assistant", 
                            "content": content_right,
                            "model": model_right,
                            "stats": stats_right
                        })
                    else:
                        st.error(f"❌ Aucune réponse reçue de {model_right}")
        
        return stats_left, stats_right
    
    # Exécuter le traitement parallèle
    try:
        stats_left, stats_right = asyncio.run(process_both_models())
        
        # Afficher la comparaison des performances si les deux ont réussi
        if stats_left and stats_right:
            st.markdown("---")
            st.subheader("📊 Comparaison des performances")
            
            col_perf1, col_perf2, col_perf3, col_perf4 = st.columns(4)
            
            with col_perf1:
                time_diff = stats_right['response_time'] - stats_left['response_time']
                st.metric(
                    "⏱️ Temps de réponse",
                    f"{model_left}: {stats_left['response_time']}s",
                    f"{time_diff:+.2f}s vs {model_right}"
                )
            
            with col_perf2:
                tokens_diff = stats_right['output_tokens'] - stats_left['output_tokens']
                st.metric(
                    "🔤 Tokens de sortie",
                    f"{model_left}: {stats_left['output_tokens']}",
                    f"{tokens_diff:+d} vs {model_right}"
                )
            
            with col_perf3:
                searches_diff = stats_right['web_searches'] - stats_left['web_searches']
                st.metric(
                    "🔍 Recherches web",
                    f"{model_left}: {stats_left['web_searches']}",
                    f"{searches_diff:+d} vs {model_right}"
                )
            
            with col_perf4:
                cost_diff = stats_right['total_cost'] - stats_left['total_cost']
                st.metric(
                    "💲 Coût total",
                    f"{model_left}: ${stats_left['total_cost']:.6f}",
                    f"${cost_diff:+.6f} vs {model_right}"
                )
            
            # Afficher les coûts détaillés en mode debug
            if debug_mode:
                st.subheader("💰 Détail des coûts")
                col_cost1, col_cost2 = st.columns(2)
                
                with col_cost1:
                    st.write(f"**Coûts {model_left}:**")
                    st.write(f"• Tokens d'entrée: ${stats_left['entry_cost']:.6f}")
                    st.write(f"• Tokens de sortie: ${stats_left['output_cost']:.6f}")
                    st.write(f"• Recherches web: ${stats_left['search_cost']:.6f}")
                    st.write(f"**Total: ${stats_left['total_cost']:.6f}**")
                
                with col_cost2:
                    st.write(f"**Coûts {model_right}:**")
                    st.write(f"• Tokens d'entrée: ${stats_right['entry_cost']:.6f}")
                    st.write(f"• Tokens de sortie: ${stats_right['output_cost']:.6f}")
                    st.write(f"• Recherches web: ${stats_right['search_cost']:.6f}")
                    st.write(f"**Total: ${stats_right['total_cost']:.6f}**")
                
                # Analyse comparative
                if stats_left['total_cost'] > 0 and stats_right['total_cost'] > 0:
                    ratio = stats_right['total_cost'] / stats_left['total_cost']
                    if ratio > 1:
                        st.info(f"💡 {model_right} coûte {ratio:.1f}x plus cher que {model_left}")
                    else:
                        st.info(f"💡 {model_left} coûte {1/ratio:.1f}x plus cher que {model_right}")
                
                # Comparaison des sources en mode debug
                if (stats_left.get('sources') or stats_right.get('sources')):
                    st.subheader("🔍 Comparaison des sources")
                    col_src1, col_src2 = st.columns(2)
                    
                    with col_src1:
                        st.write(f"**Sources {model_left}:**")
                        if stats_left.get('sources'):
                            for i, source in enumerate(stats_left['sources']):
                                with st.expander(f"Source {i+1}: {source.get('title', 'Sans titre')[:30]}..."):
                                    st.write(f"**URL:** {source.get('url', 'Non disponible')}")
                                    if source.get('text'):
                                        st.write(f"**Extrait:** {source['text'][:300]}...")
                        else:
                            st.write("Aucune source trouvée")
                    
                    with col_src2:
                        st.write(f"**Sources {model_right}:**")
                        if stats_right.get('sources'):
                            for i, source in enumerate(stats_right['sources']):
                                with st.expander(f"Source {i+1}: {source.get('title', 'Sans titre')[:30]}..."):
                                    st.write(f"**URL:** {source.get('url', 'Non disponible')}")
                                    if source.get('text'):
                                        st.write(f"**Extrait:** {source['text'][:300]}...")
                        else:
                            st.write("Aucune source trouvée")
    
    except Exception as e:
        st.error(f"Erreur lors du traitement parallèle: {str(e)}")
        if debug_mode:
            st.error(f"Debug - Erreur détaillée: {traceback.format_exc()}")

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; font-size: 0.9em;'>
    <p>🤖 Assistant Juridique Français - Comparaison Multi-Modèles IA</p>
    <p>⚠️ Les réponses fournies sont à titre informatif uniquement.</p>
    <p>🔵 <strong>Gauche:</strong> {model_left} | 🔴 <strong>Droite:</strong> {model_right}</p>
    <p>💡 <strong>Claude 3.5 Haiku:</strong> Rapide & économique | <strong>Claude 3.7 Sonnet:</strong> Avancé & précis | <strong>Perplexity AI:</strong> Recherche web native</p>
</div>
""".format(model_left=model_left, model_right=model_right), unsafe_allow_html=True)