"""Ce que le jumeau sait de lui-même, et ce qu'il peut faire de ce savoir en conversation.

Fonctions sans LLM, partagées par les outils de l'agent et l'API. Tout ce qui touche au code se lit au SHA ingéré.
"""
import hashlib
import re

from psycopg.rows import dict_row

from jumeau import depot, recoupement, temps
from jumeau.adaptateur import preuve
from jumeau.lecteurs import RE_CITATION_SOURCE
from jumeau.source_git import lire_au_sha

FAMILLES = {
    "EXPOSE": "interfaces",
    "DEPEND_DE": "dépendances",
    "LIT_VARIABLE": "réglages lus",
    "EXECUTE_IMAGE": "images",
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
    """Claims valides, en forme compacte pour un LLM : objet, statut, maturité, preuve, état de vérification."""
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            """SELECT c.id, c.predicat, c.objet, c.type, c.statut, c.maturite, c.confiance::float AS confiance,
                      (SELECT p.locator FROM claim_preuve cp JOIN preuve p ON p.id = cp.preuve_id
                       WHERE cp.claim_id = c.id ORDER BY p.id DESC LIMIT 1) AS preuve
               FROM claim c
               WHERE c.jumeau_id = %s AND c.valide_jusqua IS NULL
                 AND (%s::text IS NULL OR c.predicat = %s)
                 AND (%s::text IS NULL OR c.objet ILIKE '%%' || %s || '%%')
               ORDER BY c.predicat, c.objet LIMIT %s""",
            (jumeau_id, predicat, predicat, recherche, recherche, limite)).fetchall()
    etats = recoupement.etats(conn, jumeau_id)
    return [{**c, "verification": etats.get(c["id"])} for c in lignes]


def _claim_proposee(jumeau, predicat, objet, type_claim):
    if type_claim not in TYPES_CLAIM:
        raise ValueError(f"type inconnu : {type_claim} (attendus : {', '.join(sorted(TYPES_CLAIM))})")
    predicat = re.sub(r"[^A-Z_]", "", predicat.upper().replace(" ", "_"))[:40]
    objet = " ".join(objet.split())[:300]  # une ligne : pas de texte multi-lignes réinjectable
    if not predicat or not objet:
        raise ValueError("prédicat et objet requis")
    if predicat in FAMILLES:
        raise ValueError(f"{predicat} est réservé à l'extraction structurelle du code")
    return {"sujet": jumeau["nom"], "predicat": predicat, "objet": objet, "type": type_claim,
            "confiance": CONFIANCE_PROPOSITION}


def _preuve_depot(source, chemin, debut, fin):
    """Preuve de code (ou de documentation du dépôt) lue au SHA ingéré ; ValueError si les lignes n'existent pas."""
    lignes = lire_au_sha(source.get("copie") or source["emplacement"], source["curseur"])(chemin)
    if lignes is None or debut < 1 or fin < debut or fin > len(lignes) or fin - debut >= MAX_LIGNES:
        raise ValueError(f"preuve introuvable : {chemin}#L{debut}-L{fin}")
    return preuve(source["nom"], source["curseur"][:12], chemin, lignes, debut, fin)


def _preuve_source(lecteur, citation):
    """Preuve d'une source branchée, vérifiée par son lecteur, avec le hash du texte cité."""
    citation = citation.strip("` ")
    m = RE_CITATION_SOURCE.fullmatch(citation)
    if not m or not lecteur.verifier(citation):
        raise ValueError(f"preuve introuvable : {citation}")
    debut = int(m["debut"])
    fin = int(m["fin"] or debut)
    if fin - debut >= MAX_LIGNES:
        raise ValueError(f"preuve trop longue : {citation}")
    lu = lecteur.lire(m["ref"], debut, fin, version=m["version"])
    texte = "\n".join(lu["lignes"])
    return {"type": lecteur.nature.upper(), "locator": lu["locator"], "chemin": lu["ref"], "sha": lu["version"],
            "ligne_debut": debut, "ligne_fin": fin, "citation": texte, "hash": hashlib.sha256(texte.encode()).hexdigest()}


def proposer(conn, jumeau, source, predicat, objet, type_claim, chemin, debut, fin, justification, acteur, modele):
    """Le jumeau propose une connaissance ; la preuve doit exister au SHA. Jamais validée ici (revue humaine)."""
    c = _claim_proposee(jumeau, predicat, objet, type_claim)
    p = _preuve_depot(source, chemin, debut, fin)
    activite = {"extracteur": "jumeau-conversation", "modele": modele, "acteur": acteur,
                "justification": justification[:1000]}
    return depot.enregistrer_proposition(conn, jumeau, source["id"], c, p, activite)


def proposer_source(conn, jumeau, lecteur, predicat, objet, type_claim, citation, justification, acteur, modele):
    """Comme `proposer`, mais la preuve est une citation `systeme://espace/ref@version#La-Lb` d'une source branchée :
    le lecteur la vérifie, puis elle est enregistrée avec le hash du texte cité."""
    c = _claim_proposee(jumeau, predicat, objet, type_claim)
    p = _preuve_source(lecteur, citation)
    activite = {"extracteur": "jumeau-conversation", "modele": modele, "acteur": acteur,
                "justification": justification[:1000]}
    return depot.enregistrer_proposition(conn, jumeau, lecteur.source_id, c, p, activite)


def recouper(conn, jumeau, sources, lecteurs, claim_id, citation, raison, acteur, modele):
    """Ajoute à une connaissance existante une seconde preuve, d'un autre système que les siennes (code ou documentation
    du dépôt `chemin#La-Lb` au SHA ingéré, ou source branchée `systeme://…`). Ni statut ni objet ne changent : le juge
    rejoue la vérification. Vrai si la preuve est nouvelle."""
    citation = citation.strip("` ")
    m = RE_CITATION_SOURCE.fullmatch(citation)
    if m:
        lecteur = next((l for l in lecteurs if l.systeme == m["systeme"] and l.espace == m["espace"]), None)
        if not lecteur:
            raise LookupError(f"source inconnue : {citation}")
        source_id, p, type_source = lecteur.source_id, _preuve_source(lecteur, citation), lecteur.systeme.upper()
    else:
        mc = RE_CITATION.fullmatch(citation)
        if not mc:
            raise ValueError(f"citation attendue (chemin#Ldébut-Lfin ou systeme://espace/ref@version#Ldébut) : {citation}")
        depot_nom, chemin, debut, fin = decouper(mc)
        source = resoudre_source(sources, depot_nom, chemin)
        source_id, p, type_source = source["id"], _preuve_depot(source, chemin, debut, fin), "GIT"
    nouveau = recoupement.systeme_de_preuve(p.get("type", "CODE"), p["chemin"], type_source)

    def meme_systeme(existants):
        if set(existants) == {nouveau}:
            raise ValueError(f"ce n'est pas un recoupement : une autre source du même système ({nouveau})")

    activite = {"extracteur": "jumeau-conversation", "modele": modele, "acteur": acteur, "justification": raison[:1000]}
    return depot.ajouter_preuve(conn, jumeau, claim_id, source_id, p, activite, meme_systeme)


def _ancrer_lignes(conn, jumeau, source, claim_id, chemin, debut, fin, raison, origine):
    lu = lire_code(source, chemin, debut, fin)  # LookupError / ValueError si le fichier ou les lignes n'existent pas
    if not lu["locator"].endswith(f"#L{debut}-L{fin}"):
        raise ValueError(f"lignes introuvables ou trop longues : {chemin}#L{debut}-L{fin}")
    return depot.ancrer(conn, jumeau, claim_id, source["id"], chemin, debut, fin, lu["locator"], raison, origine)


def ancrer(conn, jumeau, sources, claim_id, citation_code, raison, origine="AGENT"):
    """Rattache une connaissance de source à des lignes de code vérifiées au SHA ingéré ; vrai si nouvelle. Pas une preuve."""
    m = RE_CITATION.fullmatch(citation_code.strip("` "))
    if not m:
        raise ValueError(f"citation de code attendue (chemin#Ldébut-Lfin) : {citation_code}")
    depot_nom, chemin, debut, fin = decouper(m)
    source = resoudre_source(sources, depot_nom, chemin)
    return _ancrer_lignes(conn, jumeau, source, claim_id, chemin, debut, fin, raison, origine)


CLE_JIRA = "[A-Z][A-Z0-9]+-[0-9]+"
MAX_ANCRES_JIRA = 5  # fichiers ancrés par connaissance


def ancrer_jira(conn, jumeau, sources):
    """Ancrage du harness : une connaissance prouvée par un ticket Jira est ancrée (fichier, ligne 1) aux fichiers
    des commits dont le titre cite ce ticket. Rejouable ; renvoie le nombre d'ancres créées."""
    lignes = conn.execute(
        "SELECT DISTINCT cp.claim_id, p.chemin FROM claim_preuve cp JOIN preuve p ON p.id = cp.preuve_id "
        "JOIN source so ON so.id = p.source_id JOIN claim c ON c.id = cp.claim_id "
        "WHERE c.jumeau_id = %s AND c.valide_jusqua IS NULL AND cp.role = 'SUPPORT' AND so.type = 'JIRA' "
        "AND p.chemin ~ %s", (jumeau["id"], f"^{CLE_JIRA}$")).fetchall()
    creees = 0
    for claim_id, cle in lignes:
        restant = MAX_ANCRES_JIRA
        for source in sources:
            for commit in temps.commits_citant(source, cle):
                for chemin in commit["fichiers"][:restant]:
                    try:
                        creees += _ancrer_lignes(conn, jumeau, source, claim_id, chemin, 1, 1,
                                                 f"fichier modifié par le commit {commit['sha']} ({cle})", "HARNESS")
                        restant -= 1
                    except (LookupError, ValueError):  # fichier supprimé depuis, ou vide : on passe
                        continue
    return creees


def autoportrait(jumeau, claims):
    """Identité du jumeau, déduite de ses Claims (sans LLM) : injectée dans son prompt système."""
    lignes = [f"Nom : {jumeau['nom']} · équipe propriétaire : {jumeau['equipe']}"]
    if jumeau.get("mission"):
        lignes.append(f"Mission déclarée par l'équipe : {jumeau['mission']} (domaine : {jumeau.get('domaine', 'À confirmer')})")
    # Extraction structurelle : seulement les comptes ; le détail se lit avec l'outil mes_connaissances.
    comptes = [f"{n} {titre}" for predicat, titre in FAMILLES.items()
               if (n := sum(c["predicat"] == predicat for c in claims))]
    if comptes:
        lignes.append("Extraction du code : " + ", ".join(comptes) + " — détail avec mes_connaissances")
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
