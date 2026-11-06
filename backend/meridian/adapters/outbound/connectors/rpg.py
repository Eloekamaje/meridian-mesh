"""Sidecar RPG structurel : fixed et **FREE, sans exécution ni réseau."""
from __future__ import annotations

import re
from pathlib import Path

from meridian.domain.code_index import CouvertureFichier, Observation

__all__ = ["RpgSidecar"]

PROVIDER = "rpg"
PARSER = "rpg-structural"
VERSION = "1.0"
LANGAGE = "rpg"
SUFFIXES = frozenset({".rpg", ".rpgle", ".sqlrpgle"})
PARSER_VERSION = VERSION
EXTENSIONS = tuple(sorted(SUFFIXES))

_RE_EXEC_SQL = re.compile(r"^\s*EXEC\s+SQL\b", re.I)
_RE_END_EXEC = re.compile(r"\bEND-EXEC\b", re.I)
_RE_END_PROC = re.compile(r"^(?:END-PROC|ENDPROC|PEND)\b", re.I)
_RE_END_DS = re.compile(r"^(?:END-DS|ENDDS)\b", re.I)
_RE_DCL_F = re.compile(r"\bDCL-F\s+([A-Za-z0-9_#@$/]+)", re.I)
_RE_DCL_PROC = re.compile(r"\bDCL-PROC\s+([A-Za-z0-9_#@$]+)", re.I)
_RE_DCL_S = re.compile(r"\bDCL-S\s+([A-Za-z0-9_#@$]+)", re.I)
_RE_DCL_DS = re.compile(r"\bDCL-DS\s+([A-Za-z0-9_#@$]+)", re.I)
_RE_BEGSR = re.compile(r"\bBEGSR\s+([A-Za-z0-9_#@$]+)", re.I)
_RE_CALLP = re.compile(
    r"\bCALLP\b\s*(?:\([^)]*\)\s*)?([A-Za-z0-9_#@$]+)", re.I)
_RE_EXSR = re.compile(
    r"\bEXSR\b\s*(?:\([^)]*\)\s*)?([A-Za-z0-9_#@$]+)", re.I)
_RE_CALL = re.compile(
    r"\bCALL\b\s*(?:\([^)]*\)\s*)?"
    r"(?:'([^']+)'|\"([^\"]+)\"|([A-Za-z0-9_#@$]+))", re.I)
_RE_SELECT = re.compile(r"^\s*SELECT\b", re.I)
_RE_INSERT = re.compile(r"^\s*INSERT\s+INTO\b", re.I)
_RE_DELETE_SQL = re.compile(r"^\s*DELETE\s+FROM\b", re.I)
_RE_UPDATE_SQL = re.compile(r"^\s*UPDATE\b", re.I)
_RE_SET = re.compile(r"\bSET\b", re.I)
_RE_FROM = re.compile(r"\bFROM\s+([A-Za-z0-9_#@$./]+)", re.I)
_RE_INTO = re.compile(r"\bINSERT\s+INTO\s+([A-Za-z0-9_#@$./]+)", re.I)
_RE_UPDATE = re.compile(r"^\s*UPDATE\s+([A-Za-z0-9_#@$./]+)", re.I)
_RE_DELETE = re.compile(r"^\s*DELETE\s+FROM\s+([A-Za-z0-9_#@$./]+)", re.I)
_RE_NOM = re.compile(r"^\s*([A-Za-z0-9_#@$]+)")
_RE_SPEC_FIXE = re.compile(r"^([A-Za-z0-9_#@$/]+)")
_RE_JETON = re.compile(r"[A-Za-z0-9_#@$]+")
_RE_OPERATION = {
    "CHAIN": re.compile(r"\bCHAIN\b\s*(?:\([^)]*\)\s*)?([A-Za-z0-9_#@$]+)", re.I),
    "SETLL": re.compile(r"\bSETLL\b\s*(?:\([^)]*\)\s*)?([A-Za-z0-9_#@$]+)", re.I),
    "READ": re.compile(r"\bREAD\b\s*(?:\([^)]*\)\s*)?([A-Za-z0-9_#@$]+)", re.I),
    "WRITE": re.compile(r"\bWRITE\b\s*(?:\([^)]*\)\s*)?([A-Za-z0-9_#@$]+)", re.I),
    "UPDATE": re.compile(r"\bUPDATE\b\s*(?:\([^)]*\)\s*)?([A-Za-z0-9_#@$]+)", re.I),
    "DELETE": re.compile(r"\bDELETE\b\s*(?:\([^)]*\)\s*)?([A-Za-z0-9_#@$]+)", re.I),
}


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


def _groupe(correspondance) -> str:
    for groupe in correspondance.groups():
        if groupe:
            return groupe
    return ""


def _sans_commentaires(texte: str, dans_bloc: bool = False):
    """Retire les commentaires RPG hors littéraux ; rend le texte et l'état bloc."""
    sortie = []
    i = 0
    guillemet = None
    while i < len(texte):
        if dans_bloc:
            fin = texte.find("*/", i)
            if fin < 0:
                return "".join(sortie), True
            i = fin + 2
            dans_bloc = False
            continue
        caractere = texte[i]
        if guillemet:
            sortie.append(caractere)
            if caractere == guillemet:
                if i + 1 < len(texte) and texte[i + 1] == guillemet:
                    sortie.append(texte[i + 1])
                    i += 2
                    continue
                guillemet = None
            i += 1
            continue
        if caractere in "'\"":
            guillemet = caractere
            sortie.append(caractere)
            i += 1
            continue
        if texte.startswith("//", i):
            break
        if texte.startswith("/*", i):
            dans_bloc = True
            i += 2
            continue
        if texte.startswith("--", i) and (i == 0 or texte[i - 1].isspace()):
            break
        sortie.append(caractere)
        i += 1
    return "".join(sortie), dans_bloc


def _decouper(texte: str):
    """Sépare sur les points-virgules hors littéraux."""
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
        elif caractere in "'\"":
            guillemet = caractere
        elif caractere == ";":
            morceaux.append(texte[debut:i])
            debut = i + 1
        i += 1
    return morceaux, texte[debut:]


def _est_libre(lignes) -> bool:
    for ligne in lignes:
        texte = ligne.lstrip()
        if texte.upper().startswith(("**FREE", "/FREE", "DCL-")):
            return True
        if texte and not texte.startswith("//") and not texte.startswith("*"):
            return False
    return False


def _instructions_libres(lignes):
    """Instructions **FREE : accumulation jusqu'au point-virgule."""
    resultat = []
    courant = []
    debut = None
    dans_bloc = False
    for numero, brute in enumerate(lignes, 1):
        ligne = brute.rstrip("\r\n")
        if not dans_bloc and ligne.lstrip().upper().startswith("**FREE"):
            continue
        if not dans_bloc and ligne.lstrip().startswith("*"):
            continue
        nettoyee, dans_bloc = _sans_commentaires(ligne, dans_bloc)
        if not nettoyee.strip():
            continue
        if debut is None:
            debut = numero
        courant.append(nettoyee.strip())
        morceaux, reste = _decouper(" ".join(courant))
        for morceau in morceaux:
            if morceau.strip():
                resultat.append((debut, numero, morceau.strip(), "FREE"))
            debut = numero
        if reste.strip():
            courant = [reste.strip()]
        else:
            courant = []
            debut = None
    if courant:
        texte = " ".join(courant).strip()
        if texte:
            resultat.append((debut or 0, len(lignes), texte, "FREE"))
    return resultat


def _code_fixe(ligne: str):
    """Rend (type de spécification, code) d'une ligne RPG fixe."""
    if len(ligne) <= 6:
        return "", ""
    indicateur = ligne[5]
    if indicateur == "*" or ligne[6] == "*":
        return "", ""
    spec = indicateur.upper()
    reste = ligne[6:]
    if reste[:1] in "/+":
        reste = reste[1:]
    nettoye, _ = _sans_commentaires(reste)
    return spec, nettoye.strip()


def _instructions_fixes(lignes):
    """Instructions fixes, blocs EXEC SQL fusionnés jusqu'à END-EXEC."""
    resultat = []
    i = 0
    while i < len(lignes):
        spec, texte = _code_fixe(lignes[i].rstrip("\r\n"))
        if not texte:
            i += 1
            continue
        if _RE_EXEC_SQL.match(texte):
            morceaux = [texte]
            j = i
            while (not _RE_END_EXEC.search(" ".join(morceaux))
                   and j + 1 < len(lignes)):
                j += 1
                _, suivant = _code_fixe(lignes[j].rstrip("\r\n"))
                if suivant:
                    morceaux.append(suivant)
            resultat.append((i + 1, j + 1, " ".join(morceaux), "SQL"))
            i = j + 1
            continue
        resultat.append((i + 1, i + 1, texte, spec))
        i += 1
    return resultat


def _premier_mot(texte: str) -> str:
    trouve = _RE_NOM.match(texte)
    return trouve.group(1) if trouve else ""


class RpgSidecar:
    """Index structurel RPG : observations locales, aucune exécution de programme."""

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
                        raison="aucune structure RPG reconnue")
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
        lignes = texte.splitlines()
        instructions = (_instructions_libres(lignes) if _est_libre(lignes)
                        else _instructions_fixes(lignes))
        observations = []
        proc = ""
        for debut, fin, brute, spec in instructions:
            instruction = brute.strip().rstrip(";").strip()
            if not instruction:
                continue

            if _RE_END_PROC.match(instruction):
                proc = ""
                continue
            if _RE_END_DS.match(instruction):
                continue

            if spec == "F":
                trouve = _RE_SPEC_FIXE.match(instruction)
                if trouve:
                    nom = trouve.group(1)
                    observations.append(self._obs(
                        fichier, "rpg_file", nom, debut, fin, {"file": nom}))
                continue

            if spec == "D":
                self._extraire_d(fichier, instruction, debut, fin, proc, observations)
                continue

            trouve = _RE_DCL_F.search(instruction)
            if trouve:
                nom = trouve.group(1)
                observations.append(self._obs(
                    fichier, "rpg_file", nom, debut, fin, {"file": nom}))
                continue

            trouve = _RE_DCL_PROC.search(instruction)
            if trouve:
                nom = trouve.group(1)
                proc = nom
                observations.append(self._obs(
                    fichier, "rpg_proc", nom, debut, fin, {"proc": nom}))
                continue

            trouve = _RE_DCL_S.search(instruction)
            if trouve:
                nom = trouve.group(1)
                attributs = {"proc": proc} if proc else {}
                observations.append(self._obs(
                    fichier, "rpg_var", nom, debut, fin, attributs))
                continue

            trouve = _RE_DCL_DS.search(instruction)
            if trouve:
                nom = trouve.group(1)
                attributs = {"proc": proc} if proc else {}
                observations.append(self._obs(
                    fichier, "rpg_data_structure", nom, debut, fin, attributs))
                continue

            trouve = _RE_BEGSR.search(instruction)
            if trouve:
                nom = trouve.group(1)
                observations.append(self._obs(
                    fichier, "rpg_subroutine", nom, debut, fin, {"target": nom}))
                continue

            est_sql = spec == "SQL" or bool(_RE_EXEC_SQL.match(instruction))
            if est_sql:
                corps = _RE_EXEC_SQL.sub("", instruction)
                corps = _RE_END_EXEC.sub("", corps).strip()
                observation = self._extraire_sql(
                    fichier, corps, debut, fin, proc)
                if observation:
                    observations.append(observation)
                continue

            if _RE_SELECT.match(instruction) and _RE_FROM.search(instruction):
                observation = self._extraire_sql(
                    fichier, instruction, debut, fin, proc)
                if observation:
                    observations.append(observation)
                continue
            if _RE_INSERT.match(instruction):
                observation = self._extraire_sql(
                    fichier, instruction, debut, fin, proc)
                if observation:
                    observations.append(observation)
                continue
            if _RE_DELETE_SQL.match(instruction):
                observation = self._extraire_sql(
                    fichier, instruction, debut, fin, proc)
                if observation:
                    observations.append(observation)
                continue
            if _RE_UPDATE_SQL.match(instruction) and _RE_SET.search(instruction):
                observation = self._extraire_sql(
                    fichier, instruction, debut, fin, proc)
                if observation:
                    observations.append(observation)
                continue

            trouve = _RE_CALLP.search(instruction)
            if trouve:
                nom = trouve.group(1)
                attributs = {"target": nom}
                if proc:
                    attributs["proc"] = proc
                observations.append(self._obs(
                    fichier, "rpg_call", nom, debut, fin, attributs))
                continue

            trouve = _RE_EXSR.search(instruction)
            if trouve:
                nom = trouve.group(1)
                attributs = {"target": nom}
                if proc:
                    attributs["proc"] = proc
                observations.append(self._obs(
                    fichier, "rpg_call", nom, debut, fin, attributs))
                continue

            trouve = _RE_CALL.search(instruction)
            if trouve:
                nom = _groupe(trouve)
                if nom:
                    attributs = {"target": nom}
                    if proc:
                        attributs["proc"] = proc
                    observations.append(self._obs(
                        fichier, "rpg_call", nom, debut, fin, attributs))
                continue

            for operation, motif in _RE_OPERATION.items():
                trouve = motif.search(instruction)
                if not trouve:
                    continue
                fichier_lu = trouve.group(1)
                attributs = {"operation": operation, "file": fichier_lu}
                if proc:
                    attributs["proc"] = proc
                observations.append(self._obs(
                    fichier, "rpg_operation", operation, debut, fin, attributs))
                break
        return observations

    def _extraire_d(self, fichier, instruction, debut, fin, proc, observations):
        jetons = _RE_JETON.findall(instruction)
        if len(jetons) < 2:
            return
        nom = jetons[0]
        marqueur = jetons[1].upper()
        attributs = {"proc": proc} if proc else {}
        if marqueur == "DS":
            observations.append(self._obs(
                fichier, "rpg_data_structure", nom, debut, fin, attributs))
        elif marqueur == "S":
            observations.append(self._obs(
                fichier, "rpg_var", nom, debut, fin, attributs))

    def _extraire_sql(self, fichier, texte, debut, fin, proc):
        commande = _premier_mot(texte).upper()
        if commande not in {"SELECT", "INSERT", "UPDATE", "DELETE"}:
            return None
        table = ""
        if commande == "SELECT":
            trouve = _RE_FROM.search(texte)
        elif commande == "INSERT":
            trouve = _RE_INTO.search(texte)
        elif commande == "UPDATE":
            trouve = _RE_UPDATE.search(texte)
        else:
            trouve = _RE_DELETE.search(texte)
        if trouve:
            table = _groupe(trouve)
        attributs = {"operation": commande}
        if table:
            attributs["table"] = table
        if proc:
            attributs["proc"] = proc
        return self._obs(fichier, "rpg_sql", commande, debut, fin, attributs)

    @staticmethod
    def _obs(fichier, kind, symbol, debut, fin, attributs=None) -> Observation:
        return Observation(
            provider=PROVIDER, parser=PARSER, parser_version=VERSION, file=fichier,
            language=LANGAGE, kind=kind, symbol=symbol, start=debut, end=fin,
            attributes=attributs or {})
