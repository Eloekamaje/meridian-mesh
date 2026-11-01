"""Vérifier avant de citer (Harness v3 §4) : une preuve de source dépassée par une version plus récente le dit."""
from meridian.adapters.outbound.llm import contradicteur
from meridian.adapters.outbound.llm import flore
from meridian.adapters.outbound.connectors.lecteurs import LecteurMemoire

DOCS = {"123": {"titre": "Parcours", "versions": {"7": ["a", "b"], "9": ["a", "b", "c"]}},
        "456": {"titre": "Délais", "versions": {"2": ["x"]}}}


def wiki():
    return LecteurMemoire("Wiki TBT", "TBT", DOCS, systeme="confluence")


def test_une_citation_depassee_est_signalee_les_autres_non():
    texte = "Voir confluence://TBT/123@7#L1-L2 et confluence://TBT/456@2#L1."
    assert contradicteur.fraicheur(texte, [wiki()]) == {"confluence://TBT/123@7#L1-L2": "a changé depuis (v7 → v9)"}


def test_source_injoignable_ou_document_disparu():
    class Panne(LecteurMemoire):
        def version_actuelle(self, ref):
            raise OSError("réseau")
    panne = Panne("Wiki", "TBT", DOCS, systeme="confluence")
    assert contradicteur.fraicheur("confluence://TBT/123@9#L1", [panne]) == {"confluence://TBT/123@9#L1": "non revérifiée"}
    assert contradicteur.fraicheur("confluence://TBT/999@1#L1", [wiki()]) == {"confluence://TBT/999@1#L1": "n'existe plus"}


def test_une_journee_datadog_ne_perime_pas():
    jour = LecteurMemoire("Datadog", "svc", {"r": {"titre": "t", "versions": {"1": ["a"], "2": ["a"]}}}, systeme="datadog")
    jour.perissable = False
    assert contradicteur.fraicheur("datadog://svc/r@1#L1", [jour]) == {}


def test_la_preuve_porte_la_mention_le_texte_reste_intact():
    texte = "Seuls les conseillers valident (confluence://TBT/123@7#L1-L2)."
    mentions = contradicteur.fraicheur(texte, [wiki()])
    r = flore.vers_reponse_flore({"nom": "TBT"}, [], texte, (), mentions)
    assert r["preuves"][0]["source"].endswith("— a changé depuis (v7 → v9)")
    assert r["preuves"][0]["detail"] == "confluence://TBT/123@7#L1-L2"
    assert "a changé" not in r["reponse"]
