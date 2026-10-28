"""Jeu de verdicts de référence : la seule mesure de justesse du juge est son accord avec l'humain."""
import asyncio
import json

import pytest

from jumeau import evaluation
from jumeau.juge import Appui


def cas(id, attendu="oui", valide_par=None):
    return {"id": id, "jumeau": "conduit", "enonce": "e", "attendu": attendu, "pourquoi": "p", "propose_par": "claude",
            "valide_par": valide_par, "valide_le": "2026-10-28" if valide_par else None,
            "extraits": [{"systeme": "git", "citation": "a.py#L1-L1", "lignes": ["x = 1"]}]}


def ecrire(tmp_path, contenu):
    f = tmp_path / "v.json"
    f.write_text(json.dumps(contenu), encoding="utf-8")
    return f


def appui(id, v):
    return Appui(id=id, appui=v, concordance="une_seule_source", copie=False, raison="r")


def test_le_fichier_livre_est_valide_et_non_valide_par_humain():
    tous = evaluation.charger_verdicts()
    assert {c["attendu"] for c in tous} == {"oui", "partiel", "non"}
    assert len(tous) >= 6 and all(c["valide_par"] is None for c in tous)


def test_un_cas_mal_forme_est_refuse_avec_son_id(tmp_path):
    mauvais = {**cas("c-bad"), "attendu": "peut-etre"}
    with pytest.raises(ValueError, match="c-bad"):
        evaluation.charger_verdicts(ecrire(tmp_path, [cas("ok"), mauvais]))


def test_un_cas_sans_extrait_est_refuse(tmp_path):
    with pytest.raises(ValueError, match="c-vide"):
        evaluation.charger_verdicts(ecrire(tmp_path, [{**cas("c-vide"), "extraits": []}]))


def test_l_accord_ne_compte_que_les_valides(tmp_path):
    f = ecrire(tmp_path, [cas("a", "oui", "humain"), cas("b", "non", "humain"), cas("c", "oui")])
    juge_appels = []

    async def juge(modele, connaissances):
        juge_appels.append([c["id"] for c in connaissances])
        return {0: appui(0, "oui"), 1: appui(1, "partiel")}

    r = asyncio.run(evaluation.mesurer_verdicts(juge, None, chemin=f))
    assert juge_appels == [[0, 1]] and r["comptes"] == 2
    assert r["accord_exact"] == 0.5 and r["accord_oui"] == 1.0 and r["non_valides"] == 1


def test_avec_tous_les_non_valides_sont_signales(tmp_path):
    f = ecrire(tmp_path, [cas("a", "oui", "humain"), cas("c", "oui")])

    async def juge(modele, connaissances):
        return {i: appui(i, "oui") for i in range(len(connaissances))}

    r = asyncio.run(evaluation.mesurer_verdicts(juge, None, tous=True, chemin=f))
    assert r["comptes"] == 2 and "non validé" in evaluation.rapport_verdicts(r)


def test_sans_cas_valide_aucun_chiffre(tmp_path):
    async def juge(modele, connaissances):
        raise AssertionError("ne doit pas juger")

    r = asyncio.run(evaluation.mesurer_verdicts(juge, None, chemin=ecrire(tmp_path, [cas("c")])))
    assert r["accord_exact"] is None
    assert "aucun cas validé" in evaluation.rapport_verdicts(r)


def test_un_cas_non_juge_compte_comme_desaccord(tmp_path):
    async def juge(modele, connaissances):
        return {}

    r = asyncio.run(evaluation.mesurer_verdicts(juge, None, chemin=ecrire(tmp_path, [cas("a", "oui", "h")])))
    assert r["accord_exact"] == 0.0
