from eau_bretagne.matching import evaluer, mots_distinctifs, nom_utile, normaliser


def test_normalisation_retire_accents_et_formes_juridiques():
    assert normaliser("Société d'Écluse") == "SOCIETE D ECLUSE"
    assert nom_utile("USINE DE MARAIS ABATTAGE SAS") == "MARAIS ABATTAGE"


def test_mots_generiques_ne_sont_pas_distinctifs():
    assert mots_distinctifs("GOLF DU BOISGELIN") == {"BOISGELIN"}


def test_correspondance_forte_si_meme_nom_et_meme_commune():
    decision = evaluer("USINE DE ARMOR MECANIQUE FICTIVE SA", ["ARMOR MECANIQUE FICTIVE"], True)
    assert decision.confiance == "forte"


def test_faux_positif_sur_mot_generique_rejete():
    assert evaluer("GOLF DU BOISGELIN", ["GOLF PUB"], True).confiance == "aucune"


def test_meme_commune_sans_mot_commun_rejete():
    assert evaluer("KERFICTIF", ["ALAIN MARTIN"], True).confiance == "aucune"


def test_homonyme_dans_une_autre_commune_rejete():
    assert evaluer("USINE DE JEAN DUPONT", ["JEAN DUPONT"], False).confiance == "aucune"


def test_sigle_peut_justifier_le_rapprochement():
    noms = ["SOCIETE FICTIVE DE CONSERVES", "SOFIC"]
    assert evaluer("USINE DE SOFIC SAS", noms, True).confiance == "forte"
