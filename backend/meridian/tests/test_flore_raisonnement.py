"""Le raisonnement visible de certains modèles ne doit pas devenir la réponse."""
from meridian.adapters.outbound.llm import flore


def test_sans_raisonnement_retire_les_blocs_nova():
    texte = "<thinking>je réfléchis</thinking>\n\nLa réponse utile."
    assert flore.sans_raisonnement(texte) == "La réponse utile."


def test_sans_raisonnement_garde_une_reponse_normale():
    assert flore.sans_raisonnement("La réponse utile.") == "La réponse utile."
