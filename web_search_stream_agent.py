import anthropic
from dotenv import load_dotenv
import sys
import json

load_dotenv()

client = anthropic.Anthropic()

user_input = input("Entrez votre question : ")

# Paramètres de la requête
model = "claude-3-7-sonnet-latest"
max_tokens = 1500
temperature = 0.4
system = [
    {
        "type": "text",
        "text": "Tu es un assistant IA Français spécialisé dans le domaine du droit français.\n",
    },
    {
        "type": "text",
        "text": "Tu es capable de répondre à des questions juridiques et de fournir des conseils sur des sujets liés au droit français en citant des références en droit français.\n",
    },
    {
        "type": "text",
        "text": "Tu peux également effectuer des recherches sur le web pour trouver des informations juridiques pertinentes.\n",
    },
    {
        "type": "text",
        "text": "Important : Pour toutes tes réponses nécessitant des sources externes : Utilise systématiquement le format de citation suivant :<titre>Titre complet de la source</titre> <url>Lien exact vers la source</url><extrait>Extrait pertinent et concis de la source (limité à 2-3 phrases clés)</extrait> \n ",
    },
    {
        "type": "text",
        "text": "Tu dois toujours respecter la vie privée et la confidentialité des utilisateurs.\n",
    },
    {
        "type": "text",
        "text": "Retourne les sources pertinentes à la fin de ta réponse sous forme d'une liste avec titre et url.\n",
    },
]
messages = [
    {
        "role": "user",
        "content": user_input
    },  
]
tools = [{
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 2,
    "allowed_domains": ["www.legifrance.gouv.fr", "annuaire-entreprises.data.gouv.fr", "service-public.fr"],
    # "blocked_domains": [""],
}]

# Variable pour capturer le texte complet
complete_response_text = ""

# Démarrer le streaming
print("\n=== RÉPONSE EN STREAMING ===")

# Pour suivre si nous sommes au milieu d'une recherche web
current_search_query = ""
building_query = False
query_parts = []

with client.messages.stream(
    model=model,
    max_tokens=max_tokens,
    temperature=temperature,
    system=system,
    messages=messages,
    tools=tools
) as stream:
    # Parcourir tous les événements de streaming
    for event in stream:
        # Traiter chaque type d'événement
        if event.type == "content_block_start":
            # Vérifier si c'est le début d'un bloc d'utilisation d'outil
            if hasattr(event, "content_block") and hasattr(event.content_block, "type"):
                if event.content_block.type == "server_tool_use" and event.content_block.name == "web_search":
                    building_query = True
                    query_parts = []
        
        elif event.type == "content_block_delta":
            # Si nous sommes en train de construire une requête
            if building_query and hasattr(event, "delta") and hasattr(event.delta, "type"):
                if event.delta.type == "input_json_delta" and hasattr(event.delta, "partial_json"):
                    query_parts.append(event.delta.partial_json)
            
            # Si c'est un delta de texte normal à afficher
            elif hasattr(event, "delta") and hasattr(event.delta, "type"):
                if event.delta.type == "text_delta" and hasattr(event.delta, "text"):
                    text = event.delta.text
                    complete_response_text += text
                    print(text, end="", flush=True)
        
        elif event.type == "content_block_stop":
            # Si nous terminons la construction d'une requête de recherche
            if building_query:
                building_query = False
                # Essayer de reconstituer et d'extraire la requête
                try:
                    query_json = "".join(query_parts)
                    # Si le JSON est complet
                    if query_json.startswith("{") and query_json.endswith("}"):
                        query_data = json.loads(query_json)
                        if "query" in query_data:
                            print(f"\n\033[33mJe recherche les mots clés '{query_data['query']}'...\033[0m\n")
                    else:
                        # Tenter d'extraire la requête à partir du JSON partiel
                        if "query" in query_json:
                            # Extraction approximative
                            query_start = query_json.find('"query"')
                            if query_start != -1:
                                query_text = query_json[query_start:].split('":', 1)[1].strip()
                                # Nettoyer la chaîne
                                query_text = query_text.strip('"').strip('}').strip('"')
                                print(f"\n\033[33mJe recherche les mots clés '{query_text}'...\033[0m\n")
                except Exception as e:
                    # En cas d'erreur de parsing, afficher une information générique
                    print(f"\n\033[33mRecherche en cours...\033[0m\n")
    
    # Récupérer le message final
    final_message = stream.get_final_message()

# Récupérer les informations d'utilisation après la fin du streaming
print("\n\n=== STATISTIQUES D'UTILISATION ===")

# Les statistiques d'utilisation sont disponibles dans la réponse finale
usage = final_message.usage
input_tokens = usage.input_tokens if usage else "Non disponible"
output_tokens = usage.output_tokens if usage else "Non disponible"
web_search_requests = usage.server_tool_use.web_search_requests if usage and usage.server_tool_use else 0

print(f" Input Tokens: {input_tokens}")
print(f" Output Tokens: {output_tokens}")
print(f" Web Search Requests: {web_search_requests}")
print(f" Raison d'arrêt: {final_message.stop_reason}")

# Afficher le contenu bloc par bloc comme dans votre code original
for i, block in enumerate(final_message.content):
    # Afficher les citations si présentes
    if hasattr(block, 'citations') and block.citations:
        for j, citation in enumerate(block.citations):
            if hasattr(citation, 'title'):
                print(f" Titre: {citation.title}")
                print(f"  Citation #{j+1}:")
            
            if hasattr(citation, 'url'):
                print(f"    URL: {citation.url}")
            if hasattr(citation, 'cited_text'):
                print(f"    Extrait: {citation.cited_text[:150]}...")