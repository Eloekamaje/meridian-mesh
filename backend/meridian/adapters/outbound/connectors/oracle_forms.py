"""Sidecar Oracle Forms : exports XML locaux, sans entité externe ni exécution."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from meridian.domain.code_index import CouvertureFichier, Observation

__all__ = ["OracleFormsSidecar"]

PROVIDER = "oracle-forms"
PARSER = "oracle-forms-xml"
VERSION = "1.0"
LANGAGE = "oracle-forms"
SUFFIXES = frozenset({".xml", ".fmb", ".fmx"})
PARSER_VERSION = VERSION
EXTENSIONS = tuple(sorted(SUFFIXES))

_MODULES = frozenset({"formmodule", "form"})
_SOURCES_TABLE = ("QueryDataSourceName", "DMLDataTargetName", "DataSourceName")
_RE_SQL_TABLE = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE|DELETE\s+FROM)\s+([A-Za-z_][\w$#.]*)", re.I)
_RE_FORM_CALL = re.compile(
    r"\b(?:CALL_FORM|OPEN_FORM|NEW_FORM)\s*\(\s*['\"]([^'\"]+)['\"]", re.I)


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
            return " ".join(str(valeur).split())
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


def _occurrences(texte: str):
    """Rend, par balise locale, les plages de lignes dans l'ordre du document."""
    resultat = {}
    pile = []
    i = 0
    while i < len(texte):
        if texte[i] != "<":
            i += 1
            continue
        if texte.startswith("<!--", i):
            fin = texte.find("-->", i + 4)
            i = len(texte) if fin < 0 else fin + 3
            continue
        if texte.startswith("<![CDATA[", i):
            fin = texte.find("]]>", i + 9)
            i = len(texte) if fin < 0 else fin + 3
            continue
        if texte.startswith("<?", i):
            fin = texte.find("?>", i + 2)
            i = len(texte) if fin < 0 else fin + 2
            continue
        if texte.startswith("<!", i):
            fin = texte.find(">", i + 2)
            i = len(texte) if fin < 0 else fin + 1
            continue
        j = i + 1
        guillemet = None
        while j < len(texte):
            caractere = texte[j]
            if guillemet:
                if caractere == guillemet:
                    guillemet = None
            elif caractere in "'\"":
                guillemet = caractere
            elif caractere == ">":
                break
            j += 1
        if j >= len(texte):
            break
        brute = texte[i:j + 1]
        fermeture = brute.startswith("</")
        auto = bool(re.search(r"/\s*>$", brute))
        trouve = re.match(r"</?\s*([A-Za-z_][\w.:-]*)", brute)
        if trouve:
            local = _local(trouve.group(1)).lower()
            ligne = _ligne(texte, i)
            if fermeture:
                while pile:
                    nom, entree = pile.pop()
                    if nom == local:
                        entree["end"] = ligne
                        break
            else:
                entree = {"start": ligne, "end": _ligne(texte, j) if auto else ligne}
                resultat.setdefault(local, []).append(entree)
                if not auto:
                    pile.append((local, entree))
        i = j + 1
    return resultat


def _plages(racine, texte: str) -> dict:
    occurrences = _occurrences(texte)
    curseurs = {}
    plages = {}
    for element in racine.iter():
        local = _local(element.tag).lower()
        index = curseurs.get(local, 0)
        curseurs[local] = index + 1
        liste = occurrences.get(local, [])
        if index < len(liste):
            plages[id(element)] = (liste[index]["start"], liste[index]["end"])
    return plages


def _observer(fichier, kind, symbole, element, plages, attributs=None) -> Observation:
    debut, fin = plages.get(id(element), (0, 0))
    return Observation(
        provider=PROVIDER, parser=PARSER, parser_version=VERSION, file=fichier,
        language=LANGAGE, kind=kind, symbol=symbole or f"{kind}:{debut}",
        start=debut, end=fin, attributes=_propres(attributs or {}))


def _table_bloc(element) -> str:
    for nom in _SOURCES_TABLE:
        valeur = _attr(element, nom)
        if valeur:
            return valeur
    return ""


def _normalise_table(nom: str) -> str:
    return str(nom or "").strip().strip('"').upper()


def _extraire(racine, fichier: str, plages: dict) -> list[Observation]:
    observations = []

    def parcourir(element, module: str, bloc: str, item: str):
        local = _local(element.tag).lower()
        nom = _attr(element, "Name") or _attr(element, "name")
        if local in _MODULES:
            module = nom or module or Path(fichier).stem
            observations.append(_observer(
                fichier, "forms_module", module, element, plages,
                {"module": module}))
        elif local == "block":
            bloc = nom
            attributs = {"module": module, "block": nom}
            table = _table_bloc(element)
            if table:
                attributs["table"] = table
            observations.append(_observer(
                fichier, "forms_block", nom, element, plages, attributs))
        elif local == "item":
            item = nom
            attributs = {"module": module, "block": bloc, "item": nom}
            colonne = _attr(element, "ColumnName") or _attr(element, "columnname")
            if colonne:
                attributs["column"] = colonne
                observations.append(_observer(
                    fichier, "forms_column", colonne, element, plages, attributs))
            observations.append(_observer(
                fichier, "forms_item", nom, element, plages, attributs))
        elif local == "trigger":
            attributs = {"module": module, "trigger": nom}
            if bloc:
                attributs["block"] = bloc
            if item:
                attributs["item"] = item
            observations.append(_observer(
                fichier, "forms_trigger", nom or "TRIGGER", element, plages,
                attributs))
            code = _texte(element)
            for table in sorted({_normalise_table(m) for m in _RE_SQL_TABLE.findall(code)}):
                observations.append(_observer(
                    fichier, "forms_sql", table, element, plages,
                    {**attributs, "table": table, "sql": code[:2000]}))
            for appel in sorted({(m[1] if isinstance(m, tuple) else m)
                                 for m in _RE_FORM_CALL.findall(code)}):
                observations.append(_observer(
                    fichier, "forms_call", appel, element, plages,
                    {**attributs, "target": appel}))
        elif local == "relation":
            attributs = {"module": module, "relation": nom}
            if bloc:
                attributs["block"] = bloc
            observations.append(_observer(
                fichier, "forms_relation", nom, element, plages, attributs))
        elif local == "lov":
            observations.append(_observer(
                fichier, "forms_lov", nom, element, plages,
                {"module": module}))
        elif local == "recordgroup":
            attributs = {"module": module}
            requete = _attr(element, "Query") or _texte_enfant(element, "Query")
            if requete:
                attributs["sql"] = requete
            observations.append(_observer(
                fichier, "forms_record_group", nom, element, plages, attributs))
        for enfant in element:
            parcourir(enfant, module, bloc, item)

    parcourir(racine, "", "", "")
    return sorted(observations, key=lambda o: (o.file, o.start, o.kind, o.symbol))


def _lire(chemin: Path) -> str:
    """Décode en UTF-8, puis cp1252, puis latin-1 : jamais d'exception d'encodage."""
    donnees = chemin.read_bytes()
    for encodage in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return donnees.decode(encodage)
        except UnicodeDecodeError:
            continue
    return donnees.decode("latin-1", errors="replace")


def _cle_fichier(racine: Path, chemin: Path) -> str:
    """Chemin stable : relatif à la racine quand il y est, absolu sinon."""
    try:
        return chemin.resolve().relative_to(racine.resolve()).as_posix()
    except (OSError, ValueError, RuntimeError):
        try:
            return chemin.resolve().as_posix()
        except (OSError, RuntimeError):
            return str(chemin)


class OracleFormsSidecar:
    """Indexe les exports XML Oracle Forms sans résoudre les entités externes."""

    provider = PROVIDER
    extensions = EXTENSIONS
    parser = PARSER
    parser_version = PARSER_VERSION
    language = LANGAGE

    def index(self, racine: str, fichiers=()) -> list[Observation]:
        fichiers = tuple(fichiers or ())
        observations = []
        for chemin in self._candidats(racine, fichiers):
            if chemin.suffix.lower() != ".xml" or not chemin.is_file():
                continue
            try:
                fichier = _cle_fichier(Path(racine), chemin)
                observations.extend(self._analyser(chemin, fichier)[0])
            except Exception:
                continue
        return sorted(observations, key=lambda o: (o.file, o.start, o.kind, o.symbol))

    def couverture(self, racine: str, fichiers=()) -> list[CouvertureFichier]:
        fichiers = tuple(fichiers or ())
        lignes = {}
        for chemin in self._candidats(racine, fichiers):
            cle = _cle_fichier(Path(racine), chemin)
            if cle in lignes:
                continue
            suffixe = chemin.suffix.lower()
            if suffixe not in SUFFIXES:
                lignes[cle] = CouvertureFichier(
                    file=cle, parser=self.parser, statut="non_supporte",
                    raison="extension non prise en charge")
            elif not chemin.is_file():
                lignes[cle] = CouvertureFichier(
                    file=cle, language=LANGAGE, parser=self.parser, statut="ignore",
                    raison="fichier introuvable ou illisible")
            elif suffixe in {".fmb", ".fmx"}:
                lignes[cle] = CouvertureFichier(
                    file=cle, language=LANGAGE, parser=self.parser, statut="partiel",
                    raison="binaire Oracle Forms non décodé")
            else:
                try:
                    observations, statut, raison = self._analyser(chemin, cle)
                except OSError as erreur:
                    lignes[cle] = CouvertureFichier(
                        file=cle, language=LANGAGE, parser=self.parser, statut="ignore",
                        raison=f"lecture impossible : {erreur}")
                except (ET.ParseError, ValueError, RuntimeError) as erreur:
                    lignes[cle] = CouvertureFichier(
                        file=cle, language=LANGAGE, parser=self.parser, statut="partiel",
                        raison=f"XML invalide ou illisible : {erreur}")
                else:
                    lignes[cle] = CouvertureFichier(
                        file=cle, language=LANGAGE, parser=self.parser,
                        statut=statut, raison=raison)
        return [lignes[cle] for cle in sorted(lignes)]

    @staticmethod
    def _candidats(racine: str, fichiers):
        base = Path(racine)
        if fichiers:
            for nom in fichiers:
                chemin = Path(nom)
                yield chemin if chemin.is_absolute() else base / chemin
            return
        try:
            for chemin in sorted(base.rglob("*")):
                if chemin.is_file() and chemin.suffix.lower() in SUFFIXES:
                    yield chemin
        except OSError:
            return

    def _analyser(self, chemin: Path, fichier: str):
        texte = _lire(chemin)
        masque = _masquer_doctypes(texte)
        racine = ET.fromstring(masque)
        observations = _extraire(
            racine, fichier, _plages(racine, _masquer_zones(masque)))
        if not observations:
            return [], "partiel", "aucun module Oracle Forms reconnu"
        return observations, "indexe", ""
