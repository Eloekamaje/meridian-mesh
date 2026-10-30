"""Contrat de l'exécuteur gouverné : portée, approbation, coût, timeout, audit et catalogue."""
import ast
import asyncio
from pathlib import Path
import re

import pytest

from jumeau import executeur as module
from jumeau.capacites import ManifesteOutil, RegistreCapacites
from jumeau.executeur import (
    Approbation,
    ExecutionInvalide,
    ExecutionRefusee,
    Executeur,
    PolitiqueExecution,
    ResultatExecution,
)

SCHEMA = {"type": "object"}


def manifeste(**changements):
    champs = {
        "nom": "lire_traces",
        "version": "1.0.0",
        "description": "Lit les traces d'observabilité d'une application",
        "capacite": "observer",
        "types_objets_lus": ("Trace",),
        "schema_entree": SCHEMA,
        "schema_sortie": SCHEMA,
        "cout": 0.0,
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
        "schema_entree": SCHEMA,
        "schema_sortie": SCHEMA,
        "lecture_seule": False,
        "effets_de_bord": ("crée un Travail",),
        "timeout_ms": 2000,
        "source": "manifeste",
    }
    champs.update(changements)
    return ManifesteOutil(**champs)


def politique(**changements):
    champs = {"tenant": "banque", "persona": "flore", "perimetre": "paiements"}
    champs.update(changements)
    return PolitiqueExecution(**champs)


class Puits:
    def __init__(self):
        self.lignes = []

    def enregistrer(self, ligne):
        self.lignes.append(ligne)
        return {"statut": "ok"}


def test_lecture_autorisee_execute_et_audite():
    appels = []
    puits = Puits()

    def lire(application):
        appels.append(application)
        return {"traces": [application]}

    executeur = Executeur(RegistreCapacites([manifeste()]), {"lire_traces": lire}, audit=puits)
    resultat = asyncio.run(
        executeur.executer("lire_traces", {"application": "alpha"}, politique=politique())
    )

    assert isinstance(resultat, ResultatExecution)
    assert resultat.ok is True
    assert resultat.valeur == {"traces": ["alpha"]}
    assert resultat.erreur is None
    assert resultat.duree_ms >= 0
    assert appels == ["alpha"]
    assert len(puits.lignes) == 1
    ligne = puits.lignes[0]
    assert ligne["tenant"] == "banque"
    assert ligne["persona"] == "flore"
    assert ligne["perimetre"] == "paiements"
    assert ligne["outil"] == "lire_traces"
    assert ligne["capacite"] == "observer"
    assert ligne["statut"] == "ok"
    assert "arguments" not in ligne
    assert "application" not in ligne
    assert resultat.audit["statut"] == "ok"


def test_adaptateur_asynchrone_supporte():
    async def lire(application):
        await asyncio.sleep(0)
        return {"traces": [application]}

    executeur = Executeur(RegistreCapacites([manifeste()]), {"lire_traces": lire})
    resultat = asyncio.run(
        executeur.executer("lire_traces", {"application": "beta"}, politique=politique())
    )

    assert resultat.ok is True
    assert resultat.valeur == {"traces": ["beta"]}


def test_ecriture_refusee_sans_approbation_ou_sans_autorisation():
    appels = []
    executeur = Executeur(
        RegistreCapacites([ecriture()]),
        {"creer_travail": lambda application: appels.append(application) or {"cree": application}},
    )

    with pytest.raises(ExecutionRefusee) as sans_politique:
        asyncio.run(
            executeur.executer(
                "creer_travail",
                {"application": "alpha"},
                politique=politique(autoriser_ecritures=False),
                approbation=Approbation(acteur="flore", motif="demande"),
            )
        )
    assert sans_politique.value.statut == "ecriture_non_approuvee"

    with pytest.raises(ExecutionRefusee) as sans_approbation:
        asyncio.run(
            executeur.executer(
                "creer_travail",
                {"application": "alpha"},
                politique=politique(autoriser_ecritures=True),
            )
        )
    assert sans_approbation.value.statut == "ecriture_non_approuvee"
    assert appels == []


def test_ecriture_autorisee_avec_approbation_explicite():
    appels = []
    executeur = Executeur(
        RegistreCapacites([ecriture()]),
        {"creer_travail": lambda application: appels.append(application) or {"cree": application}},
    )
    approbation = Approbation(acteur="flore", motif="travail demandé", preuve="ticket-42")

    resultat = asyncio.run(
        executeur.executer(
            "creer_travail",
            {"application": "alpha"},
            politique=politique(autoriser_ecritures=True),
            approbation=approbation,
        )
    )

    assert resultat.ok is True
    assert resultat.valeur == {"cree": "alpha"}
    assert appels == ["alpha"]
    assert resultat.audit["approbation"] == "flore"


@pytest.mark.parametrize(
    "axe, valeur",
    (("tenant", "assurance"), ("persona", "autre"), ("perimetre", "autre")),
)
def test_hors_portee_tenant_persona_perimetre(axe, valeur):
    contrat = manifeste(tenant="banque", persona="flore", perimetre="paiements")
    executeur = Executeur(RegistreCapacites([contrat]), {"lire_traces": lambda application: {}})

    with pytest.raises(ExecutionRefusee) as refus:
        asyncio.run(
            executeur.executer("lire_traces", {}, politique=politique(**{axe: valeur}))
        )

    assert refus.value.statut == "hors_portee"


def test_portee_manifeste_exige_une_politique_correspondante():
    contrat = manifeste(tenant="banque")
    executeur = Executeur(RegistreCapacites([contrat]), {"lire_traces": lambda application: {}})
    sans_tenant = PolitiqueExecution(tenant=None, persona="flore", perimetre="paiements")

    with pytest.raises(ExecutionRefusee) as refus:
        asyncio.run(executeur.executer("lire_traces", {}, politique=sans_tenant))

    assert refus.value.statut == "hors_portee"


def test_allowlist_refuse_un_outil_non_liste():
    registre = RegistreCapacites([manifeste(), manifeste(nom="lire_logs")])
    executeur = Executeur(
        registre,
        {
            "lire_traces": lambda application: {"traces": []},
            "lire_logs": lambda application: {"logs": []},
        },
    )

    autorise = asyncio.run(
        executeur.executer(
            "lire_traces",
            {"application": "alpha"},
            politique=politique(allowlist=("lire_traces",)),
        )
    )
    assert autorise.ok is True

    with pytest.raises(ExecutionRefusee) as refus:
        asyncio.run(
            executeur.executer(
                "lire_logs",
                {"application": "alpha"},
                politique=politique(allowlist=("lire_traces",)),
            )
        )
    assert refus.value.statut == "hors_portee"


def test_allowlist_de_manifeste_est_honoree_comme_namespace():
    contrat = manifeste(allowlist=("meridian.builtin",))
    executeur = Executeur(RegistreCapacites([contrat]), {"lire_traces": lambda application: {}})

    resultat = asyncio.run(
        executeur.executer(
            "lire_traces",
            {"application": "alpha"},
            politique=politique(allowlist=("meridian.builtin",)),
        )
    )

    assert resultat.ok is True


def test_cout_refuse_au_dessus_du_plafond():
    appels = []
    executeur = Executeur(
        RegistreCapacites([manifeste(cout=2.0)]),
        {"lire_traces": lambda application: appels.append(application) or {"traces": []}},
    )

    with pytest.raises(ExecutionRefusee) as refus:
        asyncio.run(
            executeur.executer("lire_traces", {}, politique=politique(max_cout=1.0))
        )

    assert refus.value.statut == "cout"
    assert appels == []


def test_cout_nul_dans_la_politique_ne_plafonne_pas():
    executeur = Executeur(
        RegistreCapacites([manifeste(cout=99.0)]),
        {"lire_traces": lambda application: {"traces": []}},
    )

    resultat = asyncio.run(
        executeur.executer(
            "lire_traces", {"application": "alpha"}, politique=politique(max_cout=0.0)
        )
    )

    assert resultat.ok is True


def test_timeout_retourne_un_echec_sanitise():
    async def lent(application):
        await asyncio.sleep(0.2)
        return {"traces": [application]}

    executeur = Executeur(
        RegistreCapacites([manifeste(timeout_ms=5000)]), {"lire_traces": lent}
    )
    resultat = asyncio.run(
        executeur.executer(
            "lire_traces",
            {"application": "alpha"},
            politique=politique(timeout_s=0.01),
        )
    )

    assert resultat.ok is False
    assert resultat.valeur is None
    assert resultat.erreur == "TimeoutError"
    assert resultat.audit["statut"] == "timeout"


def test_timeout_du_manifeste_borne_aussi_l_appel():
    async def lent(application):
        await asyncio.sleep(0.2)
        return {"traces": [application]}

    executeur = Executeur(
        RegistreCapacites([manifeste(timeout_ms=10)]), {"lire_traces": lent}
    )
    resultat = asyncio.run(
        executeur.executer(
            "lire_traces",
            {"application": "alpha"},
            politique=politique(timeout_s=5.0),
        )
    )

    assert resultat.ok is False
    assert resultat.erreur == "TimeoutError"


def test_outil_inconnu_refuse_et_audite():
    puits = Puits()
    executeur = Executeur(RegistreCapacites([]), audit=puits)

    with pytest.raises(ExecutionRefusee) as refus:
        asyncio.run(
            executeur.executer("inconnu", {"application": "alpha"}, politique=politique())
        )

    assert refus.value.statut == "manifeste_absent"
    assert puits.lignes[0]["outil"] == "inconnu"
    assert puits.lignes[0]["statut"] == "refuse"
    assert "application" not in puits.lignes[0]


def test_adaptateur_absent_refuse():
    executeur = Executeur(RegistreCapacites([manifeste()]))

    with pytest.raises(ExecutionRefusee) as refus:
        asyncio.run(executeur.executer("lire_traces", {}, politique=politique()))

    assert refus.value.statut == "adaptateur_absent"


def test_exception_adaptateur_est_sanitisee():
    def echoue(application, token=None):
        raise RuntimeError("password=secret-tres-long")

    puits = Puits()
    executeur = Executeur(
        RegistreCapacites([manifeste()]), {"lire_traces": echoue}, audit=puits
    )
    resultat = asyncio.run(
        executeur.executer(
            "lire_traces",
            {"application": "alpha", "token": "secret-tres-long"},
            politique=politique(),
        )
    )

    assert resultat.ok is False
    assert resultat.valeur is None
    assert resultat.erreur == "RuntimeError"
    assert "secret" not in repr(resultat)
    assert "token" not in repr(resultat)
    assert "secret" not in repr(puits.lignes)
    assert puits.lignes[0]["erreur"] == "RuntimeError"


def test_echec_du_puits_d_audit_ne_perd_pas_le_resultat():
    def audit_en_panne(ligne):
        raise RuntimeError("panne du journal")

    executeur = Executeur(
        RegistreCapacites([manifeste()]),
        {"lire_traces": lambda application: {"traces": [application]}},
        audit=audit_en_panne,
    )
    resultat = asyncio.run(
        executeur.executer("lire_traces", {"application": "alpha"}, politique=politique())
    )

    assert resultat.ok is True
    assert resultat.valeur == {"traces": ["alpha"]}
    assert resultat.audit["statut"] == "ok"


def test_lister_filtre_lecture_ecriture_portee_allowlist_et_cout():
    registre = RegistreCapacites(
        [
            manifeste(nom="lire_global"),
            manifeste(nom="lire_banque", tenant="banque"),
            manifeste(nom="lire_autre", tenant="assurance"),
            ecriture(),
            manifeste(nom="lire_cher", cout=5.0),
        ]
    )
    executeur = Executeur(registre)

    def noms(politique_execution):
        return {manifeste.nom for manifeste in executeur.lister(politique_execution)}

    assert noms(politique(max_cout=1.0)) == {"lire_global", "lire_banque"}
    assert noms(politique(autoriser_ecritures=True, max_cout=1.0)) == {
        "lire_global", "lire_banque", "creer_travail"}
    assert noms(politique(allowlist=("lire_global",), max_cout=1.0)) == {"lire_global"}
    assert noms(
        PolitiqueExecution(
            tenant="assurance", persona="flore", perimetre="paiements", max_cout=1.0)
    ) == {"lire_global", "lire_autre"}


def test_arguments_et_politique_invalides_levent_execution_invalide():
    executeur = Executeur(
        RegistreCapacites([manifeste()]), {"lire_traces": lambda application: {}}
    )

    with pytest.raises(ExecutionInvalide):
        asyncio.run(
            executeur.executer("lire_traces", ["alpha"], politique=politique())
        )
    with pytest.raises(ExecutionInvalide):
        asyncio.run(
            executeur.executer("lire_traces", {}, politique={"tenant": "banque"})
        )
    with pytest.raises(ExecutionInvalide):
        executeur.enregistrer_adaptateur("lire_traces", "pas une fonction")


def test_module_sans_reseau_ni_execution_externe():
    source = Path(module.__file__).read_text(encoding="utf-8")
    interdits = (
        r"\beval\s*\(", r"\bexec\s*\(", r"__import__\s*\(", r"\bcompile\s*\(",
        r"\bimportlib\b", r"\bsocket\b", r"\burllib\b", r"\brequests\b",
        r"\bhttpx\b", r"\bsubprocess\b", r"\bos\.system\b",
    )
    for motif in interdits:
        assert re.search(motif, source) is None, motif
    arbre = ast.parse(source)
    autorises = {"__future__", "asyncio", "collections", "copy", "dataclasses", "inspect",
                 "math", "time", "typing"}
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            assert all(alias.name.split(".")[0] in autorises for alias in noeud.names)
        if isinstance(noeud, ast.ImportFrom):
            assert (noeud.module or "").split(".")[0] in autorises
