"""Runner reproductible du benchmark Méridian à quatre bras.

Le runner lance la CLI Claude Code sur des scénarios JSON et compare des bras
déclaratifs : ``skill+mcp`` (racine du dépôt), ``checklist+mcp`` (répertoire vide
avec checklist générique), ``data-only`` (pack JSON gelé, sans MCP) et ``human``
(import de réponses déjà produites). Seuls des critères objectifs déclarés dans
le scénario sont notés ; aucune note subjective n'est automatisée.
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
DEFAULT_TIMEOUT = 300.0
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

ARM_SKILL_MCP = "skill+mcp"
ARM_CHECKLIST_MCP = "checklist+mcp"
ARM_DATA_ONLY = "data-only"
ARM_HUMAN = "human"
ARMS = (ARM_SKILL_MCP, ARM_CHECKLIST_MCP, ARM_DATA_ONLY, ARM_HUMAN)
ARM_ALIASES = {
    "with-skill": ARM_SKILL_MCP,
    "without-skill": ARM_CHECKLIST_MCP,
}
DEFAULT_ARM = ARM_SKILL_MCP
DEFAULT_ARMS = (ARM_SKILL_MCP, ARM_CHECKLIST_MCP, ARM_DATA_ONLY)
CHECKLIST_PATH = Path(__file__).resolve().parent / "checklists" / "generic.md"


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


def normalize_arm(value: str) -> str:
    """Normalise un nom de bras et résout les alias historiques."""
    return ARM_ALIASES.get(value.strip().lower(), value.strip().lower())


def _arm_value(value: str) -> str:
    """Type argparse d'un bras, avec alias ``with-skill``/``without-skill``."""
    arm = normalize_arm(value)
    if arm not in ARMS:
        raise argparse.ArgumentTypeError(
            f"bras inconnu : {value} (attendu : {', '.join(ARMS)})")
    return arm


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
                        help=f"Nombre de runs par scénario et bras (défaut : {DEFAULT_RUNS}).")
    parser.add_argument("--arm", action="append", type=_arm_value, metavar="BRAS",
                        help=("Bras à exécuter (répétable) : skill+mcp (défaut), checklist+mcp, "
                              "data-only, human. Alias : with-skill, without-skill."))
    conditions = parser.add_mutually_exclusive_group()
    conditions.add_argument("--with-skill", dest="with_skill", action="store_true",
                            help="Alias historique de --arm skill+mcp.")
    conditions.add_argument("--no-with-skill", dest="with_skill", action="store_false",
                            help="Alias historique de --arm checklist+mcp.")
    parser.set_defaults(with_skill=None)
    parser.add_argument("--human-dir", type=Path,
                        help="Dossier des réponses humaines <scenario>-human.json.")
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
    args = parser.parse_args(argv)
    explicite = args.arm is not None
    if explicite and args.with_skill is not None:
        parser.error("--arm est incompatible avec --with-skill/--no-with-skill")
    if explicite:
        args.arm = list(dict.fromkeys(args.arm))
    elif args.with_skill is True:
        args.arm = [ARM_SKILL_MCP]
    elif args.with_skill is False:
        args.arm = [ARM_CHECKLIST_MCP]
    else:
        args.arm = list(DEFAULT_ARMS)
    return args


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

    data_pack = raw.get("data_pack")
    if data_pack is not None and (not isinstance(data_pack, str) or not data_pack.strip()):
        raise ScenarioError(f"{source} : le champ data_pack doit être un chemin non vide")
    if isinstance(data_pack, str):
        chemin_pack = Path(data_pack).expanduser()
        if not chemin_pack.is_absolute():
            chemin_pack = Path(source).expanduser().parent / chemin_pack
        data_pack = str(chemin_pack.resolve())

    sections = raw.get("expected_sections")
    if sections is None:
        sections = raw.get("sections")
    scenario = {
        "id": str(identifiant),
        "slug": _slugify(str(identifiant)),
        "source": str(source),
        "prompt": prompt.strip(),
        "context": raw.get("context") if isinstance(raw.get("context"), dict) else {},
        "mcp_tools": mcp_tools,
        "data_pack": data_pack,
        "expected_terms": _string_list(raw.get("expected_terms"), "expected_terms"),
        "forbidden_terms": _string_list(raw.get("forbidden_terms"), "forbidden_terms"),
        "forbidden_terms_exceptions": _exceptions(raw.get("forbidden_terms_exceptions")),
        "expected_sections": _string_list(sections, "expected_sections"),
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


def arms_depuis_args(args: argparse.Namespace) -> list[str]:
    """Retourne les bras canoniques demandés, alias historiques compris."""
    demandes = getattr(args, "arm", None)
    if demandes:
        resultat: list[str] = []
        for valeur in demandes:
            arm = normalize_arm(valeur)
            if arm not in resultat:
                resultat.append(arm)
        return resultat
    with_skill = getattr(args, "with_skill", None)
    if with_skill is True:
        return [ARM_SKILL_MCP]
    if with_skill is False:
        return [ARM_CHECKLIST_MCP]
    return list(DEFAULT_ARMS)


def conditions_depuis_option(with_skill: bool | None) -> list[tuple[str, bool]]:
    """Compatibilité : retourne les bras historiques sous forme (nom, avec_skill)."""
    if with_skill is False:
        return [(ARM_CHECKLIST_MCP, False)]
    return [(ARM_SKILL_MCP, True)]


def arm_utilise_mcp(arm: str) -> bool:
    """Indique si un bras ouvre le serveur MCP Méridian."""
    return arm in (ARM_SKILL_MCP, ARM_CHECKLIST_MCP)


def arm_utilise_skill(arm: str) -> bool:
    """Indique si un bras s'exécute dans le dépôt avec les skills visibles."""
    return arm == ARM_SKILL_MCP


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


def prepare_mcp_config(args: argparse.Namespace, repo_root: Path, required: bool = True
                       ) -> tuple[str | None, Path | None, dict[str, Any]]:
    """Prépare le fichier MCP et retourne son chemin, son dossier temporaire et sa trace."""
    if not required:
        return None, None, {"source": "disabled", "reason": "aucun bras MCP demandé"}
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


def load_checklist(chemin: str | Path | None = None) -> str:
    """Charge la checklist générique neutre du bras checklist+mcp."""
    fichier = Path(chemin).expanduser() if chemin is not None else CHECKLIST_PATH
    try:
        contenu = fichier.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise BenchmarkError(f"checklist introuvable ou illisible : {fichier} ({exc})") from exc
    if not contenu:
        raise BenchmarkError(f"checklist vide : {fichier}")
    return contenu


def load_data_pack(scenario: dict[str, Any]) -> str:
    """Charge le pack JSON gelé d'un scénario pour le bras data-only."""
    chemin_brut = scenario.get("data_pack")
    if not chemin_brut:
        raise ScenarioError(
            f"scénario {scenario['id']} : le champ data_pack est requis pour le bras data-only")
    chemin = Path(str(chemin_brut)).expanduser()
    try:
        contenu = chemin.read_text(encoding="utf-8")
    except OSError as exc:
        raise ScenarioError(f"data_pack illisible pour {scenario['id']} : {chemin} ({exc})") from exc
    try:
        json.loads(contenu)
    except json.JSONDecodeError as exc:
        raise ScenarioError(f"data_pack JSON invalide pour {scenario['id']} : {exc}") from exc
    return contenu.strip()


def build_prompt(scenario: dict[str, Any], arm: str = DEFAULT_ARM) -> str:
    """Construit le prompt d'un bras, avec pack gelé pour data-only."""
    if arm != ARM_DATA_ONLY:
        return scenario["prompt"]
    pack = load_data_pack(scenario)
    entete = (
        "Contexte du run : données gelées, aucun outil MCP. Travaille uniquement à partir "
        "du pack JSON ci-dessous, sans accès en direct ni appel d'outil Méridian.\n\n"
    )
    return f"{entete}```json\n{pack}\n```\n\n{scenario['prompt']}"


def _normalize_tool_name(nom: str) -> str:
    """Ajoute le préfixe MCP Méridian à un nom d'outil court."""
    nom = nom.strip()
    if nom.startswith("mcp__"):
        return nom
    if nom.startswith("meridian__"):
        return f"mcp__{nom}"
    return f"mcp__meridian__{nom}"


def allowed_tools(scenario: dict[str, Any], arm: str = DEFAULT_ARM) -> list[str]:
    """Construit la liste déterministe des outils autorisés pour un scénario et un bras."""
    if arm == ARM_DATA_ONLY:
        return ["Read"]
    outils = ["Read"]
    if arm == ARM_SKILL_MCP:
        outils.insert(0, "Skill")
    for outil in scenario["mcp_tools"]:
        normalise = _normalize_tool_name(outil)
        if normalise not in outils:
            outils.append(normalise)
    return outils


def build_command(scenario: dict[str, Any], mcp_config: str | None, args: argparse.Namespace,
                  claude_bin: str = "claude", arm: str = DEFAULT_ARM,
                  checklist: str | None = None) -> list[str]:
    """Construit la commande Claude Code d'un run pour un bras donné."""
    arm = normalize_arm(arm)
    commande = [
        claude_bin,
        "-p",
        build_prompt(scenario, arm),
    ]
    if arm_utilise_mcp(arm):
        if not mcp_config:
            raise BenchmarkError(f"configuration MCP requise pour le bras {arm}")
        commande.extend(["--mcp-config", mcp_config, "--strict-mcp-config"])
    if arm == ARM_CHECKLIST_MCP:
        texte = load_checklist() if checklist is None else checklist
        if texte.strip():
            commande.extend(["--append-system-prompt", texte.strip()])
    commande.extend([
        "--allowedTools",
        ",".join(allowed_tools(scenario, arm)),
        "--max-budget-usd",
        str(args.max_budget_usd),
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
    ])
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
             save: bool = True, arm: str | None = None) -> dict[str, Any]:
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
        "arm": arm or condition,
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


def _run_arm(run: dict[str, Any]) -> str:
    """Retourne le bras d'un run, avec repli sur l'ancien champ condition."""
    return str(run.get("arm") or run.get("condition") or "inconnu")


def _arm_order(arm: str) -> tuple[int, str]:
    """Trie les bras dans l'ordre du protocole, puis les inconnus."""
    return (ARMS.index(arm) if arm in ARMS else len(ARMS), arm)


def summarize_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Agrège des runs en compteurs, taux de réussite, coût et durée."""
    total = len(runs)
    reussis = sum(1 for run in runs if run.get("passed"))
    manquants = sum(1 for run in runs if run.get("missing"))
    couts = [
        cout for cout in (_to_float(run.get("cost_usd")) for run in runs) if cout is not None
    ]
    durees = [
        duree for duree in (_to_float(run.get("duration_seconds")) for run in runs)
        if duree is not None
    ]
    return {
        "runs": total,
        "passed": reussis,
        "failed": total - reussis,
        "missing": manquants,
        "pass_rate": round(reussis / total, 4) if total else 0.0,
        "total_cost_usd": round(sum(couts), 6) if couts else None,
        "mean_cost_usd": round(sum(couts) / len(couts), 6) if couts else None,
        "mean_duration_seconds": round(sum(durees) / len(durees), 3) if durees else None,
    }


def summarize_by_arm(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Agrège les runs par bras."""
    bras = sorted({_run_arm(run) for run in runs}, key=_arm_order)
    return {
        arm: summarize_runs([run for run in runs if _run_arm(run) == arm])
        for arm in bras
    }


def summarize_by_condition(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Alias historique de :func:`summarize_by_arm`."""
    return summarize_by_arm(runs)


def _delta(valeur: float | None, reference: float | None, decimales: int = 6) -> float | None:
    """Calcule un écart arrondi, ou ``None`` si une valeur manque."""
    if valeur is None or reference is None:
        return None
    return round(valeur - reference, decimales)


def compare_arms(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare les bras au bras de référence ``skill+mcp``."""
    par_bras = summarize_by_arm(runs)
    reference = par_bras.get(ARM_SKILL_MCP)
    deltas: dict[str, dict[str, Any]] = {}
    for arm, bilan in par_bras.items():
        if arm == ARM_SKILL_MCP or reference is None:
            deltas[arm] = {
                "pass_rate_delta_vs_skill_mcp": None,
                "mean_cost_delta_usd": None,
                "mean_duration_delta_seconds": None,
            }
            continue
        deltas[arm] = {
            "pass_rate_delta_vs_skill_mcp": _delta(
                bilan["pass_rate"], reference["pass_rate"], 4),
            "mean_cost_delta_usd": _delta(
                bilan["mean_cost_usd"], reference["mean_cost_usd"]),
            "mean_duration_delta_seconds": _delta(
                bilan["mean_duration_seconds"], reference["mean_duration_seconds"], 3),
        }
    return {
        "reference": ARM_SKILL_MCP,
        "by_arm": par_bras,
        "deltas_vs_reference": deltas,
    }


def human_answer_path(scenario: dict[str, Any], human_dir: str | Path | None) -> Path | None:
    """Retourne le fichier ``<scenario>-human.json`` attendu, existant ou non."""
    if human_dir is None:
        return None
    dossier = Path(human_dir).expanduser()
    candidats = [
        dossier / f"{scenario['slug']}-{ARM_HUMAN}.json",
        dossier / f"{scenario['id']}-{ARM_HUMAN}.json",
    ]
    for candidat in candidats:
        if candidat.is_file():
            return candidat
    return candidats[0]


def _as_bool(value: Any) -> bool:
    """Convertit une valeur JSON en booléen sans interpréter ``"false"`` comme vrai."""
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "oui", "passed", "pass", "ok"}
    return bool(value)


def _human_value(value: Any) -> Any:
    """Rend une valeur JSON humaine sans lever d'exception."""
    return value if isinstance(value, str) else _as_text(value)


def _human_criteria(payload: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Importe des critères ou grades fournis par le fichier humain."""
    valeur = payload.get("criteria", payload.get("grades"))
    criteres: list[dict[str, Any]] = []
    if isinstance(valeur, list):
        for element in valeur:
            if isinstance(element, dict):
                nom = element.get("name") or element.get("criterion") or element.get("id") or "critere"
                passe = element.get("passed", element.get("pass", element.get("ok", False)))
                detail = element.get("detail") or element.get("comment") or element.get("note") or ""
                criteres.append({"name": str(nom), "passed": _as_bool(passe), "detail": str(detail)})
            elif isinstance(element, str) and element.strip():
                criteres.append({"name": element.strip(), "passed": True, "detail": "critère importé"})
    elif isinstance(valeur, dict):
        for nom, statut in valeur.items():
            if isinstance(statut, dict):
                passe = statut.get("passed", statut.get("pass", statut.get("ok", False)))
                detail = statut.get("detail") or statut.get("comment") or statut.get("note") or ""
            else:
                passe = statut
                detail = "grade importé"
            criteres.append({
                "name": str(nom),
                "passed": _as_bool(passe),
                "detail": str(detail),
            })
    return criteres or None


def _human_base(scenario: dict[str, Any], arm: str) -> dict[str, Any]:
    """Construit le squelette commun d'un run humain."""
    return {
        "scenario": scenario["id"],
        "condition": arm,
        "arm": arm,
        "run": 1,
        "command": [],
        "cwd": "",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": 0.0,
        "duration_seconds": None,
        "timed_out": False,
        "returncode": None,
        "launch_error": "",
        "result_found": False,
        "result": "",
        "is_error": False,
        "cost_usd": None,
        "num_turns": None,
        "tool_calls": {},
        "tool_sequence": [],
        "errors": [],
        "parse_errors": [],
        "stderr": "",
        "missing": True,
        "missing_reason": "",
        "human_source": "",
    }


def load_human_run(scenario: dict[str, Any], arm: str = ARM_HUMAN,
                   human_dir: str | Path | None = None
                   ) -> tuple[dict[str, Any], Any | None]:
    """Charge une réponse humaine existante ou marque le run comme manquant."""
    run = _human_base(scenario, arm)
    chemin = human_answer_path(scenario, human_dir)
    if chemin is None:
        run["missing_reason"] = "aucun --human-dir fourni"
    elif not chemin.is_file():
        run["missing_reason"] = f"fichier humain absent : {chemin}"
        run["human_source"] = str(chemin)
    else:
        run["human_source"] = str(chemin)
        try:
            payload = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            run["missing_reason"] = f"fichier humain illisible : {chemin} ({exc})"
        else:
            if isinstance(payload, dict):
                return _human_from_payload(scenario, arm, run, payload), payload
            run["missing_reason"] = f"objet JSON attendu dans {chemin}"

    run["criteria"] = [
        {"name": "human_answer", "passed": False, "detail": run["missing_reason"]},
        *grade_run(scenario, run),
    ]
    run["passed"] = False
    return run, None


def _human_from_payload(scenario: dict[str, Any], arm: str, run: dict[str, Any],
                        payload: dict[str, Any]) -> dict[str, Any]:
    """Normalise une réponse humaine et ses grades éventuels."""
    reponse = payload.get("result")
    if reponse is None:
        reponse = payload.get("answer", payload.get("response", payload.get("text")))
    if reponse is None:
        reponses = payload.get("answers")
        if isinstance(reponses, dict):
            reponse = reponses.get(scenario["slug"], reponses.get(scenario["id"]))
        elif isinstance(reponses, str):
            reponse = reponses
    run["result"] = _human_value(reponse)
    run["cost_usd"] = _to_float(payload.get("cost_usd", payload.get("cost")))
    run["duration_seconds"] = _to_float(
        payload.get("duration_seconds", payload.get("duration")))
    run["num_turns"] = _to_int(payload.get("num_turns", payload.get("turns")))
    criteres = _human_criteria(payload)
    if criteres is None and "passed" in payload:
        criteres = [{
            "name": "human_grade",
            "passed": _as_bool(payload.get("passed")),
            "detail": "grade humain importé",
        }]
    if criteres is None:
        run["result_found"] = bool(run["result"])
        criteres = grade_run(scenario, run)
    else:
        run["result_found"] = True
    run["criteria"] = criteres
    run["passed"] = (
        _as_bool(payload.get("passed")) if "passed" in payload
        else all(critere["passed"] for critere in criteres)
    )
    run["missing"] = False
    run["missing_reason"] = ""
    return run


def save_human_run(run: dict[str, Any], output_dir: Path, run_index: int = 1,
                   payload: Any | None = None) -> dict[str, Any]:
    """Sauvegarde la réponse humaine, son résultat texte et son bilan."""
    dossier = Path(output_dir)
    dossier.mkdir(parents=True, exist_ok=True)
    prefixe = f"run-{run_index:02d}"
    chemin_brut = dossier / f"{prefixe}.human.json"
    chemin_resultat = dossier / f"{prefixe}.result.txt"
    chemin_bilan = dossier / f"{prefixe}.json"
    if payload is None:
        payload = {
            "missing": run.get("missing", False),
            "reason": run.get("missing_reason", ""),
            "scenario": run["scenario"],
            "arm": run["arm"],
        }
    _write_json(chemin_brut, payload)
    chemin_resultat.write_text(run.get("result") or "", encoding="utf-8")
    run["artifacts"] = {
        "human": str(chemin_brut),
        "result": str(chemin_resultat),
        "summary": str(chemin_bilan),
    }
    _write_json(chemin_bilan, run)
    return run


def print_dry_run(scenarios: list[dict[str, Any]], args: argparse.Namespace,
                  mcp_config: str | None, repo_root: Path,
                  arms: list[str] | None = None, checklist: str | None = None) -> None:
    """Affiche les commandes prévues sans exécuter ni écrire de résultats."""
    arms = arms or arms_depuis_args(args)
    espaces = Path(tempfile.gettempdir()) / "meridian-benchmark-empty"
    for scenario in scenarios:
        print(f"# Scénario {scenario['id']} ({scenario['slug']})")
        for arm in arms:
            if arm == ARM_HUMAN:
                source = human_answer_path(scenario, getattr(args, "human_dir", None))
                emplacement = str(source) if source is not None else "<--human-dir non fourni>"
                print(f"# Bras {arm} : import {emplacement} (aucune commande Claude)")
                continue
            cwd = repo_root if arm_utilise_skill(arm) else espaces
            print(f"# Bras {arm}, cwd={cwd}")
            for run_index in range(1, args.runs + 1):
                commande = build_command(scenario, mcp_config, args, arm=arm, checklist=checklist)
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
        "data_pack": scenario.get("data_pack"),
        "expected_terms": scenario["expected_terms"],
        "forbidden_terms": scenario["forbidden_terms"],
        "expected_sections": scenario["expected_sections"],
        "max_seconds": scenario["max_seconds"],
        "max_cost": scenario["max_cost"],
        "must_complete": scenario["must_complete"],
    }


def run_benchmark(scenarios: list[dict[str, Any]], args: argparse.Namespace,
                  repo_root: Path, output_dir: Path, mcp_config: str | None,
                  mcp_trace: dict[str, Any],
                  checklist: str | None = None) -> dict[str, Any]:
    """Exécute tous les scénarios et bras puis écrit le résumé global."""
    arms = arms_depuis_args(args)
    tous_les_runs: list[dict[str, Any]] = []
    bilans_scenarios = []
    for scenario in scenarios:
        runs_scenario: list[dict[str, Any]] = []
        for arm in arms:
            dossier_arm = output_dir / scenario["slug"] / arm
            if arm == ARM_HUMAN:
                run, payload = load_human_run(
                    scenario, arm, getattr(args, "human_dir", None))
                save_human_run(run, dossier_arm, 1, payload)
                runs_scenario.append(run)
                tous_les_runs.append(run)
                continue
            for run_index in range(1, args.runs + 1):
                commande = build_command(
                    scenario, mcp_config, args, arm=arm, checklist=checklist)
                if arm_utilise_skill(arm):
                    run = run_once(
                        scenario=scenario,
                        condition=arm,
                        command=commande,
                        cwd=repo_root,
                        output_dir=dossier_arm,
                        run_index=run_index,
                        timeout=args.timeout,
                        arm=arm,
                    )
                else:
                    with tempfile.TemporaryDirectory(prefix="meridian-benchmark-empty-") as espace:
                        run = run_once(
                            scenario=scenario,
                            condition=arm,
                            command=commande,
                            cwd=Path(espace),
                            output_dir=dossier_arm,
                            run_index=run_index,
                            timeout=args.timeout,
                            arm=arm,
                        )
                runs_scenario.append(run)
                tous_les_runs.append(run)
        bilan = {
            "id": scenario["id"],
            "slug": scenario["slug"],
            "scenario": _public_scenario(scenario),
            "runs": runs_scenario,
            "summary": summarize_runs(runs_scenario),
            "by_arm": summarize_by_arm(runs_scenario),
            "by_condition": summarize_by_condition(runs_scenario),
            "comparison": compare_arms(runs_scenario),
        }
        bilans_scenarios.append(bilan)
        _write_json(output_dir / scenario["slug"] / "summary.json", bilan)

    resume = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(repo_root),
        "output_dir": str(output_dir),
        "config": {
            "runs": args.runs,
            "arms": arms,
            "conditions": arms,
            "human_dir": str(getattr(args, "human_dir", "") or ""),
            "model": args.model,
            "max_budget_usd": args.max_budget_usd,
            "timeout": args.timeout,
            "mcp_config": mcp_trace,
        },
        "summary": {
            **summarize_runs(tous_les_runs),
            "by_arm": summarize_by_arm(tous_les_runs),
            "by_condition": summarize_by_condition(tous_les_runs),
        },
        "comparison": compare_arms(tous_les_runs),
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

    arms = arms_depuis_args(args)
    checklist: str | None = None
    if ARM_DATA_ONLY in arms:
        try:
            for scenario in scenarios:
                load_data_pack(scenario)
        except ScenarioError as exc:
            print(f"Erreur de data pack : {exc}", file=sys.stderr)
            return 2
    if ARM_CHECKLIST_MCP in arms:
        try:
            checklist = load_checklist()
        except BenchmarkError as exc:
            print(f"Erreur de checklist : {exc}", file=sys.stderr)
            return 2

    repo_root = REPO_ROOT
    output_dir = Path(args.output).expanduser() if args.output else default_output_dir()
    mcp_requis = any(arm_utilise_mcp(arm) for arm in arms)
    try:
        mcp_config, dossier_mcp, mcp_trace = prepare_mcp_config(
            args, repo_root, required=mcp_requis)
    except BenchmarkError as exc:
        print(f"Erreur MCP : {exc}", file=sys.stderr)
        return 2

    try:
        if args.dry_run:
            print_dry_run(scenarios, args, mcp_config, repo_root, arms, checklist)
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
                checklist=checklist,
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
