"""Harness capacitaire : manifeste obligatoire, portée, approbation, timeout, audit et découverte."""
import ast
import asyncio
import json
from pathlib import Path
import re

import pytest

from jumeau import capacites, harness
from jumeau.capacites import ManifesteOutil, RegistreCapacites
from jumeau.harness import Harness, OutilNonApprouve, OutilNonEnregistre

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
        "schema_entree": SCHEMA_ENTREE,
        "schema_sortie": SCHEMA_SORTIE,
        "timeout_ms": 2000,
        "mode_preuve": "OBSERVED",
        "source": "manifeste",
    }
    champs.update(changements)
    return ManifesteOutil(**champs)


def ecriture(**changements):
    champs = {
        "nom": "creer_travail",
        "version": "1.0.0",
        "description": "Crée un Travail pour une initiative",
        "capacite": "agir",
        "types_objets_ecrits": ("Travail",),
        "schema_entree": SCHEMA_ENTREE,
        "schema_sortie": SCHEMA_SORTIE,
        "lecture_seule": False,
        "effets_de_bord": ("crée un Travail",),
        "timeout_ms": 2000,
        "source": "manifeste",
    }
    champs.update(changements)
    return ManifesteOutil(**champs)


def noms(outils):
    return {outil.tool_name for outil in outils}


def test_un_outil_hors_manifeste_est_refuse_et_jamais_expose():
    appele = []
    harnais = Harness(
        RegistreCapacites([manifeste()]),
        {"intrus": lambda application: appele.append(application) or "secret"},
    )

    assert "intrus" not in noms(harnais.outils())
    with pytest.raises(OutilNonEnregistre):
        asyncio.run(harnais.appeler("intrus", {"application": "alpha"}))
    assert appele == []
    assert harnais.auditer()[-1]["statut"] == "refuse"
    assert harnais.auditer()[-1]["nom"] == "intrus"


def test_un_outil_read_only_est_expose_et_une_ecriture_exige_une_approbation():
    registre = RegistreCapacites([manifeste(), ecriture()])
    adaptateurs = {
        "lire_traces": lambda application: {"traces": [application]},
        "creer_travail": lambda application: {"cree": application},
    }

    sans = Harness(registre, adaptateurs)
    assert noms(sans.outils()) == {"lire_traces", "rechercher_outil", "decrire_outil"}
    with pytest.raises(OutilNonApprouve):
        asyncio.run(sans.appeler("creer_travail", {"application": "alpha"}))

    approuve = Harness(registre, adaptateurs, approuves={"creer_travail"})
    assert noms(approuve.outils()) == {
        "lire_traces", "creer_travail", "rechercher_outil", "decrire_outil"}
    assert asyncio.run(approuve.appeler("creer_travail", {"application": "alpha"})) == {
        "cree": "alpha"}


def test_les_filtres_de_portee_sont_appliques_aux_outils_exposes():
    banque = manifeste(nom="traces_banque", tenant="banque", persona="flore", perimetre="paiements")
    assurance = manifeste(nom="traces_assurance", tenant="assurance")
    registre = RegistreCapacites([banque, assurance])
    adaptateurs = {nom: lambda application: {"traces": []} for nom in ("traces_banque", "traces_assurance")}

    harnais = Harness(registre, adaptateurs, tenant="banque", persona="flore", perimetre="paiements")
    assert noms(harnais.outils()) == {"traces_banque", "rechercher_outil", "decrire_outil"}

    autre = Harness(registre, adaptateurs, tenant="assurance")
    assert noms(autre.outils()) == {"traces_assurance", "rechercher_outil", "decrire_outil"}


def test_appeler_mesure_la_duree_et_audite_le_statut():
    harnais = Harness(
        RegistreCapacites([manifeste()]),
        {"lire_traces": lambda application: {"traces": [application]}},
    )

    resultat = asyncio.run(harnais.appeler("lire_traces", {"application": "alpha"}))

    assert resultat == {"traces": ["alpha"]}
    ligne = harnais.auditer()[-1]
    assert ligne["nom"] == "lire_traces"
    assert ligne["capacite"] == "observer"
    assert ligne["statut"] == "ok"
    assert ligne["arguments"] == {"application": "alpha"}
    assert isinstance(ligne["duree_ms"], float) and ligne["duree_ms"] >= 0


def test_timeout_sur_un_callable_asynchrone_est_audite():
    async def lent(application):
        await asyncio.sleep(0.2)
        return {"traces": [application]}

    harnais = Harness(
        RegistreCapacites([manifeste(timeout_ms=5000)]),
        {"lire_traces": lent},
    )

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(harnais.appeler("lire_traces", {"application": "alpha"}, timeout_ms=10))

    ligne = harnais.auditer()[-1]
    assert ligne["statut"] == "timeout"
    assert ligne["erreur"] == "TimeoutError"
    assert ligne["duree_ms"] >= 0


def test_les_arguments_de_l_audit_sont_expurges():
    harnais = Harness(
        RegistreCapacites([manifeste()]),
        {"lire_traces": lambda application, **extra: {"traces": [application]}},
    )

    asyncio.run(harnais.appeler(
        "lire_traces",
        {"application": "alpha", "api_key": "sk-secret-123456", "token": "abcdef123456"},
    ))

    encode = json.dumps(harnais.as_dict(), ensure_ascii=False)
    assert "sk-secret-123456" not in encode
    assert "abcdef123456" not in encode
    assert harnais.auditer()[-1]["arguments"]["api_key"] == "***"
    assert harnais.auditer()[-1]["arguments"]["token"] == "***"


def test_les_outils_de_decouverte_interrogent_le_registre_sans_executer():
    appels = []
    harnais = Harness(
        RegistreCapacites([manifeste()]),
        {"lire_traces": lambda application: appels.append(application) or {"traces": []}},
    )
    catalogue = {outil.tool_name: outil for outil in harnais.outils()}

    recherche = json.loads(catalogue["rechercher_outil"]("traces"))
    assert recherche["statut"] == "ok"
    assert [outil["nom"] for outil in recherche["outils"]] == ["lire_traces"]
    assert "observer" in recherche["capacites"]

    description = json.loads(catalogue["decrire_outil"]("lire_traces"))
    assert description["statut"] == "ok"
    assert description["nom"] == "lire_traces"
    assert description["capacite"] == "observer"
    assert description["schema_entree"] == SCHEMA_ENTREE
    assert description["schema_sortie"] == SCHEMA_SORTIE
    assert description["portee"] == {"tenant": None, "persona": None, "perimetre": None}
    assert appels == []

    introuvable = json.loads(catalogue["decrire_outil"]("inexistant"))
    assert introuvable["statut"] == "introuvable"


def test_la_decouverte_ne_divulgue_pas_une_ecriture_non_approuvee():
    harnais = Harness(
        RegistreCapacites([manifeste(), ecriture()]),
        {"lire_traces": lambda application: None, "creer_travail": lambda application: None},
    )
    catalogue = {outil.tool_name: outil for outil in harnais.outils()}

    recherche = json.loads(catalogue["rechercher_outil"]("travail"))
    assert recherche["outils"] == []
    assert json.loads(catalogue["decrire_outil"]("creer_travail"))["statut"] == "indisponible"


def test_les_adaptateurs_strands_appellent_le_harness():
    harnais = Harness(
        RegistreCapacites([manifeste()]),
        {"lire_traces": lambda application: {"traces": [application]}},
    )
    outil = {candidat.tool_name: candidat for candidat in harnais.outils()}["lire_traces"]

    assert outil.tool_spec["name"] == "lire_traces"
    assert outil(application="alpha") == {"traces": ["alpha"]}
    assert harnais.auditer()[-1]["statut"] == "ok"


def test_as_dict_est_serialisable_et_ne_fuit_pas():
    harnais = Harness(
        RegistreCapacites([manifeste()]),
        {"lire_traces": lambda application, secret=None: {"traces": [application]}},
    )
    asyncio.run(harnais.appeler("lire_traces", {"application": "alpha", "secret": "hunter2"}))

    charge = harnais.as_dict()
    encode = json.dumps(charge, ensure_ascii=False, allow_nan=False)
    assert "hunter2" not in encode
    assert charge["audit"][-1]["statut"] == "ok"


def test_le_harness_est_sans_execution_dynamique_ni_reseau():
    source = Path(harness.__file__).read_text(encoding="utf-8")
    interdits = (
        r"\beval\s*\(", r"\bexec\s*\(", r"__import__\s*\(", r"\bcompile\s*\(",
        r"\bimportlib\b", r"\bsocket\b", r"\burllib\b", r"\brequests\b",
        r"\bhttpx\b", r"\bsubprocess\b", r"\bos\.system\b", r"\bopen\s*\(",
    )
    for motif in interdits:
        assert re.search(motif, source) is None, motif
    arbre = ast.parse(source)
    autorises = {"__future__", "asyncio", "collections", "copy", "inspect", "json", "re", "time",
                 "typing", "strands", "jumeau"}
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            assert all(alias.name.split(".")[0] in autorises for alias in noeud.names)
        if isinstance(noeud, ast.ImportFrom):
            assert (noeud.module or "").split(".")[0] in autorises


def test_le_catalogue_integre_reste_trois_adaptateurs_plus_la_decouverte():
    registre = RegistreCapacites(capacites.manifestes_integres())
    harnais = Harness(registre, {
        "resoudre_application": lambda terme: None,
        "mobiliser_jumeaux": lambda jumeaux, question: None,
        "concevoir_architecture": lambda question: None,
    })

    assert noms(harnais.outils()) == {
        "resoudre_application", "mobiliser_jumeaux", "concevoir_architecture",
        "rechercher_outil", "decrire_outil"}
    assert "rechercher_outil" in registre and "decrire_outil" in registre


def test_la_decouverte_suit_la_portee_demandee_au_tour():
    banque = manifeste(nom="traces_banque", tenant="banque")
    assurance = manifeste(nom="traces_assurance", tenant="assurance")
    registre = RegistreCapacites([banque, assurance])
    adaptateurs = {nom: lambda application: {"traces": []} for nom in ("traces_banque", "traces_assurance")}
    harnais = Harness(registre, adaptateurs)

    catalogue = {outil.tool_name: outil for outil in harnais.outils(tenant="banque")}
    recherche = json.loads(catalogue["rechercher_outil"]("traces"))

    assert [outil["nom"] for outil in recherche["outils"]] == ["traces_banque"]
    assert json.loads(catalogue["decrire_outil"]("traces_assurance"))["statut"] == "indisponible"


class SinkMemoire:
    def __init__(self):
        self.lignes = []

    def enregistrer(self, ligne):
        self.lignes.append(dict(ligne))
        return {"statut": "ok"}


class SinkCasse:
    def enregistrer(self, ligne):
        raise RuntimeError("base indisponible")


def test_un_audit_sink_recoit_chaque_appel_sans_remplacer_l_audit_memoire():
    sink = SinkMemoire()
    harnais = Harness(
        RegistreCapacites([manifeste()]),
        {"lire_traces": lambda application, **extra: {"traces": [application]}},
        audit_sink=sink,
    )

    assert asyncio.run(harnais.appeler(
        "lire_traces", {"application": "alpha", "token": "abcdef123456"})) == {
        "traces": ["alpha"]}
    assert asyncio.run(harnais.appeler(
        "lire_traces", {"application": "beta"})) == {"traces": ["beta"]}

    assert len(sink.lignes) == 2
    assert [ligne["outil"] for ligne in sink.lignes] == ["lire_traces", "lire_traces"]
    assert all(ligne["statut"] == "ok" for ligne in sink.lignes)
    assert sink.lignes[0]["arguments"]["token"] == "***"
    assert "abcdef123456" not in json.dumps(sink.lignes, ensure_ascii=False)
    assert [ligne["statut"] for ligne in harnais.auditer()] == ["ok", "ok"]


def test_un_echec_du_sink_d_audit_ne_casse_pas_l_appel_d_outil():
    harnais = Harness(
        RegistreCapacites([manifeste()]),
        {"lire_traces": lambda application: {"traces": [application]}},
        audit_sink=SinkCasse(),
    )

    assert asyncio.run(harnais.appeler("lire_traces", {"application": "alpha"})) == {
        "traces": ["alpha"]}
    assert harnais.auditer()[-1]["statut"] == "ok"


def test_un_echec_du_sink_est_aussi_sans_effet_sur_un_appel_en_erreur():
    def casse(application):
        raise ValueError("indisponible")

    harnais = Harness(
        RegistreCapacites([manifeste()]),
        {"lire_traces": casse},
        audit_sink=SinkCasse(),
    )

    with pytest.raises(ValueError):
        asyncio.run(harnais.appeler("lire_traces", {"application": "alpha"}))
    assert harnais.auditer()[-1]["statut"] == "erreur"
    assert harnais.auditer()[-1]["erreur"] == "ValueError"
