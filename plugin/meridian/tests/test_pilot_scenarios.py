"""Scénarios pilotes, hypothèses de valeur et amorçage idempotent du ledger."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
EVALS = RACINE / "evals"
SCENARIOS = EVALS / "scenarios"
FICHIER_VALEURS = EVALS / "value-pilote.json"
SCENARIOS_PILOTES = {"incident-paiements", "changement-reglementaire"}

CHAMPS_SCENARIO = (
    "id",
    "skill",
    "prompt",
    "context",
    "expected_terms",
    "forbidden_terms",
    "expected_sections",
    "mcp_tools",
    "value",
)
CHAMPS_VALEUR = (
    "id",
    "type",
    "libelle",
    "proprietaire",
    "beneficiaire",
    "domaine",
    "objet_source_type",
    "objet_source_id",
    "baseline",
    "cible",
    "observe",
    "unite",
    "devise",
    "periode",
    "attribution",
    "confiance",
    "preuves",
    "statut",
)
TERMES_OBLIGATOIRES = {
    "incident-paiements": {"socle", "preuve", "sla", "limite"},
    "changement-reglementaire": {"impact", "interface", "preuve", "limite"},
}
OUTILS_ATTENDUS = {
    "incident-paiements": {
        "mcp__meridian__meridian_analyser",
        "mcp__meridian__meridian_impact",
        "mcp__meridian__meridian_claims",
    },
    "changement-reglementaire": {
        "mcp__meridian__meridian_analyser",
        "mcp__meridian__meridian_impact",
    },
}
TYPES_VALEUR = {
    "revenu",
    "cout_evite",
    "cout_reduit",
    "temps",
    "qualite",
    "sla",
    "risque",
    "conformite",
    "client",
    "connaissance",
    "strategie",
    "autre",
}


def _json(chemin):
    return json.loads(Path(chemin).read_text(encoding="utf-8"))


def _scenarios():
    return {
        chemin.stem: _json(chemin)
        for chemin in sorted(SCENARIOS.glob("*.json"))
        if chemin.stem in SCENARIOS_PILOTES
    }


def _valeurs_pilote():
    donnees = _json(FICHIER_VALEURS)
    assert isinstance(donnees, dict)
    assert donnees["tenant"] == "demo"
    valeurs = donnees["valeurs"]
    assert isinstance(valeurs, list) and valeurs
    return valeurs


def test_les_deux_scenarios_existent_avec_le_schema_attendu():
    scenarios = _scenarios()
    assert set(scenarios) == {"incident-paiements", "changement-reglementaire"}
    for identifiant, scenario in scenarios.items():
        assert set(CHAMPS_SCENARIO) <= set(scenario)
        assert scenario["id"] == identifiant
        assert scenario["skill"].startswith("meridian-")
        assert isinstance(scenario["prompt"], str)
        assert len(scenario["prompt"]) > 80

        contexte = scenario["context"]
        assert contexte["tenant"] == "demo"
        assert contexte["situation"].startswith("sit-")
        assert contexte["twins"]
        assert contexte["application"] == "conduit"
        for element in scenario["context"]["twins"]:
            assert element in scenario["prompt"].lower()
        assert contexte["situation"] in scenario["prompt"]
        assert contexte["application"] in scenario["prompt"]


def test_les_termes_et_sections_des_scenarios_sont_coherents():
    for identifiant, scenario in _scenarios().items():
        termes = scenario["expected_terms"]
        assert isinstance(termes, list) and termes
        normalises = {terme.lower() for terme in termes}
        assert TERMES_OBLIGATOIRES[identifiant] <= normalises
        assert {"proposition", "lecture", "approbation"} & normalises

        interdits = scenario["forbidden_terms"]
        assert isinstance(interdits, list) and interdits
        assert "action exécutée" in interdits
        exceptions = scenario.get("forbidden_terms_exceptions") or {}
        assert isinstance(exceptions, dict)

        sections = scenario["expected_sections"]
        assert isinstance(sections, list) and sections
        assert "socle" in sections

        outils = scenario["mcp_tools"]
        assert set(outils) == OUTILS_ATTENDUS[identifiant]
        assert all(outil.startswith("mcp__meridian__") for outil in outils)


def test_les_scenarios_interdisent_les_termes_attendus():
    scenarios = _scenarios()
    incident = scenarios["incident-paiements"]
    assert "causalité confirmée" in incident["forbidden_terms"]
    exceptions = incident["forbidden_terms_exceptions"]
    assert "non" in exceptions["causalité confirmée"]
    reglementaire = scenarios["changement-reglementaire"]
    assert "déployé" in reglementaire["forbidden_terms"]
    for scenario in scenarios.values():
        assert "action exécutée" in scenario["forbidden_terms"]
        texte = scenario["prompt"].lower()
        for terme in scenario["forbidden_terms"]:
            assert terme.lower() not in texte


def test_value_pilote_et_scenarios_portent_les_memes_hypotheses():
    valeurs = {valeur["id"]: valeur for valeur in _valeurs_pilote()}
    assert set(valeurs) == {"val-pilote-incident", "val-pilote-r118"}
    for scenario in _scenarios().values():
        valeur = scenario["value"]
        assert set(CHAMPS_VALEUR) <= set(valeur)
        assert valeur == valeurs[valeur["id"]]


def test_les_valeurs_ne_fabriquent_aucun_resultat_observe():
    valeurs = list(_valeurs_pilote())
    valeurs += [scenario["value"] for scenario in _scenarios().values()]
    for valeur in valeurs:
        assert valeur["type"] in TYPES_VALEUR
        assert valeur["statut"] in {"hypothese", "mesuree"}
        assert valeur["attribution"] in {
            "directe",
            "contribution",
            "activation",
            "inconnue",
        }
        assert 0 <= float(valeur["confiance"]) <= 1
        assert valeur["objet_source_type"]
        assert valeur["objet_source_id"]
        if valeur["statut"] == "hypothese":
            assert valeur["baseline"] is None
            assert valeur["observe"] is None
            assert valeur["preuves"] == []
        if valeur["statut"] == "mesuree":
            assert valeur["observe"] is not None


def test_les_hypotheses_pilotes_ont_les_cibles_attendues():
    valeurs = {valeur["id"]: valeur for valeur in _valeurs_pilote()}
    incident = valeurs["val-pilote-incident"]
    assert incident["type"] == "cout_evite"
    assert incident["proprietaire"] == "ops"
    assert incident["domaine"] == "Paiement"
    assert incident["cible"] == 1000
    assert incident["unite"] == "EUR"
    assert incident["devise"] == "EUR"
    assert incident["objet_source_id"] == "sit-latence-paiements"

    reglementaire = valeurs["val-pilote-r118"]
    assert reglementaire["type"] in {"risque", "conformite"}
    assert reglementaire["proprietaire"] == "architecte"
    assert reglementaire["cible"] == 0
    assert reglementaire["observe"] is None
    assert reglementaire["objet_source_id"] == "sit-anomalie-fraude"


def _module_amorcage():
    chemin = EVALS / "seed_value_pilote.py"
    specification = importlib.util.spec_from_file_location(
        "seed_value_pilote", chemin
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class _FausseReponse:
    def __init__(self, charge, code=200):
        self._brut = json.dumps(charge, ensure_ascii=False).encode("utf-8")
        self.status = code

    def read(self):
        return self._brut

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *arguments):
        return False


def test_le_dry_run_ne_contacte_pas_le_reseau(monkeypatch):
    module = _module_amorcage()

    def interdit(*arguments, **options):
        raise AssertionError("appel réseau interdit en dry-run")

    monkeypatch.setattr(module.urllib.request, "urlopen", interdit)
    resume = module.executer(
        api="http://test.invalid/api",
        tenant="demo",
        dry_run=True,
    )
    assert resume["dry_run"] is True
    assert resume["ok"] is True
    assert resume["crees"] == []
    assert resume["ignores"] == []
    assert resume["erreurs"] == []
    assert resume["a_creer"] == [
        "val-pilote-incident",
        "val-pilote-r118",
    ]


def test_l_amorcage_ignore_les_identifiants_deja_presents(monkeypatch):
    module = _module_amorcage()
    appels = []

    def faux_urlopen(requete, timeout=None):
        methode = requete.get_method()
        appels.append((methode, requete.full_url))
        if methode == "GET":
            return _FausseReponse(
                {
                    "tenant": "demo",
                    "valeurs": [{"id": "val-pilote-incident"}],
                }
            )
        corps = json.loads(requete.data.decode("utf-8"))
        assert corps["statut"] == "hypothese"
        assert corps["observe"] is None
        return _FausseReponse({"valeur": {"id": corps["id"]}}, code=201)

    monkeypatch.setattr(module.urllib.request, "urlopen", faux_urlopen)
    resume = module.executer(
        api="http://test.invalid/api",
        tenant="demo",
        dry_run=False,
    )
    assert resume["ok"] is True
    assert resume["ignores"] == ["val-pilote-incident"]
    assert resume["crees"] == ["val-pilote-r118"]
    assert resume["erreurs"] == []
    assert [methode for methode, _ in appels] == ["GET", "POST"]
    assert appels[0][1].startswith(
        "http://test.invalid/api/boucle/valeurs?"
    )
    assert appels[1][1] == "http://test.invalid/api/boucle/valeurs"


def test_le_seed_refuse_un_observe_sur_une_hypothese(tmp_path, monkeypatch):
    module = _module_amorcage()
    chemin = tmp_path / "valeurs.json"
    chemin.write_text(
        json.dumps(
            [
                {
                    "id": "val-pilote-incident",
                    "type": "cout_evite",
                    "libelle": "Hypothèse",
                    "proprietaire": "ops",
                    "observe": 1200,
                    "statut": "hypothese",
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        module.urllib.request,
        "urlopen",
        lambda *arguments, **options: pytest.fail("réseau interdit"),
    )
    with pytest.raises(ValueError, match="observe interdit"):
        module.executer(chemin=chemin, dry_run=True)
