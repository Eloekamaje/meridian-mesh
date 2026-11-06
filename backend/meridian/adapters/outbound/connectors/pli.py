"""Sidecar PL/I structurel : observations locales, sans exécution ni réseau."""
from __future__ import annotations

import re
from pathlib import Path

from meridian.domain.code_index import CouvertureFichier, Observation

__all__ = ["PliSidecar"]

PROVIDER = "pli"
PARSER = "pli-structural"
VERSION = "1.0"
LANGAGE = "pli"
SUFFIXES = frozenset({".pli", ".pl1", ".inc"})
PARSER_VERSION = VERSION
EXTENSIONS = tuple(sorted(SUFFIXES))

_RE_LABEL = re.compile(r"^\s*([A-Za-z_][\w$#@]*|\d+)\s*:\s*(.*)$", re.S)
_RE_END = re.compile(r"^END\b\s*([A-Za-z_][\w$#@]*)?", re.I)
_RE_PROC = re.compile(r"^(?:PROC|PROCEDURE)\b(.*)$", re.I | re.S)
_RE_ENTRY = re.compile(r"^ENTRY\b(.*)$", re.I | re.S)
_RE_DECLARE = re.compile(r"^(?:DECLARE|DCL)\b(.*)$", re.I | re.S)
_RE_INCLUDE = re.compile(r"^%INCLUDE\b(.*)$", re.I | re.S)
_RE_EXEC_SQL = re.compile(r"^EXEC\s+SQL\b(.*)$", re.I | re.S)
_RE_RETURN = re.compile(r"^RETURN\b", re.I)
_RE_CALL = re.compile(
    r"^CALL\s+(?:\(\s*)?(?:'([^']+)'|\"([^\"]+)\"|([A-Za-z_][\w$#@.]*))", re.I)
_RE_SELECT = re.compile(r"^SELECT\b", re.I)
_RE_FROM = re.compile(r"\bFROM\s+([A-Za-z0-9_$#@.\"]+)", re.I)
_RE_INTO = re.compile(r"\bINTO\s+([A-Za-z0-9_$#@.\"]+)", re.I)
_RE_INSERT = re.compile(r"\bINSERT\s+INTO\s+([A-Za-z0-9_$#@.\"]+)", re.I)
_RE_UPDATE = re.compile(r"^\s*UPDATE\s+([A-Za-z0-9_$#@.\"]+)", re.I)
_RE_DELETE = re.compile(r"\bDELETE\s+FROM\s+([A-Za-z0-9_$#@.\"]+)", re.I)
_RE_TABLE = re.compile(r"\b(?:FROM|INTO|UPDATE)\s+([A-Za-z0-9_$#@.\"]+)", re.I)
_RE_IDENT = re.compile(r"^([A-Za-z_][\w$#@]*)")
_RE_NIVEAU = re.compile(r"^(\d{1,2})\s+(.*)$", re.S)
_RE_INCLUDE_FILE = re.compile(r"^%INCLUDE\s+FILE\s*\(\s*([^)]+?)\s*\)", re.I)
_RE_INCLUDE_LIB = re.compile(
    r"^%INCLUDE\s+([A-Za-z0-9_$#@.-]+)\s*\(\s*([^)]+?)\s*\)", re.I)
_RE_INCLUDE_SIMPLE = re.compile(
    r"^%INCLUDE\s+(?:'([^']+)'|\"([^\"]+)\"|([A-Za-z0-9_$#@./\\-]+))", re.I)
_RE_OUVRE_BLOC = re.compile(r"^(?:DO|SELECT|BEGIN)\b", re.I)
_RE_THEN_DO = re.compile(r"\bTHEN\s+DO\b", re.I)
_RE_TYPE_FIN = re.compile(
    r"\b(?:INITIAL|INIT|VALUE|STATIC|EXTERNAL|BASED|CONTROLLED|AUTOMATIC|"
    r"PARAMETER|DEFINED|GENERIC|RETURNS|OPTIONS|DIMENSION|LIKE)\b", re.I)


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


def _sans_commentaires(texte: str, dans_bloc: bool = False) -> tuple[str, bool]:
    """Retire les commentaires PL/I hors littéraux ; rend le texte et l'état bloc."""
    sortie = []
    i = 0
    while i < len(texte):
        if dans_bloc:
            fin = texte.find("*/", i)
            if fin < 0:
                return "".join(sortie), True
            i = fin + 2
            dans_bloc = False
            continue
        if texte.startswith("/*", i):
            dans_bloc = True
            i += 2
            continue
        if texte.startswith("//", i):
            break
        caractere = texte[i]
        if caractere in "'\"":
            guillemet = caractere
            sortie.append(caractere)
            i += 1
            while i < len(texte):
                sortie.append(texte[i])
                if texte[i] == guillemet:
                    if i + 1 < len(texte) and texte[i + 1] == guillemet:
                        sortie.append(texte[i + 1])
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            continue
        sortie.append(caractere)
        i += 1
    return "".join(sortie), dans_bloc


def _decouper(texte: str):
    """Sépare les instructions sur les points-virgules hors littéraux."""
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


def _instructions(lignes):
    """Rend (début, fin, instruction) par instruction logique PL/I."""
    resultat = []
    courant = []
    debut = None
    dans_bloc = False
    for numero, brute in enumerate(lignes, 1):
        ligne = brute.rstrip("\r\n")
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
    """Découpe une liste sur les virgules de premier niveau."""
    morceaux = []
    tampon = []
    profondeur = 0
    guillemet = None
    for caractere in texte:
        if guillemet:
            tampon.append(caractere)
            if caractere == guillemet:
                guillemet = None
        elif caractere in "'\"":
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


def _sans_dimension(texte: str) -> str:
    """Retire une dimension ``(n)`` après un nom de variable."""
    texte = texte.lstrip()
    if not texte.startswith("("):
        return texte
    profondeur = 0
    guillemet = None
    for i, caractere in enumerate(texte):
        if guillemet:
            if caractere == guillemet:
                guillemet = None
        elif caractere in "'\"":
            guillemet = caractere
        elif caractere == "(":
            profondeur += 1
        elif caractere == ")":
            profondeur -= 1
            if profondeur == 0:
                return texte[i + 1:].lstrip()
    return texte


def _type_declaration(reste: str) -> str:
    """Type déclaré, sans les options qui suivent (INIT, VALUE, STATIC, ...)."""
    texte = " ".join(str(reste or "").split()).strip()
    if not texte:
        return ""
    trouve = _RE_TYPE_FIN.search(texte)
    if trouve and trouve.start() > 0:
        texte = texte[:trouve.start()].strip()
    return texte


def _declarations(reste: str):
    """Rend (nom, type) pour chaque nom d'une instruction DECLARE/DCL."""
    declarations = []
    for morceau in _couper_virgules(reste):
        texte = morceau.strip()
        if not texte:
            continue
        if texte.startswith("("):
            profondeur = 0
            fermeture = None
            for i, caractere in enumerate(texte):
                if caractere == "(":
                    profondeur += 1
                elif caractere == ")":
                    profondeur -= 1
                    if profondeur == 0:
                        fermeture = i
                        break
            if fermeture is None:
                continue
            noms = [nom.strip() for nom in _couper_virgules(texte[1:fermeture])
                    if nom.strip()]
            type_ = _type_declaration(texte[fermeture + 1:])
        else:
            niveau = _RE_NIVEAU.match(texte)
            if niveau:
                texte = niveau.group(2).strip()
            identifiant = _RE_IDENT.match(texte)
            if not identifiant:
                continue
            noms = [identifiant.group(1)]
            type_ = _type_declaration(_sans_dimension(texte[identifiant.end():]))
        for nom in noms:
            nom = nom.split("(")[0].strip()
            if nom:
                declarations.append((nom, type_))
    return declarations


def _cible_include(reste: str) -> str:
    """Cible de %INCLUDE, qu'elle soit simple, FILE(...) ou bibliothèque(...)."""
    texte = str(reste or "").strip().rstrip(";").strip()
    for motif in (_RE_INCLUDE_FILE, _RE_INCLUDE_LIB):
        trouve = motif.match(texte)
        if trouve:
            cible = trouve.group(trouve.lastindex)
            return cible.strip().strip("'\"")
    trouve = _RE_INCLUDE_SIMPLE.match(texte)
    return _groupe(trouve).strip().strip("'\"") if trouve else ""


def _table_sql(commande: str, corps: str) -> str:
    """Table lue ou écrite par une instruction SQL, si elle est explicite."""
    if commande == "SELECT":
        trouve = _RE_FROM.search(corps)
    elif commande == "INSERT":
        trouve = _RE_INSERT.search(corps)
    elif commande == "UPDATE":
        trouve = _RE_UPDATE.search(corps)
    elif commande == "DELETE":
        trouve = _RE_DELETE.search(corps)
    elif commande == "MERGE":
        trouve = _RE_INTO.search(corps)
    else:
        trouve = _RE_TABLE.search(corps)
    return trouve.group(1) if trouve else ""


class PliSidecar:
    """Index structurel PL/I : aucune exécution, uniquement des observations."""

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
                        raison="aucune structure PL/I reconnue")
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
        procedures = []
        proc = ""
        profondeur_bloc = 0
        for debut, fin, instruction in _instructions(texte.splitlines()):
            brute = instruction.strip()
            if not brute:
                continue

            etiquette = ""
            reste = brute
            trouve_etiquette = _RE_LABEL.match(brute)
            if trouve_etiquette:
                etiquette = trouve_etiquette.group(1)
                reste = trouve_etiquette.group(2).strip()

            if _RE_END.match(reste):
                nom_fin = _RE_END.match(reste).group(1) or ""
                if nom_fin:
                    if procedures and procedures[-1].upper() == nom_fin.upper():
                        procedures.pop()
                        proc = procedures[-1] if procedures else ""
                    elif any(nom.upper() == nom_fin.upper() for nom in procedures):
                        while procedures and procedures[-1].upper() != nom_fin.upper():
                            procedures.pop()
                        if procedures:
                            procedures.pop()
                        proc = procedures[-1] if procedures else ""
                    elif profondeur_bloc > 0:
                        profondeur_bloc -= 1
                elif profondeur_bloc > 0:
                    profondeur_bloc -= 1
                elif procedures:
                    procedures.pop()
                    proc = procedures[-1] if procedures else ""
                continue

            if _RE_PROC.match(reste):
                if etiquette:
                    procedures.append(etiquette)
                    proc = etiquette
                    observations.append(self._obs(
                        fichier, "pli_proc", etiquette, debut, fin, {"proc": etiquette}))
                continue

            if _RE_ENTRY.match(reste):
                nom_entree = etiquette or proc
                if nom_entree:
                    observations.append(self._obs(
                        fichier, "pli_entry", nom_entree, debut, fin,
                        {"proc": nom_entree}))
                continue

            if etiquette:
                attributs = {"proc": proc} if proc else {}
                observations.append(self._obs(
                    fichier, "pli_label", etiquette, debut, fin, attributs))

            if _RE_DECLARE.match(reste):
                trouve = _RE_DECLARE.match(reste)
                for nom, type_ in _declarations(trouve.group(1)):
                    attributs = {"type": type_} if type_ else {}
                    if proc:
                        attributs["proc"] = proc
                    observations.append(self._obs(
                        fichier, "pli_var", nom, debut, fin, attributs))
                continue

            if _RE_INCLUDE.match(reste):
                cible = _cible_include(reste)
                if cible:
                    attributs = {"include": cible}
                    if proc:
                        attributs["proc"] = proc
                    observations.append(self._obs(
                        fichier, "pli_include", cible, debut, fin, attributs))
                continue

            trouve_sql = _RE_EXEC_SQL.match(reste)
            if trouve_sql:
                corps = trouve_sql.group(1).strip()
                self._ajouter_sql(
                    fichier, corps, debut, fin, proc, observations)
                continue

            trouve_select = _RE_SELECT.match(reste)
            if trouve_select and _RE_INTO.search(reste):
                self._ajouter_sql(
                    fichier, reste, debut, fin, proc, observations)
                continue

            trouve_appel = _RE_CALL.match(reste)
            if trouve_appel:
                cible = _groupe(trouve_appel)
                if cible:
                    attributs = {"target": cible}
                    if proc:
                        attributs["proc"] = proc
                    observations.append(self._obs(
                        fichier, "pli_call", cible, debut, fin, attributs))
                continue

            if _RE_RETURN.match(reste) and not etiquette:
                attributs = {"proc": proc} if proc else {}
                observations.append(self._obs(
                    fichier, "pli_label", "RETURN", debut, fin, attributs))
                continue

            if _RE_OUVRE_BLOC.match(reste) or _RE_THEN_DO.search(reste):
                profondeur_bloc += 1
        return observations

    def _ajouter_sql(self, fichier, corps, debut, fin, proc, observations):
        texte = " ".join(str(corps or "").split()).strip().rstrip(";").strip()
        if not texte:
            return
        commande = texte.split(None, 1)[0].upper()
        if not commande.isalpha():
            return
        attributs = {}
        table = _table_sql(commande, texte)
        if table:
            attributs["table"] = table
        if proc:
            attributs["proc"] = proc
        observations.append(self._obs(
            fichier, "pli_sql", commande, debut, fin, attributs))

    @staticmethod
    def _obs(fichier, kind, symbol, debut, fin, attributs=None) -> Observation:
        return Observation(
            provider=PROVIDER, parser=PARSER, parser_version=VERSION, file=fichier,
            language=LANGAGE, kind=kind, symbol=symbol, start=debut, end=fin,
            attributes=attributs or {})
