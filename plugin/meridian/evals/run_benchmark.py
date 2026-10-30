"""Runner reproductible du benchmark avec/sans skill Méridian.

Le runner lance la CLI Claude Code sur des scénarios JSON, compare une condition
avec skill (racine du dépôt) et une condition sans skill (répertoire vide), puis
note uniquement des critères objectifs déclarés dans le scénario. Aucune note
subjective n'est produite.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUNS = 3
DEFAULT_MAX_BUDGET_USD = 1.25
DEFAULT_TIMEOUT = 180.0
DEFAULT_API_URL = "http://127.0.0.1:8001/api"
DEFAULT_TENANT = "local"
DEFAULT_PERSONA = "architecte"
DEFAULT_MCP_TOOLS = (
    "meridian_analyser",
    "meridian_portefeuille",
    "meridian_impact",
    "meridian_claims",
    "meridian_learnings",
    "meridian_valeurs",
    "meridian_valeur_resume",
    "meridian_profils",
    "meridian_composition",
    "meridian_attention",
)


class ScenarioError(ValueError):
    """Scénario absent, illisible ou invalide."""


class BenchmarkError(RuntimeError):
    """Erreur d'infrastructure empêchant le benchmark de démarrer."""


def _positive_int(value: str) -> int:
    """Convertit une chaîne en entier strictement positif."""
    try:
        resultat = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("valeur entière attendue") from exc
    if resultat < 1:
        raise argparse.ArgumentTypeError("la valeur doit être supérieure ou égale à 1")
    return resultat


def _positive_float(value: str) -> float:
    """Convertit une chaîne en flottant strictement positif."""
    try:
        resultat = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("valeur numérique attendue") from exc
    if resultat <= 0:
        raise argparse.ArgumentTypeError("la valeur doit être supérieure à 0")
    return resultat


def default_output_dir() -> Path:
    """Retourne le répertoire de sortie horodaté par défaut."""
    horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path(tempfile.gettempdir()) / f"meridian-benchmark-{horodatage}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Analyse les arguments de la ligne de commande."""
    parser = argparse.ArgumentParser(
        description="Benchmark reproductible des skills Méridian avec la CLI Claude Code.",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        required=True,
        help="Chemin d'un fichier de scénario JSON (option répétable).",
    )
    parser.add_argument("--runs", type=_positive_int, default=DEFAULT_RUNS,
                        help=f"Nombre de runs par scénario et condition (défaut : {DEFAULT_RUNS}).")
    conditions = parser.add_mutually_exclusive_group()
    conditions.add_argument("--with-skill", dest="with_skill", action="store_true",
                            help="Exécuter uniquement la condition avec skill.")
    conditions.add_argument("--no-with-skill", dest="with_skill", action="store_false",
                            help="Exécuter uniquement la condition sans skill.")
    parser.set_defaults(with_skill=None)
    parser.add_argument("--mcp-config", type=Path,
                        help="Fichier MCP existant ; sinon une configuration temporaire est générée.")
    parser.add_argument("--model", help="Modèle transmis à la CLI Claude Code.")
    parser.add_argument("--max-budget-usd", type=_positive_float, default=DEFAULT_MAX_BUDGET_USD,
                        help=f"Budget maximal par run en USD (défaut : {DEFAULT_MAX_BUDGET_USD}).")
    parser.add_argument("--timeout", type=_positive_float, default=DEFAULT_TIMEOUT,
                        help=f"Timeout par run en secondes (défaut : {DEFAULT_TIMEOUT:.0f}).")
    parser.add_argument("--output", type=Path,
                        help="Répertoire de résultats (défaut : /tmp/meridian-benchmark-<timestamp>).")
    parser.add_argument("--api-url", default=os.environ.get("MERIDIAN_API_URL", DEFAULT_API_URL),
                        help="URL de l'API Méridian pour le MCP généré.")
    parser.add_argument("--tenant", default=os.environ.get("MERIDIAN_TENANT", DEFAULT_TENANT),
                        help="Tenant Méridian pour le MCP généré.")
    parser.add_argument("--persona", default=os.environ.get("MERIDIAN_PERSONA", DEFAULT_PERSONA),
                        help="Persona Méridian pour le MCP généré.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Afficher les commandes sans exécuter ni écrire de résultats.")
    return parser.parse_args(argv)


def _string_list(value: Any, champ: str) -> list[str]:
    """Normalise une valeur JSON en liste de chaînes non vides."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        resultat = []
        for element in value:
            if not isinstance(element, str) or not element.strip():
                raise ScenarioError(f"le champ {champ} doit contenir des chaînes non vides")
            resultat.append(element.strip())
        return resultat
    raise ScenarioError(f"le champ {champ} doit être une chaîne ou une liste de chaînes")


def _exceptions(value: Any) -> dict[str, list[str]]:
    """Normalise les exceptions de termes interdits, par exemple ``non`` avant ``causalité confirmée``."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ScenarioError("forbidden_terms_exceptions doit être un objet")
    resultat = {}
    for terme, negations in value.items():
        if not isinstance(terme, str) or not terme.strip():
            raise ScenarioError("clé de forbidden_terms_exceptions invalide")
        resultat[terme.strip()] = [
            negation.lower() for negation in _string_list(negations, "forbidden_terms_exceptions")
        ]
    return resultat


def _optional_float(value: Any, champ: str) -> float | None:
    """Normalise un seuil numérique optionnel."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ScenarioError(f"le champ {champ} doit être un nombre")
    try:
        resultat = float(value)
    except (TypeError, ValueError) as exc:
        raise ScenarioError(f"le champ {champ} doit être un nombre") from exc
    if resultat < 0:
        raise ScenarioError(f"le champ {champ} ne peut pas être négatif")
    return resultat


def _slugify(value: str) -> str:
    """Transforme un identifiant en nom de dossier sûr."""
    resultat = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-.")
    return resultat or "scenario"


def normalize_scenario(raw: Any, fallback_id: str, index: int | None, source: Path) -> dict[str, Any]:
    """Valide et normalise un scénario JSON."""
    if not isinstance(raw, dict):
        raise ScenarioError(f"{source} : chaque scénario doit être un objet JSON")
    prompt = raw.get("prompt") or raw.get("question")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ScenarioError(f"{source} : le champ prompt est obligatoire")
    identifiant = raw.get("id") or raw.get("name")
    if identifiant is None:
        identifiant = fallback_id if index is None else f"{fallback_id}-{index}"
    elif not isinstance(identifiant, (str, int)):
        raise ScenarioError(f"{source} : le champ id doit être une chaîne ou un entier")

    if "mcp_tools" in raw or "tools" in raw:
        mcp_tools = _string_list(raw.get("mcp_tools", raw.get("tools")), "mcp_tools")
    else:
        mcp_tools = list(DEFAULT_MCP_TOOLS)

    scenario = {
        "id": str(identifiant),
        "slug": _slugify(str(identifiant)),
        "source": str(source),
        "prompt": prompt.strip(),
        "mcp_tools": mcp_tools,
        "expected_terms": _string_list(raw.get("expected_terms"), "expected_terms"),
        "forbidden_terms": _string_list(raw.get("forbidden_terms"), "forbidden_terms"),
        "forbidden_terms_exceptions": _exceptions(raw.get("forbidden_terms_exceptions")),
        "expected_sections": _string_list(raw.get("expected_sections"), "expected_sections"),
        "max_seconds": _optional_float(raw.get("max_seconds"), "max_seconds"),
        "max_cost": _optional_float(raw.get("max_cost"), "max_cost"),
        "must_complete": bool(raw.get("must_complete", True)),
    }
    if isinstance(raw.get("skill"), str) and raw["skill"].strip():
        scenario["skill"] = raw["skill"].strip()
    return scenario


def load_scenarios(paths: Iterable[str | Path]) -> list[dict[str, Any]]:
    """Charge un ou plusieurs fichiers de scénarios JSON et déduplique les slugs."""
    scenarios: list[dict[str, Any]] = []
    for chemin_brut in paths:
        chemin = Path(chemin_brut).expanduser()
        try:
            contenu = chemin.read_text(encoding="utf-8")
        except OSError as exc:
            raise ScenarioError(f"lecture impossible de {chemin} : {exc}") from exc
        try:
            donnees = json.loads(contenu)
        except json.JSONDecodeError as exc:
            raise ScenarioError(f"JSON invalide dans {chemin} : {exc}") from exc
        if isinstance(donnees, dict) and isinstance(donnees.get("scenarios"), list):
            elements = donnees["scenarios"]
            multiple = True
        elif isinstance(donnees, list):
            elements = donnees
            multiple = True
        else:
            elements = [donnees]
            multiple = False
        if not elements:
            raise ScenarioError(f"{chemin} ne contient aucun scénario")
        for position, element in enumerate(elements, 1):
            index = position if multiple else None
            scenarios.append(normalize_scenario(element, chemin.stem, index, chemin))

    utilises: set[str] = set()
    for scenario in scenarios:
        base = scenario["slug"]
        slug = base
        suffixe = 2
        while slug in utilises:
            slug = f"{base}-{suffixe}"
            suffixe += 1
        scenario["slug"] = slug
        utilises.add(slug)
    return scenarios


def conditions_depuis_option(with_skill: bool | None) -> list[tuple[str, bool]]:
    """Retourne les conditions à exécuter selon l'option CLI."""
    if with_skill is None:
        return [("with-skill", True), ("without-skill", False)]
    return [("with-skill", True)] if with_skill else [("without-skill", False)]


def build_mcp_config(repo_root: Path, api_url: str, tenant: str, persona: str) -> dict[str, Any]:
    """Construit la configuration MCP temporaire du serveur Méridian."""
    return {
        "mcpServers": {
            "meridian": {
                "command": sys.executable,
                "args": ["-m", "plugin.meridian.mcp.server"],
                "env": {
                    "PYTHONPATH": str(repo_root),
                    "MERIDIAN_API_URL": api_url,
                    "MERIDIAN_TENANT": tenant,
                    "MERIDIAN_PERSONA": persona,
                },
            }
        }
    }


def _write_json(chemin: Path, donnees: Any) -> None:
    """Écrit un objet JSON UTF-8 lisible."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(donnees, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare_mcp_config(args: argparse.Namespace, repo_root: Path) -> tuple[str, Path | None, dict[str, Any]]:
    """Prépare le fichier MCP et retourne son chemin, son dossier temporaire et sa trace."""
    if args.mcp_config is not None:
        chemin = Path(args.mcp_config).expanduser().resolve()
        if not chemin.is_file():
            raise BenchmarkError(f"configuration MCP introuvable : {chemin}")
        return str(chemin), None, {"source": "provided", "path": str(chemin)}

    configuration = build_mcp_config(repo_root, args.api_url, args.tenant, args.persona)
    trace = {"source": "generated", "config": configuration}
    if args.dry_run:
        return "<generated-mcp-config>", None, trace
    dossier = Path(tempfile.mkdtemp(prefix="meridian-benchmark-mcp-"))
    chemin = dossier / "mcp.json"
    _write_json(chemin, configuration)
    return str(chemin), dossier, trace


def _normalize_tool_name(nom: str) -> str:
    """Ajoute le préfixe MCP Méridian à un nom d'outil court."""
    nom = nom.strip()
    if nom.startswith("mcp__"):
        return nom
    if nom.startswith("meridian__"):
        return f"mcp__{nom}"
    return f"mcp__meridian__{nom}"


def allowed_tools(scenario: dict[str, Any]) -> list[str]:
    """Construit la liste déterministe des outils autorisés pour un scénario."""
    outils = ["Skill", "Read"]
    for outil in scenario["mcp_tools"]:
        normalise = _normalize_tool_name(outil)
        if normalise not in outils:
            outils.append(normalise)
    return outils


def build_command(scenario: dict[str, Any], mcp_config: str, args: argparse.Namespace,
                  claude_bin: str = "claude") -> list[str]:
    """Construit la commande Claude Code d'un run."""
    commande = [
        claude_bin,
        "-p",
        scenario["prompt"],
        "--mcp-config",
        mcp_config,
        "--strict-mcp-config",
        "--allowedTools",
        ",".join(allowed_tools(scenario)),
        "--max-budget-usd",
        str(args.max_budget_usd),
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
    ]
    if args.model:
        commande.extend(["--model", args.model])
    return commande


def _to_text(value: Any) -> str:
    """Convertit une sortie de processus en texte UTF-8 sûr."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _as_text(value: Any) -> str:
    """Rend une valeur JSON textuelle sans jamais lever d'exception."""
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return _to_text(value)


def _to_float(value: Any) -> float | None:
    """Convertit une valeur JSON en flottant si possible."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    """Convertit une valeur JSON en entier si possible."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _tool_uses(event: dict[str, Any]) -> Iterable[dict[str, Any]]:
    """Extrait les blocs tool_use d'un événement stream-json."""
    if event.get("type") == "tool_use" and isinstance(event.get("name"), str):
        yield event
    message = event.get("message")
    if isinstance(message, dict):
        contenu = message.get("content")
        if isinstance(contenu, list):
            for bloc in contenu:
                if isinstance(bloc, dict) and bloc.get("type") == "tool_use":
                    yield bloc
    contenu = event.get("content")
    if isinstance(contenu, list):
        for bloc in contenu:
            if isinstance(bloc, dict) and bloc.get("type") == "tool_use":
                yield bloc
    flux = event.get("event")
    if isinstance(flux, dict):
        bloc = flux.get("content_block")
        if isinstance(bloc, dict) and bloc.get("type") == "tool_use":
            yield bloc


def _outil_suivi(nom: str) -> bool:
    """Indique si un outil entre dans le périmètre du benchmark."""
    return nom == "Skill" or nom.startswith("mcp__meridian__")


def parse_stream_jsonl(raw: str, stderr: str = "") -> dict[str, Any]:
    """Analyse le flux JSONL de Claude Code et extrait résultat, coût et outils."""
    etat: dict[str, Any] = {
        "events": 0,
        "result_found": False,
        "result": "",
        "is_error": False,
        "cost_usd": None,
        "duration_seconds": None,
        "num_turns": None,
        "tool_calls": {},
        "tool_sequence": [],
        "errors": [],
        "parse_errors": [],
        "stderr": stderr,
    }
    outils_vus: set[str] = set()
    for numero, ligne in enumerate(raw.splitlines(), 1):
        ligne = ligne.strip()
        if not ligne:
            continue
        try:
            evenement = json.loads(ligne)
        except json.JSONDecodeError as exc:
            etat["parse_errors"].append(f"ligne {numero} : {exc.msg}")
            continue
        if not isinstance(evenement, dict):
            etat["parse_errors"].append(f"ligne {numero} : objet JSON attendu")
            continue
        etat["events"] += 1

        for bloc in _tool_uses(evenement):
            nom = bloc.get("name")
            if not isinstance(nom, str) or not _outil_suivi(nom):
                continue
            identifiant = bloc.get("id")
            if isinstance(identifiant, str) and identifiant:
                if identifiant in outils_vus:
                    continue
                outils_vus.add(identifiant)
            etat["tool_calls"][nom] = etat["tool_calls"].get(nom, 0) + 1
            etat["tool_sequence"].append(nom)

        type_evenement = evenement.get("type")
        if type_evenement == "result":
            etat["result_found"] = True
            etat["result"] = _as_text(evenement.get("result"))
            sous_type = str(evenement.get("subtype", ""))
            etat["is_error"] = bool(evenement.get("is_error")) or sous_type.startswith("error")
            cout = _to_float(evenement.get("total_cost_usd"))
            if cout is None:
                cout = _to_float(evenement.get("cost_usd"))
            if cout is not None:
                etat["cost_usd"] = cout
            duree_ms = _to_float(evenement.get("duration_ms"))
            duree_s = _to_float(evenement.get("duration_seconds"))
            duree_api_ms = _to_float(evenement.get("duration_api_ms"))
            if duree_ms is not None:
                etat["duration_seconds"] = duree_ms / 1000.0
            elif duree_s is not None:
                etat["duration_seconds"] = duree_s
            elif duree_api_ms is not None:
                etat["duration_seconds"] = duree_api_ms / 1000.0
            tours = _to_int(evenement.get("num_turns"))
            if tours is not None:
                etat["num_turns"] = tours
            if etat["is_error"]:
                message = evenement.get("error") or etat["result"] or sous_type
                if message:
                    etat["errors"].append(_as_text(message))
        elif type_evenement == "error":
            message = evenement.get("error") or evenement.get("message") or "erreur inconnue"
            etat["errors"].append(_as_text(message))
        elif type_evenement == "system" and evenement.get("subtype") == "error":
            message = evenement.get("message") or evenement.get("error") or "erreur système"
            etat["errors"].append(_as_text(message))

    etat["errors"] = list(dict.fromkeys(etat["errors"]))
    return etat


def _normaliser_texte(texte: str) -> str:
    """Normalise accents, casse et séparateurs pour comparer des libellés de contrat."""
    decompose = unicodedata.normalize("NFKD", str(texte or ""))
    sans_accents = "".join(c for c in decompose if not unicodedata.combining(c))
    return " ".join(sans_accents.casefold().replace("_", " ").replace("-", " ").split())


def _contains(texte: str, terme: str) -> bool:
    """Teste la présence insensible à la casse, aux accents et aux séparateurs."""
    return _normaliser_texte(terme) in _normaliser_texte(texte)


def _terme_interdit_present(texte: str, terme: str, exceptions) -> bool:
    """Vrai si le terme apparaît sans être immédiatement nié par une exception."""
    if not _contains(texte, terme):
        return False
    exceptions = [_normaliser_texte(valeur) for valeur in (exceptions or [])]
    if not exceptions:
        return True
    bas = _normaliser_texte(texte)
    terme_bas = _normaliser_texte(terme)
    debut = 0
    while True:
        position = bas.find(terme_bas, debut)
        if position < 0:
            return False
        avant = bas[max(0, position - 48):position]
        apres = bas[position + len(terme_bas):position + len(terme_bas) + 24]
        if not any(negation in avant or negation in apres for negation in exceptions):
            return True
        debut = position + len(terme_bas)


def grade_run(scenario: dict[str, Any], run: dict[str, Any]) -> list[dict[str, Any]]:
    """Évalue les critères objectifs d'un run sans notation subjective."""
    criteres: list[dict[str, Any]] = []
    texte = run.get("result") or ""

    for terme in scenario["expected_terms"]:
        present = _contains(texte, terme)
        criteres.append({
            "name": f"expected_term:{terme}",
            "passed": present,
            "detail": "terme présent" if present else "terme absent du résultat final",
        })
    for terme in scenario["expected_sections"]:
        present = _contains(texte, terme)
        criteres.append({
            "name": f"expected_section:{terme}",
            "passed": present,
            "detail": "section présente" if present else "section absente du résultat final",
        })
    for terme in scenario["forbidden_terms"]:
        present = _terme_interdit_present(
            texte, terme, scenario.get("forbidden_terms_exceptions", {}).get(terme, ()))
        criteres.append({
            "name": f"forbidden_term:{terme}",
            "passed": not present,
            "detail": "terme interdit absent" if not present else "terme interdit présent sans négation",
        })

    if scenario["max_seconds"] is not None:
        duree = run.get("duration_seconds")
        respecte = duree is not None and duree <= scenario["max_seconds"]
        criteres.append({
            "name": "max_seconds",
            "passed": respecte,
            "detail": f"{duree} s pour un maximum de {scenario['max_seconds']} s",
        })
    if scenario["max_cost"] is not None:
        cout = run.get("cost_usd")
        respecte = cout is not None and cout <= scenario["max_cost"]
        criteres.append({
            "name": "max_cost",
            "passed": respecte,
            "detail": f"{cout} USD pour un maximum de {scenario['max_cost']} USD",
        })

    if scenario["must_complete"]:
        complet = bool(
            run.get("result_found")
            and not run.get("timed_out")
            and not run.get("is_error")
            and not run.get("launch_error")
            and run.get("returncode") in (0, None)
        )
        criteres.append({
            "name": "must_complete",
            "passed": complet,
            "detail": "résultat final complet" if complet else "run incomplet ou en erreur",
        })
    return criteres


def _kill_process(proc: subprocess.Popen) -> None:
    """Tue un processus et son groupe sans faire échouer le runner."""
    pid = getattr(proc, "pid", None)
    if os.name == "posix" and isinstance(pid, int) and pid > 0:
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        proc.kill()
    except Exception:
        pass


def run_once(scenario: dict[str, Any], condition: str, command: list[str], cwd: Path,
             output_dir: Path, run_index: int, timeout: float,
             save: bool = True) -> dict[str, Any]:
    """Exécute un run, sauvegarde ses artefacts et retourne son bilan."""
    debut = time.monotonic()
    stdout = ""
    stderr = ""
    timed_out = False
    launch_error = ""
    returncode: int | None = None
    proc: subprocess.Popen | None = None
    try:
        proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=(os.name == "posix"),
        )
    except (OSError, ValueError) as exc:
        launch_error = f"{type(exc).__name__} : {exc}"

    if proc is not None:
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            sortie_expiree = _to_text(exc.stdout)
            erreur_expiree = _to_text(exc.stderr)
            _kill_process(proc)
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired as exc2:
                stdout = sortie_expiree + _to_text(exc2.stdout)
                stderr = erreur_expiree + _to_text(exc2.stderr)
            except Exception as exc:
                launch_error = f"{type(exc).__name__} : {exc}"
            else:
                stdout = stdout or sortie_expiree
                stderr = stderr or erreur_expiree
        except Exception as exc:
            launch_error = f"{type(exc).__name__} : {exc}"
            _kill_process(proc)
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except Exception:
                pass
        code = getattr(proc, "returncode", None)
        returncode = code if isinstance(code, int) and not isinstance(code, bool) else None

    stdout = _to_text(stdout)
    stderr = _to_text(stderr)
    ecoule = time.monotonic() - debut
    analyse = parse_stream_jsonl(stdout, stderr)
    erreurs = list(analyse["errors"])
    if stderr.strip() and (timed_out or returncode not in (0, None)):
        erreurs.append(f"stderr : {stderr.strip()}")
    if launch_error:
        erreurs.append(launch_error)

    duree = analyse["duration_seconds"] if analyse["duration_seconds"] is not None else ecoule
    run: dict[str, Any] = {
        "scenario": scenario["id"],
        "condition": condition,
        "run": run_index,
        "command": command,
        "cwd": str(cwd),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(ecoule, 3),
        "duration_seconds": round(duree, 3),
        "timed_out": timed_out,
        "returncode": returncode,
        "launch_error": launch_error,
        "result_found": analyse["result_found"],
        "result": analyse["result"],
        "is_error": analyse["is_error"],
        "cost_usd": analyse["cost_usd"],
        "num_turns": analyse["num_turns"],
        "tool_calls": analyse["tool_calls"],
        "tool_sequence": analyse["tool_sequence"],
        "errors": erreurs,
        "parse_errors": analyse["parse_errors"],
        "stderr": analyse["stderr"],
    }
    run["criteria"] = grade_run(scenario, run)
    run["passed"] = all(critere["passed"] for critere in run["criteria"])

    artefacts: dict[str, str] = {}
    if save:
        dossier = Path(output_dir)
        dossier.mkdir(parents=True, exist_ok=True)
        prefixe = f"run-{run_index:02d}"
        chemin_brut = dossier / f"{prefixe}.jsonl"
        chemin_resultat = dossier / f"{prefixe}.result.txt"
        chemin_bilan = dossier / f"{prefixe}.json"
        chemin_brut.write_text(stdout or "", encoding="utf-8")
        chemin_resultat.write_text(analyse["result"], encoding="utf-8")
        artefacts = {
            "jsonl": str(chemin_brut),
            "result": str(chemin_resultat),
            "summary": str(chemin_bilan),
        }
        run["artifacts"] = artefacts
        _write_json(chemin_bilan, run)
    else:
        run["artifacts"] = artefacts
    return run


def summarize_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Agrège des runs en compteurs et taux de réussite."""
    total = len(runs)
    reussis = sum(1 for run in runs if run.get("passed"))
    return {
        "runs": total,
        "passed": reussis,
        "failed": total - reussis,
        "pass_rate": round(reussis / total, 4) if total else 0.0,
    }


def summarize_by_condition(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Agrège les runs par condition."""
    conditions = sorted({run["condition"] for run in runs})
    return {
        condition: summarize_runs([run for run in runs if run["condition"] == condition])
        for condition in conditions
    }


def print_dry_run(scenarios: list[dict[str, Any]], args: argparse.Namespace,
                  mcp_config: str, repo_root: Path) -> None:
    """Affiche les commandes prévues sans exécuter ni écrire de résultats."""
    conditions = conditions_depuis_option(args.with_skill)
    for scenario in scenarios:
        print(f"# Scénario {scenario['id']} ({scenario['slug']})")
        espaces = Path(tempfile.gettempdir()) / "meridian-benchmark-empty"
        for condition, avec_skill in conditions:
            cwd = repo_root if avec_skill else espaces
            print(f"# Condition {condition}, cwd={cwd}")
            for run_index in range(1, args.runs + 1):
                commande = build_command(scenario, mcp_config, args)
                print(f"# run {run_index}/{args.runs}")
                print(shlex.join(commande))


def _public_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    """Retourne une vue JSON stable du scénario."""
    return {
        "id": scenario["id"],
        "slug": scenario["slug"],
        "source": scenario["source"],
        "prompt": scenario["prompt"],
        "skill": scenario.get("skill"),
        "mcp_tools": scenario["mcp_tools"],
        "expected_terms": scenario["expected_terms"],
        "forbidden_terms": scenario["forbidden_terms"],
        "expected_sections": scenario["expected_sections"],
        "max_seconds": scenario["max_seconds"],
        "max_cost": scenario["max_cost"],
        "must_complete": scenario["must_complete"],
    }


def run_benchmark(scenarios: list[dict[str, Any]], args: argparse.Namespace,
                  repo_root: Path, output_dir: Path, mcp_config: str,
                  mcp_trace: dict[str, Any]) -> dict[str, Any]:
    """Exécute tous les scenarios et conditions puis écrit le résumé global."""
    conditions = conditions_depuis_option(args.with_skill)
    tous_les_runs: list[dict[str, Any]] = []
    bilans_scenarios = []
    for scenario in scenarios:
        runs_scenario: list[dict[str, Any]] = []
        for condition, avec_skill in conditions:
            dossier_condition = output_dir / scenario["slug"] / condition
            for run_index in range(1, args.runs + 1):
                commande = build_command(scenario, mcp_config, args)
                if avec_skill:
                    run = run_once(
                        scenario=scenario,
                        condition=condition,
                        command=commande,
                        cwd=repo_root,
                        output_dir=dossier_condition,
                        run_index=run_index,
                        timeout=args.timeout,
                    )
                else:
                    with tempfile.TemporaryDirectory(prefix="meridian-benchmark-empty-") as espace:
                        run = run_once(
                            scenario=scenario,
                            condition=condition,
                            command=commande,
                            cwd=Path(espace),
                            output_dir=dossier_condition,
                            run_index=run_index,
                            timeout=args.timeout,
                        )
                runs_scenario.append(run)
                tous_les_runs.append(run)
        bilan = {
            "id": scenario["id"],
            "slug": scenario["slug"],
            "scenario": _public_scenario(scenario),
            "runs": runs_scenario,
            "summary": summarize_runs(runs_scenario),
            "by_condition": summarize_by_condition(runs_scenario),
        }
        bilans_scenarios.append(bilan)
        _write_json(output_dir / scenario["slug"] / "summary.json", bilan)

    resume = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(repo_root),
        "output_dir": str(output_dir),
        "config": {
            "runs": args.runs,
            "conditions": [condition for condition, _ in conditions],
            "model": args.model,
            "max_budget_usd": args.max_budget_usd,
            "timeout": args.timeout,
            "mcp_config": mcp_trace,
        },
        "summary": {
            **summarize_runs(tous_les_runs),
            "by_condition": summarize_by_condition(tous_les_runs),
        },
        "scenarios": bilans_scenarios,
        "runs": tous_les_runs,
    }
    _write_json(output_dir / "summary.json", resume)
    return resume


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée CLI du benchmark."""
    args = parse_args(argv)
    try:
        scenarios = load_scenarios(args.scenario)
    except ScenarioError as exc:
        print(f"Erreur de scénario : {exc}", file=sys.stderr)
        return 2

    repo_root = REPO_ROOT
    output_dir = Path(args.output).expanduser() if args.output else default_output_dir()
    try:
        mcp_config, dossier_mcp, mcp_trace = prepare_mcp_config(args, repo_root)
    except BenchmarkError as exc:
        print(f"Erreur MCP : {exc}", file=sys.stderr)
        return 2

    try:
        if args.dry_run:
            print_dry_run(scenarios, args, mcp_config, repo_root)
            return 0
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            resume = run_benchmark(
                scenarios=scenarios,
                args=args,
                repo_root=repo_root,
                output_dir=output_dir,
                mcp_config=mcp_config,
                mcp_trace=mcp_trace,
            )
        except OSError as exc:
            print(f"Erreur d'écriture des résultats : {exc}", file=sys.stderr)
            return 2
        print(json.dumps(resume["summary"], ensure_ascii=False))
        print(f"Résultats : {output_dir}")
        return 0
    finally:
        if dossier_mcp is not None:
            _remove_tree(dossier_mcp)


def _remove_tree(chemin: Path) -> None:
    """Supprime un dossier temporaire sans masquer l'erreur principale."""
    try:
        for element in sorted(chemin.rglob("*"), reverse=True):
            if element.is_file() or element.is_symlink():
                element.unlink(missing_ok=True)
            elif element.is_dir():
                element.rmdir()
        chemin.rmdir()
    except OSError:
        pass


if __name__ == "__main__":
    sys.exit(main())
