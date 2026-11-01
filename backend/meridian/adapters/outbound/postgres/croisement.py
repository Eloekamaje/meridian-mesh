"""Croiser les sources : une contradiction n'est signalée que si ses deux citations sont vérifiées par le harness
et viennent de deux systèmes différents (Jumeau Sources §5)."""
from meridian.adapters.outbound.llm import contradicteur
from meridian.adapters.outbound.postgres import depot
from meridian.adapters.outbound.postgres.connaissance import RE_CITATION
from meridian.adapters.outbound.connectors.lecteurs import RE_CITATION_SOURCE


def _verifier(citation, sources, lecteurs):
    """Système de la citation si elle existe vraiment, sinon ValueError. Code : le dépôt ; autre : son lecteur."""
    citation = citation.strip("` ")
    m = RE_CITATION_SOURCE.fullmatch(citation)
    if m:
        lecteur = next((l for l in lecteurs if l.systeme == m["systeme"] and l.verifier(citation)), None)
        if not lecteur:
            raise ValueError(f"citation introuvable ou source non branchée : {citation}")
        return m["systeme"]
    if not RE_CITATION.fullmatch(citation) or contradicteur.citations_invalides(citation, sources):
        raise ValueError(f"citation introuvable : {citation}")
    return "git"


def signaler(conn, jumeau, enonce, citation_a, citation_b, sources, lecteurs, acteur):
    """Enregistre la contradiction OUVERTE ; ValueError si l'énoncé est vide, une citation est fausse ou les deux
    citations viennent du même système."""
    if not enonce.strip():
        raise ValueError("énoncé vide")
    a, b = (citation_a.strip("` "), citation_b.strip("` "))
    systemes = (_verifier(a, sources, lecteurs), _verifier(b, sources, lecteurs))
    if systemes[0] == systemes[1]:
        raise ValueError(f"deux citations du même système ({systemes[0]}) ne se contredisent pas : croise deux systèmes")
    return depot.enregistrer_contradiction(conn, jumeau, enonce.strip()[:500], (a, systemes[0]), (b, systemes[1]), acteur)
