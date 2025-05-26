import streamlit as st
import pandas as pd
from dotenv import load_dotenv
import os
from datetime import datetime

# Firebase imports
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    st.error("❌ Firebase non installé. Installez avec: pip install firebase-admin")

# Chargement des variables d'environnement
load_dotenv()

# Configuration de la page
st.set_page_config(
    page_title="Votes des Modèles IA",
    page_icon="📊",
    layout="wide"
)

# ==================== FIREBASE CONFIGURATION ====================

@st.cache_resource
def init_firebase():
    """Initialise la connexion Firebase"""
    if not FIREBASE_AVAILABLE:
        return None
    
    try:
        if firebase_admin._apps:
            return firestore.client()
        
        cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
        project_id = os.getenv("FIREBASE_PROJECT_ID")
        
        if not cred_path or not os.path.exists(cred_path):
            st.error(f"❌ Fichier credentials Firebase introuvable : {cred_path}")
            return None
        
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred, {'projectId': project_id})
        
        return firestore.client()
    
    except Exception as e:
        st.error(f"❌ Erreur d'initialisation Firebase : {str(e)}")
        return None

@st.cache_data(ttl=60)  # Cache pendant 1 minute
def load_all_votes(_db):
    """Charge tous les votes depuis Firebase"""
    if not _db:
        return []
    
    try:
        docs = _db.collection('votes').stream()
        votes = []
        
        for doc in docs:
            data = doc.to_dict()
            votes.append(data)
        
        return votes
    
    except Exception as e:
        st.error(f"❌ Erreur chargement votes : {str(e)}")
        return []

def calculate_model_stats(votes_df):
    """Calcule les statistiques par modèle"""
    if votes_df.empty:
        return pd.DataFrame()
    
    # Obtenir tous les modèles
    all_models = set()
    for _, row in votes_df.iterrows():
        all_models.add(row['model_left'])
        all_models.add(row['model_right'])
    
    stats = []
    
    for model in sorted(all_models):
        # Victoires (quand ce modèle est choisi)
        victoires = len(votes_df[votes_df['vote'] == model])
        
        # Participations (matches où le modèle était présent)
        participations = len(votes_df[
            (votes_df['model_left'] == model) | 
            (votes_df['model_right'] == model)
        ])
        
        # Égalités
        egalites = len(votes_df[
            ((votes_df['model_left'] == model) | (votes_df['model_right'] == model)) &
            (votes_df['vote'] == 'tie')
        ])
        
        # Défaites
        defaites = participations - victoires - egalites
        
        # Pourcentages
        taux_victoire = (victoires / participations * 100) if participations > 0 else 0
        
        stats.append({
            'Modèle': model,
            'Victoires': victoires,
            'Défaites': defaites,
            'Égalités': egalites,
            'Total': participations,
            'Taux de victoire': f"{taux_victoire:.1f}%"
        })
    
    return pd.DataFrame(stats).sort_values('Victoires', ascending=False)

# ==================== INTERFACE ====================

st.title("📊 Votes des Modèles IA")
st.markdown("Tableau récapitulatif des performances")

# Initialiser Firebase
if FIREBASE_AVAILABLE:
    db = init_firebase()
    
    if db:
        # Bouton actualiser
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("🔄 Actualiser"):
                st.cache_data.clear()
                st.rerun()
        
        with col2:
            st.info("💡 Données mises à jour toutes les minutes")
        
        # Charger les données
        with st.spinner("📥 Chargement..."):
            votes_data = load_all_votes(db)
        
        if votes_data:
            votes_df = pd.DataFrame(votes_data)
            
            # ==================== MÉTRIQUES RAPIDES ====================
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("🗳️ Total votes", len(votes_df))
            
            with col2:
                st.metric("👥 Utilisateurs", votes_df['user_session_id'].nunique())
            
            with col3:
                égalités = len(votes_df[votes_df['vote'] == 'tie'])
                st.metric("⚖️ Égalités", égalités)
            
            with col4:
                # Modèle en tête
                stats_df = calculate_model_stats(votes_df)
                if not stats_df.empty:
                    leader = stats_df.iloc[0]['Modèle']
                    st.metric("🥇 Leader", leader)
            
            st.markdown("---")
            
            # ==================== TABLEAU PRINCIPAL ====================
            
            st.header("🏆 Classement des modèles")
            
            if not stats_df.empty:
                # Styler le tableau
                def highlight_leader(s):
                    styles = []
                    for i in range(len(s)):
                        if i == 0:  # Premier rang (leader)
                            styles.append('background-color: #28a745; color: black; font-weight: bold')
                        else:
                            styles.append('')
                    return styles
                
                # Afficher le tableau avec style
                styled_df = stats_df.style.apply(highlight_leader, axis=0)
                
                st.dataframe(
                    styled_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Modèle": st.column_config.TextColumn("🤖 Modèle", width="medium"),
                        "Victoires": st.column_config.NumberColumn("🥇 Victoires", width="small"),
                        "Défaites": st.column_config.NumberColumn("❌ Défaites", width="small"),
                        "Égalités": st.column_config.NumberColumn("⚖️ Égalités", width="small"),
                        "Total": st.column_config.NumberColumn("📊 Total", width="small"),
                        "Taux de victoire": st.column_config.TextColumn("📈 Taux", width="small")
                    }
                )
                
                # ==================== DÉTAILS SUPPLÉMENTAIRES ====================
                
                st.markdown("---")
                st.header("📋 Détails")
                
                # Onglets pour plus d'infos
                tab1, tab2 = st.tabs(["📊 Statistiques", "📤 Export"])
                
                with tab1:
                    col_detail1, col_detail2 = st.columns(2)
                    
                    with col_detail1:
                        st.subheader("🎯 Résumé")
                        total_votes = len(votes_df)
                        total_egalites = len(votes_df[votes_df['vote'] == 'tie'])
                        
                        st.write(f"**Total des votes :** {total_votes}")
                        st.write(f"**Égalités :** {total_egalites} ({total_egalites/total_votes*100:.1f}%)")
                        st.write(f"**Modèles actifs :** {len(stats_df)}")
                        
                        # Top 3
                        st.subheader("🏅 Podium")
                        for i, row in stats_df.head(3).iterrows():
                            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉"
                            st.write(f"{medal} **{row['Modèle']}** - {row['Victoires']} victoires ({row['Taux de victoire']})")
                    
                    with col_detail2:
                        st.subheader("📈 Performances détaillées")
                        
                        for _, row in stats_df.iterrows():
                            with st.expander(f"📊 {row['Modèle']}", expanded=False):
                                st.write(f"**Victoires :** {row['Victoires']}")
                                st.write(f"**Défaites :** {row['Défaites']}")
                                st.write(f"**Égalités :** {row['Égalités']}")
                                st.write(f"**Total participations :** {row['Total']}")
                                st.write(f"**Taux de victoire :** {row['Taux de victoire']}")
                
                with tab2:
                    st.subheader("📤 Télécharger les données")
                    
                    col_export1, col_export2 = st.columns(2)
                    
                    with col_export1:
                        # Export CSV des stats
                        csv_data = stats_df.to_csv(index=False)
                        st.download_button(
                            label="📊 Statistiques (CSV)",
                            data=csv_data,
                            file_name=f"stats_modeles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )
                    
                    with col_export2:
                        # Export CSV des votes bruts
                        votes_csv = votes_df.to_csv(index=False)
                        st.download_button(
                            label="📋 Votes bruts (CSV)",
                            data=votes_csv,
                            file_name=f"votes_bruts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )
            
            else:
                st.warning("⚠️ Aucune statistique disponible")
        
        else:
            st.warning("⚠️ Aucun vote dans la base de données")
            st.info("💡 Utilisez d'abord l'app de comparaison pour générer des votes")
    
    else:
        st.error("❌ Connexion Firebase échouée")

else:
    st.error("❌ Firebase non disponible")

# ==================== FOOTER ====================

st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; font-size: 0.9em;'>
    <p>📊 Dashboard Simple - Votes des Modèles IA</p>
    <p>🔄 Actualisé automatiquement depuis Firebase</p>
</div>
""", unsafe_allow_html=True)