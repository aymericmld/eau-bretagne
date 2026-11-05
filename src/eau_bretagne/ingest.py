"""Collecte des sources ouvertes. Chaque fonction écrit dans data/raw et peut être relancée."""

from __future__ import annotations

import csv
import json
import struct
import time
import zlib
from collections.abc import Iterable, Iterator
from pathlib import Path

import requests

from .config import DEPARTEMENTS, HUBEAU, RAW, VIGIEAU_DATASET

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "eau-bretagne-portfolio"
MARQUEUR = b'{"commune":{"code":"'


def get_json(url: str, params: dict | None = None, essais: int = 5, timeout: int = 90) -> dict:
    """GET JSON avec reprise progressive : les API publiques expirent parfois."""
    for essai in range(essais):
        try:
            reponse = SESSION.get(url, params=params, timeout=timeout)
            reponse.raise_for_status()
            return reponse.json()
        except (requests.RequestException, ValueError):
            if essai == essais - 1:
                raise
            time.sleep(3 * (essai + 1))
    raise RuntimeError("inatteignable")


def paginer_hubeau(url: str, params: dict) -> Iterator[dict]:
    """Parcourt toutes les pages d'un endpoint Hub'Eau via le lien `next`."""
    page = get_json(url, params)
    yield from page["data"]
    while page.get("next"):
        page = get_json(page["next"])
        yield from page["data"]


def collecter_prelevements(sortie: Path = RAW / "hubeau") -> None:
    """Volumes annuels par ouvrage et description des ouvrages."""
    sortie.mkdir(parents=True, exist_ok=True)
    endpoints = {"chroniques": "chroniques", "ouvrages": "referentiel/ouvrages"}
    for nom, chemin in endpoints.items():
        lignes: list[dict] = []
        for dep in DEPARTEMENTS:
            params = {"code_departement": dep, "size": 5000, "format": "json"}
            lignes.extend(paginer_hubeau(f"{HUBEAU}/prelevements/{chemin}", params))
        (sortie / f"{nom}.json").write_text(json.dumps(lignes, ensure_ascii=False))
        print(f"prelevements/{nom}: {len(lignes)} lignes", flush=True)


def collecter_piezometrie(sortie: Path = RAW / "hubeau", debut: str = "2008-01-01") -> None:
    """Niveaux quotidiens des nappes pour les stations des quatre départements."""
    sortie.mkdir(parents=True, exist_ok=True)
    stations: list[dict] = []
    for dep in DEPARTEMENTS:
        params = {"code_departement": dep, "size": 500, "format": "json"}
        stations.extend(get_json(f"{HUBEAU}/niveaux_nappes/stations", params)["data"])
    (sortie / "piezo_stations.json").write_text(json.dumps(stations, ensure_ascii=False))
    with (sortie / "piezo_chroniques.csv").open("w", newline="") as f:
        ecrivain = csv.writer(f)
        ecrivain.writerow(["code_bss", "date", "niveau_nappe_ngf"])
        for station in stations:
            params = {
                "code_bss": station["code_bss"],
                "date_debut_mesure": debut,
                "size": 20000,
                "sort": "asc",
                "fields": "code_bss,date_mesure,niveau_nappe_eau",
            }
            donnees = get_json(f"{HUBEAU}/niveaux_nappes/chroniques", params)["data"]
            for m in donnees:
                ecrivain.writerow([m["code_bss"], m["date_mesure"], m["niveau_nappe_eau"]])
    print(f"piezometrie: {len(stations)} stations", flush=True)


def decompresser_premier_membre(blocs: Iterable[bytes]) -> Iterator[bytes]:
    """Décompresse à la volée le premier fichier d'un flux ZIP, sans rien écrire sur disque."""
    tampon = b""
    blocs = iter(blocs)
    while len(tampon) < 30:
        tampon += next(blocs)
    signature, *_ = struct.unpack("<I", tampon[:4])
    if signature != 0x04034B50:
        raise ValueError("flux ZIP invalide")
    longueur_nom, longueur_extra = struct.unpack("<HH", tampon[26:30])
    debut = 30 + longueur_nom + longueur_extra
    while len(tampon) < debut:
        tampon += next(blocs)
    inflation = zlib.decompressobj(-zlib.MAX_WBITS)
    yield inflation.decompress(tampon[debut:])
    for bloc in blocs:
        yield inflation.decompress(bloc)
        if inflation.eof:
            return


def enregistrements_communes(flux: Iterable[bytes]) -> Iterator[tuple[str, bytes]]:
    """Découpe le JSON national commune par commune, sans le charger en mémoire."""
    tampon = b""
    for bloc in flux:
        tampon += bloc
        debut = tampon.find(MARQUEUR)
        while debut != -1:
            suivant = tampon.find(MARQUEUR, debut + len(MARQUEUR))
            if suivant == -1:
                break
            brut = tampon[debut:suivant].rstrip(b", \n\r")
            yield brut[len(MARQUEUR) : len(MARQUEUR) + 5].decode(), brut
            debut = suivant
        tampon = tampon[debut:] if debut != -1 else b""
    if tampon:
        brut = tampon.rstrip(b"] \n\r").rstrip(b", \n\r")
        yield brut[len(MARQUEUR) : len(MARQUEUR) + 5].decode(), brut


def lignes_restrictions(brut: bytes) -> Iterator[list[str | None]]:
    """Ne garde que les jours avec au moins une restriction pour une commune."""
    commune = json.loads(brut)
    for jour in commune["restrictions"]:
        if jour.get("AEP") or jour.get("SOU") or jour.get("SUP"):
            yield [
                commune["commune"]["code"],
                commune["commune"]["nom"],
                jour["date"],
                jour.get("AEP"),
                jour.get("SOU"),
                jour.get("SUP"),
            ]


def collecter_restrictions_communes(sortie: Path = RAW / "vigieau") -> None:
    """Extrait les communes bretonnes de l'historique national lu en flux."""
    sortie.mkdir(parents=True, exist_ok=True)
    ressources = get_json(VIGIEAU_DATASET)["resources"]
    url = next(r["url"] for r in ressources if r["title"] == "Historique Communes")
    communes = jours = 0
    fin = max(DEPARTEMENTS)
    with SESSION.get(url, stream=True, timeout=120) as reponse:
        reponse.raise_for_status()
        flux = decompresser_premier_membre(reponse.iter_content(1 << 20))
        with (sortie / "restrictions_communes_bretagne.csv").open("w", newline="") as f:
            ecrivain = csv.writer(f)
            ecrivain.writerow(["code_commune", "nom_commune", "date", "AEP", "SOU", "SUP"])
            for code, brut in enregistrements_communes(flux):
                if code[:2] > fin and code[:2].isdigit():
                    break  # le fichier est trié par code INSEE : inutile de lire la suite
                if code[:2] in DEPARTEMENTS:
                    communes += 1
                    for ligne in lignes_restrictions(brut):
                        ecrivain.writerow(ligne)
                        jours += 1
                    if communes % 200 == 0:
                        print(f"{communes} communes, {jours} jours", flush=True)
    print(f"restrictions: {communes} communes, {jours} commune-jours", flush=True)


def collecter_communes(sortie: Path = RAW / "geo") -> None:
    """Référentiel des communes et des EPCI (geo.api.gouv.fr)."""
    sortie.mkdir(parents=True, exist_ok=True)
    champs = "nom,code,codeDepartement,codeEpci,population,surface,centre"
    communes: list[dict] = []
    for dep in DEPARTEMENTS:
        url = f"https://geo.api.gouv.fr/departements/{dep}/communes"
        reponse = SESSION.get(url, params={"fields": champs}, timeout=60)
        reponse.raise_for_status()
        communes.extend(reponse.json())
    (sortie / "communes.json").write_text(json.dumps(communes, ensure_ascii=False))
    epci = SESSION.get("https://geo.api.gouv.fr/epcis", params={"fields": "nom,code"}, timeout=60)
    epci.raise_for_status()
    (sortie / "epci.json").write_text(json.dumps(epci.json(), ensure_ascii=False))
    print(f"referentiel: {len(communes)} communes", flush=True)


def collecter_arretes(sortie: Path = RAW / "vigieau") -> None:
    """Fichiers globaux des arrêtés et des restrictions par usage."""
    sortie.mkdir(parents=True, exist_ok=True)
    fichiers = {"Arrêtés": "arretes.csv", "Restrictions": "restrictions.csv"}
    for ressource in get_json(VIGIEAU_DATASET)["resources"]:
        if ressource["title"] in fichiers:
            reponse = SESSION.get(ressource["url"], timeout=200)
            reponse.raise_for_status()
            (sortie / fichiers[ressource["title"]]).write_bytes(reponse.content)
