"""Schémas Mermaid dans les réponses de Flore : chaque flèche est une affirmation, vérifiée comme une phrase.

Flore écrit un bloc ```mermaid (flowchart) ; chaque flèche porte en commentaire ce qui la fonde : `%% c:<id>` (une
connaissance du jumeau) ou `%% r:<id>` (une relation du Mesh). Le harness, sans modèle, ne garde que les flèches
fondées sur ce qui tient (ni contesté, ni non appuyé, ni en partie), colore chacune selon son état, retire les
directives dangereuses et dit sous le schéma ce qui n'a pas été dessiné. L'interface dessine (mermaid, mode strict).
"""
import re

RE_BLOC = re.compile(r"```mermaid[ \t]*\n(.*?)(?:```|\Z)", re.DOTALL)
RE_REF = re.compile(r"%%\s*([cr]):([\w.-]+)\s*$")
RE_FLECHE = re.compile(r"<?(?:-{2,}|={2,}|-\.+-)[>ox]?")
# Une boîte : un identifiant (sans espace), puis éventuellement son libellé entre [ ], ( ), { } ou ([ ]) …
_BOITE = r"[A-Za-z_][\w-]*(?:\[[^\]\n]*\]|\([^)\n]*\)|\{[^}\n]*\}|\(\[[^\]\n]*\]\)|\[\([^)\n]*\)\])*"
# … et une flèche : boîte, flèche, libellé facultatif |…|, boîte. Sinon le dessin échouerait : la flèche est écartée.
RE_LIGNE_FLECHE = re.compile(rf"^{_BOITE}\s*<?(?:-{{2,}}|={{2,}}|-\.+-)[>ox]?\s*(?:\|[^|\n]*\|)?\s*{_BOITE}$")
RE_LIGNE_BOITE = re.compile(rf"^{_BOITE}$")
RE_BOITE_LIBELLEE = re.compile(r"([A-Za-z_][\w-]*)((?:\[[^\]\n]*\]|\([^)\n]*\)|\{[^}\n]*\})+)")


def _libelles(lignes):
    """{identifiant: forme et libellé} des boîtes, où qu'elles soient définies (y compris sur une flèche écartée)."""
    libelles = {}
    for ligne in lignes:
        sans_etiquette = re.sub(r"\|[^|\n]*\|", "", RE_REF.sub("", ligne))
        for ident, forme in RE_BOITE_LIBELLEE.findall(sans_etiquette):
            libelles.setdefault(ident, forme)
    return libelles
DEBUTS = ("flowchart", "graph")
INTERDITS = ("click", "%%{", "callback", "href")  # liens, scripts, directives d'initialisation (mode de sécurité)
MAX_LIGNES, MAX_CARACTERES = 60, 4000

NON_TENUES = ("non_appuye", "en_partie")
STYLES = {  # état → style de la flèche, et sa légende
    "valide": ("stroke:#4ADE80,stroke-width:3px", "vert épais = validé par l'équipe"),
    "verifie": ("stroke:#34D399,stroke-width:2px", "vert = vérifié"),
    "recoupe": ("stroke:#22D3EE,stroke-width:2px", "cyan = recoupé"),
    "selon": ("stroke:#93C5FD,stroke-width:1.5px", "bleu = d'après une seule source"),
    "conteste": ("stroke:#F2B84B,stroke-width:1.5px,stroke-dasharray:6 3", "orange pointillé = sources en désaccord"),
    "inconnu": ("stroke:#7C93A8,stroke-width:1px,stroke-dasharray:3 3", "gris pointillé = pas encore vérifié"),
}
ETATS_RELATION = {"confirmee": "verifie", "validee": "valide", "validation": "inconnu", "supposee": "inconnu"}


def _etat_connaissance(c):
    """État d'une connaissance pour le schéma, ou None si elle ne tient pas (on ne la dessine pas)."""
    if c is None or c.get("statut") == "CONTESTED":
        return None
    if c.get("statut") == "ACCEPTED":
        return "valide"
    etat = (c.get("verification") or {}).get("etat")
    return None if etat in NON_TENUES else (etat or "inconnu")


def _etat(ref, connaissances, relations):
    genre, ident = ref
    if genre == "c":
        return _etat_connaissance(connaissances.get(int(ident)) if ident.isdigit() else None)
    r = relations.get(ident)
    return ETATS_RELATION.get(r.get("etat")) if r else None


def _bloc(code, connaissances, relations):
    """(code mermaid vérifié ou None, flèches écartées, états des flèches gardées)."""
    lignes = [l for l in code[:MAX_CARACTERES].splitlines() if l.strip()][:MAX_LIGNES]
    if not lignes or not lignes[0].strip().lower().startswith(DEBUTS):
        return None, 0, []
    gardees, styles, ecartees, etats = [lignes[0].strip()], [], 0, []
    for ligne in lignes[1:]:
        brute = ligne.strip()
        if brute.lower().startswith(INTERDITS) or brute.lower().startswith("linkstyle"):
            continue  # le harness pose lui-même le style des flèches
        sans_ref = RE_REF.sub("", brute).strip()
        fleches = len(RE_FLECHE.findall(sans_ref))
        if not fleches:
            if RE_LIGNE_BOITE.match(sans_ref) or sans_ref.lower().startswith(("subgraph", "end", "direction")):
                gardees.append(brute)  # boîte ou sous-graphe : décor, pas une affirmation
            continue  # commentaire isolé, ligne illisible
        ref = RE_REF.search(brute)
        lisible = fleches == 1 and RE_LIGNE_FLECHE.match(sans_ref)
        etat = _etat(ref.groups(), connaissances, relations) if ref and lisible else None
        if etat is None:  # sans fondement, fondement qui ne tient pas, ou plusieurs flèches sur une ligne
            ecartees += 1
            continue
        styles.append(f"linkStyle {len(etats)} {STYLES[etat][0]}")
        etats.append(etat)
        gardees.append(brute)
    if not etats:
        return None, ecartees, []
    # Une boîte gardée garde son libellé, même s'il n'était écrit que sur une flèche écartée.
    definies = _libelles(gardees[1:])
    utilisees = {i for l in gardees[1:] for i in re.findall(r"(?<![\w\[(|{])([A-Za-z_][\w-]*)(?![\w-])",
                                                             re.sub(r"\[[^\]]*\]|\([^)]*\)|\{[^}]*\}|\|[^|]*\||%%.*", "", l))}
    a_libeller = [f"{i}{forme}" for i, forme in _libelles(lignes[1:]).items() if i in utilisees and i not in definies]
    return "\n".join(gardees[:1] + a_libeller + gardees[1:] + styles), ecartees, etats


def verifier(texte, connaissances, relations=None):
    """Réécrit chaque bloc mermaid du texte : seules restent les flèches fondées, avec leur état et une légende.
    `connaissances` : {id: connaissance (statut, verification)} ; `relations` : {id: relation du Mesh (etat)}."""
    relations = relations or {}

    def remplacer(m):
        code, ecartees, etats = _bloc(m.group(1), connaissances, relations)
        if code is None:
            return f"(Schéma non affiché : {ecartees} lien(s) sans preuve qui les appuie.)" if ecartees else ""
        legende = " · ".join(STYLES[e][1] for e in STYLES if e in etats)
        note = f" · {ecartees} lien(s) non dessiné(s) : leur preuve ne les appuie pas" if ecartees else ""
        return f"```mermaid\n{code}\n```\nLégende : {legende}{note}."

    return RE_BLOC.sub(remplacer, texte)
