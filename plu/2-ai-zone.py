from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import RACINE, lignes_pages, nom_zone_md, module_ia


DOSSIER_MARKDOWN = RACINE / "tmp" / "markdown"
DOSSIER_SELECTION = RACINE / "tmp" / "markdown_selection"


def trouver_markdowns(argument: str | None) -> list[Path]:
    if argument:
        chemin = Path(argument)
        if not chemin.is_absolute():
            chemin = RACINE / chemin
        return [chemin]
    DOSSIER_MARKDOWN.mkdir(exist_ok=True)
    return sorted(DOSSIER_MARKDOWN.glob("*.md"))


def exporter_zone_par_ia(chemin_md: Path, zone: str, fournisseur: str | None) -> Path | None:
    ia = module_ia()
    texte = chemin_md.read_text(encoding="utf-8")
    sommaire = ia.extraire_sommaire_markdown(texte)
    if not sommaire.strip():
        print(f"Sommaire introuvable : {chemin_md.name}")
        return None

    client = ia.creer_client_ia(fournisseur)
    pages, zone_trouvee = ia.localiser_pages_zone(client, sommaire, zone)
    if not pages:
        print(f"IA : aucune page trouvee pour {zone} dans {chemin_md.name}")
        return None

    contenu = lignes_pages(texte, pages)
    if not contenu:
        print(f"Pages IA introuvables dans le markdown : {pages}")
        return None

    page_debut = min(pages)
    page_fin = max(pages)
    entete = [
        f"# Selection zone {zone_trouvee}",
        "",
        f"- Fichier source : `{chemin_md.name}`",
        f"- Zone demandee : `{zone}`",
        f"- Zone trouvee par IA : `{zone_trouvee}`",
        f"- Pages : {page_debut}-{page_fin}",
        "",
        "---",
        "",
    ]

    DOSSIER_SELECTION.mkdir(exist_ok=True)
    sortie = DOSSIER_SELECTION / nom_zone_md(chemin_md.stem, str(zone_trouvee or zone), page_debut, page_fin)
    sortie.write_text("\n".join(entete) + contenu + "\n", encoding="utf-8")
    print(f"OK zone IA : {sortie}")
    return sortie


def main() -> int:
    parser = argparse.ArgumentParser(description="2-ai - Localise une zone par IA via le sommaire.")
    parser.add_argument("--zone", required=True, help="Zone demandee, ex: U, UA, UCe1, N")
    parser.add_argument("--provider", default=None, help="openrouter ou aistudio")
    parser.add_argument("markdown", nargs="?", help="Markdown source. Par defaut: tous les fichiers tmp/markdown/")
    args = parser.parse_args()

    sorties = [exporter_zone_par_ia(chemin, args.zone, args.provider) for chemin in trouver_markdowns(args.markdown)]
    return 0 if any(sorties) else 2


if __name__ == "__main__":
    sys.exit(main())
