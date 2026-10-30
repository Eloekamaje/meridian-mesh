"""Tests du runner de benchmark Méridian, sans exécution réelle de Claude."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[3]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from plugin.meridian.evals import run_benchmark as rb  # noqa: E402


def _jsonl(*evenements: dict) -> str:
    """Sérialise des événements en flux JSONL."""
    return "".join(json.dumps(evenement, ensure_ascii=False) + "\n" for evenement in evenements)


def _resultat(texte: str = "Le socle contient des faits. Limites explicites.", cout: float = 0.12,
              duree_ms: int = 1200, tours: int = 3, erreur: bool = False,
              sous_type: str = "success") -> dict:
    """Construit un événement result proche de la CLI Claude."""
    return {
        "type": "result",
        "subtype": sous_type,
        "is_error": erreur,
        "result": texte,
        "total_cost_usd": cout,
        "duration_ms": duree_ms,
        "num_turns": tours,
    }


def _flux_complet(texte: str = "Le socle contient des faits. Limites explicites.") -> str:
    """Construit un flux JSONL avec outils, message partiel et résultat final."""
    return _jsonl(
        {"type": "system", "subtype": "init"},
        {"type": "stream_event", "event": {
            "type": "content_block_start",
            "content_block": {"type": "tool_use", "id": "tool-1", "name": "Skill"},
        }},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "tool-1", "name": "Skill"},
            {"type": "tool_use", "id": "tool-2", "name": "mcp__meridian__meridian_analyser"},
        ]}},
        _resultat(texte),
    )


def _scenario(tmp_path: Path, **surcharges) -> tuple[Path, dict]:
    """Écrit un scénario JSON minimal dans un fichier temporaire."""
    donnees = {
        "id": "scenario-test",
        "prompt": "Analyse l'incident paiements.",
        "mcp_tools": ["meridian_analyser"],
        "expected_terms": ["socle"],
        "forbidden_terms": ["chaîne causale"],
        "expected_sections": ["Limites"],
        "max_seconds": 30,
        "max_cost": 0.5,
        "must_complete": True,
    }
    donnees.update(surcharges)
    chemin = tmp_path / "scenario.json"
    chemin.write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
    return chemin, donnees


class FauxProcessus:
    """Faux Popen qui rejoue un flux JSONL et simule un timeout."""

    pid = None

    def __init__(self, stdout: str, stderr: str = "", returncode: int = 0,
                 timeout_premier: bool = False) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.timeout_premier = timeout_premier
        self.appels = 0
        self.tue = False

    def communicate(self, timeout=None):
        self.appels += 1
        if self.timeout_premier and self.appels == 1:
            raise subprocess.TimeoutExpired(cmd="claude", timeout=timeout)
        return self.stdout, self.stderr

    def kill(self) -> None:
        self.tue = True
        self.returncode = -9

    def poll(self):
        return self.returncode


class FausseFabriquePopen:
    """Fabrique de faux processus qui mémorise commandes et répertoires de travail."""

    def __init__(self, stdout: str, stderr: str = "", returncode: int = 0,
                 timeout_premier: bool = False) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.timeout_premier = timeout_premier
        self.appels: list[dict] = []
        self.processus: list[FauxProcessus] = []
        self.repertoires: list[tuple[str, bool, list[str]]] = []
        self.configs_existants: list[bool] = []

    def __call__(self, commande, **options):
        cwd = Path(options["cwd"])
        contenu = [element.name for element in cwd.iterdir()] if cwd.is_dir() else []
        self.repertoires.append((str(cwd), cwd.is_dir(), contenu))
        if "--mcp-config" in commande:
            index = commande.index("--mcp-config") + 1
            self.configs_existants.append(Path(commande[index]).is_file())
        else:
            self.configs_existants.append(False)
        self.appels.append({"commande": commande, "options": options})
        processus = FauxProcessus(
            self.stdout, self.stderr, self.returncode, self.timeout_premier)
        self.processus.append(processus)
        return processus


def _normalise(**surcharges) -> dict:
    """Normalise un scénario en mémoire."""
    donnees = {
        "id": "scenario-test",
        "prompt": "Analyse l'incident paiements.",
        "expected_terms": ["socle"],
        "forbidden_terms": ["chaîne causale"],
        "expected_sections": ["Limites"],
        "max_seconds": 2.0,
        "max_cost": 0.5,
        "must_complete": True,
    }
    donnees.update(surcharges)
    return rb.normalize_scenario(donnees, "scenario-test", None, Path("scenario.json"))


def test_construction_configuration_mcp_et_commandes():
    """La configuration MCP générée et la commande respectent le contrat."""
    configuration = rb.build_mcp_config(Path("/depot"), "http://api", "demo", "ops")
    serveur = configuration["mcpServers"]["meridian"]
    assert serveur["command"] == sys.executable
    assert serveur["args"] == ["-m", "plugin.meridian.mcp.server"]
    assert serveur["env"] == {
        "PYTHONPATH": "/depot",
        "MERIDIAN_API_URL": "http://api",
        "MERIDIAN_TENANT": "demo",
        "MERIDIAN_PERSONA": "ops",
    }

    scenario = _normalise(mcp_tools=["meridian_analyser", "mcp__meridian__meridian_impact"])
    args = rb.parse_args(["--scenario", "x.json", "--model", "modele-test"])
    commande = rb.build_command(scenario, "/tmp/mcp.json", args)
    assert commande[:3] == ["claude", "-p", "Analyse l'incident paiements."]
    assert commande[commande.index("--allowedTools") + 1] == (
        "Skill,Read,mcp__meridian__meridian_analyser,mcp__meridian__meridian_impact")
    assert commande[commande.index("--model") + 1] == "modele-test"
    assert "--strict-mcp-config" in commande
    assert "--include-partial-messages" in commande
    assert commande[commande.index("--max-budget-usd") + 1] == "1.25"


def test_conditions_par_defaut_et_options_exclusives():
    """Les conditions par défaut couvrent les deux modes, les options les restreignent."""
    assert rb.conditions_depuis_option(None) == [("with-skill", True), ("without-skill", False)]
    assert rb.conditions_depuis_option(True) == [("with-skill", True)]
    assert rb.conditions_depuis_option(False) == [("without-skill", False)]
    assert rb.parse_args(["--scenario", "x.json", "--with-skill"]).with_skill is True
    assert rb.parse_args(["--scenario", "x.json", "--no-with-skill"]).with_skill is False
    assert rb.parse_args(["--scenario", "x.json"]).with_skill is None


def test_parse_stream_jsonl_extrait_resultat_cout_outils_et_erreurs():
    """Le parseur déduplique les outils, lit le coût et collecte les erreurs."""
    analyse = rb.parse_stream_jsonl(_flux_complet())
    assert analyse["result_found"] is True
    assert analyse["result"] == "Le socle contient des faits. Limites explicites."
    assert analyse["cost_usd"] == 0.12
    assert analyse["duration_seconds"] == 1.2
    assert analyse["num_turns"] == 3
    assert analyse["tool_calls"] == {"Skill": 1, "mcp__meridian__meridian_analyser": 1}
    assert analyse["tool_sequence"] == ["Skill", "mcp__meridian__meridian_analyser"]
    assert analyse["errors"] == []

    flux_erreur = "ligne invalide\n" + _jsonl(
        {"type": "result", "subtype": "error_max_budget_usd", "is_error": True,
         "result": "budget dépassé"},
    )
    erreur = rb.parse_stream_jsonl(flux_erreur)
    assert erreur["is_error"] is True
    assert "budget dépassé" in erreur["errors"]
    assert erreur["parse_errors"]


def test_grade_run_criteres_objectifs_passent_puis_echouent():
    """Les termes attendus/interdits et les seuils sont évalués objectivement."""
    scenario = _normalise()
    run = {
        "result": "Le socle contient des faits. Limites explicites.",
        "result_found": True,
        "timed_out": False,
        "is_error": False,
        "launch_error": "",
        "returncode": 0,
        "duration_seconds": 1.0,
        "cost_usd": 0.2,
    }
    criteres = rb.grade_run(scenario, run)
    assert all(critere["passed"] for critere in criteres)

    run["result"] += " Une chaîne causale est affirmée."
    run["duration_seconds"] = 3.0
    run["cost_usd"] = 0.9
    run["timed_out"] = True
    criteres = rb.grade_run(scenario, run)
    echecs = {critere["name"] for critere in criteres if not critere["passed"]}
    assert echecs == {"forbidden_term:chaîne causale", "max_seconds", "max_cost", "must_complete"}


def test_run_once_timeout_tue_le_processus_et_sauvegarde(tmp_path, monkeypatch):
    """Un timeout est consigné, le processus est tué et le runner ne plante pas."""
    fabrique = FausseFabriquePopen(
        _jsonl({"type": "assistant", "message": {"content": [{"type": "text", "text": "partiel"}]}}),
        stderr="dépassement",
        timeout_premier=True,
    )
    monkeypatch.setattr(rb.subprocess, "Popen", fabrique)
    sortie = tmp_path / "sortie"
    run = rb.run_once(
        scenario=_normalise(),
        condition="with-skill",
        command=["claude", "-p", "question"],
        cwd=tmp_path,
        output_dir=sortie,
        run_index=1,
        timeout=0.01,
    )
    assert run["timed_out"] is True
    assert run["passed"] is False
    assert fabrique.processus[0].tue is True
    assert "must_complete" in {critere["name"] for critere in run["criteria"]}
    assert (sortie / "run-01.jsonl").is_file()
    assert (sortie / "run-01.result.txt").is_file()
    bilan = json.loads((sortie / "run-01.json").read_text(encoding="utf-8"))
    assert bilan["timed_out"] is True
    assert bilan["returncode"] == -9


def test_main_avec_et_sans_skill_cwd_sorties_et_resume(tmp_path, monkeypatch, capsys):
    """Le runner exécute les deux conditions, choisit les cwd et écrit les artefacts."""
    scenario, donnees = _scenario(tmp_path)
    fabrique = FausseFabriquePopen(_flux_complet())
    monkeypatch.setattr(rb.subprocess, "Popen", fabrique)
    sortie = tmp_path / "resultats"

    code = rb.main([
        "--scenario", str(scenario),
        "--runs", "1",
        "--output", str(sortie),
        "--api-url", "http://test/api",
        "--tenant", "demo",
        "--persona", "ops",
    ])

    assert code == 0
    assert len(fabrique.appels) == 2
    assert fabrique.configs_existants == [True, True]
    assert fabrique.repertoires[0][0] == str(rb.REPO_ROOT)
    assert fabrique.repertoires[0][1] is True
    assert fabrique.repertoires[1][0] != str(rb.REPO_ROOT)
    assert fabrique.repertoires[1][1] is True
    assert fabrique.repertoires[1][2] == []

    for condition in ("with-skill", "without-skill"):
        dossier = sortie / donnees["id"] / condition
        flux = dossier / "run-01.jsonl"
        resultat = dossier / "run-01.result.txt"
        bilan = dossier / "run-01.json"
        assert flux.is_file() and resultat.is_file() and bilan.is_file()
        assert resultat.read_text(encoding="utf-8").startswith("Le socle")
        contenu = json.loads(bilan.read_text(encoding="utf-8"))
        assert contenu["condition"] == condition
        assert contenu["cost_usd"] == 0.12
        assert contenu["tool_calls"] == {"Skill": 1, "mcp__meridian__meridian_analyser": 1}
        assert contenu["passed"] is True

    resume = json.loads((sortie / "summary.json").read_text(encoding="utf-8"))
    assert resume["summary"]["runs"] == 2
    assert resume["summary"]["passed"] == 2
    assert resume["summary"]["by_condition"]["with-skill"]["passed"] == 1
    assert resume["summary"]["by_condition"]["without-skill"]["passed"] == 1
    assert (sortie / donnees["id"] / "summary.json").is_file()
    assert json.loads(capsys.readouterr().out.splitlines()[-2])["passed"] == 2


def test_main_dry_run_n_execute_rien_et_n_ecrit_rien(tmp_path, monkeypatch, capsys):
    """Le dry-run imprime les commandes sans créer de résultats ni appeler Popen."""
    scenario, _ = _scenario(tmp_path)

    def interdit(*args, **kwargs):
        raise AssertionError("Popen ne doit pas être appelé en dry-run")

    monkeypatch.setattr(rb.subprocess, "Popen", interdit)
    sortie = tmp_path / "resultats"

    code = rb.main([
        "--scenario", str(scenario),
        "--runs", "1",
        "--dry-run",
        "--output", str(sortie),
        "--model", "modele-test",
    ])

    assert code == 0
    assert not sortie.exists()
    texte = capsys.readouterr().out
    assert texte.count("claude -p") == 2
    assert "with-skill" in texte and "without-skill" in texte
    assert "--strict-mcp-config" in texte
    assert "--model modele-test" in texte
    assert "<generated-mcp-config>" in texte


def test_load_scenarios_accepte_liste_et_valide_prompt(tmp_path):
    """Le chargement accepte une liste, normalise les slugs et refuse un prompt vide."""
    fichier = tmp_path / "scenarios.json"
    fichier.write_text(json.dumps([
        {"id": "un", "prompt": "Question un"},
        {"id": "un", "prompt": "Question deux", "mcp_tools": []},
    ]), encoding="utf-8")
    scenarios = rb.load_scenarios([fichier])
    assert [scenario["slug"] for scenario in scenarios] == ["un", "un-2"]
    assert scenarios[1]["mcp_tools"] == []

    invalide = tmp_path / "invalide.json"
    invalide.write_text(json.dumps({"prompt": "   "}), encoding="utf-8")
    try:
        rb.load_scenarios([invalide])
    except rb.ScenarioError as exc:
        assert "prompt" in str(exc)
    else:
        raise AssertionError("un scénario sans prompt doit être refusé")


def test_un_terme_interdit_nie_est_accepte_et_non_nie_est_refuse():
    """Les exceptions de négation évitent de pénaliser « aucune action exécutée »."""
    scenario = _normalise(
        forbidden_terms=["action exécutée", "causalité confirmée"],
        forbidden_terms_exceptions={
            "action exécutée": ["aucune", "pas"],
            "causalité confirmée": ["non"],
        },
    )
    base = {
        "result_found": True, "timed_out": False, "is_error": False,
        "launch_error": "", "returncode": 0, "duration_seconds": 1.0,
        "cost_usd": 0.2,
    }
    nie = rb.grade_run(scenario, {**base, "result": "Aucune action exécutée ; causalité confirmée : non."})
    assert all(c["passed"] for c in nie if c["name"].startswith("forbidden_term:"))

    affirme = rb.grade_run(scenario, {**base, "result": "L'action exécutée a confirmé la causalité confirmée."})
    assert any(not c["passed"] for c in affirme if c["name"].startswith("forbidden_term:"))
