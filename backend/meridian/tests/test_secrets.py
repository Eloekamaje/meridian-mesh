"""Règles partagées de refus des secrets dans les URL."""
from __future__ import annotations

import pytest

from meridian.domain.secrets import sans_secret


def test_une_url_sans_secret_est_conservee():
    assert sans_secret("https://api.exemple.test/accounts", "cible") == (
        "https://api.exemple.test/accounts")


def test_une_valeur_non_url_est_conservee():
    assert sans_secret("comptes-api", "cible") == "comptes-api"


def test_les_identifiants_dans_l_url_sont_refuses():
    with pytest.raises(ValueError, match="identifiants"):
        sans_secret("https://user:pass@api.exemple.test/accounts", "cible")


def test_une_cle_sensible_en_requete_est_refusee():
    with pytest.raises(ValueError, match="secret"):
        sans_secret("https://api.exemple.test/accounts?token=abc", "cible")
