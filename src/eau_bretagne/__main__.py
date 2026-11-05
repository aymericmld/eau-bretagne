"""Ligne de commande : python -m eau_bretagne [collecte|sirene|transformation|tout]."""

import sys

from . import ingest, matching, pipeline


def collecte() -> None:
    ingest.collecter_communes()
    ingest.collecter_prelevements()
    ingest.collecter_arretes()
    ingest.collecter_piezometrie()
    ingest.collecter_restrictions_communes()


if __name__ == "__main__":
    etape = sys.argv[1] if len(sys.argv) > 1 else "tout"
    if etape in ("collecte", "tout"):
        collecte()
    if etape in ("sirene", "tout"):
        matching.rapprocher_ouvrages()
    if etape in ("transformation", "tout"):
        for nom, table in pipeline.construire().items():
            print(f"{nom}: {len(table)} lignes")
