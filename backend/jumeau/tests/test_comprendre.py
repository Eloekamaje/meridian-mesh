"""Le résumé d'un jumeau : les sept questions de « comprendre une application », prouvées et révisables."""
from jumeau import comprendre, connaissance, depot, methodes
from jumeau.source_git import sha_courant
from jumeau.tests.conftest import ACTIVITE, JUMEAU, besoin_pg, claim

FICHE_NIVEAUX = """# Fiche vivante — TBT

## En 30 secondes
Une maquette de suivi de **dossiers** `app.py#L1`.

## Ce qu'elle permet de faire
- **Gérer les dossiers** des personnes accompagnées `app.py#L1-L2`
- Présenter la solution aux évaluateurs `app.py#L3` et `app.py#L4`
"""


def test_fiche_lue_par_niveaux():
    f = comprendre.lire_fiche(FICHE_NIVEAUX)
    assert f["trente"]["texte"] == ["Une maquette de suivi de dossiers."]
    assert f["faire"]["puces"] == ["Gérer les dossiers des personnes accompagnées",
                                   "Présenter la solution aux évaluateurs"]
    assert f["garde"] == {"puces": [], "texte": []}


def test_la_methode_et_la_revue_parlent_des_memes_questions():
    texte = " ".join(methodes.lire("comprendre-application").split())
    assert "comprendre-application" in {m["nom"] for m in methodes.catalogue()}
    for _, titre, predicat, type_claim in comprendre.QUESTIONS:
        assert f"**{titre}**" in texte
        if predicat:
            assert f"Prédicat {predicat}, type {type_claim}" in texte
    for _, titre in comprendre.PRESENTATION:
        assert f"## {titre}" in texte  # la fiche rédigée selon la méthode est lisible par la revue


@besoin_pg
def test_une_reponse_vaut_tant_que_sa_preuve_tient(conn, depot_git):
    import subprocess
    source = {"nom": "tbt-repo", "type": "GIT", "emplacement": str(depot_git), "curseur": sha_courant(depot_git)}
    depot.enregistrer(conn, JUMEAU, source, [claim("fastapi", source["curseur"], 1)], ACTIVITE)
    src = depot.source_du_jumeau(conn, "tbt")
    def proposer(objet, debut):
        return connaissance.proposer(conn, JUMEAU, src, "REALISE_CAPACITE", objet, "CAPABILITY", "app.py", debut,
                                     debut + 1, "preuve", "gardien", "m")
    proposer("Gérer les dossiers", 10)
    proposer("Suivre les colis", 20)
    validee = proposer("Payer", 30)
    depot.reviser(conn, validee, "alice", "ACCEPTED", None)
    assert comprendre.clore_sans_preuve(conn, "tbt") == 0  # rien n'a changé : tout tient
    # Nouveau commit : deux lignes ajoutées en tête (les preuves se déplacent), les lignes 20-21 et 30-31 réécrites.
    lignes = [f"ligne {n}" for n in range(1, 401)]
    lignes[19:21] = ["autre chose", "autre chose"]
    lignes[29:31] = ["réécrit", "réécrit"]
    (depot_git / "app.py").write_text("\n".join(["entête", "entête", *lignes]) + "\n")
    subprocess.run(["git", "-C", str(depot_git), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "m"],
                   check=True)
    depot.enregistrer(conn, JUMEAU, {**source, "curseur": sha_courant(depot_git)},
                      [claim("fastapi", sha_courant(depot_git), 1)], ACTIVITE)
    assert comprendre.clore_sans_preuve(conn, "tbt") == 1
    restants = {c["objet"] for c in depot.lister_claims(conn, "tbt") if c["predicat"] in comprendre.PREDICATS}
    assert restants == {"Gérer les dossiers", "Payer"}  # déplacée mais intacte ; validée par l'équipe


@besoin_pg
def test_fusion_de_deux_connaissances_qui_disent_la_meme_chose(conn, depot_git):
    import pytest
    source = {"nom": "tbt-repo", "type": "GIT", "emplacement": str(depot_git), "curseur": sha_courant(depot_git)}
    depot.enregistrer(conn, JUMEAU, source, [claim("fastapi", source["curseur"], 1)], ACTIVITE)
    src = depot.source_du_jumeau(conn, "tbt")
    def proposer(objet, debut, predicat="REALISE_CAPACITE"):
        return connaissance.proposer(conn, JUMEAU, src, predicat, objet, "CAPABILITY", "app.py", debut, debut,
                                     "preuve", "gardien", "m")
    garder, retirer = proposer("Gérer les dossiers", 10), proposer("Gérer les dossiers des personnes", 11)
    autre = proposer("Double approbation", 12, "APPLIQUE_REGLE")
    depot.fusionner(conn, "tbt", garder, retirer)
    restants = {c["objet"]: c for c in depot.lister_claims(conn, "tbt") if c["predicat"] in comprendre.PREDICATS}
    assert set(restants) == {"Gérer les dossiers", "Double approbation"}
    assert len(restants["Gérer les dossiers"]["preuves"]) == 2  # la preuve de la connaissance retirée est gardée
    with pytest.raises(ValueError):
        depot.fusionner(conn, "tbt", garder, autre)  # pas la même question
    depot.reviser(conn, garder, "alice", "ACCEPTED", None)
    with pytest.raises(ValueError):
        depot.fusionner(conn, "tbt", autre, garder)  # une connaissance validée par l'équipe ne se retire pas


@besoin_pg
def test_reouverture_de_ce_qui_reste_prouve(conn, depot_git):
    source = {"nom": "tbt-repo", "type": "GIT", "emplacement": str(depot_git), "curseur": sha_courant(depot_git)}
    depot.enregistrer(conn, JUMEAU, source, [claim("fastapi", source["curseur"], 1)], ACTIVITE)
    src = depot.source_du_jumeau(conn, "tbt")
    cid = connaissance.proposer(conn, JUMEAU, src, "DETIENT", "Les dossiers", "DATA_FLOW", "app.py", 3, 4, "p", "g", "m")
    conn.execute("UPDATE claim SET valide_jusqua = now() WHERE id = %s", (cid,))
    assert comprendre.rouvrir_prouvees(conn, "tbt") == 1
    assert "Les dossiers" in {c["objet"] for c in depot.lister_claims(conn, "tbt")}
