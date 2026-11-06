"""Résolution déterministe d'une destination à partir des bindings de déploiement.

Le code d'un client dit « j'appelle `${accounts.base-url}` » ou « j'appelle
`https://gateway/accounts` ». Ce module suit la configuration :

    propriété -> URL -> route de passerelle -> nom de service -> Twin

Il ne devine pas une destination absente : il rend `missing_evidence` avec la question
exacte et la prochaine vérification. L'agent ne décide pas à sa place ; il choisit seulement
quelle source consulter ensuite.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import re
from urllib.parse import urlsplit

from meridian.domain.decouverte_liens import (
    Binding,
    CandidatResolution,
    DestinationResolution,
    ResolutionCase,
)
from meridian.domain.naissance_relationnelle import Consommation

_RE_PROPRIETE = re.compile(r"^\$\{?([^}]+)\}?$")
_RE_URL = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_RE_JNDI = re.compile(r"^(java:|jms/|jdbc/|eis/|queue/|topic/)", re.IGNORECASE)


def _objet(valeur, classe):
    if isinstance(valeur, classe):
        return valeur
    return classe.depuis_dict(valeur)


def _environnement_compatible(a: str, b: str) -> bool:
    return a == b or a in ("", "inconnu") or b in ("", "inconnu")


def _normaliser_nom(valeur) -> str:
    texte = " ".join(str(valeur or "").split())
    correspondance = _RE_PROPRIETE.match(texte)
    if correspondance:
        texte = correspondance.group(1)
    return texte.strip().lower().rstrip("/")


def _bindings_pour(bindings, environment: str) -> list[Binding]:
    return [b for b in (_objet(x, Binding) for x in (bindings or ()))
            if _environnement_compatible(b.environment, environment)]


def _trouver(bindings, kind: str, nom: str) -> list[Binding]:
    cible = _normaliser_nom(nom)
    return [b for b in bindings if b.kind == kind and _normaliser_nom(b.nom) == cible]


def _route_pour(bindings, chemin: str) -> Binding | None:
    """Route de passerelle la plus spécifique (préfixe le plus long)."""
    chemin = "/" + str(chemin or "").strip("/")
    candidates = [b for b in bindings if b.kind == "GATEWAY_ROUTE"
                  and (chemin == ("/" + b.nom.strip("/")) or chemin.startswith("/" + b.nom.strip("/") + "/"))]
    if not candidates:
        return None
    return max(candidates, key=lambda b: len(b.nom.strip("/")))


def _service_canonique(bindings, service: str) -> tuple[str, list[str]]:
    preuves = []
    courant = service
    for _ in range(3):
        alias = _trouver(bindings, "ALIAS", courant)
        if not alias:
            break
        preuves.extend(alias[0].evidence_ids)
        courant = alias[0].valeur
    return courant, preuves


def _resolution_service(bindings, service: str) -> tuple[str, list[dict]]:
    service, preuves_alias = _service_canonique(bindings, service)
    trouves = _trouver(bindings, "SERVICE", service)
    cibles = [{"twin_id": b.valeur, "service": service,
               "evidence_ids": [*preuves_alias, *b.evidence_ids]}
              for b in trouves]
    uniques = {}
    for cible in cibles:
        uniques.setdefault(cible["twin_id"], cible)
    return (next(iter(uniques)), list(uniques.values())) if len(uniques) == 1 else ("", list(uniques.values()))


def resoudre_destination(consommation, bindings, *, environment: str = "inconnu") -> DestinationResolution:
    """Suit la chaîne de configuration d'une consommation, sans jamais inventer la cible."""
    consommation = _objet(consommation, Consommation)
    bindings = _bindings_pour(bindings, environment)
    reference = str(getattr(consommation, "logical_ref", "") or "").strip()
    kind = str(getattr(consommation, "kind", "HTTP") or "HTTP").upper()
    preuves = list(getattr(consommation, "evidence_ids", ()) or ())
    chaine = []

    if not reference:
        return DestinationResolution(
            status="missing_evidence", evidence_ids=tuple(preuves),
            missing_evidence="référence logique absente",
            next_check="extraire l'appel sortant du code ou de la configuration")

    # 1. Propriété de configuration : ${accounts.base-url} ou accounts.base-url.
    explicite = _RE_PROPRIETE.match(reference) is not None
    if explicite or (not _RE_URL.match(reference)
                     and not _RE_JNDI.match(reference)
                     and "/" not in reference and "." in reference):
        propriete = _normaliser_nom(reference)
        trouves = _trouver(bindings, "PROPERTY", propriete)
        if not trouves:
            if explicite:
                return DestinationResolution(
                    status="missing_evidence", evidence_ids=tuple(preuves),
                    chain=tuple(chaine),
                    missing_evidence=f"propriété de configuration absente : {propriete}",
                    next_check=f"consulter le manifeste de déploiement ou la configuration pour {propriete}")
        else:
            binding = trouves[0]
            preuves.extend(binding.evidence_ids)
            chaine.append(f"property:{binding.nom}={binding.valeur}")
            reference = binding.valeur

    # 2. URL : chercher le service directement, puis la route de passerelle.
    if _RE_URL.match(reference):
        parties = urlsplit(reference)
        hote = parties.netloc.lower()
        services = _trouver(bindings, "SERVICE", hote)
        if services:
            service = services[0].valeur
            preuves.extend(services[0].evidence_ids)
            chaine.append(f"service:{hote}={service}")
        else:
            route = _route_pour(bindings, parties.path)
            if route is None:
                return DestinationResolution(
                    status="missing_evidence", evidence_ids=tuple(preuves),
                    chain=tuple(chaine),
                    missing_evidence=f"aucune route de passerelle pour {parties.path}",
                    next_check=f"consulter la table de routage gateway/ingress pour {parties.path}")
            service = route.valeur
            preuves.extend(route.evidence_ids)
            chaine.append(f"gateway:{route.nom}->{service}")
    elif kind in ("JMS", "KAFKA", "JNDI") or _RE_JNDI.match(reference):
        # 3. JNDI -> file/topic -> service propriétaire.
        jndi = _trouver(bindings, "JNDI", reference)
        if not jndi:
            return DestinationResolution(
                status="missing_evidence", evidence_ids=tuple(preuves),
                chain=tuple(chaine),
                missing_evidence=f"binding JNDI absent : {reference}",
                next_check=f"demander l'export de binding serveur pour {reference}")
        destination = jndi[0].valeur
        preuves.extend(jndi[0].evidence_ids)
        chaine.append(f"jndi:{jndi[0].nom}={destination}")
        files = _trouver(bindings, "QUEUE", destination) or _trouver(bindings, "TOPIC", destination)
        if not files:
            return DestinationResolution(
                status="missing_evidence", evidence_ids=tuple(preuves),
                chain=tuple(chaine),
                missing_evidence=f"file ou topic non rattaché : {destination}",
                next_check=f"identifier le propriétaire de {destination} sur le broker")
        service = files[0].valeur
        preuves.extend(files[0].evidence_ids)
        chaine.append(f"resource:{files[0].nom}->{service}")
    else:
        service = reference
        chaine.append(f"service:{service}")

    # 4. Service -> Twin.
    twin, candidats = _resolution_service(bindings, service)
    if not twin and len(candidats) > 1:
        return DestinationResolution(
            status="ambiguous", candidates=tuple(candidats), evidence_ids=tuple(preuves),
            chain=tuple(chaine), missing_evidence="plusieurs Twins correspondent au service",
            next_check=f"lever l'ambiguïté du service {service}")
    if not twin:
        return DestinationResolution(
            status="missing_evidence", evidence_ids=tuple(preuves), chain=tuple(chaine),
            missing_evidence=f"service non rattaché à un Twin : {service}",
            next_check=f"consulter le catalogue de services pour {service}")

    for candidate in candidats:
        if candidate["twin_id"] == twin:
            preuves.extend(candidate.get("evidence_ids") or ())
            break
    chaine.append(f"twin:{twin}")
    return DestinationResolution(
        status="resolved", target_twin_id=twin, target_service=service,
        target_operation=str(getattr(consommation, "logical_ref", "") or ""),
        evidence_ids=tuple(dict.fromkeys(preuves)), chain=tuple(chaine))


def ouvrir_resolution_case(tenant_id: str, twin_id: str, consommation,
                           resolution: DestinationResolution, *,
                           owner: str = "") -> ResolutionCase | None:
    """Un cas est ouvert uniquement quand la destination n'est pas résolue."""
    if resolution.resolved:
        return None
    return ResolutionCase(
        tenant_id=tenant_id, twin_id=twin_id,
        reference=str(getattr(consommation, "logical_ref", "") or ""),
        environment=str(getattr(consommation, "environment", "inconnu") or "inconnu"),
        missing_evidence=resolution.missing_evidence,
        next_check=resolution.next_check,
        owner=owner, evidence_ids=resolution.evidence_ids,
        candidates=resolution.candidates,
    )


def construire_demande_investigation(case: ResolutionCase, bindings, manifests) -> dict:
    """Contexte borné remis à l'investigateur : aucune secret, aucun dump de dépôt."""
    twins = []
    for manifeste in manifests or ():
        twins.append({
            "twin_id": manifeste.twin_id,
            "application_id": manifeste.application_id,
            "status": manifeste.status,
            "exposures": [
                {"operation": x.operation, "kind": x.kind, "portee": x.portee,
                 "environment": x.environment, "evidence_ids": list(x.evidence_ids)}
                for x in manifeste.exposures
                if x.portee in ("SERVICE", "PARTNER", "PUBLIC", "UNKNOWN")
            ][:80],
        })
    return {
        "case": {
            "twin_id": case.twin_id, "reference": case.reference,
            "environment": case.environment, "missing_evidence": case.missing_evidence,
            "next_check": case.next_check, "attempts": case.attempts,
            "candidates": list(case.candidates),
        },
        "bindings": [
            {"kind": b.kind, "nom": b.nom, "valeur": b.valeur,
             "environment": b.environment, "source": b.source,
             "evidence_ids": list(b.evidence_ids)}
            for b in bindings or ()
        ][:200],
        "twins": twins,
        "regles": [
            "propose uniquement des Twins présents dans la liste",
            "propose des bindings vérifiables (PROPERTY, GATEWAY_ROUTE, SERVICE, ALIAS, JNDI, QUEUE, TOPIC)",
            "ne confirme jamais une relation",
            "si la preuve manque, rends une prochaine vérification précise",
            "aucun secret, aucune URL avec identifiants",
        ],
    }


def _candidat(valeur) -> CandidatResolution:
    if isinstance(valeur, CandidatResolution):
        return valeur
    return CandidatResolution.depuis_dict(valeur)


async def investiguer_resolution_async(case: ResolutionCase, bindings, manifests, investigateur, *,
                                       limite_candidats: int = 5) -> ResolutionCase:
    reponse = await investigateur.proposer(construire_demande_investigation(case, bindings, manifests))
    return _appliquer_investigation(case, reponse, manifests=manifests,
                                   limite_candidats=limite_candidats)


def _appliquer_investigation(case: ResolutionCase, reponse, *, manifests=(),
                             limite_candidats: int) -> ResolutionCase:
    if not isinstance(reponse, dict):
        raise ValueError("réponse d'investigation : objet attendu")
    autorises = {m.twin_id for m in manifests or ()}
    existants = {c.get("id"): dict(c) for c in case.candidates}
    for brut in (reponse.get("candidates") or ())[:limite_candidats]:
        try:
            candidat = _candidat(brut)
        except ValueError:
            continue
        if autorises and candidat.twin_id not in autorises:
            continue
        existants[candidat.id] = candidat.as_dict()
    return replace(
        case, candidates=tuple(existants.values()), attempts=case.attempts + 1,
        next_check=str(reponse.get("next_check") or case.next_check or "").strip(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


def revoir_candidat(case: ResolutionCase, candidate_id: str, decision: str, acteur: str, *,
                    motif: str = "") -> tuple[ResolutionCase, list[Binding]]:
    """Accepte ou rejette une hypothèse. Un accepté produit des bindings à persister."""
    acteur = " ".join(str(acteur or "").split())
    if not acteur:
        raise ValueError("acteur obligatoire")
    gestion = str(decision or "").strip().lower()
    if gestion not in ("accepter", "rejeter"):
        raise ValueError("décision attendue : accepter ou rejeter")
    candidats = [dict(c) for c in case.candidates]
    index = next((i for i, c in enumerate(candidats) if c.get("id") == candidate_id), None)
    if index is None:
        raise LookupError("candidat de résolution introuvable")
    candidat = _candidat(candidats[index])
    if gestion == "rejeter":
        candidats[index] = replace(candidat, status="rejected").as_dict()
        return replace(case, candidates=tuple(candidats),
                       next_check=motif or case.next_check,
                       updated_at=datetime.now(timezone.utc).isoformat()), []
    bindings = []
    for brut in candidat.bindings:
        try:
            bindings.append(Binding.depuis_dict(brut))
        except ValueError:
            continue
    if not bindings and candidat.service:
        bindings.append(Binding(kind="SERVICE", nom=candidat.service, valeur=candidat.twin_id,
                                environment=case.environment, source=f"revue:{acteur}",
                                evidence_ids=candidat.evidence_ids))
    candidats[index] = replace(candidat, status="accepted").as_dict()
    return replace(
        case, candidates=tuple(candidats), status="resolved",
        target_twin_id=candidat.twin_id, resolved_at=datetime.now(timezone.utc).isoformat(),
        evidence_ids=tuple(dict.fromkeys([*case.evidence_ids, *candidat.evidence_ids])),
        updated_at=datetime.now(timezone.utc).isoformat(),
        next_check="", missing_evidence="",
    ), bindings
