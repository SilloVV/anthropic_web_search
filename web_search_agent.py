import anthropic
from dotenv import load_dotenv


load_dotenv()

client = anthropic.Anthropic()

response = client.messages.create(
    model="claude-3-7-sonnet-latest",
    max_tokens=1024,
    temperature=1,
     system=[
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
    ],
    messages=[
        {
            "role": "user",
            "content": "est-ce qu'un enfant peut être commerçant ?"
        }
    ],
    tools=[{
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 5,
        "allowed_domains": ["www.legifrance.gouv.fr", "annuaire-entreprises.data.gouv.fr",],
        # "blocked_domains": [""],
    }]
)



# Parse the response to extract the web search results
input_usage = response.usage.input_tokens
output_usage = response.usage.output_tokens
web_search_usage = response.usage.server_tool_use.web_search_requests


# Print the usage information
print(f"Input Tokens: {input_usage}")
print(f"Output Tokens: {output_usage}")
print(f"Web Search Requests: {web_search_usage}")
print(f"Raison d'arrêt: {response.stop_reason}")

first_thought = response.content[0].text
print(f"First Thought: {first_thought}")

# 2. Afficher le contenu principal bloc par bloc
print("\n=== CONTENU DE LA RÉPONSE ===")
for i, block in enumerate(response.content):
    print(f"\nBLOC #{i+1} - Type: {block.type}")
    
    # Afficher le texte du bloc
    if hasattr(block, 'text'):
        print(f"TEXTE:\n{block.text}")
    
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



