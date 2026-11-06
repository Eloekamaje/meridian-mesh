"""Liens déterministes entre observations d'indexation legacy.

Le module ne lit aucun fichier, n'exécute aucun code et ne consulte aucun service :
il ne travaille que sur les :class:`~meridian.domain.code_index.Observation` déjà
produites par les sidecars. Un lien n'est émis que lorsque la cible est prouvée et
unique ; une cible absente ou ambiguë ne produit aucun lien.

Familles de liens émises :

- ``jsp_to_servlet_mapping``, ``servlet_mapping_to_servlet``, ``servlet_to_java_type`` ;
- ``jsp_to_spring_route``, ``spring_controller_to_java_type`` ;
- ``java_to_jpa_entity``, ``sql_table_to_jpa_table`` ;
- ``sql_fk_to_table``, ``sql_fk_to_column`` ;
- ``cobol_call_to_program``, ``cobol_copy_to_copybook`` ;
- ``cobol_file_to_jcl_dataset``, ``jcl_dataset_to_cobol_file`` ;
- ``jcl_program_to_cobol_program``, ``jcl_proc_to_jcl_proc``.
"""
from __future__ import annotations

import posixpath
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from html import unescape
from urllib.parse import urlsplit

from meridian.domain.code_index import Observation

__all__ = ["Link", "STATUTS_LIEN", "lier", "rapport_liens"]

STATUTS_LIEN = ("linked", "inferred", "ambiguous")

_METHODES_HTTP = frozenset({
    "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE",
})
_KINDS_JSP = frozenset({"jsp_form", "jsp_include", "jsp_forward", "jsp_link"})
_KINDS_ROUTE = frozenset({"spring_route", "java_route", "spring_mapping"})
_KINDS_TYPE_JAVA = frozenset({
    "java_type", "java_class", "java_interface", "java_enum", "java_record",
    "java_controller", "java_service", "java_repository", "java_entity",
    "jpa_entity", "jpa_table", "java_table", "class", "type",
})
_KINDS_NON_TYPE_JAVA = frozenset({
    "java_import", "import", "java_field", "field", "java_attribute", "java_method",
    "method", "java_annotation", "annotation", "java_package", "package",
    "java_parameter", "parameter", "java_local_variable", "java_constructor",
    "java_route", "spring_route", "spring_mapping",
})
_KINDS_ENTITE_JPA = frozenset({
    "java_entity", "jpa_entity", "entity", "jpa_table", "java_table", "entity_class",
})
_KINDS_IMPORT = frozenset({"java_import", "import"})
_KINDS_CHAMP = frozenset({"java_field", "field", "java_attribute"})
_ROLES_SOURCE_JPA = frozenset({"controller", "service", "repository"})

_CONTEXTE_EL = re.compile(
    r"\$\{\s*(?:pageContext\.request\.contextPath|request\.contextPath|"
    r"pageContext\.servletContext\.contextPath)\s*\}",
    re.I,
)
_CONTEXTE_SCRIPTLET = re.compile(r"<%=\s*(?:request\.)?getContextPath\(\)\s*%>", re.I)
_IMPORT_JAVA = re.compile(r"^\s*import\s+(?:static\s+)?", re.I)
_IDENT_JAVA = re.compile(r"[A-Za-z_$][\w.$]*")
_GENERIQUES = re.compile(r"<[^<>]*>")


def _texte(valeur, maximum=1000) -> str:
    return " ".join(str(valeur if valeur is not None else "").split())[:maximum]


def _serialisable(valeur):
    if valeur is None or isinstance(valeur, (str, int, float, bool)):
        return valeur
    if isinstance(valeur, Mapping):
        return {str(cle): _serialisable(item) for cle, item in valeur.items()}
    if isinstance(valeur, (list, tuple, set)):
        return [_serialisable(item) for item in valeur]
    return str(valeur)


@dataclass(frozen=True)
class Link:
    """Arête prouvée entre deux observations, avec provenance des deux côtés."""

    kind: str
    source_file: str
    source_symbol: str
    target_file: str
    target_symbol: str
    attributes: dict = field(default_factory=dict)
    confidence: float = 1.0
    status: str = "linked"
    evidence: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.status not in STATUTS_LIEN:
            raise ValueError(f"statut de lien inconnu : {self.status!r}")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confiance de lien hors bornes")
        for nom in ("kind", "source_file", "source_symbol", "target_file", "target_symbol"):
            object.__setattr__(self, nom, _texte(getattr(self, nom), 1000))
        object.__setattr__(self, "attributes", dict(self.attributes or {}))
        object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(self, "evidence", dict(self.evidence or {}))

    @property
    def fingerprint(self) -> tuple:
        return (self.kind, self.source_file, self.source_symbol,
                self.target_file, self.target_symbol)

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "source_file": self.source_file,
            "source_symbol": self.source_symbol,
            "target_file": self.target_file,
            "target_symbol": self.target_symbol,
            "attributes": _serialisable(self.attributes),
            "confidence": self.confidence,
            "status": self.status,
            "evidence": _serialisable(self.evidence),
        }


def _preuve(observation: Observation) -> dict:
    return {
        "provider": observation.provider,
        "parser": observation.parser,
        "parser_version": observation.parser_version,
        "file": observation.file,
        "kind": observation.kind,
        "symbol": observation.symbol,
        "start": observation.start,
        "end": observation.end,
        "status": observation.status,
        "commit": observation.commit,
    }


def _statut(source: Observation, cible: Observation, statut: str) -> str:
    if source.status in {"ambiguous", "conflict"} or cible.status in {"ambiguous", "conflict"}:
        return "ambiguous"
    return statut if statut in STATUTS_LIEN else "linked"


def _lien(kind: str, source: Observation, cible: Observation, attributes: dict | None = None,
          confidence: float = 1.0, status: str = "linked",
          via: Iterable[Observation] = (),
          target_symbol: str | None = None) -> Link:
    facteur = min(float(source.confidence), float(cible.confidence)) * float(confidence)
    return Link(
        kind=kind,
        source_file=source.file,
        source_symbol=source.symbol,
        target_file=cible.file,
        target_symbol=target_symbol or cible.symbol,
        attributes=dict(attributes or {}),
        confidence=max(0.0, min(1.0, facteur)),
        status=_statut(source, cible, status),
        evidence={
            "source": _preuve(source),
            "target": _preuve(cible),
            "via": [_preuve(observation) for observation in via if observation is not None],
            "source_file": source.file,
            "source_line": source.start,
            "target_file": cible.file,
            "target_line": cible.start,
        },
    )


def _valeur(attributes: Mapping, *noms) -> str:
    for nom in noms:
        if nom not in attributes:
            continue
        valeur = attributes[nom]
        if isinstance(valeur, (list, tuple, set)):
            for item in valeur:
                texte = _texte(item)
                if texte:
                    return texte
        else:
            texte = _texte(valeur)
            if texte:
                return texte
    return ""


def _valeurs(attributes: Mapping, *noms) -> list[str]:
    resultat: list[str] = []
    for nom in noms:
        if nom not in attributes:
            continue
        valeur = attributes[nom]
        if isinstance(valeur, (list, tuple, set)):
            resultat.extend(texte for texte in (_texte(item) for item in valeur) if texte)
        else:
            texte = _texte(valeur)
            if texte:
                resultat.append(texte)
    return _uniques_textes(resultat)


def _uniques_textes(valeurs: Iterable[str]) -> list[str]:
    vus: dict[str, str] = {}
    for valeur in valeurs:
        texte = _texte(valeur)
        if texte:
            vus.setdefault(texte.casefold(), texte)
    return list(vus.values())


def _uniques(observations: Iterable[Observation]) -> list[Observation]:
    vus: dict[tuple, Observation] = {}
    for observation in observations:
        vus.setdefault((observation.file, observation.symbol), observation)
    return list(vus.values())


def _simple_java(nom: str) -> str:
    texte = _texte(nom)
    while _GENERIQUES.search(texte):
        texte = _GENERIQUES.sub("", texte)
    texte = texte.replace("[]", "").strip().rstrip(";")
    if texte.endswith(".class"):
        texte = texte[:-6]
    texte = texte.rsplit(".", 1)[-1]
    return texte.rsplit("$", 1)[-1]


def _normaliser_java(nom: str) -> str:
    texte = _texte(nom)
    while _GENERIQUES.search(texte):
        texte = _GENERIQUES.sub("", texte)
    texte = texte.replace("[]", "").strip().rstrip(";")
    if texte.endswith(".class"):
        texte = texte[:-6]
    return texte


def _normaliser_table(nom: str) -> str:
    texte = _texte(nom).strip('"`[]')
    morceaux = [morceau.strip('"`[]') for morceau in texte.split(".") if morceau.strip('"`[]')]
    return morceaux[-1].upper() if morceaux else ""


def _normaliser_nom(nom: str) -> str:
    return _texte(nom).strip("\"'").casefold()


def _normaliser_programme(nom: str) -> str:
    return _texte(nom).strip("\"'").split("(", 1)[0].strip().upper()


def _normaliser_dataset(nom: str) -> str:
    return _texte(nom).strip("\"'").upper()


def _nettoyer_chemin(chemin: str) -> str:
    texte = _texte(chemin).replace("\\", "/")
    texte = re.sub(r";jsessionid=[^/?#]*", "", texte, flags=re.I)
    texte = re.sub(r"/+", "/", texte)
    if not texte:
        return ""
    if texte == "/":
        return "/"
    absolu = texte.startswith("/")
    normalise = posixpath.normpath(texte)
    if normalise == ".":
        return ""
    if absolu and not normalise.startswith("/"):
        normalise = "/" + normalise
    return normalise.rstrip("/") or "/"


def _nettoyer_cible(valeur: str) -> str:
    texte = unescape(_texte(valeur)).strip().strip("\"'")
    if not texte:
        return ""
    if texte.casefold().startswith(("javascript:", "mailto:", "tel:", "data:", "#")):
        return ""
    texte = _CONTEXTE_EL.sub("", texte)
    texte = _CONTEXTE_SCRIPTLET.sub("", texte)
    if "://" in texte or texte.startswith("//"):
        texte = urlsplit(texte).path or ""
    else:
        texte = texte.split("#", 1)[0].split("?", 1)[0]
    if "${" in texte or "#{" in texte or "<%" in texte:
        return ""
    texte = re.sub(r";jsessionid=[^/?#]*", "", texte, flags=re.I)
    return texte.strip()


def _chemins_candidats(cible: str, fichier_source: str) -> list[tuple[str, float]]:
    """Chemins possibles d'une cible JSP, avec le facteur de confiance associé."""
    texte = _nettoyer_cible(cible)
    if not texte:
        return []
    resultat: list[tuple[str, float]] = []

    def ajouter(chemin: str, facteur: float) -> None:
        normalise = _nettoyer_chemin(chemin)
        if not normalise:
            return
        for position, (existant, ancien) in enumerate(resultat):
            if existant == normalise:
                if facteur > ancien:
                    resultat[position] = (normalise, facteur)
                return
        resultat.append((normalise, facteur))

    if texte.startswith("/"):
        ajouter(texte, 1.0)
        morceaux = texte.strip("/").split("/")
        if len(morceaux) > 1:
            ajouter("/" + "/".join(morceaux[1:]), 0.92)
    else:
        dossier = posixpath.dirname(fichier_source.replace("\\", "/"))
        resolu = posixpath.join(dossier, texte) if dossier else texte
        if not resolu.startswith("/"):
            resolu = "/" + resolu
        ajouter(resolu, 0.98)
        ajouter("/" + texte.lstrip("/"), 0.9)
        morceaux = resolu.strip("/").split("/")
        if len(morceaux) > 1:
            ajouter("/" + "/".join(morceaux[1:]), 0.88)
    return resultat


def _qualite_servlet(motif: str, chemin: str) -> float | None:
    texte = _texte(motif)
    if not texte or texte == "/":
        return None
    if texte.startswith("*."):
        return 1.0 if chemin.casefold().endswith(texte[1:].casefold()) else None
    if texte.endswith("/*"):
        base = _nettoyer_chemin(texte[:-2])
        if not base:
            return None
        if chemin == base:
            return 1.0
        if chemin.startswith(base + "/"):
            return 0.98
        return None
    return 1.0 if chemin == _nettoyer_chemin(texte) else None


@lru_cache(maxsize=512)
def _regex_spring(motif: str) -> re.Pattern | None:
    texte = _nettoyer_chemin(motif)
    if not texte:
        return None
    morceaux: list[str] = []
    i = 0
    while i < len(texte):
        if texte.startswith("**", i):
            morceaux.append(".*")
            i += 2
        elif texte[i] == "*":
            morceaux.append("[^/]*")
            i += 1
        elif texte[i] == "{":
            fin = texte.find("}", i)
            if fin < 0:
                return None
            morceaux.append("[^/]+")
            i = fin + 1
        else:
            morceaux.append(re.escape(texte[i]))
            i += 1
    return re.compile("^" + "".join(morceaux) + "$")


def _qualite_spring(motif: str, chemin: str) -> float | None:
    normalise = _nettoyer_chemin(motif)
    if not normalise:
        return None
    if not any(caractere in normalise for caractere in "*{"):
        return 1.0 if normalise == chemin else None
    regex = _regex_spring(normalise)
    if regex is None or not regex.match(chemin):
        return None
    return 0.9 if "{" in normalise else 0.95


def _groupes_par_motif(candidats: Iterable[tuple[str, float]], motif: str,
                       qualite) -> float | None:
    meilleure = None
    for chemin, facteur in candidats:
        valeur = qualite(motif, chemin)
        if valeur is None:
            continue
        pondere = valeur * facteur
        if meilleure is None or pondere > meilleure:
            meilleure = pondere
    return meilleure


def _cible_jsp(observation: Observation) -> str:
    attributes = observation.attributes
    if observation.kind.casefold() == "jsp_form":
        return _nettoyer_cible(_valeur(attributes, "action", "target"))
    return _nettoyer_cible(_valeur(
        attributes, "target", "page", "file", "url", "value", "href", "action"))


def _nom_servlet(observation: Observation) -> str:
    return _valeur(observation.attributes, "servlet_name", "name") or observation.symbol


def _motifs_servlet(observation: Observation) -> list[str]:
    motifs = _valeurs(observation.attributes, "url_patterns", "url_pattern", "patterns", "pattern")
    if not motifs and observation.symbol.startswith("/"):
        motifs = [observation.symbol]
    return _uniques_textes(motifs)


def _methode_formulaire(observation: Observation) -> str:
    valeur = _valeur(observation.attributes, "method", "http_method", "verb")
    if not valeur or "${" in valeur or "<%" in valeur:
        return ""
    valeur = valeur.upper().rsplit(".", 1)[-1]
    return valeur if valeur in _METHODES_HTTP else ""


def _methodes_route(observation: Observation) -> set[str]:
    valeurs = _valeurs(observation.attributes, "methods", "method", "http_methods",
                       "http_method", "verbs", "verb")
    methodes: set[str] = set()
    for valeur in valeurs:
        for mot in re.split(r"[,;|/\s]+", valeur):
            mot = mot.upper().rsplit(".", 1)[-1]
            if mot in _METHODES_HTTP:
                methodes.add(mot)
    return methodes


def _chemins_route(observation: Observation) -> list[str]:
    valeurs = _valeurs(observation.attributes, "paths", "path", "value", "url", "route", "mapping")
    if not valeurs and observation.symbol.startswith("/"):
        valeurs = [observation.symbol]
    prefixe = _nettoyer_cible(_valeur(
        observation.attributes, "prefix", "base_path", "class_path", "class_mapping"))
    resultat: list[str] = []
    for valeur in valeurs:
        chemin = _nettoyer_cible(valeur)
        if not chemin:
            continue
        if prefixe and not (chemin == prefixe or chemin.startswith(prefixe.rstrip("/") + "/")):
            chemin = posixpath.join(prefixe, chemin.lstrip("/"))
        if not chemin.startswith("/"):
            chemin = "/" + chemin
        normalise = _nettoyer_chemin(chemin)
        if normalise:
            resultat.append(normalise)
    return _uniques_textes(resultat)


class _Vue:
    def __init__(self, observations: Iterable[Observation]):
        self.observations = list(observations)
        self.par_kind: dict[str, list[Observation]] = {}
        for observation in self.observations:
            self.par_kind.setdefault(observation.kind.casefold(), []).append(observation)
        self._types_java: list[dict] | None = None
        self._entites: list[dict] | None = None

    def de(self, kinds: Iterable[str]) -> list[Observation]:
        resultat: list[Observation] = []
        for kind in kinds:
            resultat.extend(self.par_kind.get(kind.casefold(), ()))
        return resultat


def _index_types_java(vue: _Vue) -> list[dict]:
    if vue._types_java is not None:
        return vue._types_java
    resultat: list[dict] = []
    for observation in vue.observations:
        kind = observation.kind.casefold()
        if kind in _KINDS_NON_TYPE_JAVA:
            continue
        est_type = kind in _KINDS_TYPE_JAVA
        if not est_type and observation.language.casefold() in {"java", "kotlin"}:
            est_type = bool(_valeur(observation.attributes, "fqn", "qualified_name", "full_name"))
        if not est_type:
            continue
        attributes = observation.attributes
        nom = _valeur(attributes, "fqn", "qualified_name", "full_name", "class_name",
                      "class", "entity", "name") or observation.symbol
        paquet = _valeur(attributes, "package", "package_name", "namespace")
        if paquet and "." not in nom and not nom.startswith(paquet + "."):
            nom = paquet + "." + nom
        fqn = _normaliser_java(nom)
        simple = _simple_java(_valeur(attributes, "simple_name", "name")) or _simple_java(fqn)
        if not fqn:
            continue
        resultat.append({"obs": observation, "fqn": fqn, "simple": simple or _simple_java(fqn)})
    vue._types_java = resultat
    return resultat


def _meilleur_type(candidates: Iterable[dict]) -> Observation | None:
    entrees = list(candidates)
    if not entrees:
        return None
    priorite = {
        "java_type": 0, "java_class": 1, "java_interface": 2, "java_enum": 3,
        "java_record": 4, "class": 5, "type": 6,
    }
    entrees.sort(key=lambda item: (
        priorite.get(item["obs"].kind.casefold(), 9),
        item["obs"].file, item["obs"].start, item["obs"].symbol,
    ))
    return entrees[0]["obs"]


def _resoudre_type(vue: _Vue, nom: str) -> tuple[Observation, str] | None:
    reference = _normaliser_java(nom)
    if not reference:
        return None
    types = _index_types_java(vue)
    exacts = [item for item in types if item["fqn"].casefold() == reference.casefold()]
    if exacts:
        return _meilleur_type(exacts), "fqn"
    simple = _simple_java(reference)
    if not simple:
        return None
    simples = [item for item in types if item["simple"].casefold() == simple.casefold()]
    cibles = _uniques(item["obs"] for item in simples)
    if len(cibles) == 1:
        return cibles[0], "simple"
    return None


def _servlets_par_nom(vue: _Vue) -> dict[str, list[Observation]]:
    index: dict[str, list[Observation]] = {}
    for servlet in vue.de({"servlet"}):
        nom = _nom_servlet(servlet)
        if nom:
            index.setdefault(nom.casefold(), []).append(servlet)
    return index


def _liens_jsp_servlet_mapping(vue: _Vue) -> list[Link]:
    pages = vue.de(_KINDS_JSP)
    mappings = vue.de({"servlet_mapping"})
    if not pages or not mappings:
        return []
    servlets = _servlets_par_nom(vue)
    liens: list[Link] = []
    for page in pages:
        cible = _cible_jsp(page)
        candidats = _chemins_candidats(cible, page.file)
        if not candidats:
            continue
        correspondances: dict[tuple, list[tuple[float, str, Observation]]] = {}
        for mapping in mappings:
            nom = _nom_servlet(mapping)
            cle = (nom.casefold() or mapping.symbol.casefold(), mapping.file)
            for motif in _motifs_servlet(mapping):
                qualite = _groupes_par_motif(candidats, motif, _qualite_servlet)
                if qualite is not None:
                    correspondances.setdefault(cle, []).append((qualite, motif, mapping))
        if len(correspondances) != 1:
            continue
        trouvailles = next(iter(correspondances.values()))
        trouvailles.sort(key=lambda item: (-item[0], -len(item[1]), item[2].file,
                                           item[2].start, item[2].symbol))
        qualite, motif, mapping = trouvailles[0]
        attributes = {
            "url_pattern": motif,
            "url_patterns": sorted({item[1] for item in trouvailles}),
            "servlet_name": _nom_servlet(mapping) or mapping.symbol,
            "cible": cible,
        }
        if page.kind.casefold() == "jsp_form":
            attributes["http_method"] = _methode_formulaire(page)
        via: list[Observation] = []
        servlet = _uniques(servlets.get(_nom_servlet(mapping).casefold(), ()))
        if len(servlet) == 1:
            attributes["servlet_class"] = _valeur(
                servlet[0].attributes, "class", "servlet_class", "java_class")
            via.append(servlet[0])
        liens.append(_lien("jsp_to_servlet_mapping", page, mapping, attributes,
                           confidence=qualite, status="linked", via=via))
    return liens


def _liens_servlet_mapping_servlet(vue: _Vue) -> list[Link]:
    mappings = vue.de({"servlet_mapping"})
    servlets = vue.de({"servlet"})
    if not mappings or not servlets:
        return []
    index: dict[str, list[Observation]] = {}
    for servlet in servlets:
        nom = _nom_servlet(servlet)
        if nom:
            index.setdefault(nom.casefold(), []).append(servlet)
    liens: list[Link] = []
    for mapping in mappings:
        nom = _nom_servlet(mapping)
        if not nom:
            continue
        cibles = _uniques(index.get(nom.casefold(), ()))
        if len(cibles) != 1:
            continue
        liens.append(_lien(
            "servlet_mapping_to_servlet", mapping, cibles[0],
            {"servlet_name": nom, "url_patterns": _motifs_servlet(mapping)},
            confidence=1.0,
        ))
    return liens


def _liens_servlet_java_type(vue: _Vue) -> list[Link]:
    liens: list[Link] = []
    for servlet in vue.de({"servlet"}):
        classe = _valeur(servlet.attributes, "class", "servlet_class", "java_class")
        if not classe:
            continue
        resultat = _resoudre_type(vue, classe)
        if resultat is None:
            continue
        cible, correspondance = resultat
        liens.append(_lien(
            "servlet_to_java_type", servlet, cible,
            {"java_class": classe, "match": correspondance}, confidence=1.0,
        ))
    return liens


def _liens_jsp_spring_route(vue: _Vue) -> list[Link]:
    formulaires = [observation for observation in vue.de(_KINDS_JSP)
                   if observation.kind.casefold() == "jsp_form"]
    routes = vue.de(_KINDS_ROUTE)
    if not formulaires or not routes:
        return []
    liens: list[Link] = []
    for formulaire in formulaires:
        cible = _cible_jsp(formulaire)
        candidats = _chemins_candidats(cible, formulaire.file)
        if not candidats:
            continue
        methode = _methode_formulaire(formulaire)
        correspondances: dict[tuple, list[tuple[float, str, Observation, set[str]]]] = {}
        for route in routes:
            methodes = _methodes_route(route)
            if methode and methodes and methode not in methodes:
                continue
            for motif in _chemins_route(route):
                qualite = _groupes_par_motif(candidats, motif, _qualite_spring)
                if qualite is None:
                    continue
                cle = (route.file, route.symbol)
                correspondances.setdefault(cle, []).append((qualite, motif, route, methodes))
        if len(correspondances) != 1:
            continue
        trouvailles = next(iter(correspondances.values()))
        trouvailles.sort(key=lambda item: (-item[0], -len(item[1]), item[2].file,
                                           item[2].start, item[2].symbol))
        qualite, motif, route, methodes = trouvailles[0]
        verifiee = bool(methode and methodes and methode in methodes)
        attributes = {
            "path": motif,
            "paths": sorted({item[1] for item in trouvailles}),
            "http_method": methode,
            "method_verified": verifiee,
            "route_methods": sorted(methodes),
        }
        liens.append(_lien(
            "jsp_to_spring_route", formulaire, route, attributes,
            confidence=qualite * (1.0 if verifiee else 0.9),
            status="linked" if verifiee else "inferred",
            target_symbol=route.symbol or motif,
        ))
    return liens


def _liens_spring_java_type(vue: _Vue) -> list[Link]:
    routes = vue.de(_KINDS_ROUTE)
    if not routes:
        return []
    liens: list[Link] = []
    for route in routes:
        classe = _valeur(route.attributes, "controller", "controller_class", "java_class",
                         "class", "handler")
        if "#" in classe:
            classe = classe.split("#", 1)[0]
        statut = "linked"
        if not classe:
            types_fichier = _uniques(
                item["obs"] for item in _index_types_java(vue) if item["obs"].file == route.file)
            if len(types_fichier) != 1:
                continue
            classe = types_fichier[0].symbol
            statut = "inferred"
        resultat = _resoudre_type(vue, classe)
        if resultat is None:
            continue
        cible, correspondance = resultat
        liens.append(_lien(
            "spring_controller_to_java_type", route, cible,
            {"controller": classe, "match": correspondance},
            confidence=1.0 if statut == "linked" else 0.8, status=statut,
        ))
    return liens


def _role_java(observation: Observation) -> str:
    kind = observation.kind.casefold()
    if "controller" in kind:
        return "controller"
    if "service" in kind:
        return "service"
    if "repository" in kind or kind.endswith("_dao"):
        return "repository"
    valeurs = _valeurs(observation.attributes, "stereotype", "stereotypes", "role",
                       "roles", "annotations", "annotation")
    for valeur in valeurs:
        texte = valeur.casefold()
        if "controller" in texte or "endpoint" in texte or "resource" in texte:
            return "controller"
        if "service" in texte:
            return "service"
        if "repository" in texte or "dao" in texte:
            return "repository"
    return ""


_TABLE_ANNOTATION = re.compile(
    r"@?Table\s*\([^)]*?\bname\s*=\s*[\"']([^\"']+)[\"']", re.I)


def _table_annotation(attributes: Mapping) -> str:
    for valeur in _valeurs(attributes, "annotations", "annotation", "stereotypes", "stereotype"):
        trouve = _TABLE_ANNOTATION.search(valeur)
        if trouve:
            return trouve.group(1)
    return ""


def _entites_jpa(vue: _Vue) -> list[dict]:
    if vue._entites is not None:
        return vue._entites
    resultat: list[dict] = []
    for observation in vue.observations:
        kind = observation.kind.casefold()
        attributes = observation.attributes
        explicite = kind in {"java_entity", "jpa_entity", "entity", "jpa_table", "java_table"}
        est_entite = kind in _KINDS_ENTITE_JPA
        if not est_entite and kind in _KINDS_TYPE_JAVA:
            stereotypes = _valeurs(attributes, "stereotype", "stereotypes", "role",
                                   "annotations", "annotation")
            est_entite = (
                any("entity" in valeur.casefold() for valeur in stereotypes)
                or bool(_valeur(attributes, "table", "table_name", "nom_table"))
                or bool(_table_annotation(attributes))
                or bool(_valeur(attributes, "is_entity", "jpa", "entity_type"))
            )
        if not est_entite:
            continue
        nom = _valeur(attributes, "fqn", "qualified_name", "full_name", "class",
                      "class_name", "entity", "entity_class")
        if not nom and kind != "jpa_table":
            nom = observation.symbol
        paquet = _valeur(attributes, "package", "package_name", "namespace")
        if nom and paquet and "." not in nom and not nom.startswith(paquet + "."):
            nom = paquet + "." + nom
        fqn = _normaliser_java(nom or observation.symbol)
        simple = _simple_java(_valeur(attributes, "simple_name", "name")) or _simple_java(fqn)
        table = _valeur(attributes, "table", "table_name", "nom_table")
        if not table:
            table = _table_annotation(attributes)
        table_explicite = bool(table)
        if not table:
            table = simple
        table_norm = _normaliser_table(table)
        if not (fqn or table_norm):
            continue
        resultat.append({
            "obs": observation,
            "fqn": fqn or simple or table_norm,
            "simple": simple or _simple_java(fqn),
            "table": table_norm,
            "table_explicite": table_explicite,
            "explicite": explicite,
        })
    vue._entites = resultat
    return resultat


def _meilleure_entite(entrees: Iterable[dict]) -> dict | None:
    candidates = list(entrees)
    if not candidates:
        return None
    candidates.sort(key=lambda item: (
        not item["table_explicite"], not item["explicite"],
        item["obs"].file, item["obs"].start, item["obs"].symbol,
    ))
    return candidates[0]


def _resoudre_entite(vue: _Vue, reference: str) -> dict | None:
    nom = _reference_type(reference)
    if not nom or "*" in nom:
        return None
    entites = _entites_jpa(vue)
    exactes = [item for item in entites if item["fqn"].casefold() == nom.casefold()]
    if exactes:
        return _meilleure_entite(exactes)
    simple = _simple_java(nom)
    if not simple:
        return None
    simples = [item for item in entites if item["simple"].casefold() == simple.casefold()]
    cibles = _uniques(item["obs"] for item in simples)
    if len(cibles) == 1:
        return _meilleure_entite(item for item in simples if item["obs"] is cibles[0])
    return None


def _nom_import(attributes: Mapping, symbole: str) -> str:
    nom = _valeur(attributes, "target", "import", "fqn", "name") or symbole
    paquet = _valeur(attributes, "package", "package_name", "namespace")
    if paquet and nom and "." not in nom and not nom.startswith(paquet + "."):
        nom = paquet + "." + nom
    return nom


def _reference_type(valeur: str) -> str:
    texte = _IMPORT_JAVA.sub("", _texte(valeur)).strip().rstrip(";").strip()
    if texte.startswith("static "):
        texte = texte[7:].strip()
    if texte.endswith(".*"):
        return ""
    return _normaliser_java(texte)


def _types_dans(expression: str) -> list[str]:
    resultat = []
    for jeton in _IDENT_JAVA.findall(_texte(expression)):
        reference = _reference_type(jeton)
        if reference:
            resultat.append(reference)
    return _uniques_textes(resultat)


def _classe_source(observation: Observation) -> str:
    return _valeur(observation.attributes, "fqn", "qualified_name", "class",
                   "controller", "controller_class", "java_class", "name") or observation.symbol


def _meme_type(gauche: str, droite: str) -> bool:
    if not gauche or not droite:
        return False
    gauche, droite = _normaliser_java(gauche), _normaliser_java(droite)
    return (gauche.casefold() == droite.casefold() or
            _simple_java(gauche).casefold() == _simple_java(droite).casefold())


def _appartient_a(observation: Observation, source: Observation, classe: str) -> bool:
    proprietaire = _valeur(observation.attributes, "owner", "owner_class",
                           "declaring_class", "declaring_type")
    if not proprietaire and _valeur(observation.attributes, "type", "field_type", "data_type"):
        proprietaire = _valeur(observation.attributes, "class")
    if observation.file == source.file:
        return not proprietaire or _meme_type(proprietaire, classe)
    return bool(proprietaire and _meme_type(proprietaire, classe))


def _references_source(vue: _Vue, source: Observation) -> list[tuple[str, str, Observation | None]]:
    classe = _classe_source(source)
    resultat: list[tuple[str, str, Observation | None]] = []
    vus: set[tuple] = set()

    def ajouter(type_nom: str, via: str, preuve: Observation | None) -> None:
        reference = _reference_type(type_nom)
        if not reference:
            return
        cle = (reference.casefold(), via, preuve.fingerprint if preuve else None)
        if cle in vus:
            return
        vus.add(cle)
        resultat.append((reference, via, preuve))

    for cle in ("imports", "import", "imported_types"):
        brut = source.attributes.get(cle)
        if brut is None:
            continue
        elements = brut if isinstance(brut, (list, tuple, set)) else (brut,)
        for item in elements:
            if isinstance(item, Mapping):
                ajouter(_nom_import(item, ""), "import", None)
            else:
                ajouter(item, "import", None)
    for cle in ("fields", "field_types"):
        brut = source.attributes.get(cle)
        if brut is None:
            continue
        elements = brut if isinstance(brut, (list, tuple, set)) else (brut,)
        for champ in elements:
            if isinstance(champ, Mapping):
                expression = _valeur(champ, "type", "field_type", "data_type", "class")
            else:
                expression = _texte(champ)
            for type_nom in _types_dans(expression):
                ajouter(type_nom, "field", None)
    for nom in _valeurs(source.attributes, "references", "reference", "entity_types", "types"):
        ajouter(nom, "reference", None)

    for observation in vue.de(_KINDS_IMPORT):
        if not _appartient_a(observation, source, classe):
            continue
        ajouter(_nom_import(observation.attributes, observation.symbol),
                "import", observation)
    for observation in vue.de(_KINDS_CHAMP):
        if not _appartient_a(observation, source, classe):
            continue
        type_nom = _valeur(observation.attributes, "type", "field_type", "data_type",
                           "class", "entity_type")
        for reference in _types_dans(type_nom):
            ajouter(reference, "field", observation)
    return resultat


def _sources_jpa(vue: _Vue) -> list[Observation]:
    resultat: dict[tuple, Observation] = {}
    for route in vue.de(_KINDS_ROUTE):
        resultat.setdefault((route.file, route.symbol), route)
    for item in _index_types_java(vue):
        observation = item["obs"]
        if _role_java(observation) in _ROLES_SOURCE_JPA:
            resultat.setdefault((observation.file, observation.symbol), observation)
    return list(resultat.values())


def _liens_java_jpa(vue: _Vue) -> list[Link]:
    sources = _sources_jpa(vue)
    if not sources:
        return []
    liens: list[Link] = []
    for source in sources:
        classes_source = _classe_source(source)
        references = _references_source(vue, source)
        if source.kind.casefold() in _KINDS_ROUTE:
            controleur = _valeur(source.attributes, "controller", "controller_class",
                                 "java_class", "class", "handler")
            if "#" in controleur:
                controleur = controleur.split("#", 1)[0]
            resolu = _resoudre_type(vue, controleur) if controleur else None
            if resolu is not None and resolu[0] is not source:
                references.extend(_references_source(vue, resolu[0]))
        par_cible: dict[tuple, dict] = {}
        for reference, via, preuve in references:
            entite = _resoudre_entite(vue, reference)
            if entite is None:
                continue
            if _meme_type(reference, entite["fqn"]) and _meme_type(classes_source, entite["fqn"]):
                continue
            cle = (entite["obs"].file, entite["obs"].symbol)
            information = par_cible.setdefault(cle, {
                "entite": entite, "vias": set(), "references": set(), "preuves": [],
            })
            information["vias"].add(via)
            information["references"].add(reference)
            if preuve is not None:
                information["preuves"].append(preuve)
        for information in par_cible.values():
            entite = information["entite"]
            attributes = {
                "entity": entite["fqn"],
                "table": entite["table"],
                "via": sorted(information["vias"]),
                "references": sorted(information["references"]),
            }
            statut = "linked"
            confiance = 1.0
            if not entite["table_explicite"]:
                attributes["table_source"] = "class_name"
                statut = "inferred"
                confiance = 0.8
            liens.append(_lien(
                "java_to_jpa_entity", source, entite["obs"], attributes,
                confidence=confiance, status=statut, via=information["preuves"],
                target_symbol=entite["fqn"] or entite["obs"].symbol,
            ))
    return liens


def _tables_sql(vue: _Vue) -> list[dict]:
    resultat = []
    for observation in vue.de({"sql_table"}):
        nom = _valeur(observation.attributes, "table", "name") or observation.symbol
        normalise = _normaliser_table(nom)
        if normalise:
            resultat.append({"obs": observation, "nom": normalise})
    return resultat


def _colonnes_sql(vue: _Vue) -> list[dict]:
    resultat = []
    for observation in vue.de({"sql_column"}):
        table = _normaliser_table(
            _valeur(observation.attributes, "table", "table_name") or
            observation.symbol.rsplit(".", 1)[0])
        colonne = _valeur(observation.attributes, "colonne", "column", "column_name", "name")
        if not colonne and "." in observation.symbol:
            colonne = observation.symbol.rsplit(".", 1)[-1]
        colonne = _normaliser_table(colonne)
        if table and colonne:
            resultat.append({"obs": observation, "table": table, "colonne": colonne})
    return resultat


def _cible_table_sql(vue: _Vue, nom: str) -> Observation | None:
    normalise = _normaliser_table(nom)
    if not normalise:
        return None
    cibles = _uniques(item["obs"] for item in _tables_sql(vue) if item["nom"] == normalise)
    return cibles[0] if len(cibles) == 1 else None


def _cible_colonne_sql(vue: _Vue, table: str, colonne: str) -> Observation | None:
    normalise_table, normalise_colonne = _normaliser_table(table), _normaliser_table(colonne)
    cibles = _uniques(
        item["obs"] for item in _colonnes_sql(vue)
        if item["table"] == normalise_table and item["colonne"] == normalise_colonne)
    return cibles[0] if len(cibles) == 1 else None


def _cle_fk(table: str, colonnes: Iterable[str], references: str,
            colonnes_referencees: Iterable[str]) -> tuple:
    return (
        _normaliser_table(table),
        tuple(sorted(_normaliser_table(colonne) for colonne in colonnes)),
        _normaliser_table(references),
        tuple(sorted(_normaliser_table(colonne) for colonne in colonnes_referencees)),
    )


def _sources_fk(vue: _Vue) -> list[dict]:
    resultat = []
    vues: set[tuple] = set()
    for observation in vue.de({"sql_fk"}):
        item = {
            "obs": observation,
            "table": _normaliser_table(_valeur(observation.attributes, "table",
                                               "table_source", "source_table")),
            "references": _normaliser_table(_valeur(observation.attributes, "references",
                                                    "referenced_table", "table_cible",
                                                    "target_table")),
            "colonnes": _valeurs(observation.attributes, "colonnes", "columns"),
            "colonnes_referencees": _valeurs(observation.attributes, "colonnes_referencees",
                                             "referenced_columns"),
        }
        vues.add(_cle_fk(item["table"], item["colonnes"], item["references"],
                         item["colonnes_referencees"]))
        resultat.append(item)
    for item in _colonnes_sql(vue):
        observation = item["obs"]
        references = _valeur(observation.attributes, "references", "referenced_table")
        if not references:
            continue
        colonnes_referencees = _valeurs(observation.attributes, "colonnes_referencees",
                                        "referenced_columns")
        cle = _cle_fk(item["table"], [item["colonne"]], references, colonnes_referencees)
        if cle in vues:
            continue
        resultat.append({
            "obs": observation,
            "table": item["table"],
            "references": _normaliser_table(references),
            "colonnes": [item["colonne"]],
            "colonnes_referencees": colonnes_referencees,
        })
    return resultat


def _liens_sql_fk(vue: _Vue) -> list[Link]:
    liens: list[Link] = []
    for source in _sources_fk(vue):
        if not source["references"]:
            continue
        table = _cible_table_sql(vue, source["references"])
        if table is None:
            continue
        attributes = {
            "table_source": source["table"],
            "table_cible": source["references"],
            "colonnes": source["colonnes"],
            "colonnes_referencees": source["colonnes_referencees"],
        }
        liens.append(_lien("sql_fk_to_table", source["obs"], table, attributes))
        for colonne in source["colonnes_referencees"]:
            cible = _cible_colonne_sql(vue, source["references"], colonne)
            if cible is None:
                continue
            details = dict(attributes)
            details["colonne_cible"] = _normaliser_table(colonne)
            liens.append(_lien("sql_fk_to_column", source["obs"], cible, details))
    return liens


def _liens_sql_jpa_table(vue: _Vue) -> list[Link]:
    entites = _entites_jpa(vue)
    if not entites:
        return []
    par_table: dict[str, list[dict]] = {}
    for entite in entites:
        if entite["table"]:
            par_table.setdefault(entite["table"], []).append(entite)
    liens: list[Link] = []
    for table_norm, candidates in sorted(par_table.items()):
        fqns = {item["fqn"].casefold() for item in candidates if item["fqn"]}
        if len(fqns) != 1:
            continue
        entite = _meilleure_entite(candidates)
        if entite is None:
            continue
        tables = _uniques(item["obs"] for item in _tables_sql(vue) if item["nom"] == table_norm)
        if len(tables) != 1:
            continue
        attributes = {
            "table": table_norm,
            "entity": entite["fqn"],
            "schema_retire": True,
        }
        statut = "linked"
        confiance = 1.0
        if not entite["table_explicite"]:
            attributes["table_source"] = "class_name"
            statut = "inferred"
            confiance = 0.8
        liens.append(_lien("sql_table_to_jpa_table", tables[0], entite["obs"], attributes,
                           confidence=confiance, status=statut,
                           target_symbol=entite["fqn"] or entite["obs"].symbol))
    return liens


def _programmes_cobol(vue: _Vue) -> dict[str, list[Observation]]:
    index: dict[str, list[Observation]] = {}
    for observation in vue.de({"cobol_program"}):
        nom = _normaliser_programme(
            _valeur(observation.attributes, "program", "program_id") or observation.symbol)
        if nom:
            index.setdefault(nom, []).append(observation)
    return index


def _cible_programme(vue: _Vue, nom: str) -> Observation | None:
    normalise = _normaliser_programme(nom)
    if not normalise:
        return None
    cibles = _uniques(_programmes_cobol(vue).get(normalise, ()))
    return cibles[0] if len(cibles) == 1 else None


def _liens_cobol_call(vue: _Vue) -> list[Link]:
    liens: list[Link] = []
    for appel in vue.de({"cobol_call"}):
        nom = _valeur(appel.attributes, "target", "program") or appel.symbol
        cible = _cible_programme(vue, nom)
        if cible is None or cible is appel:
            continue
        liens.append(_lien("cobol_call_to_program", appel, cible, {"program": nom}))
    return liens


def _fichiers_copybook(vue: _Vue) -> dict[str, list[Observation]]:
    index: dict[str, list[Observation]] = {}
    for observation in vue.observations:
        chemin = observation.file.replace("\\", "/")
        racine, extension = posixpath.splitext(chemin)
        if extension.casefold() not in {".cpy", ".copy"}:
            continue
        nom = posixpath.basename(racine).casefold()
        if nom:
            index.setdefault(nom, []).append(observation)
    return index


def _representant_copybook(observations: Iterable[Observation]) -> Observation | None:
    priorite = {
        "cobol_program": 0, "cobol_division": 1, "cobol_section": 2,
        "cobol_field": 3, "cobol_paragraph": 4,
    }
    candidates = list(observations)
    if not candidates:
        return None
    candidates.sort(key=lambda observation: (
        priorite.get(observation.kind.casefold(), 9), observation.start, observation.symbol))
    return candidates[0]


def _liens_cobol_copy(vue: _Vue) -> list[Link]:
    copies = vue.de({"cobol_copy"})
    index = _fichiers_copybook(vue)
    if not copies or not index:
        return []
    liens: list[Link] = []
    for copie in copies:
        nom = _valeur(copie.attributes, "copybook", "target") or copie.symbol
        normalise = posixpath.basename(_texte(nom).replace("\\", "/"))
        normalise = posixpath.splitext(normalise)[0].casefold() or normalise.casefold()
        if not normalise:
            continue
        fichiers: dict[str, list[Observation]] = {}
        for observation in index.get(normalise, ()):
            fichiers.setdefault(observation.file, []).append(observation)
        fichiers.pop(copie.file, None)
        if len(fichiers) > 1:
            bibliotheque = _valeur(copie.attributes, "library")
            if bibliotheque:
                filtre = _texte(bibliotheque).replace("\\", "/").strip("/").casefold()
                retenus = {fichier: observations for fichier, observations in fichiers.items()
                           if filtre in fichier.replace("\\", "/").casefold()}
                if len(retenus) == 1:
                    fichiers = retenus
        if len(fichiers) != 1:
            continue
        fichier, observations = next(iter(fichiers.items()))
        representant = _representant_copybook(observations)
        if representant is None:
            continue
        liens.append(_lien(
            "cobol_copy_to_copybook", copie, representant,
            {"copybook": nom, "file_cible": fichier, "stem": normalise},
            confidence=0.9, status="linked",
            target_symbol=_normaliser_programme(nom) or normalise.upper(),
        ))
    return liens


def _datasets_cobol(vue: _Vue) -> list[tuple[Observation, str]]:
    resultat = []
    for observation in vue.de({"cobol_file"}):
        nom = _valeur(observation.attributes, "dataset", "assign")
        if nom:
            resultat.append((observation, _normaliser_dataset(nom)))
    return resultat


def _datasets_jcl(vue: _Vue) -> list[tuple[Observation, str]]:
    trouves: dict[tuple, tuple[int, Observation, str]] = {}
    for kind, priorite in (("jcl_dataset", 0), ("jcl_dd", 1)):
        for observation in vue.de({kind}):
            nom = _valeur(observation.attributes, "dsn", "dataset") or observation.symbol
            normalise = _normaliser_dataset(nom)
            if not normalise:
                continue
            cle = (observation.file, normalise)
            courant = trouves.get(cle)
            if courant is None or priorite < courant[0]:
                trouves[cle] = (priorite, observation, normalise)
    return [(observation, normalise) for _, observation, normalise in trouves.values()]


def _liens_cobol_jcl_dataset(vue: _Vue) -> list[Link]:
    liens: list[Link] = []
    for source, nom in _datasets_cobol(vue):
        cibles = _uniques(observation for observation, dataset in _datasets_jcl(vue)
                          if dataset == nom)
        if len(cibles) != 1:
            continue
        liens.append(_lien(
            "cobol_file_to_jcl_dataset", source, cibles[0],
            {"dataset": nom, "select": _valeur(source.attributes, "select")},
            target_symbol=nom,
        ))
    return liens


def _liens_jcl_cobol_dataset(vue: _Vue) -> list[Link]:
    liens: list[Link] = []
    for source, nom in _datasets_jcl(vue):
        cibles = _uniques(observation for observation, dataset in _datasets_cobol(vue)
                          if dataset == nom)
        if len(cibles) != 1:
            continue
        liens.append(_lien(
            "jcl_dataset_to_cobol_file", source, cibles[0],
            {"dataset": nom, "dd": _valeur(source.attributes, "dd")},
        ))
    return liens


def _liens_jcl_programme_cobol(vue: _Vue) -> list[Link]:
    sources: dict[tuple, Observation] = {}
    for kind in ("jcl_program", "jcl_step"):
        for observation in vue.de({kind}):
            nom = _valeur(observation.attributes, "pgm", "program")
            if not nom and kind == "jcl_program":
                nom = observation.symbol
            if not nom:
                continue
            cle = (observation.file, observation.start, observation.end,
                   _normaliser_programme(nom))
            sources.setdefault(cle, observation)
    liens: list[Link] = []
    for programme in sources.values():
        nom = _valeur(programme.attributes, "pgm", "program") or programme.symbol
        cible = _cible_programme(vue, nom)
        if cible is None:
            continue
        liens.append(_lien(
            "jcl_program_to_cobol_program", programme, cible,
            {"pgm": _normaliser_programme(nom), "step": _valeur(programme.attributes, "step")},
        ))
    return liens


def _liens_jcl_proc(vue: _Vue) -> list[Link]:
    sources: dict[tuple, Observation] = {}
    for observation in vue.de({"jcl_proc"}):
        nom = _valeur(observation.attributes, "proc") or observation.symbol
        if _valeur(observation.attributes, "step") or _valeur(observation.attributes, "job"):
            cle = (observation.file, observation.start, observation.end, _normaliser_nom(nom))
            sources.setdefault(cle, observation)
    for observation in vue.de({"jcl_step"}):
        nom = _valeur(observation.attributes, "proc")
        if nom:
            cle = (observation.file, observation.start, observation.end, _normaliser_nom(nom))
            sources.setdefault(cle, observation)
    definitions = [observation for observation in vue.de({"jcl_proc"})
                   if not _valeur(observation.attributes, "step")
                   and not _valeur(observation.attributes, "job")]
    if not sources or not definitions:
        return []
    index: dict[str, list[Observation]] = {}
    for definition in definitions:
        nom = _normaliser_nom(_valeur(definition.attributes, "proc") or definition.symbol)
        if nom:
            index.setdefault(nom, []).append(definition)
    liens: list[Link] = []
    for source in sources.values():
        nom = _valeur(source.attributes, "proc") or source.symbol
        normalise = _normaliser_nom(nom)
        if not normalise:
            continue
        cibles = [cible for cible in _uniques(index.get(normalise, ()))
                  if cible.fingerprint != source.fingerprint]
        if len(cibles) != 1:
            continue
        liens.append(_lien(
            "jcl_proc_to_jcl_proc", source, cibles[0],
            {"proc": _texte(nom), "step": _valeur(source.attributes, "step")},
        ))
    return liens


def _cle_lien(lien: Link) -> tuple:
    return lien.fingerprint + (
        tuple(sorted((str(cle), repr(_serialisable(valeur)))
                     for cle, valeur in lien.attributes.items())),
    )


def lier(observations: Iterable[Observation]) -> list[Link]:
    """Rend les liens prouvés entre observations ; aucune cible ambiguë n'est retenue."""
    vue = _Vue(observation for observation in observations or ()
               if isinstance(observation, Observation))
    constructeurs = (
        _liens_jsp_servlet_mapping,
        _liens_servlet_mapping_servlet,
        _liens_servlet_java_type,
        _liens_jsp_spring_route,
        _liens_spring_java_type,
        _liens_java_jpa,
        _liens_sql_fk,
        _liens_sql_jpa_table,
        _liens_cobol_call,
        _liens_cobol_copy,
        _liens_cobol_jcl_dataset,
        _liens_jcl_cobol_dataset,
        _liens_jcl_programme_cobol,
        _liens_jcl_proc,
    )
    uniques: dict[tuple, Link] = {}
    for constructeur in constructeurs:
        for lien in constructeur(vue):
            uniques.setdefault(_cle_lien(lien), lien)
    return sorted(uniques.values(), key=lambda lien: (
        lien.kind, lien.source_file, lien.source_symbol,
        lien.target_file, lien.target_symbol, lien.confidence))


def rapport_liens(links: Iterable[Link]) -> dict:
    """Rapport sérialisable en JSON : compteurs, confiance, fichiers et liens détaillés."""
    valides = [lien for lien in links or () if isinstance(lien, Link)]
    valides.sort(key=lambda lien: (
        lien.kind, lien.source_file, lien.source_symbol,
        lien.target_file, lien.target_symbol, lien.confidence))
    par_kind = Counter(lien.kind for lien in valides)
    par_statut = Counter(lien.status for lien in valides)
    confiances = [lien.confidence for lien in valides]
    return {
        "total": len(valides),
        "par_kind": dict(sorted(par_kind.items())),
        "par_statut": {statut: par_statut.get(statut, 0) for statut in STATUTS_LIEN},
        "confiance": {
            "min": min(confiances) if confiances else 0.0,
            "max": max(confiances) if confiances else 0.0,
            "moyenne": (sum(confiances) / len(confiances)) if confiances else 0.0,
        },
        "fichiers": {
            "sources": sorted({lien.source_file for lien in valides}),
            "cibles": sorted({lien.target_file for lien in valides}),
        },
        "liens": [lien.as_dict() for lien in valides],
    }
