# Solution 1: Vérification et diagnostic complet
import streamlit as st
import sys
from pathlib import Path
import os

st.set_page_config(page_title="Grok3 Assistant", page_icon="🤖", layout="wide")

def diagnose_grok3_structure():
    """Diagnostic complet de la structure grok3"""
    st.write("## 🔍 Diagnostic Structure Grok3")
    
    current_file = Path(__file__)
    streamlit_app_dir = current_file.parent.parent
    grok3_dir = streamlit_app_dir / "grok3"
    
    st.write(f"**Fichier actuel:** {current_file}")
    st.write(f"**Répertoire streamlit_app:** {streamlit_app_dir}")
    st.write(f"**Répertoire grok3:** {grok3_dir}")
    st.write(f"**grok3 existe:** {grok3_dir.exists()}")
    
    if grok3_dir.exists():
        st.write("**📁 Contenu du dossier grok3:**")
        files_found = []
        for item in sorted(grok3_dir.iterdir()):
            icon = "📁" if item.is_dir() else "📄"
            files_found.append(item.name)
            st.write(f"  {icon} {item.name}")
            
            # Vérifier les permissions
            try:
                readable = os.access(item, os.R_OK)
                st.write(f"      Permissions lecture: {'✅' if readable else '❌'}")
            except:
                st.write("      Permissions: Non vérifiable")
        
        # Vérifier les fichiers spécifiques
        st.write("**🔍 Vérification des fichiers attendus:**")
        expected_files = ["grok3_utils.py", "grok3_client.py", "__init__.py"]
        for file_name in expected_files:
            file_path = grok3_dir / file_name
            exists = file_path.exists()
            st.write(f"  📄 {file_name}: {'✅' if exists else '❌'}")
            if exists:
                try:
                    size = file_path.stat().st_size
                    st.write(f"      Taille: {size} bytes")
                except:
                    st.write("      Taille: Non accessible")
        
        return files_found
    else:
        st.error("❌ Le dossier grok3 n'existe pas!")
        return []

# Exécuter le diagnostic
files_in_grok3 = diagnose_grok3_structure()

# Solution 2: Import basé sur les fichiers réellement présents
current_file = Path(__file__)
streamlit_app_dir = current_file.parent.parent
grok3_dir = streamlit_app_dir / "grok3"

call_grok = None

if grok3_dir.exists():
    # Essayer d'importer depuis grok3_client.py (qui semble exister)
    grok3_client_path = grok3_dir / "grok3_client.py"
    grok3_utils_path = grok3_dir / "grok3_utils.py"
    
    st.write("## 🔧 Tentatives d'import")
    
    # Tentative 1: grok3_utils.py
    if grok3_utils_path.exists():
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("grok3_utils", grok3_utils_path)
            grok3_utils = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(grok3_utils)
            
            # Vérifier si call_grok existe dans le module
            if hasattr(grok3_utils, 'call_grok'):
                call_grok = grok3_utils.call_grok
                st.success("✅ Import depuis grok3_utils.py réussi!")
            else:
                st.warning("⚠️ grok3_utils.py trouvé mais fonction call_grok manquante")
                # Lister les fonctions disponibles
                functions = [name for name in dir(grok3_utils) if callable(getattr(grok3_utils, name)) and not name.startswith('_')]
                st.write(f"Fonctions disponibles: {functions}")
                
        except Exception as e:
            st.error(f"❌ Erreur import grok3_utils.py: {e}")
    
    # Tentative 2: grok3_client.py
    if call_grok is None and grok3_client_path.exists():
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("grok3_client", grok3_client_path)
            grok3_client = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(grok3_client)
            
            # Vérifier si call_grok existe dans grok3_client
            if hasattr(grok3_client, 'call_grok'):
                call_grok = grok3_client.call_grok
                st.success("✅ Import depuis grok3_client.py réussi!")
            else:
                st.warning("⚠️ grok3_client.py trouvé mais fonction call_grok manquante")
                # Lister les fonctions disponibles
                functions = [name for name in dir(grok3_client) if callable(getattr(grok3_client, name)) and not name.startswith('_')]
                st.write(f"Fonctions disponibles: {functions}")
                
        except Exception as e:
            st.error(f"❌ Erreur import grok3_client.py: {e}")

# Solution 3: Créer grok3_utils.py si manquant
if call_grok is None:
    st.write("## 🛠️ Création de grok3_utils.py")
    
    if st.button("📝 Créer grok3_utils.py avec fonction de base"):
        grok3_utils_content = '''"""
Module grok3_utils - Fonctions utilitaires pour Grok3
"""

def call_grok(message: str, **kwargs):
    """
    Fonction de base pour appeler Grok3
    
    Args:
        message (str): Message à envoyer à Grok
        **kwargs: Arguments supplémentaires
    
    Returns:
        str: Réponse de Grok (placeholder)
    """
    return f"Grok3 placeholder response for: {message}"

def test_grok():
    """Fonction de test"""
    return "Grok3 utils module loaded successfully!"

if __name__ == "__main__":
    print(test_grok())
'''
        
        try:
            grok3_utils_path = grok3_dir / "grok3_utils.py"
            grok3_utils_path.write_text(grok3_utils_content)
            st.success(f"✅ Fichier créé: {grok3_utils_path}")
            st.info("🔄 Rechargez la page pour utiliser le nouveau module")
        except Exception as e:
            st.error(f"❌ Erreur création fichier: {e}")

# Solution 4: Créer __init__.py si manquant
init_path = grok3_dir / "__init__.py"
if grok3_dir.exists() and not init_path.exists():
    if st.button("📝 Créer __init__.py"):
        try:
            init_content = '"""Module grok3"""\n'
            init_path.write_text(init_content)
            st.success(f"✅ Fichier __init__.py créé: {init_path}")
        except Exception as e:
            st.error(f"❌ Erreur création __init__.py: {e}")

# Solution 5: Interface de fallback
if call_grok is None:
    st.warning("⚠️ Fonction call_grok non disponible. Utilisation d'une fonction de fallback.")
    
    def call_grok_fallback(message: str, **kwargs):
        return f"[FALLBACK] Grok3 non disponible. Message reçu: {message}"
    
    call_grok = call_grok_fallback

# Interface utilisateur
st.write("## 🤖 Interface Grok3")

if call_grok:
    st.write("✅ Fonction call_grok disponible")
    
    # Test de la fonction
    if st.button("🧪 Tester call_grok"):
        try:
            result = call_grok("Test message")
            st.write(f"**Résultat:** {result}")
        except Exception as e:
            st.error(f"❌ Erreur test: {e}")
    
    # Interface principale
    user_input = st.text_area("💬 Votre message pour Grok3:", placeholder="Tapez votre question ici...")
    
    if st.button("🚀 Envoyer à Grok3") and user_input:
        try:
            with st.spinner("🤖 Grok3 réfléchit..."):
                response = call_grok(user_input)
            st.write("**Réponse de Grok3:**")
            st.write(response)
        except Exception as e:
            st.error(f"❌ Erreur appel Grok3: {e}")

else:
    st.error("❌ Impossible de charger la fonction call_grok")

# Afficher les informations de debug en bas
with st.expander("🔍 Informations de debug"):
    st.write(f"**sys.path:** {sys.path[:3]}...")  # Premiers éléments seulement
    st.write(f"**Fichiers dans grok3:** {files_in_grok3}")
    st.write(f"**call_grok disponible:** {call_grok is not None}")
    if call_grok:
        st.write(f"**Type de call_grok:** {type(call_grok)}")