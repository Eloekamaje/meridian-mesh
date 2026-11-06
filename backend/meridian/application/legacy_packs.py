"""Packs de constats legacy : observations structurelles -> Findings -> Claims prouvables.

Le module est une application pure : il ne lit aucun fichier, n'appelle aucun service et n'importe
aucun adapter. Il travaille uniquement sur les :class:`~meridian.domain.code_index.Observation`
produites par les sidecars et sur les liens déterministes de :mod:`meridian.application.code_links`.

Un Finding ne devient ``claim`` que si son prédicat est déjà prouvable par le code
(:data:`meridian.domain.recettes.PREDICATS`), si sa preuve est localisée (fichier, lignes, locator) et
si son commit est présent. Pour les prédicats composés (ADR 0027), la ligne citée doit en plus établir
elle-même le lien : une observation de parser qui ne porte pas cette preuve laisse le constat
``candidate``. Il ne produit un Claim que si la recette du prédicat est vérifiée sur les lignes citées
et si la preuve porte citation, hash, locator et commit. Tout le reste reste ``candidate``.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace

from meridian.domain.code_index import Observation
from meridian.domain.recettes import PREDICATS, recette

__all__ = [
    "Finding", "STATUTS_FINDING", "TYPES_CLAIM", "packs", "claims_promouvables",
    "rapport_packs",
]

STATUTS_FINDING = ("candidate", "claim")
METHODES_HTTP = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE"})
TYPES_CLAIM = frozenset({
    "DEPENDENCY", "CAPABILITY", "BUSINESS_RULE", "DATA_FLOW", "OWNERSHIP", "PROCESS_STEP",
    "API_USAGE", "CHANGE", "FUNCTIONALITY", "RISK", "BEHAVIOR", "CUSTOMER_IMPACT",
    "EMPLOYEE_IMPACT",
})

_KINDS_JSP = frozenset({"jsp_form", "jsp_include", "jsp_forward"})
_KINDS_ENTITE = frozenset({"jpa_entity", "java_entity", "entity"})
_KINDS_TABLE = frozenset({"jpa_table", "java_table"})
_ANNOTATIONS_INJECTION = frozenset({
    "EJB", "Autowired", "Inject", "PersistenceContext", "PersistenceUnit",
})
_PREDICATS_PREUVE_LOCALISEE = frozenset({
    "TABLE", "STOCKE_DANS", "COMPOSANT_JEE", "INJECTE", "INTERFACE_UTILISATEUR",
})


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


def _principale(valeur) -> str:
    """Première valeur utile d'un attribut scalaire ou d'une liste."""
    if isinstance(valeur, (list, tuple, set)):
        for item in valeur:
            texte = _texte(item)
            if texte:
                return texte
        return ""
    return _texte(valeur)


@dataclass(frozen=True)
class Finding:
    """Constat localisé, candidat ou promu, avec sa provenance et sa cible éventuelle."""

    kind: str
    subject: str
    predicate: str
    object: str
    claim_type: str = ""
    confidence: float = 1.0
    source_file: str = ""
    source_symbol: str = ""
    target_file: str = ""
    target_symbol: str = ""
    evidence: dict = field(default_factory=dict)
    status: str = "candidate"
    attributes: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.status not in STATUTS_FINDING:
            raise ValueError(f"statut de constat inconnu : {self.status!r}")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confiance de constat hors bornes")
        for nom in ("kind", "subject", "predicate", "object", "claim_type",
                    "source_file", "source_symbol", "target_file", "target_symbol"):
            object.__setattr__(self, nom, _texte(getattr(self, nom)))
        object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(self, "evidence", dict(self.evidence or {}))
        object.__setattr__(self, "attributes", dict(self.attributes or {}))

    @property
    def fingerprint(self) -> tuple:
        return (self.kind, self.subject, self.predicate, self.object,
                self.source_file, self.target_file, self.target_symbol)

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "claim_type": self.claim_type,
            "confidence": self.confidence,
            "source_file": self.source_file,
            "source_symbol": self.source_symbol,
            "target_file": self.target_file,
            "target_symbol": self.target_symbol,
            "evidence": _serialisable(self.evidence),
            "status": self.status,
            "attributes": _serialisable(self.attributes),
        }


def _preuve(observation: Observation) -> dict:
    debut = max(0, int(getattr(observation, "start", 0) or 0))
    fin = max(debut, int(getattr(observation, "end", debut) or debut))
    chemin = _texte(getattr(observation, "file", ""))
    commit = _texte(getattr(observation, "commit", ""))
    localisee = bool(chemin and debut >= 1)
    locator = ""
    if localisee:
        locator = (f"git://{commit}:{chemin}#L{debut}-L{fin}" if commit
                   else f"{chemin}#L{debut}-L{fin}")
    return {
        "file": chemin,
        "start": debut,
        "end": fin,
        "commit": commit,
        "locator": locator,
        "localisee": localisee,
        "provider": _texte(getattr(observation, "provider", "")),
        "parser": _texte(getattr(observation, "parser", "")),
        "parser_version": _texte(getattr(observation, "parser_version", "")),
        "kind": _texte(getattr(observation, "kind", "")),
        "symbol": _texte(getattr(observation, "symbol", "")),
    }


def _localisee(evidence: Mapping) -> bool:
    debut = int(evidence.get("start") or 0)
    fin = int(evidence.get("end") or debut)
    return bool(_texte(evidence.get("file")) and debut >= 1 and fin >= debut
                and _texte(evidence.get("locator")))


def _statut(finding: Finding) -> str:
    """``claim`` = éligible à la recette : prédicat prouvable, preuve localisée et commit présent.

    Pour les prédicats composés, la preuve localisée doit aussi être celle qui établit le lien
    (``preuve_suffisante``) ; sinon le constat reste ``candidate`` même si le parser l'a observé.
    """
    evidence = finding.evidence or {}
    if (finding.predicate.upper() in _PREDICATS_PREUVE_LOCALISEE
            and finding.attributes.get("preuve_suffisante") is False):
        return "candidate"
    return ("claim" if (finding.predicate.upper() in PREDICATS and _localisee(evidence)
                        and bool(_texte(evidence.get("commit")))) else "candidate")


def _promouvable(finding: Finding) -> bool:
    return (finding.status == "claim"
            and _statut(finding) == "claim"
            and finding.claim_type in TYPES_CLAIM
            and bool(finding.subject and finding.object))


def _index_liens(liens: Iterable) -> tuple[dict, dict]:
    """Index avant (source -> cible) et arrière (cible -> source), sans dépendre du type Link."""
    avant: dict[tuple, list] = {}
    arriere: dict[tuple, list] = {}
    for lien in liens or ():
        champs = ("kind", "source_file", "source_symbol", "target_file", "target_symbol")
        if not all(hasattr(lien, champ) for champ in champs):
            continue
        kind = _texte(lien.kind)
        source_file = _texte(lien.source_file)
        source_symbol = _texte(lien.source_symbol)
        target_file = _texte(lien.target_file)
        target_symbol = _texte(lien.target_symbol)
        avant.setdefault((kind, source_file, source_symbol), []).append(lien)
        arriere.setdefault((kind, target_file, target_symbol), []).append(lien)
    return avant, arriere


def _unique(couples: Iterable[tuple[str, str, float]]) -> tuple[str, str, float] | None:
    cibles: dict[tuple[str, str], float] = {}
    for fichier, symbole, confiance in couples:
        if not (fichier or symbole):
            continue
        cle = (fichier, symbole)
        cibles[cle] = min(cibles.get(cle, 1.0), max(0.0, min(1.0, float(confiance))))
    if len(cibles) != 1:
        return None
    (fichier, symbole), confiance = next(iter(cibles.items()))
    return fichier, symbole, confiance


def _cible(index: tuple[dict, dict], kind: str, source_file: str,
           source_symbol: str) -> tuple[str, str, float] | None:
    avant, _ = index
    liens = avant.get((kind, source_file, source_symbol), ())
    return _unique((_texte(lien.target_file), _texte(lien.target_symbol),
                    float(getattr(lien, "confidence", 1.0))) for lien in liens)


def _source(index: tuple[dict, dict], kind: str, target_file: str,
            target_symbol: str) -> tuple[str, str, float] | None:
    _, arriere = index
    liens = arriere.get((kind, target_file, target_symbol), ())
    return _unique((_texte(lien.source_file), _texte(lien.source_symbol),
                    float(getattr(lien, "confidence", 1.0))) for lien in liens)


def _methode(attributes: Mapping) -> str:
    for cle in ("http_method", "method", "methods", "http_methods", "verbs", "verb"):
        if cle not in attributes:
            continue
        valeur = attributes[cle]
        elements = valeur if isinstance(valeur, (list, tuple, set)) else (valeur,)
        for element in elements:
            for mot in str(element).upper().replace(";", ",").replace("|", ",").split(","):
                mot = mot.strip().rsplit(".", 1)[-1]
                if mot in METHODES_HTTP:
                    return mot
    return ""


def _chemin(observation: Observation) -> str:
    chemin = _valeur(observation.attributes, "path", "paths", "value", "url", "route", "mapping")
    if not chemin and " " in observation.symbol:
        chemin = observation.symbol.split(" ", 1)[1]
    if not chemin and observation.symbol.startswith("/"):
        chemin = observation.symbol
    chemin = chemin.strip()
    if chemin and not chemin.startswith("/"):
        chemin = "/" + chemin
    return chemin


def _chemin_avec_prefixe(observation: Observation) -> str:
    chemin = _chemin(observation)
    prefixe = _valeur(observation.attributes, "prefix", "base_path", "class_path",
                      "class_mapping").strip()
    if not chemin or not prefixe or prefixe == "/":
        return chemin
    prefixe = "/" + prefixe.strip("/")
    if chemin == prefixe or chemin.startswith(prefixe + "/"):
        return chemin
    return prefixe + ("" if chemin == "/" else "/" + chemin.lstrip("/"))


def _pack_spring(observations: Iterable[Observation], index) -> list[Finding]:
    findings = []
    for observation in observations:
        if observation.kind.casefold() != "spring_route":
            continue
        attributs = observation.attributes
        if attributs.get("scope") == "type":
            continue
        methode = _methode(attributs)
        chemin = _chemin_avec_prefixe(observation)
        if not chemin:
            continue
        controleur = _valeur(attributs, "controller", "controller_class", "java_class",
                             "class", "handler")
        cible = _cible(index, "spring_controller_to_java_type",
                       observation.file, observation.symbol)
        target_file, target_symbol, confiance = observation.file, controleur, 1.0
        if cible is not None:
            target_file, target_symbol, confiance = cible
            controleur = controleur or target_symbol
        preuve = _preuve(observation)
        promouvable = bool(methode and _localisee(preuve)
                            and _texte(preuve.get("commit")))
        objet = f"{methode or 'ANY'} {chemin}"
        findings.append(Finding(
            kind="EXPOSE",
            subject=controleur or observation.file,
            predicate="EXPOSE",
            object=objet,
            claim_type="API_USAGE",
            confidence=min(float(observation.confidence), confiance),
            source_file=observation.file,
            source_symbol=observation.symbol,
            target_file=target_file,
            target_symbol=target_symbol,
            evidence=preuve,
            status="claim" if promouvable else "candidate",
            attributes={
                "annotation": _valeur(attributs, "annotation", "qualified"),
                "method": methode or "ANY",
                "path": chemin,
                "controller": controleur,
                "promouvable": promouvable,
            },
        ))
    return findings


def _pack_jsp(observations: Iterable[Observation], index) -> list[Finding]:
    findings = []
    for observation in observations:
        if observation.kind.casefold() not in _KINDS_JSP:
            continue
        attributs = observation.attributes
        cible_attribut = _valeur(attributs, "target", "action", "page", "file", "url",
                                 "value", "href")
        cible = cible_attribut or observation.symbol
        target_file, target_symbol, lien = "", "", ""
        for kind in ("jsp_to_spring_route", "jsp_to_servlet_mapping"):
            enrichissement = _cible(index, kind, observation.file, observation.symbol)
            if enrichissement is not None:
                target_file, target_symbol, _ = enrichissement
                lien = kind
                break
        details = {"observation": observation.kind, "target": cible,
                   "preuve_suffisante": bool(cible_attribut)}
        if observation.kind.casefold() == "jsp_form":
            details["http_method"] = _methode(attributs)
        if lien:
            details["lien"] = lien
        findings.append(Finding(
            kind="INTERFACE_UTILISATEUR",
            subject=observation.file,
            predicate="INTERFACE_UTILISATEUR",
            object=cible or observation.symbol,
            claim_type="FUNCTIONALITY",
            confidence=float(observation.confidence),
            source_file=observation.file,
            source_symbol=observation.symbol,
            target_file=target_file,
            target_symbol=target_symbol,
            evidence=_preuve(observation),
            status="candidate",
            attributes=details,
        ))
    return findings


def _champs(observations: Iterable[Observation]) -> dict[tuple, Observation]:
    champs: dict[tuple, Observation] = {}
    for observation in observations:
        if observation.kind.casefold() not in {"java_field", "field", "java_attribute"}:
            continue
        proprietaire = _valeur(observation.attributes, "owner", "owner_class",
                               "declaring_class", "class")
        nom = _valeur(observation.attributes, "name")
        type_champ = _valeur(observation.attributes, "type", "field_type", "data_type")
        if proprietaire and nom and type_champ:
            champs[(observation.file, proprietaire, nom)] = observation
    return champs


def _champ(champs: Mapping, fichier: str, proprietaire: str, membre: str) -> Observation | None:
    observation = champs.get((fichier, proprietaire, membre))
    if observation is not None:
        return observation
    simple = proprietaire.rsplit(".", 1)[-1]
    return next((candidat for (f, owner, nom), candidat in champs.items()
                 if f == fichier and nom == membre and owner.rsplit(".", 1)[-1] == simple), None)


def _annotations(observation: Observation) -> set[str]:
    valeurs = observation.attributes.get("annotations") or ()
    if isinstance(valeurs, str):
        valeurs = (valeurs,)
    return {str(valeur).rsplit(".", 1)[-1] for valeur in valeurs}


def _annotation_injection(observation: Observation) -> str:
    annotation = _valeur(observation.attributes, "annotation", "qualified")
    return annotation.rsplit(".", 1)[-1] if annotation else ""


def _cle_table(nom: str) -> str:
    return _texte(nom).strip().strip("\"`[]").casefold()


def _simple_table(nom: str) -> str:
    return _cle_table(nom).rsplit(".", 1)[-1]


def _preuve_table(observations: Iterable[Observation], index, entite_obs: Observation,
                  entite: str, table: str) -> Observation | None:
    """Observation `jpa_table`/`sql_table` dont la ligne déclare la table (pas l'entité)."""
    cle, simple = _cle_table(table), _simple_table(table)
    if not cle:
        return None
    for observation in observations:
        if (observation.kind.casefold() not in _KINDS_TABLE
                or observation.file != entite_obs.file):
            continue
        nom = _valeur(observation.attributes, "table", "name") or observation.symbol
        if _cle_table(nom) in {cle, simple}:
            return observation
    simple_entite = _simple_table(entite)
    for observation in observations:
        if (observation.kind.casefold() not in _KINDS_TABLE
                or observation.file != entite_obs.file):
            continue
        classe = _valeur(observation.attributes, "class", "class_name", "entity", "fqn")
        if classe and _simple_table(classe) == simple_entite:
            return observation
    for cible in (entite, entite_obs.symbol):
        source = _source(index, "sql_table_to_jpa_table", entite_obs.file, cible)
        if source is None:
            continue
        fichier, symbole, _ = source
        for observation in observations:
            if observation.kind.casefold() != "sql_table" or observation.file != fichier:
                continue
            nom = _valeur(observation.attributes, "table", "name") or observation.symbol
            if _cle_table(nom) in {cle, simple} or observation.symbol == symbole:
                return observation
    return None


def _pack_jee(observations: Iterable[Observation], index) -> list[Finding]:
    observations = list(observations)
    champs = _champs(observations)
    tables_entites = set()
    for observation in observations:
        if observation.kind.casefold() in _KINDS_ENTITE:
            entite = _valeur(observation.attributes, "fqn", "qualified_name", "class",
                             "class_name", "name") or observation.symbol
            table = (_valeur(observation.attributes, "table", "table_name", "nom_table")
                     or entite.rsplit(".", 1)[-1])
            if table:
                tables_entites.add((observation.file, _cle_table(table)))
    findings = []
    for observation in observations:
        kind = observation.kind.casefold()
        attributs = observation.attributes
        if kind in {"jee_component", "ejb", "mdb"}:
            classe = _valeur(attributs, "ejb_class", "owner", "class", "fqn",
                             "class_name") or observation.symbol
            if kind == "mdb":
                nom = _valeur(attributs, "type") or "message-driven"
                preuve = True
            else:
                stereotype = _valeur(attributs, "stereotype", "annotation", "type")
                nom = stereotype or observation.symbol
                preuve = bool(stereotype)
            findings.append(Finding(
                kind="COMPOSANT_JEE", subject=classe, predicate="COMPOSANT_JEE",
                object=nom or classe, claim_type="CAPABILITY",
                confidence=float(observation.confidence),
                source_file=observation.file, source_symbol=observation.symbol,
                target_file=observation.file, target_symbol=classe,
                evidence=_preuve(observation), status="candidate",
                attributes={"observation": observation.kind,
                            "stereotype": _valeur(attributs, "stereotype", "type"),
                            "preuve_suffisante": preuve},
            ))
        elif kind in _KINDS_ENTITE:
            entite = _valeur(attributs, "fqn", "qualified_name", "class", "class_name",
                             "name") or observation.symbol
            table = _valeur(attributs, "table", "table_name", "nom_table")
            table_source = "annotation"
            if not table:
                table = entite.rsplit(".", 1)[-1]
                table_source = "class_name"
            preuve_table = (_preuve_table(observations, index, observation, entite, table)
                            if table_source == "annotation" else None)
            cible = _source(index, "sql_table_to_jpa_table", observation.file, entite)
            if cible is None and entite != observation.symbol:
                cible = _source(index, "sql_table_to_jpa_table", observation.file,
                                observation.symbol)
            target_file, target_symbol = observation.file, table
            if cible is not None:
                target_file, target_symbol, _ = cible
            findings.append(Finding(
                kind="STOCKE_DANS", subject=entite, predicate="STOCKE_DANS",
                object=table, claim_type="DATA_FLOW",
                confidence=float(observation.confidence),
                source_file=observation.file, source_symbol=observation.symbol,
                target_file=target_file, target_symbol=target_symbol,
                evidence=(_preuve(preuve_table) if preuve_table is not None
                          else _preuve(observation)),
                status="candidate",
                attributes={"observation": observation.kind, "entity": entite,
                            "table": table, "table_source": table_source,
                            "preuve": _texte(getattr(preuve_table, "kind", "")),
                            "preuve_suffisante": preuve_table is not None},
            ))
        elif kind in _KINDS_TABLE:
            table = _valeur(attributs, "table", "name") or observation.symbol
            if not table:
                continue
            entite = _valeur(attributs, "class", "class_name", "entity", "fqn")
            findings.append(Finding(
                kind="TABLE", subject=entite or observation.file, predicate="TABLE",
                object=table, claim_type="CAPABILITY",
                confidence=float(observation.confidence),
                source_file=observation.file, source_symbol=observation.symbol,
                target_file=observation.file, target_symbol=table,
                evidence=_preuve(observation), status="candidate",
                attributes={"observation": observation.kind, "table": table,
                            "preuve_suffisante": True},
            ))
            if (observation.file, _cle_table(table)) in tables_entites:
                continue
            findings.append(Finding(
                kind="STOCKE_DANS", subject=entite or observation.file,
                predicate="STOCKE_DANS", object=table, claim_type="DATA_FLOW",
                confidence=float(observation.confidence),
                source_file=observation.file, source_symbol=observation.symbol,
                target_file=observation.file, target_symbol=table,
                evidence=_preuve(observation), status="candidate",
                attributes={"observation": observation.kind, "table": table,
                            "preuve_suffisante": True},
            ))
        elif kind == "jpa_column":
            table = _valeur(attributs, "table", "table_name")
            colonne = _valeur(attributs, "name", "column", "colonne") or observation.symbol
            entite = _valeur(attributs, "class", "owner", "fqn") or table or observation.file
            objet = f"{table}.{colonne}" if table else colonne
            findings.append(Finding(
                kind="STOCKE_DANS", subject=entite, predicate="STOCKE_DANS",
                object=objet, claim_type="DATA_FLOW",
                confidence=float(observation.confidence),
                source_file=observation.file, source_symbol=observation.symbol,
                target_file=observation.file, target_symbol=table or colonne,
                evidence=_preuve(observation), status="candidate",
                attributes={"observation": observation.kind, "table": table,
                            "column": colonne, "preuve_suffisante": False},
            ))
        elif kind in {"jee_injection", "spring_injection"}:
            annotation = _annotation_injection(observation)
            if annotation not in _ANNOTATIONS_INJECTION:
                continue
            proprietaire = (_valeur(attributs, "owner", "class", "fqn", "ejb")
                            or observation.file)
            membre = _valeur(attributs, "name", "member") or observation.symbol
            champ = _champ(champs, observation.file, proprietaire, membre)
            type_injecte = (_valeur(champ.attributes, "type", "field_type", "data_type")
                            if champ else "")
            couvert = bool(champ and champ.start <= observation.start
                           and champ.end >= observation.end)
            preuve = bool(champ and type_injecte
                          and (annotation in _annotations(champ) or couvert))
            findings.append(Finding(
                kind="INJECTE", subject=proprietaire, predicate="INJECTE",
                object=type_injecte or membre, claim_type="DEPENDENCY",
                confidence=float(observation.confidence),
                source_file=observation.file, source_symbol=observation.symbol,
                target_file=(champ.file if champ else observation.file),
                target_symbol=type_injecte or membre,
                evidence=(_preuve(champ) if champ is not None else _preuve(observation)),
                status="candidate",
                attributes={"observation": observation.kind, "member": membre,
                            "annotation": annotation,
                            "field": _texte(champ.kind if champ else ""),
                            "preuve_suffisante": preuve},
            ))
        elif kind == "ejb_ref" and _valeur(attributs, "type") == "resource-ref":
            type_injecte = _valeur(attributs, "res_type", "type_injecte")
            reference = _valeur(attributs, "name", "res_ref_name") or observation.symbol
            findings.append(Finding(
                kind="INJECTE", subject=reference or observation.file,
                predicate="INJECTE", object=type_injecte or reference,
                claim_type="DEPENDENCY",
                confidence=float(observation.confidence),
                source_file=observation.file, source_symbol=observation.symbol,
                target_file=observation.file, target_symbol=type_injecte or reference,
                evidence=_preuve(observation), status="candidate",
                attributes={"observation": observation.kind, "reference": reference,
                            "preuve_suffisante": bool(type_injecte)},
            ))
    return findings


def _programmes_cobol(observations: Iterable[Observation]) -> dict[str, list[Observation]]:
    programmes: dict[str, list[Observation]] = {}
    for observation in observations:
        if observation.kind.casefold() != "cobol_program":
            continue
        programmes.setdefault(observation.file, []).append(observation)
    for liste in programmes.values():
        liste.sort(key=lambda item: (item.start, item.end, item.symbol))
    return programmes


def _proprietaire_cobol(observation: Observation,
                        programmes: Mapping[str, list[Observation]]) -> str:
    precedents = [programme for programme in programmes.get(observation.file, ())
                  if programme.start <= observation.start]
    if not precedents:
        return observation.file
    programme = precedents[-1]
    return _valeur(programme.attributes, "program", "program_id") or programme.symbol


def _sujet_jcl(observation: Observation) -> str:
    job = _valeur(observation.attributes, "job")
    etape = _valeur(observation.attributes, "step")
    if job and etape:
        return f"{job}/{etape}"
    return etape or job or observation.file


def _pack_semantique(observations: Iterable[Observation], index) -> list[Finding]:
    """Appels issus des AST ABAP/RPG/PL/I, promouvables seulement sur la ligne d'appel."""
    findings = []
    for observation in observations:
        if observation.kind.casefold() not in {"abap_call", "rpg_call", "pli_call"}:
            continue
        cible = _valeur(observation.attributes, "target", "program", "member") or observation.symbol
        if not cible:
            continue
        sujet = (_valeur(observation.attributes, "owner", "class", "program", "proc")
                 or observation.file)
        findings.append(Finding(
            kind="APPELLE", subject=sujet, predicate="APPELLE", object=cible,
            claim_type="DEPENDENCY", confidence=float(observation.confidence),
            source_file=observation.file, source_symbol=observation.symbol,
            target_file=observation.file, target_symbol=cible,
            evidence=_preuve(observation), status="candidate",
            attributes={"observation": observation.kind,
                        "parser": observation.parser,
                        "target": cible},
        ))
    return findings


def _pack_cobol_jcl(observations: Iterable[Observation], index) -> list[Finding]:
    observations = list(observations)
    programmes = _programmes_cobol(observations)
    findings = []
    for observation in observations:
        kind = observation.kind.casefold()
        attributs = observation.attributes
        if kind == "cobol_call":
            cible = _valeur(attributs, "target", "program") or observation.symbol
            enrichissement = _cible(index, "cobol_call_to_program",
                                    observation.file, observation.symbol)
            target_file = observation.file
            target_symbol = cible
            if enrichissement is not None:
                target_file, target_symbol, _ = enrichissement
            findings.append(Finding(
                kind="APPELLE",
                subject=_proprietaire_cobol(observation, programmes),
                predicate="APPELLE", object=cible, claim_type="DEPENDENCY",
                confidence=float(observation.confidence),
                source_file=observation.file, source_symbol=observation.symbol,
                target_file=target_file, target_symbol=target_symbol,
                evidence=_preuve(observation), status="candidate",
                attributes={"observation": observation.kind},
            ))
        elif kind == "cobol_copy":
            cible = _valeur(attributs, "copybook", "target") or observation.symbol
            enrichissement = _cible(index, "cobol_copy_to_copybook",
                                    observation.file, observation.symbol)
            target_file = observation.file
            target_symbol = cible
            if enrichissement is not None:
                target_file, target_symbol, _ = enrichissement
            findings.append(Finding(
                kind="COPIE",
                subject=_proprietaire_cobol(observation, programmes),
                predicate="COPIE", object=cible, claim_type="DEPENDENCY",
                confidence=float(observation.confidence),
                source_file=observation.file, source_symbol=observation.symbol,
                target_file=target_file, target_symbol=target_symbol,
                evidence=_preuve(observation), status="candidate",
                attributes={"observation": observation.kind},
            ))
        elif kind == "cobol_program":
            programme = _valeur(attributs, "program", "program_id") or observation.symbol
            findings.append(Finding(
                kind="EXECUTE", subject=observation.file, predicate="EXECUTE",
                object=programme, claim_type="PROCESS_STEP",
                confidence=float(observation.confidence),
                source_file=observation.file, source_symbol=observation.symbol,
                target_file=observation.file, target_symbol=programme,
                evidence=_preuve(observation), status="candidate",
                attributes={"observation": observation.kind, "role": "program_id"},
            ))
        elif kind == "cobol_file" and _valeur(attributs, "dataset", "assign"):
            dataset = _valeur(attributs, "dataset", "assign")
            enrichissement = _cible(index, "cobol_file_to_jcl_dataset",
                                    observation.file, observation.symbol)
            target_file = observation.file
            target_symbol = dataset
            if enrichissement is not None:
                target_file, target_symbol, _ = enrichissement
            findings.append(Finding(
                kind="LIT_DATASET",
                subject=_proprietaire_cobol(observation, programmes),
                predicate="LIT_DATASET", object=dataset, claim_type="DATA_FLOW",
                confidence=float(observation.confidence),
                source_file=observation.file, source_symbol=observation.symbol,
                target_file=target_file, target_symbol=target_symbol,
                evidence=_preuve(observation), status="candidate",
                attributes={"observation": observation.kind,
                            "select": _valeur(attributs, "select")},
            ))
        elif kind == "jcl_program":
            programme = _valeur(attributs, "pgm", "program") or observation.symbol
            enrichissement = _cible(index, "jcl_program_to_cobol_program",
                                    observation.file, observation.symbol)
            target_file = observation.file
            target_symbol = programme
            if enrichissement is not None:
                target_file, target_symbol, _ = enrichissement
            findings.append(Finding(
                kind="EXECUTE", subject=_sujet_jcl(observation), predicate="EXECUTE",
                object=programme, claim_type="PROCESS_STEP",
                confidence=float(observation.confidence),
                source_file=observation.file, source_symbol=observation.symbol,
                target_file=target_file, target_symbol=target_symbol,
                evidence=_preuve(observation), status="candidate",
                attributes={"observation": observation.kind,
                            "job": _valeur(attributs, "job"),
                            "step": _valeur(attributs, "step")},
            ))
        elif kind == "jcl_proc":
            proc = _valeur(attributs, "proc") or observation.symbol
            enrichissement = _cible(index, "jcl_proc_to_jcl_proc",
                                    observation.file, observation.symbol)
            target_file = observation.file
            target_symbol = proc
            if enrichissement is not None:
                target_file, target_symbol, _ = enrichissement
            role = "definition" if not (
                _valeur(attributs, "step") or _valeur(attributs, "job")) else "execution"
            findings.append(Finding(
                kind="EXECUTE", subject=_sujet_jcl(observation), predicate="EXECUTE",
                object=proc, claim_type="PROCESS_STEP",
                confidence=float(observation.confidence),
                source_file=observation.file, source_symbol=observation.symbol,
                target_file=target_file, target_symbol=target_symbol,
                evidence=_preuve(observation), status="candidate",
                attributes={"observation": observation.kind, "role": role},
            ))
        elif kind == "jcl_dataset":
            dataset = _valeur(attributs, "dsn", "dataset") or observation.symbol
            enrichissement = _cible(index, "jcl_dataset_to_cobol_file",
                                    observation.file, observation.symbol)
            target_file = observation.file
            target_symbol = dataset
            if enrichissement is not None:
                target_file, target_symbol, _ = enrichissement
            findings.append(Finding(
                kind="LIT_DATASET", subject=_sujet_jcl(observation),
                predicate="LIT_DATASET", object=dataset, claim_type="DATA_FLOW",
                confidence=float(observation.confidence),
                source_file=observation.file, source_symbol=observation.symbol,
                target_file=target_file, target_symbol=target_symbol,
                evidence=_preuve(observation), status="candidate",
                attributes={"observation": observation.kind,
                            "dd": _valeur(attributs, "dd")},
            ))
    return findings


def _pack_sql(observations: Iterable[Observation], index) -> list[Finding]:
    findings = []
    for observation in observations:
        kind = observation.kind.casefold()
        attributs = observation.attributes
        if kind == "sql_table":
            table = _valeur(attributs, "table", "name") or observation.symbol
            if not table:
                continue
            enrichissement = _cible(index, "sql_table_to_jpa_table",
                                    observation.file, observation.symbol)
            target_file = observation.file
            target_symbol = table
            if enrichissement is not None:
                target_file, target_symbol, _ = enrichissement
            findings.append(Finding(
                kind="TABLE", subject=observation.file, predicate="TABLE",
                object=table, claim_type="CAPABILITY",
                confidence=float(observation.confidence),
                source_file=observation.file, source_symbol=observation.symbol,
                target_file=target_file, target_symbol=target_symbol,
                evidence=_preuve(observation), status="candidate",
                attributes={"schema": _valeur(attributs, "schema"),
                            "columns": _serialisable(attributs.get("colonnes", [])),
                            "preuve_suffisante": True},
            ))
        elif kind == "sql_fk" or (kind == "sql_column" and attributs.get("references")):
            table = _valeur(attributs, "table", "table_source", "source_table")
            reference = _valeur(attributs, "references", "referenced_table",
                                "table_cible", "target_table")
            if not reference:
                continue
            enrichissement = _cible(index, "sql_fk_to_table",
                                    observation.file, observation.symbol)
            target_file = observation.file
            target_symbol = reference
            if enrichissement is not None:
                target_file, target_symbol, _ = enrichissement
            findings.append(Finding(
                kind="REFERENCE", subject=table or observation.file,
                predicate="REFERENCE", object=reference, claim_type="DATA_FLOW",
                confidence=float(observation.confidence),
                source_file=observation.file, source_symbol=observation.symbol,
                target_file=target_file, target_symbol=target_symbol,
                evidence=_preuve(observation), status="candidate",
                attributes={"table": table,
                            "columns": _serialisable(
                                attributs.get("colonnes", attributs.get("column", []))),
                            "referenced_columns": _serialisable(
                                attributs.get("colonnes_referencees", []))},
            ))
    return findings


def packs(observations: Iterable[Observation], liens: Iterable = ()) -> list[Finding]:
    """Constats des packs legacy, dédupliqués et triés.

    ``claim`` vaut pour tout constat dont le prédicat est prouvable, la preuve localisée et le commit
    présent — la recette est ensuite rejouée par :func:`claims_promouvables` sur les lignes citées.
    """
    observations = [observation for observation in observations or ()
                    if isinstance(observation, Observation)]
    index = _index_liens(liens)
    trouves: list[Finding] = []
    for constructeur in (_pack_spring, _pack_jsp, _pack_jee, _pack_cobol_jcl,
                         _pack_semantique, _pack_sql):
        trouves.extend(constructeur(observations, index))
    uniques: dict[tuple, Finding] = {}
    for finding in trouves:
        statut = _statut(finding)
        if finding.status != statut:
            finding = replace(finding, status=statut)
        precedent = uniques.get(finding.fingerprint)
        if precedent is None:
            uniques[finding.fingerprint] = finding
        elif finding.status == "claim" and precedent.status == "candidate":
            uniques[finding.fingerprint] = finding
        elif (finding.status == precedent.status
              and finding.confidence > precedent.confidence):
            uniques[finding.fingerprint] = finding
    return sorted(uniques.values(), key=lambda finding: (
        finding.kind, finding.source_file, finding.source_symbol,
        finding.subject, finding.predicate, finding.object, finding.target_file,
        finding.target_symbol,
    ))


def _lignes_preuve(finding: Finding,
                   lire: Callable[[str], list[str] | None] | None) -> tuple:
    """Lignes [start, end] lues par ``lire`` (ou déjà citées), leur citation et leur emplacement."""
    evidence = finding.evidence or {}
    debut = int(evidence.get("start") or 0)
    fin = int(evidence.get("end") or debut)
    chemin = _texte(evidence.get("file")) or finding.source_file
    citation_brute = str(evidence.get("citation") or "")
    citation = _texte(citation_brute)
    if lire is not None:
        if not (chemin and debut >= 1 and fin >= debut):
            return None, citation, debut, fin, chemin
        try:
            lignes = lire(chemin)
        except (OSError, ValueError):
            lignes = None
        if lignes is None or fin > len(lignes):
            return None, citation, debut, fin, chemin
        citees = [str(ligne) for ligne in lignes[debut - 1:fin]]
        return citees, "\n".join(citees), debut, fin, chemin
    return (citation_brute.splitlines() if citation_brute.strip() else None), citation, debut, fin, chemin


def _preuve_claim(finding: Finding, citation: str, debut: int, fin: int, chemin: str) -> dict:
    evidence = finding.evidence or {}
    return {
        "type": "CODE",
        "locator": _texte(evidence.get("locator")),
        "chemin": chemin,
        "sha": _texte(evidence.get("commit")),
        "ligne_debut": debut,
        "ligne_fin": fin,
        "citation": citation,
        "hash": _texte(evidence.get("hash")) or (
            hashlib.sha256(citation.encode("utf-8")).hexdigest() if citation else ""),
    }


def claims_promouvables(findings: Iterable[Finding],
                        lire: Callable[[str], list[str] | None] | None = None) -> list[dict]:
    """Claims au format de ``depot.enregistrer`` : seuls les Findings ``claim`` prouvés passent.

    La recette du prédicat est rejouée sur les lignes ``[start, end]`` lues par ``lire`` ; si elle ne
    rend pas ``verifie``, aucun Claim n'est produit. Sans ``lire``, seule une citation déjà présente
    peut être vérifiée. Une preuve sans citation, hash, locator et commit n'entre jamais dans un Claim.
    """
    claims: dict[tuple, dict] = {}
    for finding in findings or ():
        if not isinstance(finding, Finding) or not _promouvable(finding):
            continue
        lignes, citation, debut, fin, chemin = _lignes_preuve(finding, lire)
        if recette(finding.predicate, finding.object, lignes or []) != "verifie":
            continue
        preuve = _preuve_claim(finding, citation, debut, fin, chemin)
        if not (preuve["citation"] and preuve["hash"] and preuve["locator"] and preuve["sha"]):
            continue
        cle = (finding.subject, finding.predicate, finding.object, finding.claim_type)
        claim = claims.setdefault(cle, {
            "sujet": finding.subject,
            "predicat": finding.predicate,
            "objet": finding.object,
            "type": finding.claim_type,
            "confiance": finding.confidence,
            "preuves": [],
        })
        claim["confiance"] = min(claim["confiance"], finding.confidence)
        if preuve["locator"] not in {item["locator"] for item in claim["preuves"]}:
            claim["preuves"].append(preuve)
    return sorted(claims.values(), key=lambda claim: (
        claim["predicat"], claim["objet"], claim["sujet"], claim["type"]))


def rapport_packs(findings: Iterable[Finding]) -> dict:
    """Rapport sérialisable en JSON : compteurs, confiance, fichiers et constats détaillés."""
    valides = [finding for finding in findings or () if isinstance(finding, Finding)]
    valides.sort(key=lambda finding: (
        finding.kind, finding.source_file, finding.source_symbol,
        finding.subject, finding.predicate, finding.object, finding.target_file,
        finding.target_symbol,
    ))
    par_statut = Counter(finding.status for finding in valides)
    par_kind = Counter(finding.kind for finding in valides)
    par_predicat = Counter(finding.predicate for finding in valides)
    par_type = Counter(finding.claim_type for finding in valides if finding.claim_type)
    confiances = [finding.confidence for finding in valides]
    return {
        "total": len(valides),
        "par_statut": {statut: par_statut.get(statut, 0) for statut in STATUTS_FINDING},
        "par_kind": dict(sorted(par_kind.items())),
        "par_predicat": dict(sorted(par_predicat.items())),
        "par_type": dict(sorted(par_type.items())),
        "promouvables": sum(1 for finding in valides if _promouvable(finding)),
        "confiance": {
            "min": min(confiances) if confiances else 0.0,
            "max": max(confiances) if confiances else 0.0,
            "moyenne": (sum(confiances) / len(confiances)) if confiances else 0.0,
        },
        "fichiers": {
            "sources": sorted({finding.source_file for finding in valides if finding.source_file}),
            "cibles": sorted({finding.target_file for finding in valides if finding.target_file}),
        },
        "findings": [finding.as_dict() for finding in valides],
    }
