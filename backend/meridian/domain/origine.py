"""D'où vient une réponse de Flore (plan de remédiation L0.5).

Le serveur pose une étiquette d'origine sur chaque réponse. Elle sert à une seule chose : qu'une réponse écrite
d'avance, ou trouvée par recherche, ne se présente jamais comme une réponse calculée. Une réponse issue du modèle
(`modele`) est la seule qui n'a rien à signaler, parce que c'est celle que l'interlocuteur croit toujours avoir.

Les indicateurs (`confiance`, `couverture`, `fraicheur`, `contradictions`) des scénarios de démonstration ont été
écrits à la main : ils ne sont pas calculés, donc ils ne sont pas affichés.
"""
ORIGINES = {
    "modele": "réponse calculée",
    "scenario": "scénario de démonstration",
    "registre": "registre",
    "recherche": "recherche plein texte",
    "repli": "aucune réponse calculée",
    "refus": "question hors périmètre",
}

# Seule une réponse calculée par le modèle peut porter des indicateurs : tous les autres chemins les écrivent à la
# main (confiance 80, couverture 70…), et un chiffre écrit d'avance n'est pas une mesure.
ORIGINES_SANS_MESURE = frozenset({"scenario", "repli", "registre", "recherche", "refus"})


def marquer_origine(reponse, origine):
    """Étiquette l'origine d'une réponse ; retire les indicateurs qui n'ont pas été calculés."""
    if not isinstance(reponse, dict):
        return reponse
    reponse.setdefault("origine", origine)
    if origine in ORIGINES_SANS_MESURE or origine != "modele":
        reponse.pop("indicateurs", None)
    return reponse
