"""Runner de pilote Méridian sur le backend DeepSeek.

Le runner n'appelle jamais Claude Code : il envoie le prompt d'un scénario à
``POST /api/aurora/demander``, puis note les critères objectifs déjà utilisés par
``run_benchmark.py`` (termes attendus/interdits, sections, durée, coût). Le
backend doit tourner avec ``JUMEAU_MODELE=deepseek`` et ``DEEPSEEK_API_KEY``.

Usage (depuis ``backend/``) ::

    PYTHONPATH=..:../backend .venv/bin/python \
        ../plugin/meridian/evals/run_deepseek.py \
        --scenario ../plugin/meridian/evals/scenarios/incident-paiements.json \
        --scenario ../plugin/meridian/evals/scenarios/changement-reglementaire.json \
        --output /tmp/meridian-deepseek-pilot

Avec ``--start-backend``, un backend local temporaire est démarré sur le port de
``--api-url`` s'il ne répond pas déjà. Sinon, le runner attend un backend
joignable à ``MERIDIAN_API_URL`` (défaut ``http://127.0.0.1:8001/api``).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:  # exécution directe ou import comme module
    from . import run_benchmark as rb
except ImportError:  # pragma: no cover - chemin d'exécution directe
    import run_benchmark as rb  # type: ignore[no-redef]

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
DEFAULT_API_URL = "http://127.0.0.1:8001/api"
DEFAULT_TENANT = "demo"
DEFAULT_PERSONA = "architecte"
DEFAULT_TIMEOUT = 300.0
DEFAULT_RUNS = 1


def _positive_int(value: str) -> int:
    """Convertit une chaîne en entier strictement positif."""
    return rb._positive_int(value)


def _positive_float(value: str) -> float:
    """Convertit une chaîne en flottant strictement positif."""
    return rb._positive_float(value)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Analyse les arguments de la ligne de commande."""
    parser = argparse.ArgumentParser(
        description="Pilote Méridian sur le runtime backend DeepSeek, sans Claude Code.",
    )
    parser.add_argument("--scenario", action="append", required=True,
                        help="Chemin d'un scénario JSON (option répétable).")
    parser.add_argument("--runs", type=_positive_int, default=DEFAULT_RUNS,
                        help=f"Runs par scénario (défaut : {DEFAULT_RUNS}).")
    parser.add_argument("--output", type=Path,
                        help="Répertoire des résultats (défaut : /tmp/meridian-deepseek-<timestamp>).")
    parser.add_argument("--api-url",
                        default=os.environ.get("MERIDIAN_API_URL", DEFAULT_API_URL),
                        help="Base de l'API Méridian, chemin /api compris.")
    parser.add_argument("--tenant",
                        default=os.environ.get("MERIDIAN_TENANT", DEFAULT_TENANT),
                        help="Tenant envoyé dans X-Tenant (défaut : demo).")
    parser.add_argument("--persona",
                        default=os.environ.get("MERIDIAN_PERSONA", DEFAULT_PERSONA),
                        help="Persona du scénario, enregistré dans le rapport.")
    parser.add_argument("--timeout", type=_positive_float, default=DEFAULT_TIMEOUT,
                        help=f"Timeout par appel, en secondes (défaut : {DEFAULT_TIMEOUT:.0f}).")
    parser.add_argument("--start-backend", action="store_true",
                        help="Démarrer un backend local temporaire s'il ne répond pas déjà.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Afficher les requêtes sans appeler le backend ni écrire de résultats.")
    return parser.parse_args(argv)


def default_output_dir() -> Path:
    """Retourne un répertoire de sortie horodaté."""
    horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path(tempfile.gettempdir()) / f"meridian-deepseek-{horodatage}"


def _headers(tenant: str, espace: str | None = None) -> dict[str, str]:
    """En-têtes HTTP du run, sans aucune clé secrète."""
    entetes = {"Content-Type": "application/json", "X-Tenant": tenant}
    if espace:
        entetes["X-Espace"] = espace
    return entetes


def health_url(api_url: str) -> str:
    """Retourne ``<api>/health``."""
    return f"{api_url.rstrip('/')}/health"


def jumeaux_url(api_url: str) -> str:
    """Retourne ``<api>/jumeaux``."""
    return f"{api_url.rstrip('/')}/jumeaux"


def demander_url(api_url: str) -> str:
    """Retourne ``<api>/aurora/demander``."""
    return f"{api_url.rstrip('/')}/aurora/demander"


def backend_port(api_url: str) -> int:
    """Retourne le port du backend, 8001 par défaut."""
    return urlparse(api_url).port or 8001


def _health_ok(api_url: str, timeout: float = 2.0) -> bool:
    """Vrai si le backend répond 200 sur /health."""
    import requests

    try:
        reponse = requests.get(health_url(api_url), timeout=timeout)
    except requests.RequestException:
        return False
    return reponse.status_code == 200


class BackendTemporaire:
    """Backend local optionnel, arrêté à la fin du run."""

    def __init__(self, api_url: str, output_dir: Path):
        self.api_url = api_url
        self.port = backend_port(api_url)
        self.log_path = output_dir / "backend.log"
        self.proc: subprocess.Popen | None = None
        self._log = None

    def __enter__(self) -> "BackendTemporaire":
        if _health_ok(self.api_url):
            return self
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = self.log_path.open("w", encoding="utf-8")
        env = os.environ.copy()
        env["JUMEAU_MODELE"] = "deepseek"
        commande = [sys.executable, "-m", "uvicorn", "server:app",
                    "--host", "127.0.0.1", "--port", str(self.port)]
        try:
            self.proc = subprocess.Popen(
                commande, cwd=BACKEND_DIR, env=env, stdout=self._log,
                stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as exc:
            self._close_log()
            raise rb.BenchmarkError(
                f"démarrage du backend impossible ({exc}) ; journal : {self.log_path}") from exc
        if not self._attendre():
            self.__exit__(None, None, None)
            raise rb.BenchmarkError(
                f"backend injoignable après démarrage ; journal : {self.log_path}")
        return self

    def _attendre(self, delai: float = 90.0) -> bool:
        """Attend que /health réponde, sans lire les secrets du backend."""
        fin = time.monotonic() + delai
        while time.monotonic() < fin:
            if self.proc is not None and self.proc.poll() is not None:
                return False
            if _health_ok(self.api_url, timeout=1.0):
                return True
            time.sleep(0.5)
        return False

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    self.proc.kill()
                    self.proc.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        self._close_log()

    def _close_log(self) -> None:
        if self._log is not None:
            self._log.close()
            self._log = None


def build_payload(scenario: dict[str, Any]) -> dict[str, Any]:
    """Construit la requête Aurora : prompt du scénario et sélection déclarée."""
    contexte = scenario.get("context") if isinstance(scenario.get("context"), dict) else {}
    selection = contexte.get("twins") if isinstance(contexte.get("twins"), list) else []
    payload: dict[str, Any] = {
        "contexte": str(contexte.get("contexte") or "global"),
        "question": scenario["prompt"],
        "selection": [str(jumeau) for jumeau in selection],
        "domaine": contexte.get("domaine"),
    }
    return payload


def _espace(scenario: dict[str, Any]) -> str | None:
    """Espace explicite du scénario, s'il est déclaré."""
    contexte = scenario.get("context") if isinstance(scenario.get("context"), dict) else {}
    value = contexte.get("espace")
    return str(value) if value else None


def liste_jumeaux(api_url: str, tenant: str) -> list[dict[str, Any]]:
    """Lit les jumeaux visibles pour le tenant, sans échouer si l'appel rate."""
    import requests

    try:
        reponse = requests.get(jumeaux_url(api_url), headers=_headers(tenant), timeout=10)
        reponse.raise_for_status()
        donnees = reponse.json()
    except (requests.RequestException, ValueError):
        return []
    if isinstance(donnees, dict):
        donnees = donnees.get("jumeaux") or donnees.get("items") or []
    return [j for j in donnees if isinstance(j, dict)] if isinstance(donnees, list) else []


def _usage_normalise(brut: Any) -> dict[str, Any]:
    """Extrait jetons et coût du bloc ``usage`` du backend, sans inventer de valeur."""
    if not isinstance(brut, dict):
        return {"input_tokens": None, "output_tokens": None, "total_tokens": None,
                "cache_read_tokens": None, "cache_write_tokens": None,
                "cost_usd": None, "cost_currency": None, "cost_estimate": None,
                "model": None}
    cout = brut.get("cout") if isinstance(brut.get("cout"), dict) else {}

    def entier(cle: str) -> int | None:
        try:
            return int(brut[cle])
        except (KeyError, TypeError, ValueError):
            return None

    montant = cout.get("montant")
    try:
        montant = float(montant) if montant is not None else None
    except (TypeError, ValueError):
        montant = None
    return {
        "input_tokens": entier("entree"),
        "output_tokens": entier("sortie"),
        "total_tokens": entier("total"),
        "cache_read_tokens": entier("cache_lu"),
        "cache_write_tokens": entier("cache_ecrit"),
        "cost_usd": montant,
        "cost_currency": cout.get("devise"),
        "cost_estimate": cout.get("estimation"),
        "model": brut.get("modele"),
    }


def _critere_modele(usage: dict[str, Any]) -> dict[str, Any]:
    """Vérifie que le modèle rapporté est bien DeepSeek, jamais Claude."""
    modele = usage.get("model")
    texte = str(modele or "").casefold()
    passed = bool(texte) and "deepseek" in texte and "claude" not in texte
    if not modele:
        detail = "modèle non rapporté par le backend (impossible de prouver le fournisseur)"
    elif "claude" in texte:
        detail = f"modèle Claude détecté : {modele}"
    elif "deepseek" not in texte:
        detail = f"modèle non DeepSeek : {modele}"
    else:
        detail = f"modèle DeepSeek confirmé : {modele}"
    return {"name": "modele_deepseek", "passed": passed, "detail": detail}


def executer_run(scenario: dict[str, Any], api_url: str, tenant: str, timeout: float,
                 run_index: int) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Envoie un scénario à Aurora et retourne (bilan, réponse brute)."""
    import requests

    payload = build_payload(scenario)
    entetes = _headers(tenant, _espace(scenario))
    debut = time.monotonic()
    try:
        reponse = requests.post(demander_url(api_url), json=payload, headers=entetes,
                                timeout=timeout)
        duree = time.monotonic() - debut
    except requests.Timeout:
        duree = time.monotonic() - debut
        return {
            "arm": "deepseek",
            "run": run_index,
            "result": "",
            "result_found": False,
            "timed_out": True,
            "is_error": True,
            "launch_error": f"timeout après {timeout:.0f} s",
            "returncode": None,
            "duration_seconds": round(duree, 3),
            "cost_usd": None,
            "usage": _usage_normalise(None),
            "http_status": None,
            "model": None,
            "payload": payload,
        }, None
    except requests.RequestException as exc:
        duree = time.monotonic() - debut
        return {
            "arm": "deepseek",
            "run": run_index,
            "result": "",
            "result_found": False,
            "timed_out": False,
            "is_error": True,
            "launch_error": f"requête impossible : {exc}",
            "returncode": None,
            "duration_seconds": round(duree, 3),
            "cost_usd": None,
            "usage": _usage_normalise(None),
            "http_status": None,
            "model": None,
            "payload": payload,
        }, None

    try:
        donnees = reponse.json()
    except ValueError:
        donnees = None
    texte = ""
    if isinstance(donnees, dict):
        texte = str(donnees.get("reponse") or donnees.get("answer") or "")
    elif isinstance(donnees, str):
        texte = donnees
    usage = _usage_normalise(donnees.get("usage") if isinstance(donnees, dict) else None)
    est_ok = 200 <= reponse.status_code < 300 and bool(texte.strip())
    bilan = {
        "arm": "deepseek",
        "run": run_index,
        "result": texte,
        "result_found": bool(texte.strip()),
        "timed_out": False,
        "is_error": not est_ok,
        "launch_error": "" if est_ok else f"HTTP {reponse.status_code}",
        "returncode": 0 if est_ok else 1,
        "duration_seconds": round(duree, 3),
        "cost_usd": usage["cost_usd"],
        "usage": usage,
        "http_status": reponse.status_code,
        "model": usage["model"],
        "payload": payload,
        "comportement": donnees.get("comportement") if isinstance(donnees, dict) else None,
        "durees_backend": donnees.get("durees") if isinstance(donnees, dict) else None,
        "jumeaux_participants": donnees.get("jumeaux_participants") if isinstance(donnees, dict) else None,
    }
    return bilan, donnees if isinstance(donnees, dict) else None


def _ecrire_json(chemin: Path, donnees: Any) -> None:
    """Écrit un JSON lisible, sans secret."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(donnees, ensure_ascii=False, indent=2, default=str) + "\n",
                      encoding="utf-8")


def _criteres_run(scenario: dict[str, Any], run: dict[str, Any]) -> list[dict[str, Any]]:
    """Critères objectifs du scénario, plus la preuve du fournisseur DeepSeek."""
    criteres = rb.grade_run(scenario, run)
    criteres.append({
        "name": "http_status",
        "passed": run.get("http_status") == 200,
        "detail": f"HTTP {run.get('http_status')}",
    })
    criteres.append(_critere_modele(run.get("usage") or {}))
    return criteres


def _resume_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Résumé des runs avec jetons et coût réels."""
    base = rb.summarize_runs(runs)
    jetons_entree = [r["usage"]["input_tokens"] for r in runs
                     if isinstance(r.get("usage"), dict) and r["usage"].get("input_tokens") is not None]
    jetons_sortie = [r["usage"]["output_tokens"] for r in runs
                     if isinstance(r.get("usage"), dict) and r["usage"].get("output_tokens") is not None]
    total = [r["usage"]["total_tokens"] for r in runs
             if isinstance(r.get("usage"), dict) and r["usage"].get("total_tokens") is not None]
    modeles = sorted({str(r.get("model")) for r in runs if r.get("model")})
    return {
        **base,
        "total_input_tokens": sum(jetons_entree) if jetons_entree else None,
        "total_output_tokens": sum(jetons_sortie) if jetons_sortie else None,
        "total_tokens": sum(total) if total else None,
        "models": modeles,
    }


def _tableau_markdown(lignes: list[list[str]], entetes: list[str]) -> str:
    """Rend un tableau Markdown compact."""
    contenu = ["| " + " | ".join(entetes) + " |",
               "|" + "|".join("---" for _ in entetes) + "|"]
    contenu.extend("| " + " | ".join(str(cellule) for cellule in ligne) + " |" for ligne in lignes)
    return "\n".join(contenu)


def _fmt(value: Any, suffixe: str = "") -> str:
    """Formate une valeur absente sans inventer de chiffre."""
    return "—" if value is None else f"{value}{suffixe}"


def ecrire_rapport(dossier: Path, resume: dict[str, Any]) -> Path:
    """Écrit un rapport Markdown concis à côté du JSON."""
    lignes = [
        "# Pilote DeepSeek — " + resume["generated_at"],
        "",
        f"- Backend : `{resume['api_url']}` (tenant `{resume['tenant']}`, persona `{resume['persona']}`)",
        "- Fournisseur : **DeepSeek**, via `POST /api/aurora/demander` ; **Claude Code n'a pas été appelé**.",
        f"- Exécution : **{resume['summary']['runs_completed']}/{resume['summary']['runs']} runs complets** "
        "(HTTP 200 et texte non vide).",
        f"- Critères du scénario : **{resume['summary']['scenarios_passed']}/{resume['summary']['scenarios']} scénarios réussis**.",
        "",
        "## Résultats",
        "",
    ]
    table = []
    for scenario in resume["scenarios"]:
        s = scenario["summary"]
        table.append([
            scenario["id"],
            "réussi" if scenario["passed"] else "échec",
            _fmt(s.get("mean_duration_seconds"), " s"),
            _fmt(s.get("total_input_tokens")),
            _fmt(s.get("total_output_tokens")),
            _fmt(s.get("total_tokens")),
            _fmt(s.get("total_cost_usd"), " USD"),
            ", ".join(s.get("models") or []) or "—",
        ])
    lignes.append(_tableau_markdown(
        table, ["Scénario", "Statut", "Durée", "Jetons entrée", "Jetons sortie",
                "Jetons total", "Coût estimé", "Modèle"]))
    lignes.extend(["", "## Critères", ""])
    for scenario in resume["scenarios"]:
        lignes.append(f"### {scenario['id']}")
        lignes.append("")
        for run in scenario["runs"]:
            echecs = [c["name"] for c in run.get("criteria", []) if not c.get("passed")]
            etat = "réussi" if run.get("passed") else "échec"
            lignes.append(f"- run {run['run']} : **{etat}**, {run['duration_seconds']} s, "
                          f"{_fmt(run.get('cost_usd'), ' USD')}")
            if echecs:
                lignes.append(f"  - critères en échec : {', '.join(echecs)}")
        lignes.append("")
    absents = sorted({
        jumeau for scenario in resume["scenarios"]
        for jumeau in scenario.get("selection_absente_du_tenant", [])
    })
    lignes.extend(["## Limites", ""])
    if absents:
        lignes.append(
            f"- Sélection absente du tenant `{resume['tenant']}` : "
            f"{', '.join(f'`{j}`' for j in absents)}. Le backend répond alors sans ces Twins ; "
            "un échec de critère ne prouve pas un défaut du workflow.")
    else:
        lignes.append("- Aucune sélection absente du tenant n'a été détectée.")
    lignes.extend([
        f"- Jumeaux visibles dans le tenant : {', '.join(f'`{j}`' for j in resume.get('jumeaux_du_tenant') or []) or '`—`'}.",
        "- `/aurora/demander` renvoie une réponse Flore en prose, pas le contrat de sections du plugin "
        "(`socle`, `lecture`, `actions`, etc.) : les critères de sections peuvent échouer même sur une "
        "réponse valide.",
        "- Le coût est une estimation du backend (`usage.cout`), pas une facture.",
        "- Aucune revue humaine, aucun outcome réel, aucune preuve de supériorité statistique.",
        "- Les résultats et réponses complètes sont stockés ; les traiter selon la politique de confidentialité du projet.",
        "",
    ])
    chemin = dossier / "REPORT.md"
    chemin.write_text("\n".join(lignes), encoding="utf-8")
    return chemin


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée CLI du runner DeepSeek."""
    args = parse_args(argv)
    try:
        scenarios = rb.load_scenarios(args.scenario)
    except rb.ScenarioError as exc:
        print(f"Erreur de scénario : {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        for scenario in scenarios:
            print(json.dumps({
                "scenario": scenario["id"],
                "url": demander_url(args.api_url),
                "headers": _headers(args.tenant, _espace(scenario)),
                "payload": build_payload(scenario),
            }, ensure_ascii=False))
        return 0

    dossier = Path(args.output).expanduser() if args.output else default_output_dir()
    try:
        dossier.mkdir(parents=True, exist_ok=True)
        with BackendTemporaire(args.api_url, dossier) if args.start_backend else _contexte_vide():
            if not _health_ok(args.api_url):
                print(f"Backend injoignable : {health_url(args.api_url)} "
                      "(lancer un backend ou utiliser --start-backend)", file=sys.stderr)
                return 2
            jumeaux = liste_jumeaux(args.api_url, args.tenant)
            ids_connus = {str(j.get("id")) for j in jumeaux}
            tous_les_runs: list[dict[str, Any]] = []
            bilans = []
            for scenario in scenarios:
                selection = build_payload(scenario)["selection"]
                inconnus = [j for j in selection if j not in ids_connus]
                dossier_scenario = dossier / scenario["slug"]
                runs_scenario = []
                for run_index in range(1, args.runs + 1):
                    bilan, brut = executer_run(scenario, args.api_url, args.tenant,
                                               args.timeout, run_index)
                    bilan["criteria"] = _criteres_run(scenario, bilan)
                    bilan["passed"] = all(c["passed"] for c in bilan["criteria"])
                    runs_scenario.append(bilan)
                    tous_les_runs.append(bilan)
                    _ecrire_json(dossier_scenario / f"run-{run_index:02d}.json", bilan)
                    (dossier_scenario / f"run-{run_index:02d}.result.txt").write_text(
                        bilan["result"], encoding="utf-8")
                    if brut is not None:
                        _ecrire_json(dossier_scenario / f"run-{run_index:02d}.response.json", brut)
                bilan_scenario = {
                    "id": scenario["id"],
                    "slug": scenario["slug"],
                    "scenario": rb._public_scenario(scenario),
                    "context": scenario.get("context"),
                    "selection_envoyee": selection,
                    "selection_absente_du_tenant": inconnus,
                    "runs": runs_scenario,
                    "summary": _resume_runs(runs_scenario),
                    "passed": all(run["passed"] for run in runs_scenario),
                }
                bilans.append(bilan_scenario)
                _ecrire_json(dossier_scenario / "summary.json", bilan_scenario)
            resume = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "provider": "deepseek",
                "claude_used": False,
                "api_url": args.api_url,
                "tenant": args.tenant,
                "persona": args.persona,
                "jumeaux_du_tenant": sorted(ids_connus),
                "config": {"runs": args.runs, "timeout": args.timeout,
                           "start_backend": args.start_backend},
                "summary": {
                    **_resume_runs(tous_les_runs),
                    "scenarios": len(bilans),
                    "scenarios_passed": sum(1 for b in bilans if b["passed"]),
                    "runs_completed": sum(
                        1 for run in tous_les_runs
                        if run.get("http_status") == 200 and run.get("result_found")),
                },
                "scenarios": bilans,
                "runs": tous_les_runs,
            }
            _ecrire_json(dossier / "summary.json", resume)
            rapport = ecrire_rapport(dossier, resume)
            print(json.dumps({
                "scenarios_passed": resume["summary"]["scenarios_passed"],
                "scenarios": resume["summary"]["scenarios"],
                "runs_completed": resume["summary"]["runs_completed"],
                "runs": resume["summary"]["runs"],
                "total_tokens": resume["summary"]["total_tokens"],
                "total_cost_usd": resume["summary"]["total_cost_usd"],
            }, ensure_ascii=False))
            print(f"Résultats : {dossier}")
            print(f"Rapport : {rapport}")
            return 0
    except (rb.BenchmarkError, OSError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - message d'infrastructure sans secret
        print(f"Erreur inattendue : {exc}", file=sys.stderr)
        return 2


class _contexte_vide:
    """Contexte nul quand ``--start-backend`` n'est pas demandé."""

    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, traceback):
        return False


if __name__ == "__main__":
    sys.exit(main())
