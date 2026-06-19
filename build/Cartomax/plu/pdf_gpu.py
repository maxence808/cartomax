from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from urllib.parse import quote

import requests

GPU_DOCUMENT_URL = "https://www.geoportail-urbanisme.gouv.fr/api/document"
GPU_DOWNLOAD_BY_PARTITION_URL = (
    "https://www.geoportail-urbanisme.gouv.fr/api/document/download-by-partition/{partition}"
)
GPU_DATA_DOCUMENTS_URL = "https://data.geopf.fr/annexes/gpu/documents"


class ErreurTelechargementPdf(RuntimeError):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.details = details or {}


def ajouter_unique(liste: list, valeur) -> None:
    if valeur and valeur not in liste:
        liste.append(valeur)


def normaliser_nomfic_pdf(nomfic: str) -> str:
    valeur = str(nomfic or "").strip()
    if not valeur:
        return ""
    valeur = valeur.split("#", 1)[0].split("?", 1)[0]
    trouve = re.search(r"([^/\\]+?\.pdf)\b", valeur, flags=re.IGNORECASE)
    if trouve:
        return Path(trouve.group(1)).name
    return Path(valeur).name


def iter_valeurs_proprietes(valeur):
    if isinstance(valeur, dict):
        for sous_valeur in valeur.values():
            yield from iter_valeurs_proprietes(sous_valeur)
    elif isinstance(valeur, list):
        for sous_valeur in valeur:
            yield from iter_valeurs_proprietes(sous_valeur)
    else:
        yield valeur


def trouver_nomfic_pdf_dans_proprietes(proprietes: dict | None) -> str:
    pdfs: list[str] = []
    for valeur in iter_valeurs_proprietes(proprietes or {}):
        nomfic = normaliser_nomfic_pdf(str(valeur or ""))
        if nomfic.lower().endswith(".pdf"):
            pdfs.append(nomfic)
    for nomfic in pdfs:
        if est_pdf_reglement(nomfic):
            return nomfic
    return ""


def prefixe_partition_depuis_nomfic(nomfic: str) -> str:
    trouve = re.match(r"^(\d+)_", Path(nomfic or "").name)
    return trouve.group(1) if trouve else ""


def suffixe_partition_depuis_nomfic(nomfic: str) -> str:
    trouve = re.match(
        r"^\d+_reglement_\d{8}_([A-Za-z0-9]+)\.pdf$",
        Path(nomfic or "").name,
        flags=re.IGNORECASE,
    )
    return trouve.group(1).upper() if trouve else ""


def nomfic_reglement_probable(nomfic: str) -> str:
    nom = Path(nomfic or "").name
    trouve = re.match(r"^(\d+)_annexes?_(\d{8})(?:_[A-Za-z0-9]+)?\.pdf$", nom, flags=re.IGNORECASE)
    if trouve:
        return f"{trouve.group(1)}_reglement_{trouve.group(2)}.pdf"
    return ""


def partition_gpu_depuis_valeur(valeur) -> str:
    texte = str(valeur or "")
    trouve = re.search(r"\bDU_([A-Za-z0-9_]+)\b", texte, flags=re.IGNORECASE)
    if trouve:
        return f"DU_{trouve.group(1).upper()}"
    trouve = re.fullmatch(r"\d{5,}", texte.strip())
    if trouve:
        return f"DU_{trouve.group(0)}"
    return ""


def partitions_gpu_candidates(nomfic: str, proprietes: dict | None) -> list[str]:
    partitions: list[str] = []
    proprietes = proprietes or {}
    ajouter_unique(partitions, partition_gpu_depuis_valeur(proprietes.get("partition")))

    prefixe_nomfic = prefixe_partition_depuis_nomfic(nomfic)
    suffixe_nomfic = suffixe_partition_depuis_nomfic(nomfic)
    if prefixe_nomfic and suffixe_nomfic:
        ajouter_unique(partitions, f"DU_{prefixe_nomfic}_{suffixe_nomfic}")
    if prefixe_nomfic:
        ajouter_unique(partitions, f"DU_{prefixe_nomfic}")

    for cle in (
        "partition_doc",
        "idurba",
        "idUrba",
        "idu",
        "code_insee",
        "insee",
        "commune",
        "identifiant",
    ):
        ajouter_unique(partitions, partition_gpu_depuis_valeur(proprietes.get(cle)))

    for valeur in iter_valeurs_proprietes(proprietes):
        ajouter_unique(partitions, partition_gpu_depuis_valeur(valeur))

    return partitions


def gpu_doc_id_depuis_proprietes(proprietes: dict | None) -> str:
    proprietes = proprietes or {}
    valeur = (
        proprietes.get("gpu_doc_id")
        or proprietes.get("id_document")
        or proprietes.get("document_id")
        or proprietes.get("doc_id")
        or proprietes.get("id")
    )
    texte = str(valeur or "").strip()
    return "" if texte.startswith("DU_") else texte


def urls_geopf_depuis_proprietes(proprietes: dict | None, nomfic: str) -> list[str]:
    urls: list[str] = []
    if not nomfic:
        return urls
    nomfic_url = quote(nomfic, safe="")
    for valeur in iter_valeurs_proprietes(proprietes or {}):
        texte = str(valeur or "")
        for trouve in re.finditer(
            r"https?://data\.geopf\.fr/annexes/gpu/documents/(DU_[A-Za-z0-9_]+)/([^/\s)\]]+)/[^/\s)\]]+?\.pdf",
            texte,
            flags=re.IGNORECASE,
        ):
            partition = quote(trouve.group(1).upper(), safe="")
            document_id = quote(trouve.group(2), safe="")
            ajouter_unique(urls, f"{GPU_DATA_DOCUMENTS_URL}/{partition}/{document_id}/{nomfic_url}")
    return urls


def build_download_urls(proprietes_gpu: dict | None) -> list[str]:
    proprietes_gpu = proprietes_gpu or {}
    nomfic = normaliser_nomfic_pdf(
        proprietes_gpu.get("nomfic") or proprietes_gpu.get("nom_fichier") or ""
    )
    if not nomfic.lower().endswith(".pdf"):
        return []

    urls: list[str] = []
    nomfic_url = quote(nomfic, safe="")
    gpu_doc_id = gpu_doc_id_depuis_proprietes(proprietes_gpu)
    if gpu_doc_id:
        ajouter_unique(urls, f"{GPU_DOCUMENT_URL}/{quote(gpu_doc_id, safe='')}/files/{nomfic_url}")

    for url in urls_geopf_depuis_proprietes(proprietes_gpu, nomfic):
        ajouter_unique(urls, url)

    urlfic = (
        proprietes_gpu.get("urlfic")
        or proprietes_gpu.get("URLFIC")
        or proprietes_gpu.get("url_fic")
        or proprietes_gpu.get("url")
    )
    if urlfic and (
        not normaliser_nomfic_pdf(str(urlfic)).lower().endswith(".pdf")
        or est_pdf_reglement(normaliser_nomfic_pdf(str(urlfic)))
    ):
        ajouter_unique(urls, str(urlfic))

    partitions = partitions_gpu_candidates(nomfic, proprietes_gpu)
    if gpu_doc_id:
        for partition in partitions:
            partition_url = quote(partition, safe="")
            ajouter_unique(urls, f"{GPU_DATA_DOCUMENTS_URL}/{partition_url}/{quote(gpu_doc_id, safe='')}/{nomfic_url}")
    for partition in partitions:
        partition_url = quote(partition, safe="")
        ajouter_unique(urls, f"{GPU_DOCUMENT_URL}/download-by-partition/{partition_url}/file/{nomfic_url}")
    for partition in partitions:
        partition_url = quote(partition, safe="")
        ajouter_unique(urls, f"{GPU_DOCUMENT_URL}/download-by-partition/{partition_url}")

    return urls


def original_name_depuis_nomfic(nomfic: str) -> str:
    trouve = re.match(
        r"^(\d+)_reglement_(\d{8})(?:_[A-Za-z0-9]+)?\.pdf$",
        Path(nomfic or "").name,
        flags=re.IGNORECASE,
    )
    if not trouve:
        return ""
    return f"{trouve.group(1)}_PLU_{trouve.group(2)}"


def code_insee_depuis_nomfic_ou_proprietes(nomfic: str, proprietes: dict | None) -> str:
    for valeur in (
        nomfic,
        (proprietes or {}).get("insee"),
        (proprietes or {}).get("code_insee"),
        (proprietes or {}).get("commune"),
        (proprietes or {}).get("partition"),
        (proprietes or {}).get("idurba"),
    ):
        trouve = re.search(r"\b(\d{5})\b", str(valeur or ""))
        if trouve:
            return trouve.group(1)
    return ""


def json_ou_texte_reponse(reponse: requests.Response):
    try:
        return reponse.json()
    except ValueError:
        return (reponse.text or "")[:10000]


def decrire_reponse_api(reponse: requests.Response) -> dict:
    return {
        "url": reponse.url,
        "status_code": reponse.status_code,
        "reason": reponse.reason,
        "content_type": reponse.headers.get("Content-Type"),
        "body": json_ou_texte_reponse(reponse),
    }


def interroger_documents_gpu(partition: str, original_name: str = "") -> tuple[dict | None, dict]:
    reponse = requests.get(GPU_DOCUMENT_URL, params={"partition": partition}, timeout=30)
    trace = decrire_reponse_api(reponse)
    reponse.raise_for_status()
    documents = reponse.json()
    trace["documents"] = documents
    if not isinstance(documents, list):
        return None, trace

    candidats = [doc for doc in documents if doc.get("status") != "document.deleted"]
    if original_name:
        candidats_original = [doc for doc in candidats if doc.get("originalName") == original_name]
        if candidats_original:
            candidats = candidats_original
    if not candidats:
        candidats = documents
    document = candidats[-1] if candidats else None
    trace["document_selectionne"] = document
    return document, trace


def noms_pdf_depuis_document_gpu(document: dict | None) -> list[str]:
    if not isinstance(document, dict):
        return []
    noms: list[str] = []
    for valeur in iter_valeurs_proprietes(document):
        nomfic = normaliser_nomfic_pdf(str(valeur or ""))
        if nomfic.lower().endswith(".pdf") and nomfic not in noms:
            noms.append(nomfic)

    original_name = str(document.get("originalName") or "")
    trouve = re.match(r"^(\d+)_PLU_(\d{8})$", original_name, flags=re.IGNORECASE)
    if trouve:
        nom_probable = f"{trouve.group(1)}_reglement_{trouve.group(2)}.pdf"
        if nom_probable not in noms:
            noms.append(nom_probable)
    return [nom for nom in noms if est_pdf_reglement(nom)]


def noms_pdf_depuis_documents_gpu(documents) -> list[str]:
    noms: list[str] = []
    if not isinstance(documents, list):
        return noms
    for document in documents:
        if isinstance(document, dict) and document.get("status") == "document.deleted":
            continue
        for nomfic in noms_pdf_depuis_document_gpu(document):
            ajouter_unique(noms, nomfic)
    return noms


def trouver_nomfic_pdf_par_api_gpu(code_insee: str, details_api: dict) -> str:
    if not code_insee:
        return ""
    partition = f"DU_{code_insee}"
    document, trace_document = interroger_documents_gpu(partition)
    details_api.setdefault("recherche_document", []).append(trace_document)
    noms = noms_pdf_depuis_document_gpu(document)
    if not noms:
        noms = noms_pdf_depuis_documents_gpu(trace_document.get("documents"))
    details_api["nomfic_candidates_api"] = noms
    return noms[0] if noms else ""


def trouver_nomfic_pdf_par_partitions_gpu(partitions: list[str], details_api: dict) -> str:
    for partition in partitions:
        try:
            document, trace_document = interroger_documents_gpu(partition)
            details_api.setdefault("recherche_document", []).append(trace_document)
            noms = noms_pdf_depuis_document_gpu(document)
            if not noms:
                noms = noms_pdf_depuis_documents_gpu(trace_document.get("documents"))
            if noms:
                details_api["nomfic_candidates_api"] = noms
                details_api["partition_resolution"] = partition
                return noms[0]
        except Exception as erreur:
            details_api.setdefault("recherche_document", []).append({
                "erreur": str(erreur),
                "partition": partition,
            })
    return ""


def reponse_est_pdf(reponse: requests.Response) -> bool:
    if reponse.status_code != 200:
        return False
    if reponse.content.startswith(b"PK"):
        return False
    content_type = (reponse.headers.get("Content-Type") or "").lower()
    if "application/pdf" in content_type or "application/octet-stream" in content_type:
        return True
    return reponse.content.startswith(b"%PDF")


def raison_reponse_non_pdf(reponse: requests.Response) -> str:
    content_type = reponse.headers.get("Content-Type") or ""
    if reponse.status_code != 200:
        return f"status_code {reponse.status_code}"
    if reponse.content.startswith(b"PK"):
        return "archive ZIP recue, pas un PDF direct"
    if "json" in content_type.lower():
        return f"reponse JSON 200 ignoree ({content_type})"
    return f"content_type non PDF ({content_type or 'absent'})"


def decrire_tentative_pdf(reponse: requests.Response) -> dict:
    trace = decrire_reponse_api(reponse)
    trace["est_pdf"] = reponse_est_pdf(reponse)
    if not trace["est_pdf"]:
        trace["echec"] = raison_reponse_non_pdf(reponse)
    return trace


def enregistrer_pdf_depuis_reponse(reponse: requests.Response, destination: Path) -> bool:
    if not reponse_est_pdf(reponse):
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(reponse.content)
    return True


def telecharger_archive(partition: str, dossier_sortie: Path) -> Path | None:
    dossier_sortie.mkdir(parents=True, exist_ok=True)
    archive = dossier_sortie / f"{partition}.zip"
    if archive.exists() and archive.stat().st_size > 0:
        return archive
    url = GPU_DOWNLOAD_BY_PARTITION_URL.format(partition=quote(partition, safe=""))
    reponse = requests.get(url, timeout=120)
    if reponse.status_code == 404:
        return None
    reponse.raise_for_status()
    if not reponse.content.startswith(b"PK"):
        return None
    archive.write_bytes(reponse.content)
    return archive


def est_pdf_reglement(nom: str) -> bool:
    nom_minuscule = Path(nom).name.lower()
    if not nom_minuscule.endswith(".pdf"):
        return False
    return "reglement" in nom_minuscule


def extraire_pdf_archive(archive: Path, destination: Path, nomfic: str, details_api: dict) -> dict | None:
    with zipfile.ZipFile(archive, "r") as z:
        fichiers = z.namelist()
        fichier_exact = next((f for f in fichiers if Path(f).name.lower() == nomfic.lower()), None)
        if fichier_exact and est_pdf_reglement(fichier_exact):
            with z.open(fichier_exact) as source:
                destination.write_bytes(source.read())
            return {
                "statut": "pdf_extrait_archive",
                "nomfic": nomfic,
                "pdf": str(destination),
                "archive": str(archive),
                "taille_octets": destination.stat().st_size,
            }

        disponibles = [Path(f).name for f in fichiers if f.lower().endswith(".pdf")]
        details_api.setdefault("archive", []).append({"chemin": str(archive), "pdf_disponibles": disponibles})

        fichier_reglement = next((f for f in fichiers if est_pdf_reglement(f)), None)
        if fichier_reglement:
            destination_reglement = destination.parent / Path(fichier_reglement).name
            with z.open(fichier_reglement) as source:
                destination_reglement.write_bytes(source.read())
            return {
                "statut": "pdf_reglement_extrait_archive",
                "nomfic": Path(fichier_reglement).name,
                "nomfic_demande": nomfic,
                "pdf": str(destination_reglement),
                "archive": str(archive),
                "taille_octets": destination_reglement.stat().st_size,
            }
    return None


def resoudre_nomfic_pdf(nomfic: str, proprietes: dict | None, details_api: dict) -> str:
    nomfic_original = str(nomfic or "")
    nomfic_normalise = normaliser_nomfic_pdf(nomfic_original)
    if nomfic_normalise.lower().endswith(".pdf") and est_pdf_reglement(nomfic_normalise):
        return nomfic_normalise
    if nomfic_normalise.lower().endswith(".pdf"):
        details_api["nomfic_ignore_non_reglement"] = nomfic_normalise
        nomfic_probable = nomfic_reglement_probable(nomfic_normalise)
        if nomfic_probable:
            details_api["nomfic_reglement_probable"] = nomfic_probable
            return nomfic_probable

    nomfic_depuis_proprietes = trouver_nomfic_pdf_dans_proprietes(proprietes)
    details_api["nomfic_depuis_proprietes"] = nomfic_depuis_proprietes
    if nomfic_depuis_proprietes.lower().endswith(".pdf"):
        return nomfic_depuis_proprietes

    partitions = partitions_gpu_candidates(nomfic_normalise or nomfic_original, proprietes)
    details_api["partitions_resolution"] = partitions
    nomfic_partition = trouver_nomfic_pdf_par_partitions_gpu(partitions, details_api)
    if nomfic_partition.lower().endswith(".pdf"):
        return nomfic_partition

    code_insee = code_insee_depuis_nomfic_ou_proprietes(nomfic_original, proprietes)
    details_api["code_insee_resolution"] = code_insee
    try:
        nomfic_api = trouver_nomfic_pdf_par_api_gpu(code_insee, details_api)
    except Exception as erreur:
        details_api["recherche_document"] = {"erreur": str(erreur), "code_insee": code_insee}
        nomfic_api = ""
    if nomfic_api.lower().endswith(".pdf"):
        return nomfic_api

    raise ErreurTelechargementPdf("Aucun nom de PDF exploitable trouve.", details_api)


def telecharger_pdf_gpu(
    nomfic: str = "",
    proprietes: dict | None = None,
    dossier_sortie: str | Path = "telechargements_pdf",
) -> dict:
    proprietes = proprietes or {}
    dossier_sortie = Path(dossier_sortie)
    dossier_sortie.mkdir(parents=True, exist_ok=True)

    details_api = {
        "nomfic_recu": nomfic,
        "proprietes_gpu": proprietes,
        "recherche_document": [],
        "tentatives": [],
        "archive": [],
    }
    nomfic_resolu = resoudre_nomfic_pdf(nomfic, proprietes, details_api)
    destination = dossier_sortie / nomfic_resolu
    if destination.exists() and destination.stat().st_size > 0:
        return {
            "statut": "pdf_deja_present",
            "nomfic": nomfic_resolu,
            "pdf": str(destination),
            "taille_octets": destination.stat().st_size,
        }

    proprietes_telechargement = dict(proprietes)
    proprietes_telechargement["nomfic"] = nomfic_resolu
    partitions = partitions_gpu_candidates(nomfic_resolu, proprietes_telechargement)
    if not partitions:
        raise ErreurTelechargementPdf(f"Impossible de deduire la partition GPU depuis {nomfic_resolu}.", details_api)

    original_name = original_name_depuis_nomfic(nomfic_resolu)
    urls = build_download_urls(proprietes_telechargement)
    for partition in partitions:
        try:
            document, trace_document = interroger_documents_gpu(partition, original_name)
            details_api["recherche_document"].append(trace_document)
            document_id = document.get("id") if document else None
            if document_id:
                ajouter_unique(
                    urls,
                    f"{GPU_DOCUMENT_URL}/{quote(document_id, safe='')}/files/{quote(nomfic_resolu, safe='')}",
                )
                ajouter_unique(
                    urls,
                    f"{GPU_DATA_DOCUMENTS_URL}/{quote(partition, safe='')}/{quote(document_id, safe='')}/{quote(nomfic_resolu, safe='')}",
                )
        except Exception as erreur:
            details_api["recherche_document"].append({
                "erreur": str(erreur),
                "partition": partition,
                "original_name": original_name,
            })

    details_api["urls_testees"] = urls
    for url in urls:
        try:
            reponse = requests.get(url, timeout=120)
            tentative = decrire_tentative_pdf(reponse)
            details_api["tentatives"].append(tentative)
            if enregistrer_pdf_depuis_reponse(reponse, destination):
                return {
                    "statut": "pdf_telecharge",
                    "nomfic": nomfic_resolu,
                    "url": url,
                    "pdf": str(destination),
                    "taille_octets": destination.stat().st_size,
                    "details": details_api,
                }
        except Exception as erreur:
            details_api["tentatives"].append({"url": url, "erreur": str(erreur)})

    for partition in partitions:
        archive = telecharger_archive(partition, dossier_sortie)
        details_api["archive"].append({
            "partition": partition,
            "trouvee": bool(archive),
            "chemin": str(archive) if archive else None,
        })
        if not archive:
            continue
        resultat_archive = extraire_pdf_archive(archive, destination, nomfic_resolu, details_api)
        if resultat_archive:
            resultat_archive["details"] = details_api
            return resultat_archive

    raise ErreurTelechargementPdf(f"Telechargement impossible pour {nomfic_resolu}.", details_api)


def charger_json_proprietes(chemin: str) -> dict:
    if not chemin:
        return {}
    return json.loads(Path(chemin).read_text(encoding="utf-8"))
