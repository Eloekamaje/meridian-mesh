"""Context Pack : bornage, empreinte stable, preuves et aucune fuite de secret."""
from jumeau import contexte, profils

DOSSIER = {
    "tenant": "demo",
    "propositions": [
        {"specialiste": "impact", "type": "IMPACT", "titre": "Impact A",
         "resume": "3 aval", "preuves": ["p1", "p2"], "confiance": 0.9,
         "donnees": {"twin_id": "paiements"}},
        {"specialiste": "preuve", "type": "RISQUE", "titre": "Preuve absente",
         "resume": "token=secret123", "preuves": ["p3"], "confiance": 0.8,
         "donnees": {"twin_id": "comptes"}},
        {"specialiste": "outcome", "type": "QUESTION", "titre": "Mesurer ?",
         "resume": "question", "preuves": [], "confiance": 0.5,
         "donnees": {"situation_id": "sit-1"}},
    ],
    "limites": ["source partielle"],
}


def test_le_pack_est_borne_deterministe_et_fingerprinte():
    profil = profils.CATALOGUE_PROFILS["developpeur"]
    premier = contexte.construire("Pourquoi ?", profil, DOSSIER, max_faits=2, max_preuves=2)
    second = contexte.construire("Pourquoi ?", profil, DOSSIER, max_faits=2, max_preuves=2)

    assert len(premier.faits) == 2 and len(premier.preuves) <= 2
    assert premier.fingerprint == second.fingerprint
    assert premier.entites[0] == "paiements"
    assert "secret123" not in str(premier.as_dict())
    assert any("tronqués" in limite for limite in premier.limites)


def test_le_pack_vide_reste_borné_et_le_signale():
    pack = contexte.construire("Rien ?", profils.CATALOGUE_PROFILS["generaliste"], {"tenant": "demo"})
    assert pack.faits == () and pack.preuves == ()
    assert pack.fingerprint and "aucun fait" in " ".join(pack.limites)
