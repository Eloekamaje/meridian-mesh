"""Sidecar ABAP structurel : observations locales, sans exécution ni réseau."""
from __future__ import annotations

import re
from pathlib import Path

from meridian.domain.code_index import CouvertureFichier, Observation

__all__ = ["AbapSidecar"]

PROVIDER = "abap"
PARSER = "abap-structural"
VERSION = "1.0"
LANGAGE = "abap"
SUFFIXES = frozenset({".abap", ".abapinclude"})
PARSER_VERSION = VERSION
EXTENSIONS = tuple(sorted(SUFFIXES))

_RE_PROGRAM = re.compile(r"^\s*(?:REPORT|PROGRAM)\s+([A-Za-z0-9_/]+)", re.I)
_RE_CLASS = re.compile(
    r"^\s*CLASS\s+([A-Za-z0-9_/]+)\s+(DEFINITION|IMPLEMENTATION)\b", re.I)
_RE_ENDCLASS = re.compile(r"^\s*ENDCLASS\b", re.I)
_RE_METHOD = re.compile(r"^\s*METHOD\s+([A-Za-z0-9_/~]+)", re.I)
_RE_FORM = re.compile(r"^\s*FORM\s+([A-Za-z0-9_/]+)\b(.*)$", re.I)
_RE_FUNCTION = re.compile(r"^\s*FUNCTION\s+([A-Za-z0-9_/]+)\b", re.I)
_RE_INCLUDE = re.compile(r"^\s*INCLUDE\s+([A-Za-z0-9_/]+)\b", re.I)
_RE_TYPES = re.compile(r"^\s*TYPES\b\s*:?\s*(.*)$", re.I)
_RE_DATA = re.compile(
    r"^\s*DATA\b(?:\s*\(\s*([A-Za-z0-9_/~]+)\s*\))?\s*:?\s*(.*)$", re.I)
_RE_PARAMETERS = re.compile(r"^\s*PARAMETERS\b\s*:?\s*(.*)$", re.I)
_RE_CALL_FUNCTION = re.compile(
    r"^\s*CALL\s+FUNCTION\s+(?:'([^']+)'|\"([^\"]+)\"|([A-Za-z0-9_/]+))", re.I)
_RE_CALL_METHOD = re.compile(r"^\s*CALL\s+METHOD\s+([A-Za-z0-9_/~.>-]+)", re.I)
_RE_PERFORM = re.compile(r"^\s*PERFORM\s+([A-Za-z0-9_/]+)\b", re.I)
_RE_FROM = re.compile(r"\bFROM\s+([A-Za-z0-9_/.#]+)", re.I)
_RE_INTO = re.compile(r"^\s*INSERT\s+(?:INTO\s+)?([A-Za-z0-9_/.#]+)", re.I)
_RE_UPDATE = re.compile(r"^\s*UPDATE\s+([A-Za-z0-9_/.#]+)", re.I)
_RE_DELETE = re.compile(r"^\s*DELETE\s+(?:FROM\s+)?([A-Za-z0-9_/.#]+)", re.I)
_RE_IDENT = re.compile(r"^\s*([A-Za-z0-9_/~]+)")
_RE_PARAM_AFF = re.compile(r"([A-Za-z0-9_/~]+)\s*=")
_RE_MOT_CLE = re.compile(r"\b(?:USING|CHANGING|TABLES)\b", re.I)
_RE_JETON = re.compile(r"[A-Za-z0-9_/~]+")

_NON_DECLARATIONS = frozenset({"BEGIN", "END", "OF", "TYPE", "LIKE", "VALUE"})
_NON_PARAMETRES = frozenset({
    "TYPE", "LIKE", "VALUE", "OPTIONAL", "DEFAULT", "STRUCTURE", "TABLE", "OF",
})
_OPTIONS = frozenset({"TYPE", "LIKE", "VALUE", "OPTIONAL", "DEFAULT", "STRUCTURE"})


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


def _groupe(correspondance, debut=0, fin=None) -> str:
    """Premier groupe non vide d'une correspondance, sinon chaîne vide."""
    for groupe in correspondance.groups()[debut:fin]:
        if groupe:
            return groupe
    return ""


def _sans_commentaire(texte: str) -> str:
    """Coupe un commentaire ``"`` hors littéral ABAP."""
    guillemet = None
    i = 0
    while i < len(texte):
        caractere = texte[i]
        if guillemet:
            if caractere == guillemet:
                if i + 1 < len(texte) and texte[i + 1] == guillemet:
                    i += 2
                    continue
                guillemet = None
        elif caractere in "'`|":
            guillemet = caractere
        elif caractere == '"':
            return texte[:i]
        i += 1
    return texte


def _decouper(texte: str):
    """Sépare les instructions sur les points terminaux hors littéraux."""
    morceaux = []
    debut = 0
    guillemet = None
    i = 0
    while i < len(texte):
        caractere = texte[i]
        if guillemet:
            if caractere == guillemet:
                if i + 1 < len(texte) and texte[i + 1] == guillemet:
                    i += 2
                    continue
                guillemet = None
        elif caractere in "'`|":
            guillemet = caractere
        elif caractere == ".":
            avant = texte[i - 1] if i else ""
            apres = texte[i + 1] if i + 1 < len(texte) else ""
            if not (avant.isdigit() and apres.isdigit()):
                morceaux.append(texte[debut:i])
                debut = i + 1
        i += 1
    return morceaux, texte[debut:]


def _instructions(lignes):
    """Rend (début, fin, instruction) par instruction logique ABAP."""
    resultat = []
    courant = []
    debut = None
    for numero, brute in enumerate(lignes, 1):
        ligne = brute.rstrip("\r\n")
        if ligne.lstrip().startswith("*"):
            continue
        nettoyee = _sans_commentaire(ligne).strip()
        if not nettoyee:
            continue
        if debut is None:
            debut = numero
        courant.append(nettoyee)
        morceaux, reste = _decouper(" ".join(courant))
        for morceau in morceaux:
            if morceau.strip():
                resultat.append((debut, numero, morceau.strip()))
            debut = numero
        if reste.strip():
            courant = [reste.strip()]
        else:
            courant = []
            debut = None
    if courant:
        texte = " ".join(courant).strip()
        if texte:
            resultat.append((debut or 0, len(lignes), texte))
    return resultat


def _couper_virgules(texte: str):
    """Découpe une liste de déclarations sur les virgules de premier niveau."""
    morceaux = []
    tampon = []
    profondeur = 0
    guillemet = None
    for caractere in texte:
        if guillemet:
            tampon.append(caractere)
            if caractere == guillemet:
                guillemet = None
        elif caractere in "'`|":
            guillemet = caractere
            tampon.append(caractere)
        elif caractere == "(":
            profondeur += 1
            tampon.append(caractere)
        elif caractere == ")":
            profondeur = max(0, profondeur - 1)
            tampon.append(caractere)
        elif caractere == "," and profondeur == 0:
            morceaux.append("".join(tampon))
            tampon = []
        else:
            tampon.append(caractere)
    if tampon or texte.strip():
        morceaux.append("".join(tampon))
    return morceaux


def _noms_declaration(texte: str):
    """Noms déclarés par TYPES/DATA/PARAMETERS, y compris les chaînes à virgules."""
    noms = []
    for morceau in _couper_virgules(texte):
        trouve = _RE_IDENT.match(morceau)
        if not trouve:
            continue
        nom = trouve.group(1)
        if nom.upper() in _NON_DECLARATIONS or nom in noms:
            continue
        noms.append(nom)
    return noms


def _parametres_appel(texte: str):
    """Paramètres nommés d'un appel (``param = valeur``), dans l'ordre source."""
    noms = []
    for trouve in _RE_PARAM_AFF.finditer(texte):
        nom = trouve.group(1)
        if nom.upper() in _NON_PARAMETRES or nom in noms:
            continue
        noms.append(nom)
    return noms


def _parametres_forme(texte: str):
    """Paramètres d'un FORM/PERFORM : noms avant chaque TYPE/LIKE."""
    noms = []
    for mot in _RE_MOT_CLE.finditer(texte):
        suivant = _RE_MOT_CLE.search(texte, mot.end())
        fin = suivant.start() if suivant else len(texte)
        segment = texte[mot.end():fin]
        jetons = _RE_JETON.findall(segment)
        i = 0
        while i < len(jetons):
            jeton = jetons[i]
            if jeton.upper() in _OPTIONS:
                i += 2 if jeton.upper() in {"TYPE", "LIKE"} else 1
                continue
            if jeton not in noms:
                noms.append(jeton)
            i += 1
    return noms


class AbapSidecar:
    """Index structurel ABAP : aucune exécution, uniquement des observations."""

    provider = PROVIDER
    extensions = EXTENSIONS
    parser = PARSER
    parser_version = PARSER_VERSION
    language = LANGAGE

    def index(self, racine: str, fichiers=()) -> list[Observation]:
        fichiers = tuple(fichiers or ())
        observations = []
        for chemin in self._candidats(racine, fichiers):
            if chemin.suffix.lower() not in SUFFIXES or not chemin.is_file():
                continue
            try:
                texte = _lire(chemin)
                fichier = _cle_fichier(Path(racine), chemin)
                observations.extend(self._extraire(fichier, texte))
            except Exception:
                continue
        return observations

    def couverture(self, racine: str, fichiers=()) -> list[CouvertureFichier]:
        fichiers = tuple(fichiers or ())
        trouvees = {}
        for observation in self.index(racine, fichiers=fichiers):
            trouvees.setdefault(observation.file, observation)
        lignes = {}
        for chemin in self._candidats(racine, fichiers):
            cle = _cle_fichier(Path(racine), chemin)
            if cle in lignes:
                continue
            if chemin.suffix.lower() not in SUFFIXES:
                lignes[cle] = CouvertureFichier(
                    file=cle, parser=self.parser, statut="non_supporte",
                    raison="extension non prise en charge")
            elif cle in trouvees:
                lignes[cle] = CouvertureFichier(
                    file=cle, language=LANGAGE, parser=self.parser, statut="indexe")
            elif not chemin.is_file():
                lignes[cle] = CouvertureFichier(
                    file=cle, language=LANGAGE, parser=self.parser, statut="ignore",
                    raison="fichier introuvable ou illisible")
            else:
                try:
                    _lire(chemin)
                except OSError as erreur:
                    lignes[cle] = CouvertureFichier(
                        file=cle, language=LANGAGE, parser=self.parser, statut="ignore",
                        raison=f"lecture impossible : {erreur}")
                else:
                    lignes[cle] = CouvertureFichier(
                        file=cle, language=LANGAGE, parser=self.parser, statut="partiel",
                        raison="aucune structure ABAP reconnue")
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

    def _extraire(self, fichier: str, texte: str) -> list[Observation]:
        observations = []
        classe = ""
        for debut, fin, instruction in _instructions(texte.splitlines()):
            if not instruction:
                continue

            if _RE_ENDCLASS.match(instruction):
                classe = ""
                continue

            trouve = _RE_PROGRAM.match(instruction)
            if trouve:
                observations.append(self._obs(
                    fichier, "abap_program", trouve.group(1), debut, fin))
                continue

            trouve = _RE_CLASS.match(instruction)
            if trouve:
                nom = trouve.group(1)
                classe = nom
                observations.append(self._obs(
                    fichier, "abap_class", nom, debut, fin, {"class": nom}))
                continue

            trouve = _RE_METHOD.match(instruction)
            if trouve:
                nom = trouve.group(1)
                attributs = {"method": nom}
                if classe:
                    attributs["class"] = classe
                observations.append(self._obs(
                    fichier, "abap_method", nom, debut, fin, attributs))
                continue

            trouve = _RE_FORM.match(instruction)
            if trouve:
                nom = trouve.group(1)
                parametres = _parametres_forme(trouve.group(2))
                attributs = {"parameters": parametres} if parametres else {}
                observations.append(self._obs(
                    fichier, "abap_form", nom, debut, fin, attributs))
                continue

            trouve = _RE_FUNCTION.match(instruction)
            if trouve:
                nom = trouve.group(1)
                observations.append(self._obs(
                    fichier, "abap_function_module", nom, debut, fin,
                    {"function": nom}))
                continue

            trouve = _RE_INCLUDE.match(instruction)
            if trouve and trouve.group(1).upper() not in {"TYPE", "STRUCTURE"}:
                nom = trouve.group(1)
                observations.append(self._obs(
                    fichier, "abap_include", nom, debut, fin, {"include": nom}))
                continue

            trouve = _RE_TYPES.match(instruction)
            if trouve:
                for nom in _noms_declaration(trouve.group(1)):
                    attributs = {"class": classe} if classe else {}
                    observations.append(self._obs(
                        fichier, "abap_type", nom, debut, fin, attributs))
                continue

            trouve = _RE_DATA.match(instruction)
            if trouve:
                noms = ([trouve.group(1)] if trouve.group(1)
                        else _noms_declaration(trouve.group(2)))
                for nom in noms:
                    attributs = {"class": classe} if classe else {}
                    observations.append(self._obs(
                        fichier, "abap_data", nom, debut, fin, attributs))
                continue

            trouve = _RE_PARAMETERS.match(instruction)
            if trouve:
                for nom in _noms_declaration(trouve.group(1)):
                    observations.append(self._obs(
                        fichier, "abap_parameter", nom, debut, fin))
                continue

            trouve = _RE_CALL_FUNCTION.search(instruction)
            if trouve:
                nom = _groupe(trouve)
                if nom:
                    attributs = {"function": nom, "target": nom}
                    parametres = _parametres_appel(instruction[trouve.end():])
                    if parametres:
                        attributs["parameters"] = parametres
                    observations.append(self._obs(
                        fichier, "abap_call", nom, debut, fin, attributs))
                continue

            trouve = _RE_CALL_METHOD.search(instruction)
            if trouve:
                cible = trouve.group(1)
                methode = re.split(r"->|=>", cible)[-1]
                attributs = {"method": methode, "target": cible}
                parametres = _parametres_appel(instruction[trouve.end():])
                if parametres:
                    attributs["parameters"] = parametres
                observations.append(self._obs(
                    fichier, "abap_call", methode, debut, fin, attributs))
                continue

            trouve = _RE_PERFORM.search(instruction)
            if trouve:
                cible = trouve.group(1)
                attributs = {"target": cible}
                parametres = _parametres_forme(instruction[trouve.end():])
                if parametres:
                    attributs["parameters"] = parametres
                observations.append(self._obs(
                    fichier, "abap_call", cible, debut, fin, attributs))
                continue

            if re.match(r"^\s*SELECT\b", instruction, re.I):
                trouve = _RE_FROM.search(instruction)
                if trouve:
                    observations.append(self._obs(
                        fichier, "abap_sql", "SELECT", debut, fin,
                        {"table": trouve.group(1)}))
                continue

            trouve = _RE_INTO.match(instruction)
            if trouve:
                observations.append(self._obs(
                    fichier, "abap_sql", "INSERT", debut, fin,
                    {"table": trouve.group(1)}))
                continue

            trouve = _RE_UPDATE.match(instruction)
            if trouve:
                observations.append(self._obs(
                    fichier, "abap_sql", "UPDATE", debut, fin,
                    {"table": trouve.group(1)}))
                continue

            trouve = _RE_DELETE.match(instruction)
            if trouve:
                observations.append(self._obs(
                    fichier, "abap_sql", "DELETE", debut, fin,
                    {"table": trouve.group(1)}))
                continue
        return observations

    @staticmethod
    def _obs(fichier, kind, symbol, debut, fin, attributs=None) -> Observation:
        return Observation(
            provider=PROVIDER, parser=PARSER, parser_version=VERSION, file=fichier,
            language=LANGAGE, kind=kind, symbol=symbol, start=debut, end=fin,
            attributes=attributs or {})
