"""Revue d'un jumeau né du code (POST /jumeaux/{jid}/examiner) : l'application présentée à tout employé.

Trois niveaux, comme le jumeau la présente dans sa fiche vivante (méthode comprendre-application) : en 30
secondes, une journée avec elle, quatre blocs courts ; puis, pour aller plus loin, les sept questions et leurs
connaissances prouvées. Les faits que le harness connaît mieux que le modèle (statut, responsable, sources lues ou
non branchées, confirmations de l'équipe) sont calculés ici, pas rédigés.
"""
import re

from jumeau import comprendre, connaissance, depot, gardien

STATUTS = {"observation": "en observation", "actif": "admis dans le Mesh", "en construction": "en construction"}
DOCUMENTS = re.compile(r"\.(md|rst|txt|adoc)$|(^|/)(docs?|memory)/", re.IGNORECASE)
NON_BRANCHEES = ["Exploitation", "Incidents", "Base de données"]


def _maturite(claims):
    return {"croisees": sum(c.get("maturite") == "M3" for c in claims), "validees": sum(c.get("maturite") == "M4" for c in claims),
            # Ce que le code ne peut pas établir : écrit par le modèle, il ne compte pas comme compréhension (L1bis.2).
            "hypotheses": sum(not connaissance.prouvable(c.get("predicat")) for c in claims)}


ETATS = ("verifie", "selon", "recoupe", "conteste", "en_partie", "non_appuye")
A_REVOIR = {"non_appuye": "Non appuyée par sa preuve", "en_partie": "Appuyée en partie seulement"}
MAX_A_REVOIR = 8


def _verification(claims):
    """Combien de connaissances dans chaque état de vérification (Harness v3 §2) ; « a_verifier » : pas encore vérifiées."""
    etats = [(c.get("verification") or {}).get("etat") for c in claims]
    return {**{e: etats.count(e) for e in ETATS}, "a_verifier": etats.count(None) + etats.count("en_attente")}


def _a_revoir(claims):
    """Ce que sa preuve n'appuie pas (ou seulement en partie) ne se présente pas : c'est dans « ce que j'ignore »."""
    lignes = [f"{A_REVOIR[e]} : {c['objet']}" for c in claims
              if (e := (c.get("verification") or {}).get("etat")) in A_REVOIR]
    reste = len(lignes) - MAX_A_REVOIR
    return lignes[:MAX_A_REVOIR] + ([f"… et {reste} autre(s), dans « Pour aller plus loin »"] if reste > 0 else [])


def _lignes_troncature(troncature):
    return [f"Code : lu en partie — {t['gardes']} {famille} sur {t['trouves']}{'+' if t.get('au_moins') else ''} (plafond)"
            for famille, t in (troncature or {}).items()]


def _sources(claims, contradictions=(), code=True, troncature=None):
    chemins = {p["chemin"] for c in claims for p in c.get("preuves") or []}
    confirmees = sum(c["statut"] == "ACCEPTED" for c in claims if c["predicat"] in comprendre.PREDICATS)
    return ([({"nom": "Code", "etat": "lu en partie" if troncature else "lu", "ok": not troncature}) if code else {"nom": "Code", "etat": "inaccessible (progiciel)", "ok": False}]
            + ([{"nom": "Documentation", "etat": "lue", "ok": True}] if any(DOCUMENTS.search(c) for c in chemins) else [])
            + [{"nom": "Équipe", "etat": f"{confirmees} confirmée(s)" if confirmees else "rien de confirmé",
                "ok": bool(confirmees)}]
            + [{"nom": n, "etat": "non branchée", "ok": False} for n in NON_BRANCHEES]
            + ([{"nom": "Contradictions", "etat": f"{len(contradictions)} ouverte(s)", "ok": False}] if contradictions else []))


def depuis_connaissances(jumeau, claims, fiche, contradictions=(), substance="code", troncature=None):
    f = comprendre.lire_fiche(fiche)
    trente = f["trente"]["texte"] + f["trente"]["puces"]
    criticite = next((t.split(":", 1)[1].strip() for t in trente if t.lower().startswith("criticité")), "inconnue")
    presentation = {
        "phrases": [t for t in trente if not t.lower().startswith("criticité")],
        "reperes": {"statut": STATUTS.get(jumeau.get("statut"), jumeau.get("statut") or "inconnu"),
                    "responsable": jumeau.get("proprietaire") or "à confirmer", "criticite": criticite,
                    "cmdb": jumeau.get("ci") or "non rattachée", "substance": substance},
        "journee": " ".join(f["journee"]["texte"] + f["journee"]["puces"]),
        "blocs": [{"cle": cle, "titre": titre, "items": f[cle]["puces"] or f[cle]["texte"]}
                  for cle, titre in comprendre.PRESENTATION if cle in ("faire", "regles", "garde", "avec")],
        "sources": _sources(claims, contradictions, substance == "code", troncature),
        "maturite": _maturite(claims),
        "verification": _verification(claims),
        "contradictions": [{k: x.get(k) for k in ("id", "enonce", "preuve_a", "systeme_a", "preuve_b", "systeme_b")}
                           for x in contradictions],
        "ignore": f["ignore"]["puces"] + f["ignore"]["texte"]
                  + _lignes_troncature(troncature)
                  + _a_revoir(claims)
                  + [f"Contradiction à trancher : {x['enonce']} ({x['systeme_a']} contre {x['systeme_b']})" for x in contradictions],
    }
    questions = [{"cle": cle, "titre": titre,
                  "items": [{"texte": c["objet"], "statut": c["statut"], "verification": c.get("verification")}
                            for c in claims if c["predicat"] == predicat]}
                 for cle, titre, predicat, _ in comprendre.QUESTIONS if predicat]
    return {"identite": {k: jumeau.get(k) for k in ("nom", "mission", "domaine")},
            "presentation": presentation, "comprendre": questions}


def examiner(conn, jumeau_id, doc):
    fiche = gardien.fiche_courante(conn, jumeau_id)
    return depuis_connaissances(doc, depot.lister_claims(conn, jumeau_id), fiche and fiche["contenu"],
                                depot.contradictions_ouvertes(conn, jumeau_id),
                                depot.substance(depot.types_de_sources(conn, jumeau_id)) or "code",
                                depot.troncature(conn, jumeau_id))
