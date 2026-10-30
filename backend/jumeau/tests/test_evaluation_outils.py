"""Tests du jeu d'or hors ligne : choix d'outils, critères, porte et robustesse."""
import json

import pytest

from jumeau import capacites, evaluation_outils as eo, interface_outils, interfaces, mcp_outils


def cas(identifiant, attendus, interdits=(), criteres=None, tags=(), poids=1.0):
    return eo.CasOr(
        id=identifiant,
        question=f"Question {identifiant} ?",
        outils_attendus=tuple(attendus),
        outils_interdits=tuple(interdits),
        criteres=criteres or {},
        tags=tuple(tags),
        poids=poids,
    )


def texte_avec_preuve(cas_courant):
    return "src/app.py#L10-L20" if cas_courant.criteres.get("must_cite_preuve") else ""


def test_selecteur_parfait_atteint_un():
    jeu = eo.JeuOr()
    jeu.ajouter(cas("resolution", ("resoudre_application",), tags=("resolution",)))
    jeu.ajouter(cas("conception", ("concevoir_architecture",), tags=("conception",)))

    resultat = eo.evaluer(jeu, lambda courant: list(courant.outils_attendus))

    assert resultat["passe"] == resultat["total"] == 2
    assert resultat["pass_rate"] == 1.0
    assert resultat["score_moyen"] == 1.0
    assert resultat["faux_positifs"] == resultat["faux_negatifs"] == 0
    assert all(detail["ok"] and detail["score"] == 1.0 for detail in resultat["details"])
    assert isinstance(resultat["resultats"][0], eo.ResultatCas)
    assert resultat["resultats"][0]["ok"] is True


def test_selection_partielle_score_la_couverture_et_compte_un_faux_negatif():
    jeu = eo.JeuOr().ajouter(cas(
        "mobilisation", ("resoudre_application", "mobiliser_jumeaux")))
    resultat = eo.evaluer(jeu, lambda courant: ["resoudre_application"])
    detail = resultat["details"][0]

    assert detail["ok"] is False
    assert detail["score"] == 0.5
    assert resultat["passe"] == 0
    assert resultat["faux_negatifs"] == 1
    assert any("manquants" in raison for raison in detail["raisons"])


def test_un_outil_interdit_annule_le_score_et_compte_un_faux_positif():
    jeu = eo.JeuOr().ajouter(cas(
        "conception", ("concevoir_architecture",), interdits=("mobiliser_jumeaux",)))
    resultat = eo.evaluer(jeu, lambda courant: ["concevoir_architecture", "mobiliser_jumeaux"])
    detail = resultat["details"][0]

    assert detail["ok"] is False
    assert detail["score"] == 0.0
    assert resultat["faux_positifs"] == 1
    assert any("interdits" in raison for raison in detail["raisons"])


def test_un_outil_en_trop_sans_interdiction_reste_un_faux_positif_partiel():
    jeu = eo.JeuOr().ajouter(cas("resolution", ("resoudre_application",)))
    resultat = eo.evaluer(jeu, lambda courant: ["resoudre_application", "concevoir_architecture"])
    detail = resultat["details"][0]

    assert detail["ok"] is False
    assert detail["score"] == 0.5
    assert resultat["faux_positifs"] == 1
    assert any("en trop" in raison for raison in detail["raisons"])


def test_pass_at_k_reussit_si_un_essai_est_exact():
    jeu = eo.JeuOr().ajouter(cas("resolution", ("resoudre_application",)))

    def instable(courant):
        instable.appels += 1
        return ["concevoir_architecture"] if instable.appels == 1 else ["resoudre_application"]

    instable.appels = 0
    sans_reprise = eo.evaluer(jeu, instable, pass_k=1)
    assert sans_reprise["passe"] == 0

    instable.appels = 0
    avec_reprise = eo.evaluer(jeu, instable, pass_k=2)
    assert avec_reprise["passe"] == 1
    assert avec_reprise["pass_rate"] == 1.0
    assert avec_reprise["resultats"][0].score == 1.0


def test_repetitions_moyennent_les_meilleurs_essais_sans_cacher_un_succes():
    jeu = eo.JeuOr().ajouter(cas("resolution", ("resoudre_application",)))

    def instable(courant):
        instable.appels += 1
        return ["resoudre_application"] if instable.appels % 2 else ["concevoir_architecture"]

    instable.appels = 0
    resultat = eo.evaluer(jeu, instable, pass_k=1, repetitions=2)

    assert resultat["passe"] == 1
    assert resultat["resultats"][0].score == 0.5


def test_porte_par_tags_et_seuil_global():
    jeu = eo.JeuOr()
    jeu.ajouter(cas("resolution", ("resoudre_application",), tags=("resolution",)))
    jeu.ajouter(cas("temporel", ("mobiliser_jumeaux",), tags=("temporel",)))

    def selectionneur(courant):
        if "temporel" in courant.tags:
            return []
        return list(courant.outils_attendus)

    resultat = eo.evaluer(jeu, selectionneur)
    assert resultat["pass_rate"] == 0.5
    assert resultat["par_tag"]["resolution"]["pass_rate"] == 1.0
    assert resultat["par_tag"]["temporel"]["pass_rate"] == 0.0

    assert eo.seuils(jeu, resultat, minimum=0.5)["verdict"] == "PASS"
    assert eo.seuils(jeu, resultat, minimum=0.75)["verdict"] == "FAIL"
    assert eo.seuils(jeu, resultat, minimum=0.5, tags_obligatoires=("temporel",))["verdict"] == "FAIL"
    assert eo.seuils(jeu, resultat, minimum=0.5, tags_obligatoires=("resolution",))["verdict"] == "PASS"
    absent = eo.seuils(jeu, resultat, minimum=0.5, tags_obligatoires=("inconnu",))
    assert absent["verdict"] == "FAIL"
    assert any("absent" in motif for motif in absent["motifs"])


def test_chargement_json_liste_et_objet(tmp_path):
    liste = [cas("a", ("resoudre_application",)).as_dict(),
             cas("b", ("concevoir_architecture",), tags=("conception",)).as_dict()]
    fichier = tmp_path / "jeu.json"
    fichier.write_text(json.dumps(liste), encoding="utf-8")

    jeu = eo.JeuOr(seed=7).charger_json(fichier)
    assert jeu.seed == 7
    assert jeu.taille == len(jeu) == 2
    assert [element.id for element in jeu.cas] == ["a", "b"]

    autre = eo.JeuOr().charger_json(json.dumps({"cas": liste[:1]}))
    assert autre.taille == 1
    assert autre.cas[0].id == "a"

    texte = eo.JeuOr().charger_json(json.dumps(liste[1:]))
    assert texte.taille == 1


@pytest.mark.parametrize("donnees", [
    {"question": "sans identifiant", "outils_attendus": ["resoudre_application"]},
    {"id": "c", "question": "sans attendus"},
    {"id": "c", "question": "mauvais type", "outils_attendus": 3},
    {"id": "c", "question": "chaîne au lieu d'une liste", "outils_attendus": "resoudre_application"},
    {"id": "c", "question": "outil à la fois attendu et interdit",
     "outils_attendus": ["resoudre_application"], "outils_interdits": ["resoudre_application"]},
    {"id": "c", "question": "poids nul", "outils_attendus": ["resoudre_application"], "poids": 0},
    {"id": "c", "question": "champ inconnu", "outils_attendus": ["resoudre_application"],
     "inconnu": True},
])
def test_cas_malforme_refuse(donnees):
    with pytest.raises(eo.CasInvalide):
        eo.JeuOr().charger_json(json.dumps([donnees]))


def test_json_invalide_et_doublon_ne_modifient_pas_le_jeu():
    jeu = eo.JeuOr().charger_json(json.dumps([cas("a", ("resoudre_application",)).as_dict()]))
    with pytest.raises(eo.CasInvalide):
        jeu.charger_json("{")
    with pytest.raises(eo.CasInvalide):
        jeu.charger_json(json.dumps([cas("a", ("concevoir_architecture",)).as_dict()]))
    assert jeu.taille == 1
    assert jeu.cas[0].outils_attendus == ("resoudre_application",)


def test_aucun_secret_ne_fuit_dans_les_resultats():
    jeu = eo.JeuOr().ajouter(cas("resolution", ("resoudre_application",)))

    def selectionneur(courant):
        return ["api_key=supersecret123", "https://user:motdepasse@hote.test/outil",
                "resoudre_application"]

    resultat = eo.evaluer(jeu, selectionneur)
    sortie = json.dumps({"details": resultat["details"]}, ensure_ascii=False)
    assert "supersecret123" not in sortie
    assert "motdepasse" not in sortie
    assert "***" in sortie

    def en_panne(courant):
        raise RuntimeError("token=abcd123456")

    panne = eo.evaluer(jeu, en_panne)
    assert "abcd123456" not in json.dumps(panne["details"], ensure_ascii=False)
    assert panne["details"][0]["raisons"][0].startswith("selectionneur en erreur")


def test_chargement_refuse_un_secret():
    donnees = [{"id": "c", "question": "api_key=abcdef123", "outils_attendus": ["x"]}]
    with pytest.raises(eo.CasInvalide):
        eo.JeuOr().charger_json(json.dumps(donnees))


def test_critere_must_cite_preuve_est_obligatoire():
    jeu = eo.JeuOr().ajouter(cas(
        "preuve", ("mobiliser_jumeaux",), criteres={"must_cite_preuve": True}))

    sans = eo.evaluer(jeu, lambda courant: {"outils": ["mobiliser_jumeaux"], "texte": "réponse"})
    assert sans["passe"] == 0
    assert sans["details"][0]["score"] == 0.0

    avec = eo.evaluer(jeu, lambda courant: {
        "outils": ["mobiliser_jumeaux"], "texte": "src/app.py#L10-L12"})
    assert avec["passe"] == 1

    source = eo.evaluer(jeu, lambda courant: {
        "outils": ["mobiliser_jumeaux"], "texte": "jira://PAY/PAY-1@3#L10-L20"})
    assert source["passe"] == 1


def test_critere_must_not_write_refuse_une_ecriture():
    jeu = eo.JeuOr().ajouter(cas(
        "lecture", ("decrire_outil",), criteres={"must_not_write": True}))
    interdit = eo.evaluer(jeu, lambda courant: ["decrire_outil", "comptes.creercompte"])
    assert interdit["passe"] == 0
    assert interdit["details"][0]["score"] == 0.0
    autorise = eo.evaluer(jeu, lambda courant: ["decrire_outil"])
    assert autorise["passe"] == 1


def test_selectionneur_asynchrone_est_execute():
    async def selectionneur(courant):
        return list(courant.outils_attendus)

    jeu = eo.JeuOr().ajouter(cas("resolution", ("resoudre_application",)))
    resultat = eo.evaluer(jeu, selectionneur)
    assert resultat["passe"] == 1


def test_jeu_cognitif_valide_et_couvre_les_facettes():
    rapport = eo.valider(eo.JEU_COGNITIF)
    assert rapport["valide"] is True
    assert 6 <= eo.JEU_COGNITIF.taille <= 8
    identifiants = [courant.id for courant in eo.JEU_COGNITIF.cas]
    assert len(identifiants) == len(set(identifiants))
    tags = {tag for courant in eo.JEU_COGNITIF.cas for tag in courant.tags}
    assert {"resolution", "mobilisation", "conception", "interface", "preuve",
            "temporel", "attention", "mcp", "openapi"} <= tags
    for courant in eo.JEU_COGNITIF.cas:
        assert courant.outils_attendus
        assert set(courant.outils_attendus).isdisjoint(courant.outils_interdits)
        assert courant.question.strip()


def test_les_noms_du_jeu_cognitif_sont_reels():
    noms = {manifeste.nom for manifeste in capacites.manifestes_integres()}
    noms |= {"rechercher_outil", "decrire_outil"}

    contrat = interfaces.Contract(
        id="ctr-comptes", format="openapi", version="1.0.0", digest="reference",
        locator="reference", application_id="comptes", environment="prod")
    operations = [
        interfaces.Operation(id="op-lister", contract_id="ctr-comptes", protocol="rest",
                             method="GET", path="/comptes", name="listerComptes",
                             version="1.0.0", environment="prod"),
        interfaces.Operation(id="op-creer", contract_id="ctr-comptes", protocol="rest",
                             method="POST", path="/comptes", name="creerCompte",
                             version="1.0.0", environment="prod"),
    ]
    graphe = interfaces.InterfaceGraph(contracts=[contrat], operations=operations)
    noms |= {manifeste.nom for manifeste in interface_outils.manifests_depuis_interface(graphe)}
    noms |= {manifeste.nom for manifeste in mcp_outils.manifests_depuis_outils(
        "atlas", [{"name": "chercher", "inputSchema": {},
                   "annotations": {"readOnlyHint": True}}])}

    for courant in eo.JEU_COGNITIF.cas:
        assert set(courant.outils_attendus) <= noms
        assert set(courant.outils_interdits) <= noms


def test_le_jeu_cognitif_passe_avec_un_selectionneur_complet():
    def selectionneur(courant):
        return {"outils": list(courant.outils_attendus), "texte": texte_avec_preuve(courant)}

    resultat = eo.evaluer(eo.JEU_COGNITIF, selectionneur)
    assert resultat["passe"] == resultat["total"]
    assert resultat["pass_rate"] == 1.0
    assert resultat["faux_positifs"] == resultat["faux_negatifs"] == 0
    assert eo.seuils(eo.JEU_COGNITIF, resultat, minimum=1.0)["verdict"] == "PASS"


def test_le_jeu_cognitif_passe_avec_une_simple_liste_d_outils():
    resultat = eo.evaluer(eo.JEU_COGNITIF, lambda courant: list(courant.outils_attendus))
    assert resultat["pass_rate"] == 1.0


def test_cli_valide_le_jeu_integre(capsys):
    assert eo.main(["--valider", "--seuil", "0.9"]) == 0
    sortie = json.loads(capsys.readouterr().out)
    assert sortie["valide"] is True
    assert sortie["cas"] == eo.JEU_COGNITIF.taille

    assert eo.main([]) == 0
    affichage = json.loads(capsys.readouterr().out)
    assert affichage["jeu"] == "JEU_COGNITIF"
    assert affichage["seuil"] == 0.8
    assert len(affichage["cas"]) == eo.JEU_COGNITIF.taille
    assert affichage["schema"]["required"] == ["id", "question", "outils_attendus"]
