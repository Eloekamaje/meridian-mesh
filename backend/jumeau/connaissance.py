"""Ce que le jumeau sait de lui-même, et ce qu'il peut faire de ce savoir en conversation.

Fonctions sans LLM, partagées par les outils de l'agent et l'API. Tout ce qui touche au code se lit au SHA ingéré.
"""
import hashlib
import re

from psycopg.rows import dict_row

from jumeau import depot
from jumeau.adaptateur import preuve
from jumeau.source_git import lire_au_sha

FAMILLES = {
    "EXPOSE": "APIs exposées",
    "DEPEND_DE": "Dépendances logicielles",
    "LIT_VARIABLE": "Configuration lue",
    "EXECUTE_IMAGE": "Images exécutées",
}
# ClaimTypes du Domain_Model §13.
TYPES_CLAIM = {
    "DEPENDENCY", "CAPABILITY", "BUSINESS_RULE", "DATA_FLOW", "OWNERSHIP", "PROCESS_STEP", "API_USAGE",
    "CHANGE", "FUNCTIONALITY", "RISK", "BEHAVIOR", "CUSTOMER_IMPACT", "EMPLOYEE_IMPACT",
}
MAX_LIGNES = 200
# Citation : forme longue git://depot@sha:chemin#La-Lb, ou courte [depot:]chemin#La[-Lb] (le dépôt est facultatif
# quand le jumeau n'en a qu'un, ou quand un seul dépôt contient le fichier). Le chemin commence un mot (ni URL, ni
# « v1.2 ») et porte une extension de fichier.
RE_CITATION = re.compile(
    r"(?:git://(?P<depot_long>[^\s@`]+)@[0-9a-f]+:|(?<![\w/:.-])(?:(?P<depot>[A-Za-z0-9_.-]+):(?!//))?)"
    r"(?P<chemin>[A-Za-z_][\w.-]*(?:/[\w.-]+)*\.[A-Za-z]\w*)#L(?P<debut>\d+)(?:-L(?P<fin>\d+))?")
# Même motif sans groupes nommés, pour le composer (plusieurs citations dans une même expression).
MOTIF_CITATION = re.sub(r"\(\?P<\w+>", "(?:", RE_CITATION.pattern)


def decouper(m):
    """(dépôt ou "", chemin, début, fin) d'une citation trouvée par RE_CITATION."""
    debut = int(m.group("debut"))
    return (m.group("depot_long") or m.group("depot") or "", m.group("chemin"), debut, int(m.group("fin") or debut))


def cle_citation(depot, chemin, debut, fin):
    """Identifiant d'une citation, tel que l'écrit Flore (avec son dépôt s'il est précisé)."""
    return f"{depot + ':' if depot else ''}{chemin}#L{debut}-L{fin}"


def resoudre_source(sources, depot, chemin):
    """Le dépôt d'une citation : celui nommé, sinon le seul dépôt du jumeau, sinon le seul qui contient le fichier."""
    if depot:
        source = next((s for s in sources if s["nom"] == depot), None)
        if not source:
            raise LookupError(f"dépôt inconnu : {depot} (connus : {', '.join(s['nom'] for s in sources)})")
        return source
    if len(sources) == 1:
        return sources[0]
    candidates = [s for s in sources if lire_au_sha(s.get("copie") or s["emplacement"], s["curseur"])(chemin) is not None]
    if len(candidates) != 1:
        raise LookupError(f"{chemin} : préciser le dépôt ({', '.join(s['nom'] for s in sources)})")
    return candidates[0]


MAX_VALIDEES_PROMPT = 50
CONFIANCE_PROPOSITION = 0.5  # une interprétation du LLM vaut moins qu'une extraction structurelle


def lire_code(source, chemin, debut, fin):
    """Lignes [debut, fin] du fichier au SHA ingéré, bornées à MAX_LIGNES, avec leur locator."""
    lignes = lire_au_sha(source.get("copie") or source["emplacement"], source["curseur"])(chemin)
    if lignes is None:
        raise LookupError(f"{chemin} absent au SHA {source['curseur'][:12]}")
    if debut < 1 or debut > len(lignes) or fin < debut:
        raise ValueError(f"{chemin} compte {len(lignes)} lignes")
    fin_lue = min(fin, len(lignes), debut + MAX_LIGNES - 1)
    return {
        "locator": f"git://{source['nom']}@{source['curseur'][:12]}:{chemin}#L{debut}-L{fin_lue}",
        "lignes": [{"n": n, "texte": lignes[n - 1]} for n in range(debut, fin_lue + 1)],
        "tronque": fin_lue < min(fin, len(lignes)),
    }


def connaissances(conn, jumeau_id, predicat=None, recherche=None, limite=80):
    """Claims valides, en forme compacte pour un LLM : objet, statut, maturité, première preuve."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """SELECT c.id, c.predicat, c.objet, c.type, c.statut, c.maturite, c.confiance::float AS confiance,
                      (SELECT p.locator FROM claim_preuve cp JOIN preuve p ON p.id = cp.preuve_id
                       WHERE cp.claim_id = c.id ORDER BY p.id DESC LIMIT 1) AS preuve
               FROM claim c
               WHERE c.jumeau_id = %s AND c.valide_jusqua IS NULL
                 AND (%s::text IS NULL OR c.predicat = %s)
                 AND (%s::text IS NULL OR c.objet ILIKE '%%' || %s || '%%')
               ORDER BY c.predicat, c.objet LIMIT %s""",
            (jumeau_id, predicat, predicat, recherche, recherche, limite)).fetchall()


def proposer(conn, jumeau, source, predicat, objet, type_claim, chemin, debut, fin, justification, acteur, modele):
    """Le jumeau propose une connaissance ; la preuve doit exister au SHA. Jamais validée ici (revue humaine)."""
    if type_claim not in TYPES_CLAIM:
        raise ValueError(f"type inconnu : {type_claim} (attendus : {', '.join(sorted(TYPES_CLAIM))})")
    predicat = re.sub(r"[^A-Z_]", "", predicat.upper().replace(" ", "_"))[:40]
    objet = " ".join(objet.split())[:300]  # une ligne : pas de texte multi-lignes réinjectable
    if not predicat or not objet:
        raise ValueError("prédicat et objet requis")
    if predicat in FAMILLES:
        raise ValueError(f"{predicat} est réservé à l'extraction structurelle du code")
    lignes = lire_au_sha(source.get("copie") or source["emplacement"], source["curseur"])(chemin)
    if lignes is None or debut < 1 or fin < debut or fin > len(lignes) or fin - debut >= MAX_LIGNES:
        raise ValueError(f"preuve introuvable : {chemin}#L{debut}-L{fin}")
    p = preuve(source["nom"], source["curseur"][:12], chemin, lignes, debut, fin)
    activite = {"extracteur": "jumeau-conversation", "modele": modele, "acteur": acteur,
                "justification": justification[:1000]}
    c = {"sujet": jumeau["nom"], "predicat": predicat, "objet": objet, "type": type_claim,
         "confiance": CONFIANCE_PROPOSITION}
    return depot.enregistrer_proposition(conn, jumeau, source["id"], c, p, activite)


def autoportrait(jumeau, claims):
    """Identité du jumeau, déduite de ses Claims (sans LLM) : injectée dans son prompt système."""
    lignes = [f"Nom : {jumeau['nom']} · équipe propriétaire : {jumeau['equipe']}"]
    if jumeau.get("mission"):
        lignes.append(f"Mission déclarée par l'équipe : {jumeau['mission']} (domaine : {jumeau.get('domaine', 'À confirmer')})")
    for predicat, titre in FAMILLES.items():
        liste = [c for c in claims if c["predicat"] == predicat]
        if liste:
            objets = ", ".join(c["objet"] + (" ✓" if c["statut"] == "ACCEPTED" else "") for c in liste)
            lignes.append(f"{titre} ({len(liste)}) : {objets}")
    # Seules les propositions validées par l'équipe entrent dans le prompt : une proposition non revue,
    # éventuellement induite par du contenu malveillant du dépôt, ne doit pas s'injecter chez tous les membres.
    validees = [c for c in claims if c["predicat"] not in FAMILLES and c["statut"] == "ACCEPTED"][:MAX_VALIDEES_PROMPT]
    if validees:
        lignes.append("Connaissances validées par l'équipe : "
                      + "; ".join(f"{c['predicat']} {c['objet']}" for c in validees))
    return "\n".join(lignes)


def id_session(jumeau_id, acteur):
    """Un fil par membre et par jumeau (espace personnel) ; haché : sûr comme nom de dossier, sans collision."""
    return hashlib.sha256(f"{jumeau_id}\x00{acteur}".encode()).hexdigest()[:32]
