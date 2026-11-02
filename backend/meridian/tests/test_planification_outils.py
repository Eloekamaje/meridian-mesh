"""Outils Harness read-only du pilotage, sans fournisseur dans le contrat."""
from meridian.application.planification import outils
from meridian.domain.capacites import RegistreCapacites


def test_les_outils_planification_sont_read_only_et_generiques():
    manifestes = outils.manifestes()
    assert {m.nom for m in manifestes} == {
        "planification_capacite", "planification_prevision",
        "planification_budget", "planification_alertes", "planification_dependances",
        "planification_gantt"}
    assert all(m.lecture_seule for m in manifestes)
    assert all("jira" not in m.nom.lower() for m in manifestes)
    registre = RegistreCapacites(manifestes)
    assert registre.decrire("planification_prevision").capacite == "planifier"


def test_le_harness_expose_les_capacites_sans_appeler_la_base():
    from meridian.adapters.outbound.planification_outils import construire
    harnais = construire("postgresql://localhost/inexistant", "demo", acteur="po")
    # L'API publique du Harness est `outils()` ; les manifestes sont visibles avant tout appel réseau.
    assert {m.nom for m in harnais.registre.lister()} >= {
        "planification_capacite", "planification_prevision",
        "planification_budget", "planification_alertes", "planification_dependances",
        "planification_gantt"}


def test_le_harness_expose_quatre_outils_executables():
    from meridian.adapters.outbound.planification_outils import construire
    harnais = construire("postgresql://localhost/inexistant", "demo", acteur="po")
    noms = {outil.tool_name for outil in harnais.outils(lecture_seule=True)}
    assert {"planification_capacite", "planification_prevision",
            "planification_budget", "planification_alertes",
            "planification_dependances", "planification_gantt"} <= noms
