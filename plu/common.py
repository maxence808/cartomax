from __future__ import annotations

import importlib
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def nom_zone_md(stem: str, zone: str, page_debut: int | None = None, page_fin: int | None = None) -> str:
    suffixe_pages = ""
    if page_debut and page_fin:
        suffixe_pages = f"_p{page_debut}-{page_fin}"
    zone_propre = re.sub(r"[^0-9A-Za-z_-]+", "_", str(zone)).strip("_") or "zone"
    return f"{stem}_{zone_propre}{suffixe_pages}.md"


def page_depuis_ligne(lignes: list[str], index_ligne: int) -> int | None:
    page = None
    for index, ligne in enumerate(lignes[: index_ligne + 1]):
        match = re.match(r"^# Page\s+(\d+)\b", ligne.strip(), re.IGNORECASE)
        if match:
            page = int(match.group(1))
    return page


def lignes_pages(texte: str, pages: list[int]) -> str:
    lignes = texte.splitlines()
    pages_voulues = set(int(page) for page in pages)
    blocs: list[str] = []
    page_courante: int | None = None

    for ligne in lignes:
        match = re.match(r"^# Page\s+(\d+)\b", ligne.strip(), re.IGNORECASE)
        if match:
            page_courante = int(match.group(1))
        if page_courante in pages_voulues:
            blocs.append(ligne)

    return "\n".join(blocs).strip()


def _module(nom: str):
    try:
        return importlib.import_module(nom)
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            f"Module '{nom}' introuvable. Ajoute plu/{nom}.py ou adapte le script appele."
        ) from exc


def module_carte():
    return _module("carte_plu")


def module_pdf():
    return _module("pdf")


def module_ia():
    return _module("ia")


def module_sortie_ia():
    return _module("sortie_ia")
