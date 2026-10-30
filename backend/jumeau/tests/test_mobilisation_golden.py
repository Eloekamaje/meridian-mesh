"""Jeu d'or de mobilisation : les décisions de résolution sont versionnées et rejouées sans base ni réseau."""
import json
from pathlib import Path

import pytest

from jumeau.identite import resoudre

FIXTURE = Path(__file__).with_name("fixtures") / "mobilisation_golden.json"
DONNEES = json.loads(FIXTURE.read_text(encoding="utf-8"))
CAS = DONNEES["cas"]


def registre(cas):
    jumeaux = cas["jumeaux"]
    if isinstance(jumeaux, str):
        if jumeaux not in DONNEES["registres"]:
            pytest.fail(f"cas {cas['nom']!r} : registre inconnu {jumeaux!r}")
        return DONNEES["registres"][jumeaux]
    assert isinstance(jumeaux, list), (
        f"cas {cas['nom']!r} : jumeaux doit être un nom de registre ou une liste")
    return jumeaux


def matched_on(resolution):
    return resolution.mentions[0]["matched_on"] if resolution.mentions else None


@pytest.mark.parametrize("cas", CAS, ids=[cas["nom"] for cas in CAS])
def test_cas_du_jeu_d_or(cas):
    attendu = cas["attendu"]
    contexte = f"cas {cas['nom']!r} — question {cas['question']!r}"
    r = resoudre(cas["question"], registre(cas))

    assert r.twin_id == attendu["twin_id"], (
        f"{contexte} : twin_id attendu {attendu['twin_id']!r}, obtenu {r.twin_id!r} "
        f"(statut {r.statut!r}, motif {r.motif!r})")
    if "application_id" in attendu:
        assert r.application_id == attendu["application_id"], (
            f"{contexte} : application_id attendu {attendu['application_id']!r}, "
            f"obtenu {r.application_id!r}")
    assert r.statut == attendu["statut"], (
        f"{contexte} : statut attendu {attendu['statut']!r}, obtenu {r.statut!r} "
        f"(motif {r.motif!r})")
    assert matched_on(r) == attendu["matched_on"], (
        f"{contexte} : matched_on attendu {attendu['matched_on']!r}, "
        f"obtenu {matched_on(r)!r} (mentions {r.mentions!r})")
    assert r.requires_confirmation is attendu["requires_confirmation"], (
        f"{contexte} : requires_confirmation attendu {attendu['requires_confirmation']!r}, "
        f"obtenu {r.requires_confirmation!r}")
    assert r.absent is attendu["absent"], (
        f"{contexte} : absent attendu {attendu['absent']!r}, obtenu {r.absent!r} "
        f"(motif {r.motif!r})")
    assert r.ambigu is attendu["ambigu"], (
        f"{contexte} : ambigu attendu {attendu['ambigu']!r}, obtenu {r.ambigu!r} "
        f"(motif {r.motif!r})")

    if attendu["statut"] in {"provisoire", "ambigu"}:
        assert r.preambule().strip(), (
            f"{contexte} : préambule attendu non vide, obtenu {r.preambule()!r}")
    elif attendu["statut"] == "canonique":
        assert r.preambule() == "", (
            f"{contexte} : préambule attendu vide pour une résolution canonique, obtenu {r.preambule()!r}")
    elif attendu["absent"]:
        assert r.mentions[0]["type"] == "inconnu", (
            f"{contexte} : une absence inconnue doit rester de type inconnu, mentions {r.mentions!r}")
        assert r.preambule() == "", (
            f"{contexte} : préambule attendu vide pour une absence inconnue, obtenu {r.preambule()!r}")


def test_le_jeu_est_versionne_stable_et_lisible():
    assert DONNEES["version"] == 1
    assert 15 <= len(CAS) <= 20
    noms = [cas["nom"] for cas in CAS]
    assert len(noms) == len(set(noms))
    for cas in CAS:
        assert {"nom", "question", "jumeaux", "attendu"} <= set(cas)
        assert {"twin_id", "statut", "matched_on", "requires_confirmation", "absent",
                "ambigu"} <= set(cas["attendu"])


def test_gsf_mockup_n_est_jamais_une_application():
    cas = next((c for c in CAS if "gsf-mockup" in c["question"]
                and c["attendu"]["statut"] == "provisoire"), None)
    assert cas is not None, "cas gsf-mockup absent du jeu d'or"
    r = resoudre(cas["question"], registre(cas))

    assert r.twin_id != "gsf-mockup", f"gsf-mockup ne doit jamais être un twin : {r.twin_id!r}"
    assert r.application_id != "gsf-mockup", (
        f"gsf-mockup ne doit jamais être une application : {r.application_id!r}")
    assert r.twin_id == "nouveau-jumeau"
    assert r.application_id == "nouveau-jumeau"
    assert r.statut == "provisoire"
    assert [e["type"] for e in r.chemin] == ["source", "twin", "application"]
    assert r.chemin[0]["id"] == "repo:gsf-mockup"
    assert r.chemin[-1]["id"] == "nouveau-jumeau"
