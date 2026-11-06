"""Sidecar des descripteurs Java XML : web.xml, EJB, Struts, Spring, persistence."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from pathlib import Path

from meridian.domain.code_index import CouvertureFichier, Observation

__all__ = ["JavaDescriptorSidecar"]

PROVIDER = "java-descriptor"
PARSER = "xml-descriptor"
PARSER_VERSION = "1"
LANGAGE = "xml"
_NOMS_CONNUS = {"web.xml", "ejb-jar.xml", "struts-config.xml", "persistence.xml", "applicationcontext.xml"}


def _local(nom: str) -> str:
    return str(nom or "").rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def _ligne(texte: str, position: int) -> int:
    return texte.count("\n", 0, max(0, position)) + 1


def _espaces(texte: str) -> str:
    return re.sub(r"[^\n]", " ", texte)


def _masquer_zones(texte: str) -> str:
    for motif in (r"<!--.*?-->", r"<!\[CDATA\[.*?\]\]>", r"<\?.*?\?>"):
        texte = re.sub(motif, lambda trouve: _espaces(trouve.group(0)), texte, flags=re.S)
    return texte


def _masquer_doctypes(texte: str) -> str:
    morceaux, curseur = [], 0
    for trouve in re.finditer(r"<!DOCTYPE", texte, re.I):
        if trouve.start() < curseur:
            continue
        morceaux.append(texte[curseur:trouve.start()])
        position, profondeur, guillemet = trouve.end(), 0, ""
        while position < len(texte):
            caractere = texte[position]
            if guillemet:
                if caractere == guillemet:
                    guillemet = ""
            elif caractere in "\"'":
                guillemet = caractere
            elif caractere == "[":
                profondeur += 1
            elif caractere == "]":
                profondeur = max(0, profondeur - 1)
            elif caractere == ">" and profondeur == 0:
                position += 1
                break
            position += 1
        morceaux.append(_espaces(texte[trouve.start():position]))
        curseur = position
    morceaux.append(texte[curseur:])
    return "".join(morceaux)


def _texte(element) -> str:
    return " ".join("".join(element.itertext()).split())


def _attr(element, nom: str) -> str:
    for cle, valeur in element.attrib.items():
        if _local(cle).lower() == nom.lower():
            return str(valeur).strip()
    return ""


def _enfant(element, nom: str):
    for enfant in element:
        if _local(enfant.tag).lower() == nom.lower():
            return enfant
    return None


def _texte_enfant(element, nom: str) -> str:
    enfant = _enfant(element, nom)
    return _texte(enfant) if enfant is not None else ""


def _propres(valeurs: dict) -> dict:
    return {cle: valeur for cle, valeur in valeurs.items() if valeur not in ("", None, [], {})}


class _Localisateur:
    def __init__(self, texte: str):
        self.texte = texte
        self.curseur = 0

    def localiser(self, element) -> tuple[int, int]:
        tag = _local(element.tag)
        if not tag:
            return 0, 0
        prefixe = r"(?:(?:[A-Za-z_][\w.-]*):)?"
        ouverture = re.compile(r"<" + prefixe + re.escape(tag) + r"(?=[\s/>])").search(
            self.texte, self.curseur)
        if not ouverture:
            return 0, 0
        fin_ouverture = self.texte.find(">", ouverture.end())
        if fin_ouverture < 0:
            position = _ligne(self.texte, ouverture.start())
            return position, position
        self.curseur = fin_ouverture + 1
        debut = _ligne(self.texte, ouverture.start())
        balise = self.texte[ouverture.start():fin_ouverture + 1]
        if re.search(r"/\s*>$", balise):
            return debut, _ligne(self.texte, fin_ouverture)
        fermeture = re.compile(r"</" + prefixe + re.escape(tag) + r"\s*>").search(
            self.texte, fin_ouverture + 1)
        return debut, (_ligne(self.texte, fermeture.end() - 1) if fermeture else debut)


def _observer(fichier: str, kind: str, symbole: str, element, localisateur: _Localisateur,
              attributs: dict | None = None, confiance: float = 1.0) -> Observation:
    debut, fin = localisateur.localiser(element)
    return Observation(
        provider=PROVIDER, parser=PARSER, parser_version=PARSER_VERSION, file=fichier,
        language=LANGAGE, kind=kind, symbol=symbole or f"{kind}:{debut}", start=debut, end=fin,
        attributes=_propres(attributs or {}), confidence=confiance, status="extracted",
    )


def _web(element, local: str, localisateur, fichier: str) -> list[Observation]:
    if local == "servlet":
        nom = _texte_enfant(element, "servlet-name")
        classe = _texte_enfant(element, "servlet-class")
        jsp = _texte_enfant(element, "jsp-file")
        return [_observer(fichier, "servlet", nom or classe or jsp, element, localisateur, {
            "name": nom, "class": classe, "jsp_file": jsp,
            "load_on_startup": _texte_enfant(element, "load-on-startup"),
        })]
    if local == "servlet-mapping":
        nom = _texte_enfant(element, "servlet-name")
        motifs = [_texte(enfant) for enfant in element
                  if _local(enfant.tag).lower() == "url-pattern" and _texte(enfant)]
        return [_observer(fichier, "servlet_mapping", nom or (motifs[0] if motifs else ""), element,
                          localisateur, {"servlet_name": nom, "url_patterns": motifs,
                                         "url_pattern": motifs[0] if motifs else ""})]
    if local == "filter":
        nom = _texte_enfant(element, "filter-name")
        classe = _texte_enfant(element, "filter-class")
        return [_observer(fichier, "filter", nom or classe, element, localisateur,
                          {"name": nom, "class": classe})]
    if local == "filter-mapping":
        nom = _texte_enfant(element, "filter-name")
        motifs = [_texte(enfant) for enfant in element
                  if _local(enfant.tag).lower() == "url-pattern" and _texte(enfant)]
        return [_observer(fichier, "filter_mapping", nom or (motifs[0] if motifs else ""), element,
                          localisateur, {"filter_name": nom, "servlet_name": _texte_enfant(element, "servlet-name"),
                                         "url_patterns": motifs,
                                         "url_pattern": motifs[0] if motifs else ""})]
    if local == "listener":
        classe = _texte_enfant(element, "listener-class")
        return [_observer(fichier, "listener", classe, element, localisateur, {"class": classe})]
    if local == "welcome-file":
        return [_observer(fichier, "welcome_file", _texte(element), element, localisateur)]
    return []


def _ejb(element, local: str, localisateur, fichier: str) -> list[Observation]:
    if local in {"session", "entity"}:
        nom = _texte_enfant(element, "ejb-name")
        attributs = {
            "name": nom, "type": local, "ejb_class": _texte_enfant(element, "ejb-class"),
            "home": _texte_enfant(element, "home"), "remote": _texte_enfant(element, "remote"),
            "local": _texte_enfant(element, "local"), "local_home": _texte_enfant(element, "local-home"),
            "session_type": _texte_enfant(element, "session-type"),
        }
        observations = [_observer(fichier, "ejb", nom, element, localisateur, attributs)]
        for etiquette in ("home", "remote", "local", "local-home"):
            interface = _enfant(element, etiquette)
            valeur = _texte(interface) if interface is not None else ""
            if valeur:
                observations.append(_observer(
                    fichier, "ejb_ref", valeur, interface, localisateur,
                    {"ejb": nom, "type": etiquette, "interface": valeur}))
        return observations
    if local == "message-driven":
        nom = _texte_enfant(element, "ejb-name")
        return [_observer(fichier, "mdb", nom, element, localisateur, {
            "name": nom, "ejb_class": _texte_enfant(element, "ejb-class"),
            "destination_type": _texte_enfant(element, "destination-type"),
            "subscription_durability": _texte_enfant(element, "subscription-durability"),
            "message_selector": _texte_enfant(element, "message-selector"),
            "acknowledge_mode": _texte_enfant(element, "acknowledge-mode"),
        })]
    if local == "resource-ref":
        nom = _texte_enfant(element, "res-ref-name")
        return [_observer(fichier, "ejb_ref", nom, element, localisateur, {
            "type": "resource-ref", "res_type": _texte_enfant(element, "res-type"),
            "res_auth": _texte_enfant(element, "res-auth"),
        })]
    return []


def _struts(element, local: str, localisateur, fichier: str) -> list[Observation]:
    if local == "action":
        chemin = _attr(element, "path")
        observations = [_observer(fichier, "struts_action", chemin or _attr(element, "type"), element,
                                  localisateur, {
                                      "path": chemin, "type": _attr(element, "type"),
                                      "name": _attr(element, "name"), "scope": _attr(element, "scope"),
                                  })]
        for enfant in element:
            if _local(enfant.tag).lower() == "forward":
                nom = _attr(enfant, "name")
                observations.append(_observer(fichier, "struts_forward", nom or _attr(enfant, "path"),
                                              enfant, localisateur, {
                                                  "action": chemin, "name": nom,
                                                  "path": _attr(enfant, "path"),
                                                  "redirect": _attr(enfant, "redirect"),
                                              }))
        return observations
    if local == "global-forwards":
        observations = []
        for enfant in element:
            if _local(enfant.tag).lower() == "forward":
                nom = _attr(enfant, "name")
                observations.append(_observer(fichier, "struts_forward", nom or _attr(enfant, "path"),
                                              enfant, localisateur, {
                                                  "name": nom, "path": _attr(enfant, "path"),
                                                  "redirect": _attr(enfant, "redirect"),
                                              }))
        return observations
    return []


def _spring(element, local: str, localisateur, fichier: str) -> list[Observation]:
    if local != "bean":
        return []
    identifiant = _attr(element, "id") or _attr(element, "name")
    classe = _attr(element, "class")
    observations = [_observer(fichier, "spring_bean", identifiant or classe, element, localisateur, {
        "id": _attr(element, "id"), "name": _attr(element, "name"), "class": classe,
        "scope": _attr(element, "scope"), "parent": _attr(element, "parent"),
        "abstract": _attr(element, "abstract"), "lazy_init": _attr(element, "lazy-init"),
    })]
    for enfant in element:
        if _local(enfant.tag).lower() != "property":
            continue
        nom = _attr(enfant, "name")
        reference = _attr(enfant, "ref")
        if not reference:
            sous_ref = _enfant(enfant, "ref")
            if sous_ref is not None:
                reference = (_attr(sous_ref, "bean") or _attr(sous_ref, "local")
                             or _attr(sous_ref, "parent"))
        if reference:
            observations.append(_observer(fichier, "spring_ref", reference, enfant, localisateur, {
                "bean": identifiant, "property": nom, "ref": reference,
                "value": _attr(enfant, "value"),
            }))
    return observations


def _persistence(element, local: str, localisateur, fichier: str) -> list[Observation]:
    if local != "persistence-unit":
        return []
    nom = _attr(element, "name")
    observations = [_observer(fichier, "persistence_unit", nom, element, localisateur, {
        "name": nom, "transaction_type": _attr(element, "transaction-type"),
    })]
    for enfant in element:
        etiquette = _local(enfant.tag).lower()
        if etiquette == "class":
            observations.append(_observer(fichier, "entity_class", _texte(enfant), enfant, localisateur,
                                          {"unit": nom}))
        elif etiquette in {"jta-data-source", "non-jta-data-source"}:
            observations.append(_observer(fichier, "datasource", _texte(enfant), enfant, localisateur,
                                          {"unit": nom, "type": etiquette}))
    return observations


def _extraire(racine, type_descripteur: str, texte: str, fichier: str) -> list[Observation]:
    localisateur = _Localisateur(_masquer_zones(texte))
    observations = []
    for element in racine.iter():
        local = _local(element.tag).lower()
        if type_descripteur == "web":
            observations.extend(_web(element, local, localisateur, fichier))
        elif type_descripteur == "ejb":
            observations.extend(_ejb(element, local, localisateur, fichier))
        elif type_descripteur == "struts":
            observations.extend(_struts(element, local, localisateur, fichier))
        elif type_descripteur == "spring":
            observations.extend(_spring(element, local, localisateur, fichier))
        elif type_descripteur == "persistence":
            observations.extend(_persistence(element, local, localisateur, fichier))
    return sorted(observations, key=lambda o: (o.file, o.start, o.kind, o.symbol))


def _type_descripteur(nom: str, racine) -> str:
    local = _local(racine.tag).lower()
    if local == "web-app":
        return "web"
    if local == "ejb-jar":
        return "ejb"
    if local == "struts-config":
        return "struts"
    if local == "beans":
        return "spring"
    if local == "persistence":
        return "persistence"
    minuscule = Path(nom).name.lower()
    if minuscule == "web.xml" or minuscule.endswith("-web.xml"):
        return "web"
    if minuscule.endswith("ejb-jar.xml"):
        return "ejb"
    if minuscule.startswith("struts-config") and minuscule.endswith(".xml"):
        return "struts"
    if "applicationcontext" in minuscule or (minuscule.startswith("spring") and minuscule.endswith(".xml")):
        return "spring"
    if minuscule == "persistence.xml":
        return "persistence"
    return ""


def _nom_connu(nom: str) -> bool:
    minuscule = nom.lower()
    return (minuscule in _NOMS_CONNUS
            or "applicationcontext" in minuscule
            or (minuscule.startswith("spring") and minuscule.endswith(".xml"))
            or (minuscule.startswith("struts-config") and minuscule.endswith(".xml"))
            or minuscule.endswith("-servlet.xml"))


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
    return sorted(chemin for chemin in base.rglob("*")
                  if chemin.is_file() and chemin.suffix.lower() == ".xml" and _nom_connu(chemin.name))


def _cibles(racine: str, fichiers: Sequence[str]) -> list[str]:
    if fichiers:
        return sorted({_relatif(racine, _resoudre(racine, fichier)) for fichier in fichiers})
    return [_relatif(racine, chemin) for chemin in _decouvrir(racine)]


def _analyser(chemin: Path, fichier: str) -> tuple[list[Observation], str, str]:
    texte = chemin.read_text(encoding="utf-8-sig", errors="replace")
    masque = _masquer_doctypes(texte)
    racine = ET.fromstring(masque)
    type_descripteur = _type_descripteur(fichier, racine)
    if not type_descripteur:
        return [], "ignore", "descripteur Java non reconnu"
    return _extraire(racine, type_descripteur, masque, fichier), "indexe", ""


class JavaDescriptorSidecar:
    """Indexe les descripteurs XML Java sans résoudre les entités externes ni exécuter de code."""

    provider = PROVIDER
    extensions = (".xml",)
    parser = PARSER
    parser_version = PARSER_VERSION

    def index(self, racine: str, fichiers: Sequence[str] = ()) -> list[Observation]:
        """Observations des descripteurs demandés ou découverts sous la racine."""
        observations = []
        for fichier in _cibles(racine, fichiers):
            if Path(fichier).suffix.lower() != ".xml":
                continue
            try:
                trouvees, _, _ = _analyser(_resoudre(racine, fichier), fichier)
            except (ET.ParseError, OSError, ValueError):
                continue
            observations.extend(trouvees)
        return sorted(observations, key=lambda o: (o.file, o.start, o.kind, o.symbol))

    def couverture(self, racine: str, fichiers: Sequence[str] = ()) -> list[CouvertureFichier]:
        """Une ligne de couverture par fichier : invalide ou inconnu reste explicitement signalé."""
        resultat = []
        for fichier in _cibles(racine, fichiers):
            if Path(fichier).suffix.lower() != ".xml":
                resultat.append(CouvertureFichier(
                    file=fichier, language="", parser=PARSER, statut="non_supporte",
                    raison="extension XML non prise en charge"))
                continue
            try:
                _, statut, raison = _analyser(_resoudre(racine, fichier), fichier)
            except (ET.ParseError, OSError, ValueError) as erreur:
                resultat.append(CouvertureFichier(
                    file=fichier, language=LANGAGE, parser=PARSER, statut="partiel",
                    raison=f"XML invalide ou illisible : {erreur}"))
                continue
            resultat.append(CouvertureFichier(
                file=fichier, language=LANGAGE, parser=PARSER, statut=statut, raison=raison))
        return resultat
