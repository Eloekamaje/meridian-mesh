"""Sidecar COBOL structurel : observations locales, sans compilation ni réseau."""
from __future__ import annotations

import re
from pathlib import Path

from meridian.domain.code_index import CouvertureFichier, Observation

__all__ = ["CobolSidecar"]

PROVIDER = "cobol"
PARSER = "cobol-structural"
VERSION = "1.0"
LANGAGE = "cobol"
SUFFIXES = frozenset({".cbl", ".cob", ".cpy", ".copy", ".cobol"})

_RE_DIVISION = re.compile(r"^\s*(IDENTIFICATION|ENVIRONMENT|DATA|PROCEDURE)\s+DIVISION\b", re.I)
_RE_PROGRAM = re.compile(r"\bPROGRAM(?:-|\s+)ID\b\s*\.?\s*[\"']?([A-Z0-9][\w-]*)", re.I)
_RE_SECTION = re.compile(r"^\s*([A-Z][A-Z0-9-]*)\s+SECTION\s*\.", re.I)
_RE_PARAGRAPH = re.compile(r"^\s*([A-Z][A-Z0-9_-]*)\s*\.\s*$", re.I)
_RE_COPY = re.compile(
    r"\bCOPY\s+(?:\"([^\"]+)\"|'([^']+)'|([A-Z0-9][\w$#@-]*(?:\.[A-Z0-9][\w$#@-]*)*))"
    r"(?:\s+(?:OF|IN)\s+(?:\"([^\"]+)\"|'([^']+)'|([A-Z0-9][\w$#@-]*(?:\.[A-Z0-9][\w$#@-]*)*)))?",
    re.I,
)
_RE_CALL = re.compile(r"\bCALL\s+(?:\"([^\"]+)\"|'([^']+)'|([A-Z0-9][\w-]*))", re.I)
_RE_PERFORM = re.compile(r"\bPERFORM\s+([A-Z][\w-]*)", re.I)
_RE_EXEC = re.compile(r"\bEXEC\s+(CICS|SQL)\b(.*)", re.I)
_RE_END_EXEC = re.compile(r"\bEND-EXEC\b", re.I)
_RE_CICS_PROGRAM = re.compile(
    r"\bPROGRAM\s*\(\s*(?:\"([^\"]+)\"|'([^']+)'|([A-Z0-9][\w.$#@-]*))\s*\)", re.I
)
_RE_FD = re.compile(r"^\s*FD\s+([A-Z0-9][\w-]*)", re.I)
_RE_SELECT = re.compile(r"^\s*SELECT\s+(?:OPTIONAL\s+)?([A-Z0-9][\w-]*)", re.I)
_RE_ASSIGN = re.compile(
    r"\bASSIGN\s+(?:TO|USING)\s+(?:\"([^\"]+)\"|'([^']+)'|([A-Z0-9][\w$#@-]*(?:\.[A-Z0-9][\w$#@-]*)*))",
    re.I,
)
_RE_LEVEL = re.compile(r"^\s*(\d{1,2})\s+([A-Z][A-Z0-9_-]*)\b(.*)$", re.I)
_RE_PIC = re.compile(r"\bPIC(?:TURE)?\b(?:\s+IS)?\s+([^\s.]+)", re.I)
_RE_USAGE = re.compile(
    r"\b(COMP-3|COMP-4|COMPUTATIONAL-3|COMPUTATIONAL-4|PACKED-DECIMAL|COMP-1|COMP-2"
    r"|COMPUTATIONAL-1|COMPUTATIONAL-2|COMP|COMPUTATIONAL|BINARY|DISPLAY)\b",
    re.I,
)
_RE_VALUE = re.compile(r"\bVALUES?\b(?:\s+(?:IS|ARE))?\s+(.+)$", re.I)

_NIVEAUX = frozenset(range(1, 50)) | {66, 77, 78, 88}
_NON_PARAGRAPHES = frozenset({
    "GOBACK", "CONTINUE", "STOP", "ELSE", "EJECT", "SKIP1", "SKIP2", "SKIP3", "TITLE",
    "END-IF", "END-PERFORM", "END-EVALUATE", "END-READ", "END-WRITE", "END-REWRITE",
    "END-DELETE", "END-START", "END-CALL", "END-COMPUTE", "END-EXEC", "END-PROGRAM",
    "END-SEARCH", "END-STRING", "END-UNSTRING", "END-ADD", "END-SUBTRACT",
    "END-MULTIPLY", "END-DIVIDE", "END-ACCEPT", "END-DISPLAY", "END-RETURN",
})
_PERFORM_SANS_CIBLE = frozenset({
    "VARYING", "UNTIL", "WITH", "TEST", "TIMES", "WHEN", "THROUGH", "THRU", "FOREVER",
})
_DEVICES = frozenset({
    "DISK", "TAPE", "PRINTER", "CONSOLE", "CARD-READER", "SYSIN", "SYSOUT",
    "INPUT", "OUTPUT", "RANDOM", "DYNAMIC", "EXTERNAL",
})


def _lire(chemin: Path) -> str:
    """Décode en UTF-8, puis cp1252, puis latin-1 : aucune lecture ne lève pour l'encodage."""
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


def _detecter_format(lignes) -> str:
    """Choisit fixe ou libre : marqueurs de commentaire d'abord, puis indentation du code."""
    for ligne in lignes:
        texte = ligne.strip()
        if texte.startswith("*>"):
            return "libre"
        if ligne.startswith("*") and not ligne.startswith("**"):
            return "libre"
    for ligne in lignes:
        if len(ligne) > 6 and ligne[6] in "*/":
            prefixe = ligne[:6].strip()
            if not prefixe or prefixe.isdigit():
                return "fixe"
        if len(ligne) > 6 and ligne[6] == "-" and not ligne[:6].strip():
            return "fixe"
        if len(ligne) > 6 and ligne[:6].strip().isdigit():
            return "fixe"
    retraits = []
    for ligne in lignes:
        texte = ligne.strip()
        if not texte or texte.startswith("*"):
            continue
        retraits.append(len(ligne) - len(ligne.lstrip(" ")))
    if retraits and sorted(retraits)[len(retraits) // 2] >= 6:
        return "fixe"
    return "libre"


def _sans_commentaire_libre(texte: str) -> str:
    """Coupe un commentaire ``*>`` hors littéral."""
    guillemet = None
    i = 0
    while i < len(texte) - 1:
        caractere = texte[i]
        if guillemet:
            if caractere == guillemet:
                if i + 1 < len(texte) and texte[i + 1] == guillemet:
                    i += 2
                    continue
                guillemet = None
        elif caractere in "'\"":
            guillemet = caractere
        elif caractere == "*" and texte[i + 1] == ">":
            return texte[:i]
        i += 1
    return texte


def _lignes_code(lignes, format_: str):
    """Rend (début, fin, code) par ligne logique, continuations fixes fusionnées."""
    resultat = []
    for numero, ligne in enumerate(lignes, 1):
        ligne = ligne.rstrip("\r\n")
        if format_ == "fixe":
            if len(ligne) <= 6:
                continue
            indicateur = ligne[6]
            if indicateur in "*/":
                continue
            texte = ligne[7:72]
            if indicateur == "-" and resultat:
                debut, _, precedent = resultat[-1]
                resultat[-1] = (debut, numero, (precedent + " " + texte).strip())
                continue
            if texte.strip():
                resultat.append((numero, numero, texte.rstrip()))
        else:
            texte = ligne.strip()
            if not texte or texte.startswith("*>"):
                continue
            if texte.startswith("*") and not texte.startswith("**"):
                continue
            texte = _sans_commentaire_libre(texte).strip()
            if texte:
                resultat.append((numero, numero, texte))
    return resultat


def _premier_mot(texte: str) -> str:
    return texte.strip().split(None, 1)[0] if texte.strip() else ""


def _groupe(correspondance, debut=0, fin=None) -> str:
    """Premier groupe non vide d'une correspondance, sinon chaîne vide."""
    for groupe in correspondance.groups()[debut:fin]:
        if groupe:
            return groupe
    return ""


def _pic_longueur(pic: str, usage: str):
    """Longueur de stockage déduite du PIC et de l'USAGE, ou None si indéterminable."""
    expression = re.sub(r"\s+", "", pic.upper())
    positions = 0
    chiffres = 0
    i = 0
    while i < len(expression):
        caractere = expression[i]
        if caractere in "XAN9":
            repetition = 1
            if i + 1 < len(expression) and expression[i + 1] == "(":
                fin = expression.find(")", i + 2)
                if fin > 0:
                    try:
                        repetition = int(expression[i + 2:fin])
                    except ValueError:
                        repetition = 1
                    i = fin
            positions += repetition * (2 if caractere == "N" else 1)
            if caractere == "9":
                chiffres += repetition
        elif expression.startswith("CR", i) or expression.startswith("DB", i):
            positions += 2
            i += 1
        elif caractere in "ZV*,+-./B0$":
            positions += 1
        i += 1
    if not positions:
        return None
    usage = usage.upper()
    if usage in {"COMP-3", "COMPUTATIONAL-3", "PACKED-DECIMAL"}:
        return chiffres // 2 + 1 if chiffres else positions // 2 + 1
    if usage in {"COMP", "COMPUTATIONAL", "COMP-4", "COMPUTATIONAL-4", "BINARY"}:
        if chiffres <= 4:
            return 2
        if chiffres <= 9:
            return 4
        return 8
    if usage in {"COMP-1", "COMPUTATIONAL-1"}:
        return 4
    if usage in {"COMP-2", "COMPUTATIONAL-2"}:
        return 8
    return positions


def _valeurs(texte: str):
    """Valeurs d'une condition 88 : littéraux cités, sinon jetons simples."""
    trouve = _RE_VALUE.search(texte)
    if not trouve:
        return []
    brut = trouve.group(1).strip().rstrip(".")
    citees = re.findall(r"'([^']*)'|\"([^\"]*)\"", brut)
    valeurs = [a or b for a, b in citees]
    if valeurs:
        return valeurs
    jetons = [j.strip(" .,") for j in re.split(r"\s+", brut) if j.strip(" .,")]
    return [j for j in jetons if j.upper() not in {"THRU", "THROUGH", "IS", "ARE", "VALUE", "VALUES"}]


def _table_sql(commande: str, corps: str):
    motifs = {
        "SELECT": r"\bFROM\s+([A-Z0-9][\w$#@-]*(?:\.[A-Z0-9][\w$#@-]*)*)",
        "DELETE": r"\bFROM\s+([A-Z0-9][\w$#@-]*(?:\.[A-Z0-9][\w$#@-]*)*)",
        "INSERT": r"\bINTO\s+([A-Z0-9][\w$#@-]*(?:\.[A-Z0-9][\w$#@-]*)*)",
        "UPDATE": r"\bUPDATE\s+([A-Z0-9][\w$#@-]*(?:\.[A-Z0-9][\w$#@-]*)*)",
        "MERGE": r"\bINTO\s+([A-Z0-9][\w$#@-]*(?:\.[A-Z0-9][\w$#@-]*)*)",
    }
    motif = motifs.get(commande)
    if not motif:
        return ""
    trouve = re.search(motif, corps, re.I)
    return trouve.group(1) if trouve else ""


class CobolSidecar:
    """Index structurel COBOL/JCL-free : aucune exécution, uniquement des observations."""

    provider = PROVIDER
    extensions = tuple(SUFFIXES)
    parser = PARSER
    parser_version = VERSION
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
                        raison="aucune structure COBOL reconnue")
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
        code = _lignes_code(lignes, _detecter_format(lignes))
        observations = []
        division = ""
        i = 0
        while i < len(code):
            debut, fin, brut = code[i]
            texte_code = brut.strip()
            if not texte_code:
                i += 1
                continue
            exec_ = _RE_EXEC.search(texte_code)
            if exec_:
                langue = exec_.group(1).upper()
                morceaux = [exec_.group(2)]
                j = i
                while not _RE_END_EXEC.search(" ".join(morceaux)) and j + 1 < len(code) and j - i < 200:
                    suivant = code[j + 1][2].strip()
                    if _RE_DIVISION.match(suivant) or _RE_PROGRAM.search(suivant):
                        break
                    j += 1
                    morceaux.append(suivant)
                contenu = " ".join(morceaux)
                fin_bloc = code[j][1]
                if langue == "CICS":
                    commande = _premier_mot(contenu).upper()
                    if commande and commande != "END-EXEC":
                        attributs = {"command": commande}
                        programme = _RE_CICS_PROGRAM.search(contenu)
                        cible = _groupe(programme) if programme else ""
                        if cible:
                            attributs.update({"target": cible, "program": cible})
                        observations.append(self._obs(
                            fichier, "cobol_cics", commande, debut, fin_bloc, attributs))
                else:
                    corps = _RE_END_EXEC.sub("", contenu).strip()
                    commande = _premier_mot(corps).upper()
                    if commande:
                        attributs = {"command": commande}
                        table = _table_sql(commande, corps)
                        if table:
                            attributs["table"] = table
                        observations.append(self._obs(
                            fichier, "cobol_sql", commande, debut, fin_bloc, attributs))
                i = j + 1
                continue

            division_trouvee = _RE_DIVISION.match(texte_code)
            if division_trouvee:
                nom = division_trouvee.group(1).upper()
                division = nom
                observations.append(self._obs(
                    fichier, "cobol_division", f"{nom} DIVISION", debut, fin, {"division": nom}))
                i += 1
                continue

            programme = _RE_PROGRAM.search(texte_code)
            if programme:
                observations.append(self._obs(
                    fichier, "cobol_program", programme.group(1), debut, fin))
                i += 1
                continue

            section = _RE_SECTION.match(texte_code)
            if section:
                nom = section.group(1).upper()
                observations.append(self._obs(
                    fichier, "cobol_section", nom, debut, fin, {"section": nom}))
                i += 1
                continue

            fd = _RE_FD.match(texte_code)
            if fd:
                nom = fd.group(1)
                observations.append(self._obs(
                    fichier, "cobol_file", nom, debut, fin, {"fd": nom}))
                i += 1
                continue

            selection = _RE_SELECT.match(texte_code)
            if selection:
                nom = selection.group(1)
                bloc = [texte_code]
                j = i
                while not bloc[-1].rstrip().endswith(".") and j + 1 < len(code) and j - i < 20:
                    j += 1
                    bloc.append(code[j][2].strip())
                joint = " ".join(bloc)
                attributs = {"select": nom}
                assignation = _RE_ASSIGN.search(joint)
                cible = _groupe(assignation) if assignation else ""
                if cible:
                    attributs["assign"] = cible
                    if (assignation.group(1) or assignation.group(2)
                            or cible.upper() not in _DEVICES):
                        attributs["dataset"] = cible
                observations.append(self._obs(
                    fichier, "cobol_file", nom, debut, code[j][1], attributs))
                i += 1
                continue

            copie = _RE_COPY.search(texte_code)
            if copie:
                nom = _groupe(copie, 0, 3)
                if nom:
                    attributs = {"copybook": nom}
                    bibliotheque = _groupe(copie, 3)
                    if bibliotheque:
                        attributs["library"] = bibliotheque
                    observations.append(self._obs(
                        fichier, "cobol_copy", nom, debut, fin, attributs))
                i += 1
                continue

            appel = _RE_CALL.search(texte_code)
            if appel:
                nom = _groupe(appel)
                if nom:
                    attributs = {"target": nom}
                    if appel.group(1) or appel.group(2):
                        attributs["program"] = nom
                    observations.append(self._obs(
                        fichier, "cobol_call", nom, debut, fin, attributs))
                i += 1
                continue

            perform = _RE_PERFORM.search(texte_code)
            if perform:
                cible = perform.group(1)
                if cible.upper() not in _PERFORM_SANS_CIBLE:
                    observations.append(self._obs(
                        fichier, "cobol_perform", cible, debut, fin, {"target": cible}))
                i += 1
                continue

            niveau = _RE_LEVEL.match(texte_code)
            if niveau and int(niveau.group(1)) in _NIVEAUX and niveau.group(2).upper() != "FILLER":
                num = int(niveau.group(1))
                nom = niveau.group(2)
                reste = niveau.group(3)
                attributs = {"level": f"{num:02d}"}
                if num == 88:
                    valeurs = _valeurs(reste)
                    if valeurs:
                        attributs["values"] = valeurs
                    observations.append(self._obs(
                        fichier, "cobol_condition", nom, debut, fin, attributs))
                else:
                    pic = _RE_PIC.search(reste)
                    usage = _RE_USAGE.search(reste)
                    if pic:
                        attributs["type"] = pic.group(1)
                    if usage:
                        attributs["usage"] = usage.group(1).upper()
                    if pic:
                        longueur = _pic_longueur(pic.group(1), usage.group(1) if usage else "")
                        if longueur is not None:
                            attributs["length"] = longueur
                    observations.append(self._obs(
                        fichier, "cobol_field", nom, debut, fin, attributs))
                i += 1
                continue

            paragraphe = _RE_PARAGRAPH.match(texte_code)
            if division == "PROCEDURE" and paragraphe and paragraphe.group(1).upper() not in _NON_PARAGRAPHES:
                nom = paragraphe.group(1)
                observations.append(self._obs(
                    fichier, "cobol_paragraph", nom, debut, fin, {"paragraph": nom}))
            i += 1
        return observations

    @staticmethod
    def _obs(fichier, kind, symbol, debut, fin, attributs=None) -> Observation:
        return Observation(
            provider=PROVIDER, parser=PARSER, parser_version=VERSION, file=fichier,
            language=LANGAGE, kind=kind, symbol=symbol, start=debut, end=fin,
            attributes=attributs or {})
