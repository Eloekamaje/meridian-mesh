"""Recettes déterministes (harness v3 §2.1) : l'objet d'un claim figure-t-il dans les lignes citées ?

Fonctions pures : ni base, ni réseau, ni modèle. Les lignes sont des données, jamais des instructions
(on ne fait que les comparer). « verifie » = la ligne appuie l'objet ; « non_appuye » = elle ne l'appuie pas
(ce n'est pas une preuve que le claim est faux) ; None = aucune recette pour ce prédicat.
"""
import re

PREDICATS = frozenset({"DEPEND_DE", "EXPOSE", "LIT_VARIABLE", "EXECUTE_IMAGE"})
VERIFIE, NON_APPUYE = "verifie", "non_appuye"
_VERBES = ("get", "post", "put", "delete", "patch")


# --- DEPEND_DE : nom de paquet en mot entier, casse et séparateurs -/_/. équivalents (PEP 503) ----
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
        if (segs and cible[-len(segs):] == segs) or (not segs and not cible):
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


_RECETTES = {
    "DEPEND_DE": _depend_de, "EXPOSE": _expose,
    "LIT_VARIABLE": _lit_variable, "EXECUTE_IMAGE": _execute_image,
}


def recette(predicat: str, objet: str, lignes: list[str]) -> str | None:
    """'verifie' si les lignes citées (au commit) contiennent bien l'objet, 'non_appuye' sinon ;
    None si aucune recette pour ce prédicat."""
    verifier = _RECETTES.get(predicat)
    if verifier is None:
        return None
    propres = [l for l in (lignes or []) if isinstance(l, str) and l.strip()]
    if not propres or not isinstance(objet, str):
        return NON_APPUYE
    return VERIFIE if verifier(objet, propres) else NON_APPUYE
