"""Gestionnaire de fichiers avec interface de sélection"""

from pathlib import Path
from typing import List, Optional
import tkinter as tk
from tkinter import filedialog


class FileManager:
    """Gestionnaire de fichiers avec sélection graphique"""
    
    def __init__(self):
        self.tkinter_available = self._check_tkinter()
    
    def _check_tkinter(self) -> bool:
        """Vérifie si tkinter est disponible"""
        try:
            import tkinter
            return True
        except ImportError:
            return False
    
    def select_files(self, multiple: bool = True, file_types: Optional[List[tuple]] = None) -> List[Path]:
        """Ouvre une boîte de dialogue pour sélectionner des fichiers"""
        if not self.tkinter_available:
            raise RuntimeError("tkinter non disponible pour la sélection de fichiers")
        
        if file_types is None:
            file_types = [
                ("Fichiers PDF", "*.pdf"),
                ("Tous les fichiers", "*.*")
            ]
        
        try:
            # Créer une fenêtre tkinter cachée
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            
            if multiple:
                file_paths = filedialog.askopenfilenames(
                    title="Sélectionnez des fichiers",
                    filetypes=file_types
                )
            else:
                file_path = filedialog.askopenfilename(
                    title="Sélectionnez un fichier",
                    filetypes=file_types
                )
                file_paths = [file_path] if file_path else []
            
            root.destroy()
            
            return [Path(p) for p in file_paths if p]
            
        except Exception as e:
            raise Exception(f"Erreur lors de la sélection: {e}")
    
    def select_single_file(self, file_types: Optional[List[tuple]] = None) -> Optional[Path]:
        """Sélectionne un seul fichier"""
        files = self.select_files(multiple=False, file_types=file_types)
        return files[0] if files else None
    
    def validate_pdf_file(self, file_path: Path) -> bool:
        """Valide qu'un fichier est un PDF existant"""
        return (
            file_path.exists() and 
            file_path.is_file() and 
            file_path.suffix.lower() == '.pdf'
        )