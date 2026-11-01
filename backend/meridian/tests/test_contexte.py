"""Context Pack : bornage, empreinte stable, preuves et aucune fuite de secret."""
from meridian.domain import contexte
from meridian.domain import profils

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


def test_classement_graphe_departage_a_pertinence_egale():
    """À pertinence, confiance et fraîcheur égales, la proximité de graphe classe d'abord."""
    profil = profils.CATALOGUE_PROFILS["developpeur"]
    dossier = {
        "tenant": "demo",
        "propositions": [
            {"specialiste": "impact", "type": "IMPACT", "titre": "Impact A",
             "resume": "Meme resume", "preuves": ["p1"], "confiance": 0.8,
             "donnees": {"twin_id": "loin"}},
            {"specialiste": "impact", "type": "IMPACT", "titre": "Impact B",
             "resume": "Meme resume", "preuves": ["p2"], "confiance": 0.8,
             "donnees": {"twin_id": "proche"}},
        ],
    }

    pack = contexte.construire("Impact", profil, dossier, entites=("proche",))

    assert [fait["donnees"]["twin_id"] for fait in pack.faits] == ["proche", "loin"]
    assert pack.faits[0]["proximite"] == 1.0 and pack.faits[1]["proximite"] == 0.0
    assert pack.faits[0]["score"] > pack.faits[1]["score"]


def test_deduplication_par_identite_de_contenu_et_de_preuve():
    """Deux propositions de même contenu normalisé/preuve ne comptent qu'une fois."""
    profil = profils.CATALOGUE_PROFILS["developpeur"]
    dossier = {
        "tenant": "demo",
        "propositions": [
            {"id": "a", "specialiste": "impact", "type": "IMPACT", "titre": "Impact Carte",
             "resume": "Le delai baisse", "preuves": ["p1"], "confiance": 0.6,
             "donnees": {"twin_id": "cartes"}},
            {"id": "b", "specialiste": "impact", "type": "IMPACT", "titre": "impact carte !",
             "resume": "le delai baisse.", "preuves": ["p1"], "confiance": 0.9,
             "donnees": {"twin_id": "cartes"}},
            {"id": "c", "specialiste": "impact", "type": "IMPACT", "titre": "Impact Comptes",
             "resume": "Le solde change", "preuves": ["p2"], "confiance": 0.7,
             "donnees": {"twin_id": "comptes"}},
        ],
    }

    pack = contexte.construire("Impact", profil, dossier, max_faits=10)

    assert [fait["id"] for fait in pack.faits] == ["b", "c"]
    assert pack.faits[0]["confiance"] == 0.9


def test_budget_tokens_tronque_et_le_declare_dans_les_limites():
    """Le budget de tokens estimés borne en plus des compteurs et s'écrit dans limites."""
    profil = profils.CATALOGUE_PROFILS["developpeur"]
    propositions = [
        {"id": f"f{i}", "specialiste": "impact", "type": "IMPACT",
         "titre": f"Impact {i}", "resume": "x" * 200, "preuves": [f"p{i}"],
         "confiance": 0.8}
        for i in range(4)
    ]

    pack = contexte.construire(
        "Impact", profil, {"tenant": "demo", "propositions": propositions},
        max_faits=10, max_tokens=120)

    assert len(pack.faits) < 4
    assert pack.budget["tokens"] == 120 and "tokens_utilises" in pack.budget
    assert any("budget de 120 tokens estimés" in limite for limite in pack.limites)
    assert pack.completude == "partiel"
    assert contexte.estimer_tokens("abcd") == 1
    assert contexte.estimer_tokens("a" * 9) == 3


def test_contexte_vide_et_partiel_sont_declares_sans_certitude():
    """Un pack vide ou partiel porte son statut et interdit une conclusion certaine."""
    profil = profils.CATALOGUE_PROFILS["generaliste"]
    vide = contexte.construire("Rien ?", profil, {"tenant": "demo"})
    partiel = contexte.construire("Pourquoi ?", profil, {
        "tenant": "demo", "statut": "partiel",
        "propositions": [{"specialiste": "impact", "type": "IMPACT", "titre": "Impact",
                          "resume": "Partiel", "preuves": ["p1"], "confiance": 0.7}],
    })

    assert vide.completude == "vide" and vide.partiel is True
    assert any("aucune conclusion certaine" in limite for limite in vide.limites)
    assert partiel.completude == "partiel" and partiel.partiel is True
    assert any("contexte partiel" in limite for limite in partiel.limites)


def test_inconnues_contradictions_et_preuves_perimees_restent_explicites():
    """Les signaux d'incertitude sont conservés, y compris quand ils sont périmés."""
    profil = profils.CATALOGUE_PROFILS["developpeur"]
    dossier = {
        "tenant": "demo",
        "statut": "partiel",
        "contradictions": ["Version A contre version B"],
        "inconnues": ["Proprietaire du flux inconnu"],
        "preuves_perimees": ["p-archive"],
        "propositions": [
            {"id": "f1", "specialiste": "impact", "type": "IMPACT", "titre": "Impact",
             "resume": "Delai en baisse", "preuves": ["p-old"], "confiance": 0.7,
             "perime": True, "donnees": {"twin_id": "cartes"}},
            {"id": "f2", "specialiste": "preuve", "type": "CONTRADICTION",
             "titre": "Deux sources divergent", "resume": "A contredit B",
             "preuves": ["p2"], "confiance": 0.6},
            {"id": "f3", "specialiste": "outcome", "type": "QUESTION",
             "titre": "La baseline manque ?", "resume": "Question ouverte",
             "preuves": [], "confiance": 0.4},
        ],
    }

    pack = contexte.construire("Delai", profil, dossier)
    charge = pack.as_dict()

    assert "p-old" in pack.preuves_perimees and "p-archive" in pack.preuves_perimees
    assert "Version A contre version B" in pack.contradictions
    assert "Deux sources divergent" in pack.contradictions
    assert "Proprietaire du flux inconnu" in pack.inconnues
    assert "La baseline manque ?" in pack.inconnues
    assert pack.completude == "partiel"
    assert charge["preuves_perimees"] == list(pack.preuves_perimees)
    assert charge["contradictions"] == list(pack.contradictions)
