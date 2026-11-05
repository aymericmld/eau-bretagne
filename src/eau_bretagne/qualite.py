"""Contrôles bloquants : aucune table n'est publiée si l'un d'eux échoue."""

from __future__ import annotations

import pandas as pd

CLES = {
    "dim_commune": ["code_commune"],
    "dim_annee": ["annee"],
    "dim_mois": ["mois"],
    "fact_prelevements": ["code_commune", "annee", "usage", "milieu"],
    "fact_restrictions_mois": ["code_commune", "mois"],
    "fact_secteur": ["code_departement", "annee", "secteur"],
    "fact_taille": ["annee", "taille"],
    "fact_nappes_mois": ["code_departement", "mois"],
}
COLONNES_INTERDITES = {"nom_ouvrage", "siren", "denomination"}


def controler(tables: dict[str, pd.DataFrame], prelevements: pd.DataFrame) -> None:
    erreurs: list[str] = []
    for nom, cles in CLES.items():
        if tables[nom].duplicated(cles).any():
            erreurs.append(f"{nom} : clé dupliquée {cles}")
    for nom, table in tables.items():
        if COLONNES_INTERDITES & set(table.columns):
            erreurs.append(f"{nom} : colonne nominative publiée")

    connues = set(tables["dim_commune"].code_commune)
    for nom in ("fact_prelevements", "fact_restrictions_mois"):
        orphelins = set(tables[nom].code_commune) - connues
        if orphelins:
            erreurs.append(f"{nom} : {len(orphelins)} communes hors référentiel")

    if not set(tables["fact_restrictions_mois"].mois) <= set(tables["dim_mois"].mois):
        erreurs.append("fact_restrictions_mois : mois absent du calendrier")

    total_source = prelevements.volume.sum()
    total_table = tables["fact_prelevements"].volume_m3.sum()
    if abs(total_source - total_table) > 1:
        erreurs.append(f"volumes non réconciliés : {total_source} contre {total_table}")

    mois = tables["fact_restrictions_mois"]
    colonnes = ["jours_vigilance", "jours_restriction"]
    if (mois[colonnes].sum(axis=1) > mois.mois.dt.days_in_month).any():
        erreurs.append("fact_restrictions_mois : plus de jours que le mois n'en compte")

    indice = tables["dim_commune"].indice_exposition
    if indice.isna().any() or not indice.between(0, 100).all():
        erreurs.append("indice d'exposition manquant ou hors de [0, 100]")

    if erreurs:
        raise ValueError("Contrôles qualité en échec :\n- " + "\n- ".join(erreurs))
    print(f"contrôles qualité : {len(CLES) + 5} familles de contrôles validées")
