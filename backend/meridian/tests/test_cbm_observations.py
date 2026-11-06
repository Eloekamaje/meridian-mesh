"""Provider CBM : nœuds, relations, filtre, couverture et tolérance aux pannes."""
from meridian.adapters.outbound.connectors import cbm
from meridian.adapters.outbound.connectors.cbm_observations import (
    LABELS,
    RELATIONS,
    CbmObservations,
)

KINDS = {
    "cbm_file", "cbm_module", "cbm_class", "cbm_function", "cbm_method",
    "cbm_variable", "cbm_section", "cbm_table", "cbm_route", "cbm_env",
    "cbm_package", "cbm_decorator", "cbm_process", "cbm_image", "cbm_resource",
}

NOEUDS = {
    "File": [{
        "name": "src/App.java", "file_path": "src/App.java",
        "start_line": 1, "end_line": 90, "label": "File",
    }],
    "Module": [{
        "name": "billing", "qualified_name": "billing",
        "file_path": "src/billing.py", "start_line": 1, "end_line": 10, "label": "Module",
    }],
    "Class": [{
        "name": "App", "qualified_name": "demo.App", "file_path": "src/App.java",
        "start_line": 5, "end_line": 80, "label": "Class",
    }],
    "Function": [{
        "name": "main", "qualified_name": "demo.App.main", "file_path": "src/App.java",
        "start_line": 20, "end_line": 30,
    }],
    "Method": [{
        "name": "run", "qualified_name": "demo.App.run", "file_path": "src/App.java",
        "start_line": 40, "end_line": 50,
    }],
    "Variable": [{
        "name": "MAX", "qualified_name": "demo.App.MAX", "file_path": "src/App.java",
        "start_line": 3, "end_line": 3,
    }],
    "Section": [{
        "name": "entete", "file_path": "web/page.jsp", "start_line": 1, "end_line": 8,
    }],
    "Table": [{
        "name": "CLIENTS", "qualified_name": "public.clients", "file_path": "sql/schema.sql",
        "start_line": 12, "end_line": 20,
    }],
    "Route": [{
        "name": "/clients", "file_path": "web/WEB-INF/web.xml", "start_line": 7, "end_line": 7,
    }],
    "EnvVar": [{
        "name": "DB_URL", "file_path": "conf/app.env", "start_line": 2, "end_line": 2,
    }],
    "Package": [{
        "name": "org.springframework", "file_path": "pom.xml", "start_line": 30, "end_line": 30,
    }],
    "Decorator": [{
        "name": "Transactional", "qualified_name": "org.springframework.Transactional",
        "file_path": "src/App.java", "start_line": 18, "end_line": 18,
    }],
    "Process": [{
        "name": "BATCH01", "file_path": "jobs/BATCH01.jcl", "start_line": 1, "end_line": 5,
    }],
    "Image": [{
        "name": "eclipse-temurin:21", "file_path": "deploy/Dockerfile",
        "start_line": 1, "end_line": 1,
    }],
    "Resource": [{
        "name": "application.properties",
        "file_path": "src/main/resources/application.properties",
        "start_line": 1, "end_line": 1,
    }],
}


def _runner(noeuds=None, relations=None, appels=None):
    noeuds = noeuds or {}
    relations = relations or {}

    def runner(requete):
        if appels is not None:
            appels.append(requete)
        for label, lignes in noeuds.items():
            if f"MATCH (n:{label})" in requete:
                return [dict(ligne) for ligne in lignes]
        for type_relation, lignes in relations.items():
            if f"[:{type_relation}]" in requete:
                return [dict(ligne) for ligne in lignes]
        return []

    return runner


def _par_kind(observations):
    resultat = {}
    for observation in observations:
        resultat.setdefault(observation.kind, []).append(observation)
    return resultat


def test_couvre_tous_les_labels_avec_les_bons_kinds(tmp_path):
    observations = CbmObservations("demo", runner=_runner(NOEUDS)).index(str(tmp_path))
    kinds = _par_kind(observations)

    assert set(kinds) == KINDS
    assert len(observations) == len(LABELS) == 15
    for label, kind in LABELS.items():
        observation = kinds[kind][0]
        assert observation.attributes["label"] == label
        assert observation.provider == "cbm"
        assert observation.parser == "cbm-graph"
        assert observation.parser_version == "1"
        assert observation.status == "extracted"
        assert observation.confidence == 1.0

    fonction = kinds["cbm_function"][0]
    assert fonction.symbol == "demo.App.main"
    assert fonction.attributes["name"] == "main"
    assert fonction.attributes["qualified_name"] == "demo.App.main"
    assert (fonction.file, fonction.start, fonction.end) == ("src/App.java", 20, 30)
    assert fonction.language == "java"

    table = kinds["cbm_table"][0]
    assert (table.symbol, table.file, table.language) == ("public.clients", "sql/schema.sql", "sql")


def test_langage_deduit_de_l_extension(tmp_path):
    observations = CbmObservations("demo", runner=_runner(NOEUDS)).index(str(tmp_path))

    langues = {observation.file: observation.language for observation in observations}
    assert langues == {
        "src/App.java": "java",
        "src/billing.py": "python",
        "web/page.jsp": "jsp",
        "sql/schema.sql": "sql",
        "web/WEB-INF/web.xml": "xml",
        "conf/app.env": "dotenv",
        "pom.xml": "xml",
        "jobs/BATCH01.jcl": "jcl",
        "deploy/Dockerfile": "dockerfile",
        "src/main/resources/application.properties": "properties",
    }


def test_relations_calls_emettent_kind_et_attributs(tmp_path):
    relations = {"CALLS": [
        {
            "type": "CALLS", "source": "demo.App.main", "target": "demo.Service.run",
            "source_file": "src/App.java", "target_file": "src/Service.java",
        },
        {
            "type": "calls", "source": "demo.App.main", "target": "demo.Util.log",
            "source_file": "src/App.java", "target_file": "src/Util.java",
        },
    ]}
    observations = CbmObservations("demo", runner=_runner(relations=relations)).index(str(tmp_path))
    calls = [observation for observation in observations if observation.kind == "cbm_relation_calls"]

    assert len(calls) == 2
    premier = next(o for o in calls if o.attributes["target"] == "demo.Service.run")
    assert premier.symbol == "demo.App.main"
    assert premier.file == "src/App.java"
    assert premier.language == "java"
    assert premier.attributes == {
        "type": "CALLS",
        "source": "demo.App.main",
        "target": "demo.Service.run",
        "source_file": "src/App.java",
        "target_file": "src/Service.java",
    }


def test_filtre_fichiers_relatifs_et_absolus(tmp_path):
    relations = {"CALLS": [{
        "source": "demo.App.main", "target": "billing",
        "source_file": "src/App.java", "target_file": "src/billing.py",
    }]}
    provider = CbmObservations("demo", runner=_runner(NOEUDS, relations))

    relatifs = provider.index(str(tmp_path), fichiers=["src/billing.py"])
    assert {o.file for o in relatifs if not o.kind.startswith("cbm_relation_")} == {"src/billing.py"}
    relation = next(o for o in relatifs if o.kind == "cbm_relation_calls")
    assert relation.attributes["target"] == "billing"
    assert relation.file == "src/billing.py"

    absolus = provider.index(str(tmp_path), fichiers=[str(tmp_path / "sql/schema.sql")])
    assert {o.file for o in absolus} == {"sql/schema.sql"}
    assert [o.kind for o in absolus] == ["cbm_table"]


def test_couverture_indexe_et_non_supporte(tmp_path):
    provider = CbmObservations("demo", runner=_runner(NOEUDS))
    lignes = provider.couverture(
        str(tmp_path), fichiers=["src/App.java", "src/Absent.java", "docs/readme.md"])
    par_fichier = {ligne.file: ligne for ligne in lignes}

    assert set(par_fichier) == {"src/App.java", "src/Absent.java", "docs/readme.md"}
    assert par_fichier["src/App.java"].statut == "indexe"
    assert par_fichier["src/App.java"].language == "java"
    assert par_fichier["src/App.java"].parser == "cbm-graph"
    assert par_fichier["src/App.java"].raison == ""
    assert par_fichier["src/Absent.java"].statut == "non_supporte"
    assert par_fichier["src/Absent.java"].raison
    assert par_fichier["docs/readme.md"].language == "markdown"

    toutes = {ligne.file for ligne in provider.couverture(str(tmp_path))}
    assert "src/App.java" in toutes
    assert "src/billing.py" in toutes


def test_panne_cbm_ne_fait_pas_tomber_index_ni_couverture(tmp_path):
    def runner(requete):
        raise RuntimeError("CBM en panne")

    provider = CbmObservations("demo", runner=runner)

    assert provider.index(str(tmp_path), fichiers=["src/App.java"]) == []

    lignes = provider.couverture(str(tmp_path), fichiers=["src/App.java", "src/Absent.java"])
    assert [ligne.statut for ligne in lignes] == ["partiel", "partiel"]
    assert all("CBM en panne" in ligne.raison for ligne in lignes)
    assert provider.couverture(str(tmp_path)) == []


def test_dedoublonne_les_noeuds_mais_conserve_les_relations(tmp_path):
    noeud = {
        "name": "main", "qualified_name": "demo.App.main", "file_path": "src/App.java",
        "start_line": 20, "end_line": 30, "label": "Function",
    }
    relation = {
        "type": "CALLS", "source": "demo.App.main", "target": "demo.Service.run",
        "source_file": "src/App.java", "target_file": "src/Service.java",
    }
    runner = _runner(
        noeuds={"Function": [noeud, dict(noeud)]},
        relations={"CALLS": [relation, dict(relation)]},
    )
    observations = CbmObservations("demo", runner=runner).index(str(tmp_path))

    assert len([o for o in observations if o.kind == "cbm_function"]) == 1
    assert len([o for o in observations if o.kind == "cbm_relation_calls"]) == 2
    for observation in observations:
        assert observation.provider == "cbm"
        assert observation.parser == "cbm-graph"
        assert observation.parser_version == "1"
        assert observation.status == "extracted"
        assert observation.confidence == 1.0


def test_requetes_bornees_couvrent_tous_les_labels_et_relations(tmp_path):
    appels = []
    CbmObservations("demo", runner=_runner(appels=appels)).index(str(tmp_path))

    assert len(appels) == len(LABELS) + len(RELATIONS) == 27
    assert all("LIMIT 100000" in requete for requete in appels)
    for label in LABELS:
        assert any(f"MATCH (n:{label})" in requete for requete in appels)
    for relation in RELATIONS:
        assert any(f"[:{relation}]" in requete for requete in appels)


def test_runner_par_defaut_convertit_colonnes_et_lignes(tmp_path, monkeypatch):
    appels = []

    def faux_cli(*args):
        appels.append(args)
        requete = args[args.index("--query") + 1]
        if "MATCH (n:File)" in requete:
            return {
                "columns": [
                    "name", "qualified_name", "file_path",
                    "start_line", "end_line", "label",
                ],
                "rows": [["src/App.java", None, "src/App.java", 1, 42, "File"]],
            }
        return {"columns": [], "rows": []}

    monkeypatch.setattr(cbm, "_cli", faux_cli)
    observations = CbmObservations("demo").index(str(tmp_path))

    assert len(observations) == 1
    observation = observations[0]
    assert observation.kind == "cbm_file"
    assert observation.symbol == "src/App.java"
    assert (observation.start, observation.end) == (1, 42)

    premier = appels[0]
    assert premier[0] == "query_graph"
    assert premier[1:3] == ("--project", "demo")
    assert premier[-2:] == ("--format", "json")
    assert "MATCH (n:File)" in premier[premier.index("--query") + 1]


def test_resultats_vides_sont_toleres(tmp_path):
    provider = CbmObservations("demo", runner=lambda requete: [])

    assert provider.index(str(tmp_path)) == []
    lignes = provider.couverture(str(tmp_path), fichiers=["src/App.java"])
    assert [ligne.statut for ligne in lignes] == ["non_supporte"]
    assert lignes[0].raison
