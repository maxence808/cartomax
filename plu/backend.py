from __future__ import annotations

import csv
import datetime
import json
import os
import re
import sys
import unicodedata

from . import pdf_gpu
from . import ia as ia_module

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


def zones_compatibles(zone_ligne, zone_demandee):
    ligne = normalize_zone(zone_ligne)
    demandee = normalize_zone(zone_demandee)
    if not ligne or not demandee:
        return False
    if ligne == demandee:
        return True
    suffixe = ligne[len(demandee):] if ligne.startswith(demandee) else ""
    return bool(suffixe and suffixe[0].isdigit())


def zone_localisation_compatible(zone_demandee, zone_effective):
    demandee = normalize_zone(zone_demandee)
    effective = normalize_zone(zone_effective)
    if not demandee or not effective:
        return False
    if demandee == effective:
        return True
    if zones_compatibles(effective, demandee):
        return True
    return effective in ("A", "N") and demandee.startswith(effective)


def normalize_text(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^0-9A-Za-z]+", " ", text).strip().upper()
    return re.sub(r"\s+", " ", text)


def extract_insee(value):
    text = str(value or "")
    for motif in (
        r"(?:^|[/\\])(\d{5,9})_reglement_\d{8}\.pdf\b",
        r"\bDU_(\d{5,9})\b",
        r"\b(?:code_insee|insee)[=:/_-]?(\d{5,9})\b",
    ):
        match = re.search(motif, text, re.IGNORECASE)
        if match:
            return match.group(1)
    match = re.search(r"(?<!\d)(\d{5,9})(?!\d)", text)
    return match.group(0) if match else ""


def extract_code_postal(value):
    text = str(value or "")
    match = re.search(r"(?<!\d)((?:0[1-9]|[1-8]\d|9[0-8])\d{3})(?!\d)", text)
    return match.group(1) if match else ""


def extract_plu_date(value):
    text = str(value or "")
    iso_match = re.search(r"(?<!\d)(20\d{2})-(\d{2})-(\d{2})(?!\d)", text)
    if iso_match:
        return "-".join(iso_match.groups())
    compact_match = re.search(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)", text)
    if compact_match:
        return "-".join(compact_match.groups())
    return ""


def clean_nomfic(value):
    raw = str(value or "").strip().split("#", 1)[0].split("?", 1)[0]
    match = re.search(r"([^/\\]+?\.pdf)\b", raw, re.IGNORECASE)
    return match.group(1) if match else raw


def first_value(source, *keys):
    for key in keys:
        value = source.get(key) if isinstance(source, dict) else None
        if value not in (None, ""):
            return str(value).strip()
    return ""


def first_pdf_reference(source):
    return first_value(
        source,
        "nomfic",
        "nom_fichier",
        "fichier",
        "url_pdf",
        "pdf",
        "urlfic",
        "URLFIC",
        "url_fic",
        "url",
    )


def is_http_url(value):
    return bool(re.match(r"^https?://", str(value or "").strip(), re.IGNORECASE))


def first_http_url(*values):
    for value in values:
        text = str(value or "").strip()
        if is_http_url(text):
            return text
    return ""


def url_pdf_depuis_nomfic(value):
    nomfic = clean_nomfic(value)
    if not nomfic.lower().endswith(".pdf"):
        return ""
    try:
        urls = pdf_gpu.build_download_urls({"nomfic": nomfic})
    except Exception:
        return ""
    return first_http_url(*urls)


def safe_join(base_dir, *parts):
    path = os.path.abspath(os.path.join(base_dir, *parts))
    if os.path.commonpath([os.path.abspath(base_dir), path]) != os.path.abspath(base_dir):
        raise ValueError("Chemin refuse.")
    return path


def document_id_from_path(path):
    filename = os.path.basename(str(path or ""))
    document_id = filename.split("_reglement_", 1)[0]
    return re.sub(r"[^0-9A-Za-z_-]+", "_", document_id).strip("_") or "document"


def read_plu_base_rows():
    if not os.path.exists(PLU_BASE_CSV):
        return []
    with open(PLU_BASE_CSV, encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def read_plu_base_columns():
    if not os.path.exists(PLU_BASE_CSV):
        return [
            "adresse_point",
            "lat",
            "long",
            "date_recherche",
            "date_edition_plu",
            "ville",
            "code_insee",
            "zone",
            "lettre_zone_envoyer",
            "modele_ia",
            "url_pdf",
            "hauteur_maximale.valeur",
            "hauteur_maximale.condition",
            "hauteur_maximale.page",
            "emprise_au_sol.valeur",
            "emprise_au_sol.condition",
            "emprise_au_sol.page",
            "implantation_voies.regle",
            "implantation_voies.page",
            "implantation_limites.regle",
            "implantation_limites.page",
            "espaces_verts.regle",
            "espaces_verts.page",
            "stationnement.valeur_pl",
            "stationnement.valeur_vl",
            "stationnement.regle",
            "stationnement.page",
            "destinations.autorisees",
            "destinations.interdites",
            "contrainte_particulieres",
        ]
    with open(PLU_BASE_CSV, encoding="utf-8-sig", newline="") as file:
        return next(csv.reader(file), [])


def nested_value(source, path, default=""):
    value = source
    for part in path.split("."):
        if not isinstance(value, dict):
            return default
        value = value.get(part)
    return default if value in (None, "") else value


def serialiser_cellule(value):
    if isinstance(value, list):
        return " | ".join(serialiser_cellule(item) for item in value)
    if isinstance(value, dict):
        if "description" in value:
            return serialiser_cellule(value.get("description"))
        return json.dumps(value, ensure_ascii=False)
    return "" if value is None else str(value)


def payload_pdf_reference(payload, result):
    url_pdf = first_http_url(
        result.get("url_pdf"),
        payload.get("url_pdf"),
        result.get("url"),
        payload.get("url"),
        result.get("pdf"),
        payload.get("pdf"),
    )
    if url_pdf:
        return url_pdf

    reference_locale = (
        result.get("pdf")
        or payload.get("pdf")
        or result.get("url_pdf")
        or payload.get("url_pdf")
        or result.get("markdown_zone")
        or payload.get("markdown_section")
        or payload.get("markdown_complet")
        or ""
    )
    return url_pdf_depuis_nomfic(reference_locale) or reference_locale


def ligne_csv_depuis_resultat(result, payload):
    proprietes = payload.get("proprietes") if isinstance(payload.get("proprietes"), dict) else {}
    pdf_reference = payload_pdf_reference(payload, result)
    latitude = payload.get("latitude", payload.get("lat", result.get("latitude", result.get("lat", ""))))
    longitude = payload.get("longitude", payload.get("long", result.get("longitude", result.get("long", ""))))
    adresse = payload.get("adresse_point") or result.get("adresse_point") or (
        f"{latitude}, {longitude}" if latitude not in ("", None) and longitude not in ("", None) else ""
    )
    zone = result.get("zone_effective") or result.get("zone") or payload.get("zone") or first_value(proprietes, "libelle", "zone")

    return {
        "adresse_point": serialiser_cellule(adresse),
        "lat": serialiser_cellule(latitude),
        "long": serialiser_cellule(longitude),
        "date_recherche": datetime.datetime.now().replace(microsecond=0).isoformat(),
        "date_edition_plu": serialiser_cellule(
            result.get("date_edition_plu")
            or extract_plu_date(pdf_reference)
            or extract_plu_date(first_value(proprietes, "date_edition", "date_edition_plu", "datappro", "date"))
        ),
        "ville": serialiser_cellule(payload.get("ville") or result.get("ville") or first_value(proprietes, "commune", "nom_com", "nom_commune")),
        "code_insee": serialiser_cellule(
            extract_code_postal(adresse)
            or extract_code_postal(payload.get("adresse"))
            or extract_code_postal(first_value(proprietes, "adresse", "adresse_point", "libelle_adresse"))
        ),
        "zone": serialiser_cellule(zone),
        "lettre_zone_envoyer": serialiser_cellule(payload.get("zone") or result.get("lettre_zone_envoyer") or result.get("zone")),
        "modele_ia": serialiser_cellule(result.get("modele_ia") or result.get("modele") or payload.get("fournisseur_ia")),
        "url_pdf": serialiser_cellule(
            first_http_url(result.get("url_pdf"), payload.get("url_pdf"), result.get("url"), payload.get("url"))
            or url_pdf_depuis_nomfic(result.get("pdf") or payload.get("pdf") or result.get("url_pdf") or payload.get("url_pdf"))
        ),
        "hauteur_maximale.valeur": serialiser_cellule(nested_value(result, "hauteur_maximale.valeur", result.get("hauteur_maximale.valeur", ""))),
        "hauteur_maximale.condition": serialiser_cellule(nested_value(result, "hauteur_maximale.condition", result.get("hauteur_maximale.condition", ""))),
        "hauteur_maximale.page": serialiser_cellule(nested_value(result, "hauteur_maximale.page", result.get("hauteur_maximale.page", ""))),
        "emprise_au_sol.valeur": serialiser_cellule(nested_value(result, "emprise_au_sol.valeur", result.get("emprise_au_sol.valeur", ""))),
        "emprise_au_sol.condition": serialiser_cellule(nested_value(result, "emprise_au_sol.condition", result.get("emprise_au_sol.condition", ""))),
        "emprise_au_sol.page": serialiser_cellule(nested_value(result, "emprise_au_sol.page", result.get("emprise_au_sol.page", ""))),
        "implantation_voies.regle": serialiser_cellule(nested_value(result, "implantation_voies.regle", result.get("implantation_voies.regle", ""))),
        "implantation_voies.page": serialiser_cellule(nested_value(result, "implantation_voies.page", result.get("implantation_voies.page", ""))),
        "implantation_limites.regle": serialiser_cellule(nested_value(result, "implantation_limites.regle", result.get("implantation_limites.regle", ""))),
        "implantation_limites.page": serialiser_cellule(nested_value(result, "implantation_limites.page", result.get("implantation_limites.page", ""))),
        "espaces_verts.regle": serialiser_cellule(nested_value(result, "espaces_verts.regle", result.get("espaces_verts.regle", ""))),
        "espaces_verts.page": serialiser_cellule(nested_value(result, "espaces_verts.page", result.get("espaces_verts.page", ""))),
        "stationnement.valeur_pl": serialiser_cellule(nested_value(result, "stationnement.valeur_pl", result.get("stationnement.valeur_pl", ""))),
        "stationnement.valeur_vl": serialiser_cellule(nested_value(result, "stationnement.valeur_vl", result.get("stationnement.valeur_vl", ""))),
        "stationnement.regle": serialiser_cellule(nested_value(result, "stationnement.regle", result.get("stationnement.regle", ""))),
        "stationnement.page": serialiser_cellule(nested_value(result, "stationnement.page", result.get("stationnement.page", ""))),
        "destinations.autorisees": serialiser_cellule(nested_value(result, "destinations.autorisees", result.get("destinations.autorisees", ""))),
        "destinations.interdites": serialiser_cellule(nested_value(result, "destinations.interdites", result.get("destinations.interdites", ""))),
        "contrainte_particulieres": serialiser_cellule(result.get("contrainte_particulieres") or result.get("contrainte_particulieres") or result.get("contraintes_particulieres", "")),
    }


def enregistrer_recherche_dans_base(result, payload, raison=""):
    columns = read_plu_base_columns()
    ligne = ligne_csv_depuis_resultat(result, payload)
    os.makedirs(DATA_DIR, exist_ok=True)
    exists = os.path.exists(PLU_BASE_CSV) and os.path.getsize(PLU_BASE_CSV) > 0
    with open(PLU_BASE_CSV, "a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        if not exists:
            writer.writeheader()
        writer.writerow({column: ligne.get(column, "") for column in columns})
    return {
        "csv": PLU_BASE_CSV,
        "raison": raison,
        "ligne_base_csv": ligne,
    }


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
        "controle_cache": "pdf_zone_date_plu_ok",
    })
    return payload


def find_plu_base_row(nomfic="", zone="", proprietes=None, latitude="", longitude="", ville=""):
    rows = read_plu_base_rows()
    if not rows:
        return None

    proprietes = proprietes or {}
    zone_key = normalize_zone(
        zone
        or first_value(proprietes, "libelle", "libelong", "zone", "typezone", "type_zone")
    )
    reference_pdf = nomfic or first_pdf_reference(proprietes)
    nomfic_clean = clean_nomfic(reference_pdf)
    expected_date = (
        extract_plu_date(nomfic_clean)
        or extract_plu_date(reference_pdf)
        or extract_plu_date(first_value(proprietes, "date_edition", "date_edition_plu", "datappro", "date"))
    )
    insee = (
        extract_insee(nomfic_clean)
        or extract_insee(reference_pdf)
        or extract_insee(first_value(proprietes, "insee", "code_insee", "codeinsee"))
        or extract_insee(first_value(proprietes, "partition", "idurba", "id_document", "gpu_doc_id", "url_pdf", "pdf"))
    )
    if not insee or not zone_key or not expected_date:
        return None

    for row in rows:
        row_zone = normalize_zone(row.get("zone"))
        row_insee = extract_insee(row.get("url_pdf") or row.get("fichier_source"))
        row_url = row.get("url_pdf", "")
        row_date = extract_plu_date(row.get("date_edition_plu")) or extract_plu_date(row_url)

        if insee and row_insee != insee:
            continue

        if zone_key:
            if not zones_compatibles(row_zone, zone_key):
                continue

        if expected_date and row_date != expected_date:
            continue

        return row

    return None


def download_pdf(nomfic, proprietes=None):
    return pdf_gpu.telecharger_pdf_gpu(nomfic, proprietes=proprietes, dossier_sortie=TMP_PDF_DIR)


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


def line_range_for_pages(lines, page_start, page_end):
    page_start = int(page_start)
    page_end = int(page_end)
    start = 0
    end = len(lines)
    for index, line in enumerate(lines):
        match = re.match(r"^# Page\s+(\d+)\b", line.strip(), re.IGNORECASE)
        if not match:
            continue
        page = int(match.group(1))
        if page == page_start:
            start = index
        elif page > page_end:
            end = index
            break
    return start, end


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

    def section_key(section):
        return normalize_zone(getattr(section, "zone", "")) or getattr(section, "cle", "")

    def meme_famille(section_cle, cle):
        if not section_cle or not cle:
            return False
        return section_cle == cle or section_cle.startswith(cle)

    def fin_section_elargie(position, cle):
        for suivante in sections[position + 1:]:
            suivante_cle = section_key(suivante)
            if not meme_famille(suivante_cle, cle):
                return suivante.debut_ligne
        return len(lines)

    def candidats_pour_cle(cle):
        candidats = []
        for position, section in enumerate(sections):
            if section_key(section) != cle:
                continue
            fin = fin_section_elargie(position, cle)
            candidats.append((fin - section.debut_ligne, section.debut_ligne, fin, section))
        return candidats

    matches = candidats_pour_cle(zone_key)
    if matches:
        longueur, start, end, section = max(matches, key=lambda item: (item[0], item[1]))
        detected_zone = section.zone
        match_perfect = True
    else:
        longueur, start, end, section = (0, 0, min(len(lines), 900), None)

    if (
        zone_key
        and (not matches or longueur < 250)
        and len(zone_key) > 1
        and zone_key[0] in ("A", "N")
    ):
        parent_matches = candidats_pour_cle(zone_key[0])
        if parent_matches:
            parent_longueur, parent_start, parent_end, parent_section = max(parent_matches, key=lambda item: (item[0], item[1]))
            if parent_longueur > max(longueur * 2, 250):
                longueur, start, end, section = parent_longueur, parent_start, parent_end, parent_section
                detected_zone = parent_section.zone
                match_perfect = False

    if not section:
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


def localiser_zone_par_sommaire(payload):
    markdown_path = payload.get("markdown_complet") or payload.get("markdown") or payload.get("markdown_section")
    zone = payload.get("zone", "")
    if not markdown_path or not os.path.exists(markdown_path):
        raise RuntimeError("Markdown complet introuvable pour localiser la zone via le sommaire.")

    client = ia_module.creer_client_ia(payload.get("fournisseur_ia"))
    with open(markdown_path, encoding="utf-8", errors="replace") as file:
        text = file.read()
    sommaire = ia_module.extraire_sommaire_markdown(text)
    if not sommaire.strip():
        raise RuntimeError("Sommaire introuvable dans le markdown complet.")

    localisation_detail = ia_module.localiser_pages_zone_detail(client, sommaire, zone)
    pages_ia = sorted({int(page) for page in localisation_detail["pages"] if str(page).isdigit()})
    zone_effective = localisation_detail["zone"]
    pages = list(pages_ia)
    localisation_rejetee = bool(pages_ia) and not zone_localisation_compatible(zone, zone_effective)
    if localisation_rejetee:
        pages = []
    lines = text.splitlines()
    if pages:
        page_start, page_end = min(pages), max(pages)
        start, end = line_range_for_pages(lines, page_start, page_end)
        content = "\n".join(lines[start:end]).strip()
        pages_localisees = [page_start, page_end]
    else:
        page_start = page_end = None
        start, end = 0, len(lines)
        content = text.strip()
        pages_localisees = []

    zone_section = zone if localisation_rejetee else (zone_effective or zone)
    safe_zone = re.sub(r"[^0-9A-Za-z_-]+", "_", str(zone_section or "zone")).strip("_") or "zone"
    page_suffix = f"_p{page_start}-{page_end}" if page_start and page_end else ""
    os.makedirs(TMP_MARKDOWN_SELECTION_DIR, exist_ok=True)
    output_path = safe_join(
        TMP_MARKDOWN_SELECTION_DIR,
        f"{os.path.splitext(os.path.basename(markdown_path))[0]}_{safe_zone}{page_suffix}.md",
    )
    header = [
        f"# Selection zone {zone_section}",
        "",
        f"- Fichier source : `{os.path.basename(markdown_path)}`",
        f"- Zone demandee : `{zone}`",
        f"- Zone trouvee par IA : `{zone_effective or zone}`",
    ]
    if localisation_rejetee:
        header.append("- Localisation IA rejetee : `true`")
    if page_start and page_end:
        header.append(f"- Pages : {page_start}-{page_end}")
    header += ["", "---", ""]
    with open(output_path, "w", encoding="utf-8") as file:
        file.write("\n".join(header) + content + "\n")

    os.makedirs(TMP_OUTPUT_AI_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    document_id = document_id_from_path(markdown_path)
    localisation_prefix = f"{document_id}_localisation_sommaire_{timestamp}"
    prompt_localisation = safe_join(TMP_OUTPUT_AI_DIR, f"{localisation_prefix}_prompt_envoye.md")
    sommaire_envoye = safe_join(TMP_OUTPUT_AI_DIR, f"{localisation_prefix}_sommaire_envoye.md")
    sortie_localisation = safe_join(TMP_OUTPUT_AI_DIR, f"{localisation_prefix}_reponse_ia.txt")
    json_localisation = safe_join(TMP_OUTPUT_AI_DIR, f"{localisation_prefix}.json")
    with open(prompt_localisation, "w", encoding="utf-8") as file:
        file.write(localisation_detail.get("prompt_envoye_texte", ""))
    with open(sommaire_envoye, "w", encoding="utf-8") as file:
        file.write(
            "\n".join([
                f"# Sommaire envoye a l'IA",
                "",
                f"- Fichier source : `{os.path.basename(markdown_path)}`",
                f"- Zone demandee : `{zone}`",
                "",
                "---",
                "",
                sommaire,
                "",
            ])
        )
    with open(sortie_localisation, "w", encoding="utf-8") as file:
        file.write(localisation_detail.get("texte_reponse", ""))
    trace_localisation = {
        "source_resultat": "localisation_sommaire",
        "fournisseur_ia": client.get("fournisseur", ""),
        "modele_ia": client.get("modele", ""),
        "zone_demandee": zone,
        "zone_effective": zone_section,
        "zone_ia": zone_effective or zone,
        "pages_ia": pages_ia,
        "pages_localisees": pages_localisees,
        "localisation_rejetee": localisation_rejetee,
        "markdown_complet": markdown_path,
        "markdown_section": output_path,
        "prompt_envoye": prompt_localisation,
        "sommaire_envoye": sommaire_envoye,
        "reponse_json": localisation_detail.get("json", {}),
        "sortie_ia": sortie_localisation,
    }
    with open(json_localisation, "w", encoding="utf-8") as file:
        json.dump(trace_localisation, file, ensure_ascii=False, indent=2)

    return {
        "source_resultat": "localisation_sommaire",
        "markdown_complet": markdown_path,
        "markdown_section": output_path,
        "zone": zone,
        "zone_effective": zone_section,
        "zone_ia": zone_effective or zone,
        "pages_localisees": pages_localisees,
        "pages_ia": pages_ia,
        "lignes_localisees": [start + 1, end],
        "match_parfait": bool(pages),
        "localisation_rejetee": localisation_rejetee,
        "prompt_envoye": prompt_localisation,
        "sommaire_envoye": sommaire_envoye,
        "sortie_localisation_sommaire": sortie_localisation,
        "json_localisation_sommaire": json_localisation,
        "reponse_localisation_sommaire": localisation_detail.get("json", {}),
    }


def local_ai_response(payload, retry=False, erreur_ia=""):
    zone = payload.get("zone", "")
    row = find_plu_base_row(
        zone=zone,
        latitude=payload.get("latitude", ""),
        longitude=payload.get("longitude", ""),
        proprietes={"url_pdf": payload.get("url_pdf") or payload.get("pdf", "")},
        ville=payload.get("ville", ""),
    )
    if row:
        result = row_to_plu_payload(row)
        result["nouvelle_ligne_base"] = enregistrer_recherche_dans_base(result, payload, "reprise_base_csv")
        return result

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
        "ia_envoyee": False,
        "erreur_ia": erreur_ia,
        "avertissement": "Aucune cle IA/module IA n'est configure. Reponse locale de secours produite pour ne pas bloquer le flux.",
        "reponse_brute": excerpt or "Markdown indisponible.",
    }
    output = safe_join(TMP_OUTPUT_AI_DIR, f"analyse_locale_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json")
    with open(output, "w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
    result["sortie_ia"] = output
    return result


def ai_response(payload, retry=False):
    zone = payload.get("zone", "")
    row = find_plu_base_row(
        zone=zone,
        latitude=payload.get("latitude", ""),
        longitude=payload.get("longitude", ""),
        proprietes={"url_pdf": payload.get("url_pdf") or payload.get("pdf", "")},
        ville=payload.get("ville", ""),
    )
    if row:
        result = row_to_plu_payload(row)
        result["nouvelle_ligne_base"] = enregistrer_recherche_dans_base(result, payload, "reprise_base_csv")
        return result

    markdown_path = payload.get("markdown_section") or payload.get("markdown") or payload.get("markdown_complet")
    if not markdown_path or not os.path.exists(markdown_path):
        return local_ai_response(payload, retry=retry, erreur_ia="Markdown introuvable pour l'appel IA.")

    try:
        client = ia_module.creer_client_ia(payload.get("fournisseur_ia"))
        with open(markdown_path, encoding="utf-8", errors="replace") as file:
            texte = file.read()
        resultat = ia_module.analyser_markdown(client, texte, zone, payload)
        resultat["retry_donnees_insuffisantes"] = bool(retry)
        os.makedirs(TMP_OUTPUT_AI_DIR, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        analyse_prefix = f"{document_id_from_path(markdown_path)}_analyse_ia_{timestamp}"
        output = safe_join(TMP_OUTPUT_AI_DIR, f"{analyse_prefix}.json")
        prompt_envoye = safe_join(TMP_OUTPUT_AI_DIR, f"{analyse_prefix}_prompt_envoye.md")
        sortie_brute = safe_join(TMP_OUTPUT_AI_DIR, f"{analyse_prefix}_reponse_ia.txt")
        with open(prompt_envoye, "w", encoding="utf-8") as file:
            file.write(resultat.get("prompt_envoye_texte", ""))
        with open(sortie_brute, "w", encoding="utf-8") as file:
            file.write(resultat.get("reponse_brute_texte", ""))
        resultat["prompt_envoye"] = prompt_envoye
        resultat["sortie_ia"] = sortie_brute
        resultat["json_final"] = output
        resultat.pop("prompt_envoye_texte", None)
        if not resultat.get("donnees_insuffisantes"):
            resultat["nouvelle_ligne_base"] = enregistrer_recherche_dans_base(resultat, payload, "analyse_ia")
        resultat["reponse_brute"] = dict(resultat)
        with open(output, "w", encoding="utf-8") as file:
            json.dump(resultat, file, ensure_ascii=False, indent=2)
        return resultat
    except ia_module.ErreurConfigurationIa as error:
        return local_ai_response(payload, retry=retry, erreur_ia=str(error))
    except Exception as error:
        return local_ai_response(payload, retry=retry, erreur_ia=f"Appel IA externe echoue: {error}")


def handle_api(path, payload):
    if path in ("/api/nouveau/telecharger-pdf", "/api/charger-plu-nomfic"):
        nomfic = payload.get("nomfic")
        proprietes = payload.get("proprietes") or {}
        zone = payload.get("zone") or proprietes.get("libelle") or proprietes.get("zone")
        cached = find_plu_base_row(
            nomfic=nomfic,
            zone=zone,
            proprietes=proprietes,
            ville=payload.get("ville", ""),
        )
        if cached:
            result = row_to_plu_payload(cached)
            result["nouvelle_ligne_base"] = enregistrer_recherche_dans_base(result, payload, "reprise_base_csv_pdf")
            return result
        return download_pdf(nomfic, proprietes)

    if path == "/api/charger-plu":
        commune = payload.get("commune") or {}
        raise RuntimeError(f"Recherche automatique par commune non disponible sans nomfic. Commune recue: {commune.get('nom') or commune.get('code') or commune}")

    if path == "/api/nouveau/markdown-section":
        return markdown_section(payload.get("pdf", ""), payload.get("zone", ""))

    if path == "/api/nouveau/localiser-zone-sommaire":
        return localiser_zone_par_sommaire(payload)

    if path in ("/api/nouveau/traitement-ia", "/api/analyser-zone"):
        return ai_response(payload, retry=False)

    if path == "/api/nouveau/traitement-ia-retry":
        return ai_response(payload, retry=True)

    return None
