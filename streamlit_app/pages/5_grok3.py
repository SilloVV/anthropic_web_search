"""
Application Streamlit pour l'Assistant Juridique Grok-3

Ce module fournit une interface web interactive permettant aux utilisateurs
de poser des questions juridiques à Grok-3 et de visualiser les réponses
dans un format de chat convivial avec streaming en temps réel.

Auteur: NAKIB Wassil
Version: 0.2 - Adapté pour le streaming Grok
Date: 2025-06-26
"""

import streamlit as st
import sys
import os

# Ajouter le dossier grok3 au path Python
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
grok3_dir = os.path.join(parent_dir, 'grok3')
sys.path.insert(0, grok3_dir)

# Import simple maintenant que le path est ajouté
from grok3.grok3_utils import call_grok

import time
from typing import Any, List, Dict, Optional


# ================================
# CONFIGURATION ET CONSTANTES
# ================================

PAGE_CONFIG = {
    "page_title": "Assistant Juridique Grok-3",
    "page_icon": "⚖️",
    "layout": "wide"
}

CUSTOM_CSS = """
<style>
    .stTextArea textarea {
        font-size: 16px;
        border-radius: 10px;
    }
    
    .stButton button {
        font-weight: bold;
        border-radius: 10px;
    }
    
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    
    .user-message {
        background-color: #e8f4fd;
    }
    
    .assistant-message {
        background-color: #f0f8f0;
    }
    
    .legal-highlight {
        background-color: #fff3cd;
        border-left: 4px solid #ffc107;
        padding: 0.5rem;
        margin: 0.5rem 0;
    }
    
    .streaming-indicator {
        color: #1f77b4;
        font-style: italic;
    }
    
    .metrics-container {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 10px;
        margin: 10px 0;
    }
</style>
"""

AVAILABLE_MODELS = {
    "Grok-3 Latest (Recommandé)": "grok-3-latest",
    "Grok-3 Mini": "grok-3-mini", 
    "Grok-3 Fast": "grok-3-fast",
    "Grok-3 Mini Fast": "grok-3-mini-fast"
}

# Dictionnaire des coûts par modèle (prix par million de tokens)
MODEL_COSTS = {
    "grok-3-latest": {"input_cost": 3.00, "output_cost": 15.00},
    "grok-3-mini": {"input_cost": 0.30, "output_cost": 0.50},
    "grok-3-fast": {"input_cost": 5.00, "output_cost": 25.00},
    "grok-3-mini-fast": {"input_cost": 0.60, "output_cost": 4.00}
}

MODEL = "grok-3-latest"  # Variable globale pour le modèle actuel

# ================================
# FONCTIONS DE COÛT
# ================================

def calculate_tokens_from_chars(char_count: int) -> int:
    """Calcule le nombre de tokens basé sur le nombre de caractères (1 token = 5 chars)."""
    return max(1, char_count // 5)

def calculate_cost_from_chars(input_chars: int, output_chars: int, model_code: str) -> float:
    """Calcule le coût basé sur le nombre de caractères."""
    if model_code not in MODEL_COSTS:
        return 0.0
    
    input_tokens = calculate_tokens_from_chars(input_chars)
    output_tokens = calculate_tokens_from_chars(output_chars)
    
    cost_info = MODEL_COSTS[model_code]
    input_cost = (input_tokens / 1_000_000) * cost_info['input_cost']
    output_cost = (output_tokens / 1_000_000) * cost_info['output_cost']
    
    return input_cost + output_cost

# ================================
# FONCTIONS DE CONFIGURATION
# ================================

def configure_streamlit_page() -> None:
    """Configure les paramètres de base de la page Streamlit."""
    st.set_page_config(**PAGE_CONFIG)

def apply_custom_styling() -> None:
    """Applique le CSS personnalisé à l'interface Streamlit."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ================================
# FONCTIONS D'INITIALISATION
# ================================

def initialize_session_state() -> None:
    """Initialise les variables de session Streamlit nécessaires."""
    if 'conversation_history' not in st.session_state:
        st.session_state.conversation_history = []
    
    if 'current_query' not in st.session_state:
        st.session_state.current_query = ""
    
    if 'uploaded_files' not in st.session_state:
        st.session_state.uploaded_files = []
    
    if 'last_response_metrics' not in st.session_state:
        st.session_state.last_response_metrics = None

# ================================
# FONCTIONS D'INTERFACE UTILISATEUR
# ================================

def render_page_header() -> None:
    """Affiche l'en-tête principal de la page."""
    st.title("⚖️ Assistant Juridique Grok-3")
    st.markdown("*Posez vos questions juridiques à un expert IA avec streaming en temps réel*")
    st.markdown("---")

def render_sidebar_information() -> None:
    """Affiche les informations et instructions dans la barre latérale."""
    global MODEL
    
    with st.sidebar:
        st.header("ℹ️ Informations sur l'Assistant")
        
        # Sélecteur de modèle
        selected_model_name = st.selectbox(
            "🔧 Sélectionnez le modèle Grok à utiliser :",
            options=list(AVAILABLE_MODELS.keys()),
            index=0,
            key="model_selector"
        )
        
        # Vérifier si le modèle a changé et déclencher rerun
        new_model = AVAILABLE_MODELS[selected_model_name]
        if new_model != MODEL:
            MODEL = new_model
            st.success(f"✅ Modèle changé vers: **{MODEL}**")
            st.rerun()
        
        # Mettre à jour la variable MODEL
        MODEL = new_model
        
        # Informations sur le modèle
        st.markdown(f"**🔧 Modèle utilisé :** {MODEL}")
        st.markdown("**⚖️ Spécialité :** Droit et questions juridiques")
        st.markdown("**🔄 Mode :** Streaming temps réel")
        
        # Affichage des coûts du modèle sélectionné
        if MODEL in MODEL_COSTS:
            cost_info = MODEL_COSTS[MODEL]
            with st.expander("💰 Tarifs du modèle", expanded=False):
                st.write(f"• **Entrée:** ${cost_info['input_cost']:.2f} / million tokens")
                st.write(f"• **Sortie:** ${cost_info['output_cost']:.2f} / million tokens")
                st.caption("💡 *1 token ≈ 5 caractères*")
        
        # Métriques de la dernière réponse
        if st.session_state.last_response_metrics:
            st.header("📊 Dernières Métriques")
            metrics = st.session_state.last_response_metrics
            
            st.metric("Caractères", metrics.get('chars_count', 0))
            st.metric("Citations", metrics.get('citations_count', 0))
            
            # Affichage du coût si disponible
            if 'question_cost' in metrics:
                st.metric("💰 Coût Question", f"${metrics['question_cost']:.6f}")
            
            if metrics.get('citations'):
                with st.expander("🔗 Citations"):
                    for i, citation in enumerate(metrics['citations'][:5], 1):
                        st.write(f"{i}. {citation[:100]}...")

def render_conversation_display() -> None:
    """Affiche l'historique de conversation dans un format chat."""
    if st.session_state.conversation_history:
        for message in st.session_state.conversation_history:
            display_single_message(message)

def handle_chat_input() -> None:
    """Gère l'entrée de chat utilisateur et traite les messages."""
    # Utiliser la query stockée en session si disponible
    default_value = st.session_state.current_query
    
    user_input = st.chat_input(
        placeholder="Posez votre question juridique ici...",
        key="legal_chat_input"
    )
    
    # Si on a une query en session, l'utiliser et la nettoyer
    if st.session_state.current_query and not user_input:
        user_input = st.session_state.current_query
        st.session_state.current_query = ""
    
    if user_input:
        handle_user_query_submission(user_input)

# ================================
# FONCTIONS DE GESTION DES MESSAGES
# ================================

def add_message_to_history(role: str, content: str, metadata: Optional[Dict] = None) -> None:
    """Ajoute un message à l'historique de conversation."""
    message = {
        "role": role,
        "content": content,
        "timestamp": time.strftime("%H:%M:%S"),
        "metadata": metadata or {}
    }
    st.session_state.conversation_history.append(message)

def clear_conversation_history() -> None:
    """Efface complètement l'historique de conversation."""
    st.session_state.conversation_history = []
    st.session_state.last_response_metrics = None

def display_single_message(message: Dict[str, Any]) -> None:
    """Affiche un message individuel dans l'interface chat."""
    role_emoji = "👤" if message["role"] == "user" else "⚖️"
    role_name = "Vous" if message["role"] == "user" else "Assistant Juridique"
    
    with st.chat_message(message["role"]):
        st.markdown(f"**{role_emoji} {role_name}** - {message['timestamp']}")
        st.markdown(message["content"])
        
        # Afficher les métadonnées si disponibles
        if message.get("metadata") and message["role"] == "assistant":
            metadata = message["metadata"]
            if metadata.get("citations_count", 0) > 0:
                st.caption(f"📚 {metadata['citations_count']} citations trouvées")

def render_conversation_controls() -> None:
    """Affiche les contrôles de gestion de conversation."""
    if st.session_state.conversation_history:
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            if st.button("🗑️ Effacer l'historique", type="secondary"):
                clear_conversation_history()
                st.rerun()
        
        with col2:
            if st.button("📄 Exporter la conversation", type="secondary"):
                export_conversation_history()

def export_conversation_history() -> None:
    """Exporte l'historique de conversation en format texte."""
    if not st.session_state.conversation_history:
        st.warning("Aucune conversation à exporter.")
        return
    
    export_text = "=== HISTORIQUE CONVERSATION ASSISTANT JURIDIQUE ===\n\n"
    
    for message in st.session_state.conversation_history:
        role_name = "UTILISATEUR" if message["role"] == "user" else "ASSISTANT"
        export_text += f"[{message['timestamp']}] {role_name}:\n"
        export_text += f"{message['content']}\n\n"
        export_text += "-" * 50 + "\n\n"
    
    st.download_button(
        label="💾 Télécharger l'historique",
        data=export_text,
        file_name=f"conversation_juridique_{time.strftime('%Y%m%d_%H%M%S')}.txt",
        mime="text/plain"
    )

# ================================
# FONCTIONS DE TRAITEMENT GROK-3
# ================================

def enhance_user_query(query: str, has_file: bool = False) -> str:
    """Améliore la query utilisateur avec du contexte juridique."""
    if has_file:
        enhanced_query = f"""
CONTEXTE: Question juridique avec document joint.
QUESTION: {query}

Veuillez analyser cette question juridique en tenant compte du document fourni.
Donnez une réponse détaillée et structurée avec :
1. Une analyse claire de la situation
2. Les références légales pertinentes
3. Les implications pratiques
4. Les conseils d'action si approprié
"""
    else:
        enhanced_query = f"""
CONTEXTE: Question juridique.
QUESTION: {query}

Veuillez fournir une réponse juridique claire et détaillée avec :
1. Une explication du cadre juridique applicable
2. Les références légales pertinentes
3. Les implications et conséquences
4. Des conseils pratiques si approprié
"""
    
    return enhanced_query

def handle_user_query_submission(query: str) -> None:
    """Gère la soumission d'une question utilisateur avec streaming."""
    if not query.strip():
        st.warning("⚠️ Veuillez entrer une question avant d'envoyer.")
        return
    
    # Calculer le coût de la question
    question_cost = calculate_cost_from_chars(len(query), 0, MODEL)
    
    # Vérification de fichiers joints
    has_uploaded_file = bool(st.session_state.uploaded_files)
    
    # Ajout de la question utilisateur à l'historique
    display_query = query
    if has_uploaded_file:
        file_name = st.session_state.uploaded_files[0].name
        display_query += f"\n\n📄 *Document joint: {file_name}*"
    
    add_message_to_history("user", display_query)
    
    # Affichage de la question utilisateur
    display_single_message({
        "role": "user", 
        "content": display_query,
        "timestamp": time.strftime("%H:%M:%S"),
        "metadata": {}
    })
    
    # Préparation de la requête améliorée
    enhanced_query = enhance_user_query(query, has_uploaded_file)
    
    # Streaming avec Grok-3
    with st.chat_message("assistant"):
        st.markdown(f"**⚖️ Assistant Juridique** - {time.strftime('%H:%M:%S')}")
        
        # Container pour le streaming
        response_container = st.empty()
        status_container = st.empty()
        complete_response = ""
        final_result = None
        
        try:
            # Streaming en temps réel avec le générateur
            with st.spinner("🤖 Génération de la réponse en cours..."):
                for item in call_grok(MODEL, enhanced_query):
                    if isinstance(item, dict):
                        # C'est le résultat final
                        if item.get("type") == "final_result":
                            final_result = item
                            status_container.markdown("✅ *Réponse générée avec succès*")
                            break
                        elif item.get("type") == "error":
                            # Gestion d'erreur
                            error_msg = f"❌ Erreur: {item['message']}"
                            response_container.error(error_msg)
                            status_container.empty()
                            add_message_to_history("assistant", error_msg)
                            return
                    else:
                        # C'est un chunk de texte
                        complete_response += item
                        response_container.markdown(complete_response)
            
            # Nettoyage du statut
            status_container.empty()
            
            # Traitement du résultat final
            if final_result:
                # Calculer le coût total de la conversation
                total_cost = calculate_cost_from_chars(len(enhanced_query), len(complete_response), MODEL)
                
                # Stocker les métriques pour la sidebar
                st.session_state.last_response_metrics = {
                    'chars_count': len(complete_response),
                    'citations_count': len(final_result.get('citations', [])),
                    'citations': final_result.get('citations', []),
                    'question_cost': total_cost  # Coût total de la conversation
                }
                
                # Affichage du coût
                st.info(f"💰 **Coût de cette conversation:** ${total_cost:.6f}")
                
                # Affichage des métriques en bas de la réponse
                if final_result.get('citations'):
                    with st.expander(f"📚 Citations trouvées ({len(final_result['citations'])})", expanded=False):
                        for i, citation in enumerate(final_result['citations'], 1):
                            st.write(f"{i}. {citation}")
                
                # Ajout à l'historique avec métadonnées
                metadata = {
                    'citations_count': len(final_result.get('citations', [])),
                    'chars_count': len(complete_response)
                }
                add_message_to_history("assistant", complete_response, metadata)
            else:
                # Pas de résultat final reçu
                add_message_to_history("assistant", complete_response)
                
        except Exception as error:
            error_msg = f"❌ Erreur lors du streaming: {str(error)}"
            response_container.error(error_msg)
            status_container.empty()
            add_message_to_history("assistant", error_msg)

# ================================
# FONCTION UTILITAIRE
# ================================

def render_application_footer() -> None:
    """Affiche le pied de page de l'application."""
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: #666; padding: 20px;'>
            ⚖️ Propulsé par <strong>Grok-3</strong> | 
            🎨 Interface <strong>Streamlit</strong> | 
            📚 Assistant Juridique Intelligent | 
            🔄 <strong>Streaming Temps Réel</strong>
        </div>
        """, 
        unsafe_allow_html=True
    )

# ================================
# FONCTION PRINCIPALE
# ================================

def main() -> None:
    """Fonction principale de l'application Streamlit."""
    # Configuration et initialisation
    configure_streamlit_page()
    apply_custom_styling()
    initialize_session_state()
    
    # Rendu de l'interface
    render_page_header()
    render_sidebar_information()
    
    # Affichage de la conversation existante
    render_conversation_display()
    
    # Gestion de l'entrée chat
    handle_chat_input()
    
    # Contrôles de conversation
    render_conversation_controls()
    
    # Pied de page
    render_application_footer()

# ================================
# POINT D'ENTRÉE
# ================================

if __name__ == "__main__":
    main()