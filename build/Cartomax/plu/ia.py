from __future__ import annotations

import json
import os
import re
from pathlib import Path

import requests

try:
    from .common import RACINE
except ImportError:
    from common import RACINE


DOSSIER_OUTPUT = RACINE / "tmp" / "output_ai"
MODELE_OPENROUTER = os.getenv("OPENROUTER_MODEL", "openrouter/owl-alpha")
MODELE_AISTUDIO = os.getenv("AISTUDIO_MODEL", "gemini-2.5-flash")
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
AISTUDIO_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{modele}:generateContent"

PROMPT_SYSTEME = """
Tu es un assistant specialise dans l'analyse de reglements de PLU francais.

Tu dois extraire les regles opposables importantes du document fourni.
Priorite d'analyse : immobilier d'activite, entrepots, locaux d'activite,
logistique, acces, livraison, stationnement, exploitation et contraintes
operationnelles liees a ces usages.
Tu ne dois pas inventer.
Si une information n'est pas presente dans le PDF ou le Markdown, indique "non precisee".
Si le bloc ne contient aucune reglementation applicable a un champ demande,
ecris exactement "pas de reglementation" pour ce champ ou dans les alertes.
Tu dois citer la page source quand elle est disponible dans le Markdown.

Regles imperatives :
- Reponds uniquement en JSON valide.
- Ne mets aucun texte avant le JSON.
- Ne mets aucun texte apres le JSON.
- N'utilise pas de bloc Markdown.
- N'utilise pas ```json.
- Les cles doivent toujours etre entre guillemets doubles.
- Les valeurs inconnues doivent etre "non precisee", pas null.
- Les champs sans reglementation dans le bloc doivent contenir "pas de reglementation".
- Si le texte recu est trop incomplet pour extraire des regles, ajoute exactement
  "donnees insuffisantes" dans le premier element du champ "alertes".
""".strip()

CHAMPS_REGLES_COMPLETS = [
    "hauteur_maximale",
    "emprise_au_sol",
    "implantation_voies",
    "implantation_limites",
    "stationnement",
    "espaces_verts",
    "destinations",
    "contraintes_particulieres",
]

_CHAMPS_CLES_INSUFFISANCE = [
    ("hauteur_maximale", "valeur"),
    ("emprise_au_sol", "valeur"),
    ("implantation_voies", "regle"),
    ("stationnement", "regle"),
    ("destinations", None),
]

_VALEURS_VIDES = {"non precise", "non precisé", "non précisé", "pas de reglementation", "pas de réglementation", ""}


class ErreurConfigurationIa(RuntimeError):
    pass


class ErreurReponseIa(RuntimeError):
    def __init__(self, message: str, prompt: str = "", reponse: str = ""):
        super().__init__(message)
        self.prompt = prompt
        self.reponse = reponse


def charger_env_local() -> None:
    env_path = RACINE / ".env"
    if not env_path.exists():
        return
    for ligne in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, valeur = ligne.split("=", 1)
        cle = cle.strip()
        valeur = valeur.strip().strip('"').strip("'")
        os.environ.setdefault(cle, valeur)


def _env_premier(*cles: str) -> str:
    charger_env_local()
    for cle in cles:
        valeur = os.environ.get(cle, "").strip()
        if valeur:
            return valeur
    return ""


def creer_client_ia(fournisseur: str | None = None) -> dict:
    fournisseur = (fournisseur or os.environ.get("PLU_IA_PROVIDER") or "openrouter").strip().lower()
    alias = {
        "openrouter": "openrouter",
        "or": "openrouter",
        "aistudio": "aistudio",
        "ai_studio": "aistudio",
        "ai-studio": "aistudio",
        "google": "aistudio",
        "gemini": "aistudio",
    }
    if fournisseur in alias:
        fournisseur = alias[fournisseur]
    if fournisseur in ("ai-studio", "google", "gemini"):
        fournisseur = "aistudio"

    if fournisseur == "openrouter":
        api_key = _env_premier("OPENROUTER_API_KEY", "OPENROUTER_KEY")
        if not api_key:
            raise ErreurConfigurationIa("Cle OPENROUTER_API_KEY manquante.")
        return {
            "fournisseur": "openrouter",
            "api_key": api_key,
            "modele": os.environ.get("OPENROUTER_MODEL", MODELE_OPENROUTER),
        }

    if fournisseur == "aistudio":
        api_key = _env_premier("GEMINI_API_KEY", "GOOGLE_API_KEY", "AISTUDIO_API_KEY")
        if not api_key:
            raise ErreurConfigurationIa("Cle GEMINI_API_KEY / GOOGLE_API_KEY / AISTUDIO_API_KEY manquante.")
        return {
            "fournisseur": "aistudio",
            "api_key": api_key,
            "modele": os.environ.get("AISTUDIO_MODEL", os.environ.get("GEMINI_MODEL", MODELE_AISTUDIO)),
        }

    raise ErreurConfigurationIa(f"Fournisseur IA inconnu: {fournisseur}")


def extraire_sommaire_markdown(texte: str) -> str:
    lignes = texte.splitlines()
    indexes = [
        index for index, ligne in enumerate(lignes)
        if re.search(r"\b(sommaire|table des matieres|table of contents)\b", ligne, re.IGNORECASE)
    ]
    if indexes:
        debut = max(0, indexes[0] - 5)
        fin = min(len(lignes), debut + 700)
        return "\n".join(lignes[debut:fin])
    return "\n".join(lignes[:900])


def construire_prompt_utilisateur(
    nom_fichier: str,
    bloc_markdown: str,
    zone: str = "",
    numero_bloc: int = 1,
    champs_cibles: list[str] | None = None,
) -> str:
    champs_cibles = champs_cibles or CHAMPS_REGLES_COMPLETS
    champs = ", ".join(champs_cibles)
    zone_cible = zone or "zone_generale"

    return f"""
Analyse ce bloc Markdown extrait d'un PLU.

Fichier : {nom_fichier}
Bloc : {numero_bloc}
Paquet par zone : zone_{zone_cible}
Zone cible : {zone_cible}
Champs cibles : {champs}

Objectif :
Extraire toutes les regles applicables a la zone cible de ce paquet.
Ne traite pas les autres zones sauf si elles sont citees comme exception ou limite.
Si le paquet contient une seule zone, le champ "zone" doit reprendre cette zone.
Si le bloc contient des pages referencees, applique-les seulement quand elles completent la zone cible.

Extraire les regles concernant :
- zone cible : {zone_cible}
- hauteur maximale des constructions
- emprise au sol
- implantation par rapport aux voies
- implantation par rapport aux limites separatives
- stationnement lie aux activites, avec distinction PL et VL quand le texte donne une valeur
- espaces verts / pleine terre
- destinations autorisees ou interdites, surtout activites, entrepots, industrie, commerce, bureaux, artisanat
- contraintes particulieres uniquement si elles ont un lien avec la logistique, l'activite, l'exploitation,
  les entrepots, les livraisons, les acces, les voiries, les poids lourds, les quais, les nuisances
  d'activite, les ICPE, les risques ou les servitudes impactant un site d'activite
- exceptions importantes

Ignore dans "contraintes_particulieres" les contraintes sans impact clair sur un site logistique
ou d'activite, par exemple les regles purement residentielles, patrimoniales ou decoratives,
sauf si elles limitent directement une construction ou exploitation d'activite.

Format JSON attendu :
{{
  "fichier": "{nom_fichier}",
  "bloc": {numero_bloc},
  "zones_detectees": [
    {{
      "zone": "",
      "hauteur_maximale": {{"valeur": "non precise", "condition": "non precise", "page_source": "non precise"}},
      "emprise_au_sol": {{"valeur": "non precise", "condition": "non precise", "page_source": "non precise"}},
      "implantation_voies": {{"regle": "non precise", "page_source": "non precise"}},
      "implantation_limites": {{"regle": "non precise", "page_source": "non precise"}},
      "stationnement": {{"regle": "non precise", "valeur_pl": "non precise", "valeur_vl": "non precise", "page_source": "non precise"}},
      "espaces_verts": {{"regle": "non precise", "page_source": "non precise"}},
      "destinations": {{"autorisees": [], "interdites": [], "page_source": "non precise"}},
      "contraintes_particulieres": [
        {{"description": "exemple de contrainte liee a l'activite", "page_source": "non precise"}}
      ]
    }}
  ],
  "alertes": []
}}

Markdown a analyser :
---
{bloc_markdown}
---
""".strip()


def _messages_localisation(sommaire: str, zone: str) -> list[dict]:
    prompt = (
        "Dans ce sommaire de reglement PLU, trouve les pages correspondant a la zone demandee. "
        "Reponds uniquement en JSON valide avec: {\"pages\": [1, 2], \"zone\": \"...\"}. "
        "Ne retourne pas une autre zone sans lien direct. "
        "Si la zone demandee est absente, retourne {\"pages\": [], \"zone\": \"zone demandee\"}. "
        f"Zone demandee: {zone}\n\nSommaire:\n{sommaire[:30000]}"
    )
    return [
        {"role": "system", "content": "Tu localises une zone PLU dans un sommaire. JSON uniquement."},
        {"role": "user", "content": prompt},
    ]


def messages_vers_markdown(messages: list[dict]) -> str:
    blocs = []
    for index, message in enumerate(messages, start=1):
        role = message.get("role", "message")
        content = message.get("content", "")
        blocs.append(f"## Message {index} - {role}\n\n{content}")
    return "\n\n---\n\n".join(blocs).strip() + "\n"


def extraire_json_depuis_texte(contenu: str):
    if not contenu:
        raise json.JSONDecodeError("Reponse vide", "", 0)

    texte = contenu.strip().lstrip("\ufeff")
    bloc_markdown = re.fullmatch(r"```(?:json|JSON)?\s*(.*?)\s*```", texte, flags=re.DOTALL)
    if bloc_markdown:
        texte = bloc_markdown.group(1).strip()

    debut_objet = texte.find("{")
    debut_tableau = texte.find("[")
    debuts = [index for index in (debut_objet, debut_tableau) if index != -1]
    if not debuts:
        raise json.JSONDecodeError("Aucun debut JSON trouve", texte, 0)

    decodeur = json.JSONDecoder()
    objet, _ = decodeur.raw_decode(texte[min(debuts):])
    return objet


def _appel_openrouter(client: dict, messages: list[dict]) -> str:
    reponse = requests.post(
        OPENROUTER_ENDPOINT,
        headers={
            "Authorization": f"Bearer {client['api_key']}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://127.0.0.1:8765",
            "X-Title": "Cartomax PLU",
        },
        json={
            "model": client["modele"],
            "messages": messages,
            "temperature": 0,
            "max_tokens": 12000,
        },
        timeout=180,
    )
    reponse.raise_for_status()
    data = reponse.json()
    return data["choices"][0]["message"]["content"]


def _appel_aistudio(client: dict, messages: list[dict]) -> str:
    systeme = next((item["content"] for item in messages if item["role"] == "system"), PROMPT_SYSTEME)
    texte = "\n\n".join(item["content"] for item in messages if item["role"] != "system")
    reponse = requests.post(
        AISTUDIO_ENDPOINT.format(modele=client["modele"]),
        params={"key": client["api_key"]},
        json={
            "systemInstruction": {"parts": [{"text": systeme}]},
            "contents": [{"role": "user", "parts": [{"text": texte}]}],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": 12000,
                "responseMimeType": "application/json",
            },
        },
        timeout=180,
    )
    reponse.raise_for_status()
    return extraire_texte_aistudio(reponse.json())


def extraire_texte_aistudio(donnees: dict) -> str:
    morceaux = []
    for candidat in donnees.get("candidates", []) or []:
        contenu = candidat.get("content") or {}
        for part in contenu.get("parts", []) or []:
            texte = part.get("text")
            if texte:
                morceaux.append(texte)
    return "\n".join(morceaux).strip()


def appeler_ia_json(client: dict, messages: list[dict]):
    if client["fournisseur"] == "openrouter":
        contenu = _appel_openrouter(client, messages)
    elif client["fournisseur"] == "aistudio":
        contenu = _appel_aistudio(client, messages)
    else:
        raise ErreurConfigurationIa(f"Fournisseur IA inconnu: {client['fournisseur']}")
    return extraire_json_depuis_texte(contenu)


def appeler_ia_json_avec_texte(client: dict, messages: list[dict]) -> tuple[dict, str]:
    if client["fournisseur"] == "openrouter":
        contenu = _appel_openrouter(client, messages)
    elif client["fournisseur"] == "aistudio":
        contenu = _appel_aistudio(client, messages)
    else:
        raise ErreurConfigurationIa(f"Fournisseur IA inconnu: {client['fournisseur']}")
    return extraire_json_depuis_texte(contenu), contenu


def appeler_ia(client_ia: dict, prompt: str, systeme: str | None = None) -> str:
    messages = [
        {"role": "system", "content": systeme if systeme is not None else PROMPT_SYSTEME},
        {"role": "user", "content": prompt},
    ]
    if client_ia["fournisseur"] == "openrouter":
        return _appel_openrouter(client_ia, messages)
    if client_ia["fournisseur"] == "aistudio":
        return _appel_aistudio(client_ia, messages)
    raise ErreurConfigurationIa("Client IA invalide.")


def donnees_insuffisantes(resultat: dict | None) -> bool:
    if not isinstance(resultat, dict):
        return True

    alertes = resultat.get("alertes") or []
    if alertes and str(alertes[0]).strip().lower() in {"donnees insuffisantes", "données insuffisantes"}:
        return True

    zones = resultat.get("zones_detectees") or []
    if not zones:
        return True

    def zone_vide(zone: dict) -> bool:
        if not isinstance(zone, dict):
            return True
        vides = 0
        for champ, sous_champ in _CHAMPS_CLES_INSUFFISANCE:
            bloc = zone.get(champ)
            if not isinstance(bloc, dict):
                vides += 1
                continue
            if sous_champ:
                valeur = str(bloc.get(sous_champ) or "").strip().lower()
                if valeur in _VALEURS_VIDES:
                    vides += 1
            else:
                autorisees = bloc.get("autorisees") or []
                if not autorisees:
                    vides += 1
        return vides >= len(_CHAMPS_CLES_INSUFFISANCE)

    return all(zone_vide(zone) for zone in zones)


def _liste_vers_texte(valeur) -> str:
    if isinstance(valeur, list):
        morceaux = []
        for item in valeur:
            if isinstance(item, dict):
                morceaux.append(str(item.get("description") or item.get("valeur") or item))
            else:
                morceaux.append(str(item))
        return " | ".join(morceaux)
    return "" if valeur is None else str(valeur)


def _page(bloc: dict) -> str:
    return str(bloc.get("page") or bloc.get("page_source") or "")


def adapter_resultat_standalone(resultat: dict, zone_demandee: str) -> dict:
    zones = resultat.get("zones_detectees") if isinstance(resultat, dict) else []
    zone_data = zones[0] if zones and isinstance(zones[0], dict) else {}
    zone_effective = str(zone_data.get("zone") or zone_demandee)
    hauteur = zone_data.get("hauteur_maximale") if isinstance(zone_data.get("hauteur_maximale"), dict) else {}
    emprise = zone_data.get("emprise_au_sol") if isinstance(zone_data.get("emprise_au_sol"), dict) else {}
    voies = zone_data.get("implantation_voies") if isinstance(zone_data.get("implantation_voies"), dict) else {}
    limites = zone_data.get("implantation_limites") if isinstance(zone_data.get("implantation_limites"), dict) else {}
    stationnement = zone_data.get("stationnement") if isinstance(zone_data.get("stationnement"), dict) else {}
    verts = zone_data.get("espaces_verts") if isinstance(zone_data.get("espaces_verts"), dict) else {}
    destinations = zone_data.get("destinations") if isinstance(zone_data.get("destinations"), dict) else {}

    return {
        "zone": zone_demandee,
        "zone_effective": zone_effective,
        "donnees_insuffisantes": donnees_insuffisantes(resultat),
        "hauteur_maximale": {
            "valeur": str(hauteur.get("valeur") or "non precise"),
            "condition": str(hauteur.get("condition") or "non precise"),
            "page": _page(hauteur),
        },
        "emprise_au_sol": {
            "valeur": str(emprise.get("valeur") or "non precise"),
            "condition": str(emprise.get("condition") or "non precise"),
            "page": _page(emprise),
        },
        "implantation_voies": {"regle": str(voies.get("regle") or "non precise"), "page": _page(voies)},
        "implantation_limites": {"regle": str(limites.get("regle") or "non precise"), "page": _page(limites)},
        "espaces_verts": {"regle": str(verts.get("regle") or "non precise"), "page": _page(verts)},
        "stationnement": {
            "valeur_pl": str(stationnement.get("valeur_pl") or "non precise"),
            "valeur_vl": str(stationnement.get("valeur_vl") or "non precise"),
            "regle": str(stationnement.get("regle") or "non precise"),
            "page": _page(stationnement),
        },
        "destinations": {
            "autorisees": _liste_vers_texte(destinations.get("autorisees")),
            "interdites": _liste_vers_texte(destinations.get("interdites")),
        },
        "contrainte_particulieres": _liste_vers_texte(zone_data.get("contraintes_particulieres")),
        "alertes": resultat.get("alertes") or [],
        "resultat_ia_detaille": resultat,
    }


def localiser_pages_zone(client: dict, sommaire: str, zone: str) -> tuple[list[int], str]:
    data = appeler_ia_json(client, _messages_localisation(sommaire, zone))
    pages = [int(page) for page in data.get("pages", []) if str(page).isdigit()]
    return pages, str(data.get("zone") or zone)


def localiser_pages_zone_detail(client: dict, sommaire: str, zone: str) -> dict:
    messages = _messages_localisation(sommaire, zone)
    data, texte_reponse = appeler_ia_json_avec_texte(client, messages)
    pages = [int(page) for page in data.get("pages", []) if str(page).isdigit()]
    return {
        "pages": pages,
        "zone": str(data.get("zone") or zone),
        "json": data,
        "texte_reponse": texte_reponse,
        "prompt_envoye_texte": messages_vers_markdown(messages),
    }


def analyser_markdown(client: dict, markdown: str, zone: str, contexte: dict | None = None) -> dict:
    contexte = contexte or {}
    nom_fichier = Path(
        contexte.get("markdown_section") or contexte.get("markdown") or contexte.get("markdown_complet") or "markdown.md"
    ).name
    prompt = construire_prompt_utilisateur(nom_fichier, markdown, zone=zone)
    if str(contexte.get("analyse_markdown_complet") or "").lower() == "true":
        prompt = (
            "IMPORTANT : tu recois le Markdown complet du reglement PLU, pas seulement une section.\n"
            f"Zone cherchee : {zone or 'zone non precisee'}.\n"
            "Tu dois extraire uniquement les regles applicables a cette zone cherchee.\n"
            "Ignore les autres zones, sauf si elles sont citees comme exceptions ou renvois applicables a la zone cherchee.\n\n"
            f"{prompt}"
        )
    messages = [
        {"role": "system", "content": PROMPT_SYSTEME},
        {"role": "user", "content": prompt},
    ]
    texte_reponse = appeler_ia(client, prompt)
    try:
        resultat_json = extraire_json_depuis_texte(texte_reponse)
    except Exception as erreur:
        raise ErreurReponseIa(
            f"Reponse IA non exploitable: {erreur}",
            prompt=messages_vers_markdown(messages),
            reponse=texte_reponse,
        ) from erreur
    data = adapter_resultat_standalone(resultat_json, zone)
    data.update({
        "source_resultat": "ia",
        "modele_ia": client["modele"],
        "fournisseur_ia": client["fournisseur"],
        "ia_envoyee": True,
        "zone": data.get("zone") or zone,
        "zone_effective": data.get("zone_effective") or data.get("zone") or zone,
        "ville": contexte.get("ville", ""),
        "adresse_point": contexte.get("adresse_point", ""),
        "latitude": contexte.get("latitude", ""),
        "longitude": contexte.get("longitude", ""),
        "pdf": contexte.get("pdf", ""),
        "archive": contexte.get("archive", ""),
        "markdown_zone": contexte.get("markdown_section") or contexte.get("markdown") or contexte.get("markdown_complet") or "",
        "prompt_envoye_texte": messages_vers_markdown(messages),
        "reponse_brute_texte": texte_reponse,
    })
    return data


def analyser_fichier_markdown(client: dict, chemin: Path) -> Path:
    texte = chemin.read_text(encoding="utf-8", errors="replace")
    zone = chemin.stem.rsplit("_", 1)[-1]
    resultat = analyser_markdown(client, texte, zone, {"markdown_section": str(chemin)})
    DOSSIER_OUTPUT.mkdir(parents=True, exist_ok=True)
    sortie = DOSSIER_OUTPUT / f"{chemin.stem}_analyse_brute.json"
    sortie.write_text(json.dumps(resultat, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK IA : {sortie}")
    return sortie
