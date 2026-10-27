"""Comprendre une application : sept questions auxquelles le jumeau répond, preuves à l'appui.

La fiche vivante est rédigée selon ces questions. Les lignes des cinq premières deviennent des connaissances
(capacités d'affaires, acteurs et parcours, informations détenues, règles, échanges), chacune prouvée par sa
citation et révisable par l'équipe. Le code reste la preuve, pas le résumé.
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


def consigner(conn, jumeau, sources, fiche, modele):
    """Les lignes prouvées de la fiche deviennent des connaissances proposées ; celles que la fiche ne reprend plus
    sont closes, sauf si l'équipe les a déjà validées ou contestées. Renvoie le nombre de connaissances tenues."""
    tenues = []
    for cle, lignes in sections(fiche).items():
        predicat, type_claim = next((q[2], q[3]) for q in QUESTIONS if q[0] == cle)
        if not predicat:
            continue
        for texte, citations in lignes:
            for depot_cite, chemin, debut, fin in citations:  # la première citation vérifiable sert de preuve
                try:
                    source = connaissance.resoudre_source(sources, depot_cite, chemin)
                    tenues.append(connaissance.proposer(conn, jumeau, source, predicat, texte, type_claim, chemin,
                                                        debut, fin, "Fiche vivante du gardien", "gardien", modele))
                    break
                except (LookupError, ValueError):
                    continue
    conn.execute(
        "UPDATE claim SET valide_jusqua = now() WHERE jumeau_id = %s AND predicat = ANY(%s) AND origine = 'CONVERSATION' "
        "AND statut = 'PROPOSED' AND valide_jusqua IS NULL AND NOT (id = ANY(%s))",
        (jumeau["id"], sorted(PREDICATS), tenues))
    return len(tenues)
