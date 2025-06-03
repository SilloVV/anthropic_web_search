"""Point d'entrée principal du chat Gemini"""

import sys
from pathlib import Path

# Ajouter le dossier src au PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.utils.config import Config
from src.ui.chat_interface import ChatInterface


def main():
    """Point d'entrée principal"""
    try:
        # Charger la configuration
        config = Config()
        
        # Créer et lancer l'interface
        chat = ChatInterface(config)
        chat.run()
        
    except KeyboardInterrupt:
        print("\n👋 Au revoir !")
    except Exception as e:
        print(f"❌ Erreur fatale: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())