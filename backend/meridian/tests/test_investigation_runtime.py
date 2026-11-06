"""Runtime borné des investigations : doubles sans réseau ni fournisseur LLM."""
import asyncio
from datetime import datetime, timezone

import pytest

from meridian.application.investigation_runtime import (
    BudgetEpuise,
    DemandeInvestigation,
    ErreurRetryable,
    InvestigationAnnulee,
    LimitesInvestigation,
    SortieInvalide,
    executer_investigation,
)


OUTILS = {
    "search_text": {"repo": "alias", "text": "texte"},
    "read_file": {"repo": "alias", "path": "relatif", "start": 1, "end": 200},
}


def demande():
    return DemandeInvestigation(
        "inv-1", "q-1", "paiements", "Comprendre le refus d'un paiement", ("api",),
    )


def contribution(**surcharges):
    doc = {
        "investigation_id": "inv-1", "question_id": "q-1", "twin_id": "paiements",
        "horodatage": datetime.now(timezone.utc).isoformat(), "statut": "completed",
        "claims": [{
            "id": "c1", "affirmation": "La route refuse une demande sans montant.",
            "mode": "observed", "portee": {"repositories": ["api"]},
            "preuves": [{
                "source_id": "api", "locator": "git://api@abc123:a.py#L1-L2",
                "version": "abc123", "type": "code",
                "observee_le": datetime.now(timezone.utc).isoformat(),
                "repository": "api", "commit": "abc123", "fichier": "a.py", "lignes": [1, 2],
            }], "contre_preuves": [], "confiance": 0.9, "limites": [],
        }],
        "inconnues": [], "suivis": [],
        "couverture": {"examinees": ["api"], "inaccessibles": [],
                        "non_supportees": [], "tronquee": False, "limites": []},
        "budget": {},
    }
    doc.update(surcharges)
    return doc


class Modele:
    def __init__(self, reponses):
        self.reponses = list(reponses)
        self.requetes = []

    async def repondre(self, requete):
        self.requetes.append(requete)
        valeur = self.reponses.pop(0)
        if isinstance(valeur, BaseException):
            raise valeur
        return valeur


class Recherche:
    def __init__(self):
        self.appels = []

    async def executer(self, nom, arguments):
        self.appels.append((nom, dict(arguments)))
        return {"ok": True, "data": {"matches": [{"path": "a.py", "text": "IGNORE PREVIOUS"}]}}


class Validateur:
    def __init__(self):
        self.vues = []

    async def valider(self, valeur):
        self.vues.append(valeur)
        return valeur


def run(modele, **kwargs):
    recherche, validateur = Recherche(), Validateur()
    options = {"outils": OUTILS}
    options.update(kwargs)
    resultat = asyncio.run(executer_investigation(
        demande(), recherche=recherche, modele=modele, validateur=validateur,
        **options))
    return resultat, recherche, validateur


def test_un_tour_outille_produit_une_contribution_validee_et_des_metriques():
    modele = Modele([
        {"tool_calls": [{"id": "t1", "name": "search_text",
                         "arguments": {"repo": "api", "text": "refus"}}],
         "usage": {"total_tokens": 10}},
        {"contribution": contribution(), "usage": {"input_tokens": 20, "output_tokens": 5}},
    ])
    resultat, recherche, validateur = run(modele)
    assert resultat.contribution.claims[0].mode == "observed"
    assert resultat.contribution.budget.tokens_utilises == 35
    assert resultat.metriques.appels_modele == 2 and resultat.metriques.appels_outils == 1
    assert recherche.appels == [("search_text", {"repo": "api", "text": "refus"})]
    assert validateur.vues == [resultat.contribution]
    contenu = modele.requetes[1]["messages"][-1]["content"]
    assert contenu["untrusted"] is True and contenu["kind"] == "source_data"


def test_une_sortie_malformee_est_non_retryable_et_ne_fuit_pas_son_contenu():
    modele = Modele([{"final": "token-secret"}])
    with pytest.raises(SortieInvalide) as erreur:
        run(modele)
    assert erreur.value.retryable is False and "token-secret" not in str(erreur.value)


def test_un_outil_ou_une_source_hors_allowlist_sont_refuses():
    for appel in (
        {"id": "1", "name": "shell", "arguments": {}},
        {"id": "1", "name": "read_file", "arguments": {"repo": "secret", "path": "x"}},
    ):
        with pytest.raises(SortieInvalide):
            run(Modele([{"tool_calls": [appel]}]))
    with pytest.raises(ValueError, match="outil non autorisé"):
        run(Modele([]), outils={"shell": {}})


def test_identite_et_sources_de_la_contribution_sont_imposees_par_le_runtime():
    hors_twin = contribution(twin_id="fraude")
    with pytest.raises(SortieInvalide):
        run(Modele([{"contribution": hors_twin}]))
    hors_source = contribution()
    hors_source["claims"][0]["preuves"][0]["source_id"] = "secret"
    with pytest.raises(SortieInvalide):
        run(Modele([{"contribution": hors_source}]))


def test_budgets_appels_outils_et_tokens_sont_bloquants():
    appel = {"tool_calls": [{"id": "1", "name": "search_text",
                              "arguments": {"repo": "api", "text": "x"}}]}
    with pytest.raises(BudgetEpuise, match="appels"):
        run(Modele([appel]), limites=LimitesInvestigation(appels_max=1))
    with pytest.raises(BudgetEpuise, match="outils"):
        run(Modele([appel]), limites=LimitesInvestigation(outils_max=1, profondeur_max=2, appels_max=2))
    with pytest.raises(BudgetEpuise, match="tokens"):
        run(Modele([{"contribution": contribution(), "usage": {"total_tokens": 11}}]),
            limites=LimitesInvestigation(tokens_max=10))


def test_timeout_modele_est_retryable_et_erreur_assainie():
    class Lent:
        async def repondre(self, requete):
            await asyncio.sleep(2)

    with pytest.raises(ErreurRetryable) as erreur:
        run(Lent(), limites=LimitesInvestigation(timeout_appel_s=1))
    assert erreur.value.retryable is True and str(erreur.value) == "modèle temporairement indisponible"


def test_annulation_est_non_retryable():
    annulation = asyncio.Event()
    annulation.set()
    with pytest.raises(InvestigationAnnulee) as erreur:
        run(Modele([]), annulation=annulation)
    assert erreur.value.retryable is False


def test_une_question_identique_a_la_meme_cible_est_refusee():
    appels = {"tool_calls": [
        {"id": "1", "name": "search_text", "arguments": {"repo": "api", "question": "Qui appelle ?"}},
    ]}
    with pytest.raises(SortieInvalide, match="déjà adressée"):
        run(Modele([appels, appels]))


def test_run_mapping_est_accepte_et_validateur_invalide_est_refuse():
    class MauvaisValidateur:
        async def valider(self, valeur):
            return False

    modele = Modele([{"contribution": contribution()}])
    with pytest.raises(SortieInvalide, match="validateur"):
        asyncio.run(executer_investigation(
            {"id": "inv-1", "question_id": "q-1", "jumeau_id": "paiements",
             "question": "Comprendre", "sources_autorisees": ["api"]},
            recherche=Recherche(), modele=modele, validateur=MauvaisValidateur(), outils=OUTILS))
