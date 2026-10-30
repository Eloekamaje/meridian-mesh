#!/usr/bin/env python3
"""Amorce le Value Ledger du pilote Méridian depuis ``value-pilote.json``.

Le script est idempotent : il lit les valeurs déjà présentes pour le tenant et
ignore les identifiants existants. Il n'écrit jamais de résultat observé : une
hypothèse sans mesure réelle garde ``observe = null``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

RACINE = Path(__file__).resolve().parent
FICHIER = RACINE / "value-pilote.json"
API_DEFAUT = "http://127.0.0.1:8001/api"
TENANT_DEFAUT = "demo"
PERSONA = "architecte"
DELAI = 15
STATUTS_AUTORISES = frozenset({"hypothese", "mesuree"})


def charger(chemin=FICHIER):
    """Charge la liste des valeurs, quel que soit le contenant JSON."""
    donnees = json.loads(Path(chemin).read_text(encoding="utf-8"))
    if isinstance(donnees, list):
        valeurs = donnees
    elif isinstance(donnees, dict):
        valeurs = donnees.get("valeurs", donnees.get("values"))
    else:
        valeurs = None
    if not isinstance(valeurs, list):
        raise ValueError("value-pilote.json : liste 'valeurs' attendue")
    return valeurs


def _entetes(tenant, *, json_entrant=False):
    entetes = {
        "Accept": "application/json",
        "X-Persona": PERSONA,
        "X-Tenant": tenant,
    }
    if json_entrant:
        entetes["Content-Type"] = "application/json; charset=utf-8"
    return entetes


def _appel(api, tenant, methode, chemin, corps=None):
    donnees = None
    if corps is not None:
        donnees = json.dumps(corps, ensure_ascii=False).encode("utf-8")
    url = "{}{}".format(str(api).rstrip("/"), chemin)
    requete = urllib.request.Request(
        url,
        data=donnees,
        headers=_entetes(tenant, json_entrant=donnees is not None),
        method=methode,
    )
    try:
        with urllib.request.urlopen(requete, timeout=DELAI) as reponse:
            brut = reponse.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(
            "{} {} : HTTP {} {}".format(methode, chemin, exc.code, detail)
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            "{} {} : API injoignable ({})".format(methode, chemin, exc.reason)
        ) from exc
    try:
        charge = json.loads(brut) if brut else {}
    except ValueError as exc:
        raise RuntimeError(
            "{} {} : réponse non JSON".format(methode, chemin)
        ) from exc
    return charge


def _identifiants_existants(api, tenant):
    chemin = "/boucle/valeurs?" + urllib.parse.urlencode({"limite": 1000})
    charge = _appel(api, tenant, "GET", chemin)
    if isinstance(charge, list):
        lignes = charge
    elif isinstance(charge, dict):
        lignes = charge.get("valeurs", charge.get("values", []))
    else:
        lignes = []
    if not isinstance(lignes, list):
        raise RuntimeError("GET /boucle/valeurs : liste attendue")
    return {
        str(ligne.get("id"))
        for ligne in lignes
        if isinstance(ligne, dict) and ligne.get("id")
    }


def _valider(valeur):
    if not isinstance(valeur, dict):
        raise ValueError("valeur : objet attendu")
    resultat = dict(valeur)
    resultat["statut"] = str(resultat.get("statut") or "hypothese").lower()
    if resultat["statut"] not in STATUTS_AUTORISES:
        raise ValueError(
            "statut non amorçable : {}".format(resultat["statut"])
        )
    for champ in ("id", "type", "libelle", "proprietaire"):
        if not str(resultat.get(champ) or "").strip():
            raise ValueError("champ obligatoire manquant : {}".format(champ))
    hypothese = resultat["statut"] == "hypothese"
    if hypothese and resultat.get("observe") is not None:
        raise ValueError(
            "observe interdit pour une hypothèse : {}".format(resultat["id"])
        )
    if resultat["statut"] == "mesuree" and resultat.get("observe") is None:
        raise ValueError(
            "observe obligatoire pour une mesure : {}".format(resultat["id"])
        )
    return resultat


def executer(api=API_DEFAUT, tenant=TENANT_DEFAUT, dry_run=False,
             chemin=FICHIER):
    """Prépare ou applique l'amorçage et retourne un résumé JSON-compatible."""
    valeurs = [_valider(valeur) for valeur in charger(chemin)]
    identifiants = [valeur["id"] for valeur in valeurs]
    if len(set(identifiants)) != len(identifiants):
        raise ValueError("identifiants de valeur dupliqués")
    resume = {
        "api": str(api).rstrip("/"),
        "tenant": tenant,
        "dry_run": bool(dry_run),
        "total": len(valeurs),
        "a_creer": list(identifiants),
        "crees": [],
        "ignores": [],
        "erreurs": [],
        "ok": True,
    }
    if dry_run:
        return resume
    existants = _identifiants_existants(api, tenant)
    resume["a_creer"] = [
        identifiant
        for identifiant in identifiants
        if identifiant not in existants
    ]
    for valeur in valeurs:
        identifiant = valeur["id"]
        if identifiant in existants:
            resume["ignores"].append(identifiant)
            continue
        try:
            _appel(api, tenant, "POST", "/boucle/valeurs", corps=valeur)
        except (RuntimeError, ValueError, OSError) as exc:
            resume["erreurs"].append(
                {"id": identifiant, "erreur": str(exc)}
            )
        else:
            resume["crees"].append(identifiant)
    resume["ok"] = not resume["erreurs"]
    return resume


def main(argv=None):
    analyseur = argparse.ArgumentParser(
        description="Amorce les hypothèses de valeur du pilote Méridian."
    )
    analyseur.add_argument("--api", default=API_DEFAUT, help="URL de base API")
    analyseur.add_argument(
        "--tenant",
        default=TENANT_DEFAUT,
        help="Tenant cible",
    )
    analyseur.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche le plan sans contacter l'API",
    )
    arguments = analyseur.parse_args(argv)
    try:
        resume = executer(
            api=arguments.api,
            tenant=arguments.tenant,
            dry_run=arguments.dry_run,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        resume = {
            "api": str(arguments.api).rstrip("/"),
            "tenant": arguments.tenant,
            "dry_run": bool(arguments.dry_run),
            "total": 0,
            "a_creer": [],
            "crees": [],
            "ignores": [],
            "erreurs": [{"id": None, "erreur": str(exc)}],
            "ok": False,
        }
    print(json.dumps(resume, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if resume["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
