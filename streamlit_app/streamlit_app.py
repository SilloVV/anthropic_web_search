import streamlit as st
import anthropic
import time
from dotenv import load_dotenv
import os
import json

# Chargement des variables d'environnement
load_dotenv()

# Configuration de la page Streamlit
st.set_page_config(
    page_title="Assistant Juridique Français",
    page_icon="⚖️",
    layout="wide"
)

# Fonction pour extraire les citations du contenu
def extract_citations_from_blocks(content_blocks):
    """Extrait les citations des blocs de contenu"""
    citations = []
    
    for block in content_blocks:
        if hasattr(block, 'citations') and block.citations:
            for citation in block.citations:
                citation_info = {
                    "title": citation.title if hasattr(citation, 'title') else "Sans titre",
                    "url": citation.url if hasattr(citation, 'url') else "",
                    "text": citation.cited_text if hasattr(citation, 'cited_text') else ""
                }
                citations.append(citation_info)
    
    return citations

# Initialisation des variables de session
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'citations' not in st.session_state:
    st.session_state.citations = []
if 'usage_stats' not in st.session_state:
    st.session_state.usage_stats = {}
if 'response_time' not in st.session_state:
    st.session_state.response_time = 0

# Titre de l'application
st.title("Assistant Juridique Français 🇫🇷⚖️")

# Ajouter du CSS personnalisé dès le début pour s'assurer qu'il est toujours appliqué
st.markdown("""
<style>
.stApp {
    max-width: 1200px;
    margin: 0 auto;
}

/* Style pour le bloc de recherche avec fond gris et opacité */
div.search-block {
    background-color: rgba(220, 220, 220, 0.85);
    border-radius: 8px;
    padding: 12px 15px;
    margin-bottom: 16px;
}

div.search-block h4 {
    color: #0077b6;
    margin-top: 0;
    margin-bottom: 8px;
}

/* Style pour les citations */
div.citations-block {
    background-color: rgba(240, 240, 245, 0.85);
    border-radius: 8px;
    padding: 12px 15px;
    margin-top: 16px;
    border-left: 3px solid #0077b6;
}

div.citations-block h4 {
    color: #0077b6;
    margin-top: 0;
    margin-bottom: 8px;
}

/* Style pour les séparateurs */
hr {
    margin: 1rem 0;
    border: 0;
    height: 1px;
    background-image: linear-gradient(to right, rgba(0, 0, 0, 0), rgba(0, 0, 0, 0.2), rgba(0, 0, 0, 0));
}
</style>
""", unsafe_allow_html=True)

# Sidebar pour la configuration
with st.sidebar:
    st.header("Configuration")
    
    # Sélection du modèle
    model = st.selectbox(
        "Modèle Claude",
                ["claude-3-7-sonnet-latest", "claude-3-5-haiku-latest", "claude-3-5-sonnet-latest"]

    )
    
    # Paramètres avancés
    st.subheader("Paramètres avancés")
    temperature = st.slider("Temperature", 0.0, 1.0, 0.7, 0.1)
    max_tokens = st.slider("Tokens max en sortie", 500, 4000, 1500, 100)
    max_searches = st.slider("Nombre max de recherches web", 1, 5, 3, 1)
    
    # Domaines autorisés
    st.subheader("Domaines prioritaires pour la recherche")
    domains = st.text_area(
        "Domaines autorisés (un par ligne)",
        "www.legifrance.gouv.fr\nannuaire-entreprises.data.gouv.fr\nservice-public.fr"
    )
    allowed_domains = [d.strip() for d in domains.split('\n') if d.strip()]
    
    # Debug mode
    debug_mode = st.checkbox("Mode débogage", value=False)
    
    # Affichage de la clé API
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        api_key = st.text_input("Clé API Anthropic", type="password")
        if api_key:
            st.success("Clé API ajoutée temporairement")
    else:
        st.success("Clé API chargée depuis .env")

# Zone de texte pour la question de l'utilisateur
prompt = st.chat_input("Posez votre question juridique ici...")

# Affichage de l'historique des messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"], unsafe_allow_html=True)

# Traitement de la nouvelle question
if prompt:
    # Ajouter la question à l'historique
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Afficher la question dans l'interface
    with st.chat_message("user"):
        st.markdown(prompt)

    # Préparer le système prompt
    system = [
        {
            "type": "text",
            "text": "Tu es un assistant IA Français spécialisé dans le domaine du droit français.\n",
        },
        {
            "type": "text",
            "text": "Tu es capable de répondre à des questions juridiques et de fournir des conseils sur des sujets liés au droit français en citant des références en droit français.\n",
        },
        {
            "type": "text",
            "text": "Tu peux également effectuer des recherches sur le web pour trouver des informations juridiques pertinentes.\n",
        },
        {
            "type": "text",
            "text": "Important : Pour toutes tes réponses nécessitant des sources externes : Utilise systématiquement le format de citation suivant :<titre>Titre complet de la source</titre> <url>Lien exact vers la source</url><extrait>Extrait pertinent et concis de la source (limité à 2-3 phrases clés)</extrait> \n ",
        },
        {
            "type": "text",
            "text": "Tu dois toujours respecter la vie privée et la confidentialité des utilisateurs.\n",
        },
        {
            "type": "text",
            "text": "Retourne les sources pertinentes sous forme d'une liste avec titre et url.\n",
        },
        
    ]
    
    # Créer la liste des messages pour la requête
    api_messages = []
    for m in st.session_state.messages:
        if isinstance(m["content"], str):
            # Nettoyer le contenu des balises HTML qui pourraient causer des problèmes
            content = m["content"]
            # Supprimer les balises div, tout en conservant le contenu
            content = content.replace('<div class="search-block">', '').replace('</div>', '')
            content = content.replace('<div class="citations-block">', '').replace('</div>', '')
            api_messages.append({"role": m["role"], "content": content})
        else:
            api_messages.append({"role": m["role"], "content": m["content"]})
    
    # Configuration des outils
    tools = [{
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": max_searches,
        "allowed_domains": allowed_domains,
    }]
    
    # Zone pour afficher la réponse de l'assistant
    with st.chat_message("assistant"):
        # Conteneur principal pour la réponse
        response_placeholder = st.empty()
        
        # Zone dédiée pour les statistiques qui apparaît en bas
        stats_placeholder = st.empty()
        
        # Message d'attente initial
        response_placeholder.markdown("*Traitement de votre demande en cours...*")
        
        # Mesurer le temps de réponse
        start_time = time.time()
        
        try:
            # Créer le client Anthropic
            client = anthropic.Anthropic(api_key=api_key)
            
            # Variables pour capturer la réponse
            complete_response_text = ""
            search_queries = []
            building_query = False
            query_parts = []
            search_div_added = False
            
            # Démarrer le streaming
            with client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=api_messages,
                tools=tools
            ) as stream:
                # Parcourir tous les événements
                for event in stream:
                    # Gérer chaque type d'événement
                    if event.type == "content_block_start":
                        if hasattr(event, "content_block") and hasattr(event.content_block, "type"):
                            if event.content_block.type == "server_tool_use" and event.content_block.name == "web_search":
                                building_query = True
                                query_parts = []
                    
                    elif event.type == "content_block_delta":
                        # Capture des parties de la requête JSON
                        if building_query and hasattr(event, "delta") and hasattr(event.delta, "type"):
                            if event.delta.type == "input_json_delta" and hasattr(event.delta, "partial_json"):
                                query_parts.append(event.delta.partial_json)
                        
                        # Capture du texte de réponse
                        elif hasattr(event, "delta") and hasattr(event.delta, "type"):
                            if event.delta.type == "text_delta" and hasattr(event.delta, "text"):
                                text = event.delta.text
                                complete_response_text += text
                                
                                # Construire la mise en page complète avec les requêtes et la réponse
                                display_html = ""
                                
                                # Utiliser HTML pour créer la mise en page
                                if search_queries:
                                    # Bloc de recherches
                                    search_html = """
                                    <div class="search-block">
                                    <h4>🔍 Recherches effectuées:</h4>
                                    """
                                    for i, query in enumerate(search_queries):
                                        search_html += f"<p><strong>Recherche {i+1}:</strong> <em>{query}</em></p>"
                                    search_html += "</div>"
                                    display_html += search_html
                                
                                # Ajouter la réponse actuelle
                                display_html += f"<div>{complete_response_text}</div>"
                                
                                # Utiliser un composant html pour garantir le rendu CSS
                                response_placeholder.markdown(display_html, unsafe_allow_html=True)
                    
                    elif event.type == "content_block_stop":
                        if building_query:
                            building_query = False
                            # Reconstituer et extraire la requête complète
                            try:
                                query_json = "".join(query_parts)
                                extracted_query = None
                                
                                # Essayer d'extraire comme JSON complet
                                if query_json.startswith("{") and query_json.endswith("}"):
                                    try:
                                        query_data = json.loads(query_json)
                                        if "query" in query_data:
                                            extracted_query = query_data["query"]
                                    except json.JSONDecodeError:
                                        pass
                                
                                # Si ça échoue, essayer d'extraire la partie query uniquement
                                if not extracted_query and "query" in query_json:
                                    query_start = query_json.find('"query"')
                                    if query_start != -1:
                                        remaining = query_json[query_start:].split('":', 1)[1].strip()
                                        if remaining.startswith('"'):
                                            # Extraction d'une chaîne de caractères entre guillemets
                                            query_end = remaining[1:].find('"')
                                            if query_end != -1:
                                                extracted_query = remaining[1:query_end+1]
                                        elif remaining.startswith('{'):
                                            # Si c'est un objet complet
                                            extracted_query = remaining
                                
                                # Ajouter la requête si elle a été extraite avec succès
                                if extracted_query:
                                    search_queries.append(extracted_query)
                                    
                                    # Construire la mise en page HTML complète
                                    display_html = ""
                                    
                                    # Utiliser HTML pour créer la mise en page
                                    if search_queries:
                                        # Bloc de recherches
                                        search_html = """
                                        <div class="search-block">
                                        <h4>🔍 Recherches effectuées:</h4>
                                        """
                                        for i, query in enumerate(search_queries):
                                            search_html += f"<p><strong>Recherche {i+1}:</strong> <em>{query}</em></p>"
                                        search_html += "</div>"
                                        display_html += search_html
                                    
                                    # Ajouter la réponse actuelle
                                    display_html += f"<div>{complete_response_text}</div>"
                                    
                                    # Utiliser un composant html pour garantir le rendu CSS
                                    response_placeholder.markdown(display_html, unsafe_allow_html=True)
                            except Exception as e:
                                if debug_mode:
                                    st.error(f"Erreur lors de l'extraction de la requête: {str(e)}")
                
                # Récupérer le message final
                final_message = stream.get_final_message()
                
                # Extraire les citations des blocs de contenu
                citations = extract_citations_from_blocks(final_message.content)
                
                # Récupérer les statistiques d'utilisation
                usage = final_message.usage
                input_tokens = usage.input_tokens if usage else "Non disponible"
                output_tokens = usage.output_tokens if usage else "Non disponible"
                web_search_requests = usage.server_tool_use.web_search_requests if usage and usage.server_tool_use else 0
                
                # Calculer le temps de réponse
                response_time = round(time.time() - start_time, 2)
                
                # Afficher les statistiques d'utilisation
                try:
                    entry_cost = (int(input_tokens) / 1000000) * 3
                    output_cost = (int(output_tokens) / 1000000) * 15
                    search_cost = (int(web_search_requests) / 1000) * 10
                    total_cost = entry_cost + output_cost + search_cost
                except:
                    entry_cost = output_cost = search_cost = total_cost = 0
                
                stats_placeholder.markdown(
                    f"""
                    ⏱️ Temps de réponse: {response_time} secondes | 
                    🔤 Tokens d'entrée: {input_tokens} | 
                    💲 Coût en tokens d'entrée estimé: {entry_cost:.6f} | 
                    🔤 Tokens de sortie: {output_tokens} | 
                    💲 Coût en tokens de sortie estimé: {output_cost:.6f} | 
                    🔎 Recherches web: {web_search_requests} | 
                    💲 Coût en recherches web estimé: {search_cost:.6f} | 
                    💲 Coût total estimé: {total_cost:.6f}
                    """
                )
                
                # Afficher les citations en détail dans la sidebar si demandé
                if citations and debug_mode:
                    with st.sidebar:
                        st.subheader("Détails des citations")
                        for i, citation in enumerate(citations):
                            with st.expander(f"Citation {i+1}: {citation.get('title', 'Sans titre')[:40]}..."):
                                st.write(f"**URL:** {citation.get('url', 'Non disponible')}")
                                st.write(f"**Extrait:** {citation.get('text', 'Non disponible')}")
                
                # Mettre à jour la session
                st.session_state.citations = citations
                st.session_state.usage_stats = {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "web_search_requests": web_search_requests,
                    "response_time": response_time
                }
                st.session_state.response_time = response_time
                
                # Construire la réponse finale complète avec les recherches et citations en HTML
                final_html = ""
                
                # Ajouter le bloc de recherches si nécessaire
                if search_queries:
                    search_html = """
                    <div class="search-block">
                    <h4>🔍 Recherches effectuées:</h4>
                    """
                    for i, query in enumerate(search_queries):
                        search_html += f"<p><strong>Recherche {i+1}:</strong> <em>{query}</em></p>"
                    search_html += "</div>"
                    final_html += search_html
                
                # Ajouter la réponse
                final_html += f"<div>{complete_response_text}</div>"
                
                # Ajouter les citations si elles existent
                if citations:
                    citations_html = """
                    <div class="citations-block">
                    <h4>📚 Sources consultées:</h4>
                    """
                    for i, citation in enumerate(citations):
                        title = citation.get("title", "Sans titre")
                        url = citation.get("url", "")
                        text = citation.get("text", "")
                        
                        citations_html += f"<p><strong>Source {i+1}:</strong> {title}</p>"
                        if url:
                            citations_html += f"<p>URL: {url}</p>"
                        if text:
                            # Limiter la longueur du texte cité
                            if len(text) > 150:
                                text = text[:150] + "..."
                            citations_html += f"<p>Extrait: \"{text}\"</p>"
                    citations_html += "</div>"
                    final_html += citations_html
                
                # Ajouter la réponse à l'historique (avec les recherches et citations incluses)
                st.session_state.messages.append({"role": "assistant", "content": final_html})
                
                # Mettre à jour l'affichage une dernière fois
                response_placeholder.markdown(final_html, unsafe_allow_html=True)
        
        except Exception as e:
            st.error(f"Erreur lors de la communication avec l'API: {str(e)}")