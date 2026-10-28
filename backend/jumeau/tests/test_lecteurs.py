"""Le contrat d'une source branchée : chercher, lire à une version, vérifier une citation."""
import pytest

from jumeau.lecteurs import LecteurMemoire, RE_CITATION_SOURCE

DOCS = {"123": {"titre": "Parcours d'ouverture", "versions": {
    "6": ["Seuls les conseillers valident.", "Délai : 48 h."],
    "7": ["Seuls les conseillers valident l'ouverture.", "Délai : 24 h.", "Annexe."]}}}


def lecteur():
    return LecteurMemoire("Wiki TBT", "TBT", DOCS, systeme="confluence")


def test_chercher_et_lire_a_la_derniere_version():
    l = lecteur()
    assert l.chercher("délai") == [{"ref": "123", "titre": "Parcours d'ouverture", "extrait": "Délai : 24 h."}]
    lu = l.lire("123", 2, 3)
    assert lu["lignes"] == ["Délai : 24 h.", "Annexe."]
    assert lu["locator"] == "confluence://TBT/123@7#L2-L3"
    assert l.nature == "documentation"


def test_lire_une_version_ancienne_et_bornes():
    assert lecteur().lire("123", 2, 2, version="6")["lignes"] == ["Délai : 48 h."]
    with pytest.raises(LookupError):
        lecteur().lire("999")
    with pytest.raises(ValueError):
        lecteur().lire("123", 9, 12)


def test_verifier_une_citation():
    l = lecteur()
    assert l.verifier("confluence://TBT/123@7#L1-L2")
    assert l.verifier("`confluence://TBT/123@6#L2`")
    assert not l.verifier("confluence://TBT/123@6#L3")        # ligne absente à cette version
    assert not l.verifier("confluence://AUTRE/123@7#L1")      # autre espace
    assert not l.verifier("jira://TBT/123@7#L1")              # autre système
    assert not l.verifier("confluence://TBT/123@9#L1")        # version inexistante


def test_une_citation_de_code_n_est_pas_une_citation_de_source():
    assert RE_CITATION_SOURCE.search("git://depot@abc123:app.py#L1-L2") is None
    assert RE_CITATION_SOURCE.search("voir confluence://TBT/123@7#L4-L9.")["ref"] == "123"
