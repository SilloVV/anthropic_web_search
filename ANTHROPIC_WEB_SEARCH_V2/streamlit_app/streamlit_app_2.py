import streamlit as st
import httpx
import json
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("PERPLEXITY_API_KEY", "")

# Configuration de la page Streamlit
st.set_page_config(
    page_title="Expert Juridique IA",
    page_icon="⚖️",
    layout="wide"
)

# Chargement des variables d'environnement
load_dotenv()

def init_session_state():
    """Initialise les variables de session"""
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    if 'api_key' not in st.session_state:
        st.session_state.api_key = os.getenv("PERPLEXITY_API_KEY", "")

def prepare_context_messages(message_history, new_user_input):
    """
    Prépare les messages avec contexte limité aux 4 dernières interactions
    
    Args:
        message_history: Liste des messages de st.session_state.messages
        new_user_input: Nouvelle question de l'utilisateur
    
    Returns:
        Liste des messages formatés pour l'API
    """
    messages = [
        {
            "role": "system",
            "content": (
                "Tu es un expert juridique français qui choisit de faire une recherche ou non selon la question posée."
            )
        }
    ]
    
    # Limiter aux 4 dernières interactions (= 8 derniers messages maximum)
    # 1 interaction = 1 message user + 1 message assistant
    recent_history = message_history[-8:] if len(message_history) > 8 else message_history
    
    # Ajouter l'historique récent
    for msg in recent_history:
        if msg["role"] in ["user", "assistant"]:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
                # On n'inclut pas les métadonnées dans l'API
            })
    
    # Ajouter la nouvelle question
    messages.append({
        "role": "user",
        "content": new_user_input
    })
    
    return messages

def count_context_stats(messages):
    """
    Compte les statistiques du contexte envoyé
    
    Returns:
        dict avec interactions et tokens approximatifs
    """
    user_messages = [m for m in messages if m["role"] == "user"]
    assistant_messages = [m for m in messages if m["role"] == "assistant"]
    
    # Estimation approximative des tokens (1 token ≈ 4 caractères)
    total_chars = sum(len(m["content"]) for m in messages)
    estimated_tokens = total_chars // 4
    
    return {
        "interactions": min(len(user_messages) - 1, 4),  # -1 car nouvelle question pas encore dans l'historique
        "total_messages": len(messages) - 1,  # -1 pour le système
        "estimated_input_tokens": estimated_tokens
    }

async def stream_perplexity_response(user_input, api_key, message_history=None):
    """Fonction asynchrone pour streamer la réponse de Perplexity avec contexte limité"""
    url = "https://api.perplexity.ai/chat/completions"
    
    # Préparer les messages avec contexte limité
    messages = prepare_context_messages(message_history or [], user_input)
    
    # Statistiques pour debugging/information
    context_stats = count_context_stats(messages)
    
    payload = {
        "temperature": 0.2,
        "top_p": 0.9,
        "return_images": False,
        "return_related_questions": True,
        "top_k": 0,
        "stream": True,
        "presence_penalty": 0,
        "frequency_penalty": 1,
        "web_search_options": {"search_context_size": "medium"},
        "model": "sonar",
        "messages": messages,  # Messages avec contexte limité
        "max_tokens": 1484,
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
    
    input_tokens = 0
    output_tokens = 0
    citations = []
    full_message = ""
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream('POST', url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    yield f"Erreur API: {response.status_code}", None, None, None, None
                    return
                
                async for line in response.aiter_lines():
                    if line.startswith('data: '):
                        data = line[6:]  # Enlever "data: "
                        if data != '[DONE]':
                            try:
                                chunk = json.loads(data)
                                
                                # Contenu du message (streaming)
                                if 'choices' in chunk and len(chunk['choices']) > 0:
                                    delta = chunk['choices'][0].get('delta', {})
                                    if 'content' in delta:
                                        message = delta['content']
                                        full_message += message
                                        yield message, None, None, None, None
                                
                                # Métadonnées (tokens, citations)
                                if 'usage' in chunk and chunk['usage']:
                                    input_tokens = chunk['usage'].get('prompt_tokens', 0)
                                    output_tokens = chunk['usage'].get('completion_tokens', 0)
                                
                                if 'citations' in chunk and chunk['citations']:
                                    citations = chunk['citations']
                                    
                            except json.JSONDecodeError:
                                continue
        
        # Retourner les métadonnées finales + stats contexte
        yield None, input_tokens, output_tokens, citations, context_stats
        
    except Exception as e:
        yield f"Erreur: {str(e)}", None, None, None, None

def main():
    """Fonction principale de l'application"""
    st.title("⚖️ Expert Juridique IA")
    st.markdown("Assistant juridique alimenté par Perplexity AI - **Contexte limité aux 4 dernières interactions**")
    
    # Initialisation des variables de session
    init_session_state()
    
    # Sidebar pour la configuration
    with st.sidebar:
        
       
        st.session_state.api_key = api_key
        
        # Informations sur le contexte
        st.markdown("---")
        st.subheader("🧠 Gestion du contexte")
        st.markdown("""
        - **Historique :** 4 dernières interactions
        - **Optimisation :** Équilibre contexte/coût
        - **Limite :** 8 messages max (4 user + 4 assistant)
        """)
        
        # Statistiques de la conversation actuelle
        total_interactions = len([m for m in st.session_state.messages if m["role"] == "user"])
        if total_interactions > 0:
            st.metric("Interactions totales", total_interactions)
            context_interactions = min(total_interactions, 4)
            st.metric("Dans le contexte", context_interactions)
            
            if total_interactions > 4:
                st.warning(f"🗂️ {total_interactions - 4} interactions anciennes exclues du contexte")
        
        if st.button("Effacer l'historique"):
            st.session_state.messages = []
            st.rerun()
        
        # Informations sur les coûts
        st.markdown("---")
        st.subheader("💰 Tarification")
        st.markdown("""
        - Input: $0.000001 / token
        - Output: $0.000005 / token  
        - Recherche web: $0.008 / requête
        - **Contexte limité = coûts maîtrisés**
        """)
    
    # Affichage de l'historique des messages
    for i, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            
            # Afficher les métadonnées si disponibles
            if message.get("metadata"):
                meta = message["metadata"]
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.caption(f"🔤 Tokens entrée: {meta['input_tokens']}")
                with col2:
                    st.caption(f"🔤 Tokens sortie: {meta['output_tokens']}")
                with col3:
                    cost = (meta['input_tokens'] * 0.000001 + 
                           meta['output_tokens'] * 0.000005 + 0.008)
                    st.caption(f"💰 Coût: ${cost:.4f}")
                

                # Afficher les citations
                if meta.get('citations'):
                    with st.expander("📚 Sources"):
                        for j, citation in enumerate(meta['citations'], 1):
                            st.markdown(f"{j}. {citation}")
    
    # Zone de saisie pour les questions
    if prompt := st.chat_input("Posez votre question juridique..."):
        if not st.session_state.api_key:
            st.error("Veuillez configurer votre clé API Perplexity dans la sidebar.")
            return
        
        # Ajouter le message utilisateur à l'historique
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Afficher le message utilisateur
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Afficher la réponse de l'assistant avec streaming
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            metadata_placeholder = st.empty()
            
            full_response = ""
            metadata = {}
            context_stats = {}
            
            # Exécuter la fonction asynchrone avec contexte
            async def run_streaming():
                nonlocal full_response, metadata, context_stats
                
                async for chunk, input_tokens, output_tokens, citations, ctx_stats in stream_perplexity_response(
                    prompt, st.session_state.api_key, st.session_state.messages[:-1]  # Exclut la nouvelle question
                ):
                    if chunk:
                        if chunk.startswith("Erreur"):
                            st.error(chunk)
                            return
                        full_response += chunk
                        message_placeholder.markdown(full_response + "▌")
                    elif input_tokens is not None:
                        # Métadonnées finales reçues
                        metadata = {
                            'input_tokens': input_tokens,
                            'output_tokens': output_tokens,
                            'citations': citations or []
                        }
                        context_stats = ctx_stats or {}
                
                # Affichage final sans curseur
                message_placeholder.markdown(full_response)
                
                # Afficher les métadonnées
                if metadata:
                    with metadata_placeholder.container():
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.caption(f"🔤 Tokens entrée: {metadata['input_tokens']}")
                        with col2:
                            st.caption(f"🔤 Tokens sortie: {metadata['output_tokens']}")
                        with col3:
                            cost = (metadata['input_tokens'] * 0.000001 + 
                                   metadata['output_tokens'] * 0.000005 + 0.008)
                            st.caption(f"💰 Coût: ${cost:.4f}")
                        

                        # Afficher les citations
                        if metadata.get('citations'):
                            with st.expander("📚 Sources"):
                                for i, citation in enumerate(metadata['citations'], 1):
                                    st.markdown(f"{i}. {citation}")
            
            # Exécuter la coroutine
            try:
                asyncio.run(run_streaming())
                
                # Ajouter la réponse à l'historique avec métadonnées et stats contexte
                if full_response:
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": full_response,
                        "metadata": metadata,
                        "context_stats": context_stats
                    })
            except Exception as e:
                st.error(f"Erreur lors de la génération de la réponse: {str(e)}")

if __name__ == "__main__":
    main()