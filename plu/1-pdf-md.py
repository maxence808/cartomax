from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import fitz

from common import RACINE
from pdf_gpu import telecharger_pdf_gpu


DOSSIER_PDF = RACINE / "tmp" / "pdf"
DOSSIER_MARKDOWN = RACINE / "tmp" / "markdown"
SEUIL_TEXTE_VIDE = 50


def nettoyer_texte(texte: str) -> str:
    lignes = [ligne.strip() for ligne in texte.replace("\x00", "").replace("\r", "\n").splitlines()]
    resultat: list[str] = []
    ligne_vide = False
    for ligne in lignes:
        if not ligne:
            if not ligne_vide:
                resultat.append("")
            ligne_vide = True
        else:
            resultat.append(ligne)
            ligne_vide = False
    return "\n".join(resultat).strip()


def convertir_pdf_en_md_natif(chemin_pdf: Path, chemin_md: Path) -> dict:
    doc = fitz.open(chemin_pdf)
    pages_vides: list[int] = []
    contenu = [
        f"# Document PLU : {chemin_pdf.name}",
        "",
        "## Metadonnees",
        f"- Fichier source : `{chemin_pdf.name}`",
        f"- Nombre de pages : {doc.page_count}",
        "- Mode : extraction texte native",
        "",
        "---",
    ]

    for numero, page in enumerate(doc, start=1):
        texte = nettoyer_texte(page.get_text("text"))
        contenu += ["", f"# Page {numero}", ""]
        if len(texte.strip()) >= SEUIL_TEXTE_VIDE:
            contenu.append(texte)
        else:
            pages_vides.append(numero)
            contenu.append("> [PAGE VIDE] Aucun texte natif detecte.")
        contenu += ["", "---"]

    chemin_md.parent.mkdir(exist_ok=True)
    chemin_md.write_text("\n".join(contenu), encoding="utf-8")
    return {
        "fichier": chemin_pdf.name,
        "pages_total": doc.page_count,
        "pages_vides": pages_vides,
        "pdf_scanne_probable": len(pages_vides) == doc.page_count,
    }


def charger_json_proprietes(chemin: str) -> dict:
    if not chemin:
        return {}
    path = Path(chemin)
    if not path.is_absolute():
        path = RACINE / path
    return json.loads(path.read_text(encoding="utf-8"))


def fichiers_a_traiter(pdf: str | None, proprietes: dict | None = None) -> list[Path]:
    if pdf:
        chemin = Path(pdf)
        if not chemin.is_absolute():
            chemin = RACINE / chemin
        if chemin.exists():
            return [chemin]
        resultat = telecharger_pdf_gpu(pdf, proprietes=proprietes, dossier_sortie=DOSSIER_PDF)
        return [Path(resultat["pdf"])]
    if proprietes:
        resultat = telecharger_pdf_gpu("", proprietes=proprietes, dossier_sortie=DOSSIER_PDF)
        return [Path(resultat["pdf"])]
    DOSSIER_PDF.mkdir(exist_ok=True)
    return sorted(DOSSIER_PDF.glob("*.pdf"))


def main() -> int:
    parser = argparse.ArgumentParser(description="1 - Convertit PDF texte en Markdown.")
    parser.add_argument("pdf", nargs="?", help="PDF local, nomfic GPU ou URL contenant un PDF. Par defaut: tous les PDF de tmp/pdf/")
    parser.add_argument("--props", default="", help="Fichier JSON de proprietes GPU.")
    parser.add_argument("--code-insee", default="", help="Code INSEE si le nom du PDF est inconnu.")
    parser.add_argument("--partition", default="", help="Partition GPU, exemple: DU_200039907_A.")
    args = parser.parse_args()

    proprietes = charger_json_proprietes(args.props)
    if args.code_insee:
        proprietes["code_insee"] = args.code_insee
    if args.partition:
        proprietes["partition"] = args.partition

    fichiers = fichiers_a_traiter(args.pdf, proprietes=proprietes)
    if not fichiers:
        print("Aucun PDF trouve dans tmp/pdf/.")
        return 1

    DOSSIER_MARKDOWN.mkdir(exist_ok=True)
    code_retour = 0
    for chemin_pdf in fichiers:
        chemin_md = DOSSIER_MARKDOWN / f"{chemin_pdf.stem}.md"
        meta = convertir_pdf_en_md_natif(chemin_pdf, chemin_md)
        print(f"OK : {chemin_pdf.name} -> {chemin_md}")
        if meta["pdf_scanne_probable"]:
            code_retour = 2
            print(f"SCANNE : lance ensuite plu/1-1-pdf-ocr-md.py {chemin_pdf}")
    return code_retour


if __name__ == "__main__":
    sys.exit(main())
