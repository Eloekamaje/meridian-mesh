"""Contrat du registre capacitaire : validation, versions, portée, recherche et absence d'exécution."""
import ast
import json
from pathlib import Path
import re

import pytest

from jumeau import capacites
from jumeau.capacites import (
    AXES_PORTEE,
    CAPACITES,
    ConflitManifeste,
    ManifesteInvalide,
    ManifesteOutil,
    RegistreCapacites,
    manifestes_integres,
)

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


def manifeste(**changements):
    champs = {
        "nom": "lire_traces",
        "version": "1.0.0",
        "description": "Lit les traces d'observabilité d'une application",
        "capacite": "observer",
        "types_objets_lus": ("Trace",),
        "types_objets_ecrits": (),
        "schema_entree": SCHEMA_ENTREE,
        "schema_sortie": SCHEMA_SORTIE,
        "cout": 0.02,
        "timeout_ms": 2000,
        "mode_preuve": "OBSERVED",
        "source": "manifeste",
    }
    champs.update(changements)
    return ManifesteOutil(**champs)


def test_manifeste_valide_enregistre_et_liste():
    contrat = manifeste()
    registre = RegistreCapacites()
    assert registre.enregistrer(contrat) is contrat
    assert registre.lister() == [contrat]
    assert registre.decrire("lire_traces") is contrat
    assert "lire_traces" in registre
    assert len(registre) == 1
    assert set(CAPACITES) <= set(registre.capacites())


def test_capacite_inconnue_refusee():
    with pytest.raises(ManifesteInvalide):
        manifeste(capacite="capacite_inconnue")
    with pytest.raises(ManifesteInvalide):
        RegistreCapacites().lister(capacite="capacite_inconnue")


def test_doublon_meme_version_est_idempotent_et_contenu_different_refuse():
    registre = RegistreCapacites()
    premier = registre.enregistrer(manifeste())
    second = registre.enregistrer(manifeste())
    assert second is premier
    assert len(registre.lister()) == 1
    with pytest.raises(ConflitManifeste):
        registre.enregistrer(manifeste(description="Une autre description"))
    registre.enregistrer(manifeste(version="2.0.0"))
    assert registre.decrire("lire_traces").version == "2.0.0"
    with pytest.raises(ConflitManifeste):
        registre.enregistrer(manifeste(version="1.5.0"))


def test_filtres_capacite_lecture_seule_tenant_acteur_perimetre():
    banque = manifeste(nom="traces_banque", tenant="banque", acteur="flore", perimetre="paiements")
    assurance = manifeste(nom="traces_assurance", tenant="assurance")
    global_ = manifeste(nom="traces_globales")
    prouver = manifeste(nom="lire_claims_prouves", capacite="prouver",
                        description="Lit les claims et leurs preuves")
    ecriture = manifeste(
        nom="creer_travail",
        capacite="agir",
        description="Crée un Travail pour une initiative",
        types_objets_ecrits=("Travail",),
        lecture_seule=False,
        effets_de_bord=("crée un Travail",),
    )
    registre = RegistreCapacites([banque, assurance, global_, prouver, ecriture])

    assert {m.nom for m in registre.lister(capacite="observer")} == {
        "traces_banque", "traces_assurance", "traces_globales"}
    assert registre.lister(lecture_seule=False) == [ecriture]
    assert {m.nom for m in registre.lister(tenant="banque")} == {
        "traces_banque", "traces_globales", "lire_claims_prouves", "creer_travail"}
    assert {m.nom for m in registre.lister(tenant="assurance")} == {
        "traces_assurance", "traces_globales", "lire_claims_prouves", "creer_travail"}
    assert {m.nom for m in registre.lister(perimetre="paiements")} == {
        "traces_banque", "traces_assurance", "traces_globales", "lire_claims_prouves", "creer_travail"}
    assert {m.nom for m in registre.lister(tenant="banque", acteur="flore",
                                           perimetre="paiements", capacite="observer")} == {
        "traces_banque", "traces_globales"}


def test_recherche_lexicale_stable():
    beta = manifeste(nom="beta_traces", description="Observe les traces distribuées")
    alpha = manifeste(nom="alpha_traces", description="Observe les traces distribuées")
    claims = manifeste(nom="gamma_claims", capacite="lire_claims", description="Lit les claims prouvés")
    registre = RegistreCapacites([beta, alpha, claims])

    assert [m.nom for m in registre.chercher("traces")] == ["alpha_traces", "beta_traces"]
    assert [m.nom for m in registre.chercher("prouves")] == ["gamma_claims"]
    assert [m.nom for m in registre.chercher("observer traces")] == ["alpha_traces", "beta_traces"]
    assert registre.chercher("inexistant") == []
    assert [m.nom for m in registre.chercher("traces", capacite="observer")] == [
        "alpha_traces", "beta_traces"]


def test_ecriture_sans_effets_refusee():
    with pytest.raises(ManifesteInvalide):
        manifeste(lecture_seule=False)
    with pytest.raises(ManifesteInvalide):
        manifeste(lecture_seule=False, types_objets_ecrits=("Travail",))
    with pytest.raises(ManifesteInvalide):
        manifeste(lecture_seule=True, effets_de_bord=("écrit un Travail",))
    with pytest.raises(ManifesteInvalide):
        manifeste(lecture_seule=True, types_objets_ecrits=("Travail",))
    ecriture = manifeste(nom="creer_travail", capacite="agir", lecture_seule=False,
                         types_objets_ecrits=("Travail",), effets_de_bord=("crée un Travail",))
    assert ecriture.lecture_seule is False
    assert ecriture.effets_de_bord == ("crée un Travail",)


def test_secret_et_url_arbitraire_refuses():
    with pytest.raises(ManifesteInvalide):
        manifeste(description="api_key=abcdef1234567890")
    with pytest.raises(ManifesteInvalide):
        manifeste(description="password: hunter2secret")
    with pytest.raises(ManifesteInvalide):
        manifeste(description="<script>alert(1)</script>")
    with pytest.raises(ManifesteInvalide):
        manifeste(schema_entree={
            "type": "object",
            "properties": {"endpoint": {"type": "string", "default": "https://evil.example"}},
        })
    with pytest.raises(ManifesteInvalide):
        manifeste(allowlist=("https://annuaire.example/outils",))
    with pytest.raises(ManifesteInvalide):
        manifeste(schema_entree={"type": "object", "properties": {"password": "hunter2secret"}})


def test_as_dict_est_json_serialisable():
    registre = RegistreCapacites([manifeste(), *manifestes_integres()])
    charge = registre.as_dict()
    encode = json.dumps(charge, ensure_ascii=False, allow_nan=False)
    decode = json.loads(encode)
    assert decode["capacites"] == list(CAPACITES)
    assert len(decode["outils"]) == 5
    assert decode["outils"][0]["portee"] == {"tenant": None, "acteur": None, "perimetre": None}
    assert json.loads(json.dumps(manifeste().as_dict(), ensure_ascii=False))["nom"] == "lire_traces"


def test_manifestes_integres_sont_quatre_adaptateurs_lecture_seule():
    integres = manifestes_integres()
    assert len(integres) == 4
    assert [m.nom for m in integres] == [
        "lister_applications", "resoudre_application", "mobiliser_jumeaux", "concevoir_architecture"]
    assert {m.capacite for m in integres} == {"situer", "mobiliser_expert", "concevoir"}
    assert len({m.nom for m in integres}) == 4
    assert all(m.source == "builtin" for m in integres)
    assert all(m.lecture_seule for m in integres)
    assert all(set(m.portee) == set(AXES_PORTEE) for m in integres)
    for contrat in integres:
        if not contrat.lecture_seule:
            assert contrat.effets_de_bord
    registre = RegistreCapacites(integres)
    assert len(registre) == 4
    assert registre.lister(lecture_seule=False) == []


def test_module_sans_execution_dynamique_ni_reseau():
    source = Path(capacites.__file__).read_text(encoding="utf-8")
    interdits = (
        r"\beval\s*\(", r"\bexec\s*\(", r"__import__\s*\(", r"\bcompile\s*\(",
        r"\bimportlib\b", r"\bsocket\b", r"\burllib\b", r"\brequests\b",
        r"\bhttpx\b", r"\bsubprocess\b", r"\bos\.system\b", r"\bopen\s*\(",
    )
    for motif in interdits:
        assert re.search(motif, source) is None, motif
    arbre = ast.parse(source)
    autorises = {"__future__", "collections", "dataclasses", "json", "math", "re", "types", "typing",
                 "unicodedata"}
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            assert all(alias.name.split(".")[0] in autorises for alias in noeud.names)
        if isinstance(noeud, ast.ImportFrom):
            assert (noeud.module or "").split(".")[0] in autorises
