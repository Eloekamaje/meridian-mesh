"""Actions gouvernées et proposition de Learning depuis un dossier."""
from meridian.application import action_raisonnement as action
from meridian.application import apprentissage_raisonnement as apprentissage
from meridian.application import noyau_raisonnement as noyau
from meridian.domain import dossier_raisonnement as domaine


def _dossier(autorite="lecture", statut="proposition", gates=()):
    demande = domaine.Demande(
        question="Supprime la ressource", but="agir", niveau="N3",
        autorite=autorite, reversibilite="irreversible")
    return domaine.DossierRaisonnement(
        question=demande.question, demande=demande, statut=statut, gates=gates)


class _Gateway:
    def __init__(self):
        self.appels = []

    def proposer(self, run, **kwargs):
        self.appels.append((run, kwargs))
        return {"statut": "PROPOSE"}


def test_une_ecriture_sans_autorite_est_refusee():
    gateway = _Gateway()
    try:
        action.executer(
            gateway, _dossier(), {"tenant_id": "demo", "acteur": "a", "run_id": "r"},
            etape="1", outil="outil", operation="delete", cible="x", ecriture=True)
    except action.ActionRefusee as exc:
        assert "autorité" in str(exc)
    else:
        raise AssertionError("l'écriture aurait dû être refusée")
    assert gateway.appels == []


def test_une_ecriture_avec_autorité_est_déléguée_au_gateway():
    gateway = _Gateway()
    resultat = action.executer(
        gateway, _dossier("approbation"), {"tenant_id": "demo", "acteur": "a", "run_id": "r"},
        etape="1", outil="outil", operation="delete", cible="x", ecriture=True)
    assert resultat["statut"] == "PROPOSE"
    assert len(gateway.appels) == 1


def test_le_rollback_est_une_ecriture_gouvernee():
    gateway = _Gateway()
    resultat = action.executer_rollback(
        gateway, _dossier("approbation"), {"tenant_id": "demo", "acteur": "a", "run_id": "r"},
        etape="rollback", outil="outil", operation="restore", cible="x")
    assert resultat["statut"] == "PROPOSE"
    assert gateway.appels[0][1]["operation"] == "restore"


def test_un_dossier_non_executable_est_refuse():
    with __import__("pytest").raises(action.ActionRefusee):
        action.verifier(_dossier(statut="clarification_requise"))


def test_un_dossier_avec_constat_produit_un_learning_propose():
    dossier = noyau.analyser_reponse("Conçois une application", {"reponse": "OK"},
                                     pack_contexte={
                                         "faits": [{"titre": "Un fait", "type": "CONSTAT"}],
                                     })
    learning = apprentissage.proposer(dossier)
    assert learning is not None
    assert learning["type"] == "LEARNING"
    assert learning["statut"] == "PROPOSED"
    assert learning["source"]["dossier_id"] == dossier.id
