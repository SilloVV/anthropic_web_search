import anthropic
from dotenv import load_dotenv
import sys
import json
import datetime

# --- Configuration et Initialisation ---
load_dotenv()
try:
    client = anthropic.Anthropic()
except Exception as e:
    print(f"Erreur: Impossible d'initialiser le client Anthropic. Avez-vous défini votre ANTHROPIC_API_KEY dans un fichier .env ?")
    print(f"Détail de l'erreur: {e}")
    sys.exit(1)

# --- Définition des Outils Côté Client ---
def is_date_in_future(date_str: str) -> bool:
    """Vérifie si une date (au format YYYY-MM-DD) est strictement dans le futur."""
    try:
        target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise ValueError("Le format de la date doit être 'YYYY-MM-DD' et de type string.")
    today = datetime.datetime.now().date()
    return target_date > today

# Dictionnaire des outils locaux pour un accès facile par leur nom
available_tools = {
    "is_date_in_future": is_date_in_future,
}

# --- Définition du Schéma des Outils pour l'API ---
tools_schema = [
    {"type": "web_search_20250305", "name": "web_search"},
    {"name": "is_date_in_future", "description": "Compare une date (YYYY-MM-DD) avec la date actuelle. Retourne True si la date est dans le futur, sinon False.", "input_schema": {"type": "object", "properties": {"date_str": {"type": "string", "description": "La date à comparer au format YYYY-MM-DD."}}, "required": ["date_str"]}}
]

# --- Paramètres du Modèle et du Système ---

### MODÈLE MIS À JOUR SELON VOTRE DEMANDE ###
# Utilisation du modèle valide le plus récent de la famille Sonnet.
MODEL_NAME = "claude-3-7-sonnet-20250219"
MAX_TOKENS = 4096
TEMPERATURE = 0.3
SYSTEM_PROMPT = """
Tu es un assistant IA Français, expert reconnu en droit français.
Tu dois systématiquement utiliser l'outil de recherche web (`web_search`) pour trouver des informations à jour (articles de loi, jurisprudence) avant de répondre à une question de fond.
Tu réponds de manière formelle et structurée, en citant précisément tes sources.
Pour les sources, utilise impérativement le format :
<source>
  <titre>Titre complet de la source</titre>
  <url>Lien exact vers la source</url>
  <extrait>Extrait pertinent et concis de la source (2-3 phrases clés).</extrait>
</source>
En plus de tes compétences juridiques, tu peux répondre poliment aux salutations.
"""

# --- Boucle Principale de Conversation ---
def main():
    user_input = input("Entrez votre question : ")
    if not user_input:
        print("Aucune question fournie. Arrêt du programme.")
        return

    messages = [{"role": "user", "content": user_input}]

    while True:
        print("\n\033[34m--- Appel au modèle Claude ---\033[0m")
        
        try:
            with client.messages.stream(
                model=MODEL_NAME,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=tools_schema
            ) as stream:
                for event in stream:
                    if event.type == "content_block_delta" and event.delta.type == 'text_delta':
                        sys.stdout.write(event.delta.text)
                        sys.stdout.flush()

            final_message = stream.get_final_message()

        except anthropic.APIError as e:
            print(f"\n\033[31mERREUR API : {e}\033[0m")
            print("\nSi l'erreur est 'not_found_error', cela peut signifier que votre clé API n'a pas encore accès à ce modèle ou à ses outils.")
            print("Dans ce cas, essayez avec 'claude-3-opus-20240229'.")
            break
        except Exception as e:
            print(f"\n\033[31mUne erreur inattendue est survenue : {e}\033[0m")
            break

        print(f"\n\n\033[32mRaison de l'arrêt: {final_message.stop_reason}\033[0m")

        if final_message.stop_reason in ["end_turn", "stop_sequence"]:
            print("\n\033[32mConversation terminée.\033[0m")
            break

        elif final_message.stop_reason == "tool_use":
            print("\033[33mLe modèle a utilisé des outils. Traitement en cours...\033[0m")
            messages.append({"role": "assistant", "content": final_message.content})
            
            tool_results_content = []
            
            for tool_call in final_message.content:
                if tool_call.type == "tool_use" and tool_call.name in available_tools:
                    tool_name = tool_call.name
                    tool_input = tool_call.input
                    tool_use_id = tool_call.id
                    
                    print(f"-> Exécution de l'outil local '{tool_name}'...")
                    tool_function = available_tools[tool_name]
                    try:
                        result = tool_function(**tool_input)
                        tool_results_content.append({"type": "tool_result", "tool_use_id": tool_use_id, "content": str(result)})
                    except Exception as e:
                        tool_results_content.append({"type": "tool_result", "tool_use_id": tool_use_id, "is_error": True, "content": f"Erreur: {e}"})

            if tool_results_content:
                messages.append({"role": "user", "content": tool_results_content})
                print("\033[34mRésultats des outils locaux envoyés au modèle pour la synthèse finale.\033[0m")

if __name__ == "__main__":
    main()