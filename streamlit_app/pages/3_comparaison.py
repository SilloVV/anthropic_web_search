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
from datetime import datetime
import uuid
import hashlib

# Configuration de la page Streamlit - DOIT ÊTRE EN PREMIER
st.set_page_config(
    page_title="Assistant Juridique Français - Comparaison Multi-Modèles",
    page_icon="⚖️",
    layout="wide"
)

# Firebase imports
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    st.warning("⚠️ Firebase non installé. Mode local uniquement. Installez avec: pip install firebase-admin")

# Chargement des variables d'environnement
load_dotenv()

# ==================== FIREBASE CONFIGURATION ====================

def init_firebase():
    """Initialise la connexion Firebase"""
    if not FIREBASE_AVAILABLE:
        return None
    
    try:
        # Vérifier si Firebase est déjà initialisé
        if firebase_admin._apps:
            return firestore.client()
        
        # Récupérer les credentials depuis les variables d'environnement
        cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
        project_id = os.getenv("FIREBASE_PROJECT_ID")
        
        # Debug : afficher les valeurs
        if not cred_path:
            st.error("❌ FIREBASE_CREDENTIALS_PATH non défini dans .env")
            return None
            
        if not project_id:
            st.error("❌ FIREBASE_PROJECT_ID non défini dans .env")
            return None
            
        # Vérifier que le fichier existe
        if not os.path.exists(cred_path):
            st.error(f"❌ Fichier credentials introuvable : {cred_path}")
            st.info(f"📁 Répertoire actuel : {os.getcwd()}")
            if os.path.exists('./firebase'):
                st.info(f"📁 Fichiers dans firebase/ : {os.listdir('./firebase')}")
            else:
                st.info("📁 Dossier firebase/ inexistant")
            return None
        
        # Vérifier que le fichier JSON est valide
        try:
            with open(cred_path, 'r') as f:
                cred_data = json.load(f)
                if cred_data.get('project_id') != project_id:
                    st.warning(f"⚠️ Project ID dans credentials ({cred_data.get('project_id')}) != .env ({project_id})")
        except json.JSONDecodeError:
            st.error(f"❌ Fichier JSON credentials invalide : {cred_path}")
            return None
        
        # Initialiser Firebase
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred, {
            'projectId': project_id,
        })
        
        # Tester la connexion
        db = firestore.client()
        
        # Test simple : essayer de lire une collection
        try:
            test_collection = db.collection('test')
            list(test_collection.limit(1).stream())
            st.success("✅ Firebase connecté avec succès !")
        except Exception as test_error:
            st.error(f"❌ Test de connexion Firebase échoué : {str(test_error)}")
            return None
        
        return db
    
    except Exception as e:
        st.error(f"❌ Erreur d'initialisation Firebase : {str(e)}")
        return None

def get_session_id():
    """Génère ou récupère l'ID de session unique"""
    if 'session_id' not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    return st.session_state.session_id

def create_question_hash(question):
    """Crée un hash unique pour une question"""
    return hashlib.md5(question.encode()).hexdigest()[:16]

def save_vote_to_firebase(db, exchange_id, vote_choice, question, model_left, model_right, response_left=None, response_right=None, stats_left=None, stats_right=None):
    """Sauvegarde un vote dans Firebase avec les réponses et métriques"""
    if not db:
        return False
    
    try:
        session_id = get_session_id()
        question_hash = create_question_hash(question)
        
        vote_data = {
            "exchange_id": exchange_id,
            "question": question,
            "question_hash": question_hash,
            "model_left": model_left,
            "model_right": model_right,
            "vote": vote_choice,
            "timestamp": firestore.SERVER_TIMESTAMP,
            "user_session_id": session_id
        }
        
        # Ajouter la réponse du modèle de gauche
        if response_left:
            vote_data["response_left"] = response_left[:2000]  # Limiter à 2000 caractères
        
        # Ajouter la réponse du modèle de droite  
        if response_right:
            vote_data["response_right"] = response_right[:2000]  # Limiter à 2000 caractères
        
        # Ajouter les métriques du modèle de gauche
        if stats_left:
            vote_data["stats_left"] = {
                "response_time": stats_left.get("response_time", 0),
                "total_cost": stats_left.get("total_cost", 0),
                "input_tokens": stats_left.get("input_tokens", 0),
                "output_tokens": stats_left.get("output_tokens", 0),
                "web_searches": stats_left.get("web_searches", 0)
            }
        
        # Ajouter les métriques du modèle de droite
        if stats_right:
            vote_data["stats_right"] = {
                "response_time": stats_right.get("response_time", 0),
                "total_cost": stats_right.get("total_cost", 0),
                "input_tokens": stats_right.get("input_tokens", 0),
                "output_tokens": stats_right.get("output_tokens", 0),
                "web_searches": stats_right.get("web_searches", 0)
            }
        
        # Calculer le coût total combiné
        total_cost_combined = 0
        if stats_left:
            total_cost_combined += stats_left.get("total_cost", 0)
        if stats_right:
            total_cost_combined += stats_right.get("total_cost", 0)
        
        vote_data["total_cost_combined"] = total_cost_combined
        
        # Calculer le temps de réponse total
        total_response_time = 0
        if stats_left:
            total_response_time += stats_left.get("response_time", 0)
        if stats_right:
            total_response_time += stats_right.get("response_time", 0)
        
        vote_data["total_response_time"] = total_response_time
        
        doc_id = f"{session_id}_{exchange_id}"
        db.collection('votes').document(doc_id).set(vote_data)
        return True
        
    except Exception as e:
        st.error(f"❌ Erreur sauvegarde Firebase : {str(e)}")
        return False

def load_votes_from_firebase(db, session_id=None):
    """Charge les votes depuis Firebase"""
    if not db:
        return []
    
    try:
        query = db.collection('votes')
        if session_id:
            query = query.where('user_session_id', '==', session_id)
        
        docs = query.order_by('timestamp').stream()
        votes = []
        for doc in docs:
            data = doc.to_dict()
            if data.get('timestamp'):
                data['timestamp'] = data['timestamp'].isoformat()
            votes.append(data)
        
        return votes
        
    except Exception as e:
        st.error(f"❌ Erreur chargement Firebase : {str(e)}")
        return []

def get_firebase_stats(db):
    """Récupère les statistiques globales depuis Firebase"""
    if not db:
        return {}
    
    try:
        votes = load_votes_from_firebase(db)
        
        if not votes:
            return {}
        
        stats = {
            "total_votes": len(votes),
            "model_performance": {}
        }
        
        model_votes = {}
        
        for vote in votes:
            left_model = vote["model_left"]
            right_model = vote["model_right"]
            winner = vote["vote"]
            
            if left_model not in model_votes:
                model_votes[left_model] = {"wins": 0, "losses": 0, "ties": 0}
            if right_model not in model_votes:
                model_votes[right_model] = {"wins": 0, "losses": 0, "ties": 0}
            
            if winner == "tie":
                model_votes[left_model]["ties"] += 1
                model_votes[right_model]["ties"] += 1
            elif winner == left_model:
                model_votes[left_model]["wins"] += 1
                model_votes[right_model]["losses"] += 1
            elif winner == right_model:
                model_votes[right_model]["wins"] += 1
                model_votes[left_model]["losses"] += 1
        
        stats["model_performance"] = model_votes
        ties_total = sum(1 for vote in votes if vote["vote"] == "tie")
        stats["ties"] = ties_total
        
        return stats
        
    except Exception as e:
        st.error(f"❌ Erreur statistiques Firebase : {str(e)}")
        return {}

# ==================== FONCTIONS API ====================

def encode_pdf_to_base64(uploaded_file):
    """Encode un fichier PDF téléchargé en base64."""
    if uploaded_file is not None:
        base64_pdf = ""
        for file in uploaded_file:
            pdf_bytes = file.getvalue()
            base64_pdf += base64.b64encode(pdf_bytes).decode('utf-8')
        return base64_pdf
    return None

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
        
        content = ""
        sources = []
        
        for block in response.content:
            if block.type == "text":
                content += block.text
        
        for block in response.content:
            if hasattr(block, 'citations') and block.citations:
                for citation in block.citations:
                    source_info = {
                        "title": citation.title if hasattr(citation, 'title') else "Source",
                        "url": citation.url if hasattr(citation, 'url') else "",
                        "text": citation.cited_text if hasattr(citation, 'cited_text') else ""
                    }
                    sources.append(source_info)
        
        usage = response.usage
        input_tokens = usage.input_tokens if usage else 0
        output_tokens = usage.output_tokens if usage else 0
        web_search_requests = usage.server_tool_use.web_search_requests if usage and usage.server_tool_use else 0
        
        try:
            if "haiku" in model_name.lower():
                entry_cost = (int(input_tokens) / 1000000) * 0.8
                output_cost = (int(output_tokens) / 1000000) * 4
            else:
                entry_cost = (int(input_tokens) / 1000000) * 3
                output_cost = (int(output_tokens) / 1000000) * 15
            
            search_cost = (int(web_search_requests) / 1000) * 10
            total_cost = entry_cost + output_cost + search_cost
        except:
            entry_cost = output_cost = search_cost = total_cost = 0
        
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

def prepare_perplexity_messages(message_history, new_user_input):
    """Prépare les messages avec contexte limité aux 4 dernières interactions"""
    messages = [
        {
            "role": "system",
            "content": "Tu es un expert juridique français spécialisé dans le droit français. Tu réponds toujours en français et de manière précise."
        }
    ]
    
    recent_history = message_history[-8:] if len(message_history) > 8 else message_history
    
    for msg in recent_history:
        if msg["role"] in ["user", "assistant"]:
            content = msg["content"]
            if isinstance(content, list):
                content = next((item.get("text", "") for item in content 
                               if isinstance(item, dict) and item.get("type") == "text"), "")
            messages.append({
                "role": msg["role"],
                "content": content
            })
    
    messages.append({
        "role": "user",
        "content": new_user_input
    })
    
    return messages

async def process_perplexity_query(user_input, api_key, message_history=None):
    """Traite une requête avec Perplexity AI."""
    url = "https://api.perplexity.ai/chat/completions"
    
    messages = prepare_perplexity_messages(message_history or [], user_input)
    
    payload = {
        "temperature": 0.2,
        "top_p": 0.9,
        "return_images": False,
        "return_related_questions": False,
        "top_k": 0,
        "stream": False,
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
            
            content = data['choices'][0]['message']['content'] if 'choices' in data else ""
            
            input_tokens = data.get('usage', {}).get('prompt_tokens', 0)
            output_tokens = data.get('usage', {}).get('completion_tokens', 0)
            citations = data.get('citations', [])
            
            try:
                entry_cost = (int(input_tokens) / 1000000) * 1
                output_cost = (int(output_tokens) / 1000000) * 1
                search_cost = (1 / 1000) * 12
                total_cost = entry_cost + output_cost + search_cost
            except:
                entry_cost = output_cost = search_cost = total_cost = 0
            
            stats = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "web_searches": 1,
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
        
        api_messages = []
        for m in message_history:
            if m["role"] in ["user", "assistant"]:
                content = m["content"]
                if isinstance(content, list):
                    content = next((item.get("text", "") for item in content 
                                   if isinstance(item, dict) and item.get("type") == "text"), "")
                api_messages.append({"role": m["role"], "content": content})
        
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
        
        api_messages = []
        for m in message_history:
            if m["role"] in ["user", "assistant"]:
                content = m["content"]
                if isinstance(content, list):
                    content = next((item.get("text", "") for item in content 
                                   if isinstance(item, dict) and item.get("type") == "text"), "")
                api_messages.append({"role": m["role"], "content": content})
        
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
        clean_history = []
        for m in message_history:
            content = m["content"]
            if isinstance(content, list):
                content = next((item.get("text", "") for item in content 
                               if isinstance(item, dict) and item.get("type") == "text"), "")
            if isinstance(content, str):
                clean_history.append({"role": m["role"], "content": content})
        
        return await process_perplexity_query(prompt, perplexity_key, clean_history)
    
    else:
        return None, None, f"Modèle {model_name} non supporté"

# ==================== SYSTÈME DE VOTE ====================

def init_voting_system():
    """Initialise le système de vote dans session_state"""
    if 'votes' not in st.session_state:
        st.session_state.votes = {}
    if 'vote_history' not in st.session_state:
        st.session_state.vote_history = []
    if 'firebase_enabled' not in st.session_state:
        st.session_state.firebase_enabled = FIREBASE_AVAILABLE
    if 'firebase_db' not in st.session_state:
        st.session_state.firebase_db = None

def create_exchange_id(question_index):
    """Crée un ID unique pour un échange de questions/réponses"""
    return f"exchange_{question_index}"

def cast_vote(exchange_id, vote_choice, question, model_left, model_right):
    """Enregistre un vote localement et dans Firebase"""
    vote_data = {
        "exchange_id": exchange_id,
        "question": question,
        "model_left": model_left,
        "model_right": model_right,
        "vote": vote_choice,
        "timestamp": datetime.now().isoformat()
    }
    
    st.session_state.votes[exchange_id] = vote_data
    
    if not any(v["exchange_id"] == exchange_id for v in st.session_state.vote_history):
        st.session_state.vote_history.append(vote_data)
    else:
        for i, v in enumerate(st.session_state.vote_history):
            if v["exchange_id"] == exchange_id:
                st.session_state.vote_history[i] = vote_data
                break
    
    # Récupérer les réponses et stats correspondantes
    response_left = None
    response_right = None
    stats_left = None
    stats_right = None
    
    # Extraire l'index de l'échange depuis l'exchange_id
    try:
        exchange_index = int(exchange_id.split('_')[1])
        
        # Récupérer les réponses des assistants
        assistant_messages_left = [msg for msg in st.session_state.messages_left if msg["role"] == "assistant"]
        assistant_messages_right = [msg for msg in st.session_state.messages_right if msg["role"] == "assistant"]
        
        if exchange_index < len(assistant_messages_left):
            response_left = assistant_messages_left[exchange_index]["content"]
            stats_left = assistant_messages_left[exchange_index].get("stats")
        
        if exchange_index < len(assistant_messages_right):
            response_right = assistant_messages_right[exchange_index]["content"]
            stats_right = assistant_messages_right[exchange_index].get("stats")
            
    except (ValueError, IndexError):
        # Si on ne peut pas récupérer les données, on continue sans
        pass
    
    if st.session_state.firebase_enabled and st.session_state.firebase_db:
        success = save_vote_to_firebase(
            st.session_state.firebase_db, 
            exchange_id, 
            vote_choice, 
            question, 
            model_left, 
            model_right,
            response_left,
            response_right,
            stats_left,
            stats_right
        )
        if success:
            st.success("✅ Vote et données sauvegardés dans Firebase")
        else:
            st.warning("⚠️ Vote sauvegardé localement seulement")

def get_vote_stats(firebase_stats=False):
    """Calcule les statistiques des votes (local ou Firebase)"""
    if firebase_stats and st.session_state.firebase_db:
        return get_firebase_stats(st.session_state.firebase_db)
    
    if not st.session_state.vote_history:
        return {}
    
    stats = {
        "total_votes": len(st.session_state.vote_history),
        "model_performance": {}
    }
    
    model_votes = {}
    
    for vote in st.session_state.vote_history:
        left_model = vote["model_left"]
        right_model = vote["model_right"]
        winner = vote["vote"]
        
        if left_model not in model_votes:
            model_votes[left_model] = {"wins": 0, "losses": 0, "ties": 0}
        if right_model not in model_votes:
            model_votes[right_model] = {"wins": 0, "losses": 0, "ties": 0}
        
        if winner == "tie":
            model_votes[left_model]["ties"] += 1
            model_votes[right_model]["ties"] += 1
        elif winner == left_model:
            model_votes[left_model]["wins"] += 1
            model_votes[right_model]["losses"] += 1
        elif winner == right_model:
            model_votes[right_model]["wins"] += 1
            model_votes[left_model]["losses"] += 1
    
    stats["model_performance"] = model_votes
    
    ties_total = sum(1 for vote in st.session_state.vote_history if vote["vote"] == "tie")
    stats["ties"] = ties_total
    
    return stats

# ==================== INITIALISATION ====================

if 'messages_left' not in st.session_state:
    st.session_state.messages_left = []
if 'messages_right' not in st.session_state:
    st.session_state.messages_right = []
if 'uploaded_file' not in st.session_state:
    st.session_state.uploaded_file = None

init_voting_system()

if FIREBASE_AVAILABLE and st.session_state.firebase_enabled:
    if st.session_state.firebase_db is None:
        st.session_state.firebase_db = init_firebase()

# CSS personnalisé
st.markdown("""
<style>
:root {
    --bg-primary: #ffffff;
    --bg-secondary: #f8f9fa;
    --text-primary: #333333;
    --border-color: #e0e0e0;
    --shadow-color: rgba(0, 0, 0, 0.1);
}

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

@media (prefers-color-scheme: dark) {
    .error-box {
        background-color: rgba(139, 0, 0, 0.3);
        color: #ffb3b3;
        border-color: #8b0000;
    }
}

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

# ==================== INTERFACE PRINCIPALE ====================

st.title("Assistant Juridique Français - Comparaison Multi-Modèles 🇫🇷⚖️")
st.subheader("Comparaison côte à côte des modèles IA avec Firebase")

anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
perplexity_key = os.getenv("PERPLEXITY_API_KEY", "")

with st.sidebar:
    st.header("Configuration")
    
    st.subheader("🔥 Firebase")
    if FIREBASE_AVAILABLE:
        firebase_status = "🟢 Connecté" if st.session_state.firebase_db else "🔴 Non connecté"
        st.write(f"**Statut :** {firebase_status}")
        
        if st.session_state.firebase_db:
            st.write(f"**Session ID :** {get_session_id()[:8]}...")
            
            enable_firebase = st.checkbox("Activer Firebase", value=st.session_state.firebase_enabled)
            if enable_firebase != st.session_state.firebase_enabled:
                st.session_state.firebase_enabled = enable_firebase
                st.rerun()
        else:
            st.error("Vérifiez vos credentials Firebase")
    else:
        st.error("Firebase non installé")
    
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
            index=1,
            key="model_right"
        )
    
    vote_stats_local = get_vote_stats(firebase_stats=False)
    vote_stats_global = get_vote_stats(firebase_stats=True)
    
    if vote_stats_local or vote_stats_global:
        st.subheader("🗳️ Statistiques des votes")
        
        tab_local, tab_global = st.tabs(["📱 Mes votes", "🌍 Global"])
        
        with tab_local:
            if vote_stats_local:
                st.metric("Total", vote_stats_local["total_votes"])
                st.metric("Égalités", vote_stats_local["ties"])
                
                if vote_stats_local["model_performance"]:
                    st.write("**🏆 Performance :**")
                    for model, perf in vote_stats_local["model_performance"].items():
                        total = perf["wins"] + perf["losses"] + perf["ties"]
                        if total > 0:
                            win_rate = (perf["wins"] / total) * 100
                            st.write(f"**{model}:** {win_rate:.0f}% ({perf['wins']}/{total})")
            else:
                st.info("Aucun vote local")
        
        with tab_global:
            if vote_stats_global and st.session_state.firebase_db:
                st.metric("Total global", vote_stats_global["total_votes"])
                st.metric("Égalités", vote_stats_global["ties"])
                
                if vote_stats_global["model_performance"]:
                    st.write("**🏆 Performance globale :**")
                    
                    model_stats = []
                    for model, perf in vote_stats_global["model_performance"].items():
                        total = perf["wins"] + perf["losses"] + perf["ties"]
                        if total > 0:
                            win_rate = (perf["wins"] / total) * 100
                            model_stats.append((model, win_rate, perf["wins"], total))
                    
                    model_stats.sort(key=lambda x: x[1], reverse=True)
                    
                    for i, (model, win_rate, wins, total) in enumerate(model_stats):
                        medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "🏅"
                        st.write(f"{medal} **{model}:** {win_rate:.0f}% ({wins}/{total})")
            else:
                st.info("Pas de données globales")
    
    st.subheader("Paramètres avancés")
    temperature = st.slider("Temperature", 0.0, 1.0, 0.2, 0.1)
    max_tokens = st.slider("Tokens max", 500, 4000, 1500, 100)
    
    if model_left != "Perplexity AI" or model_right != "Perplexity AI":
        st.subheader("Document de référence")
        uploaded_file = st.file_uploader("Télécharger un PDF", type=["pdf"], accept_multiple_files=True)
        
        if uploaded_file is not None:
            st.session_state.uploaded_file = uploaded_file
            st.success(f"✅ {len(uploaded_file)} document(s) chargé(s)")
    else:
        st.session_state.uploaded_file = None
        st.info("📄 Perplexity n'accepte pas les documents PDF")
    
    st.subheader("🔑 Statut des clés API")
    if anthropic_key:
        st.success("✅ Clé Anthropic chargée depuis .env")
    else:
        st.error("❌ Clé ANTHROPIC_API_KEY manquante dans .env")
    
    if perplexity_key:
        st.success("✅ Clé Perplexity chargée depuis .env")
    else:
        st.error("❌ Clé PERPLEXITY_API_KEY manquante dans .env")
    
    debug_mode = st.checkbox("Mode debug", value=False)
    
    if st.button("🗑️ Vider l'historique local"):
        st.session_state.messages_left = []
        st.session_state.messages_right = []
        st.session_state.votes = {}
        st.session_state.vote_history = []
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

def display_messages(messages, model_name):
    for message in messages:
        with st.chat_message(message["role"]):
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
                text_content = next((item.get("text", "") for item in message["content"] 
                                   if isinstance(item, dict) and item.get("type") == "text"), "")
                st.markdown(f'<div class="response-container">{text_content}</div>', unsafe_allow_html=True)
                if any(item.get("type") == "document" for item in message["content"] if isinstance(item, dict)):
                    st.info("📎 Document PDF joint")
            else:
                st.markdown(f'<div class="response-container">{message["content"]}</div>', unsafe_allow_html=True)
            
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

def display_vote_interface(exchange_id, question, model_left, model_right):
    """Affiche l'interface de vote pour un échange donné"""
    current_vote = st.session_state.votes.get(exchange_id)
    
    st.markdown("### 🗳️ Quelle réponse préférez-vous ?")
    
    col_vote1, col_vote2, col_vote3 = st.columns(3)
    
    with col_vote1:
        if st.button(f"🥇 {model_left}", key=f"vote_left_{exchange_id}"):
            cast_vote(exchange_id, model_left, question, model_left, model_right)
            st.rerun()
    
    with col_vote2:
        if st.button("⚖️ Égalité", key=f"vote_tie_{exchange_id}"):
            cast_vote(exchange_id, "tie", question, model_left, model_right)
            st.rerun()
    
    with col_vote3:
        if st.button(f"🥇 {model_right}", key=f"vote_right_{exchange_id}"):
            cast_vote(exchange_id, model_right, question, model_left, model_right)
            st.rerun()
    
    if current_vote:
        if current_vote["vote"] == "tie":
            st.success("✅ Vous avez voté pour l'égalité")
        else:
            st.success(f"✅ Vous avez voté pour **{current_vote['vote']}**")

col1, col2 = st.columns(2)

with col1:
    st.header(f"🔵 {model_left}")
    display_messages(st.session_state.messages_left, model_left)

with col2:
    st.header(f"🔴 {model_right}")
    display_messages(st.session_state.messages_right, model_right)

def display_completed_votes():
    """Affiche les interfaces de vote pour tous les échanges terminés"""
    user_messages_left = [msg for msg in st.session_state.messages_left if msg["role"] == "user"]
    assistant_messages_left = [msg for msg in st.session_state.messages_left if msg["role"] == "assistant"]
    assistant_messages_right = [msg for msg in st.session_state.messages_right if msg["role"] == "assistant"]
    
    complete_exchanges = min(len(user_messages_left), len(assistant_messages_left), len(assistant_messages_right))
    
    for i in range(complete_exchanges):
        exchange_id = create_exchange_id(i)
        question_text = user_messages_left[i]["content"]
        
        if isinstance(question_text, list):
            question_text = next((item.get("text", "") for item in question_text 
                               if isinstance(item, dict) and item.get("type") == "text"), "Question avec document")
        
        display_question = question_text[:100] + "..." if len(question_text) > 100 else question_text
        
        with st.expander(f"🗳️ Vote pour l'échange {i+1}: {display_question}", expanded=False):
            display_vote_interface(exchange_id, question_text, model_left, model_right)

prompt = st.chat_input("Posez votre question juridique pour comparer les modèles...")

if prompt:
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
    
    async def process_both_models():
        with col1:
            with st.chat_message("assistant"):
                with st.spinner(f"🤔 {model_left} réfléchit..."):
                    if debug_mode:
                        st.write(f"🔍 Debug: Envoi de la requête à {model_left}...")
                    
                    pdf_for_left = pdf_data if model_left != "Perplexity AI" else None
                    
                    content_left, stats_left, error_left = await process_model_query(
                        model_left, 
                        prompt, 
                        st.session_state.messages_left[:-1],
                        anthropic_key, 
                        perplexity_key, 
                        max_tokens, 
                        temperature,
                        pdf_for_left
                    )
                    
                    if error_left:
                        st.markdown(f'<div class="error-box">❌ {error_left}</div>', unsafe_allow_html=True)
                    elif content_left:
                        st.markdown(f'<div class="response-container">{content_left}</div>', unsafe_allow_html=True)
                        
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
                        
                        st.session_state.messages_left.append({
                            "role": "assistant", 
                            "content": content_left,
                            "model": model_left,
                            "stats": stats_left
                        })
                    else:
                        st.error(f"❌ Aucune réponse reçue de {model_left}")
        
        with col2:
            with st.chat_message("assistant"):
                with st.spinner(f"🤔 {model_right} réfléchit..."):
                    if debug_mode:
                        st.write(f"🔍 Debug: Envoi de la requête à {model_right}...")
                    
                    pdf_for_right = pdf_data if model_right != "Perplexity AI" else None
                    
                    content_right, stats_right, error_right = await process_model_query(
                        model_right, 
                        prompt, 
                        st.session_state.messages_right[:-1],
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
                        
                        st.session_state.messages_right.append({
                            "role": "assistant", 
                            "content": content_right,
                            "model": model_right,
                            "stats": stats_right
                        })
                    else:
                        st.error(f"❌ Aucune réponse reçue de {model_right}")
        
        return stats_left, stats_right
    
    try:
        stats_left, stats_right = asyncio.run(process_both_models())
        
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
                
                if stats_left['total_cost'] > 0 and stats_right['total_cost'] > 0:
                    ratio = stats_right['total_cost'] / stats_left['total_cost']
                    if ratio > 1:
                        st.info(f"💡 {model_right} coûte {ratio:.1f}x plus cher que {model_left}")
                    else:
                        st.info(f"💡 {model_left} coûte {1/ratio:.1f}x plus cher que {model_right}")
    
    except Exception as e:
        st.error(f"Erreur lors du traitement parallèle: {str(e)}")
        if debug_mode:
            st.error(f"Debug - Erreur détaillée: {traceback.format_exc()}")

if len(st.session_state.messages_left) > 1 and len(st.session_state.messages_right) > 1:
    st.markdown("---")
    st.header("🗳️ Votez pour les meilleures réponses")
    display_completed_votes()



st.markdown("---")
st.markdown(f"""
<div style='text-align: center; color: #666; font-size: 0.9em;'>
    <p>🗳️ Vos votes sont sauvegardés {"dans Firebase" if st.session_state.firebase_enabled and st.session_state.firebase_db else "localement"}</p>
</div>
""", unsafe_allow_html=True)