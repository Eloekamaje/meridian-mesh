"""L'orchestrateur général doit ouvrir une session de dialogue, pas repartir à zéro."""
import asyncio

from meridian.adapters.outbound.llm import agent, orchestrateur


class _FauxAgent:
    kwargs = None

    def __init__(self, **kwargs):
        type(self).kwargs = kwargs

    async def invoke_async(self, *_args, **_kwargs):
        return "réponse"


def test_executer_passe_une_session_au_agent(monkeypatch):
    monkeypatch.setattr(orchestrateur, "Agent", _FauxAgent)
    monkeypatch.setattr(orchestrateur, "_modele", lambda _m: object())
    monkeypatch.setattr(agent, "gestionnaire_session", lambda session: f"session:{session}")
    monkeypatch.setattr(agent, "SummarizingConversationManager", lambda **_: "resume")

    resultat = asyncio.run(orchestrateur.executer(
        "Bonjour", jumeaux=[], selection=[], mobiliser=lambda *_: None,
        concevoir=lambda *_: None, session="travail:t1"))

    assert resultat["reponse"] == "réponse"
    assert _FauxAgent.kwargs["session_manager"] == "session:travail:t1"
    assert _FauxAgent.kwargs["conversation_manager"] == "resume"
