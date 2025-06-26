from grok3_client import client
from typing import Generator, Dict, Any, Union


import os
import requests
import json
from typing import Generator, Union, Dict, Any

def call_grok(model:str, query: str) -> Generator[Union[str, Dict[str, Any]], None, None]:
    """
    Générateur qui stream les réponses de l'API Grok et yielde le résultat final.
    
    Args:
        query (str): Question à poser
        
    Yields:
        str: Chunks de texte pendant le streaming
        Dict[str, Any]: Résultat final avec métriques
    """
    url = "https://api.x.ai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.getenv('GROK_API_KEY')}"
    }
    payload = {
        "messages": [
            {
                "role": "system", 
                "content": "You are an expert legal assistant who always answers in French."
            },
            {
                "role": "user",
                "content": query,
            }
        ],
        "model": model,
        "stream": True,
        "search_parameters": {
            "mode": "on",
            "return_citations": True,
            "sources": [
            { "type": "web", "allowed_websites": ["legifrance.gouv.fr", "juricaf.org"] },
            ]
            
            },
        
        }
    
    # Variables pour accumuler les données
    complete_text = ""
    citations = []
    
    try:
        # IMPORTANT: stream=True pour requests
        response = requests.post(url, headers=headers, json=payload, stream=True)
        response.raise_for_status()  # Lever une exception si erreur HTTP

        # Traiter chaque ligne de la réponse streaming
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                
                # Les données SSE commencent par "data: "
                if line_str.startswith('data: '):
                    json_str = line_str[6:]  # Enlever "data: "
                    
                    # Ignorer les messages de fin
                    if json_str.strip() == '[DONE]':
                        break
                    
                    try:
                        chunk_data = json.loads(json_str)
                        # Extraire le contenu textuel
                        if 'choices' in chunk_data and chunk_data['choices']:
                            choice = chunk_data['choices'][0]
                            if 'delta' in choice and 'content' in choice['delta']:
                                content = choice['delta']['content']
                                if content:
                                    complete_text += content
                                    yield content  # Yield du chunk de texte
                        
                        # Extraire les citations
                        if 'citations' in chunk_data and chunk_data['citations']:
                            citations.extend(chunk_data['citations'])
                        
                    except json.JSONDecodeError as e:
                        print(f"Erreur parsing JSON: {e} - Line: {json_str}")
                        continue
    
    except requests.exceptions.RequestException as e:
        yield {
            "type": "error",
            "message": f"Erreur API: {str(e)}"
        }
        return
    
    # Yield du résultat final
    yield {
        "type": "final_result",
        "complete_text": complete_text,
        "citations": citations
    }

# Fonction d'utilisation
def utiliser_grok_streaming(query: str):
    """Utilise le générateur de streaming Grok"""
    
    print(f"🤖 Question: {query}\n")
    print("📝 Réponse en cours...\n")
    
    chunks_received = []
    final_result = None
    
    for item in call_grok(query):
        if isinstance(item, dict):
            if item.get("type") == "final_result":
                final_result = item
                print(f"\n\n✅ Streaming terminé!")
                print(f"📊 Statistiques:")
                print(f"   • Texte: {len(item['complete_text'])} caractères")
                print(f"   • Tokens: {item['input_tokens']} → {item['output_tokens']}")
                print(f"   • Citations: {len(item['citations'])}")
                
            elif item.get("type") == "error":
                print(f"\n❌ Erreur: {item['message']}")
                return None
        else:
            # C'est un chunk de texte
            chunks_received.append(item)
            print(item, end='', flush=True)
    
    return final_result

# Exemple d'utilisation
if __name__ == "__main__":
    query = input("Entrez votre question: ")
    result = utiliser_grok_streaming(query)
    
    if result and result['citations']:
        print(f"\n📚 Citations:")
        for i, citation in enumerate(result['citations'], 1):
            print(f"   {i}. {citation}")

