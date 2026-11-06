"""Recettes déterministes (harness v3 §2.1) : l'objet d'un claim figure-t-il dans les lignes citées ?

Fonctions pures : ni base, ni réseau, ni modèle. Les lignes sont des données, jamais des instructions
(on ne fait que les comparer). « verifie » = la ligne appuie l'objet ; « non_appuye » = elle ne l'appuie pas
(ce n'est pas une preuve que le claim est faux) ; None = aucune recette pour ce prédicat.
"""
import re

_RE_COMMENTAIRES = re.compile(r"/\*[\s\S]*?\*/|<!--[\s\S]*?-->")
_RE_CHAINES = re.compile(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|`(?:[^`\\]|\\.)*`')


def _masquer(lignes):
    """Même nombre de lignes, chaînes et commentaires remplacés par des espaces : le nom d'une fonction cité dans un
    texte ne devient jamais le fondement d'une flèche."""
    def blanc(m):
        return "".join("\n" if c == "\n" else " " for c in m.group(0))

    contenu = "\n".join(lignes) if isinstance(lignes, list) else str(lignes)
    return _RE_CHAINES.sub(blanc, _RE_COMMENTAIRES.sub(blanc, contenu)).split("\n")


PREDICATS = frozenset({
    "DECLARE_DEPENDANCE", "DEPEND_DE", "EXPOSE", "LIT_VARIABLE", "EXECUTE_IMAGE",
    "APPELLE", "COPIE", "EXECUTE", "LIT_DATASET", "REFERENCE",
    "TABLE", "STOCKE_DANS", "COMPOSANT_JEE", "INJECTE", "INTERFACE_UTILISATEUR",
})
VERIFIE, NON_APPUYE = "verifie", "non_appuye"
_VERBES = ("get", "post", "put", "delete", "patch")


# --- Dépendance déclarée ou utilisée : paquet en mot entier, séparateurs PEP 503 équivalents --------
def _depend_de(objet: str, lignes: list[str]) -> bool:
    parties = [re.escape(p) for p in re.split(r"[-_.]+", objet.strip()) if p]
    if not parties:
        return False
    # ni lettre/chiffre/_/./-/@// avant, ni lettre/chiffre/_/- (ou .x) après : fastapi-users != fastapi
    motif = re.compile(r"(?<![\w.@/-])" + r"[-_.]+".join(parties) + r"(?![\w-]|\.\w)", re.I)
    # ponytail: lignes commentées (#, //) ignorées ; pas de lecture structurée des manifestes
    return any(motif.search(l) for l in lignes if not l.lstrip().startswith(("#", "//")))


# --- EXPOSE : méthode HTTP ET chemin -------------------------------------------------------------
_METHODES_RE = [
    re.compile(r"\.(get|post|put|delete|patch)\s*\(", re.I),          # FastAPI, Express, gin
    re.compile(r"@(Get|Post|Put|Delete|Patch)Mapping", re.I),         # Spring
    re.compile(r"RequestMethod\.(\w+)"),                              # Spring @RequestMapping
]
_METHODS_LISTE_RE = re.compile(r"methods\s*=\s*[\[({]([^\])}]*)", re.I)  # Flask / FastAPI api_route
_LITTERAL_RE = re.compile(r"""["'`](/[^"'`\s]*)["'`]""")
_PARAM_RE = re.compile(r"^(\{.*\}|:.+|<.*>|\[.*\])$")


def _segments(chemin: str) -> list[str]:
    segs = [s for s in chemin.split("?")[0].split("/") if s]
    return ["{}" if _PARAM_RE.match(s) else s for s in segs]  # {id} == :id == <id>


def _expose(objet: str, lignes: list[str]) -> bool:
    m = re.match(r"\s*([A-Za-z]+)\s+(\S+)\s*$", objet)
    if not m:
        return False
    verbe, cible = m.group(1).lower(), _segments(m.group(2))
    cible_brute = m.group(2)
    # ponytail: lignes jointes (décorateur sur plusieurs lignes) → une plage qui porte deux routes
    # distinctes peut valider le croisement méthode/chemin ; resserrer par décorateur si on le constate
    texte = "\n".join(lignes)
    verbes = {v.lower() for r in _METHODES_RE for v in r.findall(texte)}
    for liste in _METHODS_LISTE_RE.findall(texte):
        verbes |= {v.lower() for v in re.findall(r"[A-Za-z]+", liste)}
    if re.search(r"\.route\s*\(", texte) and "methods" not in texte.lower():
        verbes.add("get")  # Flask : GET par défaut
    if verbe not in verbes:
        return False
    # le chemin cité peut être plus long (préfixe de routeur absent de la ligne) si la fin, par
    # segments entiers, correspond ; un chemin de ligne vide ("/") ne vaut que pour la racine citée
    for chemin in _LITTERAL_RE.findall(texte):
        segs = _segments(chemin)
        if (segs and cible[-len(segs):] == segs) or (not segs and (not cible or cible_brute.endswith("/"))):
            return True
    return False


# --- LIT_VARIABLE : formes de lecture reconnues, mot entier, sensible à la casse -----------------
def _lit_variable(objet: str, lignes: list[str]) -> bool:
    nom = re.escape(objet.strip())
    if not nom:
        return False
    formes = [
        rf"environ(\.get)?\s*[\[(]\s*[\"']{nom}[\"']",     # os.environ["X"], os.environ.get("X")
        rf"(?i:getenv)\s*\(\s*[\"']{nom}[\"']",            # os.getenv, os.Getenv, System.getenv
        rf"process\.env\.{nom}(?!\w)",                     # Node
        rf"process\.env\[\s*[\"']{nom}[\"']",
        rf"^\s*(-\s*)?[\"']?{nom}[\"']?\s*[:=]",           # compose / .env
        rf"^\s*(?:ENV|ARG)\s+{nom}(?!\w)",                 # Dockerfile : déclaration, pas lecture
        rf"\$\{{?{nom}(?!\w)",                             # ${X}, $X
    ]
    motif = re.compile("|".join(formes))
    return any(motif.search(l) for l in lignes)


# --- EXECUTE_IMAGE : image sans registre Docker Hub par défaut, sans library/, sans tag/digest ---
def _image(nom: str) -> str:
    nom = nom.strip().strip("'\"").lower().split("@")[0]
    for prefixe in ("registry-1.docker.io/", "index.docker.io/", "docker.io/"):
        nom = nom.removeprefix(prefixe)
    nom = nom.removeprefix("library/")
    tete, _, queue = nom.rpartition("/")
    return (tete + "/" if tete else "") + queue.split(":")[0]


_IMAGE_LIGNE_RE = re.compile(
    r"^\s*(?:-\s*)?image\s*:\s*(\S+)|^\s*FROM\s+(?:--\S+\s+)*(\S+)", re.I)


def _execute_image(objet: str, lignes: list[str]) -> bool:
    cible = _image(objet)
    if not cible:
        return False
    for l in lignes:
        m = _IMAGE_LIGNE_RE.match(l)
        if m and _image(m.group(1) or m.group(2)) == cible:
            return True
    return False


# --- Prédicats legacy structurels (ADR 0026) : une ligne suffit à les établir -----------------------
# Insensibles à la casse, mais mots entiers ; les lignes de commentaire legacy (*, //*, --, #) sont ignorées.
_FIN_NOM = r"(?![\w-]|\.[\w-])"  # ni suffixe de nom, ni qualification supplémentaire (ACME.CLIENTS != ACME.CLIENTS.X)
_PREFIXES_COMMENTAIRE = ("*", "//*", "--", "#")


def _lignes_legacy(lignes: list[str]) -> list[str]:
    return [l for l in lignes if not l.lstrip().startswith(_PREFIXES_COMMENTAIRE)]


def _motif_legacy(motif: str, objet: str) -> re.Pattern:
    return re.compile(motif.format(nom=re.escape(objet.strip())) + _FIN_NOM, re.I)


def _appelle(objet: str, lignes: list[str]) -> bool:
    if not objet.strip():
        return False
    motifs = [
        _motif_legacy(r"\bCALL\s+(?:FUNCTION\s+)?['\"]?{nom}['\"]?", objet),
        _motif_legacy(r"\bCALLP\s+['\"]?{nom}['\"]?", objet),
        _motif_legacy(r"\bCALLB\s+['\"]?{nom}['\"]?", objet),
        _motif_legacy(r"\bEXSR\s+['\"]?{nom}['\"]?", objet),
    ]
    return any(m.search(l) for l in _lignes_legacy(lignes) for m in motifs)


def _copie(objet: str, lignes: list[str]) -> bool:
    if not objet.strip():
        return False
    motif = _motif_legacy(r"\bCOPY\s+['\"]?{nom}['\"]?", objet)
    return any(motif.search(l) for l in _lignes_legacy(lignes))


def _execute(objet: str, lignes: list[str]) -> bool:
    if not objet.strip():
        return False
    motifs = [
        _motif_legacy(r"\bEXEC\s+PGM\s*=\s*['\"]?{nom}['\"]?", objet),
        _motif_legacy(r"\bEXEC\s+PROC\s*=\s*['\"]?{nom}['\"]?", objet),
        _motif_legacy(r"\bPROGRAM-ID\s*\.\s*['\"]?{nom}['\"]?", objet),
    ]
    return any(m.search(l) for l in _lignes_legacy(lignes) for m in motifs)


def _lit_dataset(objet: str, lignes: list[str]) -> bool:
    if not objet.strip():
        return False
    motifs = [
        _motif_legacy(r"\bDSN\s*=\s*['\"]?{nom}['\"]?", objet),
        _motif_legacy(r"\bASSIGN\s+TO\s+['\"]?{nom}['\"]?", objet),
    ]
    return any(m.search(l) for l in _lignes_legacy(lignes) for m in motifs)


def _reference(objet: str, lignes: list[str]) -> bool:
    if not objet.strip():
        return False
    motif = _motif_legacy(r"\bREFERENCES\s+['\"]?{nom}['\"]?", objet)
    return any(motif.search(l) for l in _lignes_legacy(lignes))


# --- Prédicats legacy composés (ADR 0027) : la ligne citée doit établir le lien, pas seulement
# l'avoir observé. Les commentaires sont masqués, mais les chaînes restent lisibles : c'est souvent
# dans « … » que figure la table, l'action ou le type cité.
def _sans_commentaires(lignes: list[str]) -> list[str]:
    """Même nombre de lignes, commentaires remplacés par des espaces ; les chaînes restent intactes."""
    texte = "\n".join(lignes) if isinstance(lignes, list) else str(lignes)
    masque = list(texte)
    i, guillemet = 0, ""
    while i < len(texte):
        caractere = texte[i]
        if guillemet:
            if caractere == "\\":
                i += 2
                continue
            if caractere == guillemet:
                guillemet = ""
            i += 1
            continue
        if caractere in "\"'`":
            guillemet = caractere
            i += 1
            continue
        fin = None
        if texte.startswith("//", i):
            fin = texte.find("\n", i)
        elif texte.startswith("/*", i):
            fin = texte.find("*/", i + 2)
            fin = len(texte) if fin < 0 else fin + 2
        elif texte.startswith("<!--", i):
            fin = texte.find("-->", i + 4)
            fin = len(texte) if fin < 0 else fin + 3
        elif texte.startswith("<%--", i):
            fin = texte.find("--%>", i + 4)
            fin = len(texte) if fin < 0 else fin + 4
        elif texte.startswith("--", i):
            fin = texte.find("\n", i)
        elif caractere in "#*" and not texte[:i].rsplit("\n", 1)[-1].strip():
            fin = texte.find("\n", i)
        if fin is None:
            i += 1
            continue
        fin = len(texte) if fin < 0 else fin
        for position in range(i, fin):
            if masque[position] != "\n":
                masque[position] = " "
        i = fin
    return "".join(masque).split("\n")


def _lignes_propres(lignes: list[str]) -> list[str]:
    return [ligne for ligne in _sans_commentaires(lignes) if ligne.strip()]


_ANNOTATION = r"@(?:[\w.]+\.)?"
_FIN_CHEMIN = r"(?![\w./-])"


def _motif_table(objet: str) -> str:
    """Nom de table échappé, avec guillemets/crochets facultatifs et un schéma qualifiant unique."""
    parties = [re.escape(partie) for partie in objet.strip().split(".") if partie]
    if not parties:
        return ""
    if len(parties) == 1:
        partie = rf"[\"'`\[]?{parties[0]}[\"'`\]]?"
        return rf"(?:[\w\"`\[]+[\"'`\]]?\s*\.\s*)?{partie}"
    return r"\s*\.\s*".join(rf"[\"'`\[]?{partie}[\"'`\]]?" for partie in parties)


def _table(objet: str, lignes: list[str]) -> bool:
    """CREATE TABLE <objet> ou @Table(... <objet> ...)."""
    if not objet.strip():
        return False
    nom = re.escape(objet.strip())
    cible = _motif_table(objet)
    motifs = [
        re.compile(rf"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{cible}"
                   + _FIN_NOM, re.I),
        re.compile(rf"{_ANNOTATION}Table\s*\([^)]*\bname\s*=\s*[\"']{nom}[\"']", re.I),
        re.compile(rf"{_ANNOTATION}Table\s*\([^)]*\bvalue\s*=\s*[\"']{nom}[\"']", re.I),
        re.compile(rf"{_ANNOTATION}Table\s*\(\s*[\"']{nom}[\"']", re.I),
    ]
    return any(motif.search(ligne) for ligne in _lignes_propres(lignes) for motif in motifs)


def _stocke_dans(objet: str, lignes: list[str]) -> bool:
    """La table est prouvée par la ligne qui la déclare, pas par l'entité qui la mentionne."""
    return _table(objet, lignes)


def _composant_jee(objet: str, lignes: list[str]) -> bool:
    """@Stateless (ou @MessageDriven…) ou l'élément XML correspondant (<session>, <message-driven>…)."""
    if not objet.strip():
        return False
    nom = re.escape(objet.strip())
    motifs = [
        re.compile(rf"{_ANNOTATION}{nom}" + _FIN_NOM, re.I),
        re.compile(rf"<(?:\w+:)?{nom}" + _FIN_NOM, re.I),
    ]
    return any(motif.search(ligne) for ligne in _lignes_propres(lignes) for motif in motifs)


_INJECTIONS = r"EJB|Autowired|Inject|PersistenceContext|PersistenceUnit"


def _injecte(objet: str, lignes: list[str]) -> bool:
    """Le type injecté et l'annotation d'injection sur le champ cité, ou la ressource XML localisée."""
    if not objet.strip():
        return False
    nom = re.escape(objet.strip())
    texte = "\n".join(_lignes_propres(lignes))
    type_ = rf"(?<![\w.]){nom}(?![\w-]|\.[\w-])"
    annotation = rf"{_ANNOTATION}(?:{_INJECTIONS})\b"
    if re.search(annotation + rf"[^;]{{0,400}}?{type_}", texte, re.I):
        return True
    ressource = (rf"<(?:\w+:)?resource-ref\b[\s\S]*?"
                 rf"<(?:\w+:)?res-type>\s*{nom}\s*</(?:\w+:)?res-type>")
    return bool(re.search(ressource, texte, re.I))


def _interface_utilisateur(objet: str, lignes: list[str]) -> bool:
    """Formulaire, include, forward ou import JSP dont l'attribut localisé cite l'action/page."""
    if not objet.strip():
        return False
    nom = re.escape(objet.strip())
    texte = "\n".join(_lignes_propres(lignes))
    formes = [
        rf"<(?:\w+:)?form\b[^>]*\baction\s*=\s*[\"']?{nom}[\"']?",
        rf"<(?:\w+:)?include\b[^>]*\b(?:page|file)\s*=\s*[\"']?{nom}[\"']?",
        rf"<(?:\w+:)?forward\b[^>]*\bpage\s*=\s*[\"']?{nom}[\"']?",
        rf"<c:import\b[^>]*\b(?:url|value|page)\s*=\s*[\"']?{nom}[\"']?",
        rf"<%@\s*include\b[^>]*\bfile\s*=\s*[\"']?{nom}[\"']?",
    ]
    return any(re.search(forme + _FIN_CHEMIN, texte, re.I | re.S) for forme in formes)


_RECETTES = {
    "DECLARE_DEPENDANCE": _depend_de, "DEPEND_DE": _depend_de, "EXPOSE": _expose,
    "LIT_VARIABLE": _lit_variable, "EXECUTE_IMAGE": _execute_image,
    "APPELLE": _appelle, "COPIE": _copie, "EXECUTE": _execute,
    "LIT_DATASET": _lit_dataset, "REFERENCE": _reference,
    "TABLE": _table, "STOCKE_DANS": _stocke_dans,
    "COMPOSANT_JEE": _composant_jee, "INJECTE": _injecte,
    "INTERFACE_UTILISATEUR": _interface_utilisateur,
}


def recette(predicat: str, objet: str, lignes: list[str]) -> str | None:
    """'verifie' si les lignes citées (au commit) contiennent bien l'objet, 'non_appuye' sinon ;
    None si aucune recette pour ce prédicat."""
    verifier = _RECETTES.get((predicat or "").upper())
    if verifier is None:
        return None
    propres = [l for l in (lignes or []) if isinstance(l, str) and l.strip()]
    if not propres or not isinstance(objet, str):
        return NON_APPUYE
    return VERIFIE if verifier(objet, propres) else NON_APPUYE


# --- Recettes de FORME (plan L1bis.2, Sources v1 §2) ------------------------------------------------
# Elles constatent seulement que les lignes citées ont la FORME d'une décision (APPLIQUE_REGLE) ou d'une déclaration de
# donnée (DETIENT) — pas que la phrase est vraie : le sens reste au juge d'appui. Chaînes et commentaires sont ignorés.
FORME_OK, FORME_ABSENTE = "ok", "absente"
_COMMENTAIRE_LIGNE_RE = re.compile(r"#.*|//.*|--.*")
_DECISION_RES = [re.compile(m) for m in (
    r"\b(?:if|elif|match|case|raise|assert|abort|throw|HTTPException)\b",   # condition, refus, erreur, validation
    r"\breturn\b.*\b4\d\d\b",                                              # return … 4xx
    r"\s\?\s.+\s:\s",                                                      # ternaire C/JS
    r"@(?:field_)?validator\b|\bField\(.*\b(?:gt|ge|lt|le|max_length|min_length|unique)\s*=",  # pydantic, SQLModel
    r"\.(?:where|filter|filter_by)\(",                                      # une requête restreinte : une règle d'accès
    r"\b(?:cascade_delete\s*=\s*True|ondelete\s*=|cascade\s*=)",           # une suppression en cascade déclarée
)] + [re.compile(r"\bCHECK\s*\(", re.I)]                                    # contrainte SQL
_DONNEE_RES = [re.compile(m, f) for m, f in (
    (r"^\s*class\s+\w+\s*\([^)]*\b(?:Base|BaseModel|Model|DeclarativeBase|SQLModel|Document)\b", 0),
    (r"\btable\s*=\s*True\b|\bmapped_column\(|\bMapped\[|\bRelationship\(|\brelationship\(", 0),  # SQLModel, SA 2
    (r"^\s*@(?:dataclasses\.)?dataclass\b", 0),
    (r"\bCREATE\s+TABLE\b|\bALTER\s+TABLE\b", re.I),
    (r"\bColumn\(|\bmodels\.\w+Field\(", 0),
    (r"^\s*(?:export\s+)?(?:interface\s+\w+|type\s+\w+\s*=)", 0),       # schéma / interface TypeScript
    (r"\bop\.(?:create_table|add_column)\(|\bmigrations\.CreateModel\(", 0),  # migration
)]
_FORMES = {"APPLIQUE_REGLE": _DECISION_RES, "DETIENT": _DONNEE_RES}


def forme(predicat: str, lignes: list[str]) -> str | None:
    """'ok' si les lignes ont la forme attendue du prédicat, 'absente' sinon ; None si le prédicat n'a pas de recette
    de forme. Ne prouve jamais le sens."""
    motifs = _FORMES.get((predicat or "").upper())
    if motifs is None:
        return None
    nues = [_COMMENTAIRE_LIGNE_RE.sub("", l) for l in _masquer(list(lignes or []))]
    return FORME_OK if any(m.search(l) for l in nues for m in motifs) else FORME_ABSENTE
