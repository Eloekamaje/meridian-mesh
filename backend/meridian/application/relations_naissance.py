"""Résolution déterministe des relations à la naissance.

Le module ne lit ni Postgres ni le réseau : il transforme des Claims déjà lus en manifeste,
puis joint les consommations déclarées aux expositions déclarées des autres Twins. Aucun
modèle, aucune similarité floue : un candidat est une égalité normalisée, avec sa preuve.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit
import re

from meridian.domain.naissance_relationnelle import (
    Consommation,
    Exposition,
    ManifesteNaissance,
    PropositionRelation,
    Ressource,
)

_RE_METHODE = re.compile(r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(\S+)", re.IGNORECASE)
_RE_URL = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)


@dataclass(frozen=True)
class ResolutionNaissance:
    propositions: tuple[PropositionRelation, ...]
    sans_candidat: tuple[dict, ...]


class NaissanceNonPrete(ValueError):
    """Les préalables de commande/naissance ne sont pas satisfaits."""


def verifier_prealables_naissance(commande, jumeau, naissance_etat: str) -> None:
    """Garde-fou explicite des préalables B01–B07 de l'ADR-0031.

    Le hook est appelé après `naissance.etat = ne` ; cette fonction refuse aussi un appel
    direct depuis un brouillon, un échec ou un Twin sans propriétaire/périmètre.
    """
    etat = str(naissance_etat or "").strip().lower()
    if etat not in {"ne", "sans_substance"}:
        raise NaissanceNonPrete(
            f"naissance non terminée ({etat or 'inconnue'}) : twin.born interdit")
    if not isinstance(commande, dict) or not str(commande.get("id") or "").strip():
        raise NaissanceNonPrete("commande sans identifiant : twin.born interdit")
    for champ in ("id", "tenant_id", "nom"):
        if not str((jumeau or {}).get(champ) or "").strip():
            raise NaissanceNonPrete(f"Twin sans {champ} : twin.born interdit")
    if not str((jumeau or {}).get("proprietaire") or (jumeau or {}).get("equipe") or "").strip():
        raise NaissanceNonPrete("Twin sans propriétaire : twin.born interdit")
    if not str((jumeau or {}).get("perimetre_id") or "").strip():
        raise NaissanceNonPrete("Twin sans périmètre : twin.born interdit")


def _texte(valeur, maximum=500) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def _ref(valeur) -> str:
    """Référence normalisée : méthode + chemin, URL sans slash final, casse et espaces stables."""
    texte = _texte(valeur)
    if not texte:
        return ""
    correspondance = _RE_METHODE.match(texte)
    if correspondance:
        return f"{correspondance.group(1).upper()} {correspondance.group(2).rstrip('/')}".casefold()
    if _RE_URL.match(texte):
        try:
            parties = urlsplit(texte)
            chemin = parties.path.rstrip("/") or "/"
            return f"{parties.scheme.lower()}://{parties.netloc.lower()}{chemin}".casefold()
        except ValueError:
            return texte.casefold()
    return texte.casefold().rstrip("/")


def _kind(predicat: str, objet: str) -> str:
    texte = str(objet or "").strip()
    if _RE_METHODE.match(texte):
        return "HTTP"
    if texte.upper().startswith("SOAP "):
        return "SOAP"
    if _RE_URL.match(texte):
        return "HTTP"
    if str(predicat).upper() == "CONSOMME" and re.search(r"(jms|queue|topic)", texte, re.IGNORECASE):
        return "JMS"
    if texte.lower().startswith("jdbc:"):
        return "DB"
    return "AUTRE"


def _evidence(claim) -> tuple[str, ...]:
    identifiant = claim.get("id")
    preuve = claim.get("preuve")
    valeurs = []
    if identifiant is not None:
        valeurs.append(f"claim:{identifiant}")
    if preuve:
        valeurs.append(f"preuve:{preuve}")
    return tuple(valeurs)


def classer_exposition(objet: str, kind: str = "HTTP") -> tuple[str, tuple[str, ...]]:
    """Classe une route technique évidente ; ne devine jamais un service métier.

    `SERVICE`, `PARTNER` et `PUBLIC` exigent une gateway, un contrat, un réseau, une trace ou
    une déclaration humaine. Les heuristiques ci-dessous ne servent qu'à écarter le bruit.
    """
    if str(kind or "").upper() != "HTTP":
        return "UNKNOWN", ()
    chemin = _texte(objet).lower()
    for motif, portee in (
        (r"(^|/)(health|health-check|healthcheck|ready|live|metrics)(/|$|\?)", "HEALTH"),
        (r"(^|/)(admin|administration)(/|$|\?)", "ADMIN"),
        (r"(^|/)(demo|démo)(/|$|\?)", "DEMO"),
        (r"(^|/)(debug|actuator)(/|$|\?)", "DEBUG"),
        (r"(^|/)(internal|interne|private|privé)(/|$|\?)", "INTERNAL"),
    ):
        if re.search(motif, chemin):
            return portee, (f"heuristique:chemin:{portee.lower()}",)
    return "UNKNOWN", ()


def manifeste_depuis_claims(commande, jumeau, claims, *, birth_run_id: str,
                            partial: bool = False, declared_by: str = "naissance") -> ManifesteNaissance:
    """Construit le manifeste déclaré d'une naissance à partir des Claims d'interface."""
    expositions, consommations, inconnues, ressources = [], [], [], []
    for claim in claims or ():
        if not isinstance(claim, dict):
            continue
        predicat = str(claim.get("predicat") or "").strip().upper()
        objet = _texte(claim.get("objet"))
        if predicat not in ("EXPOSE", "CONSOMME") or not objet:
            continue
        preuves = _evidence(claim)
        confiance = claim.get("confiance", 0.5)
        try:
            if predicat == "EXPOSE":
                portee = str(claim.get("portee") or "").strip().upper()
                if portee:
                    frontiere = tuple(claim.get("boundary_evidence") or ())
                else:
                    portee, frontiere = classer_exposition(objet, _kind(predicat, objet))
                exposition = Exposition(
                    kind=_kind(predicat, objet), operation=objet,
                    environment=commande.get("environnement") or "inconnu",
                    evidence_ids=preuves, confidence=confiance, portee=portee,
                    boundary_evidence=frontiere,
                    ressource_id=claim.get("ressource_id") or "")
                expositions.append(exposition)
                if claim.get("ressource_id"):
                    ressources.append(Ressource(
                        id=claim["ressource_id"], kind=claim.get("ressource_kind") or "AUTRE",
                        nom=claim.get("ressource_nom") or objet,
                        owner_twin_id=jumeau.get("id") or "",
                        portee=portee, boundary_evidence=frontiere,
                        evidence_ids=preuves, environment=exposition.environment))
            else:
                consommations.append(Consommation(
                    kind=_kind(predicat, objet), logical_ref=objet,
                    environment=commande.get("environnement") or "inconnu",
                    evidence_ids=preuves, confidence=confiance,
                    portee=claim.get("portee") or "UNKNOWN",
                    boundary_evidence=tuple(claim.get("boundary_evidence") or ()),
                    ressource_id=claim.get("ressource_id") or ""))
        except ValueError as exc:
            inconnues.append(f"claim {claim.get('id')} ignoré : {_texte(exc, 'raison', 300)}")

    if partial:
        inconnues.append("naissance partielle : certaines sources n'ont pas répondu")
    if not expositions:
        inconnues.append("aucune exposition déclarée")
    if not consommations:
        inconnues.append("aucune consommation déclarée")

    statut_twin = str(jumeau.get("statut") or "").strip().lower()
    confirme = (statut_twin in {"actif", "confirme", "confirmed", "admis"}
                and not jumeau.get("candidat"))

    return ManifesteNaissance(
        tenant_id=jumeau.get("tenant_id") or commande.get("tenant_id") or "local",
        twin_id=jumeau.get("id") or commande.get("jumeau_id"),
        birth_run_id=birth_run_id,
        type=jumeau.get("type") or "APPLICATION",
        application_id=jumeau.get("application_id") or "",
        status="CONFIRMED" if confirme else "PROVISIONAL",
        owner=jumeau.get("proprietaire") or jumeau.get("equipe") or "",
        perimetre_id=jumeau.get("perimetre_id") or "",
        partial=partial,
        declared_by=declared_by,
        visibility=commande.get("visibilite") or "TEAM",
        exposures=tuple(expositions),
        consumptions=tuple(consommations),
        unknowns=tuple(inconnues),
        ressources=tuple(ressources),
    )


def _manifeste(valeur) -> ManifesteNaissance:
    if isinstance(valeur, ManifesteNaissance):
        return valeur
    return ManifesteNaissance.depuis_dict(valeur)


def _environnements_compatibles(a: str, b: str) -> bool:
    return a == b or a == "inconnu" or b == "inconnu"


def _eligibilite(manifeste, autre, consommation, exposition) -> tuple[bool, str]:
    if not exposition.eligible:
        return False, f"exposition {exposition.portee or 'UNKNOWN'}"
    if not consommation.eligible:
        return False, f"consommation {consommation.portee or 'UNKNOWN'}"
    if not manifeste.application_id or not autre.application_id:
        return False, "application non établie"
    if manifeste.application_id == autre.application_id:
        return False, "même application"
    return True, ""


def _proposition(manifeste, autre, consommation, exposition) -> PropositionRelation:
    preuves = tuple(dict.fromkeys([*consommation.evidence_ids, *exposition.evidence_ids]))
    confiance = 0.9 if consommation.kind == exposition.kind else 0.7
    if consommation.cle == exposition.cle:
        confiance = min(1.0, confiance + 0.1)
    provisoire = manifeste.status == "PROVISIONAL" or autre.status == "PROVISIONAL"
    justification = (
        f"{manifeste.twin_id} déclare consommer {consommation.logical_ref} ; "
        f"{autre.twin_id} déclare exposer {exposition.operation}."
    )
    inconnues = [*manifeste.unknowns, *autre.unknowns]
    if provisoire:
        inconnues.append("Twin provisoire : promotion requise avant confirmation")
    return PropositionRelation(
        tenant_id=manifeste.tenant_id,
        consumer_id=manifeste.twin_id,
        provider_id=autre.twin_id,
        object=exposition.operation,
        environment=(exposition.environment if exposition.environment != "inconnu"
                     else consommation.environment),
        predicate="CONSOMME",
        mode="PROPOSED" if provisoire else "DECLARED",
        state="supposee",
        confidence=confiance,
        evidence_ids=preuves,
        consumer_owner=manifeste.owner,
        provider_owner=autre.owner,
        justification=justification,
        unknowns=tuple(dict.fromkeys(inconnues)),
        transport=exposition.kind,
        portee=exposition.portee,
        boundary_evidence=tuple(dict.fromkeys([
            *exposition.boundary_evidence, *consommation.boundary_evidence])),
        consumer_application_id=manifeste.application_id,
        provider_application_id=autre.application_id,
    )


def _transport_ressource(kind: str) -> str:
    return {"QUEUE": "JMS", "TOPIC": "KAFKA", "TABLE": "DB",
            "FILE": "FILE", "ENDPOINT": "HTTP"}.get(str(kind or "").upper(), "AUTRE")


def _proposition_ressource(manifeste, autre, consommation, ressource) -> PropositionRelation:
    preuves = tuple(dict.fromkeys([*consommation.evidence_ids, *ressource.evidence_ids]))
    provisoire = manifeste.status == "PROVISIONAL" or autre.status == "PROVISIONAL"
    inconnues = [*manifeste.unknowns, *autre.unknowns]
    if provisoire:
        inconnues.append("Twin provisoire : promotion requise avant confirmation")
    return PropositionRelation(
        tenant_id=manifeste.tenant_id, consumer_id=manifeste.twin_id,
        provider_id=autre.twin_id, object=ressource.nom,
        environment=(ressource.environment if ressource.environment != "inconnu"
                     else consommation.environment),
        predicate="CONSOMME", mode="PROPOSED" if provisoire else "DECLARED",
        state="supposee", confidence=0.8, evidence_ids=preuves,
        consumer_owner=manifeste.owner, provider_owner=autre.owner,
        justification=(f"{manifeste.twin_id} consomme la ressource {ressource.id} "
                       f"exposée par {autre.twin_id}."),
        unknowns=tuple(dict.fromkeys(inconnues)),
        transport=_transport_ressource(ressource.kind), portee=ressource.portee,
        boundary_evidence=tuple(dict.fromkeys([
            *ressource.boundary_evidence, *consommation.boundary_evidence])),
        via=ressource.id, consumer_application_id=manifeste.application_id,
        provider_application_id=autre.application_id,
    )


def manifeste_legacy(jumeau, claims, *, birth_run_id: str | None = None,
                     declared_by: str = "migration") -> ManifesteNaissance:
    """Manifeste de migration pour un Twin antérieur à l'ADR-0031.

    Le statut reste `PROVISIONAL` : la migration ne vaut pas promotion. Les propositions qui
    en découlent ne pourront pas être confirmées avant la promotion du Twin.
    """
    identifiant = str((jumeau or {}).get("id") or "").strip()
    run = birth_run_id or f"legacy-{identifiant}"
    commande = {"id": run, "environnement": "inconnu"}
    return manifeste_depuis_claims(commande, jumeau, claims, birth_run_id=run,
                                   declared_by=declared_by)


def _ressource_correspondante(autre, consommation):
    if not consommation.ressource_id:
        return None
    return next((ressource for ressource in autre.ressources
                 if ressource.id == consommation.ressource_id
                 and ressource.eligible
                 and _environnements_compatibles(consommation.environment,
                                                 ressource.environment)), None)


def _eligibilite_ressource(manifeste, autre, consommation, ressource) -> tuple[bool, str]:
    if not ressource.eligible:
        return False, f"ressource {ressource.portee or 'UNKNOWN'}"
    if not consommation.eligible:
        return False, f"consommation {consommation.portee or 'UNKNOWN'}"
    if not manifeste.application_id or not autre.application_id:
        return False, "application non établie"
    if manifeste.application_id == autre.application_id:
        return False, "même application"
    return True, ""


def proposer_relations(manifeste, existants) -> ResolutionNaissance:
    """Résolveur historique, exact, des consommations et des ressources.

    Il reste exécuté à la naissance pour deux couvertures que le moteur de composants
    ne remplace pas encore : le matching exact de `logical_ref` et les ressources
    (JMS/Kafka/DB). `moteur_liens` est la cible ; ne pas ajouter ici de nouvelle
    heuristique de chemin, de service ou de configuration.
    """
    manifeste = _manifeste(manifeste)
    autres = [_manifeste(x) for x in (existants or ())]
    autres = [x for x in autres if x.tenant_id == manifeste.tenant_id and x.twin_id != manifeste.twin_id]
    propositions = {}
    sans_candidat = {}

    def noter(twin_id, reference, environment, raison, sens="consommation"):
        sans_candidat[(twin_id, reference, environment, raison)] = {
            "twin_id": twin_id, "sens": sens, "reference": reference,
            "environment": environment, "raison": raison,
        }

    for autre in autres:
        for consommation in manifeste.consumptions:
            exposition = next((x for x in autre.exposures
                               if _ref(consommation.logical_ref) == _ref(x.operation)
                               and _environnements_compatibles(consommation.environment,
                                                               x.environment)), None)
            if exposition is not None:
                autorise, raison = _eligibilite(manifeste, autre, consommation, exposition)
                if autorise:
                    proposition = _proposition(manifeste, autre, consommation, exposition)
                    propositions[proposition.id] = proposition
                else:
                    noter(manifeste.twin_id, consommation.logical_ref,
                          consommation.environment, raison)
            ressource = _ressource_correspondante(autre, consommation)
            if ressource is not None:
                autorise, raison = _eligibilite_ressource(manifeste, autre, consommation, ressource)
                if autorise:
                    proposition = _proposition_ressource(manifeste, autre, consommation, ressource)
                    propositions[proposition.id] = proposition
                elif exposition is None:
                    noter(manifeste.twin_id, consommation.logical_ref,
                          consommation.environment, raison)
            elif exposition is None:
                noter(manifeste.twin_id, consommation.logical_ref,
                      consommation.environment, "aucune exposition ni ressource correspondante")

        for consommation in autre.consumptions:
            exposition = next((x for x in manifeste.exposures
                               if _ref(consommation.logical_ref) == _ref(x.operation)
                               and _environnements_compatibles(consommation.environment,
                                                               x.environment)), None)
            if exposition is not None:
                autorise, raison = _eligibilite(autre, manifeste, consommation, exposition)
                if autorise:
                    proposition = _proposition(autre, manifeste, consommation, exposition)
                    propositions[proposition.id] = proposition
                else:
                    noter(autre.twin_id, consommation.logical_ref,
                          consommation.environment, raison)
            ressource = _ressource_correspondante(manifeste, consommation)
            if ressource is not None:
                autorise, raison = _eligibilite_ressource(autre, manifeste, consommation, ressource)
                if autorise:
                    proposition = _proposition_ressource(autre, manifeste, consommation, ressource)
                    propositions[proposition.id] = proposition
                elif exposition is None:
                    noter(autre.twin_id, consommation.logical_ref,
                          consommation.environment, raison)

    return ResolutionNaissance(tuple(propositions.values()), tuple(sans_candidat.values()))
