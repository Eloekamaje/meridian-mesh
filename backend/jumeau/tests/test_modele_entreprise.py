"""Tests du modèle d'entreprise : familles, Twins non applicatifs, invariants, cycle et sérialisation."""
import ast
from dataclasses import asdict
import json
from pathlib import Path

import pytest

from jumeau import modele_entreprise as modele
from jumeau.modele_entreprise import (
    FAMILLES, MODES, TYPES, TYPES_TWIN, Claim, Decision, Domain, Initiative,
    Investigation, Learning, ObjetEntreprise, Opportunity, Outcome, Relation, Risk,
    Situation, Source, Twin, est_twin_non_applicatif, famille_de,
    transitions_connaissance, verifier_transition,
)

RACINE = Path(__file__).resolve().parents[1]


def base(**champs):
    valeurs = {
        "id": "objet-1",
        "tenant_id": "tenant-1",
        "cree_le": "2026-01-01T08:00:00+00:00",
        "observe_le": "2026-01-02T09:00:00+00:00",
        "valide_depuis": "2026-01-02T09:00:00+00:00",
        "confiance": 0.8,
    }
    valeurs.update(champs)
    return valeurs


def twin(type_="PROCESS", **champs):
    valeurs = base(id="twin-1")
    valeurs.update(champs)
    return Twin(**valeurs, type=type_, nom="Onboarding client", mission="Ouvrir un compte")


def claim(**champs):
    valeurs = base(id="claim-1")
    valeurs.update(champs)
    valeurs.setdefault("sujet", "Twin onboarding")
    valeurs.setdefault("predicat", "REQUIERT")
    valeurs.setdefault("objet", "Vérification KYC")
    valeurs.setdefault("mode", "OBSERVED")
    return Claim(**valeurs)


def investigation(**champs):
    valeurs = base(id="investigation-1")
    valeurs.update(champs)
    return Investigation(**valeurs, titre="Comprendre le délai", question="Pourquoi 12 jours ?")


def decision(**champs):
    valeurs = base(id="decision-1")
    valeurs.update(champs)
    valeurs.setdefault("investigation_id", "investigation-1")
    return Decision(**valeurs, rationale="Réduire le délai")


def initiative(**champs):
    valeurs = base(id="initiative-1")
    valeurs.update(champs)
    valeurs.setdefault("decision_id", "decision-1")
    return Initiative(**valeurs, titre="Automatiser la pièce")


def outcome(**champs):
    valeurs = base(id="outcome-1")
    valeurs.update(champs)
    valeurs.setdefault("initiative_id", "initiative-1")
    return Outcome(**valeurs, metrique="delai_moyen_jours", valeur_attendue=5, valeur_observee=6)


def test_les_huit_familles_et_les_sept_types_sont_exposes():
    assert len(FAMILLES) == 8
    assert set(FAMILLES) == {
        "identite_structure", "sources_preuves", "connaissance", "emergence",
        "investigation", "decision", "resultat_apprentissage", "interaction_gouvernance",
    }
    assert len(TYPES_TWIN) == 7
    assert set(TYPES_TWIN) == {
        "APPLICATION", "PROCESS", "CAPABILITY", "JOURNEY", "ORGANIZATION", "PRODUCT", "DATA_DOMAIN",
    }
    assert tuple(TYPES) == tuple(TYPES_TWIN)
    assert set(MODES) == {"DECLARED", "OBSERVED", "INFERRED", "PROPOSED", "CONFIRMED"}
    assert set(TYPES_TWIN) != {"APPLICATION"}


def test_twin_process_capability_et_journey_sont_valides_pas_seulement_application():
    for type_ in ("PROCESS", "CAPABILITY", "JOURNEY", "ORGANIZATION", "PRODUCT", "DATA_DOMAIN"):
        objet = twin(type_)
        assert objet.type == type_
        assert objet.famille == "identite_structure"
        assert est_twin_non_applicatif(objet) is True
        assert est_twin_non_applicatif(type_) is True

    application = twin("APPLICATION", application_id="app-42")
    assert application.est_application is True
    assert est_twin_non_applicatif(application) is False
    assert est_twin_non_applicatif("APPLICATION") is False
    assert est_twin_non_applicatif("PROCESS") is True
    assert est_twin_non_applicatif("INCONNU") is False


def test_type_mode_et_famille_inconnus_sont_refuses():
    with pytest.raises(ValueError):
        twin("GALAXY")

    with pytest.raises(ValueError):
        claim(mode="MAGIQUE")

    with pytest.raises(ValueError):
        claim(modes=["MAGIQUE"])

    with pytest.raises(ValueError):
        ObjetEntreprise(**base(), type="CLAIM", famille="famille_inventee")

    with pytest.raises(ValueError):
        ObjetEntreprise(**base(), type="CLAIM", famille="identite_structure")

    with pytest.raises(ValueError):
        famille_de("TYPE_QUI_N_EXISTE_PAS")

    with pytest.raises(ValueError):
        ObjetEntreprise(**base(id=""), type="CLAIM")

    with pytest.raises(ValueError):
        ObjetEntreprise(**base(tenant_id="  "), type="CLAIM")


def test_claim_confirmed_sans_preuve_est_refuse():
    with pytest.raises(ValueError):
        claim(statut="CONFIRMED", preuves=[])

    with pytest.raises(ValueError):
        claim(mode="CONFIRMED", statut="SUPPORTED", preuves=[])

    confirme = claim(statut="CONFIRMED", preuves=[{"locator": "doc://kyc#L12", "extrait": "KYC requis"}])
    assert confirme.statut == "CONFIRMED"
    assert confirme.preuves


def test_decision_sans_investigation_est_refusee():
    with pytest.raises(ValueError):
        Decision(**base(), investigation_id="", rationale="Sans enquête")

    with pytest.raises(ValueError):
        Decision(**base(), investigation_id=None)

    reliee = Decision(**base(), investigation_ref="investigation-ref")
    assert reliee.investigation_id == "investigation-ref"


def test_outcome_sans_initiative_est_refuse():
    with pytest.raises(ValueError):
        Outcome(**base(), initiative_id="", metrique="delai")

    with pytest.raises(ValueError):
        Outcome(**base(), initiative_id=None, metrique="delai")

    relie = Outcome(**base(), initiative_ref="initiative-ref", metrique="delai")
    assert relie.initiative_id == "initiative-ref"


def test_cycle_de_connaissance_transitions_valides_et_invalides():
    cycle = [
        "observation", "hypothese", "claim", "claim_renforce",
        "connaissance_mature", "decision", "apprentissage",
    ]
    assert list(modele.CYCLE_CONNAISSANCE) == cycle
    for depuis, vers in zip(cycle, cycle[1:]):
        assert transitions_connaissance(depuis) == frozenset({vers})
        assert transitions_connaissance(depuis, vers) is True

    assert transitions_connaissance("apprentissage") == frozenset()
    assert transitions_connaissance("observation", "decision") is False
    assert transitions_connaissance("claim", "hypothese") is False
    with pytest.raises(ValueError):
        transitions_connaissance("etat_inconnu")
    with pytest.raises(ValueError):
        verifier_transition("observation", "decision")

    objet = claim(maturite="observation")
    assert objet.maturer("hypothese").maturite == "hypothese"
    assert objet.maturer("claim").maturite == "claim"
    with pytest.raises(ValueError):
        objet.maturer("decision")


def test_temporalite_obligatoire_sur_les_objets_importants():
    for champ in ("cree_le", "observe_le", "valide_depuis"):
        champs = base()
        champs.pop(champ)
        with pytest.raises(ValueError):
            Twin(**champs, type="PROCESS", nom="Twin sans temporalité")

        champs = base()
        champs[champ] = None
        with pytest.raises(ValueError):
            claim(**champs)

    with pytest.raises(ValueError):
        claim(valide_jusqua="2025-12-31T00:00:00+00:00")

    daté = Twin(
        **base(cree_le=None, observe_le="2026-01-02", valide_depuis="2026-01-02"),
        type="PROCESS",
        nom="Twin daté",
        temporalite={"created_at": "2026-01-01T00:00:00+00:00"},
    )
    assert daté.cree_le == "2026-01-01T00:00:00+00:00"


def test_objets_serialisables_en_json():
    objets = [
        twin("PROCESS"),
        claim(preuves=["doc://preuve#L1"]),
        Relation(**base(id="relation-1"), source_id="twin-1", cible_id="twin-2", predicat="DEPEND_DE"),
        Situation(**base(id="situation-1"), titre="Délai anormal", twin_ids=["twin-1", "twin-2"]),
        Opportunity(**base(id="opportunity-1"), titre="Automatiser", situation_id="situation-1"),
        Risk(**base(id="risk-1"), titre="Dépendance", probabilite=0.4, severite="HAUTE"),
        investigation(),
        decision(),
        initiative(),
        outcome(),
        Learning(**base(id="learning-1"), enonce="Une pièce manquante allonge le délai", outcome_ids=["outcome-1"]),
        Source(**base(id="source-1"), nom="Git", type="GIT", emplacement="/depot"),
        Domain(**base(id="domain-1"), nom="KYC", type="DISCOVERED"),
    ]
    for objet in objets:
        texte = json.dumps(objet.to_dict(), ensure_ascii=False)
        assert json.loads(texte)["id"] == objet.id
        json.dumps(asdict(objet), ensure_ascii=False)
        assert json.loads(objet.to_json()) == objet.to_dict()


def test_le_module_ne_reduit_pas_twin_a_application_et_n_importe_pas_de_base():
    source = (RACINE / "modele_entreprise.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)

    types_assignes = []
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Assign):
            for cible in noeud.targets:
                if isinstance(cible, ast.Name) and cible.id == "TYPES":
                    types_assignes.append(noeud.value)
    for valeur in types_assignes:
        if isinstance(valeur, (ast.Set, ast.List, ast.Tuple)):
            litteraux = [
                element.value for element in valeur.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            ]
            assert litteraux != ["APPLICATION"]

    imports = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.module:
            imports.add(noeud.module.split(".", 1)[0])
    interdits = {
        "psycopg", "psycopg2", "sqlite3", "sqlalchemy", "motor", "pymongo", "redis",
        "asyncpg", "requests", "httpx", "urllib", "socket",
    }
    assert imports.isdisjoint(interdits)
    assert "APPLICATION" in TYPES_TWIN and len(TYPES_TWIN) == 7
