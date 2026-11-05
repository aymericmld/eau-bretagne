"""Assemble les sources en un modèle en étoile prêt pour Power BI."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import qualite
from . import transform as t
from .config import POWERBI, PROCESSED, RAW, ROOT

ANNEES_INDICE = range(2016, 2026)  # dix années complètes ; 2026 reste partielle
ANNEES_PRESSION = range(2020, 2025)
DEPARTEMENTS_NOMS = {
    "22": "Côtes-d'Armor",
    "29": "Finistère",
    "35": "Ille-et-Vilaine",
    "56": "Morbihan",
}


def charger_json(chemin) -> pd.DataFrame:
    return pd.DataFrame(json.loads(chemin.read_text()))


def construire_communes() -> pd.DataFrame:
    communes = charger_json(RAW / "geo" / "communes.json")
    epci = charger_json(RAW / "geo" / "epci.json").rename(
        columns={"code": "codeEpci", "nom": "nom_epci"}
    )
    communes = communes.merge(epci, on="codeEpci", how="left")
    communes["longitude"] = communes.centre.map(lambda c: c["coordinates"][0])
    communes["latitude"] = communes.centre.map(lambda c: c["coordinates"][1])
    communes = communes.rename(
        columns={
            "code": "code_commune",
            "nom": "nom_commune",
            "codeDepartement": "code_departement",
            "codeEpci": "code_epci",
        }
    )
    communes["surface_km2"] = communes.surface / 100
    # Les îles sans EPCI forment leur propre territoire pour le calcul de la pression.
    communes["code_epci"] = communes.code_epci.fillna(communes.code_commune)
    communes["nom_epci"] = communes.nom_epci.fillna(communes.nom_commune)
    colonnes = [
        "code_commune",
        "nom_commune",
        "code_departement",
        "code_epci",
        "nom_epci",
        "population",
        "surface_km2",
        "longitude",
        "latitude",
    ]
    return communes[colonnes]


def rattacher_communes(df: pd.DataFrame, communes: pd.DataFrame) -> pd.DataFrame:
    """Remplace les codes de communes fusionnées par ceux de la commune actuelle."""
    fusions = pd.read_csv(ROOT / "data" / "reference" / "communes_fusionnees.csv", dtype=str)
    # Des homonymes existent entre départements : la recherche se fait par couple.
    codes = communes.set_index(["code_departement", "nom_commune"]).code_commune.to_dict()
    passage = {
        f.code_ancien: codes.get((f.code_ancien[:2], f.nom_actuel)) for f in fusions.itertuples()
    }
    if any(pd.isna(code) for code in passage.values()):
        raise ValueError("commune actuelle introuvable dans le référentiel")
    return df.assign(code_commune=df.code_commune.replace(passage))


def construire_ouvrages(prelevements: pd.DataFrame) -> pd.DataFrame:
    """Secteur et taille d'entreprise pour chaque ouvrage économique."""
    corrections = pd.read_csv(ROOT / "data" / "reference" / "corrections_secteur.csv")
    rapprochement = pd.read_csv(RAW / "sirene" / "rapprochement.csv", dtype=str)
    economiques = prelevements[prelevements.code_usage == "IND"]
    ouvrages = economiques.sort_values("annee").drop_duplicates("code_ouvrage", keep="last")
    ouvrages = ouvrages[["code_ouvrage", "nom_ouvrage"]].merge(
        rapprochement, on="code_ouvrage", how="left"
    )
    classes = [t.classer_secteur(o.nom_ouvrage, o.naf, corrections) for o in ouvrages.itertuples()]
    ouvrages[["secteur", "origine_secteur"]] = classes
    categorie = ouvrages.categorie_entreprise.where(ouvrages.confiance.ne("aucune"))
    ouvrages["taille"] = categorie.fillna("Non classé")
    return ouvrages


def construire_exposition(
    communes: pd.DataFrame, prelevements: pd.DataFrame, annuel: pd.DataFrame
) -> pd.DataFrame:
    """Trois composantes : gravité des restrictions, pression et dépendance aux eaux de surface."""
    recent = prelevements[prelevements.annee.isin(ANNEES_PRESSION)]
    recent = recent.merge(communes[["code_commune", "code_epci"]], on="code_commune")
    par_epci = recent.groupby("code_epci").volume.sum() / len(ANNEES_PRESSION)
    surface_epci = recent[recent.milieu == "Surface"].groupby("code_epci").volume.sum()
    surface_epci = surface_epci / len(ANNEES_PRESSION)
    aire = communes.groupby("code_epci").surface_km2.sum()

    expo = communes[["code_commune", "code_epci"]].copy()
    expo["gravite"] = expo.code_commune.map(t.score_gravite(annuel, ANNEES_INDICE)).fillna(0)
    expo["pression"] = expo.code_epci.map((par_epci / aire).fillna(0)).fillna(0)
    part = (surface_epci.reindex(par_epci.index).fillna(0) / par_epci.replace(0, np.nan)).fillna(0)
    expo["surface"] = expo.code_epci.map(part).fillna(0)
    expo["indice_exposition"] = t.indice_exposition(expo).round(1)
    expo["classe_exposition"] = t.classer_exposition(expo.indice_exposition)
    return expo.drop(columns="code_epci").rename(
        columns={
            "gravite": "score_gravite_annuel",
            "pression": "pression_m3_km2",
            "surface": "part_eau_surface",
        }
    )


def construire() -> dict[str, pd.DataFrame]:
    communes = construire_communes()
    prelevements = t.nettoyer_prelevements(
        charger_json(RAW / "hubeau" / "chroniques.json"),
        charger_json(RAW / "hubeau" / "ouvrages.json"),
    )
    prelevements = rattacher_communes(prelevements, communes)
    ouvrages = construire_ouvrages(prelevements)

    brut = pd.read_csv(
        RAW / "vigieau" / "restrictions_communes_bretagne.csv",
        dtype={"code_commune": str},
        usecols=["code_commune", "date", "AEP", "SOU", "SUP"],
    )
    jours = t.jours_par_niveau(brut)
    jours = jours[jours.code_commune.isin(communes.code_commune)]
    annuel = t.agreger_restrictions(jours, "YS")
    mensuel = t.agreger_restrictions(jours, "MS").rename(columns={"periode": "mois"})

    exposition = construire_exposition(communes, prelevements, annuel)
    dim_commune = communes.merge(exposition, on="code_commune")

    fact_prelevements = prelevements.groupby(
        ["code_commune", "annee", "usage", "milieu"], as_index=False
    ).agg(volume_m3=("volume", "sum"), nb_ouvrages=("code_ouvrage", "nunique"))

    economiques = prelevements[prelevements.code_usage == "IND"].merge(
        ouvrages[["code_ouvrage", "secteur", "taille"]], on="code_ouvrage"
    )
    actifs = economiques[economiques.volume > 0]
    fact_secteur = t.masquer_petits_effectifs(
        actifs.groupby(["code_departement", "annee", "secteur"], as_index=False).agg(
            volume_m3=("volume", "sum"), nb_ouvrages=("code_ouvrage", "nunique")
        )
    )
    fact_taille = t.masquer_petits_effectifs(
        actifs.groupby(["annee", "taille"], as_index=False).agg(
            volume_m3=("volume", "sum"), nb_ouvrages=("code_ouvrage", "nunique")
        )
    )

    stations = charger_json(RAW / "hubeau" / "piezo_stations.json")
    piezo = pd.read_csv(RAW / "hubeau" / "piezo_chroniques.csv")
    nappes = t.percentile_nappe(piezo).merge(
        stations[["code_bss", "code_departement"]], on="code_bss"
    )
    fact_nappes = nappes.groupby(["code_departement", "mois"], as_index=False).agg(
        percentile_median=("percentile", "median"), nb_stations=("code_bss", "nunique")
    )

    dim_departement = pd.DataFrame(
        DEPARTEMENTS_NOMS.items(), columns=["code_departement", "departement"]
    )
    mois = pd.date_range("2008-01-01", "2026-12-01", freq="MS")
    dim_mois = pd.DataFrame({"mois": mois, "annee": mois.year, "numero_mois": mois.month})
    dim_annee = pd.DataFrame({"annee": sorted(dim_mois.annee.unique())})
    tables = {
        "dim_commune": dim_commune,
        "dim_departement": dim_departement,
        "dim_annee": dim_annee,
        "dim_mois": dim_mois,
        "fact_prelevements": fact_prelevements,
        "fact_restrictions_mois": mensuel,
        "fact_secteur": fact_secteur,
        "fact_taille": fact_taille,
        "fact_nappes_mois": fact_nappes,
    }
    qualite.controler(tables, prelevements)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    POWERBI.mkdir(parents=True, exist_ok=True)
    # Les noms d'ouvrages restent locaux : seules des données agrégées sont publiées.
    economiques.to_parquet(PROCESSED / "prelevements_economiques.parquet")
    ouvrages.to_parquet(PROCESSED / "ouvrages_secteurs.parquet")
    annuel.to_parquet(PROCESSED / "restrictions_annuelles.parquet")
    for nom, table in tables.items():
        table.to_parquet(PROCESSED / f"{nom}.parquet")
        table.to_csv(POWERBI / f"{nom}.csv", index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(POWERBI / "eau_bretagne_modele.xlsx") as classeur:
        for nom, table in tables.items():
            table.to_excel(classeur, sheet_name=nom, index=False)
    return tables
