"""Le harness d'exploration reste confiné au dépôt et lit le SHA, pas l'arbre de travail."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from meridian.application.exploration_agent import ExplorationHarness, OutilsInvalides, RepoSnapshot


def _git(depot, *args):
    return subprocess.run(["git", "-C", str(depot), *args], capture_output=True, text=True, check=True)


def _depot(tmp_path, nom="api"):
    depot = tmp_path / nom
    depot.mkdir()
    _git(depot, "init", "-q")
    _git(depot, "config", "user.email", "test@example.test")
    _git(depot, "config", "user.name", "Test")
    (depot / "app.py").write_text("alpha\nsubmit\nomega\n", encoding="utf-8")
    (depot / "README.md").write_text("# API\n", encoding="utf-8")
    _git(depot, "add", ".")
    _git(depot, "commit", "-qm", "initial")
    return depot


def test_lecture_au_sha_ignore_les_modifications_non_commitees(tmp_path):
    depot = _depot(tmp_path)
    sha = _git(depot, "rev-parse", "HEAD").stdout.strip()
    snapshot = RepoSnapshot.depuis_git("api", depot, sha=sha)
    (depot / "app.py").write_text("modifié\n", encoding="utf-8")
    assert snapshot.lire("app.py")["lines"][0]["text"] == "alpha"
    assert snapshot.lire("app.py")["sha"] == sha
    assert snapshot.chercher("submit")["matches"][0]["line"] == 2


def test_recherche_regex_path_pagination_et_comptage(tmp_path):
    depot = _depot(tmp_path)
    (depot / "src").mkdir()
    (depot / "docs").mkdir()
    (depot / "src" / "Routes.java").write_text(
        "\n".join(f'@GetMapping("/r{i}")' for i in range(120)) + "\n", encoding="utf-8")
    (depot / "docs" / "note.md").write_text("@GetMapping hors code\n", encoding="utf-8")
    _git(depot, "add", ".")
    _git(depot, "commit", "-qm", "routes")
    snapshot = RepoSnapshot.depuis_git("api", depot)
    page = snapshot.chercher("@GetMapping", 100, prefixe="src")
    assert len(page["matches"]) == 100 and page["limit_reached"] is True
    assert snapshot.chercher("@GetMapping", 100, prefixe="src", offset=100)["matches"][-1]["line"] == 120
    assert snapshot.compter("@GetMapping", prefixe="src")["total"] == 120
    assert snapshot.compter("@(Get|Post)Mapping", prefixe="src", regex=True)["total"] == 120
    assert snapshot.compter("@GetMapping")["total"] == 121


def test_chemins_hors_depot_refuses(tmp_path):
    depot = _depot(tmp_path)
    snapshot = RepoSnapshot.depuis_git("api", depot)
    for chemin in ("../secret", "/etc/passwd", "a/../../secret"):
        with pytest.raises(OutilsInvalides):
            snapshot.lire(chemin)


def test_multi_repo_et_outils_confinés(tmp_path):
    api = _depot(tmp_path, "api")
    web = _depot(tmp_path, "web")
    harness = ExplorationHarness([
        RepoSnapshot.depuis_git("api", api, role="backend"),
        RepoSnapshot.depuis_git("web", web, role="frontend"),
    ], tmp_path / "state")
    assert harness.executer("list_repos")["data"][0]["role"] == "backend"
    assert harness.executer("read_file", {"repo": "web", "path": "app.py"})["ok"]
    assert harness.executer("list_files", {"repo": "web", "path": "src"})["ok"] is True
    assert harness.executer("search_code", {"repo": "web", "text": "submit"})["ok"] is True
    assert harness.executer("count_matches", {"repo": "web", "text": "submit"})["data"]["total"] == 1
    assert harness.executer("read_file", {"repo": "web", "path": "../api/app.py"})["ok"] is False
    assert harness.executer("read_file", {"repo": "inconnu", "path": "app.py"})["ok"] is False


def test_record_claim_exige_et_conserve_une_preuve_localisee(tmp_path):
    depot = _depot(tmp_path)
    harness = ExplorationHarness([RepoSnapshot.depuis_git("api", depot)], tmp_path / "state")
    resultat = harness.executer("record_claim", {
        "subject": "api", "predicate": "EXPOSE", "object": "GET /x",
        "type": "API_USAGE", "evidence": [{"repo": "api", "path": "app.py", "start": 1, "end": 2}],
    })
    assert resultat["ok"] and resultat["data"]["total"] == 1
    claim = json.loads((tmp_path / "state" / "claims.json").read_text(encoding="utf-8"))[0]
    assert claim["predicat"] == "EXPOSE" and claim["preuves"][0]["chemin"] == "app.py"
    assert claim["preuves"][0]["hash"]
    refuse = harness.executer("record_claim", {
        "subject": "api", "predicate": "EXPOSE", "object": "GET /x (description)",
        "evidence": [{"repo": "api", "path": "app.py", "start": 1, "end": 1}],
    })
    assert refuse["ok"] is False


def test_record_claim_refuse_un_prefixe_de_route_non_prouve(tmp_path):
    depot = _depot(tmp_path)
    (depot / "routes.py").write_text(
        'bp = Blueprint("service", __name__, url_prefix="/v1")\n'
        '@bp.route("/parameters")\n'
        '@bp.route("/chat-messages/<uuid:task_id>/stop")\n',
        encoding="utf-8",
    )
    _git(depot, "add", ".")
    _git(depot, "commit", "-qm", "routes")
    harness = ExplorationHarness([RepoSnapshot.depuis_git("api", depot)], tmp_path / "state")

    valide = harness.executer("record_claim", {
        "subject": "service", "predicate": "EXPOSE", "object": "GET /v1/parameters",
        "evidence": [{"repo": "api", "path": "routes.py", "start": 1, "end": 2}],
    })
    assert valide["ok"] is True

    variable = harness.executer("record_claim", {
        "subject": "service", "predicate": "EXPOSE",
        "object": "POST /v1/chat-messages/{task_id}/stop",
        "evidence": [{"repo": "api", "path": "routes.py", "start": 1, "end": 1},
                     {"repo": "api", "path": "routes.py", "start": 3, "end": 3}],
    })
    assert variable["ok"] is True

    for objet in ("GET /v1/service_api/parameters", "GET /api/parameters"):
        refuse = harness.executer("record_claim", {
            "subject": "service", "predicate": "EXPOSE", "object": objet,
            "evidence": [{"repo": "api", "path": "routes.py", "start": 1, "end": 2}],
        })
        assert refuse["ok"] is False
        assert "préfixe de route non prouvé" in refuse["error"]


def test_un_final_avec_routes_sans_claims_est_relance(tmp_path):
    depot = _depot(tmp_path)
    harness = ExplorationHarness([RepoSnapshot.depuis_git("api", depot)], tmp_path / "state")
    requetes = []

    def adapter(requete):
        requetes.append(requete)
        if len(requetes) == 1:
            return {"final": "GET /x — app.py L1"}
        return {"final": "synthèse finale"}

    final = harness.run("objectif", adapter, max_steps=3)
    assert len(requetes) == 2
    assert "record_claims" in requetes[1]["messages"][-1]["content"]
    assert final.startswith("synthèse finale")
    assert "aucun Claim enregistré" in final


def test_finaliser_rapport_ajoute_le_nombre_de_claims(tmp_path):
    depot = _depot(tmp_path)
    harness = ExplorationHarness([RepoSnapshot.depuis_git("api", depot)], tmp_path / "state")
    assert harness.executer("record_claim", {
        "subject": "api", "predicate": "EXPOSE", "object": "GET /x",
        "evidence": [{"repo": "api", "path": "app.py", "start": 1, "end": 1}],
    })["ok"] is True

    def adapter(_requete):
        return {"final": "Aucun Claim n'a été enregistré."}

    final = harness.run("objectif", adapter, max_steps=1)
    assert "1 Claim enregistré" in final
    assert (tmp_path / "state" / "report.md").read_text(encoding="utf-8") == final


def test_record_claims_enregistre_un_lot(tmp_path):
    depot = _depot(tmp_path)
    harness = ExplorationHarness([RepoSnapshot.depuis_git("api", depot)], tmp_path / "state")
    resultat = harness.executer("record_claims", {"claims": [
        {"subject": "api", "predicate": "EXPOSE", "object": "GET /a",
         "evidence": [{"repo": "api", "path": "app.py", "start": 1, "end": 1}]},
        {"subject": "api", "predicate": "EXPOSE", "object": "GET /b",
         "evidence": [{"repo": "api", "path": "app.py", "start": 1, "end": 1}]},
    ]})
    assert resultat["ok"] and resultat["data"]["enregistres"] == 2


def test_record_claims_decoupe_les_gros_lots(tmp_path):
    depot = _depot(tmp_path)
    harness = ExplorationHarness([RepoSnapshot.depuis_git("api", depot)], tmp_path / "state")
    lot = [
        {"subject": "api", "predicate": "EXPOSE", "object": f"GET /r{i}",
         "evidence": [{"repo": "api", "path": "app.py", "start": 1, "end": 1}]}
        for i in range(31)
    ]
    resultat = harness.executer("record_claims", {"claims": lot})
    assert resultat["ok"] and resultat["data"]["enregistres"] == 31
    assert resultat["data"]["total"] == 31


def test_claims_depuis_rapport_lit_les_citations():
    from meridian.application.exploration_agent import claims_depuis_rapport
    rapport = "- GET /api/cities — backend/server.py L116-L118\n- POST /api/admin/login — backend/admin_routes.py L187-L188"
    claims = claims_depuis_rapport(rapport, "TBT", "trajeo")
    assert [c["object"] for c in claims] == ["GET /api/cities", "POST /api/admin/login"]
    assert claims[0]["evidence"][0] == {"repo": "trajeo", "path": "backend/server.py", "start": 116, "end": 118}


def test_outils_semantiques_injectes_sont_appelables(tmp_path):
    depot = _depot(tmp_path)
    harness = ExplorationHarness(
        [RepoSnapshot.depuis_git("api", depot)], tmp_path / "state",
        outils_semantiques={"code_routes": lambda args: {"routes": ["GET /x"]}},
        schemas_semantiques={"code_routes": {"repo": "api"}},
    )
    resultat = harness.executer("code_routes", {"repo": "api"})
    assert resultat["ok"] and resultat["data"]["routes"] == ["GET /x"]


def test_etat_hors_des_depots(tmp_path):
    depot = _depot(tmp_path)
    with pytest.raises(OutilsInvalides):
        ExplorationHarness([RepoSnapshot.depuis_git("api", depot)], depot / "state")


def test_la_boucle_reprend_un_checkpoint(tmp_path):
    depot = _depot(tmp_path)
    etat = tmp_path / "state"
    etat.mkdir()
    checkpoint = etat / "checkpoint.json"
    checkpoint.write_text(json.dumps([
        {"role": "system", "content": "system"},
        {"role": "user", "content": "objectif", "repos": ["api"]},
        {"role": "assistant", "content": {"tool_calls": [{"id": "x", "name": "list_repos", "arguments": {}}]}},
        {"role": "tool", "content": {"ok": True, "data": []}},
    ]), encoding="utf-8")
    vu = {}

    def adapter(requete):
        vu["messages"] = requete["messages"]
        return {"final": "reprise terminée"}

    harness = ExplorationHarness([RepoSnapshot.depuis_git("api", depot)], etat)
    final = harness.run("objectif", adapter, resume=True)
    assert final.startswith("reprise terminée")
    assert "Contrôle du harness : aucun Claim enregistré" in final
    assert len(vu["messages"]) == 5
    assert "Reprends l'enquête" in vu["messages"][-1]["content"]


def test_boucle_ecrit_rapport_et_trace(tmp_path):
    depot = _depot(tmp_path)
    adaptateur = tmp_path / "adapter.py"
    adaptateur.write_text(
        "import json,sys\n"
        "r=json.load(sys.stdin)\n"
        "print(json.dumps({'final':'# Rapport\\n\\nAPI inspectée.'}))\n",
        encoding="utf-8",
    )
    harness = ExplorationHarness([RepoSnapshot.depuis_git("api", depot)], tmp_path / "state")
    final = harness.run("Comprendre l'API", [sys.executable, str(adaptateur)])
    assert "API inspectée" in final
    assert (tmp_path / "state" / "report.md").read_text(encoding="utf-8").startswith("# Rapport")
    trace = json.loads((tmp_path / "state" / "trace.json").read_text(encoding="utf-8"))
    assert trace["final"] == final and trace["objective"] == "Comprendre l'API"
