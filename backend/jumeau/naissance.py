"""Naissance d'un jumeau depuis l'atelier de commande : la commande déclenche le vrai pipeline.

Test réel d'une source GitHub, clone partiel, ingestion, inscription au registre, fiche vivante. Le jumeau naît
« en observation » : son admission reste un acte humain (bouton « Confirmer l'admission » du registre).
Sur AWS, ces étapes deviennent la machine Step Functions « Naissance » (Architecture AWS §5.2).
"""
import asyncio
import base64
import json
import logging
import os
import re
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from jumeau import gardien, registre
from jumeau.ingerer import ingerer

journal = logging.getLogger("meridian.naissance")
DEPOTS = Path(os.environ.get("JUMEAU_DEPOTS", Path.home() / ".local/share/meridian/depots"))
NOM_VALIDE = re.compile(r"[A-Za-z0-9._-]+")
BRANCHE_VALIDE = re.compile(r"[A-Za-z0-9._/-]+")
DELAI_GIT = 30


def url_depot(config):
    """URL du dépôt : explicite (`url`), sinon forge GitHub (JUMEAU_GIT_HOTE, github.com par défaut)."""
    hote = os.environ.get("JUMEAU_GIT_HOTE", "github.com")
    if config.get("url"):
        # Le serveur ne clone que depuis la forge autorisée : pas d'hôte arbitraire (SSRF) ni de chemin local,
        # sauf en développement explicite (JUMEAU_DEPOTS_LOCAUX=1).
        url = config["url"]
        if url.startswith(f"https://{hote}/") or (url.startswith("file://")
                                                  and os.environ.get("JUMEAU_DEPOTS_LOCAUX") == "1"):
            return url
        raise ValueError(f"dépôt hors de la forge autorisée ({hote})")
    organisation = (config.get("organisation") or "").strip()
    depot = (config.get("depots") or "").split(",")[0].strip()
    if not NOM_VALIDE.fullmatch(organisation) or not NOM_VALIDE.fullmatch(depot):
        raise ValueError("organisation ou dépôt invalide")
    return f"https://{hote}/{organisation}/{depot}.git"


def branche(config):
    nom = (config.get("branches") or "main").split(",")[0].strip()
    if not BRANCHE_VALIDE.fullmatch(nom) or nom.startswith("-"):
        raise ValueError(f"branche invalide : {nom!r}")
    return nom


def resoudre_secret(reference):
    """Jeton d'accès depuis sa référence : `env:NOM` (poste de développement) ou `vault:chemin#clé` (Vault KV v2).

    ponytail: authentification Vault par VAULT_TOKEN ; méthode AWS IAM de Vault sur AWS (Architecture AWS §10.5).
    """
    if not reference:
        return None
    if reference.startswith("env:"):
        valeur = os.environ.get(reference[4:])
        if not valeur:
            raise RuntimeError(f"variable {reference[4:]} absente")
        return valeur
    chemin, _, cle = (reference[6:] if reference.startswith("vault:") else reference).partition("#")
    adresse = os.environ.get("VAULT_ADDR")
    if not adresse or not os.environ.get("VAULT_TOKEN"):
        raise RuntimeError("Vault non configuré (VAULT_ADDR, VAULT_TOKEN)")
    montage = os.environ.get("VAULT_KV_MONTAGE", "secret")
    requete = urllib.request.Request(f"{adresse}/v1/{montage}/data/{chemin}",
                                     headers={"X-Vault-Token": os.environ["VAULT_TOKEN"]})
    with urllib.request.urlopen(requete, timeout=10) as r:
        return json.load(r)["data"]["data"][cle or "jeton"]


def env_git(jeton):
    """Le jeton passe par la configuration Git en variables d'environnement : ni dans l'URL, ni dans les arguments."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if jeton:
        entete = base64.b64encode(f"x-access-token:{jeton}".encode()).decode()
        env.update({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.extraHeader",
                    "GIT_CONFIG_VALUE_0": f"Authorization: Basic {entete}"})
    return env


def commande_git(args):
    return ["git", *args]


def _resultat(statut, titre=None, detail=None, action=None):
    maintenant = datetime.now(timezone.utc).strftime("%d/%m %H:%M")
    erreur = {"titre": titre, "detail": detail, "action": action} if titre else None
    return {"statut": statut, "erreur": erreur,
            "dernier_test": {"date": maintenant, "resultat": "ok" if statut == "prete" else "echec"}}


def tester_git(config):
    """Test réel : la branche déclarée est-elle lisible avec les droits fournis ?"""
    try:
        url, nom_branche = url_depot(config), branche(config)
        jeton = resoudre_secret(config.get("secret"))
    except ValueError as e:
        return _resultat("configuration_incomplete", "Configuration incomplète", str(e), "Corriger la configuration")
    except RuntimeError as e:
        return _resultat("autorisation_insuffisante", "Jeton introuvable", str(e), "Vérifier la référence du jeton")
    r = subprocess.run(commande_git(["ls-remote", "--heads", url, nom_branche]), capture_output=True, text=True,
                       env=env_git(jeton), timeout=DELAI_GIT)
    if r.returncode != 0:
        if re.search(r"Authentication|403|401|could not read Username|Permission denied", r.stderr):
            return _resultat("autorisation_insuffisante", "Accès refusé",
                             "Le jeton ne donne pas accès en lecture à ce dépôt.", "Vérifier les droits de la GitHub App")
        return _resultat("erreur_connexion", "Dépôt injoignable",
                         "Le dépôt n'a pas répondu ou n'existe pas.", "Vérifier l'organisation, le dépôt et le réseau")
    if not r.stdout.strip():
        return _resultat("perimetre_vide", "Branche absente",
                         f"La branche « {nom_branche} » n'existe pas dans ce dépôt.", "Corriger la branche")
    return _resultat("prete")


def cloner(config, cible):
    """Clone partiel (tout l'historique, sans les contenus inutiles), ou mise à jour s'il existe déjà."""
    url, nom_branche = url_depot(config), branche(config)
    env = env_git(resoudre_secret(config.get("secret")))
    if (Path(cible) / ".git").exists():
        etapes = [["-C", str(cible), "fetch", "-q", "origin", nom_branche],
                  ["-C", str(cible), "reset", "-q", "--hard", "FETCH_HEAD"]]
    else:
        Path(cible).parent.mkdir(parents=True, exist_ok=True)
        etapes = [["clone", "-q", "--filter=blob:none", "--single-branch", "--branch", nom_branche, url, str(cible)]]
    for args in etapes:
        r = subprocess.run(commande_git(args), capture_output=True, text=True, env=env, timeout=600)
        if r.returncode != 0:
            raise RuntimeError("clone impossible : dépôt injoignable ou accès refusé")
    return Path(cible)


async def _etat(db, cid, **champs):
    await db.commandes.update_one({"id": cid}, {"$set": {f"naissance.{k}": v for k, v in champs.items()}})


async def naitre(conn, db, commande, jumeau_id, rediger=None):
    """Clone, ingestion, registre, fiche vivante ; progression enregistrée dans la commande (`naissance`).

    ponytail: une seule source de code (la première source GitHub prête) par jumeau en phase 0.
    """
    source = next((s for s in commande["sources"] if s["connecteur"] == "github" and s["statut"] == "prete"), None)
    cid = commande["id"]
    if not source:
        await _etat(db, cid, etat="sans_code", etapes=[])
        return
    j = commande["jumeau"]
    jumeau = {"id": jumeau_id, "tenant_id": "local", "nom": j["nom"], "equipe": j.get("proprietaire") or "non précisée",
              "domaine": j.get("domaine"), "mission": j.get("mission")}
    etapes = []

    async def franchir(etape):
        etapes.append({"etape": etape, "quand": datetime.now(timezone.utc).isoformat()})
        await _etat(db, cid, etapes=etapes)

    await _etat(db, cid, etat="en_cours", etapes=[], debut=datetime.now(timezone.utc).isoformat())
    try:
        chemin = await asyncio.to_thread(cloner, source["config"], DEPOTS / jumeau_id)
        await franchir("clone")
        await asyncio.to_thread(ingerer, conn, jumeau, chemin)
        await registre.projeter(db, conn)
        await franchir("ingestion")
        await gardien.veiller(conn, db, jumeau_id, chemin, **({"rediger": rediger} if rediger else {}))
        await franchir("fiche")
        await _etat(db, cid, etat="ne", fin=datetime.now(timezone.utc).isoformat())
    except Exception as e:
        journal.exception("naissance de %s", jumeau_id)
        await _etat(db, cid, etat="echec", message=str(e)[:200] if isinstance(e, (RuntimeError, ValueError))
                    else "erreur pendant la naissance")
