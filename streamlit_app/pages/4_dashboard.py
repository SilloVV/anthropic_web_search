import streamlit as st
import pandas as pd
from dotenv import load_dotenv
import os
import json
from datetime import datetime

# Configuration de la page
st.set_page_config(
    page_title="Dashboard Simple - Modèles IA",
    page_icon="📊",
    layout="wide"
)

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

# ==================== FIREBASE CONFIGURATION ====================

@st.cache_resource
def init_firebase():
    """Initialise la connexion Firebase"""
    if not FIREBASE_AVAILABLE:
        return None
    
    try:
        if firebase_admin._apps:
            return firestore.client()
        
        # Méthode 1 : Fichier JSON (développement local)
        cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
        if cred_path and os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
        
        # Méthode 2 : Streamlit Secrets (Streamlit Cloud)
        elif "firebase_credentials" in st.secrets:
            firebase_config = json.loads(st.secrets["firebase_credentials"])
            cred = credentials.Certificate(firebase_config)
        
        # Méthode 3 : Variables d'environnement individuelles
        else:
            firebase_config = {
                "type": "service_account",
                "project_id": os.getenv("FIREBASE_PROJECT_ID"),
                "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
                "private_key": os.getenv("FIREBASE_PRIVATE_KEY", "").replace('\\n', '\n'),
                "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
                "client_id": os.getenv("FIREBASE_CLIENT_ID"),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_CERT_URL")
            }
            
            if not all([firebase_config["project_id"], firebase_config["private_key"], firebase_config["client_email"]]):
                st.error("❌ Variables Firebase manquantes. Vérifiez votre configuration.")
                return None
            
            cred = credentials.Certificate(firebase_config)
        
        # Initialiser Firebase
        firebase_admin.initialize_app(cred, {
            'projectId': os.getenv("FIREBASE_PROJECT_ID") or json.loads(st.secrets.get("firebase_credentials", "{}")).get("project_id"),
        })
        
        return firestore.client()
    
    except Exception as e:
        st.error(f"❌ Erreur d'initialisation Firebase : {str(e)}")
        return None

@st.cache_data(ttl=30)
def load_all_votes(_db):
    """Charge tous les votes depuis Firebase"""
    if not _db:
        return []
    
    try:
        docs = _db.collection('votes').stream()
        votes = []
        
        for doc in docs:
            data = doc.to_dict()
            
            # Convertir le timestamp Firestore
            if data.get('timestamp') and hasattr(data['timestamp'], 'timestamp'):
                data['timestamp'] = datetime.fromtimestamp(data['timestamp'].timestamp())
            
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
        # Filtrer les votes où ce modèle participe
        model_votes = votes_df[
            (votes_df['model_left'] == model) | 
            (votes_df['model_right'] == model)
        ]
        
        # Compteurs de base
        victoires = len(votes_df[votes_df['vote'] == model])
        participations = len(model_votes)
        egalites = len(model_votes[model_votes['vote'] == 'tie'])
        defaites = participations - victoires - egalites
        
        # Calculs de coût, temps et recherches
        cout_total = 0
        temps_total = 0
        recherches_total = 0
        nb_mesures = 0
        
        for _, vote in model_votes.iterrows():
            # Récupérer les stats selon la position du modèle
            stats_model = None
            if vote['model_left'] == model and 'stats_left' in vote and vote['stats_left']:
                stats_model = vote['stats_left']
            elif vote['model_right'] == model and 'stats_right' in vote and vote['stats_right']:
                stats_model = vote['stats_right']
            
            if stats_model:
                cout_total += stats_model.get('total_cost', 0)
                temps_total += stats_model.get('response_time', 0)
                recherches_total += stats_model.get('web_searches', 0)
                nb_mesures += 1
        
        cout_moyen = cout_total / nb_mesures if nb_mesures > 0 else 0
        temps_moyen = temps_total / nb_mesures if nb_mesures > 0 else 0
        recherches_moyennes = recherches_total / nb_mesures if nb_mesures > 0 else 0
        
        stats.append({
            'Modèle': model,
            'Victoires': victoires,
            'Égalités': egalites,
            'Défaites': defaites,
            'Temps moyen (s)': round(temps_moyen, 2),
            'Coût moyen ($)': f"{cout_moyen:.6f}",
            'Recherches moyennes': round(recherches_moyennes, 1)
        })
    
    return pd.DataFrame(stats).sort_values('Victoires', ascending=False)

def prepare_battles_history(votes_df):
    """Prépare l'historique des battles avec détails complets"""
    if votes_df.empty:
        return pd.DataFrame()
    
    battles = []
    
    for _, vote in votes_df.iterrows():
        # Récupérer les stats pour chaque modèle
        stats_left = vote.get('stats_left', {})
        stats_right = vote.get('stats_right', {})
        
        battle = {
            'Date': vote['timestamp'].strftime('%Y-%m-%d %H:%M:%S') if 'timestamp' in vote and pd.notna(vote['timestamp']) else 'N/A',
            'Modèle A': vote['model_left'],
            'Modèle B': vote['model_right'],
            'Gagnant': vote['vote'],
            'Question': vote.get('question', 'N/A'),
            'Réponse A': vote.get('response_left', 'N/A'),
            'Réponse B': vote.get('response_right', 'N/A'),
            'Coût A ($)': f"{stats_left.get('total_cost', 0):.6f}",
            'Coût B ($)': f"{stats_right.get('total_cost', 0):.6f}",
            'Temps A (s)': round(stats_left.get('response_time', 0), 2),
            'Temps B (s)': round(stats_right.get('response_time', 0), 2),
            'Recherches A': stats_left.get('web_searches', 0),
            'Recherches B': stats_right.get('web_searches', 0),
            'Tokens IN A': stats_left.get('input_tokens', 0),
            'Tokens OUT A': stats_left.get('output_tokens', 0),
            'Tokens IN B': stats_right.get('input_tokens', 0),
            'Tokens OUT B': stats_right.get('output_tokens', 0),
            'Utilisateur': vote.get('user_session_id', 'N/A')[:8] + '...' if vote.get('user_session_id') else 'N/A'
        }
        battles.append(battle)
    
    battles_df = pd.DataFrame(battles)
    
    # Trier par date décroissante
    if 'Date' in battles_df.columns and battles_df['Date'].iloc[0] != 'N/A':
        battles_df = battles_df.sort_values('Date', ascending=False)
    
    return battles_df

def export_to_txt(data_df, title):
    """Convertit un DataFrame en format texte lisible"""
    txt_content = f"{'='*80}\n{title.upper()}\n{'='*80}\n"
    txt_content += f"Généré le : {datetime.now().strftime('%Y-%m-%d à %H:%M:%S')}\n"
    txt_content += f"Nombre d'entrées : {len(data_df)}\n\n"
    
    for idx, row in data_df.iterrows():
        txt_content += f"{'-'*80}\nENTRÉE #{idx + 1}\n{'-'*80}\n"
        for col, value in row.items():
            txt_content += f"{col}: {value}\n"
        txt_content += "\n"
    
    return txt_content

def export_detailed_battle_to_txt(vote_data):
    """Exporte un battle détaillé en format texte"""
    txt_content = f"{'='*100}\nDÉTAIL COMPLET DU BATTLE\n{'='*100}\n"
    txt_content += f"Date : {vote_data.get('timestamp', 'N/A')}\n"
    txt_content += f"Utilisateur : {vote_data.get('user_session_id', 'N/A')}\n"
    txt_content += f"Gagnant : {vote_data.get('vote', 'N/A')}\n\n"
    
    # Question
    txt_content += f"{'='*50}\nQUESTION\n{'='*50}\n"
    txt_content += f"{vote_data.get('question', 'N/A')}\n\n"
    
    # Modèle A (gauche)
    txt_content += f"{'='*50}\nMODÈLE A : {vote_data.get('model_left', 'N/A')}\n{'='*50}\n"
    stats_left = vote_data.get('stats_left', {})
    txt_content += f"Coût : ${stats_left.get('total_cost', 0):.6f}\n"
    txt_content += f"Temps de réponse : {stats_left.get('response_time', 0):.2f}s\n"
    txt_content += f"Recherches web : {stats_left.get('web_searches', 0)}\n"
    txt_content += f"Tokens input : {stats_left.get('input_tokens', 0)}\n"
    txt_content += f"Tokens output : {stats_left.get('output_tokens', 0)}\n\n"
    txt_content += f"RÉPONSE :\n{'-'*30}\n{vote_data.get('response_left', 'N/A')}\n\n"
    
    # Modèle B (droite)
    txt_content += f"{'='*50}\nMODÈLE B : {vote_data.get('model_right', 'N/A')}\n{'='*50}\n"
    stats_right = vote_data.get('stats_right', {})
    txt_content += f"Coût : ${stats_right.get('total_cost', 0):.6f}\n"
    txt_content += f"Temps de réponse : {stats_right.get('response_time', 0):.2f}s\n"
    txt_content += f"Recherches web : {stats_right.get('web_searches', 0)}\n"
    txt_content += f"Tokens input : {stats_right.get('input_tokens', 0)}\n"
    txt_content += f"Tokens output : {stats_right.get('output_tokens', 0)}\n\n"
    txt_content += f"RÉPONSE :\n{'-'*30}\n{vote_data.get('response_right', 'N/A')}\n\n"
    
    return txt_content

# ==================== INTERFACE PRINCIPALE ====================

st.title("📊 Dashboard Simple - Modèles IA")
st.markdown("**Tableau de bord purifié avec statistiques essentielles**")

# Bouton d'actualisation
col1, col2 = st.columns([1, 4])
with col1:
    if st.button("🔄 Actualiser"):
        st.cache_data.clear()
        st.rerun()

# Initialiser Firebase
if FIREBASE_AVAILABLE:
    db = init_firebase()
    
    if db:
        # Charger les données
        with st.spinner("📥 Chargement des données..."):
            votes_data = load_all_votes(db)
        
        if votes_data:
            votes_df = pd.DataFrame(votes_data)
            
            # ==================== STATISTIQUES MODÈLES ====================
            
            st.header("📊 Statistiques par modèle")
            
            stats_df = calculate_model_stats(votes_df)
            
            if not stats_df.empty:
                # Afficher le tableau
                st.dataframe(
                    stats_df,
                    use_container_width=True,
                    hide_index=True
                )
                
                # ==================== EXPORT CSV ====================
                
                st.header("📤 Export")
                
                col_export1, col_export2 = st.columns(2)
                
                with col_export1:
                    # Export statistiques en TXT
                    txt_stats = export_to_txt(stats_df, "Statistiques des Modèles IA")
                    st.download_button(
                        label="📊 Télécharger les statistiques (TXT)",
                        data=txt_stats,
                        file_name=f"statistiques_modeles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                        mime="text/plain",
                        use_container_width=True
                    )
                
                with col_export2:
                    # Export historique en TXT
                    battles_df = prepare_battles_history(votes_df)
                    if not battles_df.empty:
                        txt_battles = export_to_txt(battles_df, "Historique Complet des Battles")
                        st.download_button(
                            label="📜 Télécharger l'historique (TXT)",
                            data=txt_battles,
                            file_name=f"historique_battles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                            mime="text/plain",
                            use_container_width=True
                        )
                
                # ==================== HISTORIQUE DES BATTLES ====================
                
                st.header("📜 Historique des battles")
                
                battles_df = prepare_battles_history(votes_df)
                
                if not battles_df.empty:
                    # Filtres pour l'historique
                    col_filter1, col_filter2, col_filter3 = st.columns(3)
                    
                    with col_filter1:
                        # Filtre par modèle
                        all_models = set(battles_df['Modèle A'].tolist() + battles_df['Modèle B'].tolist())
                        selected_model = st.selectbox(
                            "Filtrer par modèle",
                            ["Tous"] + sorted(list(all_models))
                        )
                    
                    with col_filter2:
                        # Filtre par résultat
                        selected_result = st.selectbox(
                            "Filtrer par résultat",
                            ["Tous", "Victoire", "Égalité"]
                        )
                    
                    with col_filter3:
                        # Nombre d'entrées à afficher
                        nb_entries = st.selectbox(
                            "Nombre d'entrées",
                            [10, 25, 50, 100, "Toutes"],
                            index=1
                        )
                    
                    # Appliquer les filtres
                    filtered_battles = battles_df.copy()
                    
                    if selected_model != "Tous":
                        filtered_battles = filtered_battles[
                            (filtered_battles['Modèle A'] == selected_model) |
                            (filtered_battles['Modèle B'] == selected_model)
                        ]
                    
                    if selected_result == "Égalité":
                        filtered_battles = filtered_battles[filtered_battles['Gagnant'] == 'tie']
                    elif selected_result == "Victoire":
                        filtered_battles = filtered_battles[filtered_battles['Gagnant'] != 'tie']
                    
                    # Limiter le nombre d'entrées
                    if nb_entries != "Toutes":
                        filtered_battles = filtered_battles.head(nb_entries)
                    
                    # Afficher l'historique filtré avec colonnes supplémentaires
                    st.dataframe(
                        filtered_battles,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Date": st.column_config.TextColumn("📅 Date", width="medium"),
                            "Modèle A": st.column_config.TextColumn("🤖 Modèle A", width="small"),
                            "Modèle B": st.column_config.TextColumn("🤖 Modèle B", width="small"),
                            "Gagnant": st.column_config.TextColumn("🏆 Gagnant", width="small"),
                            "Question": st.column_config.TextColumn("❓ Question", width="large"),
                            "Coût A ($)": st.column_config.TextColumn("💰 Coût A", width="small"),
                            "Coût B ($)": st.column_config.TextColumn("💰 Coût B", width="small"),
                            "Temps A (s)": st.column_config.NumberColumn("⏱️ Temps A", width="small"),
                            "Temps B (s)": st.column_config.NumberColumn("⏱️ Temps B", width="small"),
                            "Recherches A": st.column_config.NumberColumn("🔍 Rech. A", width="small"),
                            "Recherches B": st.column_config.NumberColumn("🔍 Rech. B", width="small"),
                            "Utilisateur": st.column_config.TextColumn("👤 User", width="small")
                        }
                    )
                    
                    # Section d'export de battle individuel
                    st.markdown("---")
                    st.subheader("📋 Export détaillé d'un battle spécifique")
                    
                    if not filtered_battles.empty:
                        # Sélection d'un battle spécifique
                        battle_options = []
                        for idx, battle in filtered_battles.iterrows():
                            option_text = f"{battle['Date']} - {battle['Modèle A']} vs {battle['Modèle B']} (Gagnant: {battle['Gagnant']})"
                            battle_options.append((option_text, idx))
                        
                        selected_battle = st.selectbox(
                            "Choisir un battle à exporter en détail",
                            options=[opt[0] for opt in battle_options],
                            index=0
                        )
                        
                        # Trouver l'index du battle sélectionné
                        selected_idx = None
                        for opt_text, idx in battle_options:
                            if opt_text == selected_battle:
                                selected_idx = idx
                                break
                        
                        if selected_idx is not None:
                            # Récupérer les données complètes du vote
                            vote_data = votes_data[selected_idx]
                            
                            col_detail1, col_detail2 = st.columns(2)
                            
                            with col_detail1:
                                # Aperçu du battle sélectionné
                                st.markdown("**📋 Aperçu du battle sélectionné :**")
                                st.write(f"**Date :** {vote_data.get('timestamp', 'N/A')}")
                                st.write(f"**Modèles :** {vote_data.get('model_left', 'N/A')} vs {vote_data.get('model_right', 'N/A')}")
                                st.write(f"**Gagnant :** {vote_data.get('vote', 'N/A')}")
                                
                                # Stats rapides
                                stats_left = vote_data.get('stats_left', {})
                                stats_right = vote_data.get('stats_right', {})
                                st.write(f"**Coûts :** ${stats_left.get('total_cost', 0):.6f} vs ${stats_right.get('total_cost', 0):.6f}")
                                st.write(f"**Temps :** {stats_left.get('response_time', 0):.2f}s vs {stats_right.get('response_time', 0):.2f}s")
                            
                            with col_detail2:
                                # Export du battle détaillé
                                detailed_txt = export_detailed_battle_to_txt(vote_data)
                                st.download_button(
                                    label="📄 Exporter ce battle en détail (TXT)",
                                    data=detailed_txt,
                                    file_name=f"battle_detail_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                                    mime="text/plain",
                                    use_container_width=True
                                )
                                
                                # Affichage des réponses tronquées
                                st.markdown("**👁️ Aperçu des réponses :**")
                                response_a = vote_data.get('response_left', 'N/A')
                                response_b = vote_data.get('response_right', 'N/A')
                                
                                if len(response_a) > 200:
                                    response_a = response_a[:200] + "..."
                                if len(response_b) > 200:
                                    response_b = response_b[:200] + "..."
                                
                                st.text_area(f"Réponse {vote_data.get('model_left', 'A')}", response_a, height=100, disabled=True)
                                st.text_area(f"Réponse {vote_data.get('model_right', 'B')}", response_b, height=100, disabled=True)
                    
                    # Statistiques rapides de l'historique filtré
                    if not filtered_battles.empty:
                        st.markdown("---")
                        col_hist1, col_hist2, col_hist3, col_hist4 = st.columns(4)
                        
                        with col_hist1:
                            st.metric("📊 Battles affichées", len(filtered_battles))
                        
                        with col_hist2:
                            egalites_filtrees = len(filtered_battles[filtered_battles['Gagnant'] == 'tie'])
                            st.metric("⚖️ Égalités", egalites_filtrees)
                        
                        with col_hist3:
                            utilisateurs_uniques = filtered_battles['Utilisateur'].nunique()
                            st.metric("👥 Utilisateurs", utilisateurs_uniques)
                        
                        with col_hist4:
                            if selected_model != "Tous":
                                victories_model = len(filtered_battles[filtered_battles['Gagnant'] == selected_model])
                                st.metric(f"🏆 Victoires {selected_model}", victories_model)
                
                else:
                    st.info("💡 Aucun historique de battles disponible")
            
            else:
                st.warning("⚠️ Aucune statistique disponible")
        
        else:
            st.warning("⚠️ Aucun vote dans la base de données")
            st.info("💡 Utilisez d'abord l'app de comparaison pour générer des votes")
    
    else:
        st.error("❌ Connexion Firebase échouée")

else:
    st.error("❌ Firebase non disponible")
    st.info("💡 Installez Firebase : `pip install firebase-admin`")

# ==================== FOOTER ====================

st.markdown("---")
st.markdown(f"""
<div style='text-align: center; color: #666; font-size: 0.8em;'>
    <p>📊 Dashboard Simple - Dernière mise à jour : {datetime.now().strftime('%H:%M:%S')}</p>
</div>
""", unsafe_allow_html=True)