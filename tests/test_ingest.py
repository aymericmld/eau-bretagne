import io
import json
import zipfile

from eau_bretagne.ingest import (
    decompresser_premier_membre,
    enregistrements_communes,
    lignes_restrictions,
)


def commune(code, jours):
    return {"commune": {"code": code, "nom": f"C{code}"}, "restrictions": jours}


def test_flux_zip_et_decoupage_par_commune():
    jours = [
        {"AEP": None, "SOU": None, "SUP": None, "date": "2022-08-01"},
        {"AEP": None, "SOU": "crise", "SUP": None, "date": "2022-08-02"},
    ]
    contenu = json.dumps(
        [commune("01001", jours), commune("22001", jours), commune("56001", jours)],
        separators=(",", ":"),
    ).encode()
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("h.json", contenu)
    octets = tampon.getvalue()
    blocs = [octets[i : i + 37] for i in range(0, len(octets), 37)]  # coupures arbitraires

    resultat = list(enregistrements_communes(decompresser_premier_membre(blocs)))

    assert [code for code, _ in resultat] == ["01001", "22001", "56001"]
    lignes = list(lignes_restrictions(resultat[1][1]))
    assert lignes == [["22001", "C22001", "2022-08-02", None, "crise", None]]
