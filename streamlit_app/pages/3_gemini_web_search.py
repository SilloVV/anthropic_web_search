import streamlit as st
import base64
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
import time
import pathlib

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

# Configuration de la page
st.set_page_config(
    page_title="Assistant Juridique Français",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personnalisé
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1f4e79;
        text-align: center;
        margin-bottom: 2rem;
        font-weight: bold;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .stTextArea textarea {
        font-size: 1.1rem;
    }
    .response-container {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 4px solid #1f4e79;
        margin: 1rem 0;
    }
    .warning-box {
        background-color: #fff3cd;
        border: 1px solid #ffeaa7;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Fonction pour estimer le coût
def estimate_cost(input_tokens=0, output_tokens=0, web_searches=0):
    """Estime le coût basé sur les tokens et recherches web"""
    input_cost = (input_tokens / 1_000_000) * 3.0  # 3$ par million de tokens d'input
    output_cost = (output_tokens / 1_000_000) * 15.0  # 15$ par million de tokens d'output
    search_cost = web_searches * 0.035  # 0.035$ par recherche internet
    
    total_cost = input_cost + output_cost + search_cost
    return {
        'input_cost': input_cost,
        'output_cost': output_cost,
        'search_cost': search_cost,
        'total_cost': total_cost,
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'web_searches': web_searches
    }


# Fonction pour extraire les citations des métadonnées
def extract_citations(response_metadata):
    """Extrait les citations des métadonnées de grounding"""
    citations = {}
    
    if hasattr(response_metadata, 'grounding_metadata') and response_metadata.grounding_metadata:
        grounding_metadata = response_metadata.grounding_metadata
        
        # Extraire les chunks de grounding (sources)
        if hasattr(grounding_metadata, 'grounding_chunks') and grounding_metadata.grounding_chunks:
            for grounding_chunk in grounding_metadata.grounding_chunks:
                if (hasattr(grounding_chunk, 'web') and 
                    grounding_chunk.web is not None):
                    
                    web_info = grounding_chunk.web
                    title = getattr(web_info, 'title', 'Source inconnue')
                    uri = getattr(web_info, 'uri', '')
                    
                    # Éviter les doublons en utilisant l'URI comme clé
                    if uri and uri not in citations:
                        citations[uri] = {
                            'title': title,
                            'uri': uri
                        }
    
    return citations

# Fonction pour formater les citations
def format_citations(citations):
    """Formate les citations pour l'affichage"""
    if not citations:
        return ""
    
    citations_text = "\n\n---\n\n### 📚 Sources utilisées :\n\n"
    
    for i, (uri, citation) in enumerate(citations.items(), 1):
        citations_text += f"**[{i}]** [{citation['title']}]({citation['uri']})\n\n"
    
    return citations_text

# Fonction pour traiter les fichiers uploadés
def process_uploaded_files(uploaded_files):
    """Traite les fichiers uploadés et retourne les parties pour Gemini"""
    file_parts = []
    
    if uploaded_files:
        for uploaded_file in uploaded_files:
            try:
                # Lire les bytes du fichier
                file_bytes = uploaded_file.read()
                
                # Déterminer le type MIME basé sur l'extension
                file_extension = uploaded_file.name.lower().split('.')[-1]
                mime_type_map = {
                    'pdf': 'application/pdf',
                    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    'doc': 'application/msword',
                    'txt': 'text/plain',
                    'jpg': 'image/jpeg',
                    'jpeg': 'image/jpeg',
                    'png': 'image/png',
                    'gif': 'image/gif',
                    'bmp': 'image/bmp'
                }
                
                mime_type = mime_type_map.get(file_extension, 'application/octet-stream')
                
                # Créer une partie pour Gemini
                file_part = types.Part.from_bytes(
                    data=file_bytes,
                    mime_type=mime_type
                )
                file_parts.append(file_part)
                
                # Afficher les informations du fichier
                st.info(f"📁 Fichier traité : {uploaded_file.name} ({len(file_bytes)} bytes)")
                
            except Exception as e:
                st.error(f"❌ Erreur lors du traitement du fichier {uploaded_file.name}: {str(e)}")
    
    return file_parts

# Fonction pour générer la réponse
def generate_legal_response(chat_input_value):
    """Génère une réponse juridique en utilisant l'API Gemini"""
    try:
        # Chargement des variables d'environnement
        load_dotenv()
        
        # Vérification de la clé API
        api_key = os.environ.get("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY")
        if not api_key:
            st.error("❌ Clé API GEMINI_API_KEY non trouvée. Veuillez la configurer dans le fichier .env ou les secrets Streamlit.")
            return None
        
        # Initialisation du client
        client = genai.Client(api_key=api_key)
        model = "gemini-2.5-pro-preview-06-05"
        
        # Extraire le texte et les fichiers du chat_input
        if isinstance(chat_input_value, str):
            # Si c'est juste une string (exemple de question)
            question_text = chat_input_value
            uploaded_files = []
        else:
            # Si c'est un ChatInputValue avec potentiellement des fichiers
            question_text = chat_input_value.text if hasattr(chat_input_value, 'text') else str(chat_input_value)
            uploaded_files = chat_input_value.files if hasattr(chat_input_value, 'files') else []
        
        # Traiter les fichiers uploadés
        file_parts = process_uploaded_files(uploaded_files)
        
        # Construire les parties du contenu
        content_parts = []
        
        # Ajouter les fichiers en premier
        content_parts.extend(file_parts)
        
        # Ajouter le texte de la question
        content_parts.append(types.Part.from_text(text=question_text))
        
        # Configuration du contenu
        contents = [
            types.Content(
                role="user",
                parts=content_parts,
            ),
        ]
        
        # Configuration des outils
        tools = [
            types.Tool(url_context=types.UrlContext()),
            types.Tool(google_search=types.GoogleSearch()),
        ]
        
        # date d'aujourd'hui 
        today = time.strftime("%Y-%m-%d")
        # Configuration de génération
        generate_content_config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(
                thinking_budget=-1,
            ),
            tools=tools,
            response_mime_type="text/plain",
            system_instruction=[
                types.Part.from_text(text="""Votre Rôle : Vous êtes un assistant de recherche juridique IA de premier ordre. Votre mission est de simuler une recherche juridique exhaustive et de haute qualité, en fournissant des réponses rapides, fiables et précisément sourcées, à l'image des meilleures plateformes spécialisées.
Voici la date d'aujourd'hui : {today}
Votre Processus de Recherche Simulé :
Lorsque je vous pose une question, vous simulerez une recherche approfondie en consultant systématiquement les sources de référence du droit français et européen suivantes :
Sources Législatives et Réglementaires :
Les codes, lois et décrets consolidés sur Légifrance.
Sources Jurisprudentielles :
La jurisprudence de la Cour de cassation (ordres judiciaire).
La jurisprudence du Conseil d'État (ordre administratif).
Les décisions pertinentes des Cours d'appel.
Sources Doctrinales :
Les bases de données juridiques de premier plan comme Dalloz.fr, Lexis 360 et Lextenso.
Les articles de revues juridiques spécialisées (ex: Recueil Dalloz, Semaine Juridique - JCP).
Sources Institutionnelles et Pratiques :
Les fiches pratiques et les informations des sites gouvernementaux officiels comme service-public.fr et les sites des ministères.
Les analyses et commentaires publiés sur les blogs d'avocats ou d'universitaires reconnus pour leur expertise dans le domaine concerné.
Vos Principes de Réponse :
Clarté et Détails : Rédigez une réponse claire, précise et allant au détail (long). .
Fiabilité et Précision : Assurez-vous que chaque information est vérifiée à travers les sources simulées. Si une information est incertaine ou si les sources sont contradictoires, signalez-le explicitement. N'inventez jamais une réponse.
Sourçage Rigoureux : Citez systématiquement vos sources ( NUMERO ET DATE INCLUS si possible) pour chaque information clé. Utilisez le format [Source, Année] (ex: [Cour de cassation, 2e civ., 15 mai 2023], [Dalloz.fr, 2022]) ou une URL directe si elle est pertinente et stable. Si aucune source crédible n'a pu être identifiée, indiquez [Source indisponible].
Neutralité : Adoptez un ton neutre et factuel.
Format de Réponse Obligatoire :
Résumé :
Une explication bien structurée, synthétique et directe.
Citations :
[Nom de la source, Année]
[Lien direct si tu es sûr à plus de 95% de sa véracité et qu'il ne s'agit pas d'une jurisprudence]""".format(today=today)),
            ],
        )
        
        # Génération de la réponse avec estimation des coûts et extraction des citations
        response_text = ""
        estimated_web_searches = 2  # Estimation basée sur l'utilisation des outils de recherche
        citations = {}
        
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=generate_content_config,
        )
        
        # Extraire le texte de la réponse
        if response.text:
            response_text = response.text
        
        # Extraire les citations si disponibles
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'grounding_metadata'):
                citations = extract_citations(candidate)
        
        # Estimation des coûts
        # Extraire les tokens usage_metadata
                if (hasattr(response, 'usage_metadata') and 
                    response.usage_metadata is not None):
                    
                    usage = response.usage_metadata
                    input_tokens = getattr(usage, 'prompt_token_count', 0)
                    output_tokens = getattr(usage, 'candidates_token_count', 0)
        
        # Ajouter les tokens des fichiers (estimation approximative)
        for file_part in file_parts:
            input_tokens += 1000  # Estimation moyenne par fichier
        
        cost_info = estimate_cost(input_tokens, output_tokens, estimated_web_searches)
        
        # Mettre à jour le coût total de la session
        if 'total_session_cost' in st.session_state:
            st.session_state.total_session_cost += cost_info['total_cost']
        
        # Ajouter les citations à la réponse
        citations_display = format_citations(citations)
        
        # Ajouter les informations de coût à la réponse
        cost_display = f"""

---
        
### 💰 Coût estimé de cette requête :
- **Tokens d'entrée** : {cost_info['input_tokens']:,} tokens → ${cost_info['input_cost']:.4f}
- **Tokens de sortie** : {cost_info['output_tokens']:,} tokens → ${cost_info['output_cost']:.4f}
- **Recherches web** : {cost_info['web_searches']} recherche(s) → ${cost_info['search_cost']:.4f}
- **🏷️ Total estimé** : **${cost_info['total_cost']:.4f}**

        """
        
        # Construire la réponse finale avec citations et coûts
        final_response = response_text + citations_display + cost_display
        
        return final_response
        
    except Exception as e:
        st.error(f"❌ Erreur lors de la génération de la réponse : {str(e)}")
        return None

# Interface principale
def main():
    # En-tête
    st.markdown('<div class="main-header">⚖️ Assistant Juridique Français</div>', unsafe_allow_html=True)
    

    # Sidebar avec informations
    with st.sidebar:
        st.header("💰 Tarification")
        st.write("""
          **Coûts par requête :**
          - Input : **3$/M tokens**
          - Output : **15$/M tokens**
          - Recherche web : **0.035$/requête**
        
          *Coût moyen par question : ~0.04-0.1$*
        """)
        

        st.header("🔧 Configuration")
        if st.button("🔄 Effacer l'historique"):
            if 'chat_history' in st.session_state:
                st.session_state.chat_history = []
            if 'total_session_cost' in st.session_state:
                st.session_state.total_session_cost = 0.0
            st.rerun()
        
        st.header("📖 Exemples de questions")
        example_questions = [
            "Quels sont les délais de préavis pour un licenciement ?",
            "Comment créer une SAS ?",
            "Quelles sont les conditions pour un divorce par consentement mutuel ?",
            "Qu'est-ce que la légitime défense en droit pénal ?",
            "Comment contester une amende routière ?"
        ]
        
        for i, question in enumerate(example_questions):
            if st.button(f"📝 {question[:50]}...", key=f"example_{i}"):
                # Déclencher directement le traitement de l'exemple
                with st.spinner("🔍 Recherche et analyse en cours..."):
                    # Ajouter la question à l'historique
                    st.session_state.chat_history.append({
                        'type': 'question',
                        'content': question,
                        'timestamp': time.time()
                    })
                    
                    # Générer la réponse
                    response = generate_legal_response(question)
                    
                    if response:
                        # Ajouter la réponse à l'historique
                        st.session_state.chat_history.append({
                            'type': 'response',
                            'content': response,
                            'timestamp': time.time()
                        })
                        
                        st.rerun()

    # Zone de saisie avec chat_input
    user_question = st.chat_input(
        "💬 Posez votre question juridique...",
        key="chat_input",
        accept_file=True,
        file_type=["pdf","txt"]
    )
        
    # Gestion de l'historique des conversations
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    
    # Initialiser le coût total de session
    if 'total_session_cost' not in st.session_state:
        st.session_state.total_session_cost = 0.0
    
    # Traitement de la question via chat_input
    if user_question:
        with st.spinner("🔍 Recherche et analyse en cours..."):
            # Extraire le texte pour l'affichage dans l'historique
            if isinstance(user_question, str):
                display_text = user_question
            else:
                display_text = user_question.text if hasattr(user_question, 'text') else str(user_question)
                # Afficher les fichiers uploadés
                if hasattr(user_question, 'files') and user_question.files:
                    files_info = f" [📁 {len(user_question.files)} fichier(s) joint(s)]"
                    display_text += files_info
            
            # Ajouter la question à l'historique
            st.session_state.chat_history.append({
                'type': 'question',
                'content': display_text,
                'timestamp': time.time()
            })
            
            # Générer la réponse
            response = generate_legal_response(user_question)
            
            if response:
                # Ajouter la réponse à l'historique
                st.session_state.chat_history.append({
                    'type': 'response',
                    'content': response,
                    'timestamp': time.time()
                })
                
                st.rerun()
    
    # Affichage de l'historique des conversations
    if st.session_state.chat_history:
        
        # Afficher le coût total de la session
        if st.session_state.total_session_cost > 0:
            st.info(f"💰 **Coût total de la session : ${st.session_state.total_session_cost:.4f}**")
        
        
        # Afficher les conversations de la plus récente à la plus ancienne
        for i in range(len(st.session_state.chat_history) - 1, -1, -1):
            item = st.session_state.chat_history[i]
            
            if item['type'] == 'question':
                st.markdown(f"**❓ Question :** {item['content']}")
            else:  # response
                st.markdown("**🤖 Réponse :**")
                st.markdown(item['content'])
                st.markdown('</div>', unsafe_allow_html=True)
                st.markdown("---")

# Configuration de la clé API
def setup_api_key():
    st.sidebar.header("🔑 Configuration API")
    
    # Charger les variables d'environnement
    load_dotenv()
    
    # Vérifier si la clé API est déjà configurée
    if not (os.environ.get("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY")):
        st.sidebar.warning("⚠️ Clé API Gemini requise")
        st.sidebar.info("💡 Créez un fichier `.env` avec : `GEMINI_API_KEY=votre_clé`")
        
        # Option pour saisir la clé API via l'interface
        api_key_input = st.sidebar.text_input(
            "Saisissez votre clé API Gemini :",
            type="password",
            help="Vous pouvez obtenir une clé API sur https://ai.google.dev/"
        )
        
        if api_key_input:
            os.environ["GEMINI_API_KEY"] = api_key_input
            st.sidebar.success("✅ Clé API configurée avec succès !")
    else:
        st.sidebar.success("✅ Clé API configurée")

if __name__ == "__main__":
    setup_api_key()
    main()