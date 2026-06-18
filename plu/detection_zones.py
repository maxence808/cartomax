from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SectionZone:
    zone: str
    cle: str
    debut_ligne: int
    fin_ligne: int


def normaliser_zone(zone: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "", str(zone or "")).upper()


_MOTS_PAS_CODES = {
    "AFFECTEE",
    "AGRICOLE",
    "AGRICOLES",
    "COMPREND",
    "CONCERNEE",
    "DANS",
    "DEDIEE",
    "DESTINEE",
    "DONNEE",
    "DU",
    "ET",
    "EST",
    "FORESTIERE",
    "FORESTIERES",
    "HUMIDE",
    "INONDABLE",
    "MIXTE",
    "NATURELLE",
    "NATURELLES",
    "NON",
    "OU",
    "URBAINE",
    "URBAINES",
    "ZONES",
}


def _code_zone_valide(zone: str) -> bool:
    cle = normaliser_zone(zone)
    if not cle or cle in _MOTS_PAS_CODES:
        return False
    if not re.match(r"^(?:[0-9]+)?(?:U|AU|A|N|I|II)", cle):
        return False
    return bool(re.search(r"\d", cle) or len(cle) <= 5)


def _sans_accents(texte: str) -> str:
    import unicodedata

    valeur = unicodedata.normalize("NFKD", str(texte or ""))
    return "".join(car for car in valeur if not unicodedata.combining(car))


def _ligne_sommaire(ligne: str) -> bool:
    propre = ligne.strip()
    return bool(
        re.search(r"\.{5,}\s*\d+\s*$", propre)
        or re.search(r"\s{8,}\d+\s*$", propre)
    )


def _zone_depuis_titre(ligne: str) -> str:
    propre = ligne.strip()
    if not propre or _ligne_sommaire(propre):
        return ""

    simple = _sans_accents(propre)
    compact = re.sub(r"\s+", " ", simple).strip()
    upper = compact.upper()

    motifs = [
        r"\bDISPOSITIONS\s+APPLICABLES\s+(?:A|AUX|AU)\s+(?:LA\s+)?ZONE\s+([A-Z]{1,4}[0-9A-Z-]*)\b",
        r"\b(?:CHAPITRE|TITRE|SOUS\s*TITRE)\b.*\bZONE\b.*[:\-]\s*([A-Z]{1,4}[0-9A-Z-]*)\s*$",
        r"\bZONE\b.*[:\-]\s*([A-Z]{1,4}[0-9A-Z-]*)\s*$",
        r"^ZONE\s+([A-Z]{1,4}[0-9A-Z-]*)\b(?:\s*[:\-].*)?$",
        r"^([A-Z]{1,4}[0-9A-Z-]*)\s*[-:]\s*ZONE\b",
    ]
    for motif in motifs:
        match = re.search(motif, upper, re.IGNORECASE)
        if match and _code_zone_valide(match.group(1)):
            return match.group(1)

    # Certains reglements introduisent les sections A/N par un titre generique
    # avant la phrase descriptive de la zone, sans ligne "Zone N" dediee.
    if re.search(r"\bZONE(?:S)?\s+AGRICOLE(?:S)?\b", upper):
        return "A"
    if re.search(r"\bZONE(?:S)?\s+NATURELLE(?:S)?(?:\s+ET\s+FORESTIERE(?:S)?)?\b", upper):
        return "N"
    if re.match(r"^LA\s+ZONE\s+([A-Z]{1,4}[0-9A-Z-]*)\s+(?:CLASSE|CORRESPOND|COMPREND|EST)\b", upper):
        return re.match(r"^LA\s+ZONE\s+([A-Z]{1,4}[0-9A-Z-]*)\b", upper).group(1)

    return ""


def detecter_sections_zones(texte: str) -> list[SectionZone]:
    lignes = texte.splitlines()
    debuts: list[tuple[int, str]] = []

    for index, ligne in enumerate(lignes):
        zone = _zone_depuis_titre(ligne)
        cle = normaliser_zone(zone)
        if cle:
            debuts.append((index, zone))

    sections: list[SectionZone] = []
    for position, (debut, zone) in enumerate(debuts):
        fin = debuts[position + 1][0] if position + 1 < len(debuts) else len(lignes)
        sections.append(SectionZone(zone=zone, cle=normaliser_zone(zone), debut_ligne=debut, fin_ligne=fin))

    return sections
