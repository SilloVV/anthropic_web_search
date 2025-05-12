import anthropic
from dotenv import load_dotenv
import sys

load_dotenv()

client = anthropic.Anthropic()

# Paramètres de la requête
model = "claude-3-7-sonnet-latest"
max_tokens = 1024
temperature = 1
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
        "text": "Tu dois toujours respecter la vie privée et la confidentialité des utilisateurs.\n",
    }
]
messages = [
    {
        "role": "user",
        "content": "est-ce qu'un enfant peut être commerçant ?"
    }
]
tools = [{
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 3,
    "allowed_domains": ["www.legifrance.gouv.fr", "annuaire-entreprises.data.gouv.fr"],
    # "blocked_domains": [""],
}]

# Variable pour capturer le texte complet
complete_response_text = ""

# Démarrer le streaming
print("\n=== RÉPONSE EN STREAMING ===")

with client.messages.stream(
    model=model,
    max_tokens=max_tokens,
    temperature=temperature,
    system=system,
    messages=messages,
    tools=tools
) as stream:
    # Utiliser directement le text_stream au lieu de parcourir les événements
    for text in stream.text_stream:
        complete_response_text += text
        print(text, end="", flush=True)
    
    # Récupérer le message final
    final_message = stream.get_final_message()

# Récupérer les informations d'utilisation après la fin du streaming
print("\n\n=== STATISTIQUES D'UTILISATION ===")

# Les statistiques d'utilisation sont disponibles dans la réponse finale
usage = final_message.usage
input_tokens = usage.input_tokens if usage else "Non disponible"
output_tokens = usage.output_tokens if usage else "Non disponible"
web_search_requests = usage.server_tool_use.web_search_requests if usage and usage.server_tool_use else "Non disponible"

print(f"Input Tokens: {input_tokens}")
print(f"Output Tokens: {output_tokens}")
print(f"Web Search Requests: {web_search_requests}")
print(f"Raison d'arrêt: {final_message.stop_reason}")

# Afficher le contenu bloc par bloc comme dans votre code original
for i, block in enumerate(final_message.content):
    # Afficher les citations si présentes
    if hasattr(block, 'citations') and block.citations:
        print("\nCITATIONS:")
        for j, citation in enumerate(block.citations):
            print(f"  Citation #{j+1}:")
            if hasattr(citation, 'title'):
                print(f"    Titre: {citation.title}")
            if hasattr(citation, 'url'):
                print(f"    URL: {citation.url}")
            if hasattr(citation, 'cited_text'):
                print(f"    Extrait: {citation.cited_text[:150]}...")