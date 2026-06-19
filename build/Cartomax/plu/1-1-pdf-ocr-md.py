from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import RACINE, module_pdf


DOSSIER_PDF = RACINE / "tmp" / "pdf"
DOSSIER_MARKDOWN = RACINE / "tmp" / "markdown"


def fichiers_a_traiter(pdf: str | None) -> list[Path]:
    if pdf:
        chemin = Path(pdf)
        if not chemin.is_absolute():
            chemin = RACINE / chemin
        return [chemin]
    DOSSIER_PDF.mkdir(exist_ok=True)
    return sorted(DOSSIER_PDF.glob("*.pdf"))


def main() -> int:
    parser = argparse.ArgumentParser(description="1-1 - OCR complet PDF scanne vers Markdown.")
    parser.add_argument("pdf", nargs="?", help="PDF scanne a convertir. Par defaut: tous les PDF de tmp/pdf/")
    parser.add_argument("--dpi", type=int, default=200)
    args = parser.parse_args()

    pdf_mod = module_pdf()
    fichiers = fichiers_a_traiter(args.pdf)
    if not fichiers:
        print("Aucun PDF trouve dans tmp/pdf/.")
        return 1

    DOSSIER_MARKDOWN.mkdir(exist_ok=True)
    code_retour = 0
    for chemin_pdf in fichiers:
        chemin_md = DOSSIER_MARKDOWN / f"{chemin_pdf.stem}.md"
        ok = pdf_mod.ocr_document_complet(chemin_pdf, chemin_md, dpi=args.dpi)
        if ok:
            print(f"OK OCR : {chemin_pdf.name} -> {chemin_md}")
        else:
            code_retour = 1
            print(f"ERREUR OCR : {chemin_pdf.name}")
    return code_retour


if __name__ == "__main__":
    sys.exit(main())
