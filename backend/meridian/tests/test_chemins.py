"""Primitives de chemins : normalisation, motifs, suffixe et préfixe."""
from __future__ import annotations

from meridian.domain import chemins


def test_normaliser_absorbe_query_jsessionid_et_slashes():
    assert chemins.normaliser("//api//accounts/42/?x=1#top") == "/api/accounts/42"
    assert chemins.normaliser("/api/accounts;jsessionid=ABC") == "/api/accounts"
    assert chemins.normaliser("") == ""
    assert chemins.normaliser("/") == "/"


def test_segments_et_variables():
    assert chemins.segments("/api/accounts/{id}") == ["api", "accounts", "{id}"]
    assert chemins.est_variable("{id}")
    assert chemins.est_variable("<identifiant>")
    assert chemins.est_variable(":id")
    assert not chemins.est_variable("accounts")


def test_motif_compatible_avec_variables_et_jokers():
    assert chemins.motif_compatible("/api/accounts/{id}", "/api/accounts/42")
    assert chemins.motif_compatible("/api/*/accounts", "/api/v1/accounts")
    assert chemins.motif_compatible("/api/**", "/api/v1/accounts/42")
    assert not chemins.motif_compatible("/api/accounts/{id}", "/api/accounts")
    assert not chemins.motif_compatible("/api/accounts", "/api/accounts/42")


def test_score_suffixe_absorbe_le_prefixe_de_gateway():
    assert chemins.score_suffixe("/accounts/42", "/api/accounts/{id}") == 4
    assert chemins.score_suffixe("/accounts", "/api/accounts") > 0
    assert chemins.score_suffixe("/accounts", "/api/accounts/{id}") == 0
    assert chemins.score_suffixe("/123", "/{id}") == 0


def test_prefixe_est_strict_sur_les_segments():
    assert chemins.prefixe("/api", "/api/accounts")
    assert chemins.prefixe("/api", "/api")
    assert not chemins.prefixe("/api/v2", "/api/accounts")
    assert chemins.prefixe("/", "/anything")
