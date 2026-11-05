"""Paramètres partagés par toutes les étapes du pipeline."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
POWERBI = ROOT / "powerbi" / "donnees"

DEPARTEMENTS = ("22", "29", "35", "56")

HUBEAU = "https://hubeau.eaufrance.fr/api/v1"
ENTREPRISES_API = "https://recherche-entreprises.api.gouv.fr/search"
VIGIEAU_DATASET = "https://www.data.gouv.fr/api/1/datasets/donnee-secheresse-vigieau/"

# Échelle ordinale des niveaux de restriction VigiEau.
GRAVITE = {"vigilance": 1, "alerte": 2, "alerte_renforcee": 3, "crise": 4}
