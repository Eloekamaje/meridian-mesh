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


def _pack(tmp_path: Path, contenu: dict | None = None) -> Path:
    """Écrit un pack de données gelées JSON."""
    chemin = tmp_path / "data-pack.json"
    chemin.write_text(json.dumps(contenu or {"indicateur": "lenteur", "valeur": 42}),
                      encoding="utf-8")
    return chemin


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


def _valeur_option(commande: list[str], option: str) -> str | None:
    """Retourne la valeur d'une option de commande, si présente."""
    if option not in commande:
        return None
    return commande[commande.index(option) + 1]


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


def test_bras_par_defaut_alias_historiques_et_ordre():
    """Les bras sont canoniques, répétables et les anciennes options restent des alias."""
    args = rb.parse_args(["--scenario", "x.json"])
    assert args.arm == [rb.ARM_SKILL_MCP, rb.ARM_CHECKLIST_MCP, rb.ARM_DATA_ONLY]
    assert args.with_skill is None
    assert rb.arms_depuis_args(args) == [
        rb.ARM_SKILL_MCP, rb.ARM_CHECKLIST_MCP, rb.ARM_DATA_ONLY]

    assert rb.arms_depuis_args(
        rb.parse_args(["--scenario", "x.json", "--with-skill"])) == [rb.ARM_SKILL_MCP]
    assert rb.arms_depuis_args(
        rb.parse_args(["--scenario", "x.json", "--no-with-skill"])) == [rb.ARM_CHECKLIST_MCP]

    args = rb.parse_args([
        "--scenario", "x.json",
        "--arm", "with-skill",
        "--arm", "without-skill",
        "--arm", "data-only",
        "--arm", "skill+mcp",
    ])
    assert args.arm == [rb.ARM_SKILL_MCP, rb.ARM_CHECKLIST_MCP, rb.ARM_DATA_ONLY]
    assert rb.arms_depuis_args(args) == [
        rb.ARM_SKILL_MCP, rb.ARM_CHECKLIST_MCP, rb.ARM_DATA_ONLY]

    assert rb.conditions_depuis_option(None) == [(rb.ARM_SKILL_MCP, True)]
    assert rb.conditions_depuis_option(True) == [(rb.ARM_SKILL_MCP, True)]
    assert rb.conditions_depuis_option(False) == [(rb.ARM_CHECKLIST_MCP, False)]


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


def test_grade_run_accepte_le_champ_sections_et_les_exceptions():
    """Le schéma accepte ``sections`` et les exceptions de négation restent actives."""
    scenario = _normalise(
        expected_terms=["Décision"],
        expected_sections=None,
        sections=["Décision"],
        forbidden_terms=["action exécutée"],
        forbidden_terms_exceptions={"action exécutée": ["aucune"]},
    )
    assert scenario["expected_sections"] == ["Décision"]
    base = {
        "result": "Décision proposée. Aucune action exécutée.",
        "result_found": True,
        "timed_out": False,
        "is_error": False,
        "launch_error": "",
        "returncode": 0,
        "duration_seconds": 1.0,
        "cost_usd": 0.2,
    }
    assert all(critere["passed"] for critere in rb.grade_run(scenario, base))


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
        condition="skill+mcp",
        command=["claude", "-p", "question"],
        cwd=tmp_path,
        output_dir=sortie,
        run_index=1,
        timeout=0.01,
        arm="skill+mcp",
    )
    assert run["timed_out"] is True
    assert run["passed"] is False
    assert run["arm"] == "skill+mcp"
    assert fabrique.processus[0].tue is True
    assert "must_complete" in {critere["name"] for critere in run["criteria"]}
    assert (sortie / "run-01.jsonl").is_file()
    assert (sortie / "run-01.result.txt").is_file()
    bilan = json.loads((sortie / "run-01.json").read_text(encoding="utf-8"))
    assert bilan["timed_out"] is True
    assert bilan["returncode"] == -9


def test_main_deux_bras_cwd_sorties_et_resume(tmp_path, monkeypatch, capsys):
    """Le runner exécute deux bras, choisit les cwd et écrit les artefacts."""
    scenario, donnees = _scenario(tmp_path)
    fabrique = FausseFabriquePopen(_flux_complet())
    monkeypatch.setattr(rb.subprocess, "Popen", fabrique)
    sortie = tmp_path / "resultats"

    code = rb.main([
        "--scenario", str(scenario),
        "--runs", "1",
        "--arm", "skill+mcp",
        "--arm", "checklist+mcp",
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

    for arm in (rb.ARM_SKILL_MCP, rb.ARM_CHECKLIST_MCP):
        dossier = sortie / donnees["id"] / arm
        flux = dossier / "run-01.jsonl"
        resultat = dossier / "run-01.result.txt"
        bilan = dossier / "run-01.json"
        assert flux.is_file() and resultat.is_file() and bilan.is_file()
        assert resultat.read_text(encoding="utf-8").startswith("Le socle")
        contenu = json.loads(bilan.read_text(encoding="utf-8"))
        assert contenu["condition"] == arm
        assert contenu["arm"] == arm
        assert contenu["cost_usd"] == 0.12
        assert contenu["tool_calls"] == {"Skill": 1, "mcp__meridian__meridian_analyser": 1}
        assert contenu["passed"] is True

    resume = json.loads((sortie / "summary.json").read_text(encoding="utf-8"))
    assert resume["summary"]["runs"] == 2
    assert resume["summary"]["passed"] == 2
    assert resume["summary"]["by_arm"][rb.ARM_SKILL_MCP]["passed"] == 1
    assert resume["summary"]["by_arm"][rb.ARM_CHECKLIST_MCP]["passed"] == 1
    assert resume["comparison"]["reference"] == rb.ARM_SKILL_MCP
    assert (sortie / donnees["id"] / "summary.json").is_file()
    assert json.loads(capsys.readouterr().out.splitlines()[-2])["passed"] == 2


def test_checklist_prompt_generique_et_cwd_vide(tmp_path, monkeypatch):
    """Le bras checklist ajoute une checklist neutre, sans skill ni cwd du dépôt."""
    pack = _pack(tmp_path)
    scenario, _ = _scenario(
        tmp_path,
        skill="meridian-incident-ops",
        data_pack=str(pack),
    )
    fabrique = FausseFabriquePopen(_flux_complet())
    monkeypatch.setattr(rb.subprocess, "Popen", fabrique)
    sortie = tmp_path / "resultats"

    code = rb.main([
        "--scenario", str(scenario),
        "--runs", "1",
        "--arm", "checklist+mcp",
        "--output", str(sortie),
    ])

    assert code == 0
    assert len(fabrique.appels) == 1
    commande = fabrique.appels[0]["commande"]
    prompt = _valeur_option(commande, "-p")
    assert prompt == "Analyse l'incident paiements."
    assert "meridian-incident-ops" not in prompt
    assert _valeur_option(commande, "--append-system-prompt") == rb.load_checklist()
    assert "Faits" in rb.load_checklist() and "Abstention" in rb.load_checklist()
    assert "--mcp-config" in commande and "--strict-mcp-config" in commande
    assert "Skill" not in _valeur_option(commande, "--allowedTools").split(",")
    assert fabrique.repertoires[0][0] != str(rb.REPO_ROOT)
    assert fabrique.repertoires[0][2] == []


def test_data_only_sans_mcp_et_pack_gele(tmp_path, monkeypatch):
    """Le bras data-only supprime le MCP et préfixe le prompt par le pack gelé."""
    pack = _pack(tmp_path, {"indicateur": "lenteur", "valeur": 42})
    scenario, _ = _scenario(tmp_path, data_pack=str(pack))
    fabrique = FausseFabriquePopen(_flux_complet())
    monkeypatch.setattr(rb.subprocess, "Popen", fabrique)
    sortie = tmp_path / "resultats"

    code = rb.main([
        "--scenario", str(scenario),
        "--runs", "1",
        "--arm", "data-only",
        "--output", str(sortie),
    ])

    assert code == 0
    assert len(fabrique.appels) == 1
    commande = fabrique.appels[0]["commande"]
    prompt = _valeur_option(commande, "-p")
    assert "données gelées, aucun outil MCP" in prompt
    assert '"indicateur": "lenteur"' in prompt
    assert prompt.endswith("Analyse l'incident paiements.")
    assert "--mcp-config" not in commande
    assert "--strict-mcp-config" not in commande
    assert _valeur_option(commande, "--allowedTools") == "Read"
    assert _valeur_option(commande, "--max-budget-usd") == "1.25"
    assert fabrique.repertoires[0][0] != str(rb.REPO_ROOT)
    assert fabrique.repertoires[0][2] == []

    resume = json.loads((sortie / "summary.json").read_text(encoding="utf-8"))
    assert resume["config"]["mcp_config"]["source"] == "disabled"
    assert resume["summary"]["by_arm"][rb.ARM_DATA_ONLY]["passed"] == 1
    dossier = sortie / "scenario-test" / rb.ARM_DATA_ONLY
    assert (dossier / "run-01.jsonl").is_file()
    assert (dossier / "run-01.result.txt").is_file()


def test_data_pack_manquant_refuse_avant_claude(tmp_path, monkeypatch, capsys):
    """Un data-only sans pack valide échoue en code 2 sans appeler Claude."""
    def interdit(*args, **kwargs):
        raise AssertionError("Popen ne doit pas être appelé sans data pack")

    monkeypatch.setattr(rb.subprocess, "Popen", interdit)
    packs = [{}, {"data_pack": str(tmp_path / "absent.json")}]
    for surcharges in packs:
        scenario, _ = _scenario(tmp_path, **surcharges)
        code = rb.main([
            "--scenario", str(scenario),
            "--arm", "data-only",
            "--dry-run",
        ])
        assert code == 2
        assert "data_pack" in capsys.readouterr().err


def test_human_import_et_manquant(tmp_path, monkeypatch):
    """Le bras human importe les réponses disponibles et marque les manquantes."""
    def interdit(*args, **kwargs):
        raise AssertionError("Popen ne doit pas être appelé pour le bras human")

    monkeypatch.setattr(rb.subprocess, "Popen", interdit)
    scenario, _ = _scenario(tmp_path)
    humain = tmp_path / "humain"
    humain.mkdir()
    reponse = humain / "scenario-test-human.json"
    reponse.write_text(json.dumps({
        "answer": "Le socle contient des faits. Limites explicites.",
        "duration_seconds": 1.5,
        "cost_usd": 0.0,
    }), encoding="utf-8")
    sortie = tmp_path / "resultats"

    code = rb.main([
        "--scenario", str(scenario),
        "--arm", "human",
        "--human-dir", str(humain),
        "--output", str(sortie),
    ])

    assert code == 0
    dossier = sortie / "scenario-test" / rb.ARM_HUMAN
    bilan = json.loads((dossier / "run-01.json").read_text(encoding="utf-8"))
    assert bilan["missing"] is False
    assert bilan["passed"] is True
    assert bilan["result"] == "Le socle contient des faits. Limites explicites."
    assert bilan["human_source"] == str(reponse)
    assert (dossier / "run-01.human.json").is_file()
    assert (dossier / "run-01.result.txt").read_text(encoding="utf-8").startswith("Le socle")

    resume = json.loads((sortie / "summary.json").read_text(encoding="utf-8"))
    assert resume["summary"]["by_arm"][rb.ARM_HUMAN]["passed"] == 1
    assert resume["summary"]["by_arm"][rb.ARM_HUMAN]["missing"] == 0

    sortie_manquante = tmp_path / "resultats-manquants"
    code = rb.main([
        "--scenario", str(scenario),
        "--arm", "human",
        "--output", str(sortie_manquante),
    ])
    assert code == 0
    dossier = sortie_manquante / "scenario-test" / rb.ARM_HUMAN
    bilan = json.loads((dossier / "run-01.json").read_text(encoding="utf-8"))
    assert bilan["missing"] is True
    assert bilan["passed"] is False
    assert "human-dir" in bilan["missing_reason"]
    resume = json.loads((sortie_manquante / "summary.json").read_text(encoding="utf-8"))
    assert resume["summary"]["by_arm"][rb.ARM_HUMAN]["missing"] == 1
    assert resume["summary"]["by_arm"][rb.ARM_HUMAN]["passed"] == 0


def test_dry_run_par_bras_n_execute_rien_et_n_ecrit_rien(tmp_path, monkeypatch, capsys):
    """Le dry-run imprime la commande ou l'import attendu pour chaque bras."""
    pack = _pack(tmp_path)
    scenario, _ = _scenario(tmp_path, data_pack=str(pack))

    def interdit(*args, **kwargs):
        raise AssertionError("Popen ne doit pas être appelé en dry-run")

    monkeypatch.setattr(rb.subprocess, "Popen", interdit)
    sortie = tmp_path / "resultats"

    for arm in rb.ARMS:
        code = rb.main([
            "--scenario", str(scenario),
            "--runs", "1",
            "--arm", arm,
            "--dry-run",
            "--output", str(sortie),
            "--model", "modele-test",
        ])
        assert code == 0
        texte = capsys.readouterr().out
        assert f"Bras {arm}" in texte
        if arm == rb.ARM_HUMAN:
            assert "claude -p" not in texte
            assert "aucune commande Claude" in texte
        else:
            assert texte.count("claude -p") == 1
            assert "--model modele-test" in texte
        if arm == rb.ARM_CHECKLIST_MCP:
            assert "--append-system-prompt" in texte
        if arm == rb.ARM_DATA_ONLY:
            assert "--strict-mcp-config" not in texte
            assert "données gelées, aucun outil MCP" in texte
        if arm in (rb.ARM_SKILL_MCP, rb.ARM_CHECKLIST_MCP):
            assert "--strict-mcp-config" in texte
            assert "<generated-mcp-config>" in texte
    assert not sortie.exists()


def test_main_dry_run_avec_alias_historiques(tmp_path, monkeypatch, capsys):
    """Les anciennes options restent utilisables en dry-run, sans écriture."""
    scenario, _ = _scenario(tmp_path)

    def interdit(*args, **kwargs):
        raise AssertionError("Popen ne doit pas être appelé en dry-run")

    monkeypatch.setattr(rb.subprocess, "Popen", interdit)
    sortie = tmp_path / "resultats"

    code = rb.main([
        "--scenario", str(scenario),
        "--runs", "1",
        "--no-with-skill",
        "--dry-run",
        "--output", str(sortie),
    ])

    assert code == 0
    assert not sortie.exists()
    texte = capsys.readouterr().out
    assert texte.count("claude -p") == 1
    assert rb.ARM_CHECKLIST_MCP in texte
    assert "--append-system-prompt" in texte


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
    assert scenarios[0]["data_pack"] is None

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
