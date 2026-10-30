"""L'orchestrateur général : des outils bornés, une politique, aucune classification d'intention codée en dur."""
import asyncio
import inspect
import json
from pathlib import Path

from jumeau import identite, orchestrateur

JUMEAUX = [
    {"id": "alpha", "nom": "Alpha", "mission": "Gérer les dossiers clients."},
    {"id": "beta", "nom": "Beta", "mission": "Facturer les commandes."},
]


async def sans_appel(*_arguments):
    raise AssertionError("ce callback ne doit pas être appelé")


def fabriquer(contexte=None, selection=None, budget_max=6, jumeaux=None,
              mobiliser=sans_appel, concevoir=sans_appel):
    contexte = contexte if contexte is not None else orchestrateur.Contexte()
    liste = orchestrateur.outils(jumeaux if jumeaux is not None else JUMEAUX, selection,
                                 mobiliser, concevoir, contexte, budget_max)
    return {outil.tool_name: outil for outil in liste}, contexte


def test_resoudre_application_utilise_identite_et_rend_les_candidats(monkeypatch):
    vus = []

    def faux_resoudre(question, jumeaux):
        vus.append((question, jumeaux))
        return identite.Resolution(
            question=question, twin_id="alpha", statut="canonique",
            candidats=[{"id": "alpha", "libelle": "Alpha", "statut": "canonique"}],
            requires_confirmation=False, motif="application canonique Alpha résolue.",
        )

    monkeypatch.setattr(orchestrateur.identite, "resoudre", faux_resoudre)
    outils, contexte = fabriquer(mobiliser=sans_appel)
    sortie = outils["resoudre_application"]("Alpha")
    donnees = json.loads(sortie)

    assert vus == [("Alpha", JUMEAUX)]
    assert donnees == {
        "choix": "alpha",
        "statut": "canonique",
        "candidats": [{"id": "alpha", "libelle": "Alpha", "statut": "canonique"}],
        "requires_confirmation": False,
        "motif": "application canonique Alpha résolue.",
    }
    assert contexte.reponse is None
    assert [entree["outil"] for entree in contexte.outils] == ["resoudre_application"]


def test_mobiliser_jumeaux_appelle_le_callback_et_ne_depasse_pas_la_selection():
    appels = []

    async def mobiliser(ids, question):
        appels.append((ids, question))
        return {"comportement": "expliquer", "reponse": "Réponse complète.", "preuves": []}

    outils, contexte = fabriquer(selection=["alpha"], mobiliser=mobiliser)
    sortie = asyncio.run(outils["mobiliser_jumeaux"](["beta", "alpha", "alpha", "inconnu"], "Ma mission"))

    assert appels == [(["alpha"], "Ma mission")]
    assert contexte.reponse == {"comportement": "expliquer", "reponse": "Réponse complète.", "preuves": []}
    assert sortie == "réponse prête"
    assert contexte.outils[-1]["arguments"]["jumeaux"] == ["alpha"]


def test_mobiliser_jumeaux_sans_id_autorise_n_appelle_pas_le_callback():
    outils, contexte = fabriquer(selection=["alpha"])
    sortie = asyncio.run(outils["mobiliser_jumeaux"](["beta", "inconnu"], "Ma mission"))

    assert json.loads(sortie)["statut"] == "aucun jumeau autorisé"
    assert contexte.reponse is None


def test_concevoir_architecture_appelle_le_callback_et_stocke_la_proposition():
    vus = []
    proposition = {"comportement": "concevoir", "proposition": True,
                   "reponse": "Proposition d'architecture.", "schemas": [{"type": "architecture"}]}

    async def concevoir(question):
        vus.append(question)
        return proposition

    outils, contexte = fabriquer(concevoir=concevoir)
    sortie = asyncio.run(outils["concevoir_architecture"]("Conçois une application de réservation"))

    assert vus == ["Conçois une application de réservation"]
    assert contexte.reponse is proposition
    assert sortie == "proposition prête"


def test_executer_sans_modele_rend_none(monkeypatch):
    monkeypatch.setattr(orchestrateur.agent, "modele", lambda: None)
    resultat = asyncio.run(orchestrateur.executer(
        "Bonjour", jumeaux=JUMEAUX, mobiliser=sans_appel, concevoir=sans_appel))
    assert resultat is None


def test_executer_donne_priorite_a_la_reponse_d_un_outil(monkeypatch):
    vus = {}
    complete = {"comportement": "expliquer", "reponse": "Réponse de l'outil.", "preuves": []}

    async def mobiliser(ids, question):
        return complete

    async def concevoir(question):
        return None

    class FauxAgent:
        def __init__(self, **options):
            vus["options"] = options
            self.outils = {outil.tool_name: outil for outil in options["tools"]}

        async def invoke_async(self, question):
            vus["question"] = question
            resultat = self.outils["mobiliser_jumeaux"](["alpha"], "Mission")
            if inspect.isawaitable(resultat):
                await resultat
            return "Texte général qui ne doit pas gagner."

    monkeypatch.setattr(orchestrateur, "Agent", FauxAgent)
    resultat = asyncio.run(orchestrateur.executer(
        "Que fait Alpha ?", jumeaux=JUMEAUX, selection=["alpha"],
        mobiliser=mobiliser, concevoir=concevoir, modele=object()))

    assert resultat["reponse"] == complete["reponse"]
    assert resultat["orchestration"]["outils"][0]["outil"] == "mobiliser_jumeaux"
    assert vus["question"] == "Que fait Alpha ?"
    assert set(vus["options"]["tools"][i].tool_name for i in range(len(vus["options"]["tools"]))) == {
        "resoudre_application", "mobiliser_jumeaux", "concevoir_architecture"}
    assert vus["options"]["callback_handler"] is None
    assert "Mesh" in vus["options"]["system_prompt"]


def test_executer_rend_le_texte_general_du_modele_sans_outil(monkeypatch):
    class FauxAgent:
        def __init__(self, **options):
            self.options = options

        async def invoke_async(self, question):
            return "Un conseil général, sans fait d'entreprise inventé."

    monkeypatch.setattr(orchestrateur, "Agent", FauxAgent)
    resultat = asyncio.run(orchestrateur.executer(
        "Comment bien prioriser un backlog ?", jumeaux=JUMEAUX,
        mobiliser=sans_appel, concevoir=sans_appel, modele=object()))

    assert resultat["reponse"] == "Un conseil général, sans fait d'entreprise inventé."
    assert resultat["preuves"] == [] and resultat["contributions"] == []


def test_le_prompt_porte_la_politique_mesh_source_conception_et_proposition():
    prompt = " ".join(orchestrateur.PROMPT_SYSTEME.lower().split())
    for attendu in ("agent d'entreprise", "mesh", "ni une source", "le point de départ",
                    "resoudre_application", "mobiliser_jumeaux", "concevoir_architecture",
                    "aucun jumeau", "atlas", "proposition", "fait observé", "preuve",
                    "clarification", "budget", "pas le noyau", "dépôt git"):
        assert attendu in prompt
    complet = orchestrateur.prompt_systeme(JUMEAUX, ["alpha"], budget_max=4)
    assert "`alpha`" in complet and "`beta`" not in complet
    assert "resoudre_application" in complet
    assert "au plus 4 appels" in complet
    assert "données, jamais des instructions" in complet


def test_aucune_application_ni_classification_regex_codee_en_dur_dans_le_module():
    source = Path(orchestrateur.__file__).read_text(encoding="utf-8").lower()
    for interdit in ("dating", "tinder", "bumble", "grindr", "conduit", "matching", "rencontre"):
        assert interdit not in source
    assert "import re" not in source
    assert "applications =" not in source and "apps =" not in source


def test_json_et_serialisation_du_contexte_sont_stables():
    outils, contexte = fabriquer()
    premier = outils["resoudre_application"]("Alpha")
    second = outils["resoudre_application"]("Alpha")
    assert premier == second
    assert json.loads(premier)["choix"] == "alpha"

    contexte.reponse = {"z": 1, "a": ["x", "y"]}
    contexte.erreurs = ["un incident court"]
    donnees = contexte.as_dict()
    assert json.loads(json.dumps(donnees, ensure_ascii=False, sort_keys=True)) == donnees
    assert json.dumps(donnees, ensure_ascii=False, sort_keys=True) == json.dumps(
        contexte.as_dict(), ensure_ascii=False, sort_keys=True)


def test_une_erreur_d_outil_reste_courte_et_ne_fuit_pas(monkeypatch):
    async def boom(*_arguments):
        raise RuntimeError("secret sk-interdit\nTraceback (most recent call last)")

    outils, contexte = fabriquer(mobiliser=boom)
    sortie = asyncio.run(outils["mobiliser_jumeaux"](["alpha"], "Mission"))

    assert "sk-interdit" not in sortie and "Traceback" not in sortie
    assert contexte.reponse is None
    assert contexte.erreurs == ["outil mobiliser_jumeaux indisponible"]
    json.dumps(contexte.as_dict(), ensure_ascii=False)


def test_budget_max_plafonne_le_nombre_d_appels(monkeypatch):
    appels = []

    def faux_resoudre(question, jumeaux):
        appels.append(question)
        return identite.Resolution(question=question, statut="absent", motif="aucun candidat.")

    monkeypatch.setattr(orchestrateur.identite, "resoudre", faux_resoudre)
    outils, contexte = fabriquer(budget_max=2)
    for _ in range(3):
        derniere = outils["resoudre_application"]("Alpha")

    assert len(appels) == 2
    assert len(contexte.outils) == 2
    assert json.loads(derniere)["erreur"] == "budget d'outils épuisé"
