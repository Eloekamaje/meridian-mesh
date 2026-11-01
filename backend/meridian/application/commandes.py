"""Cas d'usage de la commande de jumeau : CRUD, tests de sources, import et aperçu."""
from __future__ import annotations

import logging
import secrets
from collections.abc import Awaitable, Callable, Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

from meridian.domain import import_identite
from meridian.ports.commandes import CommandesStore
from meridian.ports.naissance import NaissanceRuntime

journal = logging.getLogger("meridian")

CHAMPS_SECRETS = {"secret", "token", "jeton", "password", "passwd", "mot_de_passe",
                  "api_key", "apikey", "authorization", "bearer"}

ETAPES = (1, 2, 3, 4)

Testeur = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class CommandeIntrouvable(LookupError):
    """La commande n'existe pas dans le tenant courant."""


class CommandeModifiee(RuntimeError):
    """La commande n'est plus un brouillon modifiable."""


class EtapeInvalide(ValueError):
    """L'étape demandée ne fait pas partie du parcours de commande."""


class LancementRefuse(ValueError):
    """Le lancement ne satisfait pas une condition métier."""


class IdentiteInvalide(LancementRefuse):
    """L'identité du jumeau à créer est incomplète ou mal formée."""


class ConnecteurNonBranche(LancementRefuse):
    """Une source prête désigne un connecteur que le serveur n'implémente pas."""


class SourcePreteRequise(LancementRefuse):
    """Aucune source prête ne peut alimenter la naissance."""


class NaissanceImpossible(LancementRefuse):
    """Les sources prêtes ne fournissent ni code, ni ancre et substance."""


class JumeauExistant(RuntimeError):
    """Un jumeau porte déjà cet identifiant."""


class NaissanceIndisponible(RuntimeError):
    """La couche cognitive Postgres n'est pas configurée."""


def sans_secrets(valeur: Any) -> Any:
    """Aucune valeur secrète fournie par le client n'est persistée : seules les références Vault/env le sont."""
    if isinstance(valeur, dict):
        return {cle: sans_secrets(v) for cle, v in valeur.items()
                if str(cle).strip().lower() not in CHAMPS_SECRETS}
    if isinstance(valeur, list):
        return [sans_secrets(v) for v in valeur]
    return valeur


def proteger_source(
    source: dict[str, Any],
    connexions: Mapping[str, str],
    hotes: Mapping[str, str] | None = None,
    *,
    prefixes: Mapping[str, str],
    systemes: Iterable[str] = (),
) -> dict[str, Any]:
    """Une source GitHub, Confluence… désigne une connexion déclarée de son connecteur ; le serveur en déduit la
    référence de son jeton. Le client ne fournit jamais de référence : ni secret d'une autre connexion, ni variable
    du serveur. De même l'adresse du site (`hote`) : celle de la connexion, jamais celle du client."""
    config = sans_secrets(source.get("config")) if isinstance(source.get("config"), dict) else {}
    source = {**source, "config": config}
    prefixe = prefixes.get(source.get("connecteur"))
    if not prefixe:
        return source
    cxid = source["config"].get("connexion")
    propre = str(cxid).startswith(prefixe)
    config = {**source["config"], "secret": connexions.get(cxid, "") if propre else ""}
    systeme = "servicenow" if source["connecteur"] == "cmdb" else source["connecteur"]
    if systeme in systemes:
        config["hote"] = (hotes or {}).get(cxid, "") if propre else ""
    return {**source, "config": config}


def statut_serveur(source: dict[str, Any], avant: Mapping[str, str | None]) -> dict[str, Any]:
    """« prête » se gagne par un test de connexion sur le serveur : le client ne peut pas se l'attribuer."""
    if source.get("statut") == "prete" and avant.get(source.get("id")) != "prete":
        return {**source, "statut": avant.get(source.get("id")) or "a_configurer"}
    return source


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat()


async def creer_commande(
    store: CommandesStore,
    *,
    application_id: str = "",
    nom: str = "",
    proprietaire: str = "",
    acteur: str,
) -> dict[str, Any]:
    """Ouvre un brouillon de commande, au nom de l'acteur authentifié."""
    cid = f"cmd-{secrets.token_hex(4)}"
    doc = {
        "id": cid,
        "etat": "brouillon",
        "etape": 1,
        "jumeau": {"application_id": application_id, "nom": nom,
                    "proprietaire": proprietaire},
        "sources": [],
        "cree_par": acteur,
        "cree_le": _maintenant(),
    }
    await store.creer(doc)
    return doc


async def lister_commandes(store: CommandesStore) -> list[dict[str, Any]]:
    """Les brouillons ouverts, dans l'ordre du dépôt."""
    return await store.lister(etat="brouillon", limite=50)


async def lire_commande(store: CommandesStore, cid: str) -> dict[str, Any]:
    doc = await store.lire(cid)
    if doc is None:
        raise CommandeIntrouvable(cid)
    return doc


async def maj_commande(
    store: CommandesStore,
    cid: str,
    patch: dict[str, Any],
    *,
    prefixes: Mapping[str, str],
    systemes: Iterable[str] = (),
    maintenant: str | None = None,
) -> dict[str, Any]:
    """Met à jour un brouillon : seules les connexions déclarées fournissent secrets et hôtes."""
    patch = dict(patch)
    if not patch:
        return {"ok": True}
    if patch.get("etape") not in (None, *ETAPES):
        raise EtapeInvalide("Étape de commande invalide")
    doc = await store.lire(cid)
    if doc is None:
        raise CommandeIntrouvable(cid)
    if doc.get("etat") != "brouillon":
        raise CommandeModifiee(cid)
    if patch.get("sources"):
        docs = await store.connexions()
        connexions = {c["id"]: c["reference"] for c in docs}
        hotes = {c["id"]: c["hote"] for c in docs if c.get("hote")}
        avant = {s.get("id"): s.get("statut") for s in doc.get("sources", [])}
        patch["sources"] = [
            statut_serveur(
                proteger_source(s, connexions, hotes, prefixes=prefixes, systemes=systemes), avant
            )
            for s in patch["sources"]
        ]
    patch["maj_le"] = maintenant or _maintenant()
    if not await store.mettre_a_jour(cid, patch, etat="brouillon"):
        raise CommandeModifiee(cid)
    return {"ok": True, "maj_le": patch["maj_le"]}


async def tester_sources(
    store: CommandesStore,
    cid: str,
    ids: Iterable[str],
    *,
    tester: Testeur,
    maintenant: str | None = None,
) -> tuple[dict[str, dict[str, Any]], bool]:
    """Teste les sources demandées et persiste leurs résultats ; rend (résultats, commande modifiée)."""
    doc = await store.lire(cid)
    if doc is None:
        raise CommandeIntrouvable(cid)
    if doc.get("etat") != "brouillon":
        raise CommandeModifiee(cid)
    ids = set(ids)
    resultats: dict[str, dict[str, Any]] = {}
    for source in doc["sources"]:
        if source["id"] in ids:
            resultats[source["id"]] = await tester(source)
            source.update(resultats[source["id"]])
    if not resultats:
        return resultats, False
    if not await store.mettre_a_jour(
        cid,
        {"sources": doc["sources"], "maj_le": maintenant or _maintenant()},
        etat="brouillon",
    ):
        raise CommandeModifiee(cid)
    return resultats, True


def naissance_possible(connecteurs: Iterable[str]) -> bool:
    """Une naissance réelle exige le code (GitHub) ou l'ancre ServiceNow/CMDB et une source de substance."""
    connecteurs = set(connecteurs)
    return "github" in connecteurs or (
        bool(connecteurs & {"servicenow", "cmdb"})
        and bool(connecteurs & {"datadog", "otlp", "confluence"})
    )


async def lancer_commande(
    store: CommandesStore,
    runtime: NaissanceRuntime,
    cid: str,
    *,
    acteur: str,
    espace_id: str,
    connecteur_branche: Callable[[Any], Any],
) -> dict[str, Any]:
    """Lance la naissance d'un jumeau : validation, registre, commande et tâche de naissance."""
    doc = await store.lire(cid)
    if doc is None:
        raise CommandeIntrouvable(cid)
    if doc.get("etat") == "lancee" and doc.get("jumeau_id"):
        # Rejeu idempotent : le client a perdu la réponse du premier lancement.
        pretes = [s for s in doc.get("sources", []) if s.get("statut") == "prete"]
        return {"ok": True, "jumeau_id": doc["jumeau_id"], "sources_lancees": len(pretes),
                "sources_reportees": len(doc.get("sources", [])) - len(pretes),
                "naissance": (doc.get("naissance") or {}).get("etat"), "deja": True}
    j = doc["jumeau"]
    application_id = (j.get("application_id") or "").strip().lower()
    nom = (j.get("nom") or "").strip()
    proprietaire = (j.get("proprietaire") or "").strip()
    if not application_id or not nom or not proprietaire:
        raise IdentiteInvalide("Identité incomplète (application_id, nom et propriétaire requis)")
    if len(nom) > 200 or len(proprietaire) > 200:
        raise IdentiteInvalide("Nom ou propriétaire trop long (200 caractères maximum)")
    if not import_identite.APPLICATION_ID.fullmatch(application_id):
        raise IdentiteInvalide("application_id invalide (minuscules, chiffres, . _ -)")
    j = {**j, "application_id": application_id, "nom": nom, "proprietaire": proprietaire}
    doc = {**doc, "jumeau": j}
    pretes = [s for s in doc.get("sources", []) if s.get("statut") == "prete"]
    non_branchees = [s for s in pretes if not connecteur_branche(s.get("connecteur"))]
    if non_branchees:
        noms = ", ".join(sorted({str(s.get("nom") or s.get("connecteur")) for s in non_branchees}))
        raise ConnecteurNonBranche(f"Connecteur non branché dans les sources prêtes : {noms}")
    if not pretes:
        raise SourcePreteRequise("Au moins une source prête est requise pour lancer")
    if not runtime.disponible():
        raise NaissanceIndisponible("La naissance nécessite la couche cognitive Postgres (JUMEAU_PG_DSN).")
    connecteurs = {s.get("connecteur") for s in pretes}
    if not naissance_possible(connecteurs):
        raise NaissanceImpossible(
            "Aucune source prête ne permet une naissance : ajoutez GitHub, ou ServiceNow/CMDB "
            "avec Datadog, OTLP ou Confluence.",
        )
    jid = application_id
    if runtime.en_cours(jid) or await store.jumeau_existe(jid):
        raise JumeauExistant("Un jumeau porte déjà cet identifiant — choisissez un autre App ID")
    nouveau = {
        "id": jid, "nom": nom, "domaine": "Non classé", "mission": "",
        "proprietaire": proprietaire,
        "statut": "observation", "autonomie": "aucune",
        "couverture": min(20 + len(pretes) * 9, 88), "fraicheur": "à l'instant", "sante": "inconnu",
        "position": {"x": 1260, "y": 40},
        "sources": {s.get("connecteur"): True for s in pretes if s.get("connecteur")},
    }
    if not await store.inserer_jumeau(nouveau):
        raise JumeauExistant("Un jumeau porte déjà cet identifiant — choisissez un autre App ID")
    maintenant = _maintenant()
    etat_commande = {"etat": "lancee", "jumeau_id": jid, "lancee_le": maintenant,
                     "naissance": {"etat": "en_cours", "debut": maintenant}}
    await store.marquer_lancee(cid, etat_commande)
    await runtime.demarrer(doc, jid, acteur=acteur, espace_id=espace_id)
    return {"ok": True, "jumeau_id": jid, "sources_lancees": len(pretes),
            "sources_reportees": len(doc.get("sources", [])) - len(pretes), "naissance": "en_cours"}


async def notifier_naissance(runtime: NaissanceRuntime, jid: str, texte: str) -> None:
    """Une notification manquée ne masque pas l'échec déjà journalisé."""
    try:
        await runtime.notifier(jid, texte)
    except Exception:  # noqa: BLE001 - la commande reflète déjà l'issue, la notification reste secondaire
        journal.warning("notification de naissance impossible", exc_info=True)


async def echec_naissance(
    store: CommandesStore,
    runtime: NaissanceRuntime,
    commande: Mapping[str, Any],
    jid: str,
    message: str,
    *,
    maintenant: str | None = None,
) -> None:
    """La commande reflète un échec de naissance, jamais un état « en cours » qui ne finirait pas."""
    await store.marquer_echec_naissance(commande["id"], message, maintenant or _maintenant())
    nom = (commande.get("jumeau") or {}).get("nom") or jid
    await notifier_naissance(runtime, jid, f"La naissance de {nom} a échoué : {message}.")


async def apercu_import(
    store: CommandesStore,
    cid: str,
    mode: str,
    contenu: Any,
    *,
    connus: Iterable[str] | None = None,
) -> dict:
    """Valide l'import et rend l'aperçu, sans écrire ni créer de source."""
    doc = await store.lire(cid)
    if doc is None:
        raise CommandeIntrouvable(cid)
    if doc.get("etat") != "brouillon":
        raise CommandeModifiee(cid)
    prepare = import_identite.preparer(
        contenu,
        mode,
        [(s.get("connecteur"), s.get("nom")) for s in doc.get("sources", [])],
        connus=list(connus) if connus is not None else None,
    )
    return {
        "mode": mode,
        "detectees": 1,
        "identite": prepare["identite"],
        "nouvelles": prepare["nouvelles"],
        "ignorees": prepare["ignorees"],
        "presentes": [{"connecteur": s.get("connecteur"), "nom": s.get("nom")}
                      for s in doc.get("sources", [])],
        "a_mapper": [],
        "message": f"{len(prepare['nouvelles'])} source(s) prêtes à importer, "
                   f"{len(prepare['ignorees'])} déjà présente(s) et ignorée(s).",
    }


async def suivre_naissance(store: CommandesStore, cid: str) -> dict:
    """État de naissance d'une commande, sans transport HTTP."""
    doc = await store.lire(cid)
    if doc is None:
        raise CommandeIntrouvable(cid)
    return {"jumeau_id": doc.get("jumeau_id"),
            **(doc.get("naissance") or {"etat": "non_lancee"})}
