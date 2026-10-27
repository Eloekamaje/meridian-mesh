"""Comprendre une application : les sept questions de la méthode comprendre-application (methodes/).

Le savoir-faire est dans la méthode, que l'agent applique avec ses outils : c'est lui qui enquête et propose
chaque connaissance prouvée. Ce module n'en garde que ce qu'il faut au harness : les questions et leurs
prédicats (pour la revue), la lecture des sections de la fiche, et la tenue des comptes après une passe.
"""
import re

from jumeau import connaissance

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
RE_PUCE = re.compile(r"^\s*[-*]\s+(.*)")


def _cle_du_titre(titre):
    titre = titre.strip().strip("#").strip().lower().replace("’", "'")
    return next((cle for cle, t, *_ in QUESTIONS if titre.startswith(t.lower())), None)


def sections(fiche):
    """{clé : [(texte sans citations ni gras, [citations découpées])]} pour chacune des sept questions."""
    resultat, courante = {q[0]: [] for q in QUESTIONS}, None
    for ligne in (fiche or "").splitlines():
        if ligne.lstrip().startswith("#"):
            courante = _cle_du_titre(ligne)
            continue
        puce = RE_PUCE.match(ligne)
        if courante and puce:
            citations = [connaissance.decouper(m) for m in connaissance.RE_CITATION.finditer(puce.group(1))]
            texte = re.sub(r"\s*`[^`]*#L\d+[^`]*`", "", puce.group(1))
            texte = re.sub(r"\s+(et|,)\s*$", "", texte.replace("**", "")).strip(" ;,.")
            resultat[courante].append((" ".join(texte.split()), citations))
    return resultat


def clore_non_reprises(conn, jumeau_id, proposees):
    """Après une passe complète du gardien : les réponses qu'il n'a pas reprises sont closes, sauf si l'équipe les a
    déjà validées ou contestées. Une passe sans aucune proposition ne clôt rien (panne plutôt que changement)."""
    if not proposees:
        return 0
    return conn.execute(
        "UPDATE claim SET valide_jusqua = now() WHERE jumeau_id = %s AND predicat = ANY(%s) AND origine = 'CONVERSATION' "
        "AND statut = 'PROPOSED' AND valide_jusqua IS NULL AND NOT (id = ANY(%s))",
        (jumeau_id, sorted(PREDICATS), list(proposees))).rowcount
