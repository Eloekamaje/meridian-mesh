"""Moteur de liens entre composants.

Le moteur ne lit aucun fichier : il reçoit des observations déjà extraites, résout les
identités (service, hôte, route, file), apparie les appels aux interfaces, puis rend des
soupçons et des questions. Une observation runtime ne confirme pas un lien : elle l'étaye.
La revue humaine reste la seule à le confirmer.
"""
from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from urllib.parse import urlsplit

from meridian.domain import chemins
from meridian.domain.decouverte_liens import ResolutionCase
from meridian.domain.liens_composants import (
    Appel,
    Composant,
    Configuration,
    Deploiement,
    ExtractionDepot,
    IdentiteDeclaree,
    Interface,
    LienPropose,
    Preuve,
    QuestionLien,
    RapportLiens,
    RoutePasserelle,
)
from meridian.domain.naissance_relationnelle import PropositionRelation

__all__ = [
    "IndexIdentites",
    "extractions_depuis_manifests",
    "filtrer_local",
    "moteur_liens",
    "revoir_lien",
    "vers_proposition",
    "vers_resolution_case",
]

_RE_PROPRIETE = re.compile(r"^\$\{([^}]+)\}$")
_TLDS_INTERNES = (".local", ".internal", ".svc", ".cluster.local", ".lan", ".home")


def _texte(valeur, maximum=1000) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def _environnement(valeur) -> str:
    return str(valeur or "inconnu").strip().lower()


def _env_compatible(a: str, b: str) -> bool:
    return a == b or a in ("", "inconnu") or b in ("", "inconnu")


def _normaliser_chemin(chemin: str) -> str:
    texte = str(chemin or "")
    if "://" in texte:
        texte = urlsplit(texte).path
    return chemins.normaliser(texte)


def _segments(chemin: str) -> list[str]:
    return chemins.segments(_normaliser_chemin(chemin))


def _est_variable(segment: str) -> bool:
    return chemins.est_variable(segment)


def _segment_compatible(gauche: str, droite: str) -> bool:
    return chemins.segment_compatible(gauche, droite)


def _score_chemin(consommateur: str, producteur: str) -> int:
    return chemins.score_suffixe(consommateur, producteur)


def _prefixe(prefixe: str, chemin: str) -> bool:
    return chemins.prefixe(prefixe, chemin)


def _nom_propriete(cible: str) -> str:
    trouve = _RE_PROPRIETE.match(str(cible or "").strip())
    return trouve.group(1).strip() if trouve else str(cible or "").strip()


def _nom_hote(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _hote_public(hote: str) -> bool:
    hote = str(hote or "").strip().lower()
    if not hote or hote == "localhost" or "." not in hote:
        return False
    if any(hote.endswith(suffixe) for suffixe in _TLDS_INTERNES):
        return False
    try:
        adresse = ipaddress.ip_address(hote)
    except ValueError:
        return True
    return not (adresse.is_private or adresse.is_loopback or adresse.is_link_local)


def _protocoles_compatibles(consommateur: str, producteur: str) -> bool:
    return str(consommateur or "").upper() == str(producteur or "").upper()


def _uniques(valeurs):
    return list(dict.fromkeys(valeurs))


@dataclass(frozen=True)
class Cible:
    status: str
    composants: tuple[str, ...] = ()
    service: str = ""
    chemin: str = ""
    chemin_matching: str = ""
    host: str = ""
    preuves: tuple[Preuve, ...] = ()
    missing_evidence: str = ""
    next_check: str = ""
    deduction: bool = False


@dataclass
class IndexIdentites:
    composants: dict[str, object] = field(default_factory=dict)
    services: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    hosts: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    queues: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    routes: list[RoutePasserelle] = field(default_factory=list)
    deployments: list[Deploiement] = field(default_factory=list)
    declarations: list[IdentiteDeclaree] = field(default_factory=list)

    def ajouter_extraction(self, extraction: ExtractionDepot) -> None:
        composant = extraction.composant
        self.composants[composant.id] = composant
        for deploiement in extraction.deploiements:
            self.deployments.append(deploiement)
            if deploiement.service_name:
                self.services.setdefault(deploiement.service_name.casefold(), []).append(
                    (deploiement.composant_id, deploiement.environment))
            # Un hôte d'ingress est une porte d'entrée, pas le producteur : il ne doit
            # jamais rattacher l'appel au composant qui porte la gateway.
            if not deploiement.routes:
                for host in deploiement.hosts:
                    self.hosts.setdefault(host.casefold(), []).append(
                        (deploiement.composant_id, deploiement.environment))
            for route in deploiement.routes:
                self.routes.append(route)
        for interface in extraction.interfaces:
            if interface.service_name:
                self.services.setdefault(interface.service_name.casefold(), []).append(
                    (interface.composant_id, interface.environment))
            if interface.protocole in ("JMS", "KAFKA") and interface.role == "FOURNISSEUR":
                self.queues.setdefault(interface.operation.casefold(), []).append(
                    (interface.composant_id, interface.environment))

    def ajouter_declaration(self, declaration: IdentiteDeclaree) -> None:
        self.declarations.append(declaration)
        self.services.setdefault(declaration.service_name.casefold(), []).append(
            (declaration.composant_id, declaration.environment))

    def preuves_declaration(self, service: str, composants) -> tuple[Preuve, ...]:
        return tuple(
            declaration.preuve for declaration in self.declarations
            if declaration.preuve is not None
            and declaration.service_name.casefold() == str(service or "").casefold()
            and declaration.composant_id in set(composants)
        )

    def _composants(self, entrees, environment: str) -> tuple[str, ...]:
        return tuple(_uniques(
            composant for composant, env in (entrees or ())
            if _env_compatible(env, environment)))

    def resoudre_service(self, service: str, environment: str) -> tuple[str, ...]:
        return self._composants(self.services.get(str(service or "").casefold()), environment)

    def resoudre_host(self, host: str, environment: str) -> tuple[str, ...]:
        return self._composants(self.hosts.get(str(host or "").casefold()), environment)

    def resoudre_queue(self, queue: str, environment: str) -> tuple[str, ...]:
        return self._composants(self.queues.get(str(queue or "").casefold()), environment)

    def resoudre_route(self, chemin: str, environment: str, host: str = ""):
        chemin = _normaliser_chemin(chemin)
        host = str(host or "").casefold()
        candidats = [
            route for route in self.routes
            if _env_compatible(route.environment, environment)
            and _prefixe(route.chemin, chemin)
            and (not route.host or not host or route.host.casefold() == host)
        ]
        if not candidats:
            return []
        candidats.sort(key=lambda route: (len(_segments(route.chemin)),
                                          bool(route.host and host and route.host.casefold() == host)),
                       reverse=True)
        longueur = len(_segments(candidats[0].chemin))
        return [route for route in candidats if len(_segments(route.chemin)) == longueur]

    def services_du_composant(self, composant_id: str) -> tuple[str, ...]:
        return tuple(_uniques(
            nom for nom, entrees in self.services.items()
            if any(composant == composant_id for composant, _ in entrees)))

    def portee(self, interface: Interface) -> str:
        if interface.portee != "UNKNOWN":
            return interface.portee
        services = {interface.service_name.casefold()} if interface.service_name else set()
        services.update(nom.casefold() for nom in self.services_du_composant(interface.composant_id))
        for route in self.routes:
            if route.service.casefold() not in services:
                continue
            if interface.protocole == "SOAP":
                # Une route d'ingress vers le service publie le endpoint SOAP ; l'action
                # SOAP n'est pas un chemin HTTP et ne peut pas être comparée telle quelle.
                return "SERVICE"
            chemin_backend = route.chemin_backend or route.chemin
            if (_prefixe(chemin_backend, interface.chemin)
                    or _prefixe(interface.chemin, chemin_backend)):
                return "SERVICE"
        return "UNKNOWN"


def _configurations(extractions) -> dict[str, list[Configuration]]:
    index: dict[str, list[Configuration]] = {}
    for extraction in extractions:
        for configuration in extraction.configurations:
            index.setdefault(configuration.cle.casefold(), []).append(configuration)
    return index


def _resoudre(
    appel: Appel, index: IndexIdentites, configurations: dict[str, list[Configuration]],
) -> Cible:
    environnement = appel.environment
    if appel.cible_type == "PROPRIETE":
        cle = _nom_propriete(appel.cible).casefold()
        candidates = [configuration for configuration in configurations.get(cle, ())
                      if _env_compatible(configuration.environment, environnement)]
        if not candidates:
            return Cible(
                status="propriete_absente", chemin=appel.chemin,
                missing_evidence=f"propriété de configuration absente : {_nom_propriete(appel.cible)}",
                next_check="consulter la configuration de déploiement ou la déclaration du propriétaire",
                preuves=appel.preuves,
            )
        configuration = candidates[0]
        valeur = configuration.valeur
        preuves = (*appel.preuves, *configuration.preuves)
        if "://" in valeur:
            return _resoudre_url(appel, index, valeur, preuves)
        composants = index.resoudre_service(valeur, environnement)
        if composants:
            return Cible("resolved", composants, service=valeur, chemin=appel.chemin,
                         preuves=(*preuves, *index.preuves_declaration(valeur, composants)))
        return Cible(
            status="service_inconnu", service=valeur, chemin=appel.chemin, preuves=preuves,
            missing_evidence=f"service non rattaché à un composant : {valeur}",
            next_check=f"déclarer le service {valeur} et son application propriétaire",
        )

    if appel.cible_type == "URL":
        return _resoudre_url(appel, index, appel.cible, appel.preuves)

    if appel.cible_type == "SERVICE":
        composants = index.resoudre_service(appel.cible, environnement)
        if composants:
            return Cible("resolved", composants, service=appel.cible, chemin=appel.chemin,
                         preuves=(*appel.preuves,
                                  *index.preuves_declaration(appel.cible, composants)))
        return Cible(
            status="service_inconnu", service=appel.cible, chemin=appel.chemin,
            preuves=appel.preuves,
            missing_evidence=f"service non rattaché à un composant : {appel.cible}",
            next_check=f"déclarer le service {appel.cible} et son application propriétaire",
        )

    if appel.cible_type in ("QUEUE", "JNDI"):
        destination = appel.cible
        preuves = list(appel.preuves)
        if appel.cible_type == "JNDI":
            for configuration in configurations.get(f"jndi:{appel.cible}".casefold(), ()):
                if _env_compatible(configuration.environment, environnement):
                    destination = configuration.valeur
                    preuves.extend(configuration.preuves)
                    break
        composants = index.resoudre_queue(destination, environnement)
        if composants:
            return Cible("resolved", composants, service=destination, chemin=destination,
                         preuves=tuple(preuves))
        manque = (f"binding JNDI absent ou destination sans listener : {appel.cible}"
                  if appel.cible_type == "JNDI"
                  else f"aucun listener rattaché à la file : {destination}")
        return Cible(
            status="producteur_inconnu", chemin=appel.chemin or destination,
            preuves=tuple(preuves), missing_evidence=manque,
            next_check=f"identifier le composant qui consomme {destination}",
        )

    return Cible("chemin_seul", chemin=appel.chemin, preuves=appel.preuves)


def _chemin_apres_reecriture(chemin_appel: str, chemin_url: str,
                             route: RoutePasserelle) -> str:
    """Chemin backend d'une route d'ingress, ou vide si la route ne réécrit rien.

    Le chemin le plus précis est celui de l'appel (une propriété peut ne porter qu'une
    base d'URL) ; le suffixe externe est conservé quand la route le couvre.
    """
    if not route.chemin_backend:
        return ""
    externe = _normaliser_chemin(chemin_appel or chemin_url)
    base = _normaliser_chemin(route.chemin)
    suffixe = externe[len(base):] if base and externe.startswith(base) else ""
    backend = _normaliser_chemin(route.chemin_backend)
    return _normaliser_chemin(backend.rstrip("/") + "/" + suffixe.lstrip("/"))


def _resoudre_url(appel: Appel, index: IndexIdentites, url: str,
                  preuves) -> Cible:
    host = _nom_hote(url)
    try:
        chemin = _normaliser_chemin(urlsplit(url).path)
    except ValueError:
        chemin = appel.chemin
    composants = index.resoudre_host(host, appel.environment)
    if not composants:
        # Un appel direct au nom du service Kubernetes ne passe pas par un ingress.
        composants = index.resoudre_service(host, appel.environment)
    if composants:
        return Cible("resolved", composants, service=host, chemin=chemin, host=host,
                     preuves=(*preuves, *index.preuves_declaration(host, composants)))
    routes = index.resoudre_route(chemin, appel.environment, host)
    if routes:
        services = {route.service.casefold() for route in routes}
        if len(services) > 1:
            return Cible(
                status="producteur_inconnu", chemin=chemin, host=host,
                preuves=tuple(preuves),
                missing_evidence=f"plusieurs routes de passerelle correspondent à {chemin}",
                next_check="lever l'ambiguïté de la route avec la gateway",
            )
        route = routes[0]
        composants = index.resoudre_service(route.service, appel.environment)
        preuves = (*preuves, *route.preuves)
        if composants:
            chemin_matching = _chemin_apres_reecriture(appel.chemin, chemin, route)
            return Cible("resolved", composants, service=route.service, chemin=chemin,
                         chemin_matching=chemin_matching, host=host,
                         preuves=(*preuves,
                                  *index.preuves_declaration(route.service, composants)))
        return Cible(
            status="service_inconnu", service=route.service, chemin=chemin, host=host,
            preuves=tuple(preuves),
            missing_evidence=f"la route {route.chemin} mène au service {route.service}, "
                             "non rattaché à un composant",
            next_check=f"déclarer le service {route.service} et son application propriétaire",
        )
    if _hote_public(host):
        return Cible("externe", chemin=chemin, host=host, preuves=tuple(preuves))
    return Cible(
        status="producteur_inconnu", chemin=chemin, host=host, preuves=tuple(preuves),
        missing_evidence=f"aucun producteur trouvé pour {appel.methode} {chemin or host}",
        next_check="chercher la route dans la gateway, le contrat ou demander au propriétaire",
    )


def _unifier_interfaces(interfaces: list[Interface]) -> list[Interface]:
    """Une observation de code sans environnement complète l'interface déclarée.

    Sans cette unification, la même route déclarée en `prod` et observée par CBM en
    `inconnu` produirait deux liens identiques. Les preuves de code sont cumulées sur
    chaque environnement déclaré ; sans déclaration, l'interface reste `inconnu`.
    """
    groupes: dict[tuple, list[Interface]] = {}
    for interface in interfaces:
        chemin = _normaliser_chemin(interface.chemin)
        operation = ((interface.methode.upper(), chemin) if chemin
                     else (interface.methode.upper(), interface.operation.casefold()))
        groupes.setdefault((interface.application_id, interface.composant_id,
                            interface.protocole, operation), []).append(interface)
    resultat: list[Interface] = []
    for groupe in groupes.values():
        connues = [interface for interface in groupe if interface.environment != "inconnu"]
        inconnues = [interface for interface in groupe if interface.environment == "inconnu"]
        if not connues:
            resultat.extend(inconnues)
            continue
        for base in connues:
            fusion = base
            for inconnue in inconnues:
                fusion = replace(
                    fusion,
                    nom=fusion.nom or inconnue.nom,
                    source_kind=("CODE" if "CODE" in (fusion.source_kind, inconnue.source_kind)
                                 else fusion.source_kind),
                    portee=(fusion.portee if fusion.portee != "UNKNOWN"
                            else inconnue.portee),
                    service_name=fusion.service_name or inconnue.service_name,
                    context_path=fusion.context_path or inconnue.context_path,
                    contrat_ref=fusion.contrat_ref or inconnue.contrat_ref,
                    preuves=tuple(_uniques([*fusion.preuves, *inconnue.preuves])),
                )
            resultat.append(fusion)
    return resultat


def _candidates(appel: Appel, cible: Cible,
                interfaces: list[Interface]) -> list[tuple[int, Interface]]:
    resultat: list[tuple[int, Interface]] = []
    for interface in interfaces:
        if not _env_compatible(interface.environment, appel.environment):
            continue
        if cible.composants and interface.composant_id not in cible.composants:
            continue
        if appel.cible_type == "JNDI":
            # Un nom JNDI traduit par binding désigne une file ou un topic ; l'interface
            # correspondante est JMS/KAFKA, pas JNDI.
            if interface.protocole not in ("JMS", "KAFKA"):
                continue
            if interface.operation.casefold() == (cible.service or appel.cible).casefold():
                resultat.append((3, interface))
            continue
        if not _protocoles_compatibles(appel.protocole, interface.protocole):
            continue
        if appel.protocole == "HTTP":
            if not _methode_compatible(appel.methode, interface.methode):
                continue
            chemin_appel = cible.chemin_matching or appel.chemin
            if not chemin_appel:
                score = 1 if not cible.composants else 2
            else:
                score = _score_chemin(chemin_appel, interface.chemin)
            if score:
                resultat.append((score, interface))
        elif appel.protocole in ("JMS", "KAFKA"):
            if interface.operation.casefold() == appel.cible.casefold():
                resultat.append((3, interface))
        elif appel.protocole == "SOAP":
            if not appel.chemin or interface.chemin.casefold() == appel.chemin.casefold():
                resultat.append((2, interface))
            elif interface.nom and interface.nom.casefold() == appel.operation.casefold():
                resultat.append((2, interface))
            elif cible.composants:
                # Une URL WSDL ne porte pas l'action SOAP : le service identifié suffit
                # à proposer l'interface, puis la revue tranche.
                resultat.append((1, interface))
        else:
            if not appel.chemin or interface.operation.casefold() == appel.operation.casefold():
                resultat.append((1, interface))
    resultat.sort(key=lambda item: (-item[0], item[1].application_id,
                                    item[1].composant_id, item[1].operation))
    return resultat


def _methode_compatible(consommateur: str, producteur: str) -> bool:
    gauche = str(consommateur or "ANY").upper()
    droite = str(producteur or "ANY").upper()
    return gauche in ("", "ANY") or droite in ("", "ANY") or gauche == droite


def _trace_confirme(lien: LienPropose, traces: list[Appel], index: IndexIdentites,
                    configurations: dict[str, list[Configuration]]) -> bool:
    for trace in traces:
        if trace.composant_id != lien.consommateur_composant_id:
            continue
        if trace.operation and trace.operation != lien.operation:
            continue
        cible = _resoudre(trace, index, configurations)
        if lien.fournisseur_composant_id in cible.composants:
            return True
    return False


def _portee_et_preuves(interface: Interface, index: IndexIdentites) -> tuple[str, list[Preuve]]:
    portee = index.portee(interface)
    preuves = list(interface.preuves)
    if portee != "UNKNOWN":
        for route in index.routes:
            if route.service.casefold() in {
                service.casefold() for service in index.services_du_composant(interface.composant_id)
            } and (_prefixe(route.chemin, interface.chemin)
                   or _prefixe(interface.chemin, route.chemin)):
                preuves.extend(route.preuves)
    return portee, preuves


def _lien(appel: Appel, interface: Interface, cible: Cible, index: IndexIdentites,
          traces: list[Appel], configurations: dict[str, list[Configuration]]) -> LienPropose:
    nature = "interne" if appel.application_id == interface.application_id else "mesh"
    portee, preuves = _portee_et_preuves(interface, index)
    preuves = _uniques([*preuves, *appel.preuves, *cible.preuves])
    verifications = ["implemente"]
    if cible.status == "resolved" and not cible.deduction:
        verifications.append("configure")
    operation = interface.operation
    # Un appel venu du code ne connaît pas l'environnement de déploiement : l'interface
    # déclarée est plus précise et porte le lien. Sans déclaration, « inconnu » reste visible.
    environment = (appel.environment if appel.environment != "inconnu"
                   else interface.environment)
    provisoire = LienPropose(
        consommateur_composant_id=appel.composant_id,
        consommateur_application_id=appel.application_id,
        fournisseur_composant_id=interface.composant_id,
        fournisseur_application_id=interface.application_id,
        fournisseur_service=interface.service_name or cible.service,
        interface_id=interface.id, operation=operation, protocole=interface.protocole,
        environment=environment, portee=portee, nature=nature,
        state="suggere", confiance=0.55, verifications=tuple(verifications),
        preuves=tuple(preuves),
    )
    if _trace_confirme(provisoire, traces, index, configurations):
        verifications.append("observe")
    confiance = 0.55 + 0.15 * len(verifications) - (0.15 if cible.deduction else 0)
    manques: list[str] = []
    verifications_a_faire: list[str] = []
    if nature == "mesh" and portee == "UNKNOWN":
        manques.append("portée de l'interface non établie")
        verifications_a_faire.append(
            f"identifier la frontière de {interface.composant_id} (ingress, gateway, contrat)")
    if cible.status == "service_inconnu":
        manques.append(f"service non rattaché à un composant : {cible.service}")
        verifications_a_faire.append(
            f"déclarer le service {cible.service} et son application propriétaire")
    if cible.deduction or (not cible.composants and cible.chemin):
        manques.append("hôte non résolu ; lien déduit du chemin")
        verifications_a_faire.append(
            f"confirmer le propriétaire du service ou de l'hôte {cible.host or ''}".strip())
    inconnues = []
    if "observe" not in verifications:
        inconnues.append("usage runtime non observé")
    if nature == "mesh" and portee == "UNKNOWN":
        inconnues.append("portée non établie")
    return replace(
        provisoire, confiance=min(0.95, max(0.0, confiance)),
        verifications=tuple(_uniques(verifications)),
        missing_evidence="; ".join(_uniques(manques)),
        next_check="; ".join(_uniques(verifications_a_faire)),
        unknowns=tuple(_uniques(inconnues)),
    )


def _question(appel: Appel, cible: Cible, type_: str, question: str,
              candidats=()) -> QuestionLien:
    return QuestionLien(
        type=type_, sujet=f"{appel.methode} {appel.chemin or appel.cible}".strip(),
        question=question, environment=appel.environment,
        composant_id=appel.composant_id, application_id=appel.application_id,
        candidats=tuple(candidats),
        missing_evidence=cible.missing_evidence,
        next_check=cible.next_check,
        preuves=tuple(_uniques([*appel.preuves, *cible.preuves])),
    )


def _fusionner(liens: list[LienPropose]) -> list[LienPropose]:
    groupes: dict[tuple, LienPropose] = {}
    for lien in liens:
        cle = (lien.consommateur_composant_id, lien.fournisseur_composant_id,
               lien.interface_id or lien.operation, lien.environment)
        existant = groupes.get(cle)
        if existant is None:
            groupes[cle] = lien
            continue
        groupes[cle] = replace(
            existant,
            confiance=max(existant.confiance, lien.confiance),
            verifications=tuple(_uniques([*existant.verifications, *lien.verifications])),
            preuves=tuple(_uniques([*existant.preuves, *lien.preuves])),
            missing_evidence="; ".join(_uniques(
                [existant.missing_evidence, lien.missing_evidence])).strip("; "),
            next_check="; ".join(_uniques([existant.next_check, lien.next_check])).strip("; "),
            unknowns=tuple(_uniques([*existant.unknowns, *lien.unknowns])),
        )
    return list(groupes.values())


def _contradictions(liens: list[LienPropose]) -> tuple[list[LienPropose], list[QuestionLien]]:
    groupes: dict[tuple, list[LienPropose]] = {}
    for lien in liens:
        if lien.nature != "mesh":
            continue
        groupes.setdefault((lien.consommateur_composant_id, lien.operation,
                            lien.environment), []).append(lien)
    marques: dict[str, LienPropose] = {}
    questions: list[QuestionLien] = []
    for (consommateur, operation, environment), groupe in groupes.items():
        applications = {lien.fournisseur_application_id for lien in groupe
                        if lien.fournisseur_application_id}
        if len(applications) <= 1:
            continue
        candidats = [{
            "composant_id": lien.fournisseur_composant_id,
            "application_id": lien.fournisseur_application_id,
            "operation": lien.operation,
            "service": lien.fournisseur_service,
        } for lien in groupe]
        for lien in groupe:
            marques[lien.id] = replace(
                lien, state="conteste",
                missing_evidence="deux producteurs incompatibles pour la même opération",
                next_check="trancher entre les producteurs candidats avec le propriétaire",
            )
        questions.append(QuestionLien(
            type="CONTRADICTION",
            sujet=f"{consommateur} → {operation}",
            question=f"Deux producteurs revendiquent {operation} pour {consommateur}. "
                     "Lequel est réellement appelé en production ?",
            environment=environment, composant_id=consommateur,
            application_id=groupe[0].consommateur_application_id,
            candidats=tuple(candidats),
            missing_evidence="preuves de configuration et d'observation incompatibles",
            next_check="confronter la gateway, la trace et la déclaration du propriétaire",
            preuves=tuple(_uniques([preuve for lien in groupe for preuve in lien.preuves])),
        ))
    return [marques.get(lien.id, lien) for lien in liens], questions


def _externe(appel: Appel, cible: Cible) -> LienPropose:
    return LienPropose(
        consommateur_composant_id=appel.composant_id,
        consommateur_application_id=appel.application_id,
        fournisseur_composant_id="", fournisseur_application_id="",
        fournisseur_service=cible.host, operation=f"{appel.methode} {cible.chemin}".strip(),
        protocole=appel.protocole, environment=appel.environment, portee="UNKNOWN",
        nature="externe", state="suggere", confiance=0.6,
        verifications=("configure",), preuves=tuple([*appel.preuves, *cible.preuves]),
        unknowns=("contrat et propriétaire du fournisseur externe non vérifiés",),
        missing_evidence="fournisseur externe : aucun Twin interne ne porte ce service",
        next_check="vérifier le contrat, le propriétaire et l'usage du fournisseur externe",
    )


def moteur_liens(extractions, declarations=(), traces=()) -> RapportLiens:
    """Extrait les liens possibles d'un ensemble de dépôts déjà lus.

    `extractions` contient des `ExtractionDepot`. `declarations` complète les identités
    manquantes. `traces` ajoute des appels observés, sans jamais confirmer un lien.
    """
    extractions = list(extractions or ())
    index = IndexIdentites()
    interfaces: list[Interface] = []
    appels: list[Appel] = []
    diagnostics: list[str] = []
    for extraction in extractions:
        if not isinstance(extraction, ExtractionDepot):
            raise TypeError("extraction attendue : ExtractionDepot")
        index.ajouter_extraction(extraction)
        interfaces.extend(extraction.interfaces)
        appels.extend(extraction.appels)
        diagnostics.extend(extraction.diagnostics)
    for declaration in declarations or ():
        if not isinstance(declaration, IdentiteDeclaree):
            raise TypeError("déclaration attendue : IdentiteDeclaree")
        index.ajouter_declaration(declaration)
    traces = [trace for trace in (traces or ()) if isinstance(trace, Appel)]
    appels.extend(traces)
    interfaces = _unifier_interfaces(interfaces)
    index_configurations = _configurations(extractions)

    liens: list[LienPropose] = []
    questions: list[QuestionLien] = []
    for appel in appels:
        cible = _resoudre(appel, index, index_configurations)
        if cible.status == "externe":
            liens.append(_externe(appel, cible))
            continue
        candidates = _candidates(appel, cible, interfaces)
        if not candidates:
            if cible.status == "propriete_absente":
                questions.append(_question(
                    appel, cible, "PROPRIETE_ABSENTE",
                    f"Où est définie la propriété {_nom_propriete(appel.cible)} "
                    f"pour {appel.composant_id} en {appel.environment} ?"))
            elif cible.status == "service_inconnu":
                questions.append(_question(
                    appel, cible, "SERVICE_INCONNU",
                    f"Quel composant et quelle application fournissent le service "
                    f"{cible.service} en {appel.environment} ?"))
            else:
                questions.append(_question(
                    appel, cible, "PRODUCTEUR_INCONNU",
                    f"Quel composant expose {appel.methode} "
                    f"{cible.chemin or appel.cible} en {appel.environment} ?"))
            continue
        meilleur = candidates[0][0]
        retenus = [interface for score, interface in candidates if score == meilleur]
        if len({interface.composant_id for interface in retenus}) > 1:
            candidats = [{
                "composant_id": interface.composant_id,
                "application_id": interface.application_id,
                "operation": interface.operation,
                "service": interface.service_name,
            } for interface in retenus]
            questions.append(_question(
                appel, cible, "AMBIGU",
                f"Plusieurs composants exposent {appel.methode} "
                f"{cible.chemin or appel.cible} en {appel.environment}. Lequel est appelé ?",
                candidats=candidats))
        for interface in retenus:
            if interface.composant_id == appel.composant_id:
                continue
            liens.append(_lien(appel, interface, cible, index, traces, index_configurations))

    liens = _fusionner(liens)
    liens, questions_contradiction = _contradictions(liens)
    questions.extend(questions_contradiction)
    questions = list({
        (question.type, question.sujet, question.environment): question
        for question in questions
    }.values())
    liens.sort(key=lambda lien: (lien.nature, lien.consommateur_composant_id,
                                 lien.fournisseur_composant_id, lien.operation))
    questions.sort(key=lambda question: (question.type, question.sujet))
    return RapportLiens(
        liens=tuple(liens), questions=tuple(questions),
        diagnostics=tuple(dict.fromkeys(diagnostics)),
    )


def revoir_lien(lien: LienPropose, decision: str, acteur: str, *, motif: str = "") -> LienPropose:
    """Confirme, rejette ou conteste un soupçon. L'acteur et le motif restent attachés."""
    acteur = _texte(acteur, 200)
    if not acteur:
        raise ValueError("acteur obligatoire")
    gestion = str(decision or "").strip().lower()
    if gestion not in ("accepter", "rejeter", "contester"):
        raise ValueError("décision attendue : accepter, rejeter ou contester")
    etat = {"accepter": "confirme", "rejeter": "rejete", "contester": "conteste"}[gestion]
    preuve = Preuve(
        source="DECLARATION", locator=f"revue:{acteur}",
        detail=f"{gestion} {motif}".strip(), mode="DECLARE", confidence=1.0)
    manque = lien.missing_evidence
    if gestion == "accepter" and lien.nature == "mesh" and lien.portee not in (
            "SERVICE", "PARTNER", "PUBLIC"):
        manque = "; ".join(filter(None, [manque,
                                         "portée non éligible : relation Mesh non créée"]))
    return replace(
        lien, state=etat, preuves=tuple([*lien.preuves, preuve]),
        missing_evidence=manque,
        next_check="" if gestion == "accepter" and not manque else lien.next_check,
    )


def filtrer_local(rapport: RapportLiens, twin_id: str) -> RapportLiens:
    """Ne garde que les liens et questions où le Twin naissant est impliqué.

    La naissance déclenche une découverte locale bornée : le nouveau Twin ne doit
    ni payer ni exposer les liens entre deux autres Twins.
    """
    twin_id = str(twin_id or "").strip()
    if not twin_id:
        return RapportLiens(diagnostics=rapport.diagnostics)
    liens = tuple(
        lien for lien in rapport.liens
        if twin_id in (lien.consommateur_composant_id, lien.fournisseur_composant_id))
    questions = tuple(
        question for question in rapport.questions
        if question.composant_id == twin_id
        or any(str(candidat.get("composant_id") or "") == twin_id
               for candidat in question.candidats))
    return RapportLiens(liens=liens, questions=questions,
                        diagnostics=rapport.diagnostics)


def vers_proposition(lien: LienPropose, tenant_id: str, *,
                     owners: Mapping[str, str] | None = None) -> PropositionRelation:
    """Transforme un lien Mesh en proposition gouvernée, sans jamais le confirmer."""
    if lien.nature != "mesh" or not lien.fournisseur_application_id:
        raise ValueError("seul un lien Mesh avec fournisseur identifié devient une proposition")
    owners = owners or {}
    etat = {
        "suggere": "supposee",
        "confirme": "confirmee",
        "conteste": "contestee",
        "rejete": "obsolete",
    }[lien.state]
    if lien.state == "confirme":
        mode = "DECLARED"
    elif "observe" in lien.verifications:
        mode = "OBSERVED"
    else:
        mode = "INFERRED"
    preuves = tuple(preuve.locator for preuve in lien.preuves)
    frontieres = tuple(preuve.locator for preuve in lien.preuves
                       if preuve.source in ("CONTRAT", "DEPLOIEMENT", "HELM"))
    return PropositionRelation(
        tenant_id=tenant_id,
        consumer_id=lien.consommateur_composant_id,
        provider_id=lien.fournisseur_composant_id,
        object=lien.operation, environment=lien.environment, predicate="CONSOMME",
        mode=mode, state=etat, confidence=lien.confiance, evidence_ids=preuves,
        consumer_owner=(owners.get(lien.consommateur_composant_id)
                        or owners.get(lien.consommateur_application_id, "")),
        provider_owner=(owners.get(lien.fournisseur_composant_id)
                        or owners.get(lien.fournisseur_application_id, "")),
        justification=(
            f"lien {lien.nature} découvert dans le code, la configuration, le déploiement "
            f"ou le contrat ; vérifications : {', '.join(lien.verifications) or 'aucune'}"
        ),
        unknowns=lien.unknowns, transport=lien.protocole, portee=lien.portee,
        boundary_evidence=frontieres, via=lien.interface_id,
        consumer_application_id=lien.consommateur_application_id,
        provider_application_id=lien.fournisseur_application_id,
    )


def vers_resolution_case(question: QuestionLien, tenant_id: str, twin_id: str, *,
                         owner: str = "") -> ResolutionCase:
    """Transforme une question ouverte en cas durable, avec la prochaine vérification."""
    return ResolutionCase(
        tenant_id=tenant_id, twin_id=twin_id, reference=question.sujet,
        environment=question.environment, missing_evidence=question.missing_evidence,
        next_check=question.next_check, owner=owner,
        evidence_ids=tuple(preuve.locator for preuve in question.preuves),
        candidates=question.candidats,
    )


def _methode_et_chemin(valeur: str) -> tuple[str, str]:
    texte = " ".join(str(valeur or "").split())
    trouve = re.match(r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(\S+)$", texte, re.I)
    if trouve:
        return trouve.group(1).upper(), _normaliser_chemin(trouve.group(2))
    if "://" in texte:
        return "", _normaliser_chemin(urlsplit(texte).path)
    if texte.startswith("/"):
        return "", _normaliser_chemin(texte)
    return "", ""


def _appel_depuis_consommation(manifeste, consommation, application: str) -> Appel:
    reference = str(consommation.logical_ref or "").strip()
    methode, chemin = _methode_et_chemin(consommation.target_hint or reference)
    protocole = str(consommation.kind or "HTTP").upper()
    if reference.startswith("${"):
        cible_type, cible = "PROPRIETE", reference
    elif "://" in reference:
        cible_type, cible = "URL", reference
        chemin = chemin or _normaliser_chemin(urlsplit(reference).path)
    elif reference.startswith(("jms/", "queue/", "topic/")) or protocole in ("JMS", "KAFKA", "JNDI"):
        cible_type = "QUEUE" if protocole in ("JMS", "KAFKA") else "JNDI"
        cible = reference
        chemin = reference
    elif re.match(r"^[A-Za-z0-9_.-]+$", reference) and "/" not in reference:
        cible_type, cible = "PROPRIETE", reference
    elif reference.startswith("/"):
        cible_type, cible = "CHEMIN", reference
        chemin = _normaliser_chemin(reference)
    else:
        cible_type, cible = "SERVICE", reference
    preuves = tuple(
        Preuve(source="CODE" if str(identifiant).startswith("code:") else "CONTRAT",
               locator=str(identifiant), detail=reference,
               confidence=consommation.confidence)
        for identifiant in consommation.evidence_ids)
    return Appel(
        composant_id=manifeste.twin_id, application_id=application,
        protocole=protocole, cible=cible, cible_type=cible_type,
        methode=methode or "ANY", chemin=chemin,
        operation=f"{methode} {chemin}".strip() or reference,
        environment=consommation.environment, source_kind="CONTRAT",
        preuves=preuves,
    )


def extractions_depuis_manifests(manifests, bindings=()) -> list[ExtractionDepot]:
    """Branche le moteur sur les manifestes et bindings déjà persistés.

    Les manifestes fournissent les interfaces et les appels déclarés ; les bindings
    fournissent les services, routes de passerelle et propriétés déjà résolus.
    """
    manifests = list(manifests or ())
    par_twin = {manifeste.twin_id: manifeste for manifeste in manifests}
    bindings = list(bindings or ())
    services = {}
    for binding in bindings:
        if str(getattr(binding, "kind", "")).upper() != "SERVICE":
            continue
        manifeste = par_twin.get(binding.valeur)
        application = (manifeste.application_id or manifeste.twin_id) if manifeste else binding.valeur
        services.setdefault(binding.valeur, []).append(
            (binding.nom, application, binding.environment))
    extractions = []
    for manifeste in manifests:
        application = manifeste.application_id or manifeste.twin_id
        service_name = services.get(manifeste.twin_id, [("", "", manifeste.tenant_id)])[0][0]
        interfaces = []
        for exposition in manifeste.exposures:
            methode, chemin = _methode_et_chemin(exposition.operation)
            preuves = tuple(
                Preuve(source="CODE" if str(identifiant).startswith("code:") else "CONTRAT",
                       locator=str(identifiant), detail=exposition.operation,
                       confidence=exposition.confidence)
                for identifiant in exposition.evidence_ids)
            interfaces.append(Interface(
                composant_id=manifeste.twin_id, application_id=application,
                protocole=exposition.kind, operation=exposition.operation,
                methode=methode, chemin=chemin, nom=exposition.operation,
                environment=exposition.environment, portee=exposition.portee,
                source_kind="CODE" if any(preuve.source == "CODE" for preuve in preuves)
                else "CONTRAT",
                service_name=service_name, preuves=preuves,
            ))
        appels = [
            _appel_depuis_consommation(manifeste, consommation, application)
            for consommation in manifeste.consumptions
        ]
        extractions.append(ExtractionDepot(
            composant=Composant(
                application_id=application,
                nom=manifeste.twin_id, type="APPLICATION", owner=manifeste.owner),
            interfaces=tuple(interfaces), appels=tuple(appels),
        ))

    if not bindings:
        return extractions
    tenant = manifests[0].tenant_id if manifests else "inconnu"
    composant_gateway = Composant(
        application_id=tenant, nom="liens-declares", type="GATEWAY")
    deployments = []
    configurations = []
    interfaces_binding = []
    for binding in bindings:
        kind = str(getattr(binding, "kind", "")).upper()
        environment = str(getattr(binding, "environment", "inconnu"))
        preuve = Preuve(
            source="CONFIG" if kind in ("PROPERTY", "JNDI") else "DEPLOIEMENT",
            locator=str(getattr(binding, "source", "") or f"binding:{kind}"),
            detail=f"{kind} {binding.nom}", confidence=0.9)
        if kind == "SERVICE":
            manifeste = par_twin.get(binding.valeur)
            deployments.append(Deploiement(
                composant_id=binding.valeur,
                application_id=((manifeste.application_id or manifeste.twin_id)
                                if manifeste else binding.valeur),
                environment=environment, service_name=binding.nom, preuves=(preuve,)))
        elif kind == "GATEWAY_ROUTE":
            deployments.append(Deploiement(
                composant_id=composant_gateway.id,
                application_id=composant_gateway.application_id,
                environment=environment, service_name="",
                routes=(RoutePasserelle(
                    chemin=binding.nom, service=binding.valeur,
                    environment=environment, preuves=(preuve,)),),
                preuves=(preuve,)))
        elif kind == "PROPERTY":
            configurations.append(Configuration(
                cle=binding.nom, valeur=binding.valeur,
                fichier=str(getattr(binding, "source", "") or "binding"),
                environment=environment, source_kind="CONFIG", preuves=(preuve,)))
        elif kind == "JNDI":
            # Le binding traduit un nom JNDI vers une destination (file, topic, service).
            configurations.append(Configuration(
                cle=f"jndi:{binding.nom}", valeur=binding.valeur,
                fichier=str(getattr(binding, "source", "") or "binding"),
                environment=environment, source_kind="CONFIG", preuves=(preuve,)))
        elif kind in ("QUEUE", "TOPIC"):
            manifeste = par_twin.get(binding.valeur)
            interfaces_binding.append(Interface(
                composant_id=binding.valeur,
                application_id=((manifeste.application_id or manifeste.twin_id)
                                if manifeste else binding.valeur),
                protocole="JMS" if kind == "QUEUE" else "KAFKA",
                operation=binding.nom, methode="RECOIT", chemin=binding.nom,
                environment=environment, source_kind="CONFIG", preuves=(preuve,)))
    extractions.append(ExtractionDepot(
        composant=composant_gateway, interfaces=tuple(interfaces_binding),
        deploiements=tuple(deployments), configurations=tuple(configurations)))
    return extractions
