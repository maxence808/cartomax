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


def detecter_sections_zones(texte: str) -> list[SectionZone]:
    lignes = texte.splitlines()
    debuts: list[tuple[int, str]] = []
    motif = re.compile(
        r"^\s{0,3}(?:#{1,6}\s*)?(?:zone|secteur)?\s*([A-Z]{1,4}[0-9A-Z-]*)\b",
        re.IGNORECASE,
    )

    for index, ligne in enumerate(lignes):
        propre = ligne.strip()
        if not propre:
            continue
        match = motif.match(propre)
        if not match:
            continue
        zone = match.group(1)
        cle = normaliser_zone(zone)
        if cle:
            debuts.append((index, zone))

    sections: list[SectionZone] = []
    for position, (debut, zone) in enumerate(debuts):
        fin = debuts[position + 1][0] if position + 1 < len(debuts) else len(lignes)
        sections.append(SectionZone(zone=zone, cle=normaliser_zone(zone), debut_ligne=debut, fin_ligne=fin))

    return sections
