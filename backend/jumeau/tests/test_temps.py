"""Le temps du jumeau : historique au commit ingéré, commits entre deux versions, évolution des connaissances."""
import subprocess

import pytest

from jumeau import depot, temps
from jumeau.source_git import sha_courant
from jumeau.tests.conftest import ACTIVITE, JUMEAU, SOURCE, besoin_pg, claim


def commit(depot_git, fichier, contenu, message, date):
    (depot_git / fichier).write_text(contenu)
    env = {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date, "PATH": "/usr/bin:/bin"}
    subprocess.run(["git", "-C", str(depot_git), "add", "."], check=True)
    subprocess.run(["git", "-C", str(depot_git), "-c", "user.name=Alice", "-c", "user.email=a@a", "commit", "-qm", message],
                   check=True, env=env)
    return sha_courant(depot_git)


@pytest.fixture
def histoire(depot_git):
    sha_regle = commit(depot_git, "regles.py", "PLAFOND = 500\n", "Plafond de virement à 500", "2026-09-01T10:00:00")
    sha_api = commit(depot_git, "api.py", "route = '/virements'\n", "Expose les virements", "2026-10-01T10:00:00")
    sha_futur = commit(depot_git, "futur.py", "x = 1\n", "Pas encore ingéré", "2026-10-20T10:00:00")
    source = {"nom": "tbt", "emplacement": str(depot_git), "curseur": sha_api}
    return source, sha_regle, sha_api, sha_futur


def test_historique_s_arrete_au_commit_ingere(histoire):
    source, _, sha_api, _ = histoire
    messages = [c["message"] for c in temps.historique(source)]
    assert messages[0] == "Expose les virements" and "Pas encore ingéré" not in messages
    c = temps.historique(source)[0]
    assert (c["sha"], c["date"], c["auteur"], c["fichiers"]) == (sha_api[:12], "2026-10-01", "Alice", ["api.py"])


def test_historique_filtre_par_date_et_par_chemin(histoire):
    source, *_ = histoire
    assert [c["message"] for c in temps.historique(source, depuis="2026-09-15")] == ["Expose les virements"]
    assert [c["message"] for c in temps.historique(source, chemin="regles.py")] == ["Plafond de virement à 500"]


def test_historique_refuse_les_arguments_dangereux(histoire):
    source, *_ = histoire
    for mauvais in ({"depuis": "--all"}, {"chemin": "../x"}, {"depuis": "hier; rm"}):
        with pytest.raises(ValueError):
            temps.historique(source, **mauvais)


def test_commits_entre_deux_versions_avec_fichiers_touches(histoire):
    source, sha_regle, sha_api, _ = histoire
    [c] = temps.commits_entre(source, sha_regle, sha_api)
    assert c["message"] == "Expose les virements" and c["fichiers"] == ["api.py"]


def test_commits_entre_sans_version_precedente(histoire):
    source, *_ = histoire
    assert len(temps.commits_entre(source, None, source["curseur"])) == 3  # init + 2


@besoin_pg
def test_evolution_des_connaissances_depuis_une_date(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor"), claim("fastapi", ligne=1)], ACTIVITE)
    conn.execute("UPDATE claim SET valide_depuis = '2026-09-01' WHERE objet = 'fastapi'")
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor")], ACTIVITE)  # fastapi disparaît
    e = temps.evolution(conn, "tbt", "2026-10-01")
    assert [c["objet"] for c in e["apparus"]] == ["motor"]
    assert [c["objet"] for c in e["disparus"]] == ["fastapi"]
