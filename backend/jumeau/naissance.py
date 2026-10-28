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
from urllib.parse import quote, urlparse
from datetime import datetime, timezone
from pathlib import Path

from jumeau import depot, gardien, registre
from jumeau.ingerer import ingerer

journal = logging.getLogger("meridian.naissance")
DEPOTS = Path(os.environ.get("JUMEAU_DEPOTS", Path.home() / ".local/share/meridian/depots"))
NOM_VALIDE = re.compile(r"(?!\.+$)[A-Za-z0-9._-]+")  # pas de nom fait uniquement de points (« . », « .. »)
HOTE_VALIDE = re.compile(r"[a-z0-9.-]+")
PREFIXE_VAULT = os.environ.get("JUMEAU_VAULT_PREFIXE", "meridian/")
PREFIXE_ENV = "MERIDIAN_"
BRANCHE_VALIDE = re.compile(r"[A-Za-z0-9._/-]+")
DELAI_GIT = 30


def url_depot(config):
    """URL du dépôt : explicite (`url`), sinon forge GitHub (JUMEAU_GIT_HOTE, github.com par défaut)."""
    hote = _hote_autorise()
    if config.get("url"):
        # Le serveur ne clone que depuis la forge autorisée : pas d'hôte arbitraire (SSRF) ni de chemin local,
        # sauf en développement explicite (JUMEAU_DEPOTS_LOCAUX=1). L'URL est analysée, pas comparée par préfixe.
        url = config["url"]
        u = urlparse(url)
        if u.scheme == "file" and os.environ.get("JUMEAU_DEPOTS_LOCAUX") == "1":
            return url
        if (u.scheme == "https" and u.hostname == hote and u.port is None and not u.username and not u.password
                and ".." not in u.path.split("/")):
            return url
        raise ValueError(f"dépôt hors de la forge autorisée ({hote})")
    organisation = (config.get("organisation") or "").strip()
    depot = (config.get("depots") or "").split(",")[0].strip()
    if not NOM_VALIDE.fullmatch(organisation) or not NOM_VALIDE.fullmatch(depot):
        raise ValueError("organisation ou dépôt invalide")
    return f"https://{hote}/{organisation}/{depot}.git"


def _hote_autorise():
    hote = os.environ.get("JUMEAU_GIT_HOTE", "github.com").lower()
    if not HOTE_VALIDE.fullmatch(hote):
        raise ValueError("JUMEAU_GIT_HOTE invalide : un nom d'hôte attendu")
    return hote


def branche(config):
    nom = (config.get("branches") or "main").split(",")[0].strip()
    if not BRANCHE_VALIDE.fullmatch(nom) or nom.startswith("-"):
        raise ValueError(f"branche invalide : {nom!r}")
    return nom


def _vault(chemin, donnees=None):
    """Lecture (ou écriture si `donnees`) d'un secret KV v2 sous le préfixe de Méridian."""
    if not chemin.startswith(PREFIXE_VAULT) or ".." in chemin.split("/") or not re.fullmatch(r"[\w./-]+", chemin):
        raise RuntimeError(f"chemin Vault non autorisé (préfixe {PREFIXE_VAULT} requis)")
    adresse = os.environ.get("VAULT_ADDR", "")
    if not adresse.startswith(("https://", "http://127.0.0.1")) or not os.environ.get("VAULT_TOKEN"):
        raise RuntimeError("Vault non configuré (VAULT_ADDR en https, VAULT_TOKEN)")
    montage = os.environ.get("VAULT_KV_MONTAGE", "secret")
    corps = json.dumps({"data": donnees}).encode() if donnees is not None else None
    requete = urllib.request.Request(f"{adresse}/v1/{montage}/data/{quote(chemin)}", data=corps,
                                     headers={"X-Vault-Token": os.environ["VAULT_TOKEN"],
                                              "Content-Type": "application/json"})
    with urllib.request.urlopen(requete, timeout=10) as r:
        return json.load(r)["data"]


def deposer_jeton(chemin, jeton):
    """Dépose un jeton dans Vault sous le préfixe de Méridian ; renvoie sa référence (seule conservée en base)."""
    _vault(f"{PREFIXE_VAULT}{chemin}", {"jeton": jeton})
    return f"vault:{PREFIXE_VAULT}{chemin}#jeton"


def resoudre_secret(reference):
    """Jeton d'accès depuis sa référence : `env:NOM` (poste de développement) ou `vault:chemin#clé` (Vault KV v2).

    ponytail: authentification Vault par VAULT_TOKEN ; méthode AWS IAM de Vault sur AWS (Architecture AWS §10.5).
    """
    if not reference:
        return None
    # Une commande ne peut nommer que des secrets prévus pour Méridian : jamais un autre secret du serveur.
    if reference.startswith("env:"):
        nom = reference[4:]
        if not nom.startswith(PREFIXE_ENV) or not os.environ.get(nom):
            raise RuntimeError(f"variable non autorisée ou absente (préfixe {PREFIXE_ENV} requis)")
        return os.environ[nom]
    chemin, _, cle = (reference[6:] if reference.startswith("vault:") else reference).partition("#")
    return _vault(chemin)["data"][cle or "jeton"]


def env_git(jeton):
    """Environnement minimal de Git : aucun secret du serveur hérité, configuration durcie, jeton en en-tête.

    Le jeton passe par la configuration Git en variables d'environnement : ni dans l'URL, ni dans les arguments.
    Pas de redirection HTTP (l'en-tête suivrait vers un autre hôte), pas de hooks, protocoles limités.
    """
    config = {"http.followRedirects": "false", "core.hooksPath": "/dev/null", "protocol.allow": "never",
              "protocol.https.allow": "always"}
    if os.environ.get("JUMEAU_DEPOTS_LOCAUX") == "1":
        config["protocol.file.allow"] = "always"
    if jeton:
        entete = base64.b64encode(f"x-access-token:{jeton}".encode()).decode()
        config["http.extraHeader"] = f"Authorization: Basic {entete}"
    env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG") if k in os.environ}
    env.update({"GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_COUNT": str(len(config))})
    for i, (cle, valeur) in enumerate(config.items()):
        env[f"GIT_CONFIG_KEY_{i}"], env[f"GIT_CONFIG_VALUE_{i}"] = cle, valeur
    return env


def commande_git(args):
    return ["git", *args]


def _resultat(statut, titre=None, detail=None, action=None):
    maintenant = datetime.now(timezone.utc).strftime("%d/%m %H:%M")
    erreur = {"titre": titre, "detail": detail, "action": action} if titre else None
    return {"statut": statut, "erreur": erreur,
            "dernier_test": {"date": maintenant, "resultat": "ok" if statut == "prete" else "echec"}}


def tester_git(config):
    """Test réel : chaque dépôt est-il lisible, sur sa branche, avec les droits fournis ? Premier échec rapporté."""
    try:
        configs = configs_depots(config) if "selection" in config else [config]
    except ValueError as e:
        return _resultat("configuration_incomplete", "Configuration incomplète", str(e), "Corriger la configuration")
    if not configs:
        return _resultat("configuration_incomplete", "Configuration incomplète", "Aucun dépôt choisi.",
                         "Choisir un dépôt")
    for c in configs:
        resultat = _tester_un_depot(c)
        if resultat["statut"] != "prete":
            if len(configs) > 1 and resultat["erreur"]:
                resultat["erreur"]["detail"] = f"{c['organisation']}/{c['depots']} : {resultat['erreur']['detail']}"
            return resultat
    return resultat


def _tester_un_depot(config):
    try:
        url, nom_branche = url_depot(config), branche(config)
        jeton = resoudre_secret(config.get("secret"))
    except ValueError as e:
        return _resultat("configuration_incomplete", "Configuration incomplète", str(e), "Corriger la configuration")
    except RuntimeError as e:
        return _resultat("autorisation_insuffisante", "Jeton introuvable", str(e), "Vérifier la référence du jeton")
    try:
        r = subprocess.run(commande_git(["ls-remote", "--heads", url, nom_branche]), capture_output=True, text=True,
                           env=env_git(jeton), timeout=DELAI_GIT)
    except subprocess.TimeoutExpired:
        return _resultat("erreur_connexion", "Dépôt injoignable", "Le dépôt n'a pas répondu à temps.",
                         "Vérifier le réseau")
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
    # Défense en profondeur : aucun lien symbolique versionné ne doit mener hors du dépôt.
    for lien in [c for c in Path(cible).rglob("*") if c.is_symlink() and ".git" not in c.relative_to(cible).parts]:
        lien.unlink()
    return Path(cible)


async def _etat(db, cid, **champs):
    await db.commandes.update_one({"id": cid}, {"$set": {f"naissance.{k}": v for k, v in champs.items()}})


def depots_de(config):
    """Dépôts d'une source GitHub, chacun sur sa branche : « api@main, front@develop, infra » (branche par défaut
    pour ceux qui n'en précisent pas). Une URL explicite désigne un seul dépôt."""
    defaut = branche(config)
    if config.get("url"):
        return [(Path(urlparse(config["url"]).path).stem, defaut)]
    paires = []
    for entree in (e.strip() for e in (config.get("depots") or "").split(",") if e.strip()):
        nom, _, br = entree.partition("@")
        nom, br = nom.strip(), br.strip() or defaut
        if not NOM_VALIDE.fullmatch(nom) or not BRANCHE_VALIDE.fullmatch(br) or br.startswith("-"):
            raise ValueError(f"dépôt ou branche invalide : {entree!r}")
        paires.append((nom, br))
    return paires


def configs_depots(config):
    """Une configuration par dépôt d'une source GitHub : couples dépôt/branche choisis dans l'interface
    (`selection`, « propriétaire/nom »), sinon l'ancienne saisie « dépôt@branche, … » sous une organisation."""
    if "selection" not in config:
        return [{**config, "depots": nom, "branches": br} for nom, br in depots_de(config)]
    configs = []
    for choix in config["selection"] or []:
        if not (choix.get("depot") or "").strip():
            continue  # ligne ajoutée mais pas encore remplie
        proprietaire, _, nom = choix["depot"].strip().partition("/")
        if not NOM_VALIDE.fullmatch(proprietaire) or not NOM_VALIDE.fullmatch(nom or ""):
            raise ValueError(f"dépôt attendu sous la forme propriétaire/nom : {choix['depot']!r}")
        configs.append({**{k: v for k, v in config.items() if k != "selection"}, "organisation": proprietaire,
                        "depots": nom, "branches": (choix.get("branche") or "").strip() or "main"})
    return configs


def sources_de_code(commande):
    """Chaque dépôt de chaque source GitHub prête, avec sa propre configuration (dépôt, branche)."""
    configs = [c for s in commande["sources"] if s["connecteur"] == "github" and s["statut"] == "prete"
               for c in configs_depots(s["config"])]
    # Le nom du dépôt identifie sa source, son clone et sa copie dans le jumeau : deux homonymes se mélangeraient.
    noms = [depots_de(c)[0][0] for c in configs]
    doublons = sorted({n for n in noms if noms.count(n) > 1})
    if doublons:
        raise ValueError(f"deux dépôts portent le même nom : {', '.join(doublons)}")
    return configs


async def naitre(conn, db, commande, jumeau_id, rediger=None):
    """Clone et ingère chaque dépôt (chacun sur sa branche), puis registre et fiche vivante ; progression
    enregistrée dans la commande (`naissance`)."""
    cid = commande["id"]
    try:
        configs = sources_de_code(commande)
    except ValueError as e:
        await _etat(db, cid, etat="echec", message=str(e)[:200], etapes=[])
        return
    if not configs:
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
        chemins = []
        for config in configs:
            nom = depots_de(config)[0][0]
            chemin = await asyncio.to_thread(cloner, config, DEPOTS / jumeau_id / nom)
            origine = {"branche": branche(config), "url": url_depot(config), "secret_ref": config.get("secret") or None}
            await asyncio.to_thread(ingerer, conn, jumeau, chemin, origine)
            chemins.append(chemin)
        from jumeau.systemes import SYSTEMES  # import local : les lecteurs importent ce module
        for s in commande["sources"]:
            if s["connecteur"] in SYSTEMES and s["statut"] == "prete":
                depot.declarer_source(conn, jumeau, SYSTEMES[s["connecteur"]].source_de(s["config"]))
        await franchir("clone")
        await registre.projeter(db, conn)
        await franchir("ingestion")
        await gardien.veiller(conn, db, jumeau_id, **({"rediger": rediger} if rediger else {}))
        await franchir("fiche")
        await _etat(db, cid, etat="ne", depots=[c.name for c in chemins], fin=datetime.now(timezone.utc).isoformat())
    except Exception as e:
        journal.exception("naissance de %s", jumeau_id)
        await _etat(db, cid, etat="echec", message=str(e)[:200] if isinstance(e, (RuntimeError, ValueError))
                    else "erreur pendant la naissance")
