# IMPORTS
import requests
from typing import Dict, List, Optional, Any, Union, Tuple
import datetime, json, time
import os
import sys

# Ajoutez le répertoire courant au chemin Python
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


# Pour récupérer le token d'authentification
from LEGIFRANCE.legifrance_init import obtain_legifrance_token



# Variables
BASE_URL = "https://sandbox-api.piste.gouv.fr/dila/legifrance/lf-engine-app"

def create_code_payload(numero_article:str, nom_code:str)->str:
    """
    Définit le payload pour la recherche d'un article dans le code
    
    Args:
        numero_article (str): Le numéro de l'article à rechercher
        nom_code (str): Le nom du code dans lequel rechercher l'article
    Returns:
        str: Le payload JSON pour la recherche
    
    """
    return {
    "recherche": {
        "champs": [
            {
                "typeChamp": "NUM_ARTICLE",
                "criteres": [
                    {
                        "typeRecherche": "TOUS_LES_MOTS_DANS_UN_CHAMP",
                        "valeur": numero_article,
                        "operateur": "ET",
                        "proximite": 5
                    }
                ],
                "operateur": "ET"
            }
        ],
        "filtres": [
            {
                "facette": "NOM_CODE",
                "valeurs": [
                    nom_code
                ]
            }
        ],
        "pageNumber": 1,
        "pageSize": 2,
        "operateur": "ET",
        "sort": "PERTINENCE",
        "typePagination": "ARTICLE"
    },
    "fond": "CODE_DATE"
}

#fonction utile
def multiple_code_search_api(
    liste_articles: List[Dict[str, str]],
) -> Optional[Dict[str, Any]]:
    """
    Fais une recherche multiple sur Legifrance à partir d'une liste d'articles.

    Args:
        liste_articles (List[Dict[str, str]]): Liste de dictionnaires avec clés:
            - "numero": numéro de l'article (ex. "L121.2")
            - "nom_code": nom du code (ex. "Code de commerce")
    Returns:
        Dict où chaque clé "<nom_code>-<numero>" mappe au JSON retourné,
        ou None si toutes les requêtes ont échoué.
    """
    retry_count = 3
    retry_delay = 1

    token = obtain_legifrance_token()
    url = f"{BASE_URL}/search"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    results: Dict[str, Any] = {}
    any_success = False

    for article in liste_articles:
        numero = article.get("numero")
        nom_code = article.get("nom_code")
        key = f"{nom_code}-{numero}"
        payload = create_code_payload(numero, nom_code)

        data = None
        for attempt in range(1, retry_count + 1):
            try:
                resp = requests.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                any_success = True
                break
            except requests.RequestException as err:
                print(f"Erreur pour {key}, tentative {attempt}: {err}")
                if attempt < retry_count:
                    time.sleep(retry_delay)
        results[key] = data
        # sauvegarder les résultats dans un fichier JSON
        with open("multiple_code_search_results.json", "w", encoding="utf-8") as json_file:
            json.dump(data, json_file, ensure_ascii=False, indent=4)

    return results if any_success else None

