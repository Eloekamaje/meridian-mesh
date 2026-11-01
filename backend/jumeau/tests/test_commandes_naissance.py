"""Les chemins de naissance d'une commande : code ou ancre ServiceNow/CMDB + substance."""
import pytest

server = pytest.importorskip("server")


def test_le_code_suffit():
    assert server.naissance_possible({"github"})


def test_ancre_servicenow_ou_cmdb_avec_substance():
    assert server.naissance_possible({"servicenow", "datadog"})
    assert server.naissance_possible({"cmdb", "confluence"})
    assert server.naissance_possible({"servicenow", "otlp"})


def test_sans_code_sans_ancre_ou_sans_substance_est_refuse():
    assert not server.naissance_possible({"datadog"})
    assert not server.naissance_possible({"servicenow"})
    assert not server.naissance_possible({"jira", "servicenow"})
    assert not server.naissance_possible({"confluence"})
