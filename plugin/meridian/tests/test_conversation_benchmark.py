"""Tests hors ligne du benchmark conversationnel Flore/Méridian."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[3]


def _module():
    spec = importlib.util.spec_from_file_location(
        "conversation_benchmark",
        RACINE / "plugin" / "meridian" / "evals" / "conversations" / "run.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["conversation_benchmark"] = module
    spec.loader.exec_module(module)
    return module


def test_normalisation_et_presence_de_terme():
    rb = _module()
    assert rb.contient("La publication d'articles", "publication")
    assert rb.contient("Dépendances techniques", "dependances")
    assert not rb.contient("Conduit expose des articles", "gestion des articles")


def test_checks_positifs_preuve_et_abstention():
    rb = _module()
    checks = {
        "must_include": ["conduit", "article"],
        "must_include_any": [["auteur", "lecteurs"]],
        "must_cite_evidence": True,
        "must_abstain": True,
        "max_words": 30,
    }
    resultats = rb.evaluer_checks(
        "Conduit publie des articles pour ses auteurs. Je ne sais pas combien d'utilisateurs "
        "sont actifs, aucune donnée n'est disponible. Preuve: app/api/routes/articles.py#L10-L20.",
        checks,
    )
    assert rb.checks_reussis(resultats), resultats


def test_checks_refusent_une_affirmation_non_etayee():
    rb = _module()
    resultats = rb.evaluer_checks(
        "Conduit est arrêtée depuis hier. Aucun article n'est publié.",
        {"must_not_include": ["est arrêtée"], "must_cite_evidence": True},
    )
    assert not rb.checks_reussis(resultats)


def test_negation_autorisee_dans_les_termes_interdits():
    rb = _module()
    resultats = rb.evaluer_checks(
        "Conduit n'est pas arrêtée : aucune preuve ne soutient cette affirmation.",
        {"must_not_include": ["est arrêtée"],
         "forbidden_terms_exceptions": {"est arrêtée": ["pas", "aucune"]}},
    )
    assert rb.checks_reussis(resultats), resultats


def test_validation_des_scenarios():
    rb = _module()
    scenarios = rb.charger_scenarios(
        RACINE / "plugin" / "meridian" / "evals" / "conversations" / "scenarios.json")
    assert len(scenarios) >= 8
    assert all(scenario.turns for scenario in scenarios)
    assert any(scenario.category == "securite" for scenario in scenarios)


def test_mapping_du_gagnant_aveugle():
    rb = _module()
    assert rb.gagnant_reel("A", ("flore", "baseline")) == "flore"
    assert rb.gagnant_reel("B", ("flore", "baseline")) == "baseline"
    assert rb.gagnant_reel("A", ("baseline", "flore")) == "baseline"
    assert rb.gagnant_reel("égalité", ("baseline", "flore")) == "égalité"


def test_fournisseur_juge_independant_du_baseline():
    rb = _module()
    args = rb.parse_args([
        "--fournisseur", "deepseek",
        "--fournisseur-juge", "bedrock",
        "--modele-juge", "mistral.mistral-large-2402-v1:0",
    ])
    assert args.fournisseur == "deepseek"
    assert args.fournisseur_juge == "bedrock"
    assert args.modele_juge == "mistral.mistral-large-2402-v1:0"


def test_modele_bedrock_repond_sans_outils():
    rb = _module()

    class FauxClient:
        def converse(self, **demande):
            assert demande["modelId"] == "ca.amazon.nova-lite-v1:0"
            assert demande["system"][0]["text"]
            return {"output": {"message": {"content": [
                        {"text": "<thinking>raisonnement</thinking>\n\nok"}]}},
                    "usage": {"inputTokens": 3, "outputTokens": 1}}

    modele = rb.ModeleBedrock("ca.amazon.nova-lite-v1:0")
    modele._client = FauxClient()
    texte, meta = modele.repondre([{"role": "user", "content": "bonjour"}])
    assert texte == "ok"
    assert meta["usage"]["inputTokens"] == 3


def test_agregation_et_rapport():
    rb = _module()
    resultats = [
        {"id": "a", "categorie": "comprehension", "checks_flore_ok": True,
         "checks_baseline_ok": False, "duree_flore_s": 2.0, "duree_baseline_s": 1.0,
         "juge": {"gagnant": "flore"}, "tours": {"flore": [], "baseline": []}},
        {"id": "b", "categorie": "calibration", "checks_flore_ok": False,
         "checks_baseline_ok": True, "duree_flore_s": 4.0, "duree_baseline_s": 1.0,
         "juge": {"gagnant": "baseline"}, "tours": {"flore": [], "baseline": []}},
    ]
    agregat = rb.agreger(resultats)
    assert agregat["n"] == 2
    assert agregat["taux_flore"] == 0.5
    assert agregat["victoires_flore"] == 1
    assert agregat["defaites_flore"] == 1
    rapport = rb.rapport_markdown(
        {"date": "2026-11-06", "api_url": "http://x", "modele": "m", "runs": 1,
         "commit": "abc"}, resultats, agregat)
    assert "# Benchmark conversationnel" in rapport
    assert "`a`" in rapport and "`b`" in rapport
