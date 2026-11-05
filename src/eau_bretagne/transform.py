"""Nettoyage des sources et calcul des indicateurs. Fonctions pures, testées unitairement."""

from __future__ import annotations

import re

import pandas as pd

from .config import GRAVITE
from .matching import normaliser

USAGES = {
    "AEP": "Eau potable",
    "IND": "Activités économiques",
    "IRR": "Irrigation",
}
USAGES_EXCLUS = {"BAR", "CAN"}  # eau turbinée ou transitant : elle retourne au milieu
SEUIL_DIFFUSION = 3  # pas de résultat sectoriel publié sous 3 ouvrages
PONDERATIONS = {"gravite": 0.5, "pression": 0.3, "surface": 0.2}


def nettoyer_prelevements(brut: pd.DataFrame, ouvrages: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par ouvrage, année et usage, avec le type de ressource."""
    df = brut[~brut.code_usage.isin(USAGES_EXCLUS)].copy()
    cles = ["code_ouvrage", "annee", "code_usage"]
    # Doublons : même ouvrage déclaré par deux agences ; on garde le plus grand volume.
    df = df.sort_values("volume", ascending=False).drop_duplicates(cles)
    milieu = ouvrages.drop_duplicates("code_ouvrage")[["code_ouvrage", "libelle_type_milieu"]]
    df = df.merge(milieu, on="code_ouvrage", how="left")
    df["milieu"] = df.libelle_type_milieu.map(
        {"Souterrain": "Souterrain", "Surface continental": "Surface"}
    ).fillna("Non renseigné")
    df["usage"] = df.code_usage.map(USAGES)
    df["volume_forfaitaire"] = df.libelle_mode_obtention_volume.eq("Volume forfaitaire")
    colonnes = cles + [
        "usage",
        "milieu",
        "volume",
        "volume_forfaitaire",
        "code_commune_insee",
        "code_departement",
        "nom_ouvrage",
        "longitude",
        "latitude",
    ]
    return df[colonnes].rename(columns={"code_commune_insee": "code_commune"})


def secteur_depuis_naf(naf: object) -> str | None:
    """Regroupe un code NAF rév. 2 (ou rév. 1 pour les entités anciennes) en secteur lisible."""
    if not isinstance(naf, str) or len(naf) < 2 or not naf[:2].isdigit():
        return None
    division = int(naf[:2])
    ancien = re.fullmatch(r"\d\d\.\d[A-Z]", naf) is not None
    if ancien:
        return {15: "Agroalimentaire", 92: "Sports et loisirs"}.get(division, "Services et autres")
    if division in (10, 11):
        return "Agroalimentaire"
    if division <= 3:
        return "Agriculture et aquaculture"
    if division <= 9:
        return "Carrières et matériaux"
    if division <= 33:
        return "Autre industrie"
    if division <= 39:
        return "Énergie, eau et déchets"
    if division == 93:
        return "Sports et loisirs"
    if division == 96:
        return "Blanchisserie"
    if division in (84, 85, 86, 87, 88):
        return "Services publics et santé"
    return "Services et autres"


def classer_secteur(nom: str, naf: object, corrections: pd.DataFrame) -> tuple[str, str]:
    """Priorité au motif documenté, puis au NAF Sirene. Renvoie (secteur, origine)."""
    nom_normalise = normaliser(nom)
    for correction in corrections.itertuples():
        if re.search(rf"\b(?:{correction.motif_nom})\b", nom_normalise):
            return correction.secteur, "correction documentée"
    secteur = secteur_depuis_naf(naf)
    if secteur:
        return secteur, "Sirene"
    return "Non identifié", "aucune"


def jours_par_niveau(restrictions: pd.DataFrame) -> pd.DataFrame:
    """Niveau quotidien d'une commune : le plus sévère parmi les ressources AEP, SOU et SUP."""
    df = restrictions.copy()
    niveaux = df[["AEP", "SOU", "SUP"]].apply(lambda c: c.map(GRAVITE)).fillna(0)
    df["niveau"] = niveaux.max(axis=1).astype(int)
    df["date"] = pd.to_datetime(df.date)
    return df[df.niveau > 0][["code_commune", "date", "niveau"]]


def agreger_restrictions(jours: pd.DataFrame, frequence: str = "YS") -> pd.DataFrame:
    """Nombre de jours par niveau, par commune et par période."""
    periode = jours.date.dt.to_period("Y" if frequence == "YS" else "M").dt.start_time
    tableau = (
        jours.assign(periode=periode)
        .pivot_table(
            index=["code_commune", "periode"],
            columns="niveau",
            values="date",
            aggfunc="count",
            fill_value=0,
        )
        .reindex(columns=[1, 2, 3, 4], fill_value=0)
    )
    tableau.columns = ["jours_vigilance", "jours_alerte", "jours_alerte_renforcee", "jours_crise"]
    tableau["jours_restriction"] = tableau[
        ["jours_alerte", "jours_alerte_renforcee", "jours_crise"]
    ].sum(axis=1)
    return tableau.reset_index()


def score_gravite(annuel: pd.DataFrame, annees: range) -> pd.Series:
    """Jours pondérés par an : alerte = 1, alerte renforcée = 2, crise = 3. Vigilance exclue."""
    fenetre = annuel[annuel.periode.dt.year.isin(annees)]
    total = (
        (fenetre.jours_alerte + 2 * fenetre.jours_alerte_renforcee + 3 * fenetre.jours_crise)
        .groupby(fenetre.code_commune)
        .sum()
    )
    return total / len(annees)


def rang_centile(serie: pd.Series) -> pd.Series:
    """Rang relatif de 0 à 100. Les ex æquo partagent le même rang."""
    return serie.rank(pct=True, method="average") * 100


def indice_exposition(
    composantes: pd.DataFrame, poids: dict[str, float] = PONDERATIONS
) -> pd.Series:
    """Moyenne pondérée des rangs centiles : l'indice est relatif à la Bretagne."""
    if abs(sum(poids.values()) - 1) > 1e-9:
        raise ValueError("les pondérations doivent totaliser 1")
    return sum(rang_centile(composantes[nom]) * valeur for nom, valeur in poids.items())


def classer_exposition(indice: pd.Series) -> pd.Series:
    """Quatre classes de même effectif : une lecture relative, pas un seuil de danger."""
    libelles = ["1 - Faible", "2 - Modérée", "3 - Élevée", "4 - Très élevée"]
    return pd.qcut(indice.rank(method="first"), 4, labels=libelles).astype(str)


def masquer_petits_effectifs(df: pd.DataFrame, colonne: str = "nb_ouvrages") -> pd.DataFrame:
    """Applique le seuil de diffusion pour qu'aucun site ne soit identifiable par déduction."""
    return df[df[colonne] >= SEUIL_DIFFUSION].copy()


def percentile_nappe(chroniques: pd.DataFrame, min_annees: int = 8) -> pd.DataFrame:
    """Situe chaque mois d'une station par rapport aux mêmes mois de son propre historique."""
    df = chroniques.dropna(subset=["niveau_nappe_ngf"]).copy()
    df["mois"] = pd.to_datetime(df.date).dt.to_period("M").dt.start_time
    mensuel = df.groupby(["code_bss", "mois"], as_index=False).niveau_nappe_ngf.mean()
    mensuel["mois_calendaire"] = mensuel.mois.dt.month
    groupes = mensuel.groupby(["code_bss", "mois_calendaire"]).niveau_nappe_ngf
    mensuel["percentile"] = groupes.rank(pct=True) * 100
    mensuel = mensuel[groupes.transform("count") >= min_annees]
    return mensuel.drop(columns="mois_calendaire")
