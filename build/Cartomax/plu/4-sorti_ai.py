from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from common import RACINE, module_sortie_ia
from csv_cache import enregistrer_resultat_dans_base_csv


DOSSIER_ENTREE = RACINE / "tmp" / "output_ai"
DOSSIER_SORTIE = RACINE / "data" / "resultats_plu"
BASE_CSV = RACINE / "data" / "base_resultats_plu.csv"


def trouver_json(argument: str | None) -> list[Path]:
    if argument:
        chemin = Path(argument)
        if not chemin.is_absolute():
            chemin = RACINE / chemin
        return [chemin]
    DOSSIER_ENTREE.mkdir(exist_ok=True)
    return sorted(DOSSIER_ENTREE.glob("*_analyse_brute.json"))


def source_markdown_depuis_json(chemin_json: Path) -> str:
    stem = chemin_json.stem.replace("_analyse_brute", "")
    selection = RACINE / "tmp" / "markdown_selection"
    candidat = selection / f"{stem}.md"
    if candidat.exists():
        return candidat.name
    return f"{stem}.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="4 - Fusionne la sortie IA et ajoute les lignes dans le CSV.")
    parser.add_argument("json", nargs="?", help="Fichier *_analyse_brute.json. Par defaut: tous les fichiers tmp/output_ai/")
    parser.add_argument("--csv", default=str(BASE_CSV), help="CSV de sortie.")
    args = parser.parse_args()

    sortie_mod = module_sortie_ia()
    fichiers = trouver_json(args.json)
    if not fichiers:
        print("Aucun fichier *_analyse_brute.json trouve dans tmp/output_ai/.")
        return 1

    DOSSIER_SORTIE.mkdir(exist_ok=True)
    chemin_csv = Path(args.csv)
    if not chemin_csv.is_absolute():
        chemin_csv = RACINE / chemin_csv

    for chemin_json in fichiers:
        resultat = sortie_mod.fusionner_resultats(chemin_json)
        nom_base = sortie_mod.extraire_nom_base(chemin_json)
        chemin_resultat = DOSSIER_SORTIE / f"{nom_base}_regles_plu.json"
        chemin_resultat.write_text(json.dumps(resultat, ensure_ascii=False, indent=2), encoding="utf-8")

        markdown_source = source_markdown_depuis_json(chemin_json)
        enregistrer_resultat_dans_base_csv(
            resultat,
            fichier_source=resultat.get("fichier_source", "") or markdown_source,
            markdown_source=markdown_source,
            sortie_ia=chemin_json.name,
            chemin_csv=chemin_csv,
        )
        print(f"OK JSON : {chemin_resultat}")
        print(f"OK CSV  : {chemin_csv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
