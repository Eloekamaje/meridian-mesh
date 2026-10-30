"""Chargeur de manifestes : fichier ou dossier, validation stricte, refus des doublons et zéro exécution."""
import ast
import json
from pathlib import Path
import re

import pytest

from jumeau import chargeur_manifestes
from jumeau.capacites import ManifesteOutil, RegistreCapacites
from jumeau.chargeur_manifestes import DoublonManifeste, ManifesteRefuse, charger, lister_fichiers

SCHEMA_ENTREE = {
    "type": "object",
    "properties": {"application": {"type": "string"}},
    "required": ["application"],
    "additionalProperties": False,
}
SCHEMA_SORTIE = {
    "type": "object",
    "properties": {"traces": {"type": "array", "items": {"type": "object"}}},
    "required": ["traces"],
    "additionalProperties": False,
}


def manifeste(nom="lire_traces", version="1.0.0", **changements):
    champs = {
        "nom": nom,
        "version": version,
        "description": "Lit les traces d'observabilité d'une application",
        "capacite": "observer",
        "types_objets_lus": ["Trace"],
        "schema_entree": SCHEMA_ENTREE,
        "schema_sortie": SCHEMA_SORTIE,
        "timeout_ms": 2000,
        "mode_preuve": "OBSERVED",
        "source": "manifeste",
    }
    champs.update(changements)
    return champs


def ecrire(fichier, contenu):
    fichier.write_text(json.dumps(contenu, ensure_ascii=False), encoding="utf-8")
    return fichier


def test_lister_fichiers_trie_et_ignore_les_non_json(tmp_path):
    ecrire(tmp_path / "b.json", manifeste(nom="outil_b"))
    ecrire(tmp_path / "a.json", manifeste(nom="outil_a"))
    (tmp_path / "note.txt").write_text("pas un manifeste", encoding="utf-8")
    (tmp_path / "sous-dossier").mkdir()
    ecrire(tmp_path / "sous-dossier" / "c.json", manifeste(nom="outil_c"))

    assert [fichier.name for fichier in lister_fichiers(tmp_path)] == ["a.json", "b.json"]
    assert lister_fichiers(tmp_path / "a.json") == [tmp_path / "a.json"]


def test_charger_un_fichier_unique(tmp_path):
    fichier = ecrire(tmp_path / "outil.json", manifeste())
    registre = RegistreCapacites()

    contrats = charger(registre, fichier)

    assert [contrat.nom for contrat in contrats] == ["lire_traces"]
    assert registre.decrire("lire_traces") == contrats[0]
    assert len(registre) == 1


def test_charger_un_dossier_et_un_tableau_de_manifestes(tmp_path):
    ecrire(tmp_path / "a.json", manifeste(nom="outil_a"))
    ecrire(tmp_path / "b.json", [manifeste(nom="outil_b"), manifeste(nom="outil_c")])
    registre = RegistreCapacites()

    contrats = charger(registre, tmp_path)

    assert [contrat.nom for contrat in contrats] == ["outil_a", "outil_b", "outil_c"]
    assert {outil.nom for outil in registre} == {"outil_a", "outil_b", "outil_c"}


def test_refuse_une_cle_inconnue_sans_rien_inscrire(tmp_path):
    ecrire(tmp_path / "a.json", manifeste(nom="outil_a"))
    ecrire(tmp_path / "b.json", {**manifeste(nom="outil_b"), "executeur": "python -c ..."})
    registre = RegistreCapacites()

    with pytest.raises(ManifesteRefuse, match="inconnue"):
        charger(registre, tmp_path)
    assert len(registre) == 0


@pytest.mark.parametrize("description", [
    "Utilise token=abcdef123456 pour lire les traces",
    "Voir https://example.com/traces pour le contrat",
])
def test_refuse_les_secrets_et_les_url(tmp_path, description):
    fichier = ecrire(tmp_path / "outil.json", manifeste(description=description))
    registre = RegistreCapacites()

    with pytest.raises(ManifesteRefuse):
        charger(registre, fichier)
    assert len(registre) == 0


def test_refuse_un_manifeste_invalide(tmp_path):
    fichier = ecrire(tmp_path / "outil.json", manifeste(capacite="capacite_inconnue"))
    with pytest.raises(ManifesteRefuse):
        charger(RegistreCapacites(), fichier)

    fichier = ecrire(tmp_path / "liste.json", ["pas un objet"])
    with pytest.raises(ManifesteRefuse):
        charger(RegistreCapacites(), fichier)


def test_refuse_deux_fois_le_meme_nom_et_la_meme_version(tmp_path):
    ecrire(tmp_path / "a.json", manifeste(nom="outil_a"))
    ecrire(tmp_path / "b.json", manifeste(nom="outil_a"))
    registre = RegistreCapacites()

    with pytest.raises(DoublonManifeste):
        charger(registre, tmp_path)
    assert len(registre) == 0

    registre.enregistrer(ManifesteOutil(**manifeste(nom="outil_a")))
    fichier = ecrire(tmp_path / "c.json", manifeste(nom="outil_a"))
    with pytest.raises(DoublonManifeste):
        charger(registre, fichier)


def test_refuse_une_cle_json_dupliquee(tmp_path):
    fichier = tmp_path / "outil.json"
    contenu = json.dumps(manifeste(), ensure_ascii=False)
    fichier.write_text(contenu[:-1] + ', "nom": "autre"}', encoding="utf-8")

    with pytest.raises(ManifesteRefuse, match="dupliquée"):
        charger(RegistreCapacites(), fichier)


def test_le_chargeur_est_sans_execution_dynamique_ni_reseau():
    source = Path(chargeur_manifestes.__file__).read_text(encoding="utf-8")
    interdits = (
        r"\beval\s*\(", r"\bexec\s*\(", r"__import__\s*\(", r"\bcompile\s*\(",
        r"\bimportlib\b", r"\bsocket\b", r"\burllib\b", r"\brequests\b",
        r"\bhttpx\b", r"\bsubprocess\b", r"\bos\.system\b", r"\bopen\s*\(",
    )
    for motif in interdits:
        assert re.search(motif, source) is None, motif
    arbre = ast.parse(source)
    autorises = {"__future__", "collections", "json", "pathlib", "typing", "jumeau"}
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            assert all(alias.name.split(".")[0] in autorises for alias in noeud.names)
        if isinstance(noeud, ast.ImportFrom):
            assert (noeud.module or "").split(".")[0] in autorises
