"""Résolveur de contexte : surfaces, identifiants explicites et divulgation progressive."""
from copy import deepcopy
from datetime import date, datetime

import pytest

from meridian.domain import contexte
from meridian.domain import profils
from meridian.application import resolveur_contexte as resolveur

PROFIL = profils.CATALOGUE_PROFILS["developpeur"]
DOSSIER = {
    "tenant": "banque",
    "question": "Que change le paiement ?",
    "propositions": [
        {"specialiste": "impact", "type": "IMPACT", "titre": "Impact paiements",
         "resume": "Deux applications aval", "preuves": ["p1", "p2"], "confiance": 0.95,
         "donnees": {"twin_id": "paiements"}},
        {"specialiste": "preuve", "type": "RISQUE", "titre": "Risque comptes",
         "resume": "Preuve partielle", "preuves": ["p3"], "confiance": 0.85,
         "donnees": {"twin_id": "comptes"}},
        {"specialiste": "outcome", "type": "QUESTION", "titre": "Mesurer ?",
         "resume": "Baseline absente", "preuves": [], "confiance": 0.55,
         "donnees": {"situation_id": "sit-1"}},
        {"specialiste": "impact", "type": "IMPACT", "titre": "Impact cartes",
         "resume": "Un flux aval", "preuves": ["p4"], "confiance": 0.80,
         "donnees": {"twin_id": "cartes"}},
        {"specialiste": "preuve", "type": "PREUVE", "titre": "Contrat stable",
         "resume": "Contrat lu", "preuves": ["p5"], "confiance": 0.75,
         "donnees": {"twin_id": "contrats"}},
        {"specialiste": "impact", "type": "IMPACT", "titre": "Impact crédit",
         "resume": "Deux consommateurs", "preuves": ["p6"], "confiance": 0.70,
         "donnees": {"twin_id": "credit"}},
        {"specialiste": "preuve", "type": "LIMITE", "titre": "Source partielle",
         "resume": "Une source manque", "preuves": ["p7"], "confiance": 0.60,
         "donnees": {"twin_id": "sources"}},
    ],
    "limites": ["source partielle"],
}


@pytest.mark.parametrize(
    ("surface", "options", "entites", "domaine"),
    [
        ("atlas", {"domaine": "paiements", "twin_id": "paiements"}, ("paiements",), "paiements"),
        ("twin", {"twin_id": "paiements"}, ("paiements",), None),
        ("situation", {"situation_id": "sit-1"}, ("sit-1",), None),
        ("work", {"work_id": "wrk-1"}, ("wrk-1",), None),
        ("global", {}, (), None),
    ],
)
def test_chaque_surface_se_resout_sans_inventer_d_identifiant(surface, options, entites, domaine):
    """Chaque surface retient uniquement les sélecteurs qui lui sont propres."""
    resolu = resolveur.resoudre("banque", surface, **options)

    assert resolu.tenant == "banque"
    assert resolu.surface == surface
    assert resolu.entites == entites
    assert resolu.domaine == domaine
    assert resolu.scope == "tenant"
    assert resolu.source
    assert resolveur.resoudre("banque", surface.upper(), **options).surface == surface


def test_atlas_accepte_le_domaine_seul_et_le_twin_seul():
    """L'Atlas peut être résolu par domaine, par Twin, ou sans sélection."""
    par_domaine = resolveur.resoudre("banque", "atlas", domaine="paiements")
    par_twin = resolveur.resoudre("banque", "atlas", twin_id="paiements")
    global_atlas = resolveur.resoudre("banque", "atlas")

    assert par_domaine.entites == () and par_domaine.domaine == "paiements"
    assert par_twin.entites == ("paiements",) and par_twin.domaine is None
    assert global_atlas.entites == () and global_atlas.domaine is None


@pytest.mark.parametrize(
    ("surface", "options"),
    [
        ("twin", {}),
        ("situation", {}),
        ("work", {}),
        ("twin", {"situation_id": "sit-1"}),
        ("situation", {"twin_id": "paiements"}),
        ("work", {"situation_id": "sit-1"}),
        ("global", {"twin_id": "paiements"}),
        ("global", {"domaine": "paiements"}),
    ],
)
def test_identifiant_manquant_ou_hors_surface_leve(surface, options):
    """Un identifiant obligatoire absent ou ambigu ne produit jamais un contexte."""
    with pytest.raises(resolveur.ContexteInvalide):
        resolveur.resoudre("banque", surface, **options)


@pytest.mark.parametrize("surface", ["inconnue", "", "atlas-inconnu", None, 42])
def test_surface_inconnue_leve(surface):
    """Une surface hors énumération est refusée avec l'exception dédiée."""
    with pytest.raises(resolveur.SurfaceInconnue):
        resolveur.resoudre("banque", surface)


@pytest.mark.parametrize("tenant", [None, "", "   ", "banque/est", "banque ouest", 42])
def test_tenant_invalide_leve(tenant):
    """Le tenant doit être un identifiant non vide et sans espace."""
    with pytest.raises(resolveur.ContexteInvalide):
        resolveur.resoudre(tenant, "global")


@pytest.mark.parametrize(
    ("valeur", "attendue"),
    [
        ("2026-10-31", "2026-10-31"),
        (" 2026-10-31 ", "2026-10-31"),
        ("2024-02-29", "2024-02-29"),
        (date(2026, 10, 31), "2026-10-31"),
        (datetime(2026, 10, 31, 23, 30), "2026-10-31"),
        ("2026-10-31T23:30:00Z", "2026-10-31"),
        (None, None),
    ],
)
def test_date_iso_valide_et_normalisee(valeur, attendue):
    """La période rendue est toujours une date ISO ou None."""
    resolu = resolveur.resoudre("banque", "global", date=valeur)
    assert resolu.periode == attendue


@pytest.mark.parametrize("valeur", ["2023-02-29", "31/12/2024", "", "2026-13-01", "pas-une-date", 20261031])
def test_date_invalide_leve(valeur):
    """Une date non ISO ou impossible est refusée."""
    with pytest.raises(resolveur.ContexteInvalide):
        resolveur.resoudre("banque", "global", date=valeur)


def test_perimetre_devient_le_scope_et_utilisateur_est_conserve():
    """Les permissions et l'utilisateur explicites sont portés par le contexte."""
    resolu = resolveur.resoudre(
        "banque", "twin", twin_id="paiements", utilisateur="alice@example.test",
        perimetre="equipe-paiements")

    assert resolu.utilisateur == "alice@example.test"
    assert resolu.scope == "equipe-paiements"
    assert resolu.as_dict() == {
        "tenant": "banque",
        "surface": "twin",
        "entites": ["paiements"],
        "domaine": None,
        "periode": None,
        "utilisateur": "alice@example.test",
        "scope": "equipe-paiements",
        "source": "twin_id",
    }


def test_le_pack_est_borne_et_reste_dans_le_tenant_resolu():
    """Le pack applique les budgets, porte le tenant explicite et son empreinte."""
    contexte_resolu = resolveur.resoudre("banque", "twin", twin_id="paiements")
    dossier_avant = deepcopy(DOSSIER)
    resultat = resolveur.construire_pack(
        contexte_resolu, DOSSIER, PROFIL, max_faits=2, max_preuves=2, max_entites=2)

    pack = resultat["pack"]
    assert resultat["surface"] == "twin"
    assert resultat["periode"] is None
    assert resultat["contexte"]["tenant"] == "banque"
    assert pack["tenant"] == "banque"
    assert len(pack["faits"]) == 2
    assert len(pack["preuves"]) <= 2
    assert len(pack["entites"]) <= 2
    assert pack["question"] == DOSSIER["question"]
    assert set(resultat) == {"contexte", "pack", "surface", "periode"}
    assert resolveur.fingerprint(resultat) == pack["fingerprint"]
    assert DOSSIER == dossier_avant


def test_le_pack_reprend_le_tenant_resolu_si_le_dossier_ne_le_porte_pas():
    """L'absence de tenant dans le dossier ne produit pas un pack hors tenant."""
    contexte_resolu = resolveur.resoudre("banque", "global")
    dossier = {cle: valeur for cle, valeur in DOSSIER.items() if cle != "tenant"}

    resultat = resolveur.construire_pack(contexte_resolu, dossier, PROFIL)

    assert resultat["pack"]["tenant"] == "banque"
    assert "tenant" not in dossier


def test_un_dossier_hors_tenant_est_refuse():
    """Un pack ne peut pas mélanger deux tenants."""
    contexte_resolu = resolveur.resoudre("autre-banque", "twin", twin_id="paiements")
    with pytest.raises(resolveur.ContexteInvalide):
        resolveur.construire_pack(contexte_resolu, DOSSIER, PROFIL)


def test_resume_detail_expandre_sans_mutation_ni_nouveau_fait():
    """Le résumé tronque, le détail complète, l'expansion cible sans muter le pack."""
    contexte_resolu = resolveur.resoudre("banque", "twin", twin_id="paiements")
    resultat = resolveur.construire_pack(contexte_resolu, DOSSIER, PROFIL)
    pack = contexte.construire("Question ?", PROFIL, DOSSIER)
    avant = deepcopy(pack.as_dict())

    court = resolveur.resume(pack, limite=2)
    complet = resolveur.detail(pack)
    cible = resolveur.expandre(pack, ["p1"])

    assert len(court["faits"]) == 2 and court["tronque"] is True
    assert len(complet["faits"]) == len(pack.faits)
    assert cible["faits"] and cible["preuves"] == ["p1"]
    assert resolveur.fingerprint(court) == pack.fingerprint
    assert resolveur.fingerprint(complet) == pack.fingerprint
    assert resolveur.fingerprint(cible) == pack.fingerprint
    assert resolveur.expandre(pack, ["inconnu"])["faits"] == []
    assert resolveur.expandre(pack, ["inconnu"])["preuves"] == []
    assert pack.as_dict() == avant

    court["faits"][0]["titre"] = "modifié"
    complet["faits"][0]["preuves"].append("ajout")
    cible["faits"][0]["preuves"].append("ajout")
    assert pack.as_dict() == avant
    assert resultat["pack"]["tenant"] == "banque"


def test_construire_pack_refuse_un_contexte_non_resolu():
    """Le résolveur n'invente pas un contexte à partir d'un objet quelconque."""
    with pytest.raises(resolveur.ContexteInvalide):
        resolveur.construire_pack({"surface": "twin"}, DOSSIER, PROFIL)


def test_construire_pack_transmet_le_budget_tokens_et_les_signaux_partiels():
    """Le résolveur borne aussi en tokens et conserve contradictions/preuves périmées."""
    contexte_resolu = resolveur.resoudre("banque", "twin", twin_id="paiements")
    dossier = deepcopy(DOSSIER)
    dossier["statut"] = "partiel"
    dossier["contradictions"] = ["Deux impacts se contredisent"]
    dossier["preuves_perimees"] = ["p-archive"]
    dossier["propositions"][0]["perime"] = True

    resultat = resolveur.construire_pack(
        contexte_resolu, dossier, PROFIL, max_tokens=50, max_faits=3)

    pack = resultat["pack"]
    assert pack["budget"]["tokens"] == 50
    assert "tokens_utilises" in pack["budget"]
    assert pack["completude"] == "partiel"
    assert "Deux impacts se contredisent" in pack["contradictions"]
    assert "p-archive" in pack["preuves_perimees"]
    assert "p1" in pack["preuves_perimees"]
    assert any("tokens" in limite or "partiel" in limite for limite in pack["limites"])


def test_resume_et_detail_conservent_inconnues_contradictions_et_preuves_perimees():
    """La divulgation progressive ne masque jamais les signaux d'incertitude."""
    pack = resolveur.construire_pack(
        resolveur.resoudre("banque", "global"), DOSSIER, PROFIL)["pack"]
    pack["inconnues"] = ["Inconnue explicite"]
    pack["contradictions"] = ["Contradiction explicite"]
    pack["preuves_perimees"] = ["preuve-perimee"]
    pack["completude"] = "partiel"

    court = resolveur.resume(pack, limite=1)
    complet = resolveur.detail(pack)

    for vue in (court, complet):
        assert vue["inconnues"] == ["Inconnue explicite"]
        assert vue["contradictions"] == ["Contradiction explicite"]
        assert vue["preuves_perimees"] == ["preuve-perimee"]
        assert vue["completude"] == "partiel"
