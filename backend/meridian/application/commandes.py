"""Cas d'usage de la commande de jumeau : CRUD, tests de sources, import et aperçu."""
from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable, Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

from meridian.domain import import_identite
from meridian.ports.commandes import CommandesStore

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
