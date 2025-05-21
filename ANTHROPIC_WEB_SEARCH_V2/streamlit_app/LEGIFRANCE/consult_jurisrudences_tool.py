from LEGIFRANCE.legifrance_init import obtain_legifrance_token
import requests
import json
from typing import List


# Variables
BASE_URL = "https://sandbox-api.piste.gouv.fr/dila/legifrance/lf-engine-app"


def consult_juri_text(id:str)->str:
    """
    Récupère le texte d'un article juridique à partir de son ID.
    
    À utiliser dans le cas où l'on dispose d'un id commencçant par 'JURITEXT' . 
    
    Args:
        id (str): L'ID du texte JURI à récupérer.

    Returns:
        str: Le texte de l'article.
    """
    # URL de l'API Légifrance
    url = f"{BASE_URL}/consult/juri"
    
    # Obtenir le token d'authentification 
    token = obtain_legifrance_token()
    
    # Créer le payload pour la requête
    payload = {
        "textId":id,
    }
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "accept": "application/json"
    }
     
    
    response = requests.post(f"{url}",
                                    json=payload,
                                    headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        
        # Sauvegarder les résultats dans un fichier JSON
        with open("consult_juri_text_results.json", "w", encoding="utf-8") as json_file:
            json.dump(data, json_file, ensure_ascii=False, indent=4)
        return data.get('text', '')
    else:
        print(f"Erreur lors de la récupération du texte : {response.status_code}")
        return ""
    
def consult_multiple_juri_text(id_list: List[str]) -> List[str]:
    """
    Récupère le texte d'une liste d'articles juridiques à partir de leurs IDs.
    
    À utiliser dans le cas où l'on dispose d'une liste d'id commencçant par 'JURITEXT' .
    
    Args:
        id_list (List[str]): Liste des IDs des textes JURI à récupérer.

    Returns:
        List[str]: Liste des textes des articles.
    """
    texts = []
    for id in id_list:
        text = consult_juri_text(id)
        if text:
            texts.append(text)
    return texts
    