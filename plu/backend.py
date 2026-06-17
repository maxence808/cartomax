from __future__ import annotations

import csv
import datetime
import json
import os
import re
import sys
from urllib.request import Request, urlopen

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
TMP_DIR = os.path.join(BASE_DIR, "tmp")
TMP_PDF_DIR = os.path.join(TMP_DIR, "pdf")
TMP_MARKDOWN_DIR = os.path.join(TMP_DIR, "markdown")
TMP_MARKDOWN_SELECTION_DIR = os.path.join(TMP_DIR, "markdown_selection")
TMP_OUTPUT_AI_DIR = os.path.join(TMP_DIR, "output_ai")
PLU_BASE_CSV = os.path.join(DATA_DIR, "base_resultats_plu.csv")


def read_json_request(handler):
    content_length = int(handler.headers.get("Content-Length", "0"))
    if content_length <= 0:
        return {}
    return json.loads(handler.rfile.read(content_length).decode("utf-8"))


def normalize_zone(value):
    return re.sub(r"[^0-9A-Za-z]+", "", str(value or "")).upper()


def extract_insee(value):
    match = re.search(r"\b\d{5}\b", str(value or ""))
    return match.group(0) if match else ""


def clean_nomfic(value):
    raw = str(value or "").strip().split("#", 1)[0].split("?", 1)[0]
    match = re.search(r"([^/\\]+?\.pdf)\b", raw, re.IGNORECASE)
    return match.group(1) if match else raw


def safe_join(base_dir, *parts):
    path = os.path.abspath(os.path.join(base_dir, *parts))
    if os.path.commonpath([os.path.abspath(base_dir), path]) != os.path.abspath(base_dir):
        raise ValueError("Chemin refuse.")
    return path


def read_plu_base_rows():
    if not os.path.exists(PLU_BASE_CSV):
        return []
    with open(PLU_BASE_CSV, encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def row_to_plu_payload(row, source="base_csv"):
    payload = dict(row)
    payload.update({
        "source_resultat": source,
        "base_csv": PLU_BASE_CSV,
        "markdown_zone": row.get("markdown_source", ""),
        "sortie_ia": row.get("sortie_ia", ""),
        "url_pdf": row.get("url_pdf", ""),
        "modele_ia": row.get("modele_ia", row.get("modele", "")),
        "reponse_brute": row,
    })
    return payload


def find_plu_base_row(nomfic="", zone="", proprietes=None, latitude="", longitude=""):
    rows = read_plu_base_rows()
    if not rows:
        return None

    proprietes = proprietes or {}
    zone_key = normalize_zone(zone or proprietes.get("libelle") or proprietes.get("zone") or proprietes.get("typezone"))
    nomfic_clean = clean_nomfic(nomfic or proprietes.get("nomfic") or proprietes.get("nom_fichier"))
    insee = (
        extract_insee(nomfic_clean)
        or extract_insee(proprietes.get("insee"))
        or extract_insee(proprietes.get("code_insee"))
        or extract_insee(proprietes.get("partition"))
        or extract_insee(proprietes.get("idurba"))
    )

    best = None
    best_score = -1
    for row in rows:
        row_zone = normalize_zone(row.get("zone") or row.get("lettre_zone_envoyer"))
        row_insee = extract_insee(row.get("code_insee") or row.get("url_pdf") or row.get("fichier_source"))
        row_url = row.get("url_pdf", "")
        score = 0
        if zone_key and row_zone == zone_key:
            score += 3
        if insee and row_insee == insee:
            score += 3
        if nomfic_clean and nomfic_clean.lower() in row_url.lower():
            score += 4
        if latitude and longitude and row.get("lat") == str(latitude) and row.get("long") == str(longitude):
            score += 2
        if score > best_score:
            best = row
            best_score = score

    return best if best_score >= 3 else None


def guess_pdf_urls(nomfic, proprietes=None):
    proprietes = proprietes or {}
    nomfic = clean_nomfic(nomfic)
    urls = []
    direct = str(proprietes.get("url_pdf") or proprietes.get("url") or "").strip()
    if direct:
        urls.append(direct)

    for raw in (nomfic, proprietes.get("nomfic"), proprietes.get("nom_fichier"), proprietes.get("fichier")):
        raw = str(raw or "").strip()
        if raw.startswith("http"):
            urls.append(raw)

    insee = (
        extract_insee(nomfic)
        or extract_insee(proprietes.get("partition"))
        or extract_insee(proprietes.get("idurba"))
        or extract_insee(proprietes.get("insee"))
        or extract_insee(proprietes.get("code_insee"))
    )
    if nomfic and insee:
        urls.append(f"https://www.geoportail-urbanisme.gouv.fr/api/document/download-by-partition/DU_{insee}/file/{nomfic}")

    unique = []
    for url in urls:
        if url and url not in unique:
            unique.append(url)
    return unique


def download_pdf(nomfic, proprietes=None):
    nomfic = clean_nomfic(nomfic)
    if not nomfic:
        raise RuntimeError("Nom du fichier PDF manquant.")
    if not nomfic.lower().endswith(".pdf"):
        nomfic = f"{nomfic}.pdf"

    os.makedirs(TMP_PDF_DIR, exist_ok=True)
    destination = safe_join(TMP_PDF_DIR, os.path.basename(nomfic))
    if os.path.exists(destination) and os.path.getsize(destination) > 0:
        return {"statut": "pdf_deja_present", "nomfic": nomfic, "pdf": destination}

    errors = []
    for url in guess_pdf_urls(nomfic, proprietes):
        try:
            request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(request, timeout=120) as response:
                content = response.read()
            if content[:4] != b"%PDF":
                errors.append({"url": url, "erreur": "La reponse n'est pas un PDF."})
                continue
            with open(destination, "wb") as file:
                file.write(content)
            return {"statut": "pdf_telecharge", "nomfic": nomfic, "pdf": destination, "url": url}
        except Exception as error:
            errors.append({"url": url, "erreur": str(error)})

    raise RuntimeError(f"Telechargement PDF impossible pour {nomfic}: {errors}")


def extract_pdf_text_to_markdown(pdf_path):
    os.makedirs(TMP_MARKDOWN_DIR, exist_ok=True)
    if not os.path.exists(pdf_path):
        raise RuntimeError(f"PDF introuvable: {pdf_path}")

    markdown_path = safe_join(TMP_MARKDOWN_DIR, f"{os.path.splitext(os.path.basename(pdf_path))[0]}.md")
    if os.path.exists(markdown_path) and os.path.getsize(markdown_path) > 0:
        return markdown_path

    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF n'est pas installe: impossible de convertir le PDF en Markdown.") from exc

    doc = fitz.open(pdf_path)
    lines = [f"# Document PLU : {os.path.basename(pdf_path)}", "", f"- Pages : {doc.page_count}", "", "---"]
    for index, page in enumerate(doc, start=1):
        text = page.get_text("text").replace("\x00", "").strip()
        lines += ["", f"# Page {index}", "", text or "> [PAGE VIDE]", "", "---"]

    with open(markdown_path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))
    return markdown_path


def page_for_line(lines, line_index):
    page = None
    for line in lines[:line_index + 1]:
        match = re.match(r"^# Page\s+(\d+)\b", line.strip(), re.IGNORECASE)
        if match:
            page = int(match.group(1))
    return page


def detect_zone_sections(text):
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from detection_zones import detecter_sections_zones
        return detecter_sections_zones(text)
    except Exception:
        return []


def markdown_section(pdf_path, zone):
    markdown_path = extract_pdf_text_to_markdown(pdf_path)
    with open(markdown_path, encoding="utf-8") as file:
        text = file.read()
    lines = text.splitlines()
    zone_key = normalize_zone(zone)
    sections = detect_zone_sections(text)
    matches = [
        section for section in sections
        if normalize_zone(getattr(section, "zone", "")) == zone_key or getattr(section, "cle", "") == zone_key
    ]

    if matches:
        section = matches[0]
        start, end = section.debut_ligne, section.fin_ligne
        detected_zone = section.zone
        match_perfect = True
    else:
        start, end = 0, min(len(lines), 900)
        detected_zone = zone or "zone"
        match_perfect = False

    page_start = page_for_line(lines, start)
    page_end = page_for_line(lines, max(start, end - 1))
    content = "\n".join(lines[start:end]).strip()
    safe_zone = re.sub(r"[^0-9A-Za-z_-]+", "_", str(detected_zone or zone or "zone")).strip("_") or "zone"
    page_suffix = f"_p{page_start}-{page_end}" if page_start and page_end else ""
    os.makedirs(TMP_MARKDOWN_SELECTION_DIR, exist_ok=True)
    output_path = safe_join(TMP_MARKDOWN_SELECTION_DIR, f"{os.path.splitext(os.path.basename(markdown_path))[0]}_{safe_zone}{page_suffix}.md")

    header = [
        f"# Selection zone {detected_zone}",
        "",
        f"- Fichier source : `{os.path.basename(markdown_path)}`",
        f"- Zone demandee : `{zone}`",
        f"- Match parfait : `{str(match_perfect).lower()}`",
    ]
    if page_start and page_end:
        header.append(f"- Pages : {page_start}-{page_end}")
    header += ["", "---", ""]

    with open(output_path, "w", encoding="utf-8") as file:
        file.write("\n".join(header) + content + "\n")

    return {
        "markdown_complet": markdown_path,
        "markdown_section": output_path,
        "match_parfait": match_perfect,
        "zone_effective": detected_zone,
        "pages_localisees": [page for page in (page_start, page_end) if page],
        "zones_detectees": [section.zone for section in sections[:80]],
        "avertissement": "" if match_perfect else "Zone exacte non trouvee automatiquement. Une section large a ete extraite.",
        "pdf_scanne": False,
    }


def local_ai_response(payload, retry=False):
    zone = payload.get("zone", "")
    row = find_plu_base_row(
        zone=zone,
        latitude=payload.get("latitude", ""),
        longitude=payload.get("longitude", ""),
        proprietes={"url_pdf": payload.get("url_pdf") or payload.get("pdf", "")},
    )
    if row:
        return row_to_plu_payload(row)

    markdown_path = payload.get("markdown_section") or payload.get("markdown") or payload.get("markdown_complet")
    excerpt = ""
    if markdown_path and os.path.exists(markdown_path):
        with open(markdown_path, encoding="utf-8", errors="replace") as file:
            excerpt = file.read(5000)

    os.makedirs(TMP_OUTPUT_AI_DIR, exist_ok=True)
    result = {
        "source_resultat": "analyse_locale",
        "modele_ia": "local-sans-cle-ia",
        "zone": zone,
        "zone_effective": zone,
        "ville": payload.get("ville", ""),
        "adresse_point": payload.get("adresse_point", ""),
        "latitude": payload.get("latitude", ""),
        "longitude": payload.get("longitude", ""),
        "markdown_zone": markdown_path or "",
        "pdf": payload.get("pdf", ""),
        "archive": payload.get("archive", ""),
        "retry_donnees_insuffisantes": bool(retry),
        "donnees_insuffisantes": False,
        "avertissement": "Aucune cle IA/module IA n'est configure. Reponse locale de secours produite pour ne pas bloquer le flux.",
        "reponse_brute": excerpt or "Markdown indisponible.",
    }
    output = safe_join(TMP_OUTPUT_AI_DIR, f"analyse_locale_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json")
    with open(output, "w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
    result["sortie_ia"] = output
    return result


def handle_api(path, payload):
    if path in ("/api/nouveau/telecharger-pdf", "/api/charger-plu-nomfic"):
        nomfic = payload.get("nomfic")
        proprietes = payload.get("proprietes") or {}
        zone = payload.get("zone") or proprietes.get("libelle") or proprietes.get("zone")
        cached = find_plu_base_row(nomfic=nomfic, zone=zone, proprietes=proprietes)
        if cached:
            return row_to_plu_payload(cached)
        return download_pdf(nomfic, proprietes)

    if path == "/api/charger-plu":
        commune = payload.get("commune") or {}
        raise RuntimeError(f"Recherche automatique par commune non disponible sans nomfic. Commune recue: {commune.get('nom') or commune.get('code') or commune}")

    if path == "/api/nouveau/markdown-section":
        return markdown_section(payload.get("pdf", ""), payload.get("zone", ""))

    if path in ("/api/nouveau/traitement-ia", "/api/analyser-zone"):
        return local_ai_response(payload, retry=False)

    if path == "/api/nouveau/traitement-ia-retry":
        return local_ai_response(payload, retry=True)

    return None
