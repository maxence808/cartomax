from __future__ import annotations

import csv
from pathlib import Path

from common import RACINE

BASE_CSV = RACINE / "data" / "base_resultats_plu.csv"


def enregistrer_resultat_dans_base_csv(
    resultat: dict,
    *,
    fichier_source: str = "",
    markdown_source: str = "",
    sortie_ia: str = "",
    chemin_csv: str | Path = BASE_CSV,
) -> Path:
    chemin = Path(chemin_csv)
    if not chemin.is_absolute():
        chemin = RACINE / chemin
    chemin.parent.mkdir(parents=True, exist_ok=True)

    ligne = {
        "fichier_source": fichier_source,
        "markdown_source": markdown_source,
        "sortie_ia": sortie_ia,
        **{cle: _serialiser(valeur) for cle, valeur in resultat.items()},
    }

    colonnes = list(ligne)
    existe = chemin.exists() and chemin.stat().st_size > 0
    if existe:
        with open(chemin, encoding="utf-8", newline="") as fichier:
            lecteur = csv.reader(fichier)
            colonnes_existantes = next(lecteur, [])
        colonnes = list(dict.fromkeys([*colonnes_existantes, *colonnes]))

    with open(chemin, "a", encoding="utf-8", newline="") as fichier:
        writer = csv.DictWriter(fichier, fieldnames=colonnes)
        if not existe:
            writer.writeheader()
        writer.writerow({colonne: ligne.get(colonne, "") for colonne in colonnes})

    return chemin


def _serialiser(valeur) -> str:
    if isinstance(valeur, (dict, list, tuple)):
        import json

        return json.dumps(valeur, ensure_ascii=False)
    return "" if valeur is None else str(valeur)
