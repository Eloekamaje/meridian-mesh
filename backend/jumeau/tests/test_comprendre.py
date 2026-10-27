"""Le résumé d'un jumeau : les sept questions de « comprendre une application », prouvées et révisables."""
from jumeau import comprendre, depot
from jumeau.source_git import sha_courant
from jumeau.tests.conftest import ACTIVITE, JUMEAU, besoin_pg, claim

FICHE = """# Fiche vivante — TBT

## À quoi elle sert
- **Gérer les dossiers** des personnes accompagnées `app.py#L1-L2`
- Présenter la solution aux évaluateurs `app.py#L3` et `app.py#L4`
- Une capacité sans preuve

## Pour qui, dans quels parcours
- Agents de terrain : saisie hors ligne `app.py#L5`

## Les règles qu'elle applique
- Accès d'urgence avec double approbation `inconnu.py#L1`

## Comment elle vit
- Refonte le 25 octobre `app.py#L6`

## Ce que l'on ne sait pas encore
- Qui s'en sert réellement
"""


def test_sections_de_la_fiche_lues_par_question():
    s = comprendre.sections(FICHE)
    assert [t for t, _ in s["sert"]] == ["Gérer les dossiers des personnes accompagnées",
                                         "Présenter la solution aux évaluateurs", "Une capacité sans preuve"]
    assert s["sert"][1][1] == [("", "app.py", 3, 3), ("", "app.py", 4, 4)]
    assert s["inconnu"] == [("Qui s'en sert réellement", [])]
    assert s["informations"] == [] and s["echanges"] == []


@besoin_pg
def test_les_lignes_prouvees_deviennent_des_connaissances_revisables(conn, depot_git):
    source = {"nom": "tbt-repo", "type": "GIT", "emplacement": str(depot_git), "curseur": sha_courant(depot_git)}
    depot.enregistrer(conn, JUMEAU, source, [claim("fastapi", source["curseur"], 1)], ACTIVITE)
    sources = depot.sources_du_jumeau(conn, "tbt")
    comprendre.consigner(conn, JUMEAU, sources, FICHE, "modele-test")
    objets = {(c["predicat"], c["objet"]) for c in depot.lister_claims(conn, "tbt")}
    assert ("REALISE_CAPACITE", "Gérer les dossiers des personnes accompagnées") in objets
    assert ("SERT_ACTEUR", "Agents de terrain : saisie hors ligne") in objets
    assert not any(o == "Une capacité sans preuve" for _, o in objets)            # pas de preuve, pas de connaissance
    assert not any(p == "APPLIQUE_REGLE" for p, _ in objets)                      # citation fausse
    # Une capacité validée par l'équipe reste, même si la fiche suivante ne la reprend plus ; les autres sont closes.
    cid = next(c["id"] for c in depot.lister_claims(conn, "tbt") if c["objet"].startswith("Présenter"))
    depot.reviser(conn, cid, "alice", "ACCEPTED", None)
    comprendre.consigner(conn, JUMEAU, sources, "## À quoi elle sert\n- Suivre les orientations `app.py#L7`\n", "m")
    restants = {c["objet"] for c in depot.lister_claims(conn, "tbt") if c["predicat"] in comprendre.PREDICATS}
    assert restants == {"Présenter la solution aux évaluateurs", "Suivre les orientations"}
