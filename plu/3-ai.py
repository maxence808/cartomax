from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import RACINE, module_ia


DOSSIER_SELECTION = RACINE / "tmp" / "markdown_selection"


def trouver_markdowns(argument: str | None) -> list[Path]:
    if argument:
        chemin = Path(argument)
        if not chemin.is_absolute():
            chemin = RACINE / chemin
        return [chemin]
    DOSSIER_SELECTION.mkdir(exist_ok=True)
    return sorted(DOSSIER_SELECTION.glob("*.md"))


def main() -> int:
    parser = argparse.ArgumentParser(description="3 - Envoie le Markdown de zone a l'IA.")
    parser.add_argument("markdown", nargs="?", help="Markdown de zone. Par defaut: tous les fichiers tmp/markdown_selection/")
    parser.add_argument("--provider", default=None, help="openrouter ou aistudio")
    args = parser.parse_args()

    fichiers = trouver_markdowns(args.markdown)
    if not fichiers:
        print("Aucun Markdown de zone trouve dans tmp/markdown_selection/.")
        return 1

    ia = module_ia()
    client = ia.creer_client_ia(args.provider)
    print(f"Fournisseur IA : {client['fournisseur']} / modele : {client.get('modele')}")
    for chemin in fichiers:
        ia.analyser_fichier_markdown(client, chemin)
    return 0


if __name__ == "__main__":
    sys.exit(main())
