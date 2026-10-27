"""Le résumé d'un jumeau : les sept questions de « comprendre une application », prouvées et révisables."""
from jumeau import comprendre, connaissance, depot, methodes
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


def test_la_methode_et_la_revue_parlent_des_memes_questions():
    texte = " ".join(methodes.lire("comprendre-application").split())
    assert "comprendre-application" in {m["nom"] for m in methodes.catalogue()}
    for _, titre, predicat, type_claim in comprendre.QUESTIONS:
        assert f"## {titre}" in texte  # la fiche rédigée selon la méthode est lisible par la revue
        if predicat:
            assert f"Prédicat {predicat}, type {type_claim}" in texte


@besoin_pg
def test_apres_une_passe_les_reponses_non_reprises_sont_closes(conn, depot_git):
    source = {"nom": "tbt-repo", "type": "GIT", "emplacement": str(depot_git), "curseur": sha_courant(depot_git)}
    depot.enregistrer(conn, JUMEAU, source, [claim("fastapi", source["curseur"], 1)], ACTIVITE)
    src = depot.source_du_jumeau(conn, "tbt")
    def proposer(objet):
        return connaissance.proposer(conn, JUMEAU, src, "REALISE_CAPACITE", objet, "CAPABILITY", "app.py", 1, 2,
                                     "preuve", "gardien", "m")
    ancienne, validee, reprise = proposer("Suivre les colis"), proposer("Gérer les dossiers"), proposer("Payer")
    depot.reviser(conn, validee, "alice", "ACCEPTED", None)
    assert comprendre.clore_non_reprises(conn, "tbt", []) == 0  # passe sans proposition : rien n'est clos
    assert comprendre.clore_non_reprises(conn, "tbt", [reprise]) == 1
    restants = {c["objet"] for c in depot.lister_claims(conn, "tbt") if c["predicat"] in comprendre.PREDICATS}
    assert restants == {"Gérer les dossiers", "Payer"}
