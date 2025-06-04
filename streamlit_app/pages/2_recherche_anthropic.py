import streamlit as st
import anthropic
import time
from dotenv import load_dotenv
import os
import json
import base64

# Chargement des variables d'environnement
load_dotenv()

# Configuration de la page Streamlit
st.set_page_config(
    page_title="Assistant Juridique Français",
    page_icon="⚖️",
    layout="wide"
)

# Fonction pour encoder un PDF en base64
def encode_pdf_to_base64(uploaded_file):
    """
    Encode un fichier PDF téléchargé en base64.
    
    Args:
        uploaded_file: Fichier téléchargé via st.file_uploader
        
    Returns:
        str: Chaîne encodée en base64
    """
    if uploaded_file is not None:
        base64_pdf = ""
        for file in uploaded_file:
            # Lire le contenu du fichier
            pdf_bytes = file.getvalue()
            
            # Encoder en base64
            base64_pdf += base64.b64encode(pdf_bytes).decode('utf-8')
        
        return base64_pdf
    
    return None

# Fonction pour gérer les erreurs de recherche web
def handle_search_error(query_parts):
    """
    Gère les erreurs de recherche web en fonction du code d'erreur reçu.
    
    Args:
        query_parts (list): Les parties de la requête JSON
        
    Returns:
        tuple: (is_error, error_message)
    """
    try:
        # Joindre les parties de la requête et parser le JSON
        query_json = "".join(query_parts)
        if not query_json:
            return False, None
            
        # Vérifier si c'est une erreur
        if "error_code" in query_json:
            # Essayer de parser le JSON complet
            try:
                response_data = json.loads(query_json)
                # Vérifier si c'est une structure d'erreur
                if response_data.get("content", {}).get("type") == "web_search_tool_result_error":
                    error_code = response_data["content"].get("error_code")
                    
                    error_messages = {
                        "too_many_requests": "Limite de requêtes dépassée. Veuillez réessayer plus tard.",
                        "invalid_input": "Requête de recherche invalide. Veuillez vérifier vos paramètres.",
                        "max_uses_exceeded": "Nombre maximum de recherches web dépassé.",
                        "query_too_long": "La requête dépasse la longueur maximale autorisée.",
                        "unavailable": "Une erreur interne s'est produite. Veuillez réessayer ultérieurement."
                    }
                    
                    error_message = error_messages.get(error_code, f"Erreur inconnue: {error_code}")
                    return True, error_message
            except json.JSONDecodeError:
                # Si le parsing échoue, essayer d'extraire le code d'erreur directement
                if "error_code" in query_json:
                    for error_code in ["too_many_requests", "invalid_input", "max_uses_exceeded", "query_too_long", "unavailable"]:
                        if error_code in query_json:
                            error_messages = {
                                "too_many_requests": "Limite de requêtes dépassée. Veuillez réessayer plus tard.",
                                "invalid_input": "Requête de recherche invalide. Veuillez vérifier vos paramètres.",
                                "max_uses_exceeded": "Nombre maximum de recherches web dépassé.",
                                "query_too_long": "La requête dépasse la longueur maximale autorisée.",
                                "unavailable": "Une erreur interne s'est produite. Veuillez réessayer ultérieurement."
                            }
                            return True, error_messages.get(error_code, f"Erreur inconnue: {error_code}")
    
    except Exception as e:
        # En cas d'erreur durant le traitement, on considère qu'il n'y a pas d'erreur détectée
        return False, None
        
    return False, None

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
if 'search_errors' not in st.session_state:
    st.session_state.search_errors = []
if 'uploaded_file' not in st.session_state:
    st.session_state.uploaded_file = None

# Titre de l'application
st.title("Assistant Juridique Français Anthropic 🇫🇷⚖️")

# Ajouter du CSS personnalisé dès le début pour s'assurer qu'il est toujours appliqué
st.markdown("""
<style>
.stApp {
    max-width: 1200px;
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

/* Style pour les erreurs */
div.error-block {
    background-color: rgba(255, 235, 235, 0.85);
    border-radius: 8px;
    padding: 12px 15px;
    margin-bottom: 16px;
    border-left: 3px solid #e63946;
}

div.error-block h4 {
    color: #e63946;
    margin-top: 0;
    margin-bottom: 8px;
}

/* Style pour les documents */
div.document-block {
    background-color: rgba(230, 245, 255, 0.85);
    border-radius: 8px;
    padding: 12px 15px;
    margin-bottom: 16px;
    border-left: 3px solid #0096c7;
}

div.document-block h4 {
    color: #0096c7;
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
        ["claude-3-7-sonnet-latest","claude-3-5-haiku-latest", "claude-4-0-sonnet"]
    )
    
    # Paramètres avancés
    st.subheader("Paramètres avancés")
    temperature = st.slider("Temperature", 0.0, 1.0, 0.3, 0.1)
    max_tokens = st.slider("Tokens max en sortie", 500, 4000, 3000, 100)
    max_searches = st.slider("Nombre max de recherches web", 1, 5, 3, 1)
    
    # Domaines autorisés
    st.subheader("Domaines prioritaires pour la recherche")
    domains = st.text_area(
        "Domaines autorisés (un par ligne)",
        "www.legifrance.gouv.fr\nannuaire-entreprises.data.gouv.fr\nservice-public.fr\nwww.conseil-constitutionnel.fr\nwww.conseil-etat.fr\n"
    )
    allowed_domains = [d.strip() for d in domains.split('\n') if d.strip()]
    
    # Téléchargement de document
    st.subheader("Document de référence")
    uploaded_file = st.file_uploader("Télécharger un PDF (8 Mo Maximum)", type=["pdf"],accept_multiple_files=True)
    
    # Si un fichier est téléchargé, l'enregistrer dans la session
    if uploaded_file is not None:
        for file in uploaded_file:
            # Vérifier si le fichier est un PDF
            if file.type != "application/pdf":
                st.error("Veuillez télécharger un fichier PDF valide.")
                
            st.session_state.uploaded_file = uploaded_file
            st.success(f"Document '{file.name}' prêt à être utilisé")
        
        # Ajouter une prévisualisation du document PDF
        pdf_display = f'<iframe src="data:application/pdf;base64,{encode_pdf_to_base64(uploaded_file)}" width="100%" height="200" type="application/pdf"></iframe>'
        st.markdown(pdf_display, unsafe_allow_html=True)
    
   
    
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
        # Vérifier si le message contient un document
        if isinstance(message["content"], list) and any(item.get("type") == "document" for item in message["content"] if isinstance(item, dict)):
            # Trouver l'élément texte
            text_content = next((item.get("text", "") for item in message["content"] if isinstance(item, dict) and item.get("type") == "text"), "")
            st.markdown(text_content)
            st.info("📎 Document PDF joint à cette question")
        else:
            st.markdown(message["content"], unsafe_allow_html=True)

# Traitement de la nouvelle question
if prompt:
    # Construire le contenu du message en fonction de la présence d'un PDF
    pdf_data = None
    if st.session_state.uploaded_file is not None:
        pdf_data = encode_pdf_to_base64(st.session_state.uploaded_file)
   
    
    if pdf_data:
        # Message avec document attaché
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
        # Pour stockage dans l'historique
        st.session_state.messages.append({"role": "user", "content": message_content})
        
        # Pour affichage dans l'interface
        with st.chat_message("user"):
            st.markdown(prompt)
            st.info("📎 Document PDF joint à cette question")
    else:
        # Message standard sans document
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
    
    # récupérer la date actuelle
    date = time.strftime("%d/%m/%Y")

    # Préparer le système prompt
    system = [
        {
            "type": "text",
            "text": "Tu es un assistant IA Français spécialisé dans le domaine du droit français qui répond toujours en français.\n",
        },
        
        {
            "type": "text",
            "text": "Tu peux effectuer des recherches sur le web pour trouver des informations juridiques pertinentes.\n",
        },
        {
            "type": "text",
            "text": "Pour toute question relative à la date. Demande toi quelle est la date d'ajourd'hui. La date d'aujourd'hui est le {date} ce qui est après la date de tes recherches.. \n",
        },
                {
            "type": "text",
            "text": "n Lorsque la source est précise, il n'est pas nécéssaire d'ajouter des mots clés en plus dans tes recherches\n",
        },
        {
            "type": "text",
            "text": "Si il s'agit d'une question concernant une source écrite de droit, fais toujours au moins une recherche internet et répond sous cette structure :\n",
        },

        {
            "type": "text",
            "text": "Commence par écrire le Titre de la source écrite. Définis ensuite le cadre légal de la source relativement à la question. Fais ensuite une synthèse concise générale de la source écrite. Enfin fais une analyse approfondie étape par étape en ajoutant les référence à la fin de chaque paragraphe sous la forme [numéro de référence] de celle ci.\n",
        },
        {
            "type": "text",
            "text": " Pose une question afférente au sujet à l'utilisateur.\n",
        },
        {
            "type": "text",
            "text": "Si il s'agit d'une question concernant une l'état du droit dans un domaine ou l'application du droit à des faits, fais toujours au strict minimum une recherche internet et répond sous cette structure :\n",
        },
        {
            "type": "text",
            "text": "Premièrement, Planifie la réponse sous la forme d'un plan. Ensuite, définit le cadre légal relatif à la question ou au domaine d'application du droit. Fais ensuite une synthèse concise de la réponse pointant sur les différentes partie de la future analyse approfondie. Fais ensuite une analyse approfondie. \n",
        },
        {
            "type": "text",
            "text": "Si il s'agit d'une question concernant une l'état du droit dans un domaine ou l'application du droit à des faits, fais toujours au strict minimum une recherche internet et répond sous cette structure :\n",
        },
        
        {
            "type": "text",
            "text": "Si il s'agit d'une analyse de document, fais toujours au moins une recherche internet.\n",
        },

        {
            "type": "text",
            "text": "Ajoute les références utilisées à la fin de ton paragraphe sous la forme [numéro de reference]\n ",
        },
        {
            "type": "text",
            "text": "Enfin, Retourne les sources pertinentes sous forme d'une liste numerotées avec titre et url.\n",
        }
    ]
    
    # Créer la liste des messages pour la requête
    api_messages = []
    for m in st.session_state.messages:
        # Si le contenu est une liste (contenant un document), le traiter différemment
        if isinstance(m["content"], list):
            api_messages.append({"role": m["role"], "content": m["content"]})
        # Si c'est une chaîne simple (texte standard)
        elif isinstance(m["content"], str):
            # Nettoyer le contenu des balises HTML
            content = m["content"]
            content = content.replace('<div class="search-block">', '').replace('</div>', '')
            content = content.replace('<div class="citations-block">', '').replace('</div>', '')
            content = content.replace('<div class="error-block">', '').replace('</div>', '')
            content = content.replace('<div class="document-block">', '').replace('</div>', '')
            api_messages.append({"role": m["role"], "content": content})
        # Autres cas (si nécessaire)
        else:
            api_messages.append({"role": m["role"], "content": m["content"]})
    
    # Configuration des outils
    tools = [{
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": max_searches,
        "allowed_domains": allowed_domains,
    }
   
             ]
    
    # Réinitialiser les erreurs de recherche
    st.session_state.search_errors = []
    
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
                            elif event.delta.type == "tool_result_delta" and hasattr(event.delta, "partial_tool_result"):
                                # Capturer les résultats d'outils qui pourraient contenir des erreurs
                                query_parts.append(event.delta.partial_tool_result)
                        
                        # Capture du texte de réponse
                        elif hasattr(event, "delta") and hasattr(event.delta, "type"):
                            if event.delta.type == "text_delta" and hasattr(event.delta, "text"):
                                text = event.delta.text
                                complete_response_text += text
                                
                                # Construire la mise en page complète avec les requêtes, erreurs et la réponse
                                display_html = ""
                                
                                # Afficher les erreurs de recherche s'il y en a
                                if st.session_state.search_errors:
                                    error_html = """
                                    <div class="error-block">
                                    <h4>⚠️ Erreurs de recherche:</h4>
                                    """
                                    for i, error in enumerate(st.session_state.search_errors):
                                        error_html += f"<p><strong>Erreur {i+1}:</strong> <em>{error}</em></p>"
                                    error_html += "</div>"
                                    display_html += error_html
                                
                                # Utiliser HTML pour créer la mise en page des recherches
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
                            
                            # Vérifier si nous avons une erreur
                            is_error, error_message = handle_search_error(query_parts)
                            
                            if is_error and error_message:
                                # Ajouter l'erreur à la liste des erreurs
                                st.session_state.search_errors.append(error_message)
                                
                                # Construire la mise en page HTML avec les erreurs
                                display_html = ""
                                
                                # Afficher les erreurs de recherche
                                error_html = """
                                <div class="error-block">
                                <h4>⚠️ Erreurs de recherche:</h4>
                                """
                                for i, error in enumerate(st.session_state.search_errors):
                                    error_html += f"<p><strong>Erreur {i+1}:</strong> <em>{error}</em></p>"
                                error_html += "</div>"
                                display_html += error_html
                                
                                # Utiliser HTML pour créer la mise en page des recherches
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
                            else:
                                # Reconstituer et extraire la requête complète (traitement normal)
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
                                        # Afficher les erreurs de recherche s'il y en a
                                        if st.session_state.search_errors:
                                            error_html = """
                                            <div class="error-block">
                                            <h4>⚠️ Erreurs de recherche:</h4>
                                            """
                                            for i, error in enumerate(st.session_state.search_errors):
                                                error_html += f"<p><strong>Erreur {i+1}:</strong> <em>{error}</em></p>"
                                            error_html += "</div>"
                                            display_html += error_html
                                        
                                        # Utiliser HTML pour créer la mise en page des recherches
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
                
                # Ajouter un coût supplémentaire si un PDF a été utilisé
                pdf_cost = 0
                if pdf_data:
                    # Estimation du coût basée sur la taille du PDF (à ajuster selon vos tarifs)
                    pdf_size_mb = len(pdf_data) / (1024 * 1024)  # Convertir en Mo
                    pdf_cost = pdf_size_mb * 0.01  # Coût fictif, à adapter
                    total_cost += pdf_cost
                
                stats_placeholder.markdown(
                    f"""
                    ⏱️ Temps de réponse: {response_time} secondes | 
                    🔤 Tokens d'entrée: {input_tokens} | 
                    💲 Coût en tokens d'entrée estimé: {entry_cost:.6f} | 
                    🔤 Tokens de sortie: {output_tokens} | 
                    💲 Coût en tokens de sortie estimé: {output_cost:.6f} | 
                    🔎 Recherches web: {web_search_requests} | 
                    💲 Coût en recherches web estimé: {search_cost:.6f} |
                    {"📄 Document PDF traité |" if pdf_data else ""}
                    💲 Coût total estimé: {total_cost:.6f}
                     Raison d'arrêt: {final_message.stop_reason}
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
                
                # Construire la réponse finale complète avec les recherches, erreurs et citations en HTML
                final_html = ""
                
                # Ajouter le bloc d'erreurs si nécessaire
                if st.session_state.search_errors:
                    error_html = """
                    <div class="error-block">
                    <h4>⚠️ Erreurs de recherche:</h4>
                    """
                    for i, error in enumerate(st.session_state.search_errors):
                        error_html += f"<p><strong>Erreur {i+1}:</strong> <em>{error}</em></p>"
                    error_html += "</div>"
                    final_html += error_html
                
                # Ajouter le bloc document si un PDF a été utilisé
                if pdf_data:
                    pdf_name = st.session_state.uploaded_file.name if hasattr(st.session_state.uploaded_file, 'name') else "Document"
                    document_html = f"""
                    <div class="document-block">
                    <h4>📄 Document de référence utilisé:</h4>
                    <p>{pdf_name}</p>
                    </div>
                    """
                    final_html += document_html
                
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
                # if citations:
                #     citations_html = """
                #     <div class="citations-block">
                #     <h4>📚 Sources consultées:</h4>
                #     """
                #     for i, citation in enumerate(citations):
                #         title = citation.get("title", "Sans titre")
                #         url = citation.get("url", "")
                #         text = citation.get("text", "")
                        
                #         citations_html += f"<p><strong>Source {i+1}:</strong> {title}</p>"
                #         if url:
                #             citations_html += f"<p>URL: {url}</p>"
                #         if text:
                #             # Limiter la longueur du texte cité
                #             if len(text) > 150:
                #                 text = text[:150] + "..."
                #             citations_html += f"<p>Extrait: \"{text}\"</p>"
                #     citations_html += "</div>"
                #     final_html += citations_html
                
                # Ajouter la réponse à l'historique (avec les recherches et citations incluses)
                st.session_state.messages.append({"role": "assistant", "content": final_html})
                
                # Mettre à jour l'affichage une dernière fois
                response_placeholder.markdown(final_html, unsafe_allow_html=True)
        
        except Exception as e:
            st.error(f"Erreur lors de la communication avec l'API: {str(e)}")