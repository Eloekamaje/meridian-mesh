"""Sidecar PowerBuilder structurel : extraction PBL locale, sans runtime propriétaire.

L'analyse binaire des bibliothèques ``.pbl`` adapte le format documenté et le code
de `powerbuilder-pbl-dump <https://github.com/gmai2006/powerbuilder-pbl-dump>`_
(pbl_util.py, pbl_extractor.py, pbl-spec.txt), publié sous licence MIT :

MIT License

Copyright (c) 2020 gmai2006

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
from __future__ import annotations

import re
import struct
from pathlib import Path

from meridian.domain.code_index import CouvertureFichier, Observation

__all__ = ["PowerBuilderSidecar", "extraire_pbl"]

PROVIDER = "powerbuilder"
PARSER = "powerbuilder-structural"
VERSION = "1.0"
LANGAGE = "powerbuilder"
SUFFIXES = frozenset({
    ".sra", ".srd", ".srf", ".srj", ".srm", ".srp", ".srq", ".srs",
    ".sru", ".srw", ".srx", ".pbl",
})
SOURCES = frozenset(SUFFIXES - {".pbl"})
PARSER_VERSION = VERSION
EXTENSIONS = tuple(sorted(SUFFIXES))

BLOC_PBL = 512
BLOC_PBL_UNICODE = 1024
TAILLE_NOD = 3072
ENTREE_PBL = 24
ENTREE_PBL_UNICODE = 28
DONNEES_PBL = BLOC_PBL - 10


class _PblIllisible(Exception):
    """Erreur interne d'analyse PBL, convertie en résultat structuré."""


def _u16(donnees: bytes, offset: int) -> int:
    if offset < 0 or offset + 2 > len(donnees):
        raise _PblIllisible("champ 16 bits hors bornes")
    return struct.unpack_from("<H", donnees, offset)[0]


def _u32(donnees: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(donnees):
        raise _PblIllisible("champ 32 bits hors bornes")
    return struct.unpack_from("<I", donnees, offset)[0]


def _entete_pbl(donnees: bytes) -> tuple[bool, int]:
    """Rend (unicode, taille de l'en-tête) après validation des signatures."""
    if len(donnees) < BLOC_PBL:
        raise _PblIllisible("fichier trop court pour un en-tête PBL")
    if donnees[:4] != b"HDR*":
        raise _PblIllisible("signature HDR* absente")
    prefixe = donnees[4:32]
    if prefixe.startswith("PowerBuilder".encode("utf-16le")):
        nom = prefixe.decode("utf-16le", "replace").split("\x00", 1)[0]
        if not nom.startswith("PowerBuilder"):
            raise _PblIllisible("signature PowerBuilder Unicode absente")
        return True, BLOC_PBL_UNICODE
    if donnees[4:16].startswith(b"PowerBuilder"):
        return False, BLOC_PBL
    raise _PblIllisible("signature PowerBuilder absente")


def _racine_pbl(donnees: bytes, taille_entete: int) -> int:
    racine = taille_entete + BLOC_PBL
    if donnees[racine:racine + 4] == b"NOD*":
        return racine
    limite = min(len(donnees), taille_entete + 64 * BLOC_PBL)
    for offset in range(taille_entete, limite, BLOC_PBL):
        if donnees[offset:offset + 4] == b"NOD*":
            return offset
    raise _PblIllisible("premier bloc NOD* introuvable")


def _noeuds_pbl(donnees: bytes, racine: int, unicode: bool):
    """Parcourt l'arbre NOD* et rend les entrées ENT* et les erreurs de structure."""
    entrees = []
    erreurs = []
    vus = set()
    pile = [racine]
    fixe = ENTREE_PBL_UNICODE if unicode else ENTREE_PBL
    while pile:
        offset = pile.pop()
        if offset <= 0 or offset in vus:
            continue
        vus.add(offset)
        if offset + TAILLE_NOD > len(donnees):
            erreurs.append(f"bloc NOD* tronqué à l'offset {offset}")
            continue
        bloc = donnees[offset:offset + TAILLE_NOD]
        if bloc[:4] != b"NOD*":
            erreurs.append(f"signature NOD* absente à l'offset {offset}")
            continue
        gauche = _u32(bloc, 4)
        droite = _u32(bloc, 12)
        nombre = _u16(bloc, 20)
        position = 32
        for index in range(nombre):
            if (position + fixe > len(bloc)
                    or bloc[position:position + 4] != b"ENT*"):
                erreurs.append(
                    f"entrée {index} illisible dans le bloc NOD* à l'offset {offset}")
                break
            taille_nom = _u16(bloc, position + fixe - 2)
            if taille_nom <= 0 or position + fixe + taille_nom > len(bloc):
                erreurs.append(
                    f"nom d'entrée {index} invalide dans le bloc NOD* à l'offset {offset}")
                break
            brut_nom = bloc[position + fixe:position + fixe + taille_nom]
            if unicode:
                nom = brut_nom.decode("utf-16le", "replace")
                donnees_objet = _u32(bloc, position + 12)
                taille_objet = _u32(bloc, position + 16)
                commentaire = _u16(bloc, position + 24)
            else:
                nom = brut_nom.decode("cp1252", "replace")
                donnees_objet = _u32(bloc, position + 8)
                taille_objet = _u32(bloc, position + 12)
                commentaire = _u16(bloc, position + 20)
            entrees.append({
                "nom": nom.rstrip("\x00"),
                "donnees": donnees_objet,
                "taille": taille_objet,
                "commentaire": commentaire,
            })
            position += fixe + taille_nom
        for enfant in (gauche, droite):
            if enfant:
                pile.append(enfant)
    return entrees, erreurs


def _blocs_donnees_pbl(donnees: bytes, offset: int, taille: int, unicode: bool):
    """Concatène la chaîne DAT* d'un objet et signale toute troncature."""
    if taille <= 0:
        return b"", [], ""
    morceaux = []
    offsets = []
    vus = set()
    courant = offset
    total = 0
    erreur = ""
    limite = min(
        max(1, (taille + DONNEES_PBL - 1) // DONNEES_PBL) + 8,
        len(donnees) // BLOC_PBL + 2,
    )
    while courant and total < taille:
        if courant in vus:
            erreur = f"boucle dans les blocs DAT* à l'offset {courant}"
            break
        if len(vus) >= limite:
            erreur = "chaîne de blocs DAT* anormalement longue"
            break
        vus.add(courant)
        if courant < 0 or courant + 10 > len(donnees):
            erreur = f"bloc DAT* hors bornes à l'offset {courant}"
            break
        if donnees[courant:courant + 4] != b"DAT*":
            erreur = f"signature DAT* absente à l'offset {courant}"
            break
        suivant = _u32(donnees, courant + 4)
        longueur = _u16(donnees, courant + 8)
        if longueur > DONNEES_PBL:
            erreur = f"longueur DAT* invalide à l'offset {courant}"
            break
        debut = courant + 10
        fin = debut + longueur
        if fin > len(donnees):
            morceaux.append(donnees[debut:])
            offsets.append(courant)
            total += len(donnees) - debut
            erreur = f"bloc DAT* tronqué à l'offset {courant}"
            break
        morceaux.append(donnees[debut:fin])
        offsets.append(courant)
        total += longueur
        courant = suivant
    brut = b"".join(morceaux)[:taille]
    if not erreur and len(brut) < taille:
        erreur = f"données incomplètes ({len(brut)}/{taille} octets)"
    return brut, offsets, erreur


def _decoder_pbl(brut: bytes, unicode: bool) -> str:
    if unicode:
        texte = brut.decode("utf-16le", "replace")
    elif brut[:2] in (b"\xff\xfe", b"\xfe\xff"):
        texte = brut.decode("utf-16", "replace")
    else:
        texte = ""
        for encodage in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                texte = brut.decode(encodage)
                break
            except UnicodeDecodeError:
                continue
    texte = texte.lstrip("\ufeff").replace("\x00", "")
    return texte.replace("\r\n", "\n").replace("\r", "\n")


def _objet_erreur(chemin, message: str, fatal: bool = True, nom=None) -> dict:
    if nom is None:
        try:
            nom = Path(chemin).name if fatal else ""
        except (TypeError, ValueError):
            nom = ""
    return {
        "nom": nom, "name": nom, "objet": "",
        "extension": Path(nom).suffix.lower(), "texte": "", "text": "",
        "commentaire": "", "octets": 0, "unicode": False, "offsets": [],
        "erreur": message, "fatal": bool(fatal),
    }


def _analyser_pbl(donnees: bytes, chemin) -> list[dict]:
    unicode, taille_entete = _entete_pbl(donnees)
    racine = _racine_pbl(donnees, taille_entete)
    entrees, erreurs = _noeuds_pbl(donnees, racine, unicode)
    objets = []
    for entree in entrees:
        nom = entree["nom"]
        suffixe = Path(nom).suffix.lower()
        if suffixe not in SOURCES:
            continue
        brut, offsets, erreur = _blocs_donnees_pbl(
            donnees, entree["donnees"], entree["taille"], unicode)
        taille_commentaire = entree["commentaire"] * (2 if unicode else 1)
        if taille_commentaire > len(brut):
            erreur = erreur or "commentaire tronqué"
        taille_commentaire = min(taille_commentaire, len(brut))
        commentaire = _decoder_pbl(brut[:taille_commentaire], unicode)
        texte = _decoder_pbl(brut[taille_commentaire:], unicode)
        objet = {
            "nom": nom, "name": nom, "objet": Path(nom).stem,
            "extension": suffixe, "texte": texte, "text": texte,
            "commentaire": commentaire, "octets": entree["taille"],
            "unicode": unicode, "offsets": offsets,
        }
        if erreur:
            objet["erreur"] = erreur
            objet["fatal"] = False
        objets.append(objet)
    objets.sort(key=lambda objet: (objet["nom"].lower(), objet["nom"]))
    for message in erreurs:
        objets.append(_objet_erreur(chemin, message, fatal=False))
    return objets


def extraire_pbl(chemin) -> list[dict]:
    """Extrait les objets source d'un ``.pbl`` sans runtime PowerBuilder.

    Chaque objet rendu expose ``nom``/``name``, ``objet``, ``extension``,
    ``texte``/``text``, ``commentaire``, ``octets``, ``unicode`` et ``offsets``.
    Un fichier illisible rend un unique élément avec ``erreur`` et ``fatal`` ;
    une extraction partielle ajoute ``erreur`` sur l'objet concerné. La fonction
    ne lève jamais : toute anomalie devient un résultat structuré.
    """
    try:
        donnees = Path(chemin).read_bytes()
    except Exception as exception:
        return [_objet_erreur(chemin, f"lecture impossible : {exception}")]
    try:
        return _analyser_pbl(donnees, chemin)
    except _PblIllisible as exception:
        return [_objet_erreur(chemin, f"PBL illisible : {exception}")]
    except Exception as exception:
        return [_objet_erreur(
            chemin, f"PBL illisible : {type(exception).__name__}: {exception}")]


_RE_GLOBAL = re.compile(r"^\s*global\s+type\b", re.I)
_RE_TYPE = re.compile(
    r"^\s*(?:(?:global|shared|private|protected|public)\s+)?type\s+"
    r"([A-Za-z_]\w*)\s+from\s+([A-Za-z_]\w*)\b"
    r"(?:\s+within\s+([A-Za-z_]\w*))?\s*$",
    re.I,
)
_RE_FIN_TYPE = re.compile(r"^\s*end\s+type\b", re.I)
_RE_VARIABLES = re.compile(
    r"^\s*(?:global|shared|local|type)\s+variables\s*$", re.I)
_RE_FIN_VARIABLES = re.compile(r"^\s*end\s+variables\b", re.I)
_RE_FORWARD = re.compile(r"^\s*forward\s*$", re.I)
_RE_FIN_FORWARD = re.compile(r"^\s*end\s+forward\b", re.I)
_RE_PROTOTYPES = re.compile(r"^\s*forward\s+prototypes\b", re.I)
_RE_FIN_PROTOTYPES = re.compile(r"^\s*end\s+prototypes\b", re.I)
_RE_FONCTION = re.compile(
    r"^\s*(?:(?:public|private|protected|global|shared|local)\s+)*function\s+"
    r"(?:[A-Za-z_]\w*(?:\{\d+\})?(?:\[\])?\s+)?"
    r"([A-Za-z_]\w*)\s*\([^)]*\)\s*;?\s*$",
    re.I,
)
_RE_FIN_FONCTION = re.compile(r"^\s*end\s+function\b", re.I)
_RE_EVENEMENT = re.compile(
    r"^\s*event\s+([A-Za-z_]\w*)\s*(?:\([^)]*\))?\s*;?\s*$", re.I)
_RE_FIN_EVENEMENT = re.compile(r"^\s*end\s+event\b", re.I)
_RE_ON_POINT = re.compile(
    r"^\s*on\s+([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s*;?\s*$", re.I)
_RE_ON_CIBLE = re.compile(
    r"^\s*on\s+([A-Za-z_]\w*)\s*::\s*([A-Za-z_]\w*)\s*;?\s*$", re.I)
_RE_ON_SIMPLE = re.compile(
    r"^\s*on\s+([A-Za-z_]\w*)\s*;?\s*$", re.I)
_RE_FIN_ON = re.compile(r"^\s*end\s+on\b", re.I)
_RE_DATAOBJECT = re.compile(
    r"\bdataobject\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([A-Za-z_]\w*))", re.I)
_RE_SQL = re.compile(r"^\s*(SELECT|INSERT|UPDATE|DELETE)\b", re.I)
_RE_SQL_FROM = re.compile(
    r"\bFROM\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)", re.I)
_RE_SQL_INTO = re.compile(
    r"\bINSERT\s+(?:INTO\s+)?([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)", re.I)
_RE_SQL_UPDATE = re.compile(
    r"^\s*UPDATE\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)", re.I)
_RE_SQL_DELETE = re.compile(
    r"^\s*DELETE\s+FROM\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)", re.I)
_RE_FRONTIERE = re.compile(
    r"^\s*(?:end\s+(?:function|event|on|type|variables|prototypes|forward)\b"
    r"|end\s+if\b|on\s+|event\s+|function\s+|type\s+|global\s+type\b"
    r"|forward\s*$)",
    re.I,
)
_RE_DECLARATION = re.compile(
    r"^\s*(?:(?:public|private|protected)\s*:?\s*)?"
    r"([A-Za-z_]\w*(?:\{\d+\})?(?:\[\])?)\s+(.+)$",
    re.I,
)
_RE_NOM = re.compile(r"^\s*([A-Za-z_]\w*)")
_RE_APPEL = re.compile(
    r"\b([A-Za-z_]\w*(?:\s*\.\s*[A-Za-z_]\w*)*)\s*\(")

_MOTS_NON_VARIABLES = frozenset({
    "end", "public", "private", "protected", "global", "shared", "local",
})
_MOTS_INTERDITS = frozenset({
    "if", "elseif", "else", "for", "while", "do", "choose", "case", "return",
    "select", "insert", "update", "delete", "values", "into", "from", "where",
    "and", "or", "not", "then", "to", "step", "next", "loop", "until", "exit",
    "continue", "goto", "try", "catch", "finally", "throw", "function", "event",
    "on", "end", "type", "variables", "forward", "prototypes", "public",
    "private", "protected", "global", "shared", "local", "within", "using",
    "create", "destroy",
})


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


def _sans_commentaire(texte: str, dans_bloc: bool = False):
    """Retire les commentaires ``//`` et ``/* */`` hors littéraux."""
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
            if caractere == "~" and i + 1 < len(texte):
                sortie.append(texte[i + 1])
                i += 2
                continue
            if caractere == guillemet:
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
        sortie.append(caractere)
        i += 1
    return "".join(sortie), dans_bloc


def _lignes_code(texte: str):
    """Rend (numéro, code sans commentaire) par ligne source."""
    resultat = []
    dans_bloc = False
    for numero, brute in enumerate(texte.splitlines(), 1):
        code, dans_bloc = _sans_commentaire(brute.rstrip("\r\n"), dans_bloc)
        resultat.append((numero, code.rstrip()))
    return resultat


def _masque(texte: str) -> str:
    """Remplace le contenu des littéraux par des espaces, hors délimiteurs."""
    sortie = []
    guillemet = None
    i = 0
    while i < len(texte):
        caractere = texte[i]
        if guillemet:
            sortie.append(" ")
            if caractere == "~" and i + 1 < len(texte):
                sortie.append(" ")
                i += 2
                continue
            if caractere == guillemet:
                guillemet = None
        elif caractere in "'\"":
            guillemet = caractere
            sortie.append(" ")
        else:
            sortie.append(caractere)
        i += 1
    return "".join(sortie)


def _couper_virgules(texte: str):
    """Découpe sur les virgules de premier niveau, hors littéraux."""
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


def _noms_variables(texte: str):
    """Noms déclarés par une ligne de section ``variables``."""
    declaration = _RE_DECLARATION.match(texte)
    if not declaration:
        return []
    noms = []
    for morceau in _couper_virgules(declaration.group(2)):
        trouve = _RE_NOM.match(morceau)
        if not trouve:
            continue
        nom = trouve.group(1)
        if nom.lower() in _MOTS_NON_VARIABLES or nom in noms:
            continue
        noms.append(nom)
    return noms


def _table_sql(commande: str, texte: str) -> str:
    motif = {
        "SELECT": _RE_SQL_FROM,
        "INSERT": _RE_SQL_INTO,
        "UPDATE": _RE_SQL_UPDATE,
        "DELETE": _RE_SQL_DELETE,
    }.get(commande)
    if not motif:
        return ""
    trouve = motif.search(texte)
    return trouve.group(1) if trouve else ""


def _bloc_sql(lignes, depart):
    """Rend la dernière ligne et le texte d'une instruction SQL éventuellement multiligne."""
    morceaux = [lignes[depart][1]]
    masque = _masque(lignes[depart][1])
    j = depart
    while ";" not in masque and j + 1 < len(lignes):
        suivant = lignes[j + 1][1]
        if _RE_FRONTIERE.match(suivant.strip()):
            break
        j += 1
        morceaux.append(suivant)
        masque = _masque(suivant)
    return j, " ".join(morceaux)


def _dedupliquer(observations):
    """Garde la déclaration la plus complète d'un objet ou DataWindow."""
    resultat = []
    positions = {}
    for observation in observations:
        if observation.kind in {"pb_object", "pb_datawindow"}:
            cle = (observation.kind, observation.symbol)
            if cle in positions:
                index = positions[cle]
                precedent = resultat[index]
                if (observation.start, observation.end) >= (precedent.start, precedent.end):
                    resultat[index] = observation
                continue
            positions[cle] = len(resultat)
        resultat.append(observation)
    return resultat


class PowerBuilderSidecar:
    """Index structurel PowerBuilder : aucune exécution, uniquement des observations."""

    provider = PROVIDER
    extensions = EXTENSIONS
    parser = PARSER
    parser_version = PARSER_VERSION
    language = LANGAGE

    def index(self, racine: str, fichiers=()) -> list[Observation]:
        fichiers = tuple(fichiers or ())
        observations = []
        for chemin in self._candidats(racine, fichiers):
            suffixe = chemin.suffix.lower()
            if suffixe not in SUFFIXES or not chemin.is_file():
                continue
            if suffixe == ".pbl":
                for objet in extraire_pbl(chemin):
                    if (objet.get("fatal") or not objet.get("nom")
                            or not objet.get("texte")):
                        continue
                    fichier = f"pbl://{chemin.name}/{objet['nom']}"
                    try:
                        observations.extend(self._extraire(fichier, objet["texte"]))
                    except Exception:
                        continue
                continue
            try:
                texte = _lire(chemin)
                fichier = _cle_fichier(Path(racine), chemin)
                observations.extend(self._extraire(fichier, texte))
            except Exception:
                continue
        return sorted(observations, key=lambda o: (o.file, o.start, o.kind, o.symbol))

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
            suffixe = chemin.suffix.lower()
            if suffixe not in SUFFIXES:
                lignes[cle] = CouvertureFichier(
                    file=cle, parser=self.parser, statut="non_supporte",
                    raison="extension non prise en charge")
            elif not chemin.is_file():
                lignes[cle] = CouvertureFichier(
                    file=cle, language=LANGAGE, parser=self.parser, statut="ignore",
                    raison="fichier introuvable ou illisible")
            elif suffixe == ".pbl":
                statut, raison = self._couverture_pbl(chemin)
                lignes[cle] = CouvertureFichier(
                    file=cle, language=LANGAGE, parser=self.parser,
                    statut=statut, raison=raison)
            elif cle in trouvees:
                lignes[cle] = CouvertureFichier(
                    file=cle, language=LANGAGE, parser=self.parser, statut="indexe")
            else:
                try:
                    texte = _lire(chemin)
                except OSError as erreur:
                    lignes[cle] = CouvertureFichier(
                        file=cle, language=LANGAGE, parser=self.parser, statut="ignore",
                        raison=f"lecture impossible : {erreur}")
                else:
                    if suffixe == ".srd" and texte.strip():
                        lignes[cle] = CouvertureFichier(
                            file=cle, language=LANGAGE, parser=self.parser,
                            statut="indexe")
                    elif suffixe == ".srd":
                        lignes[cle] = CouvertureFichier(
                            file=cle, language=LANGAGE, parser=self.parser,
                            statut="partiel", raison="DataWindow vide")
                    else:
                        lignes[cle] = CouvertureFichier(
                            file=cle, language=LANGAGE, parser=self.parser,
                            statut="partiel",
                            raison="aucune structure PowerBuilder reconnue")
        return [lignes[cle] for cle in sorted(lignes)]

    @staticmethod
    def _couverture_pbl(chemin: Path) -> tuple[str, str]:
        objets = extraire_pbl(chemin)
        erreurs = [objet for objet in objets if objet.get("erreur")]
        if any(objet.get("fatal") for objet in objets):
            return "partiel", erreurs[0]["erreur"]
        if erreurs:
            details = "; ".join(
                f"{objet.get('nom') or 'structure'}: {objet['erreur']}"
                for objet in erreurs[:3])
            return "partiel", f"extraction partielle : {details}"
        return "indexe", ""

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
        lignes = _lignes_code(texte)
        dernier = lignes[-1][0] if lignes else 0
        objet = ""
        dans_forward = False
        dans_prototypes = False
        dans_variables = False
        pile_types = []
        fonctions = []
        evenements = []
        i = 0
        while i < len(lignes):
            numero, code = lignes[i]
            brut = code.strip()
            if not brut:
                i += 1
                continue

            if _RE_FIN_FORWARD.match(brut):
                dans_forward = False
                i += 1
                continue
            if _RE_FIN_PROTOTYPES.match(brut):
                dans_prototypes = False
                i += 1
                continue
            if _RE_FIN_FONCTION.match(brut):
                if fonctions:
                    fonction = fonctions.pop()
                    observations.append(self._obs(
                        fichier, "pb_function", fonction["nom"],
                        fonction["debut"], numero, fonction["attributs"]))
                i += 1
                continue
            if _RE_FIN_EVENEMENT.match(brut) or _RE_FIN_ON.match(brut):
                if evenements:
                    evenement = evenements.pop()
                    observations.append(self._obs(
                        fichier, "pb_event", evenement["nom"],
                        evenement["debut"], numero, evenement["attributs"]))
                i += 1
                continue
            if _RE_FIN_VARIABLES.match(brut):
                dans_variables = False
                i += 1
                continue
            if _RE_FIN_TYPE.match(brut):
                if pile_types:
                    type_ = pile_types.pop()
                    if type_["genre"]:
                        observations.append(self._obs(
                            fichier, type_["genre"], type_["nom"],
                            type_["debut"], numero, type_["attributs"]))
                i += 1
                continue

            if _RE_PROTOTYPES.match(brut):
                dans_prototypes = True
                i += 1
                continue
            if _RE_FORWARD.match(brut):
                dans_forward = True
                i += 1
                continue

            masque = _masque(brut)
            sql = _RE_SQL.match(masque)
            if sql:
                j, bloc = _bloc_sql(lignes, i)
                commande = sql.group(1).upper()
                table = _table_sql(commande, _masque(bloc))
                attributs = {"table": table} if table else {}
                observations.append(self._obs(
                    fichier, "pb_sql", commande, numero, lignes[j][0], attributs))
                i = j + 1
                continue

            if _RE_VARIABLES.match(brut):
                dans_variables = True
                i += 1
                continue

            type_trouve = _RE_TYPE.match(brut)
            if type_trouve:
                nom = type_trouve.group(1)
                base = type_trouve.group(2)
                parent = type_trouve.group(3) or ""
                est_global = bool(_RE_GLOBAL.match(brut))
                if est_global:
                    objet = nom
                if base.lower() == "datawindow":
                    genre = "pb_datawindow"
                    attributs = {"datawindow": nom}
                    contexte = parent or objet
                    if contexte:
                        attributs["object"] = contexte
                    est_datawindow = True
                elif est_global:
                    genre = "pb_object"
                    attributs = {"object": nom}
                    est_datawindow = False
                else:
                    genre = ""
                    attributs = {}
                    est_datawindow = False
                pile_types.append({
                    "genre": genre, "nom": nom, "debut": numero,
                    "attributs": attributs, "datawindow": est_datawindow,
                })
                i += 1
                continue

            if not dans_prototypes:
                fonction = _RE_FONCTION.match(brut)
                if fonction:
                    nom = fonction.group(1)
                    attributs = {"function": nom}
                    if objet:
                        attributs["object"] = objet
                    fonctions.append({
                        "nom": nom, "debut": numero, "attributs": attributs})
                    i += 1
                    continue

            evenement = _RE_ON_POINT.match(brut) or _RE_ON_CIBLE.match(brut)
            if evenement:
                cible = evenement.group(1)
                nom = evenement.group(2)
                attributs = {"event": nom, "target": cible}
                if objet:
                    attributs["object"] = objet
                evenements.append({
                    "nom": nom, "debut": numero, "attributs": attributs})
                i += 1
                continue
            simple = _RE_ON_SIMPLE.match(brut)
            if simple:
                nom = simple.group(1)
                attributs = {"event": nom}
                if objet:
                    attributs["object"] = objet
                evenements.append({
                    "nom": nom, "debut": numero, "attributs": attributs})
                i += 1
                continue
            declaration = _RE_EVENEMENT.match(brut)
            if declaration:
                nom = declaration.group(1)
                attributs = {"event": nom}
                if objet:
                    attributs["object"] = objet
                evenements.append({
                    "nom": nom, "debut": numero, "attributs": attributs})
                i += 1
                continue

            if dans_variables:
                attributs = {"object": objet} if objet else {}
                for nom in _noms_variables(brut):
                    observations.append(self._obs(
                        fichier, "pb_var", nom, numero, numero, attributs))
                i += 1
                continue

            if pile_types and pile_types[-1].get("datawindow"):
                dataobject = _RE_DATAOBJECT.search(brut)
                if dataobject:
                    valeur = _groupe(dataobject)
                    if valeur:
                        pile_types[-1]["attributs"]["datawindow"] = valeur
                i += 1
                continue

            if dans_forward or dans_prototypes:
                i += 1
                continue

            vus = set()
            for appel in _RE_APPEL.finditer(masque):
                chemin = re.sub(r"\s+", "", appel.group(1))
                if not chemin:
                    continue
                premier = chemin.split(".")[0].lower()
                if premier in _MOTS_INTERDITS:
                    continue
                symbole = chemin.split(".")[-1]
                if (symbole, chemin) in vus:
                    continue
                vus.add((symbole, chemin))
                observations.append(self._obs(
                    fichier, "pb_call", symbole, numero, numero,
                    {"target": chemin}))
            i += 1

        for fonction in fonctions:
            observations.append(self._obs(
                fichier, "pb_function", fonction["nom"], fonction["debut"],
                dernier, fonction["attributs"]))
        for evenement in evenements:
            observations.append(self._obs(
                fichier, "pb_event", evenement["nom"], evenement["debut"],
                dernier, evenement["attributs"]))
        for type_ in pile_types:
            if type_["genre"]:
                observations.append(self._obs(
                    fichier, type_["genre"], type_["nom"], type_["debut"],
                    dernier, type_["attributs"]))
        return _dedupliquer(observations)

    @staticmethod
    def _obs(fichier, kind, symbol, debut, fin, attributs=None) -> Observation:
        return Observation(
            provider=PROVIDER, parser=PARSER, parser_version=VERSION, file=fichier,
            language=LANGAGE, kind=kind, symbol=symbol, start=debut, end=fin,
            attributes=attributs or {})
