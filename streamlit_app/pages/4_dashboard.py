import streamlit as st
import pandas as pd
from dotenv import load_dotenv
import os
import json
from datetime import datetime, timedelta

# Configuration de la page - DOIT ÊTRE EN PREMIER
st.set_page_config(
    page_title="Dashboard Analytics - Modèles IA",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
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

@st.cache_data(ttl=30)  # Cache pendant 30 secondes
def load_all_votes(_db):
    """Charge tous les votes depuis Firebase avec métadonnées enrichies"""
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

def calculate_enhanced_stats(votes_df):
    """Calcule les statistiques enrichies par modèle"""
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
        
        # Métriques de performance
        taux_victoire = (victoires / participations * 100) if participations > 0 else 0
        taux_egalite = (egalites / participations * 100) if participations > 0 else 0
        
        # Calculs de coût et temps (nouvelles données)
        cout_total = 0
        temps_total = 0
        tokens_input_total = 0
        tokens_output_total = 0
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
                tokens_input_total += stats_model.get('input_tokens', 0)
                tokens_output_total += stats_model.get('output_tokens', 0)
                recherches_total += stats_model.get('web_searches', 0)
                nb_mesures += 1
        
        cout_moyen = cout_total / nb_mesures if nb_mesures > 0 else 0
        temps_moyen = temps_total / nb_mesures if nb_mesures > 0 else 0
        tokens_input_moyen = tokens_input_total / nb_mesures if nb_mesures > 0 else 0
        tokens_output_moyen = tokens_output_total / nb_mesures if nb_mesures > 0 else 0
        recherches_moyennes = recherches_total / nb_mesures if nb_mesures > 0 else 0
        
        # Score composite pour le classement
        score = taux_victoire - (cout_moyen * 1000000) + (100 - temps_moyen)  # Favorise victoires, pénalise coût et temps
        
        stats.append({
            'Modèle': model,
            'Victoires': victoires,
            'Défaites': defaites,
            'Égalités': egalites,
            'Total': participations,
            'Taux victoire': f"{taux_victoire:.1f}%",
            'Taux égalité': f"{taux_egalite:.1f}%",
            'Coût moyen': f"${cout_moyen:.6f}",
            'Temps moyen': f"{temps_moyen:.1f}s",
            'Tokens IN': int(tokens_input_moyen),
            'Tokens OUT': int(tokens_output_moyen),
            'Recherches': f"{recherches_moyennes:.1f}",
            'Score': score,
            'Efficacité': f"{(victoires/cout_total*1000000):.0f}" if cout_total > 0 else "∞"  # Victoires par $ dépensé
        })
    
    return pd.DataFrame(stats).sort_values('Victoires', ascending=False)

def create_summary_cards(stats_df, votes_df):
    """Crée des cartes de résumé"""
    
    # Trouver le meilleur dans chaque catégorie
    if not stats_df.empty:
        # Convertir les pourcentages en float pour comparaison
        stats_df_calc = stats_df.copy()
        stats_df_calc['taux_num'] = stats_df_calc['Taux victoire'].str.replace('%', '').astype(float)
        stats_df_calc['temps_num'] = stats_df_calc['Temps moyen'].str.replace('s', '').astype(float)
        stats_df_calc['cout_num'] = stats_df_calc['Coût moyen'].str.replace('$', '').astype(float)
        
        plus_victorieux = stats_df_calc.loc[stats_df_calc['taux_num'].idxmax(), 'Modèle']
        plus_rapide = stats_df_calc.loc[stats_df_calc['temps_num'].idxmin(), 'Modèle'] if stats_df_calc['temps_num'].max() > 0 else "N/A"
        moins_cher = stats_df_calc.loc[stats_df_calc['cout_num'].idxmin(), 'Modèle'] if stats_df_calc['cout_num'].max() > 0 else "N/A"
        
        return {
            'plus_victorieux': plus_victorieux,
            'plus_rapide': plus_rapide,
            'moins_cher': moins_cher
        }
    
    return None

def analyze_temporal_patterns(votes_df):
    """Analyse les patterns temporels"""
    if votes_df.empty or 'timestamp' not in votes_df.columns:
        return None
    
    valid_votes = votes_df[votes_df['timestamp'].notna()].copy()
    if valid_votes.empty:
        return None
    
    # Analyse par jour
    valid_votes['date'] = valid_votes['timestamp'].dt.date
    daily_stats = valid_votes.groupby('date').size()
    
    # Analyse par heure
    valid_votes['hour'] = valid_votes['timestamp'].dt.hour
    hourly_stats = valid_votes.groupby('hour').size()
    
    return {
        'daily_stats': daily_stats,
        'hourly_stats': hourly_stats,
        'peak_day': daily_stats.idxmax() if not daily_stats.empty else None,
        'peak_hour': hourly_stats.idxmax() if not hourly_stats.empty else None,
        'total_days': len(daily_stats)
    }

# ==================== CSS PERSONNALISÉ ====================

st.markdown("""
<style>
.metric-card {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 1.5rem;
    border-radius: 10px;
    color: white;
    text-align: center;
    margin: 0.5rem 0;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.leader-card {
    background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
}

.speed-card {
    background: linear-gradient(135deg, #ffc107 0%, #fd7e14 100%);
    color: black;
}

.cost-card {
    background: linear-gradient(135deg, #17a2b8 0%, #6f42c1 100%);
}

.stat-box {
    background-color: #f8f9fa;
    border-left: 4px solid #007bff;
    padding: 15px;
    margin: 10px 0;
    border-radius: 5px;
}

.warning-box {
    background-color: #fff3cd;
    border-left: 4px solid #ffc107;
    padding: 15px;
    margin: 10px 0;
    border-radius: 5px;
    color: #856404;
}

.success-box {
    background-color: #d4edda;
    border-left: 4px solid #28a745;
    padding: 15px;
    margin: 10px 0;
    border-radius: 5px;
    color: #155724;
}

.highlight-row {
    background-color: #28a745 !important;
    color: black !important;
    font-weight: bold !important;
}

.second-place {
    background-color: #17a2b8 !important;
    color: white !important;
    font-weight: bold !important;
}

.third-place {
    background-color: #ffc107 !important;
    color: black !important;
    font-weight: bold !important;
}

.performance-bar {
    height: 20px;
    background-color: #e9ecef;
    border-radius: 10px;
    overflow: hidden;
    margin: 5px 0;
}

.performance-fill {
    height: 100%;
    background: linear-gradient(90deg, #28a745, #20c997);
    transition: width 0.3s ease;
}
</style>
""", unsafe_allow_html=True)

# ==================== INTERFACE PRINCIPALE ====================

st.title("📊 Dashboard Analytics - Modèles IA")
st.markdown("**Analyse complète des performances et métriques (sans graphiques)**")

# Sidebar pour les contrôles
with st.sidebar:
    st.header("⚙️ Contrôles")
    
    # Actualisation avec temps
    col_refresh1, col_refresh2 = st.columns([3, 1])
    with col_refresh1:
        if st.button("🔄 Actualiser", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    
    with col_refresh2:
        st.write(f"{datetime.now().strftime('%H:%M')}")
    
    st.info("🔄 Auto-refresh : 30s")
    
    # Options d'affichage
    st.subheader("🎨 Affichage")
    show_detailed_stats = st.checkbox("Analyses détaillées", value=True)
    show_temporal = st.checkbox("Analyse temporelle", value=True)
    show_confrontations = st.checkbox("Face à face", value=True)
    
    # Filtres
    st.subheader("🔍 Filtres")
    
    # Informations système
    st.markdown("---")
    st.subheader("ℹ️ Système")
    if FIREBASE_AVAILABLE:
        st.success("✅ Firebase OK")
    else:
        st.error("❌ Firebase KO")
    
    st.caption(f"Dernière MAJ: {datetime.now().strftime('%H:%M:%S')}")

# Initialiser Firebase
if FIREBASE_AVAILABLE:
    db = init_firebase()
    
    if db:
        # Charger les données
        with st.spinner("📥 Chargement des données..."):
            votes_data = load_all_votes(db)
        
        if votes_data:
            votes_df = pd.DataFrame(votes_data)
            
            # ==================== MÉTRIQUES GLOBALES ====================
            
            st.header("📈 Vue d'ensemble")
            
            # Calculer les stats enrichies
            stats_df = calculate_enhanced_stats(votes_df)
            summary_cards = create_summary_cards(stats_df, votes_df)
            
            # Métriques principales
            col1, col2, col3, col4, col5 = st.columns(5)
            
            with col1:
                total_votes = len(votes_df)
                if 'timestamp' in votes_df.columns:
                    votes_today = len(votes_df[votes_df['timestamp'].dt.date == datetime.now().date()])
                    delta_text = f"+{votes_today} aujourd'hui"
                else:
                    delta_text = None
                
                st.metric(
                    label="🗳️ Total votes",
                    value=total_votes,
                    delta=delta_text
                )
            
            with col2:
                unique_users = votes_df['user_session_id'].nunique()
                avg_votes_per_user = total_votes / unique_users if unique_users > 0 else 0
                st.metric(
                    label="👥 Utilisateurs",
                    value=unique_users,
                    delta=f"{avg_votes_per_user:.1f} votes/user"
                )
            
            with col3:
                égalités = len(votes_df[votes_df['vote'] == 'tie'])
                taux_egalite = (égalités / total_votes * 100) if total_votes > 0 else 0
                st.metric(
                    label="⚖️ Égalités", 
                    value=égalités,
                    delta=f"{taux_egalite:.1f}%"
                )
            
            with col4:
                # Coût total si disponible
                cout_total = 0
                if 'total_cost_combined' in votes_df.columns:
                    cout_total = votes_df['total_cost_combined'].sum()
                
                if cout_total > 0:
                    cout_moyen = cout_total / total_votes
                    st.metric(
                        label="💰 Coût total",
                        value=f"${cout_total:.4f}",
                        delta=f"${cout_moyen:.6f}/vote"
                    )
                else:
                    st.metric(label="💰 Coût total", value="N/A")
            
            with col5:
                # Temps total si disponible
                if 'total_response_time' in votes_df.columns:
                    temps_total = votes_df['total_response_time'].sum()
                    temps_moyen = temps_total / total_votes if total_votes > 0 else 0
                    st.metric(
                        label="⏱️ Temps total",
                        value=f"{temps_total:.1f}s",
                        delta=f"{temps_moyen:.1f}s/vote"
                    )
                else:
                    st.metric(label="⏱️ Temps total", value="N/A")
            
            # Cartes de champions
            if summary_cards:
                st.markdown("---")
                st.subheader("🏆 Champions par catégorie")
                
                col_champ1, col_champ2, col_champ3 = st.columns(3)
                
                with col_champ1:
                    st.markdown(f"""
                    <div class="metric-card leader-card">
                        <h3>🥇 Plus victorieux</h3>
                        <h2>{summary_cards['plus_victorieux']}</h2>
                        <p>Taux de victoire le plus élevé</p>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col_champ2:
                    st.markdown(f"""
                    <div class="metric-card speed-card">
                        <h3>⚡ Plus rapide</h3>
                        <h2>{summary_cards['plus_rapide']}</h2>
                        <p>Temps de réponse le plus court</p>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col_champ3:
                    st.markdown(f"""
                    <div class="metric-card cost-card">
                        <h3>💰 Plus économique</h3>
                        <h2>{summary_cards['moins_cher']}</h2>
                        <p>Coût moyen le plus bas</p>
                    </div>
                    """, unsafe_allow_html=True)
            
            st.markdown("---")
            
            # ==================== TABLEAU DE CLASSEMENT ENRICHI ====================
            
            st.header("🏆 Classement détaillé des modèles")
            
            if not stats_df.empty:
                # Fonction de style pour le podium
                def highlight_podium(row):
                    if row.name == 0:  # Premier
                        return ['background-color: #28a745; color: black; font-weight: bold'] * len(row)
                    elif row.name == 1:  # Deuxième
                        return ['background-color: #17a2b8; color: white; font-weight: bold'] * len(row)
                    elif row.name == 2:  # Troisième
                        return ['background-color: #ffc107; color: black; font-weight: bold'] * len(row)
                    else:
                        return [''] * len(row)
                
                # Préparer le DataFrame pour l'affichage
                display_df = stats_df.drop(['Score'], axis=1, errors='ignore')
                styled_df = display_df.style.apply(highlight_podium, axis=1)
                
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
                        "Taux victoire": st.column_config.TextColumn("📈 % Vict.", width="small"),
                        "Taux égalité": st.column_config.TextColumn("⚖️ % Égal.", width="small"),
                        "Coût moyen": st.column_config.TextColumn("💰 Coût", width="small"),
                        "Temps moyen": st.column_config.TextColumn("⏱️ Temps", width="small"),
                        "Tokens IN": st.column_config.NumberColumn("🔤 IN", width="small"),
                        "Tokens OUT": st.column_config.NumberColumn("🔤 OUT", width="small"),
                        "Recherches": st.column_config.TextColumn("🔍 Rech.", width="small"),
                        "Efficacité": st.column_config.TextColumn("⚡ Effic.", width="small")
                    }
                )
                
                # Barres de progression visuelles
                st.subheader("📊 Barres de performance")
                
                for _, row in stats_df.iterrows():
                    taux_num = float(row['Taux victoire'].replace('%', ''))
                    
                    st.write(f"**{row['Modèle']}** - {row['Taux victoire']}")
                    progress_bar = st.progress(taux_num / 100)
                    
                    # Détails en colonnes
                    col_det1, col_det2, col_det3, col_det4 = st.columns(4)
                    with col_det1:
                        st.caption(f"🥇 {row['Victoires']} victoires")
                    with col_det2:
                        st.caption(f"💰 {row['Coût moyen']}")
                    with col_det3:
                        st.caption(f"⏱️ {row['Temps moyen']}")
                    with col_det4:
                        st.caption(f"🔍 {row['Recherches']} recherches")
                    
                    st.markdown("---")
                
                # ==================== ANALYSES DÉTAILLÉES ====================
                
                if show_detailed_stats:
                    st.header("🔍 Analyses avancées")
                    
                    tab1, tab2, tab3, tab4 = st.tabs(["📊 Résumé", "⚔️ Face à face", "💰 Économie", "⏰ Temporel"])
                    
                    with tab1:
                        col_analysis1, col_analysis2 = st.columns(2)
                        
                        with col_analysis1:
                            st.markdown("""
                            <div class="success-box">
                                <h4>🎯 Analyse générale</h4>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            total_participations = stats_df['Total'].sum() // 2  # Chaque vote compte pour 2 participations
                            
                            st.write(f"**📊 Matchs totaux :** {total_participations}")
                            st.write(f"**🤖 Modèles actifs :** {len(stats_df)}")
                            st.write(f"**👥 Utilisateurs actifs :** {votes_df['user_session_id'].nunique()}")
                            
                            if 'timestamp' in votes_df.columns:
                                votes_today = len(votes_df[votes_df['timestamp'].dt.date == datetime.now().date()])
                                st.write(f"**📅 Votes aujourd'hui :** {votes_today}")
                            
                            # Top performer
                            best_model = stats_df.iloc[0]
                            st.markdown(f"""
                            <div class="stat-box">
                                <strong>👑 Modèle dominant :</strong><br>
                                🥇 {best_model['Modèle']}<br>
                                📈 {best_model['Taux victoire']} de victoires<br>
                                💰 {best_model['Coût moyen']} par utilisation
                            </div>
                            """, unsafe_allow_html=True)
                        
                        with col_analysis2:
                            st.markdown("""
                            <div class="warning-box">
                                <h4>⚡ Points d'attention</h4>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            # Analyses des tendances
                            if len(stats_df) >= 2:
                                ecart_leader = float(stats_df.iloc[0]['Taux victoire'].replace('%', '')) - float(stats_df.iloc[1]['Taux victoire'].replace('%', ''))
                                
                                if ecart_leader > 20:
                                    st.warning(f"🔥 {stats_df.iloc[0]['Modèle']} domine largement (+{ecart_leader:.1f}%)")
                                elif ecart_leader < 5:
                                    st.info(f"🤝 Competition serrée entre les leaders ({ecart_leader:.1f}% d'écart)")
                                
                                # Analyse des coûts
                                costs = []
                                for _, row in stats_df.iterrows():
                                    try:
                                        cost_val = float(row['Coût moyen'].replace('$', ''))
                                        if cost_val > 0:
                                            costs.append(cost_val)
                                    except:
                                        continue
                                
                                if costs:
                                    max_cost = max(costs)
                                    min_cost = min(costs)
                                    if max_cost > min_cost * 2:
                                        st.warning(f"💸 Écart de coût important (×{max_cost/min_cost:.1f})")
                            
                            # Recommandations
                            st.markdown("**🎯 Recommandations :**")
                            
                            # Modèle le plus équilibré
                            balanced_scores = []
                            for _, row in stats_df.iterrows():
                                try:
                                    taux = float(row['Taux victoire'].replace('%', ''))
                                    temps = float(row['Temps moyen'].replace('s', ''))
                                    cout = float(row['Coût moyen'].replace('$', ''))
                                    
                                    # Score équilibré (performance / (coût + temps))
                                    balance_score = taux / (cout * 1000000 + temps) if (cout + temps) > 0 else taux
                                    balanced_scores.append((row['Modèle'], balance_score))
                                except:
                                    continue
                            
                            if balanced_scores:
                                best_balanced = max(balanced_scores, key=lambda x: x[1])
                                st.success(f"⚖️ **Plus équilibré :** {best_balanced[0]}")
                    
                    with tab2:
                        if show_confrontations:
                            st.subheader("⚔️ Confrontations directes")
                            
                            models = stats_df['Modèle'].tolist()
                            if len(models) >= 2:
                                # Matrice des confrontations
                                confrontation_data = []
                                
                                for i, model_a in enumerate(models):
                                    for j, model_b in enumerate(models[i+1:], i+1):
                                        # Compter les victoires directes
                                        direct_matches = votes_df[
                                            ((votes_df['model_left'] == model_a) & (votes_df['model_right'] == model_b)) |
                                            ((votes_df['model_left'] == model_b) & (votes_df['model_right'] == model_a))
                                        ]
                                        
                                        if len(direct_matches) > 0:
                                            wins_a = len(direct_matches[direct_matches['vote'] == model_a])
                                            wins_b = len(direct_matches[direct_matches['vote'] == model_b])
                                            ties = len(direct_matches[direct_matches['vote'] == 'tie'])
                                            
                                            confrontation_data.append({
                                                'Match': f"{model_a} vs {model_b}",
                                                'Modèle A': model_a,
                                                'Victoires A': wins_a,
                                                'Égalités': ties,
                                                'Victoires B': wins_b,
                                                'Modèle B': model_b,
                                                'Total matchs': wins_a + wins_b + ties,
                                                'Dominance': model_a if wins_a > wins_b else model_b if wins_b > wins_a else "Égalité"
                                            })
                                
                                if confrontation_data:
                                    confrontation_df = pd.DataFrame(confrontation_data)
                                    
                                    st.dataframe(
                                        confrontation_df,
                                        use_container_width=True,
                                        hide_index=True,
                                        column_config={
                                            "Match": st.column_config.TextColumn("⚔️ Match", width="medium"),
                                            "Modèle A": st.column_config.TextColumn("🤖 Modèle A", width="medium"),
                                            "Victoires A": st.column_config.NumberColumn("🥇 Vict. A", width="small"),
                                            "Égalités": st.column_config.NumberColumn("⚖️ Égal.", width="small"),
                                            "Victoires B": st.column_config.NumberColumn("🥇 Vict. B", width="small"),
                                            "Modèle B": st.column_config.TextColumn("🤖 Modèle B", width="medium"),
                                            "Total matchs": st.column_config.NumberColumn("📊 Total", width="small"),
                                            "Dominance": st.column_config.TextColumn("👑 Dominant", width="medium")
                                        }
                                    )
                                    
                                    # Analyse des rivalités
                                    st.subheader("🔥 Rivalités les plus intenses")
                                    
                                    for _, match in confrontation_df.iterrows():
                                        if match['Total matchs'] >= 3:  # Au moins 3 confrontations
                                            with st.expander(f"📊 {match['Match']} ({match['Total matchs']} matchs)", expanded=False):
                                                
                                                col_rival1, col_rival2, col_rival3 = st.columns(3)
                                                
                                                with col_rival1:
                                                    st.write(f"**{match['Modèle A']}**")
                                                    st.write(f"🥇 {match['Victoires A']} victoires")
                                                    st.write(f"📈 {(match['Victoires A']/match['Total matchs']*100):.1f}%")
                                                
                                                with col_rival2:
                                                    st.write("**⚖️ Égalités**")
                                                    st.write(f"🤝 {match['Égalités']} égalités")
                                                    st.write(f"📊 {(match['Égalités']/match['Total matchs']*100):.1f}%")
                                                
                                                with col_rival3:
                                                    st.write(f"**{match['Modèle B']}**")
                                                    st.write(f"🥇 {match['Victoires B']} victoires")
                                                    st.write(f"📈 {(match['Victoires B']/match['Total matchs']*100):.1f}%")
                                                
                                                # Verdict de la rivalité
                                                if match['Dominance'] != "Égalité":
                                                    écart = abs(match['Victoires A'] - match['Victoires B'])
                                                    if écart >= 2:
                                                        st.success(f"👑 **{match['Dominance']}** domine cette rivalité")
                                                    else:
                                                        st.info(f"🤝 Rivalité équilibrée avec léger avantage à **{match['Dominance']}**")
                                                else:
                                                    st.info("🤝 Parfaite égalité dans cette rivalité !")
                                
                                else:
                                    st.info("💡 Pas assez de confrontations directes pour analyser")
                            else:
                                st.info("💡 Pas assez de modèles pour les confrontations directes")
                    
                    with tab3:
                        st.subheader("💰 Analyse économique détaillée")
                        
                        if 'total_cost_combined' in votes_df.columns:
                            col_eco1, col_eco2 = st.columns(2)
                            
                            with col_eco1:
                                cout_total = votes_df['total_cost_combined'].sum()
                                cout_moyen_vote = votes_df['total_cost_combined'].mean()
                                cout_median = votes_df['total_cost_combined'].median()
                                
                                st.markdown("""
                                <div class="stat-box">
                                    <h4>💰 Statistiques de coût</h4>
                                </div>
                                """, unsafe_allow_html=True)
                                
                                st.metric("💰 Coût total", f"${cout_total:.6f}")
                                st.metric("💸 Coût moyen/vote", f"${cout_moyen_vote:.6f}")
                                st.metric("📊 Coût médian", f"${cout_median:.6f}")
                                
                                # Projection mensuelle
                                if 'timestamp' in votes_df.columns:
                                    votes_per_day = len(votes_df) / max(1, (datetime.now() - votes_df['timestamp'].min()).days)
                                    cout_projection_mensuel = cout_moyen_vote * votes_per_day * 30
                                    st.metric("📅 Projection mensuelle", f"${cout_projection_mensuel:.4f}")
                            
                            with col_eco2:
                                st.markdown("""
                                <div class="warning-box">
                                    <h4>📊 Analyse des coûts par modèle</h4>
                                </div>
                                """, unsafe_allow_html=True)
                                
                                # Créer un classement par efficacité économique
                                cost_efficiency = []
                                for _, row in stats_df.iterrows():
                                    try:
                                        cout = float(row['Coût moyen'].replace('$', ''))
                                        victoires = row['Victoires']
                                        if cout > 0 and victoires > 0:
                                            efficacite = victoires / cout
                                            cost_efficiency.append({
                                                'Modèle': row['Modèle'],
                                                'Coût': cout,
                                                'Victoires': victoires,
                                                'Efficacité': efficacite,
                                                'Classement': 0
                                            })
                                    except:
                                        continue
                                
                                if cost_efficiency:
                                    # Trier par efficacité
                                    cost_efficiency.sort(key=lambda x: x['Efficacité'], reverse=True)
                                    
                                    for i, model_cost in enumerate(cost_efficiency):
                                        model_cost['Classement'] = i + 1
                                        
                                        medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."
                                        
                                        st.write(f"{medal} **{model_cost['Modèle']}**")
                                        st.write(f"   💰 ${model_cost['Coût']:.6f} par utilisation")
                                        st.write(f"   🥇 {model_cost['Victoires']} victoires")
                                        st.write(f"   ⚡ {model_cost['Efficacité']:.0f} victoires/$")
                                        st.markdown("---")
                                
                                # Recommandation économique
                                if cost_efficiency:
                                    best_value = cost_efficiency[0]
                                    st.markdown(f"""
                                    <div class="success-box">
                                        <strong>💡 Meilleur rapport qualité/prix :</strong><br>
                                        🏆 {best_value['Modèle']}<br>
                                        💰 {best_value['Efficacité']:.0f} victoires par dollar dépensé
                                    </div>
                                    """, unsafe_allow_html=True)
                        
                        else:
                            st.info("💡 Pas de données de coût disponibles dans cette base")
                    
                    with tab4:
                        if show_temporal and 'timestamp' in votes_df.columns:
                            st.subheader("⏰ Analyse temporelle")
                            
                            temporal_analysis = analyze_temporal_patterns(votes_df)
                            
                            if temporal_analysis:
                                col_temp1, col_temp2 = st.columns(2)
                                
                                with col_temp1:
                                    st.markdown("""
                                    <div class="stat-box">
                                        <h4>📅 Activité par jour</h4>
                                    </div>
                                    """, unsafe_allow_html=True)
                                    
                                    # Stats par jour
                                    daily_stats = temporal_analysis['daily_stats']
                                    
                                    if not daily_stats.empty:
                                        st.metric("📊 Jours d'activité", len(daily_stats))
                                        st.metric("🔥 Jour le plus actif", f"{temporal_analysis['peak_day']}")
                                        st.metric("📈 Max votes/jour", daily_stats.max())
                                        st.metric("📊 Moyenne votes/jour", f"{daily_stats.mean():.1f}")
                                        
                                        # Tableau des derniers jours
                                        st.write("**📅 Activité récente :**")
                                        recent_days = daily_stats.tail(7)
                                        for date, votes in recent_days.items():
                                            day_name = date.strftime('%A')
                                            st.write(f"• {date} ({day_name}): {votes} votes")
                                
                                with col_temp2:
                                    st.markdown("""
                                    <div class="warning-box">
                                        <h4>🕐 Activité par heure</h4>
                                    </div>
                                    """, unsafe_allow_html=True)
                                    
                                    # Stats par heure
                                    hourly_stats = temporal_analysis['hourly_stats']
                                    
                                    if not hourly_stats.empty:
                                        peak_hour = temporal_analysis['peak_hour']
                                        st.metric("⏰ Heure de pointe", f"{peak_hour}h")
                                        st.metric("🔥 Max votes/heure", hourly_stats.max())
                                        
                                        # Créer des créneaux
                                        morning = hourly_stats[hourly_stats.index.isin(range(6, 12))].sum()
                                        afternoon = hourly_stats[hourly_stats.index.isin(range(12, 18))].sum()
                                        evening = hourly_stats[hourly_stats.index.isin(range(18, 24))].sum()
                                        night = hourly_stats[hourly_stats.index.isin(range(0, 6))].sum()
                                        
                                        st.write("**🕐 Répartition par créneau :**")
                                        st.write(f"🌅 Matin (6h-12h): {morning} votes")
                                        st.write(f"☀️ Après-midi (12h-18h): {afternoon} votes")
                                        st.write(f"🌆 Soirée (18h-24h): {evening} votes")
                                        st.write(f"🌙 Nuit (0h-6h): {night} votes")
                                        
                                        # Créneau le plus actif
                                        periods = [('Matin', morning), ('Après-midi', afternoon), ('Soirée', evening), ('Nuit', night)]
                                        most_active = max(periods, key=lambda x: x[1])
                                        st.success(f"🏆 Créneau le plus actif: **{most_active[0]}** ({most_active[1]} votes)")
                            
                            else:
                                st.info("💡 Pas assez de données temporelles pour l'analyse")
                        
                        else:
                            st.info("💡 Analyse temporelle non disponible (pas de timestamps)")
                
                # ==================== EXPORT AVANCÉ ====================
                
                st.markdown("---")
                st.header("📤 Export et sauvegarde")
                
                col_export1, col_export2, col_export3 = st.columns(3)
                
                with col_export1:
                    # Export des statistiques enrichies
                    csv_stats_enriched = stats_df.drop(['Score'], axis=1, errors='ignore').to_csv(index=False)
                    st.download_button(
                        label="📊 Stats enrichies (CSV)",
                        data=csv_stats_enriched,
                        file_name=f"stats_enrichies_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                
                with col_export2:
                    # Export des votes bruts avec métadonnées
                    votes_with_metadata = votes_df.copy()
                    if 'timestamp' in votes_with_metadata.columns:
                        votes_with_metadata['date'] = votes_with_metadata['timestamp'].dt.date
                        votes_with_metadata['hour'] = votes_with_metadata['timestamp'].dt.hour
                    
                    votes_csv_enriched = votes_with_metadata.to_csv(index=False)
                    st.download_button(
                        label="🗃️ Votes enrichis (CSV)",
                        data=votes_csv_enriched,
                        file_name=f"votes_enrichis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                
                with col_export3:
                    # Rapport de synthèse
                    rapport_synthese = f"""# RAPPORT DE SYNTHÈSE - {datetime.now().strftime('%Y-%m-%d %H:%M')}

## 📊 Vue d'ensemble
- Total votes: {len(votes_df)}
- Utilisateurs uniques: {votes_df['user_session_id'].nunique()}
- Modèles actifs: {len(stats_df)}
- Taux d'égalités: {(len(votes_df[votes_df['vote'] == 'tie']) / len(votes_df) * 100):.1f}%

## 🏆 Classement des modèles
"""
                    
                    for i, (_, row) in enumerate(stats_df.head(5).iterrows()):
                        medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."
                        rapport_synthese += f"{medal} {row['Modèle']}: {row['Taux victoire']} ({row['Victoires']}/{row['Total']})\n"
                    
                    if summary_cards:
                        rapport_synthese += f"""
## 🏆 Champions par catégorie
- Plus victorieux: {summary_cards['plus_victorieux']}
- Plus rapide: {summary_cards['plus_rapide']}
- Plus économique: {summary_cards['moins_cher']}
"""
                    
                    st.download_button(
                        label="📋 Rapport de synthèse",
                        data=rapport_synthese,
                        file_name=f"rapport_synthese_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                        mime="text/markdown",
                        use_container_width=True
                    )
            
            else:
                st.warning("⚠️ Aucune statistique disponible")
        
        else:
            st.warning("⚠️ Aucun vote dans la base de données")
            st.info("💡 Utilisez d'abord l'app de comparaison pour générer des votes")
            
            # Afficher un exemple amélioré
            st.markdown("---")
            st.subheader("👀 Aperçu du dashboard enrichi (exemple)")
            
            # Données d'exemple plus complètes
            example_data = {
                'Modèle': ['Claude 3.7 Sonnet', 'Claude 3.5 Haiku', 'Perplexity AI'],
                'Victoires': [15, 12, 8],
                'Défaites': [8, 10, 15],
                'Égalités': [2, 3, 2],
                'Total': [25, 25, 25],
                'Taux victoire': ['60.0%', '48.0%', '32.0%'],
                'Coût moyen': ['$0.003456', '$0.002134', '$0.001987'],
                'Temps moyen': ['2.3s', '1.8s', '3.1s'],
                'Efficacité': ['4340', '5629', '4024']
            }
            
            example_df = pd.DataFrame(example_data)
            
            # Appliquer le style d'exemple
            def style_example(row):
                if row.name == 0:
                    return ['background-color: #28a745; color: black; font-weight: bold'] * len(row)
                elif row.name == 1:
                    return ['background-color: #17a2b8; color: white; font-weight: bold'] * len(row)
                elif row.name == 2:
                    return ['background-color: #ffc107; color: black; font-weight: bold'] * len(row)
                else:
                    return [''] * len(row)
            
            styled_example = example_df.style.apply(style_example, axis=1)
            st.dataframe(styled_example, use_container_width=True, hide_index=True)
            
            st.success("🎯 Une fois que vous aurez des votes, le dashboard affichera des analyses détaillées comme celle-ci !")
    
    else:
        st.error("❌ Connexion Firebase échouée")
        st.info("💡 Vérifiez votre configuration Firebase dans les secrets/variables d'environnement")

else:
    st.error("❌ Firebase non disponible")
    st.info("💡 Installez Firebase : `pip install firebase-admin`")

# ==================== FOOTER ENRICHI ====================

st.markdown("---")

# Statistiques du dashboard
col_footer1, col_footer2, col_footer3 = st.columns(3)

with col_footer1:
    st.caption("📊 **Dashboard Analytics**")
    st.caption("Assistant Juridique IA")

with col_footer2:
    st.caption(f"🔄 **Dernière MAJ**")
    st.caption(f"{datetime.now().strftime('%H:%M:%S')}")

with col_footer3:
    st.caption("💾 **Stockage**")
    st.caption("Firebase Firestore")

st.markdown(f"""
<div style='text-align: center; color: #666; font-size: 0.8em; margin-top: 20px;'>
    <p>🚀 Dashboard sans graphiques - Optimisé pour la performance</p>
    <p>📈 Analyse complète des performances des modèles IA</p>
</div>
""", unsafe_allow_html=True)