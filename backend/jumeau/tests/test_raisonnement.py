"""Trace de raisonnement : étapes auditables, pas de chaîne de pensée cachée."""
from types import SimpleNamespace

from jumeau import profils, raisonnement

PROFIL = profils.CATALOGUE_PROFILS["developpeur"]
PLAN = SimpleNamespace(
    methodes=[SimpleNamespace(id="adr")], competences=[SimpleNamespace(id="rediger_adr")],
    specialistes_socle=("preuve", "impact"))
CONTEXTE = SimpleNamespace(as_dict=lambda: {"fingerprint": "abc123", "limites": ["contexte borné"]})
DOSSIER = {
    "specialistes": [
        {"specialiste": "impact", "statut": "ok", "propositions": [{"titre": "Impact"}], "limites": []},
        {"specialiste": "preuve", "statut": "partiel", "propositions": [], "limites": ["preuve absente"]},
    ],
    "propositions": [
        {"type": "IMPACT", "titre": "Impact A", "resume": "3 aval", "preuves": ["p1"]},
        {"type": "RISQUE", "titre": "Contradiction", "resume": "deux claims", "preuves": ["p2"]},
        {"type": "QUESTION", "titre": "Mesurer ?", "resume": "question", "preuves": []},
    ],
    "limites": ["dossier partiel"],
}
REPONSE = {"decision_support": {"options": [{"id": "opt-1", "label": "Observer"}],
                                "abstention": "baseline absente"}}


def test_trace_auditable_et_stable():
    un = raisonnement.construire("Pourquoi ?", PROFIL, PLAN, CONTEXTE, DOSSIER, REPONSE)
    deux = raisonnement.construire("Pourquoi ?", PROFIL, PLAN, CONTEXTE, DOSSIER, REPONSE)

    assert un.trace_id == deux.trace_id and un.trace_id.startswith("tr-")
    assert un.contexte_fingerprint == "abc123"
    assert [e["specialiste"] for e in un.etapes] == ["impact", "preuve"]
    assert un.contradictions == ("Contradiction",)
    assert un.incertitudes == ("Mesurer ?",)
    assert un.alternatives == ({"id": "opt-1", "label": "Observer"},)
    assert un.decision_support["abstention"] == "baseline absente"
    assert "preuve absente" in un.limites and "dossier partiel" in un.limites
    assert "raisonnement caché" not in str(un.as_dict())
