"""Spécialiste de preuve : constate la qualité des preuves d'un dossier, sans jamais écrire.

Il lit les Claims du tenant (et les ``claim_ids`` / ``twin_ids`` demandés), puis propose des constats et
des risques : claim sans preuve SUPPORT, claim faible ou contesté, preuve périmée, doublon contradictoire.
Aucune promotion, aucune réouverture, aucune action n'est exécutée : les propositions portent seulement
des identifiants d'action qu'un humain peut examiner.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from meridian.domain import temporalite
from meridian.domain.specialistes import ContexteSpecialiste, Proposition, ResultatSpecialiste

__all__ = ["SpecialistePreuve", "construire_propositions", "lire_claims"]

NOM = "preuve"
SEUIL_CONFIANCE_FAIBLE = 0.5
SEUIL_FRAICHEUR_JOURS = 30
MAX_CLAIMS = 200
MAX_REFS = 40

TITRE_SANS_PREUVE = "Claim sans preuve suffisante"
TITRE_CONTESTE = "Claim contesté/faible"
TITRE_PERIMEE = "Preuve périmée"
TITRE_CONTRADICTION = "Contradiction"
TITRE_SUFFISANTES = "Preuves suffisantes"

_RE_MOT_DE_PASSE_URL = re.compile(r"(?i)(://)[^/@\s:]+:[^/@\s]+@")
_RE_IDENTIFIANT_URL_SENSIBLE = re.compile(
    r"(?i)(\b(?:https?|ftp|postgres(?:ql)?|redis|mongodb(?:\+srv)?)://)[^/@\s]+@")
_SCHEMES_IDENTIFIANTS = frozenset({
    "git", "declaration", "confluence", "jira", "servicenow", "datadog", "otlp",
})
_CLES_SENSIBLES = ("password", "passwd", "secret", "token", "credential", "authorization", "key")
_COLONNES = (
    "id", "tenant_id", "twin_id", "sujet", "predicat", "objet", "type", "statut", "maturite",
    "confiance", "valide_depuis", "valide_jusqua", "enregistre_le", "origine", "preuves",
)
_REQUETE = """
SELECT c.id, c.tenant_id, c.jumeau_id AS twin_id, c.sujet, c.predicat, c.objet, c.type,
       c.statut, c.maturite, c.confiance::float AS confiance, c.valide_depuis, c.valide_jusqua,
       c.enregistre_le, c.origine,
       (SELECT coalesce(json_agg(json_build_object(
            'id', p.id, 'type', p.type, 'locator', p.locator, 'chemin', p.chemin, 'sha', p.sha,
            'ligne_debut', p.ligne_debut, 'ligne_fin', p.ligne_fin, 'hash', p.hash,
            'role', cp.role, 'observee_le', p.observee_le) ORDER BY p.id), '[]')
        FROM claim_preuve cp JOIN preuve p ON p.id = cp.preuve_id
        WHERE cp.claim_id = c.id) AS preuves
FROM claim c
WHERE {conditions}
ORDER BY c.id
LIMIT %s
"""


def _cle_sensible(cle) -> bool:
    compacte = str(cle or "").lower().replace("-", "_")
    return any(marque in compacte for marque in _CLES_SENSIBLES)


def _assainir_locator(valeur) -> str:
    locator = " ".join(str(valeur or "").split())[:300]
    try:
        parties = urlsplit(locator)
    except (ValueError, UnicodeError):
        return locator
    if not parties.scheme or not parties.netloc:
        return locator
    netloc = parties.netloc
    utilisateur_sensible = (parties.username is not None
                            and parties.scheme.lower() not in _SCHEMES_IDENTIFIANTS)
    if parties.password is not None or utilisateur_sensible:
        netloc = re.sub(r"^[^@]*@", "***@", netloc)
    query = parties.query
    if query:
        paires = parse_qsl(query, keep_blank_values=True)
        query = urlencode([(cle, "***" if _cle_sensible(cle) else element) for cle, element in paires])
    return urlunsplit((parties.scheme, netloc, parties.path, query, parties.fragment))


def _texte(valeur, maximum=240) -> str:
    texte = " ".join(str(valeur or "").split())
    texte = _RE_MOT_DE_PASSE_URL.sub(r"\1***@", texte)
    texte = _RE_IDENTIFIANT_URL_SENSIBLE.sub(r"\1***@", texte)
    return texte[:maximum]


def _locator(preuve: Mapping) -> str:
    return _assainir_locator(preuve.get("locator"))


def _role(preuve: Mapping) -> str:
    return _texte(preuve.get("role") or "SUPPORT", 40).upper()


def _confiance(claim: Mapping) -> float:
    try:
        return max(0.0, min(1.0, float(claim.get("confiance"))))
    except (TypeError, ValueError):
        return 0.5


def _preuves(claim: Mapping) -> list[dict]:
    preuves = claim.get("preuves") or ()
    if isinstance(preuves, Mapping):
        return [dict(preuves)]
    return [dict(preuve) for preuve in preuves if isinstance(preuve, Mapping)]


def _supports(claim: Mapping) -> list[dict]:
    return [preuve for preuve in _preuves(claim) if _role(preuve) == "SUPPORT"]


def _refs(claim: Mapping, preuves=()) -> tuple[str, ...]:
    identifiant = claim.get("id")
    refs = [f"claim:{identifiant}" if identifiant is not None else "claim"]
    for preuve in preuves:
        if preuve.get("id") is not None:
            refs.append(str(preuve["id"]))
        locator = _locator(preuve)
        if locator:
            refs.append(locator)
    return tuple(refs[:MAX_REFS])


def _refs_groupe(claims, supports_seulement=False) -> tuple[str, ...]:
    refs = []
    for claim in claims:
        preuves = _supports(claim) if supports_seulement else _preuves(claim)
        refs.extend(_refs(claim, preuves))
    return tuple(dict.fromkeys(refs))[:MAX_REFS]


def _claim_depuis_ligne(ligne) -> dict:
    if isinstance(ligne, Mapping):
        claim = dict(ligne)
    else:
        claim = dict(zip(_COLONNES, ligne))
    preuves = claim.get("preuves")
    if isinstance(preuves, str):
        try:
            preuves = json.loads(preuves)
        except (TypeError, ValueError):
            preuves = []
    if isinstance(preuves, Mapping):
        preuves = [preuves]
    claim["preuves"] = [dict(preuve) for preuve in (preuves or []) if isinstance(preuve, Mapping)]
    return claim


def lire_claims(conn, contexte: ContexteSpecialiste, limite: int = MAX_CLAIMS) -> list[dict]:
    """Claims du tenant, filtrés par ``claim_ids`` et/ou ``twin_ids`` ; SELECT seulement.

    Les APIs ``depot.lister_claims`` / ``connaissance.connaissances`` n'exposent ni le rôle des
    preuves ni leur date d'observation : cette lecture directe, tenant-scopée, est donc nécessaire.
    Les claim_ids explicites peuvent désigner un claim clos ; sans eux, seuls les claims courants
    sont lus.
    """
    if conn is None:
        return []
    conditions, parametres = ["c.tenant_id = %s"], [contexte.tenant]
    selection_explicite = bool(contexte.claim_ids)
    if selection_explicite:
        conditions.append("c.id::text = ANY(%s)")
        parametres.append(list(contexte.claim_ids))
    if contexte.twin_ids:
        conditions.append("c.jumeau_id = ANY(%s)")
        parametres.append(list(contexte.twin_ids))
    if not selection_explicite:
        conditions.append("c.valide_jusqua IS NULL")
    parametres.append(max(1, int(limite)))
    requete = _REQUETE.format(conditions=" AND ".join(conditions))
    if isinstance(conn, (list, tuple)):
        lignes = conn
    else:
        if hasattr(conn, "execute"):
            curseur = conn.execute(requete, parametres)
        else:
            curseur = conn.cursor()
            curseur.execute(requete, parametres)
        lignes = curseur.fetchall() if hasattr(curseur, "fetchall") else curseur
    return [_claim_depuis_ligne(ligne) for ligne in lignes or ()]


def _observation(preuve: Mapping):
    for cle in ("observee_le", "observe_le", "observed_at"):
        valeur = preuve.get(cle)
        if valeur:
            return valeur
    return None


def _age(etat: Mapping) -> str:
    age = etat.get("age_jours")
    try:
        return f"{float(age):g} j"
    except (TypeError, ValueError):
        return "âge inconnu"


def _peremption(claim: Mapping, supports, maintenant, seuil_jours) -> list[str]:
    raisons = []
    etat_claim = temporalite.fraicheur(claim, maintenant=maintenant, seuil_jours=seuil_jours)
    if etat_claim.get("etat") == "perimee":
        raisons.append(f"validité du claim observée il y a {_age(etat_claim)}")
    if claim.get("valide_jusqua") and not temporalite.est_valide(claim, maintenant):
        raisons.append("validité du claim terminée")
    for preuve in supports:
        observation = _observation(preuve)
        if not observation:
            continue
        etat = temporalite.fraicheur({"observe_le": observation}, maintenant=maintenant,
                                     seuil_jours=seuil_jours)
        if etat.get("etat") == "perimee":
            locator = _locator(preuve) or f"preuve {preuve.get('id')}"
            raisons.append(f"{locator} observée il y a {_age(etat)}")
    return list(dict.fromkeys(raisons))


def _sans_preuve(claim: Mapping) -> Proposition:
    identifiant = claim.get("id")
    preuves = _preuves(claim)
    roles = sorted({_role(preuve) for preuve in preuves})
    complement = f" (rôles présents : {', '.join(roles)})" if roles else ""
    return Proposition(
        specialiste=NOM,
        type="RISQUE",
        titre=TITRE_SANS_PREUVE,
        resume=(f"Claim {identifiant} : aucune preuve de rôle SUPPORT{complement} ; "
                "la connaissance ne peut pas être tenue pour appuyée."),
        preuves=_refs(claim, preuves),
        confiance=0.95,
        actions=("demander_preuve", "verifier_preuve"),
        donnees={
            "claim_id": identifiant,
            "twin_id": _texte(claim.get("twin_id"), 120),
            "statut": _texte(claim.get("statut"), 40),
            "roles_preuve": roles,
            "nb_preuves": len(preuves),
        },
    )


def _faible(claim: Mapping) -> Proposition | None:
    statut = _texte(claim.get("statut"), 40).upper()
    confiance = _confiance(claim)
    if statut != "CONTESTED" and confiance >= SEUIL_CONFIANCE_FAIBLE:
        return None
    conteste = statut == "CONTESTED"
    if conteste:
        resume = (f"Claim {claim.get('id')} est CONTESTED (confiance {confiance:.2f}) : "
                  "sa validité doit être revue avant d'être utilisée.")
    else:
        resume = (f"Claim {claim.get('id')} a une confiance faible ({confiance:.2f} < "
                  f"{SEUIL_CONFIANCE_FAIBLE:.2f}) : l'appui doit être renforcé.")
    return Proposition(
        specialiste=NOM,
        type="CONSTAT" if conteste else "RISQUE",
        titre=TITRE_CONTESTE,
        resume=resume,
        preuves=_refs(claim, _supports(claim)),
        confiance=0.85 if conteste else 0.75,
        actions=("verifier_preuve", "reouvrir_claim"),
        donnees={
            "claim_id": claim.get("id"),
            "twin_id": _texte(claim.get("twin_id"), 120),
            "statut": statut,
            "confiance_claim": confiance,
        },
    )


def _perimee(claim: Mapping, supports, maintenant, seuil_jours) -> Proposition | None:
    raisons = _peremption(claim, supports, maintenant, seuil_jours)
    if not raisons:
        return None
    return Proposition(
        specialiste=NOM,
        type="RISQUE",
        titre=TITRE_PERIMEE,
        resume=(f"Claim {claim.get('id')} : preuve ou validité périmée "
                f"({'; '.join(raisons)})."),
        preuves=_refs(claim, supports),
        confiance=0.85,
        actions=("verifier_preuve", "demander_preuve"),
        donnees={
            "claim_id": claim.get("id"),
            "twin_id": _texte(claim.get("twin_id"), 120),
            "raisons": raisons[:5],
            "nb_preuves_support": len(supports),
        },
    )


def _triplet(claim: Mapping):
    return (
        _texte(claim.get("sujet"), 300).casefold(),
        _texte(claim.get("predicat"), 80).upper(),
        _texte(claim.get("objet"), 300).casefold(),
    )


def _contradictions(claims) -> list[Proposition]:
    groupes = {}
    for claim in claims:
        cle = _triplet(claim)
        if not any(cle):
            continue
        groupes.setdefault(cle, []).append(claim)
    propositions = []
    for groupe in groupes.values():
        uniques, vus = [], set()
        for claim in groupe:
            identifiant = (claim.get("id"), claim.get("twin_id"))
            if identifiant in vus:
                continue
            vus.add(identifiant)
            uniques.append(claim)
        if len(uniques) < 2:
            continue
        identifiants = [claim.get("id") for claim in uniques]
        twins = list(dict.fromkeys(_texte(claim.get("twin_id"), 120) for claim in uniques))
        sujet = _texte(uniques[0].get("sujet"), 300)
        predicat = _texte(uniques[0].get("predicat"), 80)
        objet = _texte(uniques[0].get("objet"), 300)
        propositions.append(Proposition(
            specialiste=NOM,
            type="CONSTAT",
            titre=TITRE_CONTRADICTION,
            resume=(f"Claims {', '.join(str(i) for i in identifiants)} portent le même énoncé "
                    f"({sujet} / {predicat} / {objet}) : contradiction ou doublon à trancher."),
            preuves=_refs_groupe(uniques),
            confiance=0.8,
            actions=("verifier_preuve", "reouvrir_claim"),
            donnees={
                "claim_ids": identifiants,
                "twin_ids": twins,
                "sujet": sujet,
                "predicat": predicat,
                "objet": objet,
            },
        ))
    return propositions


def _suffisantes(claims) -> Proposition | None:
    if not claims or not all(_supports(claim) for claim in claims):
        return None
    confiance = sum(_confiance(claim) for claim in claims) / len(claims)
    identifiants = [claim.get("id") for claim in claims]
    twins = list(dict.fromkeys(_texte(claim.get("twin_id"), 120) for claim in claims))
    total = sum(len(_supports(claim)) for claim in claims)
    return Proposition(
        specialiste=NOM,
        type="CONSTAT",
        titre=TITRE_SUFFISANTES,
        resume=(f"Les {len(claims)} claims sélectionnés portent tous au moins une preuve SUPPORT "
                f"({total} preuve(s) au total)."),
        preuves=_refs_groupe(claims, supports_seulement=True),
        confiance=confiance,
        actions=("verifier_preuve",),
        donnees={
            "claim_ids": identifiants,
            "twin_ids": twins,
            "nb_claims": len(claims),
            "nb_preuves_support": total,
        },
    )


def construire_propositions(claims, *, maintenant=None, seuil_jours=SEUIL_FRAICHEUR_JOURS) -> list[Proposition]:
    """Mappe des Claims (dicts avec ``preuves``) vers des propositions ; fonction pure, sans I/O."""
    uniques, vus = [], set()
    for claim in claims or ():
        if not isinstance(claim, Mapping):
            continue
        if claim.get("id") is not None:
            identifiant = (claim.get("id"), claim.get("twin_id"))
            if identifiant in vus:
                continue
            vus.add(identifiant)
        uniques.append(claim)
    if not uniques:
        return []
    instant = maintenant or datetime.now(timezone.utc).isoformat()
    propositions = []
    for claim in uniques:
        supports = _supports(claim)
        if not supports:
            propositions.append(_sans_preuve(claim))
            continue
        faible = _faible(claim)
        if faible:
            propositions.append(faible)
        perimee = _perimee(claim, supports, instant, seuil_jours)
        if perimee:
            propositions.append(perimee)
    propositions.extend(_contradictions(uniques))
    suffisantes = _suffisantes(uniques)
    if suffisantes:
        propositions.append(suffisantes)
    return propositions


class SpecialistePreuve:
    """Spécialiste en lecture seule : il propose des constats et risques, jamais une promotion."""

    nom = NOM
    autorite = "proposition"

    def analyser(self, contexte: ContexteSpecialiste) -> ResultatSpecialiste:
        try:
            if not isinstance(contexte, ContexteSpecialiste):
                raise TypeError("ContexteSpecialiste attendu")
            if contexte.conn is None:
                return ResultatSpecialiste(
                    specialiste=self.nom,
                    statut="partiel",
                    limites=["aucune connexion : les claims n'ont pas été lus, aucune proposition inventée"],
                )
            claims = lire_claims(contexte.conn, contexte)
            if not claims:
                return ResultatSpecialiste(
                    specialiste=self.nom,
                    statut="partiel",
                    limites=["aucun claim lisible pour ce contexte, aucune proposition inventée"],
                )
            return ResultatSpecialiste(
                specialiste=self.nom,
                statut="ok",
                propositions=construire_propositions(
                    claims, maintenant=contexte.maintenant, seuil_jours=SEUIL_FRAICHEUR_JOURS),
            )
        except Exception as exc:  # noqa: BLE001 - l'orchestrateur attend un statut, pas une trace
            return ResultatSpecialiste(specialiste=self.nom, statut="erreur", erreur=type(exc).__name__)
