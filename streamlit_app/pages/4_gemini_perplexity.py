import streamlit as st
import asyncio
import os
from pathlib import Path
import tempfile
from datetime import datetime
from features.router.router import LegalRouter

# Import pour la gestion des coûts (selon votre système)
from costs_manager.cost import calculate_cost, display_cost, COSTS

# ========== FONCTIONS DE COÛTS ADAPTÉES POUR STREAMLIT ==========

def add_cost_to_session(model, input_tokens=0, output_tokens=0, searches=0):
    """Ajoute un coût à la session Streamlit"""
    cost_info = calculate_cost(model, input_tokens, output_tokens, searches)
    
    if "error" not in cost_info:
        if 'session_costs' not in st.session_state:
            st.session_state.session_costs = []
        st.session_state.session_costs.append(cost_info)
        return cost_info
    return None

def get_session_total():
    """Retourne le détail complet des coûts de session pour Streamlit"""
    if 'session_costs' not in st.session_state or not st.session_state.session_costs:
        return None
    
    session_costs = st.session_state.session_costs
    
    # Calcul des totaux
    total_cost = sum(cost["total_cost"] for cost in session_costs)
    total_input_tokens = sum(cost["input_tokens"] for cost in session_costs)
    total_output_tokens = sum(cost["output_tokens"] for cost in session_costs)
    total_tokens = total_input_tokens + total_output_tokens
    total_searches = sum(cost["searches"] for cost in session_costs)
    
    # Grouper par modèle
    by_model = {}
    for cost in session_costs:
        model = cost["model"]
        if model not in by_model:
            by_model[model] = {
                "cost": 0.0,
                "calls": 0,
                "tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "searches": 0
            }
        
        by_model[model]["cost"] += cost["total_cost"]
        by_model[model]["calls"] += 1
        by_model[model]["tokens"] += cost["input_tokens"] + cost["output_tokens"]
        by_model[model]["input_tokens"] += cost["input_tokens"]
        by_model[model]["output_tokens"] += cost["output_tokens"]
        by_model[model]["searches"] += cost["searches"]
    
    return {
        "total_cost": total_cost,
        "total_tokens": total_tokens,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_searches": total_searches,
        "total_calls": len(session_costs),
        "by_model": by_model
    }

def clear_session_costs():
    """Remet à zéro les coûts de session"""
    if 'session_costs' in st.session_state:
        st.session_state.session_costs = []

def get_session_costs_count():
    """Retourne le nombre d'interactions avec coûts"""
    if 'session_costs' not in st.session_state:
        return 0
    return len(st.session_state.session_costs)

# Configuration de la page
st.set_page_config(
    page_title="🏛️ Assistant Juridique",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personnalisé pour améliorer l'apparence
st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 2rem 0;
        background: linear-gradient(90deg, #1e3a8a, #3b82f6);
        color: white;
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    
    .doc-info {
        background-color: #ecfdf5;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #10b981;
        margin-bottom: 1rem;
    }
    
    .warning-box {
        background-color: #fef3c7;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #f59e0b;
        margin: 1rem 0;
    }
    
    .response-box {
        background-color: #f8fafc;
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 4px solid #3b82f6;
        margin: 1rem 0;
    }
    
    .classification-box {
        background-color: #ede9fe;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #8b5cf6;
        margin: 1rem 0;
    }
    
    .cost-box {
        background-color: #f0fdf4;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #22c55e;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Initialisation du session state
def init_session_state():
    if 'router' not in st.session_state:
        st.session_state.router = LegalRouter()
    if 'current_document' not in st.session_state:
        st.session_state.current_document = None
    if 'questions_history' not in st.session_state:
        st.session_state.questions_history = []
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    if 'last_response' not in st.session_state:
        st.session_state.last_response = None
    if 'last_classification' not in st.session_state:
        st.session_state.last_classification = None
    if 'session_costs' not in st.session_state:
        st.session_state.session_costs = []

# Fonction pour traiter l'upload de fichier
def handle_file_upload(uploaded_file):
    if uploaded_file is not None:
        # Créer un fichier temporaire
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{uploaded_file.name}") as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_path = tmp_file.name
        
        st.session_state.current_document = tmp_path
        st.session_state.router.current_document = tmp_path
        return tmp_path
    return None

# Fonction asynchrone pour traiter les questions
async def process_question_async(question, document_path=None):
    try:
        # Votre router gère déjà les coûts automatiquement
        response = await st.session_state.router.process_question(question, document_path)
        
        # Récupérer la classification si disponible
        classification = getattr(st.session_state.router, 'last_classification', None)
        
        # TODO: Intégrer ici la récupération des métriques de coût depuis votre router
        # Exemple d'utilisation (vous devrez adapter selon votre router):
        # if hasattr(st.session_state.router, 'last_cost_info'):
        #     cost_info = st.session_state.router.last_cost_info
        #     add_cost_to_session(
        #         model=cost_info.get('model', 'unknown'),
        #         input_tokens=cost_info.get('input_tokens', 0),
        #         output_tokens=cost_info.get('output_tokens', 0),
        #         searches=cost_info.get('searches', 0)
        #     )
        
        return response, classification
    except Exception as e:
        st.error(f"Erreur lors du traitement: {e}")
        return None, None

# Interface principale
def main():
    init_session_state()
    
    # En-tête principal
    st.markdown("""
    <div class="main-header">
        <h1>🏛️ ASSISTANT JURIDIQUE</h1>
        <p>Votre assistant intelligent pour l'analyse juridique</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar pour la gestion des documents
    with st.sidebar:
        st.header("📁 Document Actuel")
        
        # Informations sur le document actuel
        if st.session_state.current_document:
            st.markdown(f"""
            <div class="doc-info">
                <strong>📄 Document actuel:</strong><br>
                {os.path.basename(st.session_state.current_document)}
            </div>
            """, unsafe_allow_html=True)
            
            if st.button("🗑️ Supprimer le document"):
                # Nettoyer le fichier temporaire
                if os.path.exists(st.session_state.current_document):
                    os.unlink(st.session_state.current_document)
                st.session_state.current_document = None
                st.session_state.router.current_document = None
                st.success("Document supprimé")
                st.rerun()
        else:
            st.info("📄 Aucun document chargé\n\nUtilisez le chat pour uploader un fichier PDF ou TXT")
        
        st.divider()
        
        # Statistiques de session
        st.header("📊 Session")
        
        if st.session_state.questions_history:
            st.metric("Questions posées", len(st.session_state.questions_history))
            
            if st.session_state.current_document:
                st.metric("Document", os.path.basename(st.session_state.current_document))
            else:
                st.metric("Mode", "Sans document")
        else:
            st.info("💡 Posez votre première question pour voir les statistiques")
        
        st.divider()
        
        # Coûts de la session
        st.header("💰 Coûts de Session")
        
        # Debug: Afficher le contenu brut de session_costs
        if st.checkbox("🔍 Mode Debug", help="Affiche les données brutes de coûts"):
            st.write("**Debug - session_costs:**", st.session_state.get('session_costs', []))
            st.write("**Debug - nombre d'entrées:**", len(st.session_state.get('session_costs', [])))
        
        try:
            session_total = get_session_total()
            
            # Debug: Afficher ce que retourne get_session_total()
            if st.session_state.get('session_costs', []):
                st.write(f"🔍 Debug session_total: {session_total}")
            
            if session_total and session_total.get('total_cost', 0) > 0:
                col1, col2 = st.columns(2)
                
                with col1:
                    st.metric("Coût Total", f"${session_total['total_cost']:.4f}")
                    st.metric("Interactions", session_total['total_calls'])
                
                with col2:
                    st.metric("Tokens Total", f"{session_total['total_tokens']:,}")
                    st.metric("Recherches", session_total['total_searches'])
                    
                # Coût moyen par question
                if len(st.session_state.questions_history) > 0:
                    avg_cost = session_total['total_cost'] / len(st.session_state.questions_history)
                    st.metric("Coût/Question", f"${avg_cost:.4f}")
                
                # Détail des coûts par modèle
                with st.expander("💳 Détail par modèle"):
                    if session_total.get('by_model'):
                        for model, data in session_total['by_model'].items():
                            st.write(f"**{model.upper()}:**")
                            st.write(f"  • Coût: ${data['cost']:.4f}")
                            st.write(f"  • Appels: {data['calls']}")
                            st.write(f"  • Tokens: {data['tokens']:,}")
                            if data['searches'] > 0:
                                st.write(f"  • Recherches: {data['searches']}")
                            st.write("---")
                
                # Détail des tokens
                with st.expander("🎯 Détail des tokens"):
                    st.write(f"**Tokens d'entrée:** {session_total['total_input_tokens']:,}")
                    st.write(f"**Tokens de sortie:** {session_total['total_output_tokens']:,}")
                    st.write(f"**Total:** {session_total['total_tokens']:,}")
                    
            else:
                st.info("💡 Les coûts s'afficheront après votre première question")
                
                # Afficher les tarifs disponibles
                with st.expander("📋 Tarifs par modèle"):
                    for model, pricing in COSTS.items():
                        st.write(f"**{model.upper()}:**")
                        st.write(f"  • Input: ${pricing['input']}/M tokens")
                        st.write(f"  • Output: ${pricing['output']}/M tokens")
                        st.write(f"  • Recherche: ${pricing['search']}/recherche")
                        st.write("---")
                
        except Exception as e:
            st.error(f"Erreur dans l'affichage des coûts: {e}")
            if st.session_state.questions_history:
                st.metric("Questions posées", len(st.session_state.questions_history))
                st.warning("📊 Données de coûts temporairement indisponibles")
        
        # Boutons de gestion
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Réinitialiser"):
                # Nettoyer le fichier temporaire si il existe
                if st.session_state.current_document and os.path.exists(st.session_state.current_document):
                    os.unlink(st.session_state.current_document)
                
                # Réinitialiser seulement les données nécessaires
                st.session_state.current_document = None
                st.session_state.questions_history = []
                st.session_state.last_response = None
                st.session_state.last_classification = None
                st.session_state.processing = False
                clear_session_costs()
                
                # Réinitialiser le router
                st.session_state.router = LegalRouter()
                
                st.success("Session réinitialisée")
                st.rerun()
        
        with col2:
            if st.button("💰 Effacer coûts"):
                clear_session_costs()
                st.success("Coûts effacés")
                st.rerun()
    
    # Zone principale
    
    # Zone de contexte
    if st.session_state.current_document:
        st.markdown(f"""
        <div class="doc-info">
            <strong>📄 Contexte actuel:</strong> {os.path.basename(st.session_state.current_document)}<br>
            <em>💡 Votre question sera analysée avec ce document</em>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="warning-box">
            <strong>🔍 Mode recherche sans document</strong><br>
            <em>💡 Votre question sera classifiée automatiquement</em>
        </div>
        """, unsafe_allow_html=True)
    
    # Affichage de la dernière réponse et classification
    if st.session_state.last_response:
        st.markdown("### 📋 Réponse")
        st.markdown(f"""
        <div class="response-box">
            {st.session_state.last_response}
        </div>
        """, unsafe_allow_html=True)
    
    if st.session_state.last_classification:
        st.markdown("### 🏷️ Classification")
        st.markdown(f"""
        <div class="classification-box">
            <strong>Type de question:</strong> {st.session_state.last_classification}
        </div>
        """, unsafe_allow_html=True)
    
    # Chat input pour les questions avec upload de fichiers
    user_question = st.chat_input(
        "💬 Posez votre question juridique...",
        key="chat_input",
        accept_file=True,
        file_type=["pdf","txt"]
    )
    
    # Traitement des questions et fichiers
    if user_question and not st.session_state.processing:
        st.session_state.processing = True
        
        # Gérer les fichiers uploadés via chat_input
        if hasattr(user_question, 'files') and user_question.files:
            uploaded_file = user_question.files[0]  # Prendre le premier fichier
            doc_path = handle_file_upload(uploaded_file)
            if doc_path:
                st.success(f"✅ Document chargé: {uploaded_file.name}")
        
        # Extraire le texte de la question
        question_text = user_question.text if hasattr(user_question, 'text') else user_question
        
        with st.spinner("🔄 Analyse en cours..."):
            # Utiliser asyncio pour traiter la question
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                response, classification = loop.run_until_complete(
                    process_question_async(question_text, st.session_state.current_document)
                )
                
                if response:
                    # Sauvegarder la réponse et classification
                    st.session_state.last_response = response
                    st.session_state.last_classification = classification
                    
                    # Ajouter à l'historique
                    st.session_state.questions_history.append({
                        'question': user_question,
                        'response': response,
                        'classification': classification,
                        'document': os.path.basename(st.session_state.current_document) if st.session_state.current_document else "Aucun",
                        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                    
                    st.success("✅ Analyse terminée!")
                else:
                    st.error("❌ Erreur lors de l'analyse")
                
            except Exception as e:
                st.error(f"❌ Erreur: {e}")
            finally:
                loop.close()
                st.session_state.processing = False
                st.rerun()
    
    # Affichage de l'historique des questions
    if st.session_state.questions_history:
        st.header("📚 Historique des Questions")
        
        # Afficher les 5 dernières questions
        for i, entry in enumerate(reversed(st.session_state.questions_history[-5:]), 1):
            question_num = len(st.session_state.questions_history) - i + 1
            with st.expander(f"Question {question_num}: {entry['question'][:50]}..."):
                st.write(f"**Question:** {entry['question']}")
                if entry.get('response'):
                    st.write(f"**Réponse:** {entry['response'][:300]}...")
                if entry.get('classification'):
                    st.write(f"**Classification:** {entry['classification']}")
                st.write(f"**Document utilisé:** {entry['document']}")
                st.write(f"**Timestamp:** {entry['timestamp']}")
        
        if len(st.session_state.questions_history) > 5:
            st.info(f"📝 {len(st.session_state.questions_history) - 5} autres questions dans l'historique complet")
    
    # Footer
    st.divider()
    st.markdown("""
    <div style='text-align: center; color: #6b7280; padding: 1rem;'>
        🏛️ Assistant Juridique - Développé avec Streamlit<br>
        <em>Pour une utilisation professionnelle, consultez toujours un avocat qualifié</em>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()