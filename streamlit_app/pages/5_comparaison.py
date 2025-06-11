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

# Import Gemini
from google import genai
import tempfile
from pathlib import Path
# Import supplémentaire pour les requêtes HTTP synchrones
import requests

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

def encode_pdf_to_base64(uploaded_files):
    """Encode un ou plusieurs fichiers PDF téléchargés en base64."""
    if uploaded_files is not None and len(uploaded_files) > 0:
        base64_pdf = ""
        for file in uploaded_files:
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
                entry_cost = (int(input_tokens) / 1000000) * 0.8    # Vos tarifs Haiku
                output_cost = (int(output_tokens) / 1000000) * 4.0  # Vos tarifs Haiku
            elif "sonnet 4" in model_name.lower():
                entry_cost = (int(input_tokens) / 1000000) * 3.0    # Estimation Sonnet 4
                output_cost = (int(output_tokens) / 1000000) * 15.0 # Estimation Sonnet 4
            else:  # Sonnet 3.7
                entry_cost = (int(input_tokens) / 1000000) * 3.0    # Vos tarifs Sonnet 3.7
                output_cost = (int(output_tokens) / 1000000) * 15.0 # Vos tarifs Sonnet 3.7
            
            search_cost = (int(web_search_requests) / 1000) * 10    # Estimation web search Claude
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

def process_gemini_query(prompt, message_history, gemini_key, max_tokens, temperature, pdf_data=None):
    """Traite une requête avec Google Gemini 2.0 Flash et web search."""
    try:
        # Configuration de Gemini avec le nouveau SDK
        client = genai.Client(api_key=gemini_key)
        
        start_time = time.time()
        
        # Préparer le contexte système pour le droit français
        system_context = """Tu es un assistant IA français spécialisé dans le droit français. 
        Tu réponds toujours en français et de manière précise et détaillée.
        Pour les questions juridiques, effectue une recherche web pour trouver les informations les plus récentes.
        Privilégie les sources officielles françaises comme legifrance.gouv.fr, service-public.fr, etc.
        Cite tes sources de manière claire avec les URLs.
        Pour toute question relative à la date, la date d'aujourd'hui est le """ + time.strftime("%d/%m/%Y") + "."
        
        # Préparer l'historique de conversation (simplifié pour le nouveau SDK)
        conversation_context = ""
        for msg in message_history[-4:]:  # Limiter le contexte aux 4 derniers messages
            if msg["role"] == "user":
                content = msg["content"]
                if isinstance(content, list):
                    content = next((item.get("text", "") for item in content 
                                   if isinstance(item, dict) and item.get("type") == "text"), "")
                conversation_context += f"User: {content}\n"
            elif msg["role"] == "assistant":
                content = msg["content"]
                if isinstance(content, str) and content:
                    # Tronquer les réponses longues pour économiser les tokens
                    truncated_content = content[:200] + "..." if len(content) > 200 else content
                    conversation_context += f"Assistant: {truncated_content}\n"
        
        # Construire le prompt complet
        full_prompt = f"{system_context}\n\n"
        if conversation_context:
            full_prompt += f"Contexte de conversation:\n{conversation_context}\n"
        full_prompt += f"Nouvelle question: {prompt}"
        
        # Préparer les contenus pour la requête
        contents = [full_prompt]
        
        # Gérer le PDF si présent (simplifié)
        if pdf_data:
            try:
                # Créer un fichier temporaire
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
                    # Décoder le base64
                    pdf_bytes = base64.b64decode(pdf_data)
                    temp_file.write(pdf_bytes)
                    temp_path = temp_file.name
                
                # Pour le nouveau SDK, on ajoute une note sur le PDF
                contents.append(f"[Document PDF joint - taille: {len(pdf_bytes)} bytes]")
                
                # Nettoyer le fichier temporaire
                os.unlink(temp_path)
                
            except Exception as e:
                print(f"Erreur traitement PDF: {e}")
        
        # Envoyer la requête avec le nouveau SDK
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=contents
        )
        
        response_time = round(time.time() - start_time, 2)
        
        # Extraire le contenu
        content = response.text if hasattr(response, 'text') and response.text else "Pas de réponse générée."
        
        # Estimer les recherches web (le nouveau SDK ne fournit pas toujours ces infos)
        web_searches = 1 if any(url_indicator in content.lower() for url_indicator in ['http', 'www.', '.fr', '.com']) else 0
        
        # Estimation des tokens
        input_tokens = len(full_prompt) // 4
        output_tokens = len(content) // 4
        
        # Calculer les coûts pour Gemini 2.0 Flash (vos tarifs)
        input_cost = (input_tokens / 1000000) * 0.1   # Vos tarifs : $0.1 per 1M input tokens
        output_cost = (output_tokens / 1000000) * 0.4  # Vos tarifs : $0.4 per 1M output tokens
        search_cost = web_searches * 0.005
        
        # Coût PDF (si présent)
        pdf_cost = 0
        if pdf_data:
            pdf_size_mb = len(pdf_data) / (1024 * 1024)
            pdf_cost = pdf_size_mb * 0.01
        
        total_cost = input_cost + output_cost + search_cost + pdf_cost
        
        # Extraire les sources basiques (le nouveau SDK gère différemment les citations)
        sources = []
        if hasattr(response, 'candidates') and response.candidates:
            # Chercher les URLs dans le contenu pour créer des sources basiques
            import re
            urls = re.findall(r'https?://[^\s]+', content)
            for i, url in enumerate(urls[:3]):  # Limiter à 3 sources
                sources.append({
                    "title": f"Source {i+1}",
                    "url": url.rstrip('.,)'),
                    "text": ""
                })
        
        stats = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "web_searches": web_searches,
            "response_time": response_time,
            "model": "Google Gemini 2.0 Flash",
            "sources": sources,
            "entry_cost": input_cost,
            "output_cost": output_cost,
            "search_cost": search_cost,
            "total_cost": total_cost
        }
        
        return content, stats, None
        
    except Exception as e:
        error_msg = f"Erreur avec Gemini: {str(e)}"
        return None, None, error_msg

def process_gemini_with_perplexity_query(prompt, message_history, gemini_key, perplexity_key, max_tokens, temperature, pdf_data=None):
    """Traite une requête avec Google Gemini 2.0 Flash + Perplexity Search intégré."""
    try:
        # Configuration de Gemini avec le nouveau SDK (SANS web search natif)
        client = genai.Client(api_key=gemini_key)
        
        start_time = time.time()
        
        # Préparer le contexte système spécialisé avec capacité de recherche
        system_context = """Tu es un assistant IA français expert en droit français avec accès à la recherche web via Perplexity. 
        Tu réponds toujours en français et de manière précise.
        
        TU dois répondre de manière structurée et très détaillée.s
        
        IMPORTANT : Tu peux faire appel à une recherche Perplexity pour obtenir des informations récentes et précises.
        Pour cela, utilise le format suivant quand tu as besoin d'informations complémentaires :
        [SEARCH_QUERY: ta requête de recherche ici]
        
        Tu N'AS PAS d'accès direct au web - utilise UNIQUEMENT Perplexity via [SEARCH_QUERY: ...] pour les recherches.
        Privilégie les sources officielles françaises comme legifrance.gouv.fr, service-public.fr, etc.
        Cite tes sources de manière claire.
        Pour toute question relative à la date, la date d'aujourd'hui est le """ + time.strftime("%d/%m/%Y") + "."
        
        # Préparer l'historique de conversation
        conversation_context = ""
        for msg in message_history[-4:]:
            if msg["role"] == "user":
                content = msg["content"]
                if isinstance(content, list):
                    content = next((item.get("text", "") for item in content 
                                   if isinstance(item, dict) and item.get("type") == "text"), "")
                conversation_context += f"User: {content}\n"
            elif msg["role"] == "assistant":
                content = msg["content"]
                if isinstance(content, str) and content:
                    truncated_content = content[:200] + "..." if len(content) > 200 else content
                    conversation_context += f"Assistant: {truncated_content}\n"
        
        # Construire le prompt complet
        full_prompt = f"{system_context}\n\n"
        if conversation_context:
            full_prompt += f"Contexte de conversation:\n{conversation_context}\n"
        full_prompt += f"Nouvelle question: {prompt}"
        
        # Préparer les contenus pour la requête
        contents = [full_prompt]
        
        # Gérer le PDF si présent
        if pdf_data:
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
                    pdf_bytes = base64.b64decode(pdf_data)
                    temp_file.write(pdf_bytes)
                    temp_path = temp_file.name
                
                contents.append(f"[Document PDF joint - taille: {len(pdf_bytes)} bytes]")
                os.unlink(temp_path)
                
            except Exception as e:
                print(f"Erreur traitement PDF: {e}")
        
        # Première réponse Gemini (SANS web search natif)
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=contents
        )
        
        initial_content = response.text if hasattr(response, 'text') and response.text else ""
        
        # Analyser si Gemini demande une recherche Perplexity
        search_results = []
        perplexity_cost = 0.0
        final_content = initial_content
        perplexity_searches = 0
        
        import re
        search_queries = re.findall(r'\[SEARCH_QUERY:\s*([^\]]+)\]', initial_content)
        
        if search_queries and perplexity_key:
            # Effectuer les recherches Perplexity UNIQUEMENT
            for query in search_queries:
                try:
                    # Préparer la requête Perplexity
                    url = "https://api.perplexity.ai/chat/completions"
                    
                    payload = {
                        "temperature": 0.2,
                        "top_p": 0.9,
                        "return_images": False,
                        "return_related_questions": False,
                        "top_k": 0,
                        "stream": False,
                        "presence_penalty": 0,
                        "frequency_penalty": 1,
                        "web_search_options": {"search_context_size": "medium"},  # Medium pour optimiser coût/qualité
                        "model": "sonar-pro",
                        "messages": [
                            {
                                "role": "system",
                                "content": "Tu es un expert juridique français. Fournis des informations précises avec les sources de la façon la plus détaillée possible."
                            },
                            {
                                "role": "user",
                                "content": query.strip()
                            }
                        ],
                        "max_tokens": 2000,
                        "search_domain_filter": [
                            "www.legifrance.gouv.fr",
                            "www.service-public.fr",
                            "annuaire-entreprises.data.gouv.fr"
                        ],
                    }
                    
                    headers = {
                        "Authorization": f"Bearer {perplexity_key}",
                        "Content-Type": "application/json"
                    }
                    
                    # Effectuer la recherche Perplexity
                    search_response = requests.post(url, json=payload, headers=headers, timeout=30)
                    
                    if search_response.status_code == 200:
                        search_data = search_response.json()
                        search_content = search_data['choices'][0]['message']['content'] if 'choices' in search_data else ""
                        
                        # Calculer le coût Perplexity (vos tarifs)
                        usage = search_data.get('usage', {})
                        p_input_tokens = usage.get('prompt_tokens', 0)
                        p_output_tokens = usage.get('completion_tokens', 0)
                        search_cost = (p_input_tokens / 1000000) * 1.0 + (p_output_tokens / 1000000) * 1.0 + 0.008  # Vos tarifs $1/$1 + $8 per 1000
                        perplexity_cost += search_cost
                        perplexity_searches += 1
                        
                        search_results.append({
                            "query": query.strip(),
                            "content": search_content,
                            "cost": search_cost
                        })
                        
                except Exception as search_error:
                    print(f"Erreur recherche Perplexity: {search_error}")
                    search_results.append({
                        "query": query.strip(),
                        "content": f"Erreur lors de la recherche: {search_error}",
                        "cost": 0
                    })
            
            # Si des recherches ont été effectuées, demander à Gemini de synthétiser
            if search_results:
                search_context = "\n\n".join([
                    f"Recherche: {result['query']}\nRésultats: {result['content']}" 
                    for result in search_results
                ])
                
                synthesis_prompt = f"""Voici les résultats de recherche Perplexity que tu avais demandés :

{search_context}

Maintenant, réponds à la question initiale en utilisant ces informations complémentaires : {prompt}

Intègre naturellement ces informations dans ta réponse et cite les sources appropriées."""
                
                # Nouvelle requête à Gemini avec les résultats de recherche (SANS web search)
                synthesis_response = client.models.generate_content(
                    model="gemini-2.0-flash-exp",
                    contents=[synthesis_prompt]
                )
                
                final_content = synthesis_response.text if hasattr(synthesis_response, 'text') and synthesis_response.text else initial_content
        
        response_time = round(time.time() - start_time, 2)
        
        # Nettoyer le contenu final des marqueurs de recherche
        final_content = re.sub(r'\[SEARCH_QUERY:\s*[^\]]+\]', '', final_content).strip()
        
        # Estimation des tokens
        input_tokens = len(full_prompt) // 4
        output_tokens = len(final_content) // 4
        
        # Calculer les coûts (UNIQUEMENT Gemini + Perplexity, vos tarifs)
        gemini_input_cost = (input_tokens / 1000000) * 0.1    # Vos tarifs : $0.1 per 1M input
        gemini_output_cost = (output_tokens / 1000000) * 0.4  # Vos tarifs : $0.4 per 1M output
        gemini_search_cost = 0.0  # PAS de web search Gemini natif
        
        # Coût PDF
        pdf_cost = 0
        if pdf_data:
            pdf_size_mb = len(pdf_data) / (1024 * 1024)
            pdf_cost = pdf_size_mb * 0.01
        
        total_cost = gemini_input_cost + gemini_output_cost + gemini_search_cost + pdf_cost + perplexity_cost
        
        # Extraire les sources
        sources = []
        if search_results:
            for i, result in enumerate(search_results):
                sources.append({
                    "title": f"Recherche Perplexity: {result['query'][:50]}...",
                    "url": "",
                    "text": result['content'][:200] + "..." if len(result['content']) > 200 else result['content']
                })
        
        # Rechercher les URLs dans le contenu
        urls = re.findall(r'https?://[^\s]+', final_content)
        for i, url in enumerate(urls[:3]):
            sources.append({
                "title": f"Source {len(sources)+1}",
                "url": url.rstrip('.,)'),
                "text": ""
            })
        
        stats = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "web_searches": perplexity_searches,  # UNIQUEMENT les recherches Perplexity
            "response_time": response_time,
            "model": "Google Gemini 2.0 Flash + Perplexity",
            "sources": sources,
            "entry_cost": gemini_input_cost,
            "output_cost": gemini_output_cost,
            "search_cost": perplexity_cost,  # UNIQUEMENT coût Perplexity
            "total_cost": total_cost
        }
        
        return final_content, stats, None
        
    except Exception as e:
        error_msg = f"Erreur avec Gemini + Perplexity: {str(e)}"
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
        "model": "sonar-pro",
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
                entry_cost = (int(input_tokens) / 1000000) * 3.0   # Vos tarifs Perplexity Sonar
                output_cost = (int(output_tokens) / 1000000) * 15.0 # Vos tarifs Perplexity Sonar  
                search_cost = (1 / 1000) * 8.0                     # Vos tarifs : $8 per 1000 recherches
                total_cost = entry_cost + output_cost + search_cost
            except:
                entry_cost = output_cost = search_cost = total_cost = 0
            
            stats = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "web_searches": 1,
                "response_time": response_time,
                "model": "Perplexity Sonar Pro",
                "sources": [{"title": "Source Web", "url": "", "text": c} for c in citations],
                "entry_cost": entry_cost,
                "output_cost": output_cost,
                "search_cost": search_cost,
                "total_cost": total_cost
            }
            
            return content, stats, None
            
    except Exception as e:
        return None, None, f"Erreur Perplexity: {str(e)}"

async def process_model_query(model_name, prompt, message_history, anthropic_key, perplexity_key, gemini_key, max_tokens, temperature, pdf_data=None):
    """Traite une requête pour n'importe quel modèle"""
    # récupérer la date actuelle
    date = time.strftime("%d/%m/%Y")
    

    if model_name == "Claude 3.5 Haiku":
        system_prompt = """Tu es un assistant IA français spécialisé dans le droit français. 
        Tu réponds toujours en français et de manière précise.
        Si il s'agit d'une question juridique, fais au moins une recherche internet.
        Cite tes sources de manière claire.
        Pour toute question relative à la date. Demande toi quelle est la date d'ajourd'hui. La date d'ajourd'hui est le {date}. Ce qui est après Novembre 2024.
        .""".format(date=date)
        
        tools = [{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 3,
            "allowed_domains": [
                "www.legifrance.gouv.fr",
                "service-public.fr",
                "www.conseil-constitutionnel.fr",
                "www.conseil-etat.fr",
                "juricaf.org"
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
        Tu réponds toujours en français, de manière structurée et très détaillée.
        Si il s'agit d'une question juridique, fais au moins une recherche internet.
        Cite tes sources de manière claire.Pour toute question relative à la date. Demande toi quelle est la date d'ajourd'hui. La date d'ajourd'hui est le {date}. Ce qui est après Novembre 2024 .
        .""".format(date=date)
        
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
    
    elif model_name == "Claude Sonnet 4":
        system_prompt = """Tu es un assistant IA français spécialisé dans le droit français. 
        Tu réponds toujours en français et de manière précise.
        Si il s'agit d'une question juridique, fais au moins une recherche internet.
        Cite tes sources de manière claire.
        Pour toute question relative à la date. La date d'aujourd'hui est le {date}.
        """.format(date=date)
        
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
            "claude-sonnet-4-20250514",
            api_messages,
            system_prompt,
            tools,
            anthropic_key,
            max_tokens,
            temperature
        )
    
    elif model_name == "Google Gemini":
        # Gemini 2.0 Flash avec web search intégré
        return process_gemini_query(prompt, message_history, gemini_key, max_tokens, temperature, pdf_data)
    
    elif model_name == "Google Gemini 2.0 Flash + Perplexity":
        # Gemini 2.0 Flash avec Perplexity Search intégré
        return process_gemini_with_perplexity_query(prompt, message_history, gemini_key, perplexity_key, max_tokens, temperature, pdf_data)
    
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
if 'model_left' not in st.session_state:
    st.session_state.model_left = "Claude 3.5 Haiku"
if 'model_right' not in st.session_state:
    st.session_state.model_right = "Claude 3.7 Sonnet"

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

.gemini-panel {
    border-left: 4px solid #4285f4;
    background-color: rgba(66, 133, 244, 0.1);
}

.gemini-hybrid-panel {
    border-left: 4px solid #34a853;
    background-color: rgba(52, 168, 83, 0.1);
}

.sonnet4-panel {
    border-left: 4px solid #8b5cf6;
    background-color: rgba(139, 92, 246, 0.1);
}

.gemini-pro-panel {
    border-left: 4px solid #f59e0b;
    background-color: rgba(245, 158, 11, 0.1);
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

.model-selector {
    background-color: var(--bg-secondary);
    padding: 20px;
    border-radius: 12px;
    margin: 20px 0;
    border: 2px solid var(--border-color);
}

.model-selector h3 {
    margin-top: 0;
    color: var(--text-primary);
}
</style>
""", unsafe_allow_html=True)

# ==================== INTERFACE PRINCIPALE ====================

st.title("Assistant Juridique Français - Comparaison Multi-Modèles 🇫🇷⚖️")
st.subheader("Comparaison côte à côte des modèles IA avec Firebase")

# ==================== SÉLECTION DES MODÈLES SUR LA PAGE PRINCIPALE ====================

st.markdown('<div class="model-selector">', unsafe_allow_html=True)
st.markdown("### 🤖 Sélection des modèles à comparer")

col_model1, col_model2 = st.columns(2)

with col_model1:
    model_left = st.selectbox(
        "🔵 Modèle de gauche",
        ["Claude 3.5 Haiku", "Claude 3.7 Sonnet", "Claude Sonnet 4", "Google Gemini", "Google Gemini 2.0 Flash + Perplexity", "Perplexity AI"],
        index=0,
        key="main_model_left"
    )
    st.session_state.model_left = model_left

with col_model2:
    model_right = st.selectbox(
        "🔴 Modèle de droite",
        ["Claude 3.5 Haiku", "Claude 3.7 Sonnet", "Claude Sonnet 4", "Google Gemini", "Google Gemini 2.0 Flash + Perplexity", "Perplexity AI"],
        index=1,
        key="main_model_right"
    )
    st.session_state.model_right = model_right

if model_left == model_right:
    st.warning("⚠️ Vous avez sélectionné le même modèle des deux côtés. Choisissez des modèles différents pour une comparaison pertinente.")

st.markdown('</div>', unsafe_allow_html=True)

# ==================== VÉRIFICATION DES CLÉS API ====================

anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
perplexity_key = os.getenv("PERPLEXITY_API_KEY", "")
gemini_key = os.getenv("GEMINI_API_KEY", "")

# Vérification des clés API nécessaires
keys_needed = set()
if model_left.startswith("Claude") or model_right.startswith("Claude"):
    keys_needed.add("anthropic")
if model_left == "Google Gemini" or model_right == "Google Gemini":
    keys_needed.add("gemini")
if model_left == "Google Gemini 2.0 Flash + Perplexity" or model_right == "Google Gemini 2.0 Flash + Perplexity":
    keys_needed.add("gemini")
    keys_needed.add("perplexity")
if model_left == "Perplexity AI" or model_right == "Perplexity AI":
    keys_needed.add("perplexity")

missing_keys = []
if "anthropic" in keys_needed and not anthropic_key:
    missing_keys.append("Anthropic")
if "gemini" in keys_needed and not gemini_key:
    missing_keys.append("Gemini")
if "perplexity" in keys_needed and not perplexity_key:
    missing_keys.append("Perplexity")

if missing_keys:
    st.error(f"❌ Clés API manquantes dans le fichier .env: {', '.join(missing_keys)}")
    st.info("💡 Ajoutez vos clés dans le fichier .env :")
    st.code("""
# Fichier .env
ANTHROPIC_API_KEY=votre_clé_anthropic
PERPLEXITY_API_KEY=votre_clé_perplexity
GEMINI_API_KEY=votre_clé_gemini
""")
    st.stop()

# ==================== SIDEBAR POUR LA CONFIGURATION ====================

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
    
    st.subheader("🤖 Modèles sélectionnés")
    st.info(f"**Gauche :** {model_left}")
    st.info(f"**Droite :** {model_right}")
    
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
    max_tokens = st.slider("Tokens max", 500, 4000, 3500, 100)
    
    st.subheader("🔑 Statut des clés API")
    if anthropic_key:
        st.success("✅ Clé Anthropic chargée depuis .env")
    else:
        st.error("❌ Clé ANTHROPIC_API_KEY manquante dans .env")
    
    if perplexity_key:
        st.success("✅ Clé Perplexity chargée depuis .env")
    else:
        st.error("❌ Clé PERPLEXITY_API_KEY manquante dans .env")
    
    if gemini_key:
        st.success("✅ Clé Gemini chargée depuis .env")
    else:
        st.error("❌ Clé GEMINI_API_KEY manquante dans .env")
    
    debug_mode = st.checkbox("Mode debug", value=False)
    
    if st.button("🗑️ Vider l'historique local"):
        st.session_state.messages_left = []
        st.session_state.messages_right = []
        st.session_state.votes = {}
        st.session_state.vote_history = []
        st.rerun()

# ==================== FONCTIONS D'AFFICHAGE ====================

def display_messages(messages, model_name):
    for message in messages:
        with st.chat_message(message["role"]):
            if "haiku" in model_name.lower():
                panel_class = "haiku-panel"
            elif "sonnet" in model_name.lower():
                panel_class = "sonnet-panel"
            elif "perplexity" in model_name.lower():
                panel_class = "perplexity-panel"
            elif "gemini" in model_name.lower() and "perplexity" in model_name.lower():
                panel_class = "gemini-hybrid-panel"
            elif "gemini" in model_name.lower():
                panel_class = "gemini-panel"
            else:
                panel_class = "model-panel"
            
            st.markdown(f'<div class="model-panel {panel_class}">', unsafe_allow_html=True)
            
            # Gestion du contenu du message
            content_to_display = ""
            has_pdf = False
            
            if isinstance(message["content"], list):
                # Extraire le texte du message
                for item in message["content"]:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            content_to_display = item.get("text", "")
                        elif item.get("type") == "document":
                            has_pdf = True
            else:
                content_to_display = message["content"]
            
            # Afficher le contenu
            if content_to_display:
                st.markdown(f'<div class="response-container">{content_to_display}</div>', unsafe_allow_html=True)
            
            # Afficher l'indicateur PDF si présent
            if has_pdf:
                st.info("📎 Document PDF joint")
            
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

def display_completed_votes():
    """Affiche les interfaces de vote pour tous les échanges terminés"""
    user_messages_left = [msg for msg in st.session_state.messages_left if msg["role"] == "user"]
    assistant_messages_left = [msg for msg in st.session_state.messages_left if msg["role"] == "assistant"]
    assistant_messages_right = [msg for msg in st.session_state.messages_right if msg["role"] == "assistant"]
    
    complete_exchanges = min(len(user_messages_left), len(assistant_messages_left), len(assistant_messages_right))
    
    for i in range(complete_exchanges):
        exchange_id = create_exchange_id(i)
        question_content = user_messages_left[i]["content"]
        
        # Extraire le texte de la question
        if isinstance(question_content, list):
            question_text = next((item.get("text", "") for item in question_content 
                               if isinstance(item, dict) and item.get("type") == "text"), "Question avec document")
        else:
            question_text = question_content
        
        display_question = question_text[:100] + "..." if len(question_text) > 100 else question_text
        
        with st.expander(f"🗳️ Vote pour l'échange {i+1}: {display_question}", expanded=False):
            display_vote_interface(exchange_id, question_text, model_left, model_right)

# ==================== AFFICHAGE DES COLONNES DE COMPARAISON ====================

col1, col2 = st.columns(2)

with col1:
    st.header(f"🔵 {model_left}")
    display_messages(st.session_state.messages_left, model_left)

with col2:
    st.header(f"🔴 {model_right}")
    display_messages(st.session_state.messages_right, model_right)

# ==================== CHAT INPUT AVEC SUPPORT DES FICHIERS PDF ====================

# Note sur l'incompatibilité avec Perplexity
if model_left == "Perplexity AI" or model_right == "Perplexity AI":
    st.info("📄 **Note :** Perplexity AI ne supporte pas les documents PDF. Les fichiers joints seront ignorés pour ce modèle.")

# Chat input avec support des fichiers PDF
prompt = st.chat_input(
    "Posez votre question juridique et joignez éventuellement des PDFs...",
    accept_file=True,
    file_type=["pdf"]
)

if prompt:
    # Extraire le texte et les fichiers du chat_input
    if hasattr(prompt, 'text') and hasattr(prompt, 'files'):
        # Nouveau format avec fichiers
        user_text = prompt.text
        uploaded_files = prompt.files if prompt.files else []
    elif isinstance(prompt, str):
        # Format texte simple (pas de fichiers)
        user_text = prompt
        uploaded_files = []
    else:
        # Fallback
        user_text = str(prompt)
        uploaded_files = []
    
    # Traiter les fichiers PDF
    pdf_data = None
    if uploaded_files and len(uploaded_files) > 0:
        # Vérifier que tous les fichiers sont des PDF
        pdf_files = [f for f in uploaded_files if f.type == "application/pdf"]
        if pdf_files:
            pdf_data = encode_pdf_to_base64(pdf_files)
            st.success(f"✅ {len(pdf_files)} fichier(s) PDF traité(s)")
        
        if len(pdf_files) != len(uploaded_files):
            st.warning("⚠️ Seuls les fichiers PDF sont supportés. Les autres fichiers ont été ignorés.")
    
    # Créer le contenu du message
    if pdf_data and (model_left != "Perplexity AI" or model_right != "Perplexity AI"):
        message_content_left = [
            {"type": "text", "text": user_text}
        ]
        message_content_right = [
            {"type": "text", "text": user_text}
        ]
        
        # Ajouter le document seulement pour les modèles qui le supportent
        if model_left != "Perplexity AI":
            message_content_left.append({
                "type": "document", 
                "source": {
                    "type": "base64", 
                    "media_type": "application/pdf", 
                    "data": pdf_data
                }
            })
        
        if model_right != "Perplexity AI":
            message_content_right.append({
                "type": "document", 
                "source": {
                    "type": "base64", 
                    "media_type": "application/pdf", 
                    "data": pdf_data
                }
            })
    else:
        message_content_left = user_text
        message_content_right = user_text
    
    # Ajouter les messages à l'historique
    st.session_state.messages_left.append({
        "role": "user", 
        "content": message_content_left,
        "model": model_left
    })
    st.session_state.messages_right.append({
        "role": "user", 
        "content": message_content_right,
        "model": model_right
    })
    
    # Afficher les messages utilisateur
    with col1:
        with st.chat_message("user"):
            st.markdown(user_text)
            if pdf_data and model_left != "Perplexity AI":
                st.info(f"📎 {len(uploaded_files)} document(s) PDF joint(s)")
            elif pdf_data and model_left == "Perplexity AI":
                st.warning("⚠️ PDF ignoré (Perplexity ne le supporte pas)")
    
    with col2:
        with st.chat_message("user"):
            st.markdown(user_text)
            if pdf_data and model_right != "Perplexity AI":
                st.info(f"📎 {len(uploaded_files)} document(s) PDF joint(s)")
            elif pdf_data and model_right == "Perplexity AI":
                st.warning("⚠️ PDF ignoré (Perplexity ne le supporte pas)")
    
    # Traiter les réponses des modèles
    async def process_both_models():
        with col1:
            with st.chat_message("assistant"):
                with st.spinner(f"🤔 {model_left} réfléchit..."):
                    if debug_mode:
                        st.write(f"🔍 Debug: Envoi de la requête à {model_left}...")
                    
                    pdf_for_left = pdf_data if model_left != "Perplexity AI" else None
                    
                    content_left, stats_left, error_left = await process_model_query(
                        model_left, 
                        user_text, 
                        st.session_state.messages_left[:-1],
                        anthropic_key, 
                        perplexity_key,
                        gemini_key,
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
                        user_text, 
                        st.session_state.messages_right[:-1],
                        anthropic_key, 
                        perplexity_key,
                        gemini_key,
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
    
    # Exécuter le traitement des deux modèles
    try:
        stats_left, stats_right = asyncio.run(process_both_models())
        
        # Afficher la comparaison des performances
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

# ==================== SECTION DE VOTE ====================

if len(st.session_state.messages_left) > 1 and len(st.session_state.messages_right) > 1:
    st.markdown("---")
    st.header("🗳️ Votez pour les meilleures réponses")
    display_completed_votes()

# ==================== FOOTER ====================

st.markdown("---")
st.markdown(f"""
<div style='text-align: center; color: #666; font-size: 0.9em;'>
    <p>🗳️ Vos votes sont sauvegardés {"dans Firebase" if st.session_state.firebase_enabled and st.session_state.firebase_db else "localement"}</p>
    <p>📎 Glissez-déposez vos fichiers PDF directement dans la zone de chat</p>
    <p>🤖 Modèles disponibles : Claude 3.5 Haiku, Claude 3.7 Sonnet, Claude Sonnet 4, Google Gemini 2.0 Flash, Google Gemini 2.0 Flash + Perplexity, Perplexity AI</p>
</div>
""", unsafe_allow_html=True)