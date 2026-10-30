#!/usr/bin/env python3
"""Fige les réponses de ``/boucle/analyser`` dans des paquets reproductibles.

Le script ne fait que lire : il interroge l'API en lecture seule, assainit la
réponse et l'écrit sous ``data/<scenario>.json``. Idempotent : les durées
volatiles sont retirées et un fichier identique n'est pas réécrit. Aucun
secret n'est accepté en argument et les clés ou jetons sensibles sont masqués.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping

RACINE = Path(__file__).resolve().parent
SCENARIOS = RACINE / "scenarios"
SORTIE_DEFAUT = RACINE / "data"
API_DEFAUT = "http://127.0.0.1:8001/api"
TENANT_DEFAUT = "demo"
PERSONA_DEFAUT = "architecte"
DELAI_DEFAUT = 30.0
CHAMPS_PAQUET = ("profil", "composition", "dossier", "reponse")
CHAMPS_VOLATILES = frozenset({"duree_ms"})

_MARQUEURS_SECRETS = (
    "password",
    "passwd",
    "secret",
    "token",
    "credential",
    "authorization",
)
_CLES_SECRETES = frozenset({
    "pwd",
    "pass",
    "auth",
    "key",
    "apikey",
    "api_key",
    "api-key",
    "access_key",
    "accesskey",
    "private_key",
    "privatekey",
    "client_secret",
    "clientsecret",
    "bearer",
    "password",
    "passwd",
})
_JETON_SENSIBLE = re.compile(
    r"(?i)(?:\bbearer\s+[A-Za-z0-9_.~+/=-]{12,}|\bsk-[A-Za-z0-9_-]{8,}|"
    r"\bgh[pousr]_[A-Za-z0-9]{10,}|\bxox[baprs]-[A-Za-z0-9-]{10,})"
)
_URL_AVEC_IDENTIFIANTS = re.compile(r"(?i)[a-z][a-z0-9+.-]*://[^/\s@]+@")
_PARAMETRE_SECRET = re.compile(
    r"(?i)([?&](?:token|secret|password|passwd|key|apikey|api_key)=)[^&\s]+"
)


class FreezeError(RuntimeError):
    """Erreur de lecture, d'appel API ou d'écriture du paquet de données."""


def _cle_sensible(cle: Any) -> bool:
    """Indique si une clé JSON doit être masquée."""
    normalisee = str(cle).strip().lower()
    if normalisee.endswith(("_ref", "-ref", "_reference", "-reference")):
        return False
    compacte = normalisee.replace("-", "_")
    if compacte in _CLES_SECRETES:
        return True
    if compacte.endswith("_key"):
        return True
    return any(marque in compacte for marque in _MARQUEURS_SECRETS)


def _chaine_sensible(valeur: str) -> bool:
    """Indique si une chaîne contient un jeton ou des identifiants d'URL."""
    if _JETON_SENSIBLE.search(valeur):
        return True
    if _URL_AVEC_IDENTIFIANTS.search(valeur):
        return True
    return bool(_PARAMETRE_SECRET.search(valeur))


def assainir(valeur: Any) -> Any:
    """Masque récursivement les clés et valeurs sensibles, sans mutation."""
    if isinstance(valeur, Mapping):
        resultat = {}
        for cle, contenu in valeur.items():
            nom = str(cle)
            resultat[nom] = "***" if _cle_sensible(nom) else assainir(contenu)
        return resultat
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return [assainir(element) for element in valeur]
    if isinstance(valeur, str):
        return "***" if _chaine_sensible(valeur) else valeur
    if valeur is None or isinstance(valeur, (bool, int, float)):
        return valeur
    return assainir(str(valeur))


def charger_scenario(chemin: Path) -> dict[str, Any]:
    """Charge et valide le minimum nécessaire pour appeler l'API."""
    try:
        donnees = json.loads(Path(chemin).read_text(encoding="utf-8"))
    except OSError as exc:
        raise FreezeError(f"lecture impossible de {chemin} : {exc}") from exc
    except json.JSONDecodeError as exc:
        raise FreezeError(f"JSON invalide dans {chemin} : {exc}") from exc
    if not isinstance(donnees, dict):
        raise FreezeError(f"{chemin} : objet JSON attendu")
    identifiant = donnees.get("id")
    prompt = donnees.get("prompt")
    contexte = donnees.get("context")
    if not isinstance(identifiant, str) or not identifiant.strip():
        raise FreezeError(f"{chemin} : champ id obligatoire")
    if not isinstance(prompt, str) or not prompt.strip():
        raise FreezeError(f"{chemin} : champ prompt obligatoire")
    if contexte is not None and not isinstance(contexte, dict):
        raise FreezeError(f"{chemin} : champ context objet attendu")
    return donnees


def construire_payload(scenario: Mapping[str, Any]) -> dict[str, Any]:
    """Construit le corps de ``POST /boucle/analyser`` depuis un scénario."""
    contexte = scenario.get("context") or {}
    payload: dict[str, Any] = {"question": str(scenario["prompt"]).strip()}
    correspondances = (
        ("situation_id", "situation"),
        ("application_id", "application"),
        ("scope", "scope"),
        ("domaine", "domaine"),
        ("profil", "profil"),
    )
    for champ_api, cle in correspondances:
        valeur = contexte.get(cle)
        if valeur is None:
            continue
        if not isinstance(valeur, str) or not valeur.strip():
            raise FreezeError(f"context.{cle} doit être une chaîne non vide")
        payload[champ_api] = valeur.strip()

    twins = contexte.get("twins", contexte.get("twin_ids"))
    if twins is not None:
        if not isinstance(twins, list) or not all(
                isinstance(twin, str) and twin.strip() for twin in twins):
            raise FreezeError(
                "context.twins doit être une liste de chaînes non vides"
            )
        payload["twin_ids"] = [twin.strip() for twin in twins]
    return payload


def _entetes(tenant: str, persona: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "X-Persona": persona,
        "X-Tenant": tenant,
    }


def appeler_api(api: str, tenant: str, persona: str,
                payload: Mapping[str, Any],
                timeout: float = DELAI_DEFAUT) -> dict[str, Any]:
    """Appelle ``/boucle/analyser`` et retourne la réponse assainie."""
    url = f"{str(api).rstrip('/')}/boucle/analyser"
    corps = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    requete = urllib.request.Request(
        url,
        data=corps,
        headers=_entetes(tenant, persona),
        method="POST",
    )
    try:
        with urllib.request.urlopen(requete, timeout=timeout) as reponse:
            brut = reponse.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise FreezeError(
            f"POST /boucle/analyser : HTTP {exc.code} {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise FreezeError(
            f"POST /boucle/analyser : API injoignable ({exc.reason})"
        ) from exc
    except OSError as exc:
        raise FreezeError(f"POST /boucle/analyser : {exc}") from exc
    try:
        charge = json.loads(brut) if brut else {}
    except json.JSONDecodeError as exc:
        raise FreezeError("POST /boucle/analyser : réponse non JSON") from exc
    if not isinstance(charge, dict):
        raise FreezeError("POST /boucle/analyser : objet JSON attendu")
    return assainir(charge)


def _retirer_volatils(valeur: Any) -> Any:
    """Retire les mesures de durée pour rendre les paquets reproductibles."""
    if isinstance(valeur, Mapping):
        return {
            str(cle): _retirer_volatils(contenu)
            for cle, contenu in valeur.items()
            if str(cle) not in CHAMPS_VOLATILES
        }
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return [_retirer_volatils(element) for element in valeur]
    return valeur


def extraire_paquet(charge: Mapping[str, Any]) -> dict[str, Any]:
    """Ne conserve que les quatre sections, sans mesures volatiles."""
    manquants = [champ for champ in CHAMPS_PAQUET if champ not in charge]
    if manquants:
        raise FreezeError(
            "réponse incomplète, champs absents : " + ", ".join(manquants)
        )
    return {
        champ: _retirer_volatils(charge[champ])
        for champ in CHAMPS_PAQUET
    }


def ecrire_idempotent(chemin: Path, donnees: Mapping[str, Any]) -> bool:
    """Écrit le JSON s'il diffère ; vrai si le fichier a changé."""
    chemin = Path(chemin)
    texte = json.dumps(
        donnees, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    if chemin.is_file():
        try:
            if chemin.read_text(encoding="utf-8") == texte:
                return False
        except OSError:
            pass
    chemin.parent.mkdir(parents=True, exist_ok=True)
    descripteur, nom = tempfile.mkstemp(
        prefix=f".{chemin.name}.", suffix=".tmp", dir=str(chemin.parent)
    )
    try:
        with os.fdopen(descripteur, "w", encoding="utf-8") as fichier:
            fichier.write(texte)
        os.replace(nom, chemin)
    except Exception:
        try:
            os.unlink(nom)
        except OSError:
            pass
        raise
    return True


def _chemins_scenarios(chemins: Iterable[str | Path] | None) -> list[Path]:
    if chemins:
        resultat = []
        for chemin_brut in chemins:
            chemin = Path(chemin_brut).expanduser()
            if chemin.is_dir():
                resultat.extend(sorted(chemin.glob("*.json")))
            else:
                resultat.append(chemin)
    else:
        resultat = sorted(SCENARIOS.glob("*.json"))
    uniques = []
    vus = set()
    for chemin in resultat:
        cle = str(chemin.resolve())
        if cle not in vus:
            vus.add(cle)
            uniques.append(chemin)
    if not uniques:
        raise FreezeError("aucun scénario à figer")
    return uniques


def executer(chemins: Iterable[str | Path] | None = None,
             api: str = API_DEFAUT,
             tenant: str = TENANT_DEFAUT, persona: str = PERSONA_DEFAUT,
             sortie: str | Path = SORTIE_DEFAUT, dry_run: bool = False,
             timeout: float = DELAI_DEFAUT) -> dict[str, Any]:
    """Fige les scénarios et retourne un résumé JSON-compatible."""
    sortie = Path(sortie)
    resume: dict[str, Any] = {
        "api": str(api).rstrip("/"),
        "tenant": tenant,
        "persona": persona,
        "sortie": str(sortie),
        "dry_run": bool(dry_run),
        "appels": [],
        "ecrits": [],
        "inchanges": [],
        "erreurs": [],
        "ok": True,
    }
    try:
        chemins_scenarios = _chemins_scenarios(chemins)
    except FreezeError as exc:
        resume["erreurs"].append({"scenario": None, "erreur": str(exc)})
        resume["ok"] = False
        return resume

    vus: set[str] = set()
    for chemin in chemins_scenarios:
        try:
            scenario = charger_scenario(chemin)
            identifiant = str(scenario["id"]).strip()
            if identifiant in vus:
                raise FreezeError(
                    f"identifiant de scénario dupliqué : {identifiant}"
                )
            vus.add(identifiant)
            payload = construire_payload(scenario)
            contexte = scenario.get("context") or {}
            tenant_scenario = str(contexte.get("tenant") or tenant)
            persona_scenario = str(contexte.get("persona") or persona)
            appel = {
                "scenario": identifiant,
                "scenario_file": str(chemin),
                "tenant": tenant_scenario,
                "persona": persona_scenario,
                "payload": payload,
            }
            resume["appels"].append(appel)
            if dry_run:
                continue
            charge = appeler_api(
                api=api,
                tenant=tenant_scenario,
                persona=persona_scenario,
                payload=payload,
                timeout=timeout,
            )
            paquet = extraire_paquet(charge)
            destination = sortie / f"{identifiant}.json"
            change = ecrire_idempotent(destination, paquet)
            appel["sortie"] = str(destination)
            liste = resume["ecrits"] if change else resume["inchanges"]
            liste.append(identifiant)
        except (FreezeError, OSError, ValueError) as exc:
            resume["erreurs"].append(
                {"scenario": str(chemin), "erreur": str(exc)}
            )
    resume["ok"] = not resume["erreurs"]
    return resume


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée CLI du figeur de données."""
    analyseur = argparse.ArgumentParser(
        description="Fige les réponses /boucle/analyser en paquets.",
    )
    analyseur.add_argument(
        "--scenario",
        action="append",
        help=("Fichier ou dossier de scénarios "
              "(répétable ; défaut : scenarios/)."),
    )
    analyseur.add_argument(
        "--api",
        default=os.environ.get("MERIDIAN_API_URL", API_DEFAUT),
        help="URL de base de l'API Méridian.",
    )
    analyseur.add_argument(
        "--tenant",
        default=os.environ.get("MERIDIAN_TENANT", TENANT_DEFAUT),
        help="Tenant à interroger.",
    )
    analyseur.add_argument(
        "--persona",
        default=os.environ.get("MERIDIAN_PERSONA", PERSONA_DEFAUT),
        help="Persona transmis à l'API.",
    )
    analyseur.add_argument(
        "--output",
        type=Path,
        default=SORTIE_DEFAUT,
        help="Dossier des paquets gelés (défaut : data/).",
    )
    analyseur.add_argument(
        "--timeout",
        type=float,
        default=DELAI_DEFAUT,
        help="Délai maximal par appel API en secondes.",
    )
    analyseur.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche les appels prévus sans contacter l'API ni écrire.",
    )
    arguments = analyseur.parse_args(argv)
    try:
        resume = executer(
            chemins=arguments.scenario,
            api=arguments.api,
            tenant=arguments.tenant,
            persona=arguments.persona,
            sortie=arguments.output,
            dry_run=arguments.dry_run,
            timeout=arguments.timeout,
        )
    except (FreezeError, OSError, ValueError) as exc:
        resume = {
            "api": str(arguments.api).rstrip("/"),
            "tenant": arguments.tenant,
            "persona": arguments.persona,
            "sortie": str(arguments.output),
            "dry_run": bool(arguments.dry_run),
            "appels": [],
            "ecrits": [],
            "inchanges": [],
            "erreurs": [{"scenario": None, "erreur": str(exc)}],
            "ok": False,
        }
    print(json.dumps(resume, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if resume["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
