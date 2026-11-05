"""Rapprochement des noms d'ouvrages Hub'Eau avec les entreprises du répertoire Sirene.

Hub'Eau ne fournit ni secteur ni taille d'entreprise, seulement un nom d'ouvrage libre.
Le rapprochement exige un mot distinctif commun : une ressemblance sur des mots génériques
(« GOLF », « USINE ») ne suffit jamais.
"""

from __future__ import annotations

import difflib
import json
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import ENTREPRISES_API, RAW
from .ingest import get_json

FORMES = [
    "USINE",
    "DE",
    "DU",
    "LA",
    "LE",
    "LES",
    "DES",
    "D",
    "L",
    "ET",
    "EN",
    "SAS",
    "SA",
    "SARL",
    "SNC",
    "SCEA",
    "EARL",
    "SCA",
    "SASU",
    "EURL",
    "STE",
    "SOC",
    "SOCIETE",
    "ETS",
    "ETABLISSEMENT",
    "ETABLISSEMENTS",
    "GAEC",
    "SCI",
]
GENERIQUES = {
    "GOLF",
    "CLUB",
    "ASSOCIATION",
    "ASS",
    "SPORTIVE",
    "FORAGE",
    "FORAGES",
    "PUITS",
    "CARRIERE",
    "CARRIERES",
    "INDUSTRIE",
    "INDUSTRIES",
    "FRANCE",
    "OUEST",
    "BRETAGNE",
    "ATLANTIQUE",
    "GROUPE",
    "COOPERATIVE",
    "PRODUCTIONS",
    "PRODUITS",
    "SERVICES",
    "CENTRE",
    "INTERNATIONAL",
}


def normaliser(texte: str | None) -> str:
    """Majuscules sans accents ni ponctuation."""
    sans_accent = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", sans_accent.upper()).split())


def nom_utile(texte: str | None) -> str:
    """Retire les formes juridiques et les mots de liaison."""
    return " ".join(m for m in normaliser(texte).split() if m not in FORMES)


def mots_distinctifs(texte: str | None) -> set[str]:
    return {m for m in nom_utile(texte).split() if m not in GENERIQUES and len(m) > 2}


@dataclass(frozen=True)
class Decision:
    confiance: str  # "forte", "moyenne" ou "aucune"
    similarite: float


def evaluer(nom_ouvrage: str, noms_candidat: list[str], meme_commune: bool) -> Decision:
    """Évalue un candidat Sirene à partir de ses dénominations et de sa localisation."""
    cible = nom_utile(nom_ouvrage)
    meilleure = max(
        (difflib.SequenceMatcher(None, nom_utile(n), cible).ratio() for n in noms_candidat),
        default=0.0,
    )
    communs = any(mots_distinctifs(n) & mots_distinctifs(nom_ouvrage) for n in noms_candidat)
    if not communs:
        return Decision("aucune", meilleure)
    if not meme_commune:  # un nom courant sans ancrage local produit trop d'homonymes
        return Decision("aucune", meilleure)
    return Decision("forte" if meilleure >= 0.7 else "moyenne", meilleure)


def rechercher(nom: str, departement: str) -> list[dict]:
    params = {"q": nom, "departement": departement, "per_page": 5}
    return get_json(ENTREPRISES_API, params, timeout=30)["results"]


def rapprocher_ouvrage(ouvrage: dict) -> dict:
    """Retient le meilleur candidat pour un ouvrage (code, nom, commune, département)."""
    cible = nom_utile(ouvrage["nom_ouvrage"])
    resultat = {"code_ouvrage": ouvrage["code_ouvrage"], "confiance": "aucune", "similarite": 0.0}
    meilleur_rang = 0
    rangs = {"aucune": 0, "moyenne": 1, "forte": 2}
    for candidat in rechercher(cible, ouvrage["code_departement"]) if cible else []:
        noms = [
            n
            for n in (
                candidat.get("nom_complet"),
                candidat.get("nom_raison_sociale"),
                candidat.get("sigle"),
            )
            if n
        ]
        sites = candidat.get("matching_etablissements") or []
        meme = any(s.get("commune") == ouvrage["code_commune_insee"] for s in sites)
        decision = evaluer(ouvrage["nom_ouvrage"], noms, meme)
        rang = rangs[decision.confiance]
        if rang > meilleur_rang or (
            rang == meilleur_rang and decision.similarite > resultat["similarite"] and rang
        ):
            meilleur_rang = rang
            resultat = {
                "code_ouvrage": ouvrage["code_ouvrage"],
                "confiance": decision.confiance,
                "similarite": round(decision.similarite, 3),
                "siren": candidat.get("siren"),
                "denomination": candidat.get("nom_complet"),
                "naf": candidat.get("activite_principale"),
                "categorie_entreprise": candidat.get("categorie_entreprise"),
                "tranche_effectif": candidat.get("tranche_effectif_salarie"),
            }
    return resultat


def rapprocher_ouvrages(
    chroniques: Path = RAW / "hubeau" / "chroniques.json",
    sortie: Path = RAW / "sirene" / "rapprochement.csv",
    pause: float = 0.2,
) -> pd.DataFrame:
    """Rapproche chaque ouvrage économique, avec reprise sur le fichier déjà constitué."""
    sortie.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(json.loads(chroniques.read_text()))
    ind = (
        df[df.code_usage == "IND"].sort_values("annee").drop_duplicates("code_ouvrage", keep="last")
    )
    deja = (
        pd.read_csv(sortie, dtype=str)
        if sortie.exists()
        else pd.DataFrame(columns=["code_ouvrage"])
    )
    lignes = deja.to_dict("records")
    connus = set(deja.code_ouvrage)
    for ouvrage in ind.to_dict("records"):
        if ouvrage["code_ouvrage"] not in connus:
            lignes.append(rapprocher_ouvrage(ouvrage))
            time.sleep(pause)  # l'API limite le nombre de requêtes par seconde
    resultat = pd.DataFrame(lignes)
    resultat.to_csv(sortie, index=False)
    return resultat
