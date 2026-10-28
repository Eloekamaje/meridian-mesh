"""Plafond d'extraction : au-delà, l'ingestion dégrade (sous-ensemble stable, signalé) au lieu d'échouer."""
import logging

import pytest

from jumeau import cbm, depot, examen
from jumeau.tests.conftest import ACTIVITE, JUMEAU, SOURCE, besoin_pg, claim


def faux_cli(routes, **autres):
    familles = {"routes": routes, **autres}
    colonnes = {"routes": ["chemin", "debut", "fin", "methode", "route"], "paquets": ["chemin", "paquet"],
                "variables": ["chemin", "variable", "ligne"], "images": ["chemin", "image"]}

    def cli(*args):
        requete = args[args.index("--query") + 1]
        famille = next(f for f, q in cbm.REQUETES.items() if requete.startswith(q))
        return {"columns": colonnes[famille], "rows": familles.get(famille, [])}
    return cli


def routes(n):
    return [[f"src/f{i % 977:04d}.py", i, i + 2, "GET", f"/r{i}"] for i in range(n)]


def test_vingt_mille_routes_s_ingerent_tronquees_et_signalees(monkeypatch, caplog):
    monkeypatch.setattr(cbm, "_cli", faux_cli(routes(20000)))
    with caplog.at_level(logging.WARNING):
        resultats, troncature = cbm.interroger("p")
    assert len(resultats["routes"]) == cbm.plafond() == 10000
    assert troncature == {"routes": {"gardes": 10000, "trouves": 20000}}
    assert "routes" in caplog.text and "20000" in caplog.text


def test_sous_ensemble_deterministe_quel_que_soit_l_ordre_de_reponse(monkeypatch):
    monkeypatch.setenv("JUMEAU_PLAFOND", "100")
    lignes = routes(500)
    monkeypatch.setattr(cbm, "_cli", faux_cli(lignes))
    a, _ = cbm.interroger("p")
    monkeypatch.setattr(cbm, "_cli", faux_cli(lignes[::-1]))
    b, _ = cbm.interroger("p")
    assert a == b and len(a["routes"]) == 100
    chemins = [(r["chemin"], r["debut"]) for r in a["routes"]]
    assert chemins == sorted(chemins)  # par fichier puis ligne


def test_sous_le_plafond_rien_n_est_signale(monkeypatch):
    monkeypatch.setattr(cbm, "_cli", faux_cli(routes(10)))
    resultats, troncature = cbm.interroger("p")
    assert len(resultats["routes"]) == 10 and troncature == {}


def test_plafond_par_famille_et_borne(monkeypatch):
    monkeypatch.setenv("JUMEAU_PLAFOND", "100")
    monkeypatch.setattr(cbm, "_cli", faux_cli(routes(10), paquets=[[f"a{i}.py", f"p{i}"] for i in range(150)]))
    _, troncature = cbm.interroger("p")
    assert troncature == {"paquets": {"gardes": 100, "trouves": 150}}
    for brut, attendu in (("1", cbm.PLAFOND_MIN), ("999999999", cbm.PLAFOND_MAX), ("abc", 10000)):
        monkeypatch.setenv("JUMEAU_PLAFOND", brut)
        assert cbm.plafond() == attendu


def test_reponse_coupee_par_le_binaire_est_signalee(monkeypatch):
    def cli(*args):
        return {**faux_cli(routes(30))(*args), "has_more": True}
    monkeypatch.setattr(cbm, "_cli", cli)
    _, troncature = cbm.interroger("p")
    assert troncature["routes"] == {"gardes": 30, "trouves": 30, "au_moins": True}


def test_examen_dit_lu_en_partie():
    t = {"routes": {"gardes": 10000, "trouves": 20000}}
    e = examen.depuis_connaissances({"nom": "X"}, [], None, troncature=t)
    assert {"nom": "Code", "etat": "lu en partie", "ok": False} in e["presentation"]["sources"]
    assert "Code : lu en partie — 10000 routes sur 20000 (plafond)" in e["presentation"]["ignore"]


@besoin_pg
def test_troncature_persistee_et_connaissance_validee_survit(conn):
    depot.appliquer_schema(conn)
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("fastapi"), claim("motor", ligne=4)], ACTIVITE)
    fastapi = conn.execute("SELECT id FROM claim WHERE objet = 'fastapi'").fetchone()[0]
    depot.reviser(conn, fastapi, "alice", "ACCEPTED", "vu")  # une acceptation passe toujours par une revue
    t = {"routes": {"gardes": 1, "trouves": 2}}
    depot.enregistrer(conn, JUMEAU, {**SOURCE, "troncature": t}, [claim("uvicorn", ligne=5)], ACTIVITE)
    restes = {o: v for o, v in conn.execute("SELECT objet, valide_jusqua IS NULL FROM claim")}
    assert restes == {"fastapi": True, "motor": False, "uvicorn": True}  # validée gardée, proposée au-delà close
    assert depot.troncature(conn, JUMEAU["id"]) == t
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("uvicorn", ligne=5)], ACTIVITE)
    assert depot.troncature(conn, JUMEAU["id"]) == {}
