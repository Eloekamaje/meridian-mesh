"""Revue d'un jumeau né du code : présentée à tout employé, par niveaux, faits calculés par le harness."""
from meridian.adapters.outbound.postgres import examen

def claim(predicat, objet, statut="PROPOSED", chemin="app.py"):
    return {"predicat": predicat, "objet": objet, "statut": statut, "preuves": [{"chemin": chemin}]}


CLAIMS = [claim("REALISE_CAPACITE", "Gérer les dossiers", "ACCEPTED"), claim("APPLIQUE_REGLE", "Double approbation"),
          claim("REALISE_CAPACITE", "Présenter la solution", chemin="memory/PRD.md"), claim("DEPEND_DE", "fastapi")]
FICHE = """# Fiche vivante

## En 30 secondes
Une maquette qui montre le suivi de **dossiers** `memory/PRD.md#L4`.
Elle sert à convaincre des évaluateurs.
Criticité : faible — aucune donnée réelle

## Une journée avec elle
Une agente ouvre un dossier.
Un réviseur le vérifie.

## Ce qu'elle permet de faire
- Ouvrir un dossier hors ligne `app.py#L3`

## Les règles à retenir
- Pas d'orientation sans consentement `app.py#L9`

## Avec qui elle travaille
Personne : maquette autonome `memory/PRD.md#L3`.

## D'où je le sais, et ce que j'ignore
- Qui l'utilisera réellement
"""


def test_presentation_par_niveaux():
    e = examen.depuis_connaissances({"nom": "X", "statut": "observation", "proprietaire": "Équipe Y"}, CLAIMS, FICHE)
    p = e["presentation"]
    assert p["phrases"] == ["Une maquette qui montre le suivi de dossiers.", "Elle sert à convaincre des évaluateurs."]
    assert p["reperes"] == {"statut": "en observation", "responsable": "Équipe Y", "criticite": "faible — aucune donnée réelle",
                            "cmdb": "non rattachée", "substance": "code"}
    assert p["journee"] == "Une agente ouvre un dossier. Un réviseur le vérifie."
    assert [(b["cle"], b["items"]) for b in p["blocs"]] == [
        ("faire", ["Ouvrir un dossier hors ligne"]), ("regles", ["Pas d'orientation sans consentement"]),
        ("garde", []), ("avec", ["Personne : maquette autonome."])]
    assert p["ignore"] == ["Qui l'utilisera réellement"]
    sources = {s["nom"]: s["etat"] for s in p["sources"]}
    assert sources["Documentation"] == "lue" and sources["Équipe"] == "1 confirmée(s)"
    assert sources["Exploitation"] == "non branchée"
    assert "fastapi" not in str(e)


def test_pour_aller_plus_loin_les_sept_questions():
    e = examen.depuis_connaissances({"nom": "X"}, CLAIMS, None)
    blocs = {b["cle"]: b["items"] for b in e["comprendre"]}
    assert blocs["sert"] == [{"texte": "Gérer les dossiers", "statut": "ACCEPTED", "verification": None},
                             {"texte": "Présenter la solution", "statut": "PROPOSED", "verification": None}]
    assert e["presentation"]["reperes"]["responsable"] == "à confirmer"
    assert e["presentation"]["reperes"]["criticite"] == "inconnue"


def test_reperes_de_substance_et_code_non_lu_sans_code():
    r = examen.depuis_connaissances({"nom": "P", "ci": "CI-1"}, [], FICHE, substance="interfaces observées (Datadog)")
    assert r["presentation"]["reperes"]["substance"] == "interfaces observées (Datadog)"
    assert r["presentation"]["reperes"]["cmdb"] == "CI-1"
    assert {"nom": "Code", "etat": "inaccessible (progiciel)", "ok": False} in r["presentation"]["sources"]
    avec = examen.depuis_connaissances({"nom": "P"}, [], FICHE)
    assert avec["presentation"]["reperes"]["substance"] == "code"
    assert {"nom": "Code", "etat": "lu", "ok": True} in avec["presentation"]["sources"]


def test_verification_comptee_et_non_appuyee_hors_presentation():
    def v(objet, etat):
        return {**claim("APPLIQUE_REGLE", objet), "verification": {"etat": etat, "raison": "r"}}
    claims = [v("A", "verifie"), v("B", "selon"), v("C", "non_appuye"), v("D", "en_partie"), claim("DEPEND_DE", "x")]
    p = examen.depuis_connaissances({"nom": "X"}, claims, FICHE)["presentation"]
    assert p["verification"] == {"verifie": 1, "selon": 1, "recoupe": 0, "conteste": 0, "en_partie": 1, "non_appuye": 1,
                                 "incertain": 0,
                                 "a_verifier": 1}
    assert p["ignore"] == ["Qui l'utilisera réellement", "Non appuyée par sa preuve : C", "Appuyée en partie seulement : D"]


def test_a_revoir_borne():
    claims = [{**claim("APPLIQUE_REGLE", f"R{i}"), "verification": {"etat": "non_appuye"}} for i in range(11)]
    ignore = examen.depuis_connaissances({"nom": "X"}, claims, FICHE)["presentation"]["ignore"]
    assert len(ignore) == 1 + examen.MAX_A_REVOIR + 1 and ignore[-1].startswith("… et 3 autre(s)")


def test_une_regle_etablie_par_la_forme_ne_compte_pas_comme_hypothese():
    # Les compteurs lisent la maturité, seule vérité : une règle passée M2 (forme + juge) n'est plus une hypothèse.
    claims = [{**claim("APPLIQUE_REGLE", "R1"), "maturite": "M2"}, {**claim("APPLIQUE_REGLE", "R2"), "maturite": "M1"},
              {**claim("SERT_ACTEUR", "Lecteurs"), "maturite": "M1"}, {**claim("DEPEND_DE", "x"), "maturite": "M2"}]
    assert examen.depuis_connaissances({"nom": "X"}, claims, FICHE)["presentation"]["maturite"]["hypotheses"] == 2
