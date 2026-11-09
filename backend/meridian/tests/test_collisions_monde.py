"""Tests de caractérisation des collisions dev/cognition.

Référence : ``docs/MERIDIAN_Convergence_Dev_Cognition_v1.md`` (§2, §3, §5).
Chaque test ``test_collision_<n>_<sujet>`` épingle le comportement **divergent**
de l'ancien monde fusionné — l'assert documente la collision elle-même. Après
les phases 1-5 du plan §7, toutes ont basculé en XFAIL (la collision est
corrigée) ; elles portent désormais ``@pytest.mark.xfail(strict=True)`` :

- **XFAIL** — état sain : l'assert épinglé échoue, la divergence est résolue ;
- **XPASS** — régression : l'ancien comportement divergent est de retour, la
  suite échoue (``strict=True``), signal de réécrire la caractérisation.

Base réelle requise (``JUMEAU_PG_DSN``, fixture ``conn`` = schéma jetable par
test) ; les identifiants sont préfixés ``col-`` pour rester repérables.
"""
import inspect
from dataclasses import fields
from datetime import datetime, timezone

import pytest

from meridian.adapters.inbound.http import boucle as http_boucle
from meridian.adapters.outbound.postgres import (
    boucle,
    decision_travail,
    depot,
    detecteur_opportunites,
    entreprise_depot,
    journal_episodes,
    objets_exploitation as depot_exploitation,
    twins_types,
)
from meridian.application import commandes_boucle
from meridian.domain import attention
from meridian.domain import modele_entreprise as modele
from meridian.domain import objets_exploitation as domaine_exploit
from meridian.tests.conftest import besoin_pg

TENANT = "banque"


def _evenements(conn, tenant=TENANT):
    """``(objet_type, objet_id, action)`` consignés dans ``evenement_episode``."""
    lignes = conn.execute(
        "SELECT objet_type, objet_id, action FROM evenement_episode WHERE tenant_id = %s",
        (tenant,),
    ).fetchall()
    return {(ligne[0], ligne[1], ligne[2]) for ligne in lignes}


def _preparer_duplication(conn):
    """Deux applications ACCEPTED sur la même capacité twin (signature ``duplication``)."""
    for app_id, nom in (("col-app-a", "App A"), ("col-app-b", "App B")):
        twins_types.creer_twin(conn, TENANT, app_id, "APPLICATION", nom, acteur="alice")
    twins_types.creer_twin(
        conn, TENANT, "col-cap-1", "CAPABILITY", "Gérer les dossiers", acteur="alice")
    claim_ids = []
    for app_id in ("col-app-a", "col-app-b"):
        claim = twins_types.creer_claim(
            conn, TENANT, app_id, "REALISE_CAPACITE", "col-cap-1",
            source="referentiel", preuve="docs/capacites.md#L1",
            acteur="alice", texte=f"{app_id} réalise la capacité")
        depot.reviser(conn, claim["id"], "bob", "ACCEPTED", "vu en comité")
        claim_ids.append(claim["id"])
    return claim_ids


def _chaine(conn, *, titre="collision"):
    """Situation → Investigation canoniques, écrites par ``enregistrer_boucle``."""
    situation = commandes_boucle.creer_situation(boucle, conn, TENANT, titre=titre)
    investigation = commandes_boucle.ouvrir_investigation(
        boucle, conn, TENANT, situation.objet["id"], question=f"instruire {titre}")
    return situation.objet, investigation.objet


# ---------------------------------------------------------------------------
# COLLISION-1 (§2.1) : une HYPOTHESIS épistémique est relue en classe workflow.
# ``_CLASSES_LECTURE["HYPOTHESIS"] = HypothesisExploitation`` — la lecture typée
# canonique construit la mauvaise classe (champs perdus : rival_ids, need_id) et
# échoue dès ``as_dict=False`` ; le cycle workflow refuse EMISE en 409 permanent.
# ---------------------------------------------------------------------------


@besoin_pg
@pytest.mark.xfail(
    strict=True,
    reason="COLLISION-1 (doc §2.1) : la lecture canonique construit la classe "
    "workflow pour une HYPOTHESIS épistémique — phase 1 (CONJECTURE) doit faire "
    "basculer ce test")
def test_collision_1_hypothese_epistemique_relue_en_classe_workflow(conn):
    # Écriture épistémique : même producteur que detecteurs_besoins (B6) —
    # ``boucle.Hypothesis`` EMISE persistée par ``enregistrer_boucle``.
    hypothese = boucle.Hypothesis(
        id="col-hyp-epis-1", tenant_id=TENANT,
        enonce="l'usage observé contredit le contrat déclaré",
        statut="EMISE",
        rival_ids=["col-hyp-epis-2", "col-hyp-epis-3"],
        situation_id="col-sit-epis", need_id="col-need-epis")
    ligne = boucle.enregistrer_boucle(conn, TENANT, hypothese)
    assert ligne["type"] == "HYPOTHESIS"
    assert ligne["donnees"]["statut"] == "EMISE"
    assert ligne["donnees"]["rival_ids"] == ["col-hyp-epis-2", "col-hyp-epis-3"]

    # La classe construite par la lecture canonique est la classe workflow, pas
    # l'épistémique : ``rival_ids`` n'existe même pas parmi ses champs.
    assert boucle._CLASSES_LECTURE["HYPOTHESIS"] is domaine_exploit.Hypothesis
    assert "rival_ids" not in {f.name for f in fields(domaine_exploit.Hypothesis)}

    # Lecture ``as_dict=True`` (le seul chemin HTTP actuel) : ligne brute OK.
    relue = boucle.lire_boucle(conn, TENANT, "col-hyp-epis-1")
    assert relue["donnees"]["statut"] == "EMISE"

    # Lecture typée ``as_dict=False`` : la construction de la classe workflow
    # lève — ``investigation_id`` obligatoire absent, statut EMISE hors vocabulaire.
    with pytest.raises(domaine_exploit.ObjetsExploitationInvalide):
        boucle.lire_boucle(conn, TENANT, "col-hyp-epis-1", as_dict=False)

    # L'hypothèse épistémique remonte dans la liste workflow (vocabulaires mélangés).
    listees = commandes_boucle.lister_hypotheses(boucle, conn, TENANT)
    trouvees = {l["id"]: l for l in listees}
    assert trouvees["col-hyp-epis-1"]["donnees"]["statut"] == "EMISE"

    # Son cycle est gelé côté workflow : EMISE ∉ TRANSITIONS_HYPOTHESIS → 409.
    with pytest.raises(commandes_boucle.TransitionRefusee):
        commandes_boucle.changer_statut_hypothese(
            boucle, conn, TENANT, "col-hyp-epis-1", "STRENGTHENED")


@besoin_pg
def test_collision_1b_hypothese_workflow_relue_correctement(conn):
    """Témoin non cassé : une Hypothesis workflow (route typée) se relit bien."""
    _, investigation = _chaine(conn, titre="collision-1b")
    cree = commandes_boucle.creer_hypothese(
        boucle, conn, TENANT, investigation["id"], enonce="hypothèse workflow")
    objet = boucle.lire_boucle(
        conn, TENANT, cree.objet["id"], as_dict=False)
    assert isinstance(objet, domaine_exploit.Hypothesis)
    assert objet.investigation_id == investigation["id"]
    assert objet.statut == "OPEN"


# ---------------------------------------------------------------------------
# COLLISION-2 (§2.1, risque §5.3) : ``_source_principale`` porte deux branches
# ``type == "HYPOTHESIS"`` ; la seconde (situation_id/need_id, cognition,
# boucle.py:1399-1403) est inaccessible — la chaîne épistémique s'arrête à
# elle-même et l'épisode perd son lien causal.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="COLLISION-2 (doc §5.3) : branche morte dans _source_principale — "
    "le nettoyage de phase 1 doit faire basculer ce test")
def test_collision_2_source_principale_branche_morte():
    # Une HYPOTHESIS épistémique porte situation_id/need_id, jamais investigation_id :
    # la branche dev (:1363) rend None et la branche cognition (:1399) n'est jamais atteinte.
    ligne_epistemique = {
        "id": "col-hyp-epis-1", "type": "HYPOTHESIS",
        "donnees": {"situation_id": "col-sit-epis", "need_id": "col-need-epis"}}
    # Attendu sémantique : "col-sit-epis". Observé : None (branche morte).
    assert boucle._source_principale(ligne_epistemique) is None

    # La branche dev gagne toujours, même quand les deux vocabulaires cohabitent.
    hybride = {
        "id": "col-hyp-2", "type": "HYPOTHESIS",
        "donnees": {"investigation_id": "col-inv-1", "situation_id": "col-sit-1"}}
    assert boucle._source_principale(hybride) == "col-inv-1"

    # Témoin : les autres types relisent bien leur source (NEED → situation_id).
    assert boucle._source_principale(
        {"type": "NEED", "donnees": {"situation_id": "col-sit-1"}}) == "col-sit-1"


@besoin_pg
@pytest.mark.xfail(
    strict=True,
    reason="COLLISION-2 (doc §5.3) : l'épisode d'une HYPOTHESIS épistémique perd "
    "son lien causal à cause de la branche morte — le nettoyage doit faire "
    "basculer ce test")
def test_collision_2b_episode_sans_lien_causal(conn):
    """Conséquence DB : ``evenement_episode.donnees.lien_cause`` est NULL."""
    hypothese = boucle.Hypothesis(
        id="col-hyp-epis-ch", tenant_id=TENANT,
        enonce="le déclaré est obsolète", statut="EMISE",
        rival_ids=["col-hyp-epis-ch2"], situation_id="col-sit-ch")
    boucle.enregistrer_boucle(conn, TENANT, hypothese)
    evenement = conn.execute(
        "SELECT donnees->>'lien_cause' AS lien FROM evenement_episode "
        "WHERE tenant_id = %s AND objet_id = %s",
        (TENANT, "col-hyp-epis-ch")).fetchone()
    assert evenement is not None
    # Attendu : "col-sit-ch" (chaîne vers la Situation). Observé : None.
    assert evenement[0] is None


# ---------------------------------------------------------------------------
# COLLISION-3 (§2.2) : une OPPORTUNITY de détecteur (statut PROPOSED, sans
# expression_id) est gelée pour le moteur de transitions, invisible de
# ``GET /expressions/{eid}/opportunities`` et impossible à réécrire par le
# chemin B (trace humaine exigée).
# ---------------------------------------------------------------------------


@besoin_pg
@pytest.mark.xfail(
    strict=True,
    reason="COLLISION-3 (doc §2.2) : OPPORTUNITY PROPOSED gelée et invisible "
    "aux routes typées — phase 2 (unification) doit faire basculer ce test")
def test_collision_3_opportunity_detectee_gelee(conn):
    _preparer_duplication(conn)
    rapport = detecteur_opportunites.detecter(conn, TENANT)
    assert rapport["erreurs"] == []
    [cree] = rapport["crees"]
    opportunite_id = cree["id"]

    relue = boucle.lire_boucle(conn, TENANT, opportunite_id)
    assert relue["donnees"]["statut"] == "PROPOSED"
    assert not relue["donnees"].get("expression_id")

    # Gelée : ``PROPOSED`` ∉ STATUTS_OPPORTUNITE → toute cible échoue,
    # avant même d'atteindre la table de transitions (422 métier, pas un 409).
    with pytest.raises(domaine_exploit.ObjetsExploitationInvalide) as excinfo:
        commandes_boucle.changer_statut_opportunite(
            boucle, conn, TENANT, opportunite_id, "MATURING", motif="qualifier")
    assert "PROPOSED" in str(excinfo.value)

    # Invisible : ``GET /expressions/{eid}/opportunities`` exige ``expression_id``.
    situation, _ = _chaine(conn, titre="collision-3")
    expression = commandes_boucle.creer_expression(
        boucle, conn, TENANT, situation["id"],
        formulation="deux applications réalisent la même capacité", auteur="alice")
    assert commandes_boucle.lister_opportunites(
        boucle, conn, TENANT, expression.objet["id"]) == []

    # Elle n'est visible que par les lectures génériques non typées.
    generiques = entreprise_depot.lister_objets(conn, TENANT, type_="OPPORTUNITY")
    assert {o["id"] for o in generiques} == {opportunite_id}
    exploit = boucle.lister_objets_exploitation(conn, TENANT, type_="OPPORTUNITY")
    assert {o["id"] for o in exploit} == {opportunite_id}

    # Réécriture refusée par le chemin B : PROPOSED hors taxonomie d'exploitation
    # (et sans ``expression_id`` ni ``auteur + justification``).
    with pytest.raises(domaine_exploit.ObjetsExploitationInvalide):
        depot_exploitation.enregistrer_objets_exploitation(conn, TENANT, relue)


# ---------------------------------------------------------------------------
# COLLISION-4 (§2.2, blocage 4) : RISK est lisible (``_CLASSES_LECTURE``) mais
# pas dans ``TYPES_COMPLEMENTAIRES`` — ``enregistrer_boucle`` le refuse, donc le
# détecteur stocke des risques (concentration_risque, dette_vs_usage) comme des
# OPPORTUNITY. Le chemin d'exploitation, lui, accepte RISK.
# ---------------------------------------------------------------------------


@besoin_pg
@pytest.mark.xfail(
    strict=True,
    reason="COLLISION-4 (doc §2.2) : RISK refusé par enregistrer_boucle — "
    "l'ouverture prévue en phase 2 doit faire basculer ce test")
def test_collision_4_risk_refuse_par_enregistrer_boucle(conn):
    assert "RISK" not in boucle.TYPES_BOUCLE + boucle.TYPES_COMPLEMENTAIRES

    with pytest.raises(boucle.BoucleInvalide, match="hors boucle"):
        boucle.enregistrer_boucle(conn, TENANT, {
            "id": "col-risk-boucle", "tenant_id": TENANT, "type": "RISK",
            "donnees": {"statut": "DETECTED", "description": "risque canonique"}})

    # Asymétrie : le chemin d'exploitation accepte RISK (trace humaine par
    # ``auteur + justification``, sans Expression), et la lecture canonique
    # sait reconstruire ``modele.Risk``.
    instant = boucle._instant()
    risque = modele.Risk(
        id="col-risk-exploit", tenant_id=TENANT, titre="risque d'exploitation",
        description="risque écrit par le chemin B",
        auteur="alice", justification="revue d'architecture",
        cree_le=instant, observe_le=instant, valide_depuis=instant)
    ligne = depot_exploitation.enregistrer_objets_exploitation(conn, TENANT, risque)
    assert ligne["type"] == "RISK"
    relu = boucle.lire_boucle(conn, TENANT, "col-risk-exploit", as_dict=False)
    assert isinstance(relu, modele.Risk)


# ---------------------------------------------------------------------------
# COLLISION-5 (§3.2, risque §5.6) : ``decision_travail`` écrit une DECISION
# orpheline (sans investigation_id) quand aucun parent canonique n'existe —
# empoisonnée en réécriture et en lecture typée, et invisible du journal.
# ---------------------------------------------------------------------------


@besoin_pg
@pytest.mark.xfail(
    strict=True,
    reason="COLLISION-5 (doc §3.2) : DECISION orpheline irréparable par le "
    "chemin canonique — le choix « un seul producteur outbox » doit faire "
    "basculer ce test")
def test_collision_5_decision_orpheline(conn):
    ligne = decision_travail.enregistrer_decision_travail(
        conn, TENANT,
        case={"id": "col-case-1", "titre": "cas sans parent canonique"},
        decision={"texte": "conserver l'adaptateur CBM", "par": "alice",
                  "quand": "2026-11-20T10:00:00+00:00"})
    decision_id = ligne["id"]
    assert ligne["type"] == "DECISION"
    assert ligne["donnees"]["statut"] == "DECIDED"
    # La ligne est écrite sans parent : le lien promis « à renseigner plus tard ».
    assert not ligne["donnees"].get("investigation_id")

    # Lecture brute OK ; lecture typée impossible — ``modele.Decision`` exige le lien.
    assert boucle.lire_boucle(conn, TENANT, decision_id)["id"] == decision_id
    with pytest.raises(modele.ModeleInvalide, match="investigation_id"):
        boucle.lire_boucle(conn, TENANT, decision_id, as_dict=False)

    # L'orchestrateur ne peut ni la relire ni la trancher : source « incomplète ».
    with pytest.raises(commandes_boucle.TransitionRefusee, match="incomplète"):
        commandes_boucle.trancher_decision(
            boucle, conn, TENANT, decision_id, acteur="alice", choix="conserver")

    # Toute repasse par le chemin canonique est refusée : la DECISION est empoisonnée.
    with pytest.raises(boucle.BoucleInvalide, match="investigation_id"):
        boucle.enregistrer_boucle(conn, TENANT, ligne)

    # Elle n'a laissé aucun événement d'épisode (écriture hors ``enregistrer_boucle``).
    assert conn.execute(
        "SELECT 1 FROM evenement_episode WHERE tenant_id = %s AND objet_id = %s",
        (TENANT, decision_id)).fetchone() is None


# ---------------------------------------------------------------------------
# COLLISION-6 (risque §5.4) : ``evenement_episode`` ne voit que
# ``enregistrer_boucle`` — les écritures des routes typées passant par
# ``enregistrer_objets_exploitation`` sont absentes de ``GET /episodes``.
# ---------------------------------------------------------------------------


@besoin_pg
@pytest.mark.xfail(
    strict=True,
    reason="COLLISION-6 (doc §5.4) : /episodes aveugle aux écritures typées — "
    "le branchement du journal en phase 3 doit faire basculer ce test")
def test_collision_6_episodes_aveugle_aux_ecritures_typees(conn):
    # Route typée → chemin A : la SITUATION est journalisée.
    situation = commandes_boucle.creer_situation(boucle, conn, TENANT, titre="collision-6")
    situation_id = situation.objet["id"]

    # Route typée → chemin B : l'EXPRESSION est écrite par
    # ``enregistrer_objets_exploitation`` qui n'importe jamais ``journal_episodes``.
    expression = commandes_boucle.creer_expression(
        boucle, conn, TENANT, situation_id,
        formulation="les dossiers sont gérés deux fois", auteur="alice")
    expression_id = expression.objet["id"]
    assert boucle.lire_boucle(conn, TENANT, expression_id)["type"] == "EXPRESSION"

    evenements = _evenements(conn)
    assert ("SITUATION", situation_id, "cree") in evenements
    assert not any(objet_id == expression_id for _, objet_id, _ in evenements)
    assert not any(type_ == "EXPRESSION" for type_, _, _ in evenements)

    # La route GET /episodes (journal_episodes.episodes) ne voit que l'épisode A.
    episodes = journal_episodes.episodes(conn, TENANT)
    assert {e["episode_id"] for e in episodes} == {situation_id}
    assert all(
        e["objet_id"] != expression_id
        for e in journal_episodes.lire_episode(conn, TENANT, situation_id))

    # Témoin : le même genre d'objet par ``enregistrer_boucle`` est bien vu.
    temoin = boucle.enregistrer_boucle(conn, TENANT, boucle.Situation(
        id="col-sit-epi", tenant_id=TENANT, titre="situation canonique"))
    evenements = _evenements(conn)
    assert ("SITUATION", temoin["id"], "cree") in evenements


# ---------------------------------------------------------------------------
# COLLISION-7 (§3.1, risques §5.10) : ``POST /objets`` générique accepte un
# ``statut`` initial arbitraire et un ``mode`` client — là où les routes typées
# forcent les champs serveur — et lit sa source sans verrou ``FOR UPDATE``.
# ---------------------------------------------------------------------------


@besoin_pg
@pytest.mark.xfail(
    strict=True,
    reason="COLLISION-7 (doc §3.1/§5.10) : POST /objets sans statut serveur ni "
    "verrou — la restriction prévue doit faire basculer ce test")
def test_collision_7_post_objets_sans_verrou(conn):
    _, investigation = _chaine(conn, titre="collision-7")

    # Le chemin générique instancie ``_CLASSES[type]`` directement : une DECISION
    # naît DECIDED sans passer par proposer → trancher (la route typée refuse le
    # statut client en 422 et exige la trace acteur/choix/decide_le à la transition).
    classe_decision = boucle._CLASSES["DECISION"]
    assert classe_decision is boucle.Decision
    decidee = classe_decision(
        id="col-dec-direct", tenant_id=TENANT,
        investigation_id=investigation["id"],
        options=["conserver", "retirer"], statut="DECIDED",
        acteur="alice", choix="conserver", decide_le="2026-11-20T10:00:00+00:00",
        titre="décision écrite directement tranchée")
    ligne = boucle.enregistrer_boucle(conn, TENANT, decidee)
    assert ligne["donnees"]["statut"] == "DECIDED"
    assert boucle.est_decision_tranchee(ligne)

    # Même tolérance sur ``mode`` : CONFIRMED est un mode valide du domaine et
    # traverse la création générique (§5.10) — impossible par les routes typées.
    conjecture = boucle._CLASSES["CONJECTURE"](
        id="col-conj-mode", tenant_id=TENANT,
        enonce="conjecture à mode arbitraire", statut="EMISE",
        mode="CONFIRMED")
    ligne = boucle.enregistrer_boucle(conn, TENANT, conjecture)
    assert ligne["mode"] == "CONFIRMED"


@pytest.mark.xfail(
    strict=True,
    reason="COLLISION-7 (doc §3.1) : la transition générique lit sa source sans "
    "FOR UPDATE — l'unification d'autorité doit faire basculer ce test")
def test_collision_7b_transition_generique_sans_verrou():
    """Lecture seule du code : les routes typées verrouillent, ``/objets`` non."""
    generique = (
        inspect.getsource(http_boucle.creer_objet)
        + inspect.getsource(http_boucle.transition_objet))
    assert "lire_boucle" in generique
    assert "for_update" not in generique
    # Témoin : les routes typées verrouillent systématiquement la source.
    assert "for_update" in inspect.getsource(commandes_boucle._source)
    assert commandes_boucle._source.__kwdefaults__["for_update"] is True


# ---------------------------------------------------------------------------
# COLLISION-8 (risque §5.5) : deux canaux d'attention disjoints —
# ``donnees.attention`` (cognition : resolution_besoins, decroissance_confiance)
# vs scoring ``domain/attention.py`` + PanneauActions (dev) ; aucun ne lit
# l'autre.
# ---------------------------------------------------------------------------


@besoin_pg
@pytest.mark.xfail(
    strict=True,
    reason="COLLISION-8 (doc §5.5) : deux canaux attention disjoints — "
    "l'unification en phase 4 doit faire basculer ce test")
def test_collision_8_double_canal_attention(conn):
    # Canal cognition : ``donnees.attention`` est un champ jsonb de
    # ``objet_entreprise``, posé par les boucles cognition (ici rejoué par
    # ``fusionner_donnees`` comme le fait resolution_besoins.verifier_paris).
    boucle.enregistrer_boucle(conn, TENANT, boucle.Situation(
        id="col-sit-att", tenant_id=TENANT, titre="besoin remonté en attention"))
    boucle.fusionner_donnees(
        conn, TENANT, "col-sit-att",
        {"attention": {"raison": "intention_expiree",
                       "depuis": "2026-11-20T00:00:00+00:00"}})
    ligne = boucle.lire_boucle(conn, TENANT, "col-sit-att")
    assert ligne["donnees"]["attention"]["raison"] == "intention_expiree"

    # Canal dev : ``domain/attention.score`` (utilisé par GET /cognitif/attention
    # et PanneauActions) ne lit jamais ``donnees.attention`` — le drapeau
    # cognition n'a strictement aucun effet sur le fil d'attention dev.
    instant = datetime(2026, 11, 21, tzinfo=timezone.utc)
    avec = attention.score(ligne, maintenant=instant)
    sans_attention = dict(ligne)
    sans_attention["donnees"] = {
        cle: valeur for cle, valeur in ligne["donnees"].items() if cle != "attention"}
    sans = attention.score(sans_attention, maintenant=instant)
    assert avec == sans

    # Les producteurs cognition écrivent bien ``donnees.attention``…
    from meridian.adapters.outbound.postgres import (
        decroissance_confiance, resolution_besoins)
    assert "attention" in inspect.getsource(resolution_besoins)
    assert "attention" in inspect.getsource(decroissance_confiance)

    # …pendant que le panneau d'actions de l'UI ne le lit pas non plus.
    from pathlib import Path
    panneau = (
        Path(__file__).resolve().parents[3]
        / "frontend" / "src" / "components" / "boucle" / "PanneauActions.jsx")
    assert panneau.is_file()
    assert "attention" not in panneau.read_text(encoding="utf-8")
