"""Scénarios adversariaux, paquets gelés, clés et revue humaine."""
from __future__ import annotations

import importlib.util
import json
import re
import unicodedata
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
EVALS = RACINE / "evals"
SCENARIOS = EVALS / "scenarios"
DATA = EVALS / "data"
CLES = EVALS / "answer-keys"
HUMAIN = EVALS / "human"

ADVERSARIAUX = ("incident-preuve-perimee", "portefeuille-baseline-absente")
TOUS = ("incident-paiements", "changement-reglementaire", *ADVERSARIAUX)
CHAMPS_PAQUET = {"profil", "composition", "dossier", "reponse"}
CHAMPS_REVUE = {
    "reviewer_id",
    "scenario",
    "decision_accuracy",
    "evidence_grounding",
    "calibration",
    "usefulness",
    "trust",
    "critical_errors",
    "would_approve",
    "time_seconds",
    "comments",
}


def _json(chemin: Path):
    return json.loads(Path(chemin).read_text(encoding="utf-8"))


def _normaliser(texte: str) -> str:
    decompose = unicodedata.normalize("NFKD", str(texte or ""))
    sans_accents = "".join(
        c for c in decompose if not unicodedata.combining(c)
    )
    return " ".join(
        sans_accents.casefold().replace("_", " ").replace("-", " ").split()
    )


def _contient(termes, fragment: str) -> bool:
    return any(fragment in _normaliser(terme) for terme in termes)


def _scenario(identifiant: str) -> dict:
    chemin = SCENARIOS / f"{identifiant}.json"
    assert chemin.is_file(), f"scénario absent : {chemin}"
    return _json(chemin)


def _module_freeze():
    chemin = EVALS / "freeze_data.py"
    specification = importlib.util.spec_from_file_location(
        "freeze_data", chemin
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_les_deux_scenarios_adversariaux_existent_avec_les_champs_attendus():
    for identifiant in ADVERSARIAUX:
        scenario = _scenario(identifiant)
        assert scenario["id"] == identifiant
        assert scenario["skill"].startswith("meridian-")
        assert len(scenario["prompt"]) > 80
        assert scenario["context"]["tenant"] == "demo"
        assert isinstance(scenario["expected_terms"], list)
        assert scenario["expected_terms"]
        assert isinstance(scenario["expected_sections"], list)
        assert scenario["expected_sections"]
        assert isinstance(scenario["forbidden_terms"], list)
        assert scenario["forbidden_terms"]
        assert scenario["mcp_tools"]
        assert all(
            outil.startswith("mcp__meridian__")
            for outil in scenario["mcp_tools"]
        )
        assert scenario["data_pack"] == f"../data/{identifiant}.json"

        valeur = scenario["value"]
        assert valeur["statut"] == "hypothese"
        assert valeur["observe"] is None
        assert valeur["baseline"] is None
        assert valeur["preuves"] == []
        assert 0 <= float(valeur["confiance"]) <= 1


def test_chaque_scenario_reference_son_paquet_et_sa_cle():
    for identifiant in TOUS:
        scenario = _scenario(identifiant)
        paquet = (SCENARIOS / scenario["data_pack"]).resolve()
        assert paquet == (DATA / f"{identifiant}.json").resolve()
        assert paquet.is_file()

        cle = _json(CLES / f"{identifiant}.json")
        assert (EVALS / cle["data_pack"]).resolve() == paquet
        assert (EVALS / cle["scenario_file"]).resolve() == (
            SCENARIOS / f"{identifiant}.json"
        ).resolve()


def test_la_preuve_perimee_exige_peremption_abstention_et_confiance_reduite():
    scenario = _scenario("incident-preuve-perimee")
    assert scenario["context"]["situation"] == "sit-connaissance-support"
    assert "support" in scenario["context"]["twins"]

    termes = scenario["expected_terms"]
    for fragment in ("perim", "fraicheur", "abstention", "confiance"):
        assert _contient(termes, fragment), fragment
    assert _contient(scenario["expected_sections"], "abstention")

    interdits = scenario["forbidden_terms"]
    assert _contient(interdits, "causalite confirmee") or _contient(
        interdits, "cause racine certaine"
    )
    assert "action exécutée" in interdits
    exceptions = scenario.get("forbidden_terms_exceptions") or {}
    assert "non" in exceptions["causalité confirmée"]


def test_le_portefeuille_sans_baseline_exige_dette_et_refus():
    scenario = _scenario("portefeuille-baseline-absente")
    assert scenario["context"]["scope"] == "portfolio"
    assert scenario["context"]["domaine"] == "Paiement"
    assert "situation" not in scenario["context"]

    termes = scenario["expected_terms"]
    for fragment in (
        "baseline",
        "dette de mesure",
        "valeur realisee",
        "abstention",
    ):
        assert _contient(termes, fragment), fragment
    assert _contient(scenario["expected_sections"], "dette de mesure")

    interdits = scenario["forbidden_terms"]
    assert _contient(interdits, "valeur realisee")
    assert _contient(interdits, "action executee")
    assert "non" in scenario["forbidden_terms_exceptions"]["valeur réalisée"]


def test_les_cles_de_reponse_sont_completes_et_reliees_aux_paquets():
    for identifiant in TOUS:
        cle = _json(CLES / f"{identifiant}.json")
        assert cle["scenario"] == identifiant
        assert cle["version"] == 1
        assert cle["provenance"] == "authored"
        for champ in (
            "expected_decision_points",
            "required_evidence",
            "acceptable_options",
            "unacceptable_claims",
        ):
            assert isinstance(cle[champ], list) and cle[champ], champ
        assert isinstance(cle["abstention_condition"], str)
        assert len(cle["abstention_condition"]) > 20

        scenario_file = EVALS / cle["scenario_file"]
        data_pack = EVALS / cle["data_pack"]
        assert scenario_file.is_file(), scenario_file
        assert data_pack.is_file(), data_pack
        assert data_pack.parent == DATA
        assert scenario_file.parent == SCENARIOS
        assert "observe" not in cle


def test_les_cles_adversariales_interdisent_les_affirmations_fabriquees():
    preuve = _json(CLES / "incident-preuve-perimee.json")
    affirmations = _normaliser(" ".join(preuve["unacceptable_claims"]))
    assert "cause" in affirmations
    assert "preuve" in affirmations
    assert "perim" in affirmations or "recente" in affirmations

    baseline = _json(CLES / "portefeuille-baseline-absente.json")
    affirmations = _normaliser(" ".join(baseline["unacceptable_claims"]))
    assert "valeur" in affirmations or "roi" in affirmations
    assert "baseline" in affirmations
    assert "action" in affirmations


@pytest.mark.parametrize("identifiant", TOUS)
def test_les_paquets_de_donnees_sont_geles_et_sanitises(identifiant: str):
    chemin = DATA / f"{identifiant}.json"
    assert chemin.is_file(), f"paquet absent : {chemin}"
    paquet = _json(chemin)
    assert set(paquet) == CHAMPS_PAQUET
    assert isinstance(paquet["profil"], dict) and paquet["profil"]
    assert isinstance(paquet["composition"], dict) and paquet["composition"]
    assert isinstance(paquet["dossier"], dict) and paquet["dossier"]
    assert isinstance(paquet["reponse"], dict) and paquet["reponse"]
    assert paquet["profil"].get("id") == "architecte"

    texte = chemin.read_text(encoding="utf-8")
    assert "non généré" not in texte
    assert not re.search(
        r"(?i)(?:bearer\s+[A-Za-z0-9_.~+/=-]{12,}|\bsk-[A-Za-z0-9_-]{8,}|"
        r"\bgh[pousr]_[A-Za-z0-9]{10,})",
        texte,
    )


def test_aucune_valeur_observee_n_est_fabriquee_dans_les_artefacts_authors():
    for identifiant in ADVERSARIAUX:
        valeur = _scenario(identifiant)["value"]
        assert valeur["statut"] == "hypothese"
        assert valeur["observe"] is None
        assert valeur["baseline"] is None
        assert valeur["preuves"] == []

    for identifiant in TOUS:
        cle = _json(CLES / f"{identifiant}.json")
        assert "observe" not in cle
        assert not any(
            mot in _normaliser(json.dumps(cle, ensure_ascii=False))
            for mot in ("observe 8", "observe 1", "valeur mesuree")
        )


def test_le_schema_de_revue_humaine_couvre_tous_les_champs_obligatoires():
    schema = _json(HUMAIN / "review.schema.json")
    assert schema["$schema"].startswith("https://json-schema.org/")
    assert schema["type"] == "object"
    assert set(schema["required"]) == CHAMPS_REVUE
    assert set(schema["properties"]) >= CHAMPS_REVUE
    proprietes = schema["properties"]

    for champ in ("decision_accuracy", "evidence_grounding", "calibration"):
        assert proprietes[champ]["type"] == "integer"
        assert proprietes[champ]["minimum"] == 0
        assert proprietes[champ]["maximum"] == 4
    for champ in ("usefulness", "trust"):
        assert proprietes[champ]["type"] == "integer"
        assert proprietes[champ]["minimum"] == 1
        assert proprietes[champ]["maximum"] == 5

    assert proprietes["reviewer_id"]["type"] == "string"
    assert proprietes["scenario"]["type"] == "string"
    assert proprietes["critical_errors"]["type"] == "array"
    assert proprietes["would_approve"]["type"] == "boolean"
    assert proprietes["time_seconds"]["type"] == "integer"
    assert proprietes["time_seconds"]["minimum"] == 0
    assert proprietes["comments"]["type"] == "string"

    recommandations = (HUMAIN / "README.md").read_text(encoding="utf-8")
    for champ in CHAMPS_REVUE:
        assert f"`{champ}`" in recommandations, champ


def test_une_revue_humaine_valide_respecte_le_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = _json(HUMAIN / "review.schema.json")
    jsonschema.Draft202012Validator.check_schema(schema)
    revue = {
        "reviewer_id": "reviewer-01",
        "scenario": "incident-preuve-perimee",
        "decision_accuracy": 3,
        "evidence_grounding": 4,
        "calibration": 4,
        "usefulness": 4,
        "trust": 4,
        "critical_errors": [],
        "would_approve": True,
        "time_seconds": 240,
        "comments": (
            "La preuve périmée est signalée et la cause n'est pas confirmée."
        ),
    }
    jsonschema.validate(revue, schema)

    invalide = dict(revue)
    del invalide["comments"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalide, schema)


def test_le_freezer_ne_contacte_pas_le_reseau_en_dry_run(monkeypatch):
    module = _module_freeze()

    def interdit(*arguments, **options):
        raise AssertionError("appel réseau interdit en dry-run")

    monkeypatch.setattr(module.urllib.request, "urlopen", interdit)
    resume = module.executer(dry_run=True)
    assert resume["dry_run"] is True
    assert resume["ok"] is True
    assert resume["ecrits"] == []
    assert resume["erreurs"] == []
    assert {appel["scenario"] for appel in resume["appels"]} == set(TOUS)


def test_le_payload_portefeuille_est_global_et_le_payload_incident_est_situe():
    module = _module_freeze()
    portefeuille = module.construire_payload(
        _scenario("portefeuille-baseline-absente")
    )
    assert portefeuille["scope"] == "portfolio"
    assert portefeuille["domaine"] == "Paiement"
    assert "situation_id" not in portefeuille
    assert "twin_ids" not in portefeuille
    assert "application_id" not in portefeuille

    preuve = module.construire_payload(_scenario("incident-preuve-perimee"))
    assert preuve["situation_id"] == "sit-connaissance-support"
    assert preuve["twin_ids"] == ["support"]
    assert preuve["application_id"] == "conduit"


def test_le_freezer_est_idempotent_et_masque_les_secrets(tmp_path):
    module = _module_freeze()
    chemin = tmp_path / "paquet.json"
    paquet = {
        "profil": {"id": "architecte"},
        "composition": {},
        "dossier": {},
        "reponse": {},
    }
    assert module.ecrire_idempotent(chemin, paquet) is True
    assert module.ecrire_idempotent(chemin, paquet) is False
    assert _json(chemin) == paquet

    assaini = module.assainir({
        "token": "valeur",
        "note": "Bearer abcdefghijklmnop",
        "url": "https://user:pass@example.com/ressource",
        "libelle": "Paiement",
    })
    assert assaini["token"] == "***"
    assert assaini["note"] == "***"
    assert assaini["url"] == "***"
    assert assaini["libelle"] == "Paiement"


def test_le_freezer_retire_les_durees_et_refuse_un_paquet_incomplet():
    module = _module_freeze()
    charge = {
        "profil": {},
        "composition": {},
        "dossier": {"duree_ms": 12.3, "statut": "ok"},
        "reponse": {"specialistes": [{"duree_ms": 4.2, "statut": "ok"}]},
    }
    paquet = module.extraire_paquet(charge)
    assert set(paquet) == CHAMPS_PAQUET
    assert "duree_ms" not in paquet["dossier"]
    assert "duree_ms" not in paquet["reponse"]["specialistes"][0]

    with pytest.raises(module.FreezeError):
        module.extraire_paquet({"profil": {}})
