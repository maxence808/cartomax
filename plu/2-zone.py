from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import RACINE, nom_zone_md, page_depuis_ligne
from detection_zones import detecter_sections_zones, normaliser_zone


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


def exporter_zone(chemin_md: Path, zone: str) -> Path | None:
    texte = chemin_md.read_text(encoding="utf-8")
    lignes = texte.splitlines()
    sections = detecter_sections_zones(texte)
    cible = normaliser_zone(zone)
    matches = [section for section in sections if section.cle == cible]

    if not matches:
        print(f"Aucun match parfait pour {zone} dans {chemin_md.name}.")
        if sections:
            print("Zones detectees : " + ", ".join(section.zone for section in sections))
        return None

    section = matches[0]
    page_debut = page_depuis_ligne(lignes, section.debut_ligne)
    page_fin = page_depuis_ligne(lignes, max(section.fin_ligne - 1, section.debut_ligne))
    contenu = "\n".join(lignes[section.debut_ligne:section.fin_ligne]).strip()
    entete = [
        f"# Selection zone {section.zone}",
        "",
        f"- Fichier source : `{chemin_md.name}`",
        f"- Zone demandee : `{zone}`",
        f"- Zone detectee : `{section.zone}`",
    ]
    if page_debut and page_fin:
        entete.append(f"- Pages : {page_debut}-{page_fin}")
    entete += ["", "---", ""]

    DOSSIER_SELECTION.mkdir(exist_ok=True)
    sortie = DOSSIER_SELECTION / nom_zone_md(chemin_md.stem, section.zone, page_debut, page_fin)
    sortie.write_text("\n".join(entete) + contenu + "\n", encoding="utf-8")
    print(f"OK zone auto : {sortie}")
    return sortie


def main() -> int:
    parser = argparse.ArgumentParser(description="2 - Selection auto de zone par match parfait.")
    parser.add_argument("--zone", required=True, help="Zone demandee, ex: U, UA, UCe1, N")
    parser.add_argument("markdown", nargs="?", help="Markdown source. Par defaut: tous les fichiers tmp/markdown/")
    args = parser.parse_args()

    sorties = [exporter_zone(chemin, args.zone) for chemin in trouver_markdowns(args.markdown)]
    return 0 if any(sorties) else 2


if __name__ == "__main__":
    sys.exit(main())
