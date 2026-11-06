"""Permission de publication de la carte : rôle, autorité ou équipe propriétaire."""
from types import SimpleNamespace

from meridian.adapters.inbound.http import interfaces
from meridian.domain import roles

JUMEAU = {"equipe": "equipe-tbt"}


def _request(**etat):
    return SimpleNamespace(state=SimpleNamespace(**etat))


def test_role_canonique_mappe_les_postes_sur_les_roles_adr():
    attendus = {
        "product_owner": "APPLICATION_OWNER",
        "application_owner": "APPLICATION_OWNER",
        "architecte": "PORTFOLIO_OWNER",
        "portfolio_owner": "PORTFOLIO_OWNER",
        "admin": "TENANT_ADMIN",
        "administrateur": "TENANT_ADMIN",
        "tenant_admin": "TENANT_ADMIN",
        "developpeur": "MAINTAINER",
        "mainteneur": "MAINTAINER",
        "lecteur": "VIEWER",
        "auditeur": "AUDITOR",
    }
    assert {poste: roles.role_canonique(poste) for poste in attendus} == attendus


def test_role_canonique_normalise_casse_accents_et_separateurs():
    assert roles.role_canonique("  Product Owner ") == "APPLICATION_OWNER"
    assert roles.role_canonique("Développeur") == "MAINTAINER"
    assert roles.role_canonique("Auditeur") == "AUDITOR"
    assert roles.role_canonique("tenant-admin") == "TENANT_ADMIN"
    assert roles.role_canonique("AUDITOR") == "AUDITOR"
    assert roles.role_canonique("MEMBER") == "MEMBER"
    assert roles.role_canonique("inconnu") == ""
    assert roles.role_canonique(None) == ""


def test_publication_autorisee_en_demo():
    assert interfaces._peut_publier(_request(auth_mode="demo"), JUMEAU)


def test_publication_autorisee_par_role_ou_autorite():
    assert interfaces._peut_publier(_request(auth_mode="local", role="product_owner"), JUMEAU)
    assert interfaces._peut_publier(_request(auth_mode="local", role="Product Owner"), JUMEAU)
    assert interfaces._peut_publier(_request(auth_mode="local", role="architecte"), JUMEAU)
    assert interfaces._peut_publier(_request(auth_mode="local", role="tenant_admin"), JUMEAU)
    assert interfaces._peut_publier(_request(auth_mode="local", autorite="decision"), JUMEAU)


def test_publication_refusee_hors_roles_de_publication():
    assert not interfaces._peut_publier(_request(auth_mode="local", role="developpeur"), JUMEAU)
    assert not interfaces._peut_publier(_request(auth_mode="local", role="Développeur"), JUMEAU)
    assert not interfaces._peut_publier(_request(auth_mode="local", role="auditeur"), JUMEAU)
    assert not interfaces._peut_publier(_request(auth_mode="local", role="lecteur"), JUMEAU)


def test_publication_autorisee_par_equipe_proprietaire():
    assert interfaces._peut_publier(
        _request(auth_mode="local", role="membre", equipe="equipe-tbt"), JUMEAU)
    assert not interfaces._peut_publier(
        _request(auth_mode="local", role="membre", equipe="autre"), JUMEAU)


def test_publication_autorisee_par_equipes_identite():
    assert interfaces._peut_publier(
        _request(auth_mode="local", role="membre", equipes=["equipe-tbt"]), JUMEAU)
    assert interfaces._peut_publier(
        _request(auth_mode="oidc", role="membre", equipes=["autre", "equipe-tbt"]), JUMEAU)
    assert not interfaces._peut_publier(
        _request(auth_mode="local", role="membre", equipes=["autre"]), JUMEAU)
