"""Comprendre une application : les sept questions de la méthode comprendre-application (methodes/).

Le savoir-faire est dans la méthode, que l'agent applique avec ses outils : c'est lui qui enquête et propose
chaque connaissance prouvée. Ce module n'en garde que ce qu'il faut au harness : les questions et leurs
prédicats (pour la revue), la lecture des sections de la fiche, et la péremption des réponses dont la
preuve ne tient plus.
"""
import hashlib
import re

from jumeau import connaissance
from jumeau.source_git import lire_au_sha

# (clé, titre de section dans la fiche, prédicat de la connaissance, type de Claim)
QUESTIONS = [
    ("sert", "À quoi elle sert", "REALISE_CAPACITE", "CAPABILITY"),
    ("pour_qui", "Pour qui, dans quels parcours", "SERT_ACTEUR", "PROCESS_STEP"),
    ("informations", "Les informations qu'elle détient", "DETIENT", "DATA_FLOW"),
    ("regles", "Les règles qu'elle applique", "APPLIQUE_REGLE", "BUSINESS_RULE"),
    ("echanges", "Avec qui elle échange", "ECHANGE_AVEC", "DATA_FLOW"),
    ("vie", "Comment elle vit", None, None),
    ("inconnu", "Ce que l'on ne sait pas encore", None, None),
]
PREDICATS = {q[2] for q in QUESTIONS if q[2]}
# Sections de la fiche vivante, du plus court au plus détaillé (méthode comprendre-application, « Fiche vivante »).
PRESENTATION = [
    ("trente", "En 30 secondes"),
    ("journee", "Une journée avec elle"),
    ("faire", "Ce qu'elle permet de faire"),
    ("regles", "Les règles à retenir"),
    ("garde", "Ce qu'elle garde"),
    ("avec", "Avec qui elle travaille"),
    ("ignore", "D'où je le sais, et ce que j'ignore"),
]
RE_PUCE = re.compile(r"^\s*[-*]\s+(.*)")


def _propre(texte):
    """Texte lisible : sans citations ni gras Markdown."""
    texte = re.sub(r"\s*`[^`]*#L\d+[^`]*`", "", texte)
    texte = re.sub(r"\s+(et|,)\s*$", "", texte.replace("**", "")).strip(" ;,")
    return " ".join(texte.split())


def lire_fiche(fiche, titres=PRESENTATION):
    """{clé : {"puces": [texte], "texte": [paragraphe]}} pour chaque section de `titres` trouvée dans la fiche."""
    resultat, courante = {cle: {"puces": [], "texte": []} for cle, _ in titres}, None
    for ligne in (fiche or "").splitlines():
        if ligne.lstrip().startswith("#"):
            nom = ligne.strip().strip("#").strip().lower().replace("’", "'")
            courante = next((cle for cle, t in titres if nom.startswith(t.lower().replace("’", "'"))), None)
            continue
        if not courante or not ligne.strip():
            continue
        puce = RE_PUCE.match(ligne)
        if puce:
            resultat[courante]["puces"].append(_propre(puce.group(1)))
        else:
            resultat[courante]["texte"].append(_propre(ligne))
    return resultat


def _preuves_des_reponses(conn, jumeau_id, ouvertes):
    """(id, chemin, début, fin, empreinte, emplacement, copie, curseur) des réponses proposées, ouvertes ou closes."""
    return conn.execute(
        f"""SELECT c.id, p.chemin, p.ligne_debut, p.ligne_fin, p.hash, s.emplacement, s.copie, s.curseur
           FROM claim c
           JOIN LATERAL (SELECT p.* FROM claim_preuve cp JOIN preuve p ON p.id = cp.preuve_id
                         WHERE cp.claim_id = c.id ORDER BY p.id DESC LIMIT 1) p ON true
           JOIN source s ON s.id = p.source_id
           WHERE c.jumeau_id = %s AND c.predicat = ANY(%s) AND c.origine = 'CONVERSATION'
             AND c.statut = 'PROPOSED' AND c.valide_jusqua IS {"NULL" if ouvertes else "NOT NULL"}""",
        (jumeau_id, sorted(PREDICATS))).fetchall()


def _tiennent(lignes):
    """Ids dont la preuve tient au dernier commit (lignes identiques, même déplacées dans le fichier)."""
    lecteurs, tiennent = {}, set()
    for cid, chemin, debut, fin, empreinte, emplacement, copie, curseur in lignes:
        lire = lecteurs.setdefault((copie or emplacement, curseur), lire_au_sha(copie or emplacement, curseur))
        try:
            contenu = lire(chemin)
        except ValueError:
            contenu = None
        if contenu is not None and _citation_deplacee(contenu, fin - debut + 1, empreinte):
            tiennent.add(cid)
    return tiennent


def rouvrir_prouvees(conn, jumeau_id):
    """Rouvre les réponses proposées closes dont la preuve tient encore (réparation d'une clôture abusive)."""
    closes = _preuves_des_reponses(conn, jumeau_id, ouvertes=False)
    a_rouvrir = sorted(_tiennent(closes))
    if a_rouvrir:
        conn.execute("UPDATE claim SET valide_jusqua = NULL WHERE id = ANY(%s)", (a_rouvrir,))
    return len(a_rouvrir)


def clore_sans_preuve(conn, jumeau_id):
    """Une connaissance proposée vaut tant que sa preuve tient : les lignes citées existent encore, telles quelles,
    au dernier commit (même déplacées dans le fichier). Sinon elle est close ; celles que l'équipe a revues restent.
    Un agent qui oublie une réponse d'une passe à l'autre ne détruit donc rien de prouvé."""
    lignes = _preuves_des_reponses(conn, jumeau_id, ouvertes=True)
    tiennent = _tiennent(lignes)
    perimees = [cid for cid, *_ in lignes if cid not in tiennent]
    if perimees:
        conn.execute("UPDATE claim SET valide_jusqua = now() WHERE id = ANY(%s)", (perimees,))
    return len(perimees)


def _citation_deplacee(contenu, longueur, empreinte):
    return any(hashlib.sha256("\n".join(contenu[i:i + longueur]).encode()).hexdigest() == empreinte
               for i in range(len(contenu) - longueur + 1))
