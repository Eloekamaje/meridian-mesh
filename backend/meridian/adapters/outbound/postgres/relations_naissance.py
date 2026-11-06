"""Persistance du manifeste de naissance et des propositions de relation.

Ce module est l'adapter Postgres du protocole ADR-0031. Il ne décide jamais à la place du
domaine : il lit les Claims d'interface, écrit le manifeste comme artefact, émet
`twin.born` dans l'outbox, puis persiste les propositions déterministes.
"""
from __future__ import annotations

import logging

from psycopg.rows import dict_row

from meridian.adapters.outbound.postgres import entreprise_depot
from meridian.adapters.outbound.postgres import execution_depot
from meridian.application import relations_naissance as resolution
from meridian.domain.naissance_relationnelle import (
    ManifesteNaissance,
    PropositionRelation,
    decider,
    marquer_observee,
)

journal = logging.getLogger("meridian.relations_naissance")

_TYPE_MANIFESTE = "ARTIFACT"
_FAMILLE_MANIFESTE = "sources_preuves"
_TYPE_RELATION = "RELATION"
_FAMILLE_RELATION = "connaissance"


def lire_claims_interface(conn, tenant_id: str, twin_id: str) -> list[dict]:
    """Claims EXPOSE/CONSOMME valides, avec un locator de preuve pour le manifeste."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """SELECT c.id, c.predicat, c.objet, c.statut, c.confiance::float AS confiance,
                      (SELECT p.locator FROM claim_preuve cp JOIN preuve p ON p.id = cp.preuve_id
                       WHERE cp.claim_id = c.id ORDER BY p.id DESC LIMIT 1) AS preuve
               FROM claim c
               WHERE c.tenant_id = %s AND c.jumeau_id = %s AND c.valide_jusqua IS NULL
                 AND c.predicat IN ('EXPOSE', 'CONSOMME')
                 AND c.statut NOT IN ('INVALIDATED', 'SUPERSEDED')
               ORDER BY c.predicat, c.objet""",
            (tenant_id, twin_id),
        ).fetchall()


def enregistrer_manifeste(conn, manifeste: ManifesteNaissance) -> dict:
    return entreprise_depot.enregistrer_objet(conn, manifeste.tenant_id, {
        "id": manifeste.id,
        "famille": _FAMILLE_MANIFESTE,
        "type": _TYPE_MANIFESTE,
        "mode": "DECLARED",
        "titre": f"Manifeste de naissance — {manifeste.twin_id}",
        "donnees": manifeste.as_dict(),
        "observe_le": manifeste.declared_at,
    })


def lire_manifestes(conn, tenant_id: str, *, exclude_twin_id: str | None = None) -> list[ManifesteNaissance]:
    """Dernier manifeste valide par Twin, dans le tenant."""
    objets = entreprise_depot.lister_objets(
        conn, tenant_id, famille=_FAMILLE_MANIFESTE, type_=_TYPE_MANIFESTE, limite=1000)
    par_twin: dict[str, ManifesteNaissance] = {}
    for objet in objets:
        donnees = objet.get("donnees") or {}
        if donnees.get("kind") != "manifeste_naissance":
            continue
        if exclude_twin_id and donnees.get("twin_id") == exclude_twin_id:
            continue
        try:
            manifeste = ManifesteNaissance.depuis_dict(donnees)
        except ValueError:
            journal.warning("manifeste de naissance illisible : %s", objet.get("id"))
            continue
        precedent = par_twin.get(manifeste.twin_id)
        if precedent is None or manifeste.declared_at >= precedent.declared_at:
            par_twin[manifeste.twin_id] = manifeste
    return list(par_twin.values())


def enregistrer_proposition(conn, proposition: PropositionRelation) -> dict:
    return entreprise_depot.enregistrer_objet(conn, proposition.tenant_id, {
        "id": proposition.id,
        "famille": _FAMILLE_RELATION,
        "type": _TYPE_RELATION,
        "mode": proposition.mode,
        "titre": f"{proposition.consumer_id} → {proposition.provider_id} · {proposition.object}",
        "donnees": proposition.as_dict(),
    })


def lister_propositions(conn, tenant_id: str, *, twin_id: str | None = None,
                        state: str | None = None, limite: int = 1000) -> list[dict]:
    if state and str(state).strip().lower() in ("proposee", "proposée"):
        state = "supposee"
    objets = entreprise_depot.lister_objets(
        conn, tenant_id, famille=_FAMILLE_RELATION, type_=_TYPE_RELATION, limite=limite)
    sortie = []
    for objet in objets:
        donnees = objet.get("donnees") or {}
        if donnees.get("kind") != "proposition_naissance":
            continue
        if twin_id and twin_id not in (donnees.get("consumer_id"), donnees.get("provider_id")):
            continue
        if state and str(donnees.get("state") or "").lower() != str(state).lower():
            continue
        sortie.append({**donnees, "id": objet.get("id"), "version": objet.get("version")})
    return sortie


def review_proposition(conn, tenant_id: str, proposition_id: str, *, decision: str,
                       acteur: str, motif: str = "", confirmations=(), critique: bool | None = None,
                       gouvernance: bool = False) -> PropositionRelation:
    objet = entreprise_depot.lire_objet(conn, tenant_id, proposition_id)
    if objet is None:
        raise LookupError("proposition de relation introuvable")
    donnees = objet.get("donnees") or {}
    if donnees.get("kind") != "proposition_naissance":
        raise LookupError("cet objet n'est pas une proposition de relation")
    proposition = PropositionRelation.depuis_dict(donnees)
    tranchee = decider(proposition, decision, acteur, motif=motif,
                       confirmations=confirmations,
                       critique=proposition.critique if critique is None else critique,
                       gouvernance=gouvernance)
    enregistrer_proposition(conn, tranchee)
    return tranchee


def observer_proposition(conn, tenant_id: str, proposition_id: str, *,
                         evidence_ids=(), observed_at: str = "") -> PropositionRelation:
    objet = entreprise_depot.lire_objet(conn, tenant_id, proposition_id)
    if objet is None:
        raise LookupError("proposition de relation introuvable")
    donnees = objet.get("donnees") or {}
    if donnees.get("kind") != "proposition_naissance":
        raise LookupError("cet objet n'est pas une proposition de relation")
    proposition = marquer_observee(
        PropositionRelation.depuis_dict(donnees), observed_at=observed_at,
        evidence_ids=evidence_ids)
    enregistrer_proposition(conn, proposition)
    return proposition


def _evenement_existe(conn, tenant_id: str, type_: str, twin_id: str, birth_run_id: str) -> bool:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """SELECT id FROM execution_outbox
               WHERE tenant_id = %s AND type = %s
                 AND payload->>'twin_id' = %s AND payload->>'birth_run_id' = %s
               LIMIT 1""",
            (tenant_id, type_, twin_id, birth_run_id),
        ).fetchone() is not None


def emettre_twin_born(conn, manifeste: ManifesteNaissance) -> bool:
    """Émet l'événement après la naissance, une seule fois par (twin, run)."""
    if _evenement_existe(conn, manifeste.tenant_id, "twin.born",
                         manifeste.twin_id, manifeste.birth_run_id):
        return False
    payload = manifeste.as_dict()
    with conn.transaction():
        execution_depot.ajouter_evenement(
            conn, manifeste.tenant_id, manifeste.birth_run_id, "twin.born", payload)
        execution_depot.ajouter_outbox(
            conn, manifeste.tenant_id, manifeste.birth_run_id, "twin.born", payload)
    return True


def celebrer_naissance(conn, commande, jumeau, *, partial: bool = False,
                       acteur: str = "naissance", naissance_etat: str = "ne") -> dict:
    """Après `naissance.etat = ne`, produit le manifeste, l'événement et les propositions."""
    resolution.verifier_prealables_naissance(commande, jumeau, naissance_etat)
    tenant = jumeau.get("tenant_id") or commande.get("tenant_id") or "local"
    twin_id = jumeau.get("id") or commande.get("jumeau_id")
    claims = lire_claims_interface(conn, tenant, twin_id)
    manifeste = resolution.manifeste_depuis_claims(
        commande, jumeau, claims, birth_run_id=commande["id"], partial=partial,
        declared_by=acteur)
    enregistrer_manifeste(conn, manifeste)
    emis = emettre_twin_born(conn, manifeste)
    existants = lire_manifestes(conn, tenant, exclude_twin_id=twin_id)
    resultat = resolution.proposer_relations(manifeste, existants)
    for proposition in resultat.propositions:
        enregistrer_proposition(conn, proposition)
    return {
        "manifeste": manifeste.as_dict(),
        "evenement_emis": emis,
        "propositions": [p.as_dict() for p in resultat.propositions],
        "sans_candidat": list(resultat.sans_candidat),
    }


def traiter_twin_born(conn, payload) -> dict:
    """Consommateur idempotent de `twin.born` : reconstruit les propositions manquantes."""
    manifeste = ManifesteNaissance.depuis_dict(payload)
    existants = lire_manifestes(conn, manifeste.tenant_id, exclude_twin_id=manifeste.twin_id)
    resultat = resolution.proposer_relations(manifeste, existants)
    for proposition in resultat.propositions:
        enregistrer_proposition(conn, proposition)
    return {"propositions": len(resultat.propositions),
            "sans_candidat": list(resultat.sans_candidat)}


def backfill_manifestes(conn, tenant_id: str, *, appliquer: bool = False,
                        limite: int | None = None) -> dict:
    """Prépare les Twins existants avec un manifeste de migration, sans les promouvoir."""
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            """SELECT id, nom, tenant_id, equipe, type, application_id, perimetre_id
               FROM jumeau WHERE tenant_id = %s ORDER BY id""",
            (tenant_id,),
        ).fetchall()
    if limite is not None:
        lignes = lignes[:max(1, int(limite))]
    existants = {m.twin_id for m in lire_manifestes(conn, tenant_id)}
    a_creer, crees, ignores = [], [], []
    for ligne in lignes:
        if ligne["id"] in existants:
            ignores.append(ligne["id"])
            continue
        a_creer.append(ligne["id"])
        if not appliquer:
            continue
        manifeste = resolution.manifeste_legacy(dict(ligne), lire_claims_interface(
            conn, tenant_id, ligne["id"]))
        enregistrer_manifeste(conn, manifeste)
        crees.append(ligne["id"])
    return {"dry_run": not appliquer, "twins": len(lignes), "a_creer": a_creer,
            "crees": crees, "ignores": ignores}


def rafraichir_manifestes_legacy(conn, tenant_id: str, *, appliquer: bool = False,
                                 limite: int | None = None) -> dict:
    """Reconstruit les manifestes `legacy-*` après une évolution du modèle (portée, ressources)."""
    objets = entreprise_depot.lister_objets(
        conn, tenant_id, famille=_FAMILLE_MANIFESTE, type_=_TYPE_MANIFESTE, limite=1000)
    legacy = [o for o in objets
              if str((o.get("donnees") or {}).get("birth_run_id") or "").startswith("legacy-")]
    if limite is not None:
        legacy = legacy[:max(1, int(limite))]
    a_rafraichir, rafraichis, ignores = [], [], []
    for objet in legacy:
        donnees = objet.get("donnees") or {}
        twin_id = donnees.get("twin_id")
        with conn.cursor(row_factory=dict_row) as cur:
            ligne = cur.execute(
                """SELECT id, nom, tenant_id, equipe, type, application_id, perimetre_id
                   FROM jumeau WHERE tenant_id = %s AND id = %s""",
                (tenant_id, twin_id),
            ).fetchone()
        if ligne is None:
            ignores.append(twin_id)
            continue
        a_rafraichir.append(twin_id)
        if not appliquer:
            continue
        manifeste = resolution.manifeste_legacy(
            dict(ligne), lire_claims_interface(conn, tenant_id, twin_id))
        enregistrer_manifeste(conn, manifeste)
        rafraichis.append(twin_id)
    return {"dry_run": not appliquer, "a_rafraichir": a_rafraichir,
            "rafraichis": rafraichis, "ignores": ignores}
