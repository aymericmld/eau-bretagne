import pandas as pd
import pytest

from eau_bretagne import transform as t

CORRECTIONS = pd.DataFrame(
    {"motif_nom": ["GOLF", "BARRAGE"], "secteur": ["Sports et loisirs", "Non identifié"]}
)


def brut(**kw):
    base = {
        "code_ouvrage": "A",
        "annee": 2022,
        "code_usage": "IND",
        "volume": 10.0,
        "libelle_mode_obtention_volume": "Volume mesuré",
        "code_commune_insee": "29019",
        "code_departement": "29",
        "nom_ouvrage": "X",
        "longitude": -4.5,
        "latitude": 48.4,
    }
    return base | kw


def test_barrages_exclus_et_doublons_retires():
    df = pd.DataFrame([brut(), brut(volume=30.0), brut(code_usage="BAR", volume=9e9)])
    ouvrages = pd.DataFrame({"code_ouvrage": ["A"], "libelle_type_milieu": ["Souterrain"]})
    resultat = t.nettoyer_prelevements(df, ouvrages)
    assert len(resultat) == 1
    assert resultat.volume.iloc[0] == 30.0
    assert resultat.milieu.iloc[0] == "Souterrain"


@pytest.mark.parametrize(
    ("naf", "attendu"),
    [
        ("10.51D", "Agroalimentaire"),
        ("15.2Z", "Agroalimentaire"),
        ("08.12Z", "Carrières et matériaux"),
        ("25.94Z", "Autre industrie"),
        ("93.12Z", "Sports et loisirs"),
        (None, None),
        (float("nan"), None),
    ],
)
def test_secteur_depuis_naf(naf, attendu):
    assert t.secteur_depuis_naf(naf) == attendu


def test_correction_prioritaire_sur_naf():
    assert t.classer_secteur("GOLF DE RENNES", "68.20B", CORRECTIONS)[0] == "Sports et loisirs"
    assert t.classer_secteur("INCONNU", None, CORRECTIONS) == ("Non identifié", "aucune")


def test_correction_sur_mots_entiers_uniquement():
    corrections = pd.DataFrame({"motif_nom": ["INITIAL"], "secteur": ["Blanchisserie"]})
    nom = "SCA D INITIATIVES ET DE COOPERATION AGRICOLES"
    assert t.classer_secteur(nom, "46.22Z", corrections)[0] == "Services et autres"
    assert t.classer_secteur("USINE DE INITIAL BTB", None, corrections)[0] == "Blanchisserie"


def test_niveau_du_jour_est_le_plus_severe():
    df = pd.DataFrame(
        {
            "code_commune": ["1", "1"],
            "date": ["2022-08-01", "2022-08-02"],
            "AEP": [None, None],
            "SOU": ["alerte", None],
            "SUP": ["crise", "vigilance"],
        }
    )
    assert t.jours_par_niveau(df).niveau.tolist() == [4, 1]


def test_jours_de_restriction_excluent_la_vigilance():
    jours = pd.DataFrame(
        {
            "code_commune": ["1"] * 3,
            "date": pd.to_datetime(["2022-08-01", "2022-08-02", "2022-08-03"]),
            "niveau": [1, 2, 4],
        }
    )
    ligne = t.agreger_restrictions(jours).iloc[0]
    assert ligne.jours_vigilance == 1
    assert ligne.jours_restriction == 2


def test_score_gravite_annualise_et_pondere():
    annuel = pd.DataFrame(
        {
            "code_commune": ["1"],
            "periode": pd.to_datetime(["2022-01-01"]),
            "jours_alerte": [10],
            "jours_alerte_renforcee": [5],
            "jours_crise": [2],
        }
    )
    assert t.score_gravite(annuel, range(2021, 2023)).loc["1"] == pytest.approx(13)


def test_indice_croissant_et_ponderations_controlees():
    composantes = pd.DataFrame(
        {"gravite": [1, 2, 3, 4], "pression": [1, 2, 3, 4], "surface": [1, 2, 3, 4]}
    )
    indice = t.indice_exposition(composantes)
    assert indice.is_monotonic_increasing
    assert indice.iloc[-1] == pytest.approx(100)
    with pytest.raises(ValueError):
        t.indice_exposition(composantes, {"gravite": 0.5, "pression": 0.1, "surface": 0.1})


def test_classes_de_meme_effectif():
    classes = t.classer_exposition(pd.Series(range(8), dtype=float))
    assert classes.value_counts().tolist() == [2, 2, 2, 2]


def test_seuil_de_diffusion():
    df = pd.DataFrame({"nb_ouvrages": [2, 3]})
    assert t.masquer_petits_effectifs(df).nb_ouvrages.tolist() == [3]


def test_percentile_nappe_compare_au_meme_mois():
    dates = pd.date_range("2010-08-15", periods=10, freq=pd.DateOffset(years=1))
    df = pd.DataFrame(
        {"code_bss": "B", "date": dates, "niveau_nappe_ngf": [float(i) for i in range(10)]}
    )
    resultat = t.percentile_nappe(df)
    assert resultat.percentile.iloc[0] == pytest.approx(10)
    assert resultat.percentile.iloc[-1] == pytest.approx(100)
