"""Résolution des paris datés des besoins (plan Cognition IA, C6).

Chaque NEED ou UNKNOWN détecté emporte un pari daté : une intention de la mémoire
prospective dont l'échéance est le moment où le jumeau se juge lui-même. À la passe du
gardien, :func:`verifier_paris` rouvre les intentions **dues** et ré-évalue le signal
d'origine, sans IA ni réseau — uniquement des requêtes SQL bornées via psycopg :

- ``contournement`` : le couple ``(subject, predicate)`` de ``interface_assertion``
  présente-t-il encore un ``observed`` hors ``declared`` ? (même logique que
  :mod:`detecteurs_besoins`, réutilisée)
- ``recurrence`` : le twin compte-t-il encore au moins ``seuil_recurrence``
  SITUATION canoniques sur l'une des deux fenêtres glissantes consécutives ?
- ``question_non_tranchee`` : un claim ou objet répondant à la question est-il
  apparu, ou la question a-t-elle été résolue manuellement ? (recherche lexicale
  bornée — volontairement minimal)

Verdict à l'échéance :

- signal disparu → l'intention est close ``fait`` ; le NEED transite
  ``QUALIFIE → CORROBORE`` (ou ``OUVERT → QUALIFIE`` quand la transition est
  applicable), l'UNKNOWN passe ``RESOLU`` ;
- signal persistant → l'intention est close ``expire`` et l'objet remonte dans le
  fil d'attention : ``donnees.attention = {"raison": "intention_expiree", ...}``.

Un NEED ``OUVERT``/``QUALIFIE`` de signature connue sans ``intention_id`` reçoit un
pari daté à la première passe (``creer_paris``) : c'est ce qui rend le besoin jugeable
à échéance — B7 ne pose pas d'intention sur les NEED ``contournement``/``recurrence``.

C4 : chaque pari daté est aussi une prédiction calibrée — ``_ouvrir_pari`` écrit
la prédiction ``ouverte`` dans ``prediction_calibration`` et chaque jugement la
résout (``succes`` si le besoin est corroboré/résolu, ``echec`` s'il expire) ;
le pari daté alimente ainsi le Brier réel sans écriture supplémentaire.

Fail-closed : toute erreur (intention introuvable, transition refusée, persistance
refusée) remonte dans ``erreurs`` du rapport, jamais avalée ; l'intention reste alors
ouverte et le pari est rejoué à la passe suivante.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row

from meridian.adapters.outbound.postgres import (
    boucle, calibration, detecteurs_besoins, discriminant, entreprise_depot, memoire_prospective,
)
from meridian.domain import memoire_prospective as domaine_prospectif

__all__ = [
    "STATUTS_NEED_JUGEABLES",
    "STATUTS_UNKNOWN_JUGEABLES",
    "verifier_paris",
]

STATUTS_NEED_JUGEABLES = ("OUVERT", "QUALIFIE")
STATUTS_UNKNOWN_JUGEABLES = ("OUVERT", "EN_COURS", "RESOLU")
_DESTINATIONS = {"OUVERT": "QUALIFIE", "QUALIFIE": "CORROBORE"}
_ABSENT = object()
_LIMITE_LECTURE = 500

# Mots vides bornés : le jugement lexical d'une question tranchée ne retient que
# les tokens porteurs (≥3 caractères hors cette liste).
_VIDES = frozenset((
    "avec", "dans", "elle", "elles", "entre", "est", "être", "etre", "eux", "pour",
    "quel", "quoi", "sans", "sont", "sous", "leur", "leurs", "mais", "nous", "vous",
    "cette", "quelle", "quels", "quelles", "comment", "combien", "pourquoi", "quand",
    "aussi", "alors", "ainsi", "comme", "dont", "chez", "vers", "tous", "tout",
    "toute", "toutes", "avoir", "avons", "fait", "faire", "peut", "plus", "moins",
    "qui", "que", "des", "les", "une", "aux", "ont", "pas", "non", "sur", "par",
    "ces", "ses", "son", "nos", "vos", "mes", "tes", "lui", "car", "été", "oui",
))


class ResolutionInvalide(ValueError):
    """Un pari ne peut pas être jugé : signature inconnue, sujet absent."""


def _tenant(valeur: Any) -> str:
    return detecteurs_besoins._tenant(valeur)


def _texte(valeur: Any, maximum: int = 1000) -> str:
    return detecteurs_besoins._texte(valeur, maximum)


def _donnees(ligne: Any) -> dict:
    return detecteurs_besoins._donnees(ligne)


def _instant(valeur: Any = None) -> datetime:
    return detecteurs_besoins._instant(valeur)


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


def _lire_needs(conn: Any, tenant: str) -> list[dict]:
    return entreprise_depot.lister_objets(conn, tenant, type_="NEED", limite=1000)


def _lire_unknowns(conn: Any, tenant: str) -> list[dict]:
    return entreprise_depot.lister_objets(conn, tenant, type_="UNKNOWN", limite=1000)


def _lire_intentions_dues(conn: Any, tenant: str, instant: datetime) -> list[dict]:
    return memoire_prospective.echeances(conn, tenant, maintenant=instant, limite=_LIMITE_LECTURE)


def _lire_claims(conn: Any, tenant: str) -> list[dict]:
    """Claims du tenant, bornés ; une table absente rend une liste vide."""
    try:
        with conn.transaction():  # savepoint : la transaction de l'appelant survit
            with conn.cursor(row_factory=dict_row) as cur:
                return [dict(ligne) for ligne in cur.execute(
                    "SELECT sujet, predicat, objet, statut, enregistre_le FROM claim "
                    "WHERE tenant_id = %s ORDER BY enregistre_le DESC LIMIT %s",
                    (tenant, _LIMITE_LECTURE)).fetchall()]
    except psycopg.errors.UndefinedTable:
        return []


def _lire_intention(conn: Any, tenant: str, intention_id: str) -> dict | None:
    """Lit l'intention ; ``None`` si la table ou la ligne est absente."""
    try:
        with conn.transaction():  # savepoint : une table absente ne casse pas la passe
            return memoire_prospective.lire(conn, tenant, intention_id)
    except psycopg.errors.UndefinedTable:
        return None


# --- Charge des besoins jugeables ---


def _statut(ligne: Mapping) -> str:
    return _texte(_donnees(ligne).get("statut")).upper()


def _intention_id(ligne: Mapping) -> str:
    return _texte(_donnees(ligne).get("intention_id"))


def _candidats(needs: Iterable[Mapping], unknowns: Iterable[Mapping]) -> dict[str, dict]:
    """Objets jugeables indexés par identifiant : NEED OUVERT/QUALIFIE, UNKNOWN vivants."""
    candidats: dict[str, dict] = {}
    for ligne in needs or ():
        if _statut(ligne) in STATUTS_NEED_JUGEABLES:
            candidats[_texte(ligne.get("id"))] = {"objet": ligne, "genre": "NEED"}
    for ligne in unknowns or ():
        if _statut(ligne) in STATUTS_UNKNOWN_JUGEABLES:
            candidats[_texte(ligne.get("id"))] = {"objet": ligne, "genre": "UNKNOWN"}
    return candidats


def _lier_paris(
    candidats: dict[str, dict], intentions: Iterable[Mapping],
) -> dict[str, dict]:
    """Complète les liens intention → objet quand l'objet ne porte pas ``intention_id``.

    ``question_non_tranchee`` écrit ``donnees.unknown_id`` côté intention ; le même
    convention vaut pour ``need_id``. ``evidence_ids`` sert de repli.
    """
    for intention in intentions or ():
        identifiant = _texte(intention.get("id"))
        donnees = _donnees(intention)
        references = {_texte(donnees.get("need_id")), _texte(donnees.get("unknown_id"))}
        references.update(_texte(ref) for ref in (intention.get("evidence_ids") or ()))
        for reference in references:
            if not reference or reference not in candidats:
                continue
            entree = candidats[reference]
            if _intention_id(entree["objet"]):
                continue
            entree["intention_id"] = identifiant
    return candidats


# --- Ré-évaluation des signaux ---


def _sujet_contournement(donnees: Mapping) -> tuple[str, str]:
    sujet = _texte(donnees.get("sujet_detection"))
    if "|" in sujet:
        premiere, seconde = sujet.split("|", 1)
        return _texte(premiere), _texte(seconde)
    for preuve in (donnees.get("preuves") or ()):
        if isinstance(preuve, Mapping) and preuve.get("subject") and preuve.get("predicate"):
            return _texte(preuve.get("subject")), _texte(preuve.get("predicate"))
    raise ResolutionInvalide("contournement : couple (subject, predicate) introuvable")


def _persiste_contournement(donnees: Mapping, assertions: Iterable[Mapping]) -> bool:
    sujet, predicat = _sujet_contournement(donnees)
    for contradiction in detecteurs_besoins._contradictions_assertions(assertions):
        if (contradiction["subject"] == sujet and contradiction["predicate"] == predicat
                and contradiction["excedent"]):
            return True
    return False


def _twin_recurrence(donnees: Mapping) -> str:
    sujet = _texte(donnees.get("sujet_detection"))
    if sujet.startswith("twin:"):
        return _texte(sujet[5:])
    twin_ids = [str(t).strip() for t in (donnees.get("twin_ids") or ()) if str(t).strip()]
    if twin_ids:
        return twin_ids[0]
    raise ResolutionInvalide("recurrence : twin introuvable")


def _persiste_recurrence(
    donnees: Mapping, situations: Iterable[Mapping], seuil: int,
    fenetre_jours: int, instant: datetime,
) -> bool:
    """Vrai tant qu'une des deux fenêtres glissantes consécutives atteint le seuil."""
    twin = _twin_recurrence(donnees)
    borne_recente = instant - timedelta(days=fenetre_jours)
    borne_ancienne = instant - timedelta(days=2 * fenetre_jours)
    recentes = precedentes = 0
    for ligne in situations or ():
        if twin not in detecteurs_besoins._twin_ids_situation(ligne):
            continue
        observe = _en_datetime(ligne.get("observe_le") or _donnees(ligne).get("observe_le"))
        if observe is None or observe > instant or observe < borne_ancienne:
            continue
        if observe >= borne_recente:
            recentes += 1
        else:
            precedentes += 1
    return recentes >= seuil or precedentes >= seuil


def _tokens_question(question: Any) -> list[str]:
    normalisee = detecteurs_besoins._normaliser(question)
    tokens = []
    for token in normalisee.split():
        if len(token) >= 3 and token not in _VIDES and token not in tokens:
            tokens.append(token)
    return tokens


def _question_resolue(
    ligne: Mapping, claims: Iterable[Mapping], seuil_tokens: int = 2,
) -> bool:
    """Question tranchée : marque manuelle (``RESOLU``/``resolution_claim_id``) ou
    claim partageant au moins ``seuil_tokens`` tokens porteurs de la question."""
    donnees = _donnees(ligne)
    if _statut(ligne) == "RESOLU" or _texte(donnees.get("resolution_claim_id")):
        return True
    resolution = donnees.get("resolution")
    if isinstance(resolution, Mapping) and (
            resolution.get("claim_id") or resolution.get("reponse")
            or _texte(resolution.get("statut")).lower() in {"resolu", "tranche", "tranchee"}):
        return True
    tokens = _tokens_question(donnees.get("question"))
    if not tokens:
        return False
    cree_le = _en_datetime(ligne.get("cree_le") or donnees.get("cree_le"))
    attendu = min(seuil_tokens, len(tokens))
    for claim in claims or ():
        if cree_le is not None:
            enregistre = _en_datetime(claim.get("enregistre_le") or claim.get("cree_le"))
            if enregistre is not None and enregistre < cree_le:
                continue
        texte = detecteurs_besoins._normaliser(
            " ".join(_texte(claim.get(cle)) for cle in ("sujet", "predicat", "objet", "titre")))
        if texte and sum(1 for token in tokens if token in texte) >= attendu:
            return True
    return False


def _signal_present(
    conn: Any, tenant: str, entree: Mapping, intention: Mapping, *,
    assertions: Iterable[Mapping] | None, situations: Iterable[Mapping] | None,
    claims: Iterable[Mapping] | None, seuil: int, fenetre_jours: int,
    instant: datetime,
) -> bool:
    """Ré-évalue le signal d'origine du pari ; ``True`` s'il persiste encore."""
    objet = entree["objet"]
    donnees = _donnees(objet)
    signature = _texte(donnees.get("signature")) or _texte(
        _donnees(intention).get("signature"))
    if not signature and entree["genre"] == "UNKNOWN":
        signature = "question_non_tranchee"
    if signature == "contournement":
        lot = (assertions if assertions is not None
               else detecteurs_besoins._lire_assertions(conn, tenant))
        return _persiste_contournement(donnees, lot)
    if signature == "recurrence":
        lot = (situations if situations is not None
               else detecteurs_besoins._lire_situations(
                   conn, tenant, instant - timedelta(days=2 * fenetre_jours)))
        return _persiste_recurrence(donnees, lot, seuil, fenetre_jours, instant)
    if signature == "question_non_tranchee":
        lot = claims if claims is not None else _lire_claims(conn, tenant)
        return not _question_resolue(objet, lot)
    raise ResolutionInvalide(f"signature inconnue : {signature or '(absente)'}")


# --- Verdicts ---


def _question_socratique(conn: Any, tenant: str, besoin_id: Any) -> Any:
    """La question à valeur maximale du besoin (hypothèses rivales) — fail-soft, jamais bloquante."""
    try:
        suggestion = discriminant.suggestions(conn, tenant, besoin_id)
    except Exception:
        return None
    if isinstance(suggestion, Mapping):
        return suggestion.get("question_socratique")
    return None


def _payload_mis_a_jour(ligne: Mapping, **donnees_maj: Any) -> dict:
    """Ligne prête à persister : ``donnees`` fusionnées, version laissée au dépôt."""
    payload = {cle: valeur for cle, valeur in ligne.items() if cle != "version"}
    charge = _donnees(ligne)
    charge.update(donnees_maj)
    payload["donnees"] = charge
    return payload


def _clore(clore_intention: Callable | None, conn: Any, tenant: str,
           intention_id: str, statut: str, motif: str) -> dict | None:
    if clore_intention is None:
        return None
    return clore_intention(conn, tenant, intention_id, statut=statut,
                           acteur="resolution_besoins", motif=motif)


# --- C4 : le pari daté est une prédiction calibrée ---


def _confiance_besoin(ligne: Mapping) -> float:
    """Confiance portée par l'objet ; ``CONFIANCE_DETECTEUR`` en repli (0,5)."""
    donnees = _donnees(ligne)
    for cle in ("confiance", "confiance_detecteur"):
        try:
            valeur = float(donnees.get(cle))
        except (TypeError, ValueError):
            continue
        if 0 <= valeur <= 1:
            return valeur
    return detecteurs_besoins.CONFIANCE_DETECTEUR


def _calibrer_pari(
    conn: Any, tenant: str, *, intention_id: Any, besoin_id: Any,
    signature: Any, confiance: Any, echeance: Any = None, outcome: Any = None,
) -> Any:
    """Écrit ou résout la prédiction du pari ; identifiant déterministe par intention.

    ``outcome=None`` ouvre la prédiction datée ; ``True``/``False`` la résout
    (``succes``/``echec``). Un pari rejoué vise la même ligne : la prédiction
    déjà résolue n'est pas réécrite.
    """
    tenant_propre = _tenant(tenant)
    identifiant = calibration.identifiant_prediction(
        tenant_propre, f"pari:{_texte(intention_id)}", confiance)
    existante = calibration.lire(conn, tenant_propre, identifiant)
    if existante is None:
        return calibration.enregistrer_prediction(conn, tenant_propre, {
            "id": identifiant,
            "sujet": _texte(besoin_id),
            "probabilite": confiance,
            "echeance": echeance,
            "source": _texte(signature) or "pari",
            "decision_id": _texte(besoin_id) or _texte(intention_id),
            "outcome": outcome,
        })
    if outcome is not None and existante.outcome is None:
        return calibration.resoudre(conn, tenant_propre, identifiant, outcome)
    return existante


def _tenter_calibration(calibrer: Callable | None, erreurs: list, **pari: Any) -> None:
    """Une écriture de calibration refusée remonte dans ``erreurs`` — jamais avalée."""
    if calibrer is None:
        return
    try:
        calibrer(**pari)
    except Exception as exc:
        erreurs.append({"besoin": pari.get("besoin_id"),
                        "intention_id": pari.get("intention_id"),
                        "erreur": f"calibration refusée : {exc}"})


def _ouvrir_pari(
    conn: Any, tenant: str, ligne: Mapping, signature: str, instant: datetime,
    echeance_jours: int, creer_intention: Callable,
) -> str:
    """Pose le pari daté d'un NEED : intention de vérification + ``intention_id``."""
    besoin_id = _texte(ligne.get("id"))
    echeance = (instant + timedelta(days=echeance_jours)).isoformat(timespec="seconds")
    titre = _texte(ligne.get("titre") or _donnees(ligne).get("ecart"), 200)
    intention = domaine_prospectif.Intention(
        tenant_id=tenant,
        objet=_texte(f"Vérifier le besoin {signature} : {titre or besoin_id}", 1000),
        echeance=echeance,
        scope="tenant",
        scope_id="",
        source="resolution_besoins",
        owner="gardien",
        priorite="normale",
        evidence_ids=(besoin_id,),
        donnees={"need_id": besoin_id, "signature": signature,
                 "pari": "verification"},
        id=_id_stable("intention", tenant, "verification", besoin_id),
    )
    cree = creer_intention(conn, intention)
    ligne_cree = dict(cree) if isinstance(cree, Mapping) else intention.as_dict()
    return _texte(ligne_cree.get("id")) or intention.id, ligne_cree


def verifier_paris(
    conn: Any, tenant_id: Any, *, maintenant: Any = None,
    fenetre_jours: int = detecteurs_besoins.FENETRE_JOURS_DEFAUT,
    seuil_recurrence: int = detecteurs_besoins.SEUIL_RECURRENCE,
    echeance_jours: int = detecteurs_besoins.ECHEANCE_INTENTION_JOURS,
    needs: Iterable[Mapping] | None = None,
    unknowns: Iterable[Mapping] | None = None,
    intentions: Iterable[Mapping] | None = None,
    assertions: Iterable[Mapping] | None = None,
    situations: Iterable[Mapping] | None = None,
    claims: Iterable[Mapping] | None = None,
    persister: Callable | None = None,
    clore_intention: Callable | None = None,
    creer_intention: Callable | None = _ABSENT,
    creer_paris: bool = True,
    calibrer: Callable | None = _ABSENT,
) -> dict:
    """Juge les paris datés arrivés à échéance et rend le rapport de la passe.

    Les paramètres ``needs``, ``unknowns``, ``intentions``, ``assertions``,
    ``situations`` et ``claims`` remplacent la lecture en base quand ils sont
    fournis — mode READ sans fixture DB, comme :func:`detecteurs_besoins.detecter`.
    ``persister(conn, tenant, objet)`` écrit l'objet mis à jour (défaut :
    :func:`boucle.enregistrer_boucle`) ; ``clore_intention`` clôt l'intention
    (défaut : :func:`memoire_prospective.clore`) ; ``creer_intention`` pose un
    pari daté sur les NEED de signature connue encore sans intention
    (défaut : :func:`memoire_prospective.creer`, ``None`` explicite ou
    ``creer_paris=False`` désactive) ; ``calibrer`` écrit la prédiction du pari
    dans ``prediction_calibration`` — ouverte à la pose, résolue au jugement
    (défaut : :func:`_calibrer_pari` quand une connexion est fournie, ``None``
    explicite ou ``conn=None`` désactive ; C4).

    Rapport : ``{tenant, evalues, corroborés, resolus, persistants, expires,
    paris_ouverts, erreurs, totaux}``. Une erreur par besoin remonte dans
    ``erreurs`` — jamais avalée — et l'intention concernée reste ouverte.
    """
    tenant = _tenant(tenant_id)
    fenetre_jours = detecteurs_besoins._borne(fenetre_jours, "fenetre_jours", maximum=3650)
    seuil = detecteurs_besoins._borne(seuil_recurrence, "seuil_recurrence", minimum=2, maximum=50)
    echeance_jours = detecteurs_besoins._borne(echeance_jours, "echeance_jours", maximum=365)
    instant = _instant(maintenant)
    if persister is None:
        def persister(c, t, objets):
            return boucle.enregistrer_boucle(c, t, objets)
    montee = (intentions is not None
              or detecteurs_besoins._memoire_prospective_montee(conn, tenant))
    if clore_intention is None and montee:
        clore_intention = memoire_prospective.clore
    if creer_intention is _ABSENT:
        creer_intention = memoire_prospective.creer if montee else None
    if calibrer is _ABSENT:
        calibrer = _calibrer_pari if conn is not None else None

    lignes_needs = list(needs) if needs is not None else _lire_needs(conn, tenant)
    lignes_unknowns = (
        list(unknowns) if unknowns is not None else _lire_unknowns(conn, tenant))
    index: dict[str, dict] = {}
    lot_intentions: list[dict] = []
    if intentions is not None:
        for intention in intentions:
            ligne = dict(intention)
            index[_texte(ligne.get("id"))] = ligne
            lot_intentions.append(ligne)
    elif montee:
        lot_intentions = _lire_intentions_dues(conn, tenant, instant)
        index = {_texte(i.get("id")): i for i in lot_intentions}

    def lire_intention(identifiant: str) -> dict | None:
        if identifiant in index:
            return index[identifiant]
        if not montee or conn is None:
            return None
        ligne = _lire_intention(conn, tenant, identifiant)
        if ligne is not None:
            index[identifiant] = ligne
        return ligne

    evalues: list[dict] = []
    corroborés: list[dict] = []
    resolus: list[dict] = []
    persistants: list[dict] = []
    expires: list[dict] = []
    paris_ouverts: list[dict] = []
    erreurs: list[dict] = []

    candidats = _lier_paris(_candidats(lignes_needs, lignes_unknowns), lot_intentions)

    # Un NEED de signature connue sans pari daté en reçoit un : il devient jugeable
    # à l'échéance posée, puis évalué à la passe qui la voit due.
    if creer_paris and creer_intention is not None:
        for identifiant in sorted(candidats):
            entree = candidats[identifiant]
            if entree["genre"] != "NEED":
                continue
            ligne, donnees = entree["objet"], _donnees(entree["objet"])
            if _intention_id(ligne) or entree.get("intention_id"):
                continue
            signature = _texte(donnees.get("signature"))
            if signature not in detecteurs_besoins.SIGNATURES:
                continue
            try:
                intention_id, ligne_intention = _ouvrir_pari(
                    conn, tenant, ligne, signature, instant, echeance_jours,
                    creer_intention)
                index[intention_id] = ligne_intention  # due dans echeance_jours : pas jugée à cette passe
                persister(conn, tenant, _payload_mis_a_jour(
                    ligne, intention_id=intention_id))
            except Exception as exc:
                erreurs.append({"besoin": identifiant, "signature": signature,
                                "erreur": f"pari refusé : {exc}"})
                continue
            entree["intention_id"] = intention_id
            echeance = instant + timedelta(days=echeance_jours)
            paris_ouverts.append({"besoin": identifiant, "signature": signature,
                                  "intention_id": intention_id,
                                  "echeance": echeance.isoformat(timespec="seconds")})
            # C4 : le pari ouvert est une prédiction datée, résolue au jugement.
            _tenter_calibration(
                calibrer, erreurs, conn=conn, tenant=tenant,
                intention_id=intention_id, besoin_id=identifiant,
                signature=signature, confiance=_confiance_besoin(ligne),
                echeance=echeance, outcome=None)

    for identifiant in sorted(candidats):
        entree = candidats[identifiant]
        ligne = entree["objet"]
        intention_id = _intention_id(ligne) or entree.get("intention_id")
        if not intention_id:
            continue
        try:
            intention = lire_intention(intention_id)
            if intention is None:
                raise ResolutionInvalide(f"intention introuvable : {intention_id}")
            if not domaine_prospectif.est_due(intention, instant):
                continue
            signature = _texte(_donnees(ligne).get("signature")) or _texte(
                _donnees(intention).get("signature")) or "question_non_tranchee"
            present = _signal_present(
                conn, tenant, entree, intention, assertions=assertions,
                situations=situations, claims=claims, seuil=seuil,
                fenetre_jours=fenetre_jours, instant=instant)
            evaluation = {"besoin": identifiant, "genre": entree["genre"],
                          "signature": signature, "intention_id": intention_id,
                          "issue": "signal_present" if present else "signal_disparu"}
            evalues.append(evaluation)
            if present:
                _clore(clore_intention, conn, tenant, intention_id, "expire",
                       "signal encore présent à l'échéance")
                maj = {"intention_id": intention_id,
                       "attention": {"raison": "intention_expiree",
                                     "depuis": instant.isoformat(timespec="seconds")}}
                question = _question_socratique(conn, tenant, identifiant)
                if question:
                    maj["question_socratique"] = question
                persister(conn, tenant, _payload_mis_a_jour(ligne, **maj))
                persistants.append(evaluation)
                expires.append({"intention_id": intention_id, "besoin": identifiant})
            elif entree["genre"] == "UNKNOWN":
                persister(conn, tenant, _payload_mis_a_jour(
                    ligne, statut="RESOLU", intention_id=intention_id,
                    verification={"intention_id": intention_id,
                                  "verdict": "signal_disparu",
                                  "le": instant.isoformat(timespec="seconds")}))
                _clore(clore_intention, conn, tenant, intention_id, "fait",
                       "question tranchée à l'échéance")
                resolus.append(evaluation)
            else:
                destination = _DESTINATIONS[_statut(ligne)]
                transite = boucle.transiter_need(ligne, destination)
                persister(conn, tenant, _payload_mis_a_jour(
                    ligne, statut=transite.statut, intention_id=intention_id,
                    verification={"intention_id": intention_id,
                                  "verdict": "signal_disparu",
                                  "le": instant.isoformat(timespec="seconds")}))
                _clore(clore_intention, conn, tenant, intention_id, "fait",
                       f"signal disparu : besoin {transite.statut}")
                corroborés.append(evaluation)
            # C4 : le pari jugé devient une prédiction résolue — corroboré/résolu
            # = succes, expiré = echec. L'écriture n'annule pas le verdict.
            _tenter_calibration(
                calibrer, erreurs, conn=conn, tenant=tenant,
                intention_id=intention_id, besoin_id=identifiant,
                signature=signature, confiance=_confiance_besoin(ligne),
                echeance=intention.get("echeance") if isinstance(intention, Mapping) else None,
                outcome=not present)
        except Exception as exc:  # fail-closed : l'intention reste ouverte, le pari est rejoué
            erreurs.append({"besoin": identifiant, "intention_id": intention_id,
                            "erreur": str(exc)})
    return {
        "tenant": tenant,
        "evalues": evalues,
        "corroborés": corroborés,
        "resolus": resolus,
        "persistants": persistants,
        "expires": expires,
        "paris_ouverts": paris_ouverts,
        "erreurs": erreurs,
        "totaux": {
            "evalues": len(evalues), "corroborés": len(corroborés),
            "resolus": len(resolus), "persistants": len(persistants),
            "expires": len(expires), "paris_ouverts": len(paris_ouverts),
            "erreurs": len(erreurs),
        },
    }
