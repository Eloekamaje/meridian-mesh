"""Le graphe d'interfaces : ce qu'une application offre et consomme, même hors de son code.

Fondation pure (aucune base, aucun réseau, aucun modèle) : un modèle minimal, deux parseurs (OpenAPI et configuration)
et une provenance vérifiable. Un identifiant est calculé sur le contenu, jamais sur un compteur : deux lectures du même
document rendent les mêmes identifiants. Une assertion `declared` dit ce qu'une source déclare ; elle ne devient jamais
`observed` par simple lecture d'un fichier.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Optional
from urllib.parse import unquote_plus, urlsplit, urlunsplit

METHODES_HTTP = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
_RE_EXPOSE = re.compile(r"^\s*(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/[^\s]*)\s*$", re.IGNORECASE)
CONFIANCE_HAUTE = 0.95
CONFIANCE_MOYENNE = 0.6
CONFIANCE_BASSE = 0.4

_MARQUEURS_SECRETS = ("password", "passwd", "secret", "token", "credential", "authorization")
_CLES_SECRETES = frozenset({"pwd", "pass", "auth", "apikey", "api_key", "api-key", "access_key",
                            "private_key", "key"})
_URL = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)


def _empreinte(*parties: Any) -> str:
    """Empreinte canonique : le même contenu donne toujours la même valeur, quel que soit l'ordre des clés."""
    brut = json.dumps(parties, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()


def _id(prefixe: str, *parties: Any) -> str:
    """Identifiant opaque et stable, préfixé par le type d'objet."""
    return f"{prefixe}_{_empreinte(*parties)[:16]}"


def _digest(texte: str) -> str:
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def _texte(valeur: Any) -> Optional[str]:
    if valeur is None:
        return None
    texte = str(valeur).strip()
    return texte or None


@dataclass(frozen=True)
class Contract:
    id: str
    format: str
    version: Optional[str]
    digest: str
    locator: str
    application_id: str
    environment: str


@dataclass(frozen=True)
class Operation:
    id: str
    contract_id: str
    protocol: str
    method: str
    path: str
    name: str
    version: Optional[str]
    environment: str

    @property
    def action(self) -> str:
        """Le chemin pour REST, l'action pour SOAP/gRPC : même champ, nom métier explicite."""
        return self.path


@dataclass(frozen=True)
class Binding:
    id: str
    protocol: str
    url: str
    environment: str
    gateway: Optional[str] = None


@dataclass(frozen=True)
class Assertion:
    subject: str
    predicate: str
    object: str
    mode: str
    source: str
    locator: str
    environment: str
    confidence: float
    evidence: str
    observed_at: Optional[str] = None
    valid_from: Optional[str] = None


def _cle_assertion(a: Assertion) -> tuple:
    return (a.subject, a.predicate, a.object, a.mode, a.source, a.locator, a.environment, a.confidence,
            a.evidence, a.observed_at, a.valid_from)


def _uniques(objets: Iterable[Any], cle) -> list:
    vus, sortie = set(), []
    for objet in objets:
        marque = cle(objet)
        if marque not in vus:
            vus.add(marque)
            sortie.append(objet)
    return sortie


@dataclass
class InterfaceGraph:
    contracts: list[Contract] = field(default_factory=list)
    operations: list[Operation] = field(default_factory=list)
    bindings: list[Binding] = field(default_factory=list)
    assertions: list[Assertion] = field(default_factory=list)
    partial: bool = False
    diagnostics: list[str] = field(default_factory=list)

    def index(self) -> dict:
        """Index simple, sans fusion d'identité : par application, puis par prédicat."""
        applications: dict[str, dict[str, list]] = {}
        predicats: dict[str, list[Assertion]] = {}
        for a in self.assertions:
            applications.setdefault(a.subject, {"contracts": [], "operations": [], "assertions": []})
            predicats.setdefault(a.predicate, []).append(a)
        for c in self.contracts:
            applications.setdefault(c.application_id, {"contracts": [], "operations": [], "assertions": []})
            applications[c.application_id]["contracts"].append(c)
        for o in self.operations:
            contrat = next((c for c in self.contracts if c.id == o.contract_id), None)
            application_id = contrat.application_id if contrat else o.environment
            applications.setdefault(application_id, {"contracts": [], "operations": [], "assertions": []})
            applications[application_id]["operations"].append(o)
        for a in self.assertions:
            applications[a.subject]["assertions"].append(a)
        return {"applications": applications, "predicates": predicats}

    def as_dict(self) -> dict:
        return {
            "contracts": [asdict(c) for c in self.contracts],
            "operations": [asdict(o) for o in self.operations],
            "bindings": [asdict(b) for b in self.bindings],
            "assertions": [asdict(a) for a in self.assertions],
            "partial": self.partial,
            "diagnostics": list(self.diagnostics),
        }


def _dedupliquer(graph: InterfaceGraph) -> InterfaceGraph:
    graph.contracts = _uniques(graph.contracts, lambda c: c.id)
    graph.operations = _uniques(graph.operations, lambda o: o.id)
    graph.bindings = _uniques(graph.bindings, lambda b: b.id)
    graph.assertions = _uniques(graph.assertions, _cle_assertion)
    return graph


def merge(graphs: Iterable[InterfaceGraph]) -> InterfaceGraph:
    """Réunit plusieurs graphes en dédupliquant les identifiants exacts. Aucun rapprochement sémantique."""
    resultat = InterfaceGraph()
    for graph in graphs:
        if graph is None:
            continue
        resultat.contracts.extend(graph.contracts)
        resultat.operations.extend(graph.operations)
        resultat.bindings.extend(graph.bindings)
        resultat.assertions.extend(graph.assertions)
        resultat.partial = resultat.partial or graph.partial
        for diagnostic in graph.diagnostics:
            if diagnostic not in resultat.diagnostics:
                resultat.diagnostics.append(diagnostic)
    return _dedupliquer(resultat)


def _charger_document(texte: str) -> tuple[Optional[Any], Optional[str]]:
    """JSON d'abord ; YAML seulement si PyYAML est présent. Le message d'erreur ne recopie jamais le document."""
    try:
        return json.loads(texte), None
    except json.JSONDecodeError as erreur_json:
        try:
            import yaml
        except ImportError:
            return None, f"JSON invalide ({erreur_json.msg}) et PyYAML absent : document non lu"
        try:
            donnees = yaml.safe_load(texte)
        except Exception as erreur:  # noqa: BLE001 - un document hostile ne doit jamais faire tomber la lecture
            return None, f"document illisible : {type(erreur).__name__}"
        return (donnees, None) if donnees is not None else (None, "document vide")


def _url_binding(brut: Any) -> Optional[str]:
    """Une URL de binding : identifiants retirés ; une URL relative de serveur OpenAPI reste lisible."""
    propre = _texte(brut)
    if not propre or "${" in propre:
        return None
    if propre.lower().startswith(("http://", "https://")):
        return _assainir_url(propre)
    return propre


def parse_openapi(application_id: str, texte: str, locator: str, environment: str = "inconnu") -> InterfaceGraph:
    """Lit un document OpenAPI (JSON ou YAML) sans jamais échouer : ce qui est lisible est retenu, le reste est dit."""
    texte = texte if isinstance(texte, str) else ""
    digest = _digest(texte)
    diagnostics: list[str] = []
    donnees, erreur = (None, "document vide") if not texte.strip() else _charger_document(texte)
    if erreur:
        diagnostics.append(erreur)
    if donnees is not None and not isinstance(donnees, dict):
        diagnostics.append("racine du document : objet attendu")
        donnees = None

    version = None
    if isinstance(donnees, dict):
        info = donnees.get("info")
        if not isinstance(info, dict):
            diagnostics.append("info absente ou invalide")
        else:
            version = _texte(info.get("version"))
            if version is None:
                diagnostics.append("info.version absente")

    contrat = Contract(
        id=_id("ctr", "openapi", application_id, environment, locator, digest),
        format="openapi", version=version, digest=digest, locator=locator,
        application_id=application_id, environment=environment)
    graph = InterfaceGraph(contracts=[contrat], diagnostics=diagnostics, partial=bool(diagnostics))
    if not isinstance(donnees, dict):
        return graph

    _serveurs_openapi(graph, donnees, contrat)
    _operations_openapi(graph, donnees, contrat)
    graph.partial = bool(graph.diagnostics)
    return _dedupliquer(graph)


def _serveurs_openapi(graph: InterfaceGraph, donnees: dict, contrat: Contract) -> None:
    serveurs = donnees.get("servers")
    if serveurs is None:
        return
    if not isinstance(serveurs, list):
        graph.diagnostics.append("servers : liste attendue")
        return
    for serveur in serveurs:
        url = _url_binding(serveur.get("url")) if isinstance(serveur, dict) else None
        if url is None:
            graph.diagnostics.append("serveur sans url lisible")
            continue
        graph.bindings.append(Binding(
            id=_id("bnd", "rest", url, contrat.environment, None), protocol="rest", url=url,
            environment=contrat.environment))


def _operations_openapi(graph: InterfaceGraph, donnees: dict, contrat: Contract) -> None:
    chemins = donnees.get("paths")
    if not isinstance(chemins, dict):
        graph.diagnostics.append("paths absente ou invalide")
        return
    for chemin, element in chemins.items():
        if not isinstance(chemin, str) or not isinstance(element, dict):
            graph.diagnostics.append(f"chemin ignoré : {chemin!r}")
            continue
        for methode in METHODES_HTTP:
            detail = element.get(methode)
            if detail is None:
                continue
            if not isinstance(detail, dict):
                graph.diagnostics.append(f"opération {methode.upper()} {chemin} invalide")
                continue
            methode_haute = methode.upper()
            nom = _texte(detail.get("operationId")) or f"{methode_haute} {chemin}"
            operation = Operation(
                id=_id("op", contrat.id, "rest", methode_haute, chemin, nom), contract_id=contrat.id,
                protocol="rest", method=methode_haute, path=chemin, name=nom, version=contrat.version,
                environment=contrat.environment)
            graph.operations.append(operation)
            graph.assertions.append(Assertion(
                subject=contrat.application_id, predicate="EXPOSE", object=f"{methode_haute} {chemin}",
                mode="declared", source="openapi", locator=contrat.locator, environment=contrat.environment,
                confidence=CONFIANCE_HAUTE, evidence=contrat.digest))


def _sans_commentaire(ligne: str) -> str:
    """Retire un commentaire de configuration sans confondre un `#` de fragment d'URL avec un commentaire."""
    if ligne.lstrip().startswith(("#", "!", ";")):
        return ""
    guillemet = None
    for i, caractere in enumerate(ligne):
        if guillemet:
            if caractere == guillemet:
                guillemet = None
            continue
        if caractere in "\"'":
            guillemet = caractere
        elif caractere == "#" and (i == 0 or ligne[i - 1].isspace()):
            return ligne[:i]
    return ligne


def _cle_de_ligne(ligne: str) -> str:
    contenu = ligne.strip()
    if contenu.startswith("- "):
        contenu = contenu[2:].strip()
    for separateur in ("=", ":"):
        if separateur in contenu:
            return contenu.split(separateur, 1)[0].strip().strip("\"'").lower()
    return ""


def _nettoyer_url(url: str) -> str:
    return url.rstrip(".,;:)]}")


def _cle_sensible(cle: str) -> bool:
    normalisee = unquote_plus(cle).strip().lower()
    return (normalisee in _CLES_SECRETES or normalisee.endswith(("_key", "-key"))
            or any(marque in normalisee for marque in _MARQUEURS_SECRETS))


def _query_sans_secrets(query: str) -> str:
    morceaux = []
    for morceau in query.split("&"):
        cle, separateur, _ = morceau.partition("=")
        morceaux.append(f"{cle}{separateur}***" if separateur and _cle_sensible(cle) else morceau)
    return "&".join(morceaux)


def _assainir_url(url: str) -> Optional[str]:
    """Retire les identifiants et masque les secrets de requête ; jamais `user:password@` dans le résultat."""
    try:
        parties = urlsplit(url)
        if parties.scheme.lower() not in ("http", "https") or not parties.hostname:
            return None
        hote = parties.hostname.lower()
        if ":" in hote and not hote.startswith("["):
            hote = f"[{hote}]"
        port = parties.port
        if port and not ((parties.scheme.lower() == "http" and port == 80)
                         or (parties.scheme.lower() == "https" and port == 443)):
            hote = f"{hote}:{port}"
        return urlunsplit((parties.scheme.lower(), hote, parties.path, _query_sans_secrets(parties.query), ""))
    except (ValueError, UnicodeError):
        return None


def _est_wsdl(url: str, cle: str) -> bool:
    parties = urlsplit(url)
    return ("wsdl" in cle.lower() or parties.path.lower().endswith(".wsdl")
            or "wsdl" in parties.query.lower())


def depuis_claims(application_id: str, claims: Iterable[dict], environment: str = "inconnu") -> InterfaceGraph:
    """Transforme les claims `EXPOSE` du code en opérations déclarées, pour les dépôts sans OpenAPI statique.

    Le code est une source déclarée, pas une observation runtime : les assertions restent `declared` et gardent la
    preuve du claim (`locator` / `claim id`). Une ligne `EXPOSE` mal formée est signalée, jamais inventée.
    """
    claims = [c for c in (claims or []) if isinstance(c, dict)]
    utiles = []
    for claim in claims:
        if str(claim.get("predicat") or "").upper() != "EXPOSE":
            continue
        m = _RE_EXPOSE.match(str(claim.get("objet") or ""))
        if not m:
            continue
        methode, chemin = m.group(1).upper(), m.group(2)
        preuve = str(claim.get("preuve") or claim.get("id") or "claim:expose")
        utiles.append({
            "method": methode, "path": chemin, "preuve": preuve,
            "confidence": min(float(claim.get("confiance") or 0.6), 0.8),
            "claim_id": claim.get("id"),
        })
    if not utiles:
        return InterfaceGraph(partial=True, diagnostics=["aucune exposition `EXPOSE` exploitable dans les claims"])
    empreinte = _empreinte(application_id, environment, [(u["method"], u["path"], u["preuve"]) for u in utiles])
    contrat = Contract(
        id=_id("ctr", "code", application_id, environment, empreinte), format="code", version=None,
        digest=empreinte, locator="code", application_id=application_id, environment=environment)
    graph = InterfaceGraph(contracts=[contrat])
    for u in utiles:
        operation = Operation(
            id=_id("op", contrat.id, "rest", u["method"], u["path"], u["method"]), contract_id=contrat.id,
            protocol="rest", method=u["method"], path=u["path"], name=f"{u['method']} {u['path']}",
            version=None, environment=environment)
        graph.operations.append(operation)
        graph.assertions.append(Assertion(
            subject=application_id, predicate="EXPOSE", object=f"{u['method']} {u['path']}", mode="declared",
            source="code", locator=u["preuve"], environment=environment, confidence=u["confidence"],
            evidence=str(u["claim_id"] or u["preuve"])))
    return _dedupliquer(graph)


def parse_config(application_id: str, texte: str, locator: str,
                 environment: str = "inconnu") -> InterfaceGraph:
    """Lit properties/YAML/.env : les URLs http(s) et WSDL deviennent des bindings et des assertions candidates.

    Les commentaires et les placeholders `${...}` sont ignorés, les identifiants d'URL retirés, les secrets jamais
    recopiés et les doublons supprimés. La confiance reste basse (URL nue) ou moyenne (WSDL) : c'est une déclaration.
    """
    texte = texte if isinstance(texte, str) else ""
    digest = _digest(texte)
    trouves: dict[str, dict] = {}
    for ligne in texte.splitlines():
        contenu = _sans_commentaire(ligne)
        if not contenu.strip():
            continue
        cle = _cle_de_ligne(contenu)
        for brute in _URL.findall(contenu):
            nettoyee = _nettoyer_url(brute)
            if "${" in nettoyee:
                continue
            url = _assainir_url(nettoyee)
            if url is None:
                continue
            soap = _est_wsdl(url, cle)
            if url in trouves:
                if soap:
                    trouves[url]["protocol"] = "soap"
                    trouves[url]["confidence"] = CONFIANCE_MOYENNE
            else:
                trouves[url] = {"protocol": "soap" if soap else "rest",
                                "confidence": CONFIANCE_MOYENNE if soap else CONFIANCE_BASSE}

    graph = InterfaceGraph()
    for url, info in trouves.items():
        binding = Binding(
            id=_id("bnd", info["protocol"], url, environment, None), protocol=info["protocol"], url=url,
            environment=environment)
        graph.bindings.append(binding)
        graph.assertions.append(Assertion(
            subject=application_id, predicate="CONSOMME", object=url, mode="declared", source="config",
            locator=locator, environment=environment, confidence=info["confidence"], evidence=digest))
    return _dedupliquer(graph)
