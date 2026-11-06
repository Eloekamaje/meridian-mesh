"""Sidecar Java source : déclarations, annotations Spring/JEE/JPA, sans compilation."""
from __future__ import annotations

import os
import re
from collections.abc import Sequence
from pathlib import Path

from meridian.domain.code_index import CouvertureFichier, Observation

__all__ = ["JavaSourceSidecar", "extraire"]

PROVIDER = "java"
PARSER = "java-structural"
PARSER_VERSION = "1"
LANGAGE = "java"
EXTENSION = ".java"
EXCLUSIONS = frozenset({".git", "target", "build", "node_modules"})

_IDENT = r"[A-Za-z_$][\w$]*"
_NOM_ANNOTATION = rf"{_IDENT}(?:\s*\.\s*{_IDENT})*"
_ARGUMENTS_ANNOTATION = r"\((?:[^()]|\([^()]*\))*\)"
_ANNOTATION = rf"@{_NOM_ANNOTATION}(?:\s*{_ARGUMENTS_ANNOTATION})?"
_MOT_CLE_MODIFICATEUR = (
    r"(?:public|protected|private|static|final|abstract|synchronized|native|"
    r"default|strictfp|transient|volatile|sealed|non-sealed)"
)
_MODIFICATEURS = rf"(?:{_MOT_CLE_MODIFICATEUR}\s+)*"
_TYPE = (rf"(?!(?:{_MOT_CLE_MODIFICATEUR}|class|interface|enum|record)\b)"
         rf"{_IDENT}(?:\s*\.\s*{_IDENT})*(?:\s*<[^;{{}}()]*>)?(?:\s*\[\s*\])*")
_PARAMETRES = r"(?:[^()]|\([^()]*\))*"

_MOTIF_PAQUET = re.compile(r"(?m)^[ \t]*package\s+([\w.$]+)\s*;")
_MOTIF_IMPORT = re.compile(
    r"(?m)^[ \t]*import\s+(?P<statique>static\s+)?(?P<nom>[\w.$*]+)\s*;")
_MOTIF_TYPE = re.compile(
    rf"(?m)^[ \t]*(?P<annotations>(?:{_ANNOTATION}[ \t\r\n]*)*)"
    rf"(?P<modificateurs>{_MODIFICATEURS})"
    rf"(?<!@)\b(?P<type_kind>class|interface|enum|record)\s+(?P<nom>{_IDENT})")
_MOTIF_METHODE = re.compile(
    rf"(?m)^[ \t]*(?P<annotations>(?:{_ANNOTATION}[ \t\r\n]*)*)"
    rf"(?P<modificateurs>{_MODIFICATEURS})(?:<[^;{{}}()]*>\s*)?"
    rf"(?P<retour>{_TYPE})[ \t]+(?P<nom>{_IDENT})[ \t]*"
    rf"\((?P<parametres>{_PARAMETRES})\)[ \t]*(?:throws[^{{;]*)?(?P<fin>[{{;])")
_MOTIF_CONSTRUCTEUR = re.compile(
    rf"(?m)^[ \t]*(?P<annotations>(?:{_ANNOTATION}[ \t\r\n]*)*)"
    rf"(?P<modificateurs>{_MODIFICATEURS})(?:<[^;{{}}()]*>\s*)?(?P<nom>{_IDENT})[ \t]*"
    rf"\((?P<parametres>{_PARAMETRES})\)[ \t]*(?:throws[^{{;]*)?(?P<fin>\{{)")
_MOTIF_CHAMP = re.compile(
    rf"(?m)^[ \t]*(?P<annotations>(?:{_ANNOTATION}[ \t\r\n]*)*)"
    rf"(?P<modificateurs>{_MODIFICATEURS})(?P<type>{_TYPE})[ \t]+(?P<nom>{_IDENT})"
    rf"[ \t]*(?:=[^;]*)?;")
_MOTIF_ANNOTATION = re.compile(rf"@(?P<nom>{_NOM_ANNOTATION})")

_METHODES_HTTP = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE"})
_ROUTES_SPRING = {
    "GetMapping": "GET", "PostMapping": "POST", "PutMapping": "PUT",
    "DeleteMapping": "DELETE", "PatchMapping": "PATCH",
}
_ROUTES_JAXRS = {
    "GET": "GET", "POST": "POST", "PUT": "PUT", "PATCH": "PATCH",
    "DELETE": "DELETE", "HEAD": "HEAD", "OPTIONS": "OPTIONS",
}
_STEREOTYPES = (
    "RestController", "Controller", "Service", "Repository", "Component",
    "Configuration", "Stateless", "Stateful", "Singleton", "MessageDriven",
    "Entity", "Table",
)
_COMPOSANTS_JEE = frozenset({"Stateless", "Stateful", "Singleton", "MessageDriven"})
_INJECTIONS_JEE = frozenset({"EJB", "PersistenceContext", "PersistenceUnit", "Resource"})
_COLONNES_JPA = frozenset({"Column", "JoinColumn", "Id"})
_RELATIONS_JPA = frozenset({"OneToMany", "ManyToOne", "ManyToMany"})
_KINDS_WEB = frozenset({"web_servlet", "web_filter"})


def _ligne(texte: str, position: int) -> int:
    return texte.count("\n", 0, max(0, position)) + 1


def _masquer(texte: str) -> str:
    """Masque commentaires, chaînes et text blocks en conservant les retours à la ligne."""
    caracteres = list(texte)
    taille = len(texte)
    i = 0
    while i < taille:
        caractere = texte[i]
        if texte.startswith("//", i):
            while i < taille and texte[i] != "\n":
                caracteres[i] = " "
                i += 1
        elif texte.startswith("/*", i):
            caracteres[i] = caracteres[i + 1] = " "
            i += 2
            while i < taille:
                if texte.startswith("*/", i):
                    caracteres[i] = caracteres[i + 1] = " "
                    i += 2
                    break
                if texte[i] != "\n":
                    caracteres[i] = " "
                i += 1
        elif texte.startswith('"""', i):
            for decalage in range(3):
                caracteres[i + decalage] = " "
            i += 3
            while i < taille:
                if texte.startswith('"""', i):
                    for decalage in range(3):
                        caracteres[i + decalage] = " "
                    i += 3
                    break
                if texte[i] != "\n":
                    caracteres[i] = " "
                i += 1
        elif caractere in "\"'":
            guillemet = caractere
            caracteres[i] = " "
            i += 1
            while i < taille:
                if texte[i] == "\\":
                    caracteres[i] = " "
                    if i + 1 < taille and texte[i + 1] != "\n":
                        caracteres[i + 1] = " "
                    i += 2
                    continue
                if texte[i] == guillemet:
                    caracteres[i] = " "
                    i += 1
                    break
                if texte[i] == "\n":
                    break
                caracteres[i] = " "
                i += 1
        else:
            i += 1
    return "".join(caracteres)


def _profondeurs(masque: str) -> list[int]:
    profondeur, resultat = 0, [0] * (len(masque) + 1)
    for position, caractere in enumerate(masque):
        resultat[position] = profondeur
        if caractere == "{":
            profondeur += 1
        elif caractere == "}":
            profondeur = max(0, profondeur - 1)
    resultat[len(masque)] = profondeur
    return resultat


def _fermeture(masque: str, ouverture: int) -> int:
    profondeur = 0
    for position in range(ouverture, len(masque)):
        if masque[position] == "{":
            profondeur += 1
        elif masque[position] == "}":
            profondeur -= 1
            if profondeur == 0:
                return position
    return max(ouverture, len(masque) - 1)


def _decouper(texte: str, separateur: str = ",") -> list[str]:
    morceaux, debut = [], 0
    profondeur, guillemet = 0, ""
    i = 0
    while i < len(texte):
        caractere = texte[i]
        if guillemet:
            if caractere == "\\":
                i += 2
                continue
            if caractere == guillemet:
                guillemet = ""
        elif caractere in "\"'":
            guillemet = caractere
        elif caractere in "<{([":
            profondeur += 1
        elif caractere in ">})]":
            profondeur = max(0, profondeur - 1)
        elif caractere == separateur and profondeur == 0:
            morceaux.append(texte[debut:i])
            debut = i + 1
        i += 1
    morceaux.append(texte[debut:])
    return morceaux


def _cle_valeur(morceau: str) -> tuple[str, str]:
    profondeur, guillemet = 0, ""
    i = 0
    while i < len(morceau):
        caractere = morceau[i]
        if guillemet:
            if caractere == "\\":
                i += 2
                continue
            if caractere == guillemet:
                guillemet = ""
        elif caractere in "\"'":
            guillemet = caractere
        elif caractere in "<{([":
            profondeur += 1
        elif caractere in ">})]":
            profondeur = max(0, profondeur - 1)
        elif caractere == "=" and profondeur == 0:
            return morceau[:i].strip(), morceau[i + 1:]
        i += 1
    return "", morceau


def _deséchapper(valeur: str) -> str:
    return re.sub(r"\\(.)", lambda trouve: {
        "n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f",
    }.get(trouve.group(1), trouve.group(1)), valeur)


def _valeur_brute(texte: str):
    texte = texte.strip()
    if not texte:
        return ""
    if texte.startswith("{") and texte.endswith("}"):
        return [_valeur_brute(morceau) for morceau in _decouper(texte[1:-1]) if morceau.strip()]
    if len(texte) >= 2 and texte[0] == texte[-1] and texte[0] in "\"'":
        return _deséchapper(texte[1:-1])
    return texte


def _arguments(brut: str) -> dict:
    resultat = {}
    for morceau in _decouper(brut or ""):
        morceau = morceau.strip()
        if not morceau:
            continue
        cle, valeur = _cle_valeur(morceau)
        if cle:
            resultat[cle] = _valeur_brute(valeur)
        else:
            valeur = _valeur_brute(morceau)
            if "value" not in resultat:
                resultat["value"] = valeur
            elif isinstance(resultat["value"], list):
                resultat["value"].append(valeur)
            else:
                resultat["value"] = [resultat["value"], valeur]
    return resultat


def _liste_textes(valeur) -> list[str]:
    if valeur is None:
        return []
    elements = valeur if isinstance(valeur, (list, tuple, set)) else (valeur,)
    return [str(element).strip() for element in elements if str(element).strip()]


def _nom_simple(annotation: str) -> str:
    return re.split(r"\s*\.\s*", annotation or "")[-1]


def _scan_annotations(masque: str, original: str, debut: int, fin: int) -> list[dict]:
    resultat = []
    for trouve in _MOTIF_ANNOTATION.finditer(masque, debut, fin):
        nom = _nom_simple(trouve.group("nom"))
        if not nom or nom == "interface":
            continue
        position = trouve.end()
        curseur = position
        while curseur < len(masque) and masque[curseur].isspace():
            curseur += 1
        fin_annotation = position
        arguments = {}
        if curseur < len(masque) and masque[curseur] == "(":
            ouverture = curseur
            profondeur = 0
            while curseur < len(masque):
                if masque[curseur] == "(":
                    profondeur += 1
                elif masque[curseur] == ")":
                    profondeur -= 1
                    if profondeur == 0:
                        curseur += 1
                        break
                curseur += 1
            fin_annotation = curseur
            arguments = _arguments(original[ouverture + 1:max(ouverture + 1, curseur - 1)])
        resultat.append({
            "nom": trouve.group("nom"), "simple": nom, "arguments": arguments,
            "start": trouve.start(), "end": fin_annotation,
        })
    return resultat


def _annotations_bloc(masque: str, original: str, debut: int, fin: int) -> list[dict]:
    if fin <= debut:
        return []
    return _scan_annotations(masque, original, debut, fin)


def _frontiere(texte: str, debut: int, fin: int) -> bool:
    avant = texte[debut - 1] if debut > 0 else ""
    apres = texte[fin] if fin < len(texte) else ""
    return not (avant.isalnum() or avant in "_$") and not (apres.isalnum() or apres in "_$")


def _clauses(entete: str) -> list[dict]:
    positions, profondeur, i = [], 0, 0
    while i < len(entete):
        caractere = entete[i]
        if caractere == "<":
            profondeur += 1
        elif caractere == ">":
            profondeur = max(0, profondeur - 1)
        elif profondeur == 0:
            for mot in ("extends", "implements"):
                if entete.startswith(mot, i) and _frontiere(entete, i, i + len(mot)):
                    positions.append((i, mot))
                    i += len(mot)
                    break
            else:
                i += 1
            continue
        i += 1
    resultat = []
    for index, (position, mot) in enumerate(positions):
        fin = positions[index + 1][0] if index + 1 < len(positions) else len(entete)
        for nom in _decouper(entete[position + len(mot):fin]):
            nom = " ".join(nom.split())
            if nom:
                resultat.append({"clause": mot, "nom": nom, "position": position})
    return resultat


def _type_simple(type_texte: str) -> str:
    interieur = re.findall(r"<([^<>]+)>", type_texte or "")
    base = interieur[-1] if interieur else type_texte
    base = base.split(",")[-1] if interieur else base
    return _nom_simple(base.strip().rstrip("[]").strip())


def _classe_fqn(package: str, nom: str) -> str:
    return f"{package}.{nom}" if package else nom


def _proprietaire(types: list[dict], profondeurs: list[int], position: int):
    profondeur = profondeurs[position] if position < len(profondeurs) else 0
    candidats = [type_ for type_ in types
                 if type_["ouverture"] <= position <= type_["fermeture"]
                 and type_["profondeur"] == profondeur]
    return max(candidats, key=lambda type_: type_["profondeur"]) if candidats else None


def _prefixe(type_: dict) -> str:
    for annotation in type_.get("annotations", ()):
        if annotation["simple"] != "RequestMapping":
            continue
        chemins = _liste_textes(annotation["arguments"].get("path")
                                or annotation["arguments"].get("value"))
        if chemins:
            return chemins[0]
    return ""


def _prefixe_jaxrs(type_: dict) -> str:
    for annotation in type_.get("annotations", ()):
        if annotation["simple"] != "Path":
            continue
        chemins = _liste_textes(annotation["arguments"].get("value")
                                or annotation["arguments"].get("path"))
        if chemins:
            return chemins[0]
    return ""


def _joindre_chemin(*parties) -> str:
    morceaux = []
    for partie in parties:
        morceaux.extend(fragment for fragment in str(partie or "").strip("/").split("/")
                        if fragment)
    return "/" + "/".join(morceaux) if morceaux else ""


def _table(type_: dict) -> str:
    for annotation in type_.get("annotations", ()):
        if annotation["simple"] == "Table":
            tables = _liste_textes(annotation["arguments"].get("name")
                                   or annotation["arguments"].get("value"))
            if tables:
                return tables[0]
    return ""


def _type_kind_annotation(nom: str) -> tuple[str, str]:
    if nom in _ROUTES_SPRING or nom == "RequestMapping":
        return "spring_route", "spring"
    if nom == "Bean":
        return "spring_bean", "spring"
    if nom in {"Autowired", "Value"}:
        return "spring_injection", "spring"
    if nom in {"RestController", "Controller", "Service", "Repository", "Component",
               "Configuration", "Transactional", "Scheduled"}:
        return "java_annotation", "spring"
    if nom in _COMPOSANTS_JEE:
        return "jee_component", "jee"
    if nom in _INJECTIONS_JEE:
        return "jee_injection", "jee"
    if nom == "Entity":
        return "jpa_entity", "jpa"
    if nom == "Table":
        return "jpa_table", "jpa"
    if nom in _COLONNES_JPA:
        return "jpa_column", "jpa"
    if nom in _RELATIONS_JPA:
        return "jpa_relation", "jpa"
    if nom == "NamedQuery":
        return "jpa_query", "jpa"
    if nom == "WebServlet":
        return "web_servlet", "jee"
    if nom == "WebFilter":
        return "web_filter", "jee"
    if nom == "WebListener":
        return "web_listener", "jee"
    return "java_annotation", ""


def _methodes_route(valeur) -> list[str]:
    methodes = []
    for element in _liste_textes(valeur):
        for mot in re.split(r"[,;|/\s]+", element):
            mot = mot.upper().rsplit(".", 1)[-1]
            if mot in _METHODES_HTTP and mot not in methodes:
                methodes.append(mot)
    return methodes


def _observation_route(fichier: str, annotation: dict, type_, membre) -> list[Observation]:
    nom, arguments = annotation["simple"], annotation["arguments"]
    prefixe = _prefixe(type_) if membre is not None and type_ else ""
    if nom in _ROUTES_SPRING:
        methodes = [_ROUTES_SPRING[nom]]
    else:
        methodes = _methodes_route(arguments.get("method") or arguments.get("methods")
                                   or arguments.get("http_method")) or ["ANY"]
    valeur = arguments.get("value", arguments.get("path", ""))
    propres = _liste_textes(arguments.get("path") or arguments.get("value"))
    chemins = propres or [""]
    proprietaire = _classe_fqn(type_["package"], type_["nom"]) if type_ else ""
    observations = []
    for methode in methodes:
        for chemin in chemins:
            effectif = chemin or prefixe
            symbole = f"{methode} {effectif}".strip()
            attributes = {
                "annotation": nom,
                "qualified": annotation["nom"],
                "framework": "spring",
                "value": valeur,
                "path": effectif,
                "paths": propres or ([prefixe] if prefixe else []),
                "method": methode,
                "methods": [methode],
                "http_method": methode,
                "prefix": prefixe,
                "controller": proprietaire,
                "java_class": proprietaire,
                "scope": "member" if membre is not None else "type",
            }
            if membre is not None:
                attributes["member"] = membre["nom"]
                attributes["member_kind"] = membre["kind"]
            observations.append(Observation(
                provider=PROVIDER, parser=PARSER, parser_version=PARSER_VERSION,
                file=fichier, language=LANGAGE, kind="spring_route", symbol=symbole,
                start=annotation["ligne_debut"], end=annotation["ligne_fin"],
                attributes=attributes, confidence=1.0, status="extracted",
            ))
    return observations


def _observation_annotation(fichier: str, annotation: dict, type_, membre) -> Observation:
    nom, arguments = annotation["simple"], dict(annotation["arguments"])
    kind, framework = _type_kind_annotation(nom)
    attributes = dict(arguments)
    attributes["annotation"] = nom
    if annotation["nom"] != nom:
        attributes["qualified"] = annotation["nom"]
    attributes["framework"] = framework
    attributes["scope"] = "member" if membre is not None else ("type" if type_ else "file")
    if type_ is not None:
        attributes.setdefault("class", _classe_fqn(type_["package"], type_["nom"]))
        attributes.setdefault("owner", _classe_fqn(type_["package"], type_["nom"]))
    if membre is not None:
        attributes["member"] = membre["nom"]
        attributes["member_kind"] = membre["kind"]

    symbole = nom
    if kind == "jpa_entity" and type_ is not None:
        fqn = _classe_fqn(type_["package"], type_["nom"])
        symbole = type_["nom"]
        attributes.update({
            "name": type_["nom"], "simple_name": type_["nom"], "fqn": fqn,
            "package": type_["package"], "table": _table(type_),
        })
    elif kind == "jpa_table":
        tables = _liste_textes(arguments.get("name") or arguments.get("value"))
        table = tables[0] if tables else (type_["nom"] if type_ else nom)
        symbole = table
        attributes.update({"name": table, "table": table})
        if type_ is not None:
            attributes.setdefault("class", type_["nom"])
    elif kind == "jpa_column":
        colonnes = _liste_textes(arguments.get("name") or arguments.get("value"))
        colonne = colonnes[0] if colonnes else (
            membre["nom"] if membre is not None else (type_["nom"] if type_ else nom))
        symbole = colonne
        attributes.update({"name": colonne, "column": colonne})
        if type_ is not None:
            table = _table(type_)
            if table:
                attributes.setdefault("table", table)
    elif kind == "jpa_relation":
        symbole = membre["nom"] if membre is not None else nom
        cible = arguments.get("targetEntity") or arguments.get("targetentity") or ""
        if not cible and membre is not None:
            cible = _type_simple(membre.get("type_champ", ""))
        attributes.update({"relation": nom, "target": _nom_simple(str(cible).removesuffix(".class"))})
        if type_ is not None:
            table = _table(type_)
            if table:
                attributes.setdefault("table", table)
    elif kind == "jpa_query":
        noms = _liste_textes(arguments.get("name") or arguments.get("value"))
        requete = noms[0] if noms else (type_["nom"] if type_ else nom)
        symbole = requete
        attributes.update({"name": requete, "query": arguments.get("query", "")})
    elif kind in {"jee_component", "web_listener"}:
        symbole = type_["nom"] if type_ is not None else nom
        attributes.setdefault("name", symbole)
        if kind == "jee_component":
            attributes.setdefault("stereotype", nom)
    elif kind in {"jee_injection", "spring_injection"}:
        symbole = membre["nom"] if membre is not None else nom
        attributes.setdefault("name", symbole)
    elif kind == "spring_bean":
        noms = _liste_textes(arguments.get("name") or arguments.get("value"))
        symbole = noms[0] if noms else (
            membre["nom"] if membre is not None else (
                type_["nom"] if type_ is not None else nom))
        attributes.setdefault("name", symbole)
        if membre is not None:
            attributes.setdefault("method", membre["nom"])
    elif kind in _KINDS_WEB:
        noms = _liste_textes(arguments.get("name"))
        symbole = noms[0] if noms else (type_["nom"] if type_ is not None else nom)
        motifs = _liste_textes(arguments.get("urlPatterns") or arguments.get("value"))
        attributes.setdefault("name", symbole)
        attributes["url_patterns"] = motifs
        if type_ is not None:
            attributes.setdefault("class", type_["nom"])
    elif kind == "java_annotation" and nom in _STEREOTYPES:
        attributes.setdefault("stereotype", nom)

    return Observation(
        provider=PROVIDER, parser=PARSER, parser_version=PARSER_VERSION,
        file=fichier, language=LANGAGE, kind=kind, symbol=symbole,
        start=annotation["ligne_debut"], end=annotation["ligne_fin"],
        attributes=attributes, confidence=1.0, status="extracted",
    )


def _extraire(fichier: str, texte: str) -> list[Observation]:
    masque = _masquer(texte)
    profondeurs = _profondeurs(masque)
    observations: list[Observation] = []

    paquet = ""
    for trouve in _MOTIF_PAQUET.finditer(masque):
        paquet = trouve.group(1)
        ligne = _ligne(masque, trouve.start())
        observations.append(Observation(
            provider=PROVIDER, parser=PARSER, parser_version=PARSER_VERSION, file=fichier,
            language=LANGAGE, kind="java_package", symbol=paquet, start=ligne, end=ligne,
            attributes={"package": paquet, "name": paquet}, confidence=1.0, status="extracted"))
        break

    imports = []
    for trouve in _MOTIF_IMPORT.finditer(masque):
        nom = trouve.group("nom")
        imports.append(nom)
        ligne = _ligne(masque, trouve.start())
        observations.append(Observation(
            provider=PROVIDER, parser=PARSER, parser_version=PARSER_VERSION, file=fichier,
            language=LANGAGE, kind="java_import", symbol=nom, start=ligne, end=ligne,
            attributes={"target": nom, "import": nom, "name": nom,
                        "static": bool(trouve.group("statique"))},
            confidence=1.0, status="extracted"))

    types = []
    for trouve in _MOTIF_TYPE.finditer(masque):
        nom = trouve.group("nom")
        ouverture = masque.find("{", trouve.end())
        if ouverture < 0:
            continue
        fermeture = _fermeture(masque, ouverture)
        annotations = _annotations_bloc(
            masque, texte, trouve.start("annotations"), trouve.end("annotations"))
        for annotation in annotations:
            annotation["ligne_debut"] = _ligne(masque, annotation["start"])
            annotation["ligne_fin"] = _ligne(masque, max(annotation["start"], annotation["end"] - 1))
        entete = masque[trouve.end():ouverture]
        types.append({
            "kind": "java_type", "nom": nom, "type_kind": trouve.group("type_kind"),
            "package": paquet, "fqn": _classe_fqn(paquet, nom),
            "start": trouve.start(), "end": fermeture,
            "ouverture": ouverture, "fermeture": fermeture,
            "profondeur": profondeurs[ouverture] + 1,
            "modificateurs": trouve.group("modificateurs").split(),
            "annotations": annotations,
            "clauses": _clauses(entete),
            "base_clauses": trouve.end(),
            "table": "", "champs": [], "methodes": [],
        })
    for type_ in types:
        type_["table"] = _table(type_)

    membres = []
    for trouve in _MOTIF_METHODE.finditer(masque):
        type_ = _proprietaire(types, profondeurs, trouve.start())
        if type_ is None:
            continue
        fin = trouve.end() - 1
        if trouve.group("fin") == "{":
            fin = _fermeture(masque, fin)
        annotations = _annotations_bloc(
            masque, texte, trouve.start("annotations"), trouve.end("annotations"))
        for annotation in annotations:
            annotation["ligne_debut"] = _ligne(masque, annotation["start"])
            annotation["ligne_fin"] = _ligne(masque, max(annotation["start"], annotation["end"] - 1))
        parametres = [" ".join(morceau.split()) for morceau in
                      _decouper(trouve.group("parametres")) if morceau.strip()]
        membres.append({
            "kind": "java_method", "nom": trouve.group("nom"),
            "start": trouve.start(), "end": fin, "type_": type_,
            "annotations": annotations, "retour": " ".join(trouve.group("retour").split()),
            "parametres": parametres, "modificateurs": trouve.group("modificateurs").split(),
            "constructeur": False, "type_champ": "",
        })
    for trouve in _MOTIF_CONSTRUCTEUR.finditer(masque):
        type_ = _proprietaire(types, profondeurs, trouve.start())
        if type_ is None or trouve.group("nom") != type_["nom"]:
            continue
        fin = _fermeture(masque, trouve.end() - 1)
        annotations = _annotations_bloc(
            masque, texte, trouve.start("annotations"), trouve.end("annotations"))
        for annotation in annotations:
            annotation["ligne_debut"] = _ligne(masque, annotation["start"])
            annotation["ligne_fin"] = _ligne(masque, max(annotation["start"], annotation["end"] - 1))
        parametres = [" ".join(morceau.split()) for morceau in
                      _decouper(trouve.group("parametres")) if morceau.strip()]
        membres.append({
            "kind": "java_method", "nom": trouve.group("nom"),
            "start": trouve.start(), "end": fin, "type_": type_,
            "annotations": annotations, "retour": "", "parametres": parametres,
            "modificateurs": trouve.group("modificateurs").split(),
            "constructeur": True, "type_champ": "",
        })
    for trouve in _MOTIF_CHAMP.finditer(masque):
        type_ = _proprietaire(types, profondeurs, trouve.start())
        if type_ is None:
            continue
        annotations = _annotations_bloc(
            masque, texte, trouve.start("annotations"), trouve.end("annotations"))
        for annotation in annotations:
            annotation["ligne_debut"] = _ligne(masque, annotation["start"])
            annotation["ligne_fin"] = _ligne(masque, max(annotation["start"], annotation["end"] - 1))
        type_champ = " ".join(trouve.group("type").split())
        membres.append({
            "kind": "java_field", "nom": trouve.group("nom"),
            "start": trouve.start(), "end": trouve.end() - 1, "type_": type_,
            "annotations": annotations, "retour": "", "parametres": [],
            "modificateurs": trouve.group("modificateurs").split(),
            "constructeur": False, "type_champ": type_champ,
        })

    for type_ in types:
        type_["champs"] = [
            {"name": membre["nom"], "type": membre["type_champ"],
             "annotations": [a["simple"] for a in membre["annotations"]]}
            for membre in membres if membre["type_"] is type_ and membre["kind"] == "java_field"]
        type_["methodes"] = [
            {"name": membre["nom"], "return_type": membre["retour"],
             "annotations": [a["simple"] for a in membre["annotations"]]}
            for membre in membres if membre["type_"] is type_ and membre["kind"] == "java_method"]

    for type_ in types:
        noms = [annotation["simple"] for annotation in type_["annotations"]]
        stereotype = next((nom for nom in noms if nom in _STEREOTYPES), "")
        attributes = {
            "name": type_["nom"], "simple_name": type_["nom"], "fqn": type_["fqn"],
            "class": type_["nom"], "class_name": type_["nom"],
            "qualified_name": type_["fqn"], "package": type_["package"],
            "type_kind": type_["type_kind"], "modifiers": type_["modificateurs"],
            "annotations": noms,
            "annotation_details": {a["simple"]: a["arguments"] for a in type_["annotations"]},
            "imports": list(imports), "fields": type_["champs"],
            "methods": type_["methodes"],
            "extends": [c["nom"] for c in type_["clauses"] if c["clause"] == "extends"],
            "implements": [c["nom"] for c in type_["clauses"] if c["clause"] == "implements"],
        }
        if stereotype:
            attributes["stereotype"] = stereotype
            attributes["stereotypes"] = [stereotype]
        if type_["table"]:
            attributes["table"] = type_["table"]
        observations.append(Observation(
            provider=PROVIDER, parser=PARSER, parser_version=PARSER_VERSION, file=fichier,
            language=LANGAGE, kind="java_type", symbol=type_["nom"],
            start=_ligne(masque, type_["start"]), end=_ligne(masque, type_["fermeture"]),
            attributes=attributes, confidence=1.0, status="extracted"))
        for clause in type_["clauses"]:
            attributes = {"type": type_["nom"], "class": type_["fqn"]}
            if clause["clause"] == "extends":
                symbole = f"{type_['nom']} extends {clause['nom']}"
                kind = "java_extends"
                attributes.update({"parent": clause["nom"], "extends": clause["nom"]})
            else:
                symbole = f"{type_['nom']} implements {clause['nom']}"
                kind = "java_implements"
                attributes.update({"interface": clause["nom"], "implements": clause["nom"]})
            ligne = _ligne(masque, type_["base_clauses"] + clause["position"])
            observations.append(Observation(
                provider=PROVIDER, parser=PARSER, parser_version=PARSER_VERSION, file=fichier,
                language=LANGAGE, kind=kind, symbol=symbole, start=ligne, end=ligne,
                attributes=attributes, confidence=1.0, status="extracted"))

    for membre in membres:
        type_ = membre["type_"]
        attributes = {
            "name": membre["nom"], "owner": type_["fqn"], "owner_class": type_["fqn"],
            "class": type_["nom"], "package": type_["package"],
            "modifiers": membre["modificateurs"],
            "annotations": [annotation["simple"] for annotation in membre["annotations"]],
            "annotation_details": {a["simple"]: a["arguments"] for a in membre["annotations"]},
            "scope": "member",
        }
        if membre["kind"] == "java_field":
            attributes["type"] = membre["type_champ"]
        else:
            attributes["return_type"] = membre["retour"]
            attributes["parameters"] = membre["parametres"]
            attributes["signature"] = f"{membre['nom']}({', '.join(membre['parametres'])})"
            attributes["constructor"] = membre["constructeur"]
        observations.append(Observation(
            provider=PROVIDER, parser=PARSER, parser_version=PARSER_VERSION, file=fichier,
            language=LANGAGE, kind=membre["kind"], symbol=membre["nom"],
            start=_ligne(masque, membre["start"]), end=_ligne(masque, membre["end"]),
            attributes=attributes, confidence=1.0, status="extracted"))

    for membre in membres:
        if membre["constructeur"]:
            continue
        type_ = membre["type_"]
        base = _prefixe_jaxrs(type_)
        if not base:
            continue
        methode = next((_ROUTES_JAXRS[annotation["simple"]]
                        for annotation in membre["annotations"]
                        if annotation["simple"] in _ROUTES_JAXRS), "")
        if not methode:
            continue
        sous_chemin = ""
        for annotation in membre["annotations"]:
            if annotation["simple"] != "Path":
                continue
            chemins = _liste_textes(annotation["arguments"].get("value")
                                    or annotation["arguments"].get("path"))
            if chemins:
                sous_chemin = chemins[0]
                break
        chemin = _joindre_chemin(base, sous_chemin)
        if not chemin:
            continue
        fqn = _classe_fqn(type_["package"], type_["nom"])
        observations.append(Observation(
            provider=PROVIDER, parser=PARSER, parser_version=PARSER_VERSION, file=fichier,
            language=LANGAGE, kind="jaxrs_route", symbol=f"{methode} {chemin}",
            start=_ligne(masque, membre["start"]), end=_ligne(masque, membre["end"]),
            attributes={
                "annotation": methode, "framework": "jaxrs",
                "value": sous_chemin or base, "path": chemin, "paths": [chemin],
                "method": methode, "methods": [methode], "http_method": methode,
                "prefix": base, "controller": fqn, "java_class": fqn,
                "scope": "member", "member": membre["nom"],
                "member_kind": membre["kind"],
            }, confidence=1.0, status="extracted"))

    for annotation in _scan_annotations(masque, texte, 0, len(masque)):
        annotation["ligne_debut"] = _ligne(masque, annotation["start"])
        annotation["ligne_fin"] = _ligne(masque, max(annotation["start"], annotation["end"] - 1))
        contexte = None
        for candidat in types:
            if candidat["start"] <= annotation["start"] < candidat["end"]:
                if (contexte is None or
                        candidat["end"] - candidat["start"] <
                        contexte["end"] - contexte["start"]):
                    contexte = candidat
        for candidat in membres:
            if candidat["start"] <= annotation["start"] < candidat["end"]:
                if (contexte is None or
                        candidat["end"] - candidat["start"] <
                        contexte["end"] - contexte["start"]):
                    contexte = candidat
        if contexte is not None and contexte.get("kind") == "java_type":
            type_, membre = contexte, None
        elif contexte is not None:
            type_, membre = contexte["type_"], contexte
        else:
            type_, membre = None, None
        if annotation["simple"] in _ROUTES_SPRING or annotation["simple"] == "RequestMapping":
            observations.extend(_observation_route(fichier, annotation, type_, membre))
        else:
            observations.append(_observation_annotation(fichier, annotation, type_, membre))

    return observations


def extraire(fichier: str, texte: str) -> list[Observation]:
    """Observations structurelles d'un texte Java, sans passer par le disque."""
    return _extraire(fichier, texte if isinstance(texte, str) else "")


def _resoudre(racine: str, fichier: str) -> Path:
    chemin = Path(fichier)
    return chemin if chemin.is_absolute() else Path(racine) / chemin


def _relatif(racine: str, chemin: Path) -> str:
    try:
        return chemin.resolve().relative_to(Path(racine).resolve()).as_posix()
    except (OSError, ValueError):
        return chemin.as_posix()


def _decouvrir(racine: str) -> list[Path]:
    base = Path(racine)
    if not base.is_dir():
        return []
    trouves = []
    for dossier, sous_dossiers, noms in os.walk(base):
        sous_dossiers[:] = sorted(nom for nom in sous_dossiers if nom not in EXCLUSIONS)
        for nom in sorted(noms):
            if Path(nom).suffix.lower() == EXTENSION:
                trouves.append(Path(dossier) / nom)
    return sorted(trouves)


def _est_java(fichier: str) -> bool:
    return Path(fichier).suffix.lower() == EXTENSION


def _cibles(racine: str, fichiers: Sequence[str]) -> list[str]:
    if fichiers:
        return sorted({_relatif(racine, _resoudre(racine, fichier)) for fichier in fichiers})
    return [_relatif(racine, chemin) for chemin in _decouvrir(racine)]


def _lire(chemin: Path) -> str:
    return chemin.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff")


class JavaSourceSidecar:
    """Indexe les déclarations et annotations Java sans compiler ni exécuter le code."""

    provider = PROVIDER
    extensions = (EXTENSION,)
    parser = PARSER
    parser_version = PARSER_VERSION

    def index(self, racine: str, fichiers: Sequence[str] = ()) -> list[Observation]:
        """Observations structurelles des fichiers Java demandés ou découverts sous la racine."""
        observations = []
        for fichier in _cibles(racine, fichiers):
            if not _est_java(fichier):
                continue
            try:
                texte = _lire(_resoudre(racine, fichier))
            except OSError:
                continue
            if not texte.strip():
                continue
            observations.extend(_extraire(fichier, texte))
        return sorted(observations, key=lambda o: (o.file, o.start, o.kind, o.symbol))

    def couverture(self, racine: str, fichiers: Sequence[str] = ()) -> list[CouvertureFichier]:
        """Une ligne de couverture par fichier ciblé, y compris vide ou illisible."""
        resultat = []
        for fichier in _cibles(racine, fichiers):
            if not _est_java(fichier):
                resultat.append(CouvertureFichier(
                    file=fichier, language=LANGAGE, parser=PARSER, statut="partiel",
                    raison="extension Java non prise en charge"))
                continue
            try:
                texte = _lire(_resoudre(racine, fichier))
            except OSError as erreur:
                resultat.append(CouvertureFichier(
                    file=fichier, language=LANGAGE, parser=PARSER, statut="partiel",
                    raison=f"fichier illisible : {erreur}"))
                continue
            if not texte.strip():
                resultat.append(CouvertureFichier(
                    file=fichier, language=LANGAGE, parser=PARSER, statut="ignore",
                    raison="fichier vide"))
                continue
            if _extraire(fichier, texte):
                resultat.append(CouvertureFichier(
                    file=fichier, language=LANGAGE, parser=PARSER, statut="indexe", raison=""))
            else:
                resultat.append(CouvertureFichier(
                    file=fichier, language=LANGAGE, parser=PARSER, statut="partiel",
                    raison="aucune observation structurelle"))
        return resultat
