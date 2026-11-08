"""B4 — écritures du jumeau gouvernées : manifestes déclarés, fusion approuvée, audit tracé."""
from meridian.adapters.outbound.llm import agent
from meridian.domain import capacites
from meridian.tests.test_agent import CONTEXTE


def test_manifestes_ecriture_declares_non_lecture_seule():
    manifestes = {m.nom: m for m in capacites.manifestes_ecriture_jumeau()}
    attendus = {"proposer_connaissance", "ancrer_connaissance", "recouper_connaissance",
                "signaler_contradiction", "fusionner_connaissances"}
    assert set(manifestes) == attendus
    for manifeste in manifestes.values():
        assert manifeste.lecture_seule is False
        assert manifeste.effets_de_bord, f"{manifeste.nom} sans effet de bord déclaré"


def test_ecritures_invisibles_du_catalogue_lecture_seule():
    registre = capacites.RegistreCapacites(capacites.manifestes_ecriture_jumeau())
    assert registre.lister(lecture_seule=True) == []


def test_fusion_refusee_sans_approbation():
    ctx = dict(CONTEXTE)
    ctx.pop("approuves", None)
    outils = {t.tool_name: t for t in agent.outils(ctx, "dsn", "m", agent.Budget())}
    resultat = outils["fusionner_connaissances"](garder=1, retirer=2, raison="doublon")
    assert "pas approuvé" in resultat


def test_fusion_gate_avant_budget_et_base():
    """Le gate précède tout accès DB : sans approbation, aucun connect n'est tenté
    (l'audit du refus est fail-soft sur DSN invalide)."""
    ctx = dict(CONTEXTE)
    ctx.pop("approuves", None)
    outils = {t.tool_name: t for t in agent.outils(ctx, "dsn-invalide", "m", agent.Budget())}
    assert "pas approuvé" in outils["fusionner_connaissances"](garder=1, retirer=2, raison="x")
