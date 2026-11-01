"""Runner de pilote Méridian sur le backend DeepSeek.

Le runner n'appelle jamais Claude Code. Pour chaque scénario il appelle deux
routes du backend :

- ``POST /api/boucle/analyser`` pour le contrat structuré
  (``socle``, ``lecture``, ``limites``, ``actions``, ``autorite``,
  ``prochaines_etapes``, ``decision_support``) ;
- ``POST /api/aurora/demander`` pour la prose DeepSeek et son usage
  (latence, jetons, coût).

Les critères objectifs de ``run_benchmark.py`` sont notés sur le contrat
structuré et la prose, jamais sur une sortie Claude. Le backend doit tourner avec
``JUMEAU_MODELE=deepseek`` et ``DEEPSEEK_API_KEY``.

Usage (depuis ``backend/``) ::

    PYTHONPATH=..:../backend .venv/bin/python \
        ../plugin/meridian/evals/run_deepseek.py \
        --scenario ../plugin/meridian/evals/scenarios/incident-paiements.json \
        --scenario ../plugin/meridian/evals/scenarios/changement-reglementaire.json \
        --tenant pilot --output /tmp/meridian-deepseek-pilot

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
    """Retourne ``<api>/jumeaux`` (registre legacy, repli)."""
    return f"{api_url.rstrip('/')}/jumeaux"


def twins_url(api_url: str) -> str:
    """Retourne ``<api>/boucle/twins`` (Twins typés du tenant)."""
    return f"{api_url.rstrip('/')}/boucle/twins"


def analyser_url(api_url: str) -> str:
    """Retourne ``<api>/boucle/analyser``."""
    return f"{api_url.rstrip('/')}/boucle/analyser"


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


def build_analyser_payload(scenario: dict[str, Any], persona: str = DEFAULT_PERSONA) -> dict[str, Any]:
    """Construit la requête du contrat structuré.

    La surface ``situation`` n'accepte que ``situation_id`` ; quand le scénario
    n'en déclare pas, le runner cible les Twins / l'application.
    """
    contexte = scenario.get("context") if isinstance(scenario.get("context"), dict) else {}
    selection = contexte.get("twins") if isinstance(contexte.get("twins"), list) else []
    payload: dict[str, Any] = {
        "question": scenario["prompt"],
        "profil": persona,
    }
    situation = str(contexte.get("situation") or "").strip()
    if situation:
        payload["situation_id"] = situation
        return payload
    if selection:
        payload["twin_ids"] = [str(jumeau) for jumeau in selection]
    if contexte.get("application"):
        payload["application_id"] = str(contexte["application"])
    return payload


def _espace(scenario: dict[str, Any]) -> str | None:
    """Espace explicite du scénario, s'il est déclaré."""
    contexte = scenario.get("context") if isinstance(scenario.get("context"), dict) else {}
    value = contexte.get("espace")
    return str(value) if value else None


def liste_jumeaux(api_url: str, tenant: str) -> list[dict[str, Any]]:
    """Lit le registre legacy, sans échouer si l'appel rate."""
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


def liste_twins(api_url: str, tenant: str) -> tuple[list[dict[str, Any]], str]:
    """Lit les Twins typés du tenant, avec repli sur le registre legacy."""
    import requests

    try:
        reponse = requests.get(twins_url(api_url), headers=_headers(tenant), timeout=10)
        reponse.raise_for_status()
        donnees = reponse.json()
    except (requests.RequestException, ValueError):
        return liste_jumeaux(api_url, tenant), "jumeaux"
    if isinstance(donnees, dict):
        donnees = donnees.get("twins") or donnees.get("items") or []
    lignes = [j for j in donnees if isinstance(j, dict)] if isinstance(donnees, list) else []
    return lignes, "boucle"


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


def _sans_question(valeur: Any) -> Any:
    """Retire les échos de la question pour ne pas noter le prompt lui-même."""
    if isinstance(valeur, dict):
        return {str(cle): _sans_question(element)
                for cle, element in valeur.items() if str(cle) != "question"}
    if isinstance(valeur, list):
        return [_sans_question(element) for element in valeur]
    return valeur


def _texte_contrat(donnees: Any) -> str:
    """Rend le contrat structuré en texte stable, sans les champs ``question``."""
    if not isinstance(donnees, dict):
        return ""
    return json.dumps(_sans_question(donnees), ensure_ascii=False, sort_keys=True)


def _critere_contrat(sections: Any, socle_sections: Any = None) -> dict[str, Any]:
    """Vérifie les clés du contrat structuré attendu, pas seulement du texte.

    Le backend expose les limites dans ``socle.limites`` (et les répète dans
    ``avertissements``) : la section ``limites`` est donc satisfaite à ce niveau.
    """
    presentes = {str(cle) for cle in (sections or [])}
    presentes |= {str(cle) for cle in (socle_sections or [])}
    attendues = ("socle", "lecture", "limites", "actions", "autorite",
                 "prochaines_etapes", "decision_support")
    manquantes = [cle for cle in attendues if cle not in presentes]
    return {
        "name": "contrat_structure",
        "passed": not manquantes,
        "detail": ("contrat complet : " + ", ".join(attendues) if not manquantes
                   else "sections manquantes : " + ", ".join(manquantes)),
    }


def _appel(url: str, payload: dict[str, Any], entetes: dict[str, str],
           timeout: float) -> tuple[int | None, Any, str, float]:
    """Appelle une route JSON et retourne (statut, charge, erreur, durée)."""
    import requests

    debut = time.monotonic()
    try:
        reponse = requests.post(url, json=payload, headers=entetes, timeout=timeout)
    except requests.Timeout:
        return None, None, f"timeout après {timeout:.0f} s", time.monotonic() - debut
    except requests.RequestException as exc:
        return None, None, f"requête impossible : {exc}", time.monotonic() - debut
    duree = time.monotonic() - debut
    try:
        donnees = reponse.json()
    except ValueError:
        donnees = None
    erreur = "" if 200 <= reponse.status_code < 300 else f"HTTP {reponse.status_code}"
    return reponse.status_code, donnees, erreur, duree


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
                 run_index: int, persona: str = DEFAULT_PERSONA
                 ) -> tuple[dict[str, Any], dict[str, Any]]:
    """Appelle le contrat structuré puis la prose DeepSeek, et retourne (bilan, bruts)."""
    payload_contrat = build_analyser_payload(scenario, persona)
    payload_prose = build_payload(scenario)
    entetes = _headers(tenant, _espace(scenario))
    statut_contrat, contrat, erreur_contrat, duree_contrat = _appel(
        analyser_url(api_url), payload_contrat, entetes, timeout)
    statut_prose, prose_brut, erreur_prose, duree_prose = _appel(
        demander_url(api_url), payload_prose, entetes, timeout)

    contrat_texte = _texte_contrat(contrat)
    prose_texte = ""
    if isinstance(prose_brut, dict):
        prose_texte = str(prose_brut.get("reponse") or prose_brut.get("answer") or "")
    elif isinstance(prose_brut, str):
        prose_texte = prose_brut
    usage = _usage_normalise(prose_brut.get("usage") if isinstance(prose_brut, dict) else None)
    reponse_contrat = contrat.get("reponse") if isinstance(contrat, dict) else None
    reponse_contrat = reponse_contrat if isinstance(reponse_contrat, dict) else {}
    sections = sorted(reponse_contrat.keys())
    socle = reponse_contrat.get("socle") if isinstance(reponse_contrat.get("socle"), dict) else {}
    socle_sections = sorted(socle.keys())
    est_ok = (statut_contrat == 200 and bool(contrat_texte.strip())
              and statut_prose == 200 and bool(prose_texte.strip()))
    erreurs = [erreur for erreur in (erreur_contrat, erreur_prose) if erreur]
    resultat = "\n\n".join(part for part in (contrat_texte, prose_texte) if part.strip())
    bilan = {
        "arm": "deepseek",
        "run": run_index,
        "result": resultat,
        "contract_text": contrat_texte,
        "prose_text": prose_texte,
        "result_found": bool(contrat_texte.strip()) and bool(prose_texte.strip()),
        "timed_out": "timeout" in erreur_contrat or "timeout" in erreur_prose,
        "is_error": not est_ok,
        "launch_error": " ; ".join(erreurs),
        "returncode": 0 if est_ok else 1,
        "duration_seconds": round(duree_contrat + duree_prose, 3),
        "contract_duration_seconds": round(duree_contrat, 3),
        "prose_duration_seconds": round(duree_prose, 3),
        "cost_usd": usage["cost_usd"],
        "usage": usage,
        "http_status": statut_prose,
        "contract_http_status": statut_contrat,
        "contract_sections": sections,
        "contract_socle_sections": socle_sections,
        "model": usage["model"],
        "payload": payload_prose,
        "contract_payload": payload_contrat,
        "comportement": prose_brut.get("comportement") if isinstance(prose_brut, dict) else None,
        "durees_backend": prose_brut.get("durees") if isinstance(prose_brut, dict) else None,
        "jumeaux_participants": (prose_brut.get("jumeaux_participants")
                                 if isinstance(prose_brut, dict) else None),
    }
    return bilan, {"contract": contrat, "prose": prose_brut}


def _ecrire_json(chemin: Path, donnees: Any) -> None:
    """Écrit un JSON lisible, sans secret."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(donnees, ensure_ascii=False, indent=2, default=str) + "\n",
                      encoding="utf-8")


def _criteres_run(scenario: dict[str, Any], run: dict[str, Any]) -> list[dict[str, Any]]:
    """Critères objectifs du scénario, contrat structuré et fournisseur compris."""
    criteres = rb.grade_run(scenario, run)
    contrat_ok = run.get("contract_http_status") == 200
    prose_ok = run.get("http_status") == 200
    criteres.extend([
        {
            "name": "http_status",
            "passed": contrat_ok and prose_ok,
            "detail": (f"boucle/analyser HTTP {run.get('contract_http_status')}, "
                       f"aurora/demander HTTP {run.get('http_status')}"),
        },
        {
            "name": "contract_http_status",
            "passed": contrat_ok,
            "detail": f"boucle/analyser HTTP {run.get('contract_http_status')}",
        },
        {
            "name": "prose_http_status",
            "passed": prose_ok,
            "detail": f"aurora/demander HTTP {run.get('http_status')}",
        },
        _critere_contrat(run.get("contract_sections"), run.get("contract_socle_sections")),
        _critere_modele(run.get("usage") or {}),
    ])
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
    durees_contrat = [r["contract_duration_seconds"] for r in runs
                      if r.get("contract_duration_seconds") is not None]
    durees_prose = [r["prose_duration_seconds"] for r in runs
                    if r.get("prose_duration_seconds") is not None]
    modeles = sorted({str(r.get("model")) for r in runs if r.get("model")})
    return {
        **base,
        "total_input_tokens": sum(jetons_entree) if jetons_entree else None,
        "total_output_tokens": sum(jetons_sortie) if jetons_sortie else None,
        "total_tokens": sum(total) if total else None,
        "mean_contract_duration_seconds": (
            round(sum(durees_contrat) / len(durees_contrat), 3) if durees_contrat else None),
        "mean_prose_duration_seconds": (
            round(sum(durees_prose) / len(durees_prose), 3) if durees_prose else None),
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
        "- Contrat structuré : `POST /api/boucle/analyser` ; prose : `POST /api/aurora/demander`.",
        "- Fournisseur de la prose : **DeepSeek** ; **Claude Code n'a pas été appelé**.",
        f"- Exécution : **{resume['summary']['runs_completed']}/{resume['summary']['runs']} runs complets** "
        "(contrat et prose HTTP 200, textes non vides).",
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
            _fmt(s.get("mean_contract_duration_seconds"), " s"),
            _fmt(s.get("mean_prose_duration_seconds"), " s"),
            _fmt(s.get("mean_duration_seconds"), " s"),
            _fmt(s.get("total_input_tokens")),
            _fmt(s.get("total_output_tokens")),
            _fmt(s.get("total_tokens")),
            _fmt(s.get("total_cost_usd"), " USD"),
            ", ".join(s.get("models") or []) or "—",
        ])
    lignes.append(_tableau_markdown(
        table, ["Scénario", "Statut", "Durée contrat", "Durée prose", "Durée totale",
                "Jetons entrée", "Jetons sortie", "Jetons total", "Coût estimé", "Modèle"]))
    lignes.extend(["", "## Critères", ""])
    for scenario in resume["scenarios"]:
        lignes.append(f"### {scenario['id']}")
        lignes.append("")
        for run in scenario["runs"]:
            echecs = [c for c in run.get("criteria", []) if not c.get("passed")]
            etat = "réussi" if run.get("passed") else "échec"
            lignes.append(f"- run {run['run']} : **{etat}**, contrat {run.get('contract_duration_seconds')} s, "
                          f"prose {run.get('prose_duration_seconds')} s, "
                          f"{_fmt(run.get('cost_usd'), ' USD')}")
            if echecs:
                lignes.append("  - critères en échec : "
                              + ", ".join(c["name"] for c in echecs))
                for critere in echecs:
                    lignes.append(f"    - `{critere['name']}` : {critere.get('detail', '')}")
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
        f"- Jumeaux visibles dans le tenant ({resume.get('jumeaux_source', 'boucle')}) : "
        f"{', '.join(f'`{j}`' for j in resume.get('jumeaux_du_tenant') or []) or '`—`'}.",
        "- La surface `situation` de `/boucle/analyser` n'accepte que `situation_id` ; le runner envoie donc "
        "la situation et non la liste des Twins. Les Twins sont vérifiés séparément via `/boucle/twins` et "
        "les Claims du tenant portent le contexte.",
        "- Le fixture `pilot` est **synthétique** et séparé de `demo` ; il ne prouve pas un état de production.",
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
                "headers": _headers(args.tenant, _espace(scenario)),
                "contract_url": analyser_url(args.api_url),
                "contract_payload": build_analyser_payload(scenario, args.persona),
                "prose_url": demander_url(args.api_url),
                "prose_payload": build_payload(scenario),
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
            jumeaux, source_jumeaux = liste_twins(args.api_url, args.tenant)
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
                                               args.timeout, run_index, args.persona)
                    bilan["criteria"] = _criteres_run(scenario, bilan)
                    bilan["passed"] = all(c["passed"] for c in bilan["criteria"])
                    runs_scenario.append(bilan)
                    tous_les_runs.append(bilan)
                    _ecrire_json(dossier_scenario / f"run-{run_index:02d}.json", bilan)
                    (dossier_scenario / f"run-{run_index:02d}.result.txt").write_text(
                        bilan["result"], encoding="utf-8")
                    (dossier_scenario / f"run-{run_index:02d}.contract.txt").write_text(
                        bilan["contract_text"], encoding="utf-8")
                    (dossier_scenario / f"run-{run_index:02d}.prose.txt").write_text(
                        bilan["prose_text"], encoding="utf-8")
                    _ecrire_json(dossier_scenario / f"run-{run_index:02d}.contract.json",
                                 brut.get("contract"))
                    _ecrire_json(dossier_scenario / f"run-{run_index:02d}.prose.json",
                                 brut.get("prose"))
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
                "jumeaux_source": source_jumeaux,
                "config": {"runs": args.runs, "timeout": args.timeout,
                           "start_backend": args.start_backend,
                           "contract_url": analyser_url(args.api_url),
                           "prose_url": demander_url(args.api_url)},
                "summary": {
                    **_resume_runs(tous_les_runs),
                    "scenarios": len(bilans),
                    "scenarios_passed": sum(1 for b in bilans if b["passed"]),
                    "contracts_completed": sum(
                        1 for run in tous_les_runs
                        if run.get("contract_http_status") == 200
                        and bool((run.get("contract_text") or "").strip())),
                    "prose_completed": sum(
                        1 for run in tous_les_runs
                        if run.get("http_status") == 200
                        and bool((run.get("prose_text") or "").strip())),
                    "runs_completed": sum(
                        1 for run in tous_les_runs
                        if run.get("http_status") == 200
                        and run.get("contract_http_status") == 200
                        and run.get("result_found")),
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
                "contracts_completed": resume["summary"]["contracts_completed"],
                "prose_completed": resume["summary"]["prose_completed"],
                "runs": resume["summary"]["runs"],
                "mean_contract_duration_seconds": resume["summary"]["mean_contract_duration_seconds"],
                "mean_prose_duration_seconds": resume["summary"]["mean_prose_duration_seconds"],
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
