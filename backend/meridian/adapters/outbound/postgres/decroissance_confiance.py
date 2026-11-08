"""Décroissance de confiance : érosion des beliefs et réfutation active des claims (plan Cognition IA, D2).

À chaque passe du gardien, :func:`evaluer` rejoue trois constats déterministes —
aucune IA, aucune requête réseau, uniquement des lectures bornées via psycopg :

1. **Beliefs érodés** : un BELIEF ``ACTIF`` dont
   :func:`meridian.application.beliefs.confiance_effective` passe sous
   ``seuil_belief`` est remonté dans le fil d'attention —
   ``donnees.attention = {"raison": "confiance_erodee", "confiance": …,
   "cree_le": …}``, via ``entreprise_depot.enregistrer_objet`` (version +1,
   statut inchangé). Une attention ``confiance_erodee`` déjà posée n'est pas
   réécrite : le marquage est idempotent et ``boucle.revalider`` /
   ``boucle.revoir`` l'effacent en reconstruisant l'objet canonique.

2. **ACCEPTED sans revalidation** : un claim ``ACCEPTED`` courant dont la
   dernière preuve ``SUPPORT`` a plus de ``seuil_claim_jours`` — ou qui n'en a
   plus aucune — est remonté ``raison: "preuve_perimee"``. Son statut ne change
   pas : c'est à l'équipe de le revalider.

3. **Réfutation active** : un claim ``ACCEPTED`` courant portant au moins une
   preuve ``CONTRE`` postérieure à son dernier ``SUPPORT`` passe ``CONTESTED``
   via :func:`depot.reviser` — la ``revue`` écrite est l'audit de la transition —
   et remonte ``raison: "refutation_posterieure"``. Une preuve de réfutation ne
   reste jamais silencieuse sur un claim accepté.

Le fil d'attention des claims n'est pas ``donnees.attention`` — la table
``claim`` n'a pas de ``donnees`` — mais la mémoire prospective : chaque claim
remonté reçoit une intention déjà échue (statut ``a_faire``, échéance à
l'instant de la passe) dont ``donnees.raison`` porte la raison. L'identifiant
est déterministe : une intention existante — même close — n'est jamais recréée,
comme un détecteur ne rouvre pas un besoin tranché. Sans table
``memoire_prospective`` montée, la contestation a quand même lieu : la revue et
le rapport gardent la trace, l'intention attendra une passe où le store répond.

Fail-closed : toute erreur par élément (persistance refusée, transition
refusée) remonte dans ``erreurs`` du rapport, jamais avalée ; l'élément est
rejoué à la passe suivante. Au plus ``quota`` actions par run, dans un ordre
déterministe : beliefs érodés, claims périmés, claims contestés.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from meridian.adapters.outbound.postgres import (
    depot, detecteurs_besoins, entreprise_depot, memoire_prospective,
)
from meridian.application import beliefs as croyances
from meridian.domain import memoire_prospective as domaine_prospectif

__all__ = [
    "DecroissanceInvalide",
    "QUOTA_DEFAUT",
    "SEUIL_BELIEF_DEFAUT",
    "SEUIL_CLAIM_JOURS_DEFAUT",
    "SOURCE",
    "evaluer",
]

SOURCE = "decroissance_confiance"
QUOTA_DEFAUT = 50
SEUIL_BELIEF_DEFAUT = 0.3
SEUIL_CLAIM_JOURS_DEFAUT = 180
_LIMITE_LECTURE = 1000
_ABSENT = object()


class DecroissanceInvalide(ValueError):
    """Un paramètre de l'évaluation ne respecte pas son contrat."""


def _tenant(valeur: Any) -> str:
    return detecteurs_besoins._tenant(valeur)


def _texte(valeur: Any, maximum: int = 1000) -> str:
    return detecteurs_besoins._texte(valeur, maximum)


def _donnees(ligne: Any) -> dict:
    return detecteurs_besoins._donnees(ligne)


def _instant(valeur: Any = None) -> datetime:
    try:
        return detecteurs_besoins._instant(valeur)
    except detecteurs_besoins.DetectionInvalide as exc:
        raise DecroissanceInvalide(str(exc)) from exc


def _borne(valeur: Any, champ: str, minimum: int = 1, maximum: int = 1000) -> int:
    try:
        return detecteurs_besoins._borne(
            valeur, champ, minimum=minimum, maximum=maximum)
    except detecteurs_besoins.DetectionInvalide as exc:
        raise DecroissanceInvalide(str(exc)) from exc


def _seuil_confiance(valeur: Any) -> float:
    if isinstance(valeur, bool):
        raise DecroissanceInvalide("seuil_belief doit être dans [0, 1]")
    try:
        seuil = float(valeur)
    except (TypeError, ValueError) as exc:
        raise DecroissanceInvalide("seuil_belief doit être dans [0, 1]") from exc
    if not 0.0 < seuil <= 1.0:
        raise DecroissanceInvalide("seuil_belief doit être dans [0, 1]")
    return seuil


def _id_stable(prefixe: str, *parties: Any) -> str:
    return detecteurs_besoins._id_stable(prefixe, *parties)


def _en_datetime(valeur: Any) -> datetime | None:
    if isinstance(valeur, datetime):
        instant = valeur
    else:
        try:
            instant = datetime.fromisoformat(str(valeur or "").replace("Z", "+00:00"))
        except ValueError:
            return None
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant


# --- Sources bornées ---


def _lire_beliefs(conn: Any, tenant: str) -> list[dict]:
    """Beliefs du tenant ; seuls les ACTIF courants sont des candidats à l'érosion."""
    lignes = entreprise_depot.lister_objets(conn, tenant, type_="BELIEF", limite=_LIMITE_LECTURE)
    return [
        ligne for ligne in lignes
        if ligne.get("valide_jusqua") is None
        and _texte(_donnees(ligne).get("statut") or "ACTIF").upper() == "ACTIF"
    ]


def _lire_claims_acceptes(conn: Any, tenant: str) -> list[dict]:
    """Claims ACCEPTED courants, avec leur dernier SUPPORT et leur première CONTRE postérieure.

    Le second ``LATERAL`` lit ``s.le`` : sans aucun SUPPORT, n'importe quelle
    CONTRE compte comme postérieure — un claim accepté dont le soutien a été
    défait et réfuté ne peut pas rester accepté silencieusement.
    """
    try:
        with conn.transaction():  # savepoint : la transaction de l'appelant survit
            with conn.cursor(row_factory=dict_row) as cur:
                return [dict(ligne) for ligne in cur.execute(
                    """SELECT c.id, c.jumeau_id, c.sujet, c.predicat, c.objet, j.equipe,
                              s.le AS dernier_support,
                              r.preuve_id, r.locator, r.observee_le AS refute_le
                       FROM claim c
                       JOIN jumeau j ON j.id = c.jumeau_id
                       LEFT JOIN LATERAL (
                           SELECT max(p.observee_le) AS le
                           FROM claim_preuve cp JOIN preuve p ON p.id = cp.preuve_id
                           WHERE cp.claim_id = c.id AND cp.role = 'SUPPORT'
                       ) s ON true
                       LEFT JOIN LATERAL (
                           SELECT p.id AS preuve_id, p.locator, p.observee_le
                           FROM claim_preuve cp JOIN preuve p ON p.id = cp.preuve_id
                           WHERE cp.claim_id = c.id AND cp.role = 'CONTRE'
                             AND p.observee_le > coalesce(s.le, '-infinity'::timestamptz)
                           ORDER BY p.observee_le, p.id LIMIT 1
                       ) r ON true
                       WHERE c.tenant_id = %s AND c.statut = 'ACCEPTED'
                         AND c.valide_jusqua IS NULL
                       ORDER BY c.id LIMIT %s""",
                    (tenant, _LIMITE_LECTURE)).fetchall()]
    except psycopg.errors.UndefinedTable:
        return []


# --- Actions ---


def _payload_attention(ligne: Mapping, **donnees_maj: Any) -> dict:
    """Ligne prête à persister : ``donnees`` fusionnées, version laissée au dépôt (+1)."""
    payload = {cle: valeur for cle, valeur in ligne.items() if cle != "version"}
    charge = _donnees(ligne)
    charge.update(donnees_maj)
    payload["donnees"] = charge
    return payload


def _marquer_belief(
    conn: Any, tenant: str, ligne: Mapping, confiance_effective: float,
    instant: datetime, persister: Callable,
) -> dict:
    """Pose ``donnees.attention`` sur le belief érodé ; statut inchangé."""
    donnees = _donnees(ligne)
    deja = isinstance(donnees.get("attention"), Mapping) and _texte(
        donnees["attention"].get("raison")) == "confiance_erodee"
    entree = {
        "cible": "belief",
        "id": _texte(ligne.get("id")),
        "raison": "confiance_erodee",
        "confiance": confiance_effective,
        "deja": deja,
    }
    if deja:
        return entree
    persister(conn, tenant, _payload_attention(
        ligne, attention={
            "raison": "confiance_erodee",
            "confiance": confiance_effective,
            "cree_le": instant.isoformat(timespec="seconds"),
        }))
    return entree


def _intention_claim(
    conn: Any, tenant: str, claim: Mapping, raison: str, instant: datetime,
    creer_intention: Callable,
) -> dict:
    """Remonte le claim dans la mémoire prospective : intention déjà échue, identifiant stable."""
    claim_id = claim["id"]
    enonce = _texte(
        f"{claim.get('sujet')} · {claim.get('predicat')} · {claim.get('objet')}", 300)
    libelle = (
        f"Connaissance contestée par une réfutation : {enonce}"
        if raison == "refutation_posterieure"
        else f"Revalider la connaissance acceptée (preuve périmée) : {enonce}")
    intention = domaine_prospectif.Intention(
        tenant_id=tenant,
        objet=_texte(libelle, 1000),
        echeance=instant.isoformat(timespec="seconds"),
        scope="tenant",
        scope_id="",
        source=SOURCE,
        owner=_texte(claim.get("equipe"), 200) or "equipe",
        priorite="haute" if raison == "refutation_posterieure" else "normale",
        evidence_ids=(str(claim_id),),
        donnees={
            "raison": raison,
            "claim_id": claim_id,
            "jumeau_id": _texte(claim.get("jumeau_id")),
            "signature": SOURCE,
        },
        id=_id_stable("intention", tenant, SOURCE, raison, claim_id),
    )
    ligne = creer_intention(conn, intention)
    cree_avant = _en_datetime((ligne or {}).get("created_at"))
    return {
        "cible": "claim",
        "id": claim_id,
        "raison": raison,
        "intention_id": _texte((ligne or {}).get("id")) or intention.id,
        # L'intention pré-existait (même close) : le claim était déjà remonté.
        "deja": bool(cree_avant is not None and cree_avant < instant),
    }


def _marquer_claim(conn: Any, claim_id: Any, raison: str, instant: datetime) -> None:
    """Pose ``donnees.attention`` (dict unifié) sur le claim — fail-soft si la colonne manque."""
    try:
        conn.execute(
            "UPDATE claim SET donnees = coalesce(donnees, '{}'::jsonb) || %s WHERE id = %s",
            (Jsonb({"attention": {"raison": raison,
                                  "depuis": instant.isoformat(timespec="seconds")}}),
             claim_id))
    except Exception:
        journal.warning("decroissance : attention claim %s non écrite", claim_id, exc_info=True)


def _contester(
    conn: Any, claim: Mapping, reviser: Callable,
) -> dict:
    """ACCEPTED → CONTESTED par la voie existante : revue écrite, puis statut."""
    motif = _texte(
        f"preuve de réfutation postérieure au soutien : {claim.get('locator')}"
        f" (observée le {claim.get('refute_le')})", 500)
    return reviser(conn, claim["id"], SOURCE, "CONTESTED", motif)


# --- Évaluation ---


def evaluer(
    conn: Any, tenant_id: Any, *, maintenant: Any = None,
    seuil_belief: Any = SEUIL_BELIEF_DEFAUT,
    seuil_claim_jours: Any = SEUIL_CLAIM_JOURS_DEFAUT,
    quota: Any = QUOTA_DEFAUT,
    beliefs: Iterable[Mapping] | None = None,
    claims: Iterable[Mapping] | None = None,
    persister: Callable | None = None,
    reviser: Callable | None = None,
    creer_intention: Callable | None = _ABSENT,
) -> dict:
    """Évalue l'érosion des beliefs et la fraîcheur/réfutation des claims ACCEPTED.

    ``beliefs`` et ``claims`` remplacent la lecture en base quand ils sont
    fournis — même contrat de colonnes que :func:`_lire_claims_acceptes`.
    ``persister(conn, tenant, objet)`` écrit l'objet d'entreprise mis à jour
    (défaut : :func:`entreprise_depot.enregistrer_objet`) ; ``reviser`` fait
    transiter le claim (défaut : :func:`depot.reviser`) ; ``creer_intention``
    pose l'intention d'attention (défaut : :func:`memoire_prospective.creer`
    quand la table est montée, ``None`` explicite la désactive).

    Rapport : ``{tenant, beliefs_erodes, claims_a_revalider, contestes,
    attention, erreurs, totaux}``. Une erreur par élément remonte dans
    ``erreurs`` — jamais avalée — et l'élément est rejoué à la passe suivante.
    """
    tenant = _tenant(tenant_id)
    instant = _instant(maintenant)
    seuil = _seuil_confiance(seuil_belief)
    jours = _borne(seuil_claim_jours, "seuil_claim_jours", maximum=3650)
    quota_ = _borne(quota, "quota", maximum=500)
    if persister is None:
        def persister(c, t, objet):
            return entreprise_depot.enregistrer_objet(c, t, objet)
    if reviser is None:
        reviser = depot.reviser
    if creer_intention is _ABSENT:
        montee = (
            conn is not None
            and detecteurs_besoins._memoire_prospective_montee(conn, tenant)
        )
        creer_intention = memoire_prospective.creer if montee else None

    lignes_beliefs = list(beliefs) if beliefs is not None else _lire_beliefs(conn, tenant)
    lignes_claims = list(claims) if claims is not None else _lire_claims_acceptes(conn, tenant)
    perime_depuis = instant - timedelta(days=jours)

    beliefs_erodes: list[dict] = []
    claims_a_revalider: list[dict] = []
    contestes: list[dict] = []
    attention: list[dict] = []
    erreurs: list[dict] = []
    produits = 0

    for ligne in sorted(lignes_beliefs, key=lambda element: _texte(element.get("id"))):
        effective = croyances.confiance_effective(ligne, instant)
        if effective >= seuil:
            continue
        if produits >= quota_:
            break
        produits += 1
        identifiant = _texte(ligne.get("id"))
        try:
            entree = _marquer_belief(
                conn, tenant, ligne, effective, instant, persister)
            beliefs_erodes.append({
                "id": identifiant,
                "confiance": effective,
                "deja": entree["deja"],
            })
            attention.append(entree)
        except Exception as exc:
            erreurs.append({"cible": "belief", "id": identifiant,
                            "erreur": str(exc)})

    perimes: list[dict] = []
    refutes: list[dict] = []
    for ligne in lignes_claims:
        support = _en_datetime(ligne.get("dernier_support"))
        contre = _en_datetime(ligne.get("refute_le"))
        if contre is not None and (support is None or contre > support):
            refutes.append(ligne)
        elif support is None or support <= perime_depuis:
            perimes.append(ligne)

    for ligne in sorted(refutes, key=lambda element: int(element["id"])):
        if produits >= quota_:
            break
        produits += 1
        claim_id = ligne["id"]
        try:
            enonce = _contester(conn, ligne, reviser)
            _marquer_claim(conn, claim_id, "refutation_posterieure", instant)
            contestes.append({
                "claim_id": claim_id,
                "jumeau_id": _texte(ligne.get("jumeau_id")),
                "preuve_id": ligne.get("preuve_id"),
                "locator": _texte(ligne.get("locator"), 400),
            })
            if creer_intention is not None:
                attention.append(_intention_claim(
                    conn, tenant, ligne, "refutation_posterieure",
                    instant, creer_intention))
            else:
                attention.append({
                    "cible": "claim", "id": claim_id,
                    "raison": "refutation_posterieure", "intention_id": "",
                    "deja": False,
                })
            if isinstance(enonce, Mapping):
                contestes[-1]["objet"] = _texte(enonce.get("objet"), 300)
        except Exception as exc:
            erreurs.append({"cible": "claim", "id": claim_id,
                            "erreur": str(exc)})

    for ligne in sorted(perimes, key=lambda element: int(element["id"])):
        if produits >= quota_:
            break
        produits += 1
        claim_id = ligne["id"]
        try:
            support = _en_datetime(ligne.get("dernier_support"))
            entree = {
                "claim_id": claim_id,
                "jumeau_id": _texte(ligne.get("jumeau_id")),
                "dernier_support": (
                    support.isoformat(timespec="seconds") if support else None),
            }
            claims_a_revalider.append(entree)
            _marquer_claim(conn, claim_id, "preuve_perimee", instant)
            if creer_intention is not None:
                attention.append(_intention_claim(
                    conn, tenant, ligne, "preuve_perimee",
                    instant, creer_intention))
            else:
                attention.append({
                    "cible": "claim", "id": claim_id,
                    "raison": "preuve_perimee", "intention_id": "",
                    "deja": False,
                })
        except Exception as exc:
            erreurs.append({"cible": "claim", "id": claim_id,
                            "erreur": str(exc)})

    return {
        "tenant": tenant,
        "beliefs_erodes": beliefs_erodes,
        "claims_a_revalider": claims_a_revalider,
        "contestes": contestes,
        "attention": attention,
        "erreurs": erreurs,
        "totaux": {
            "erodes": len(beliefs_erodes),
            "a_revalider": len(claims_a_revalider),
            "contestes": len(contestes),
            "attention": len(attention),
            "erreurs": len(erreurs),
            "quota": quota_,
        },
    }
