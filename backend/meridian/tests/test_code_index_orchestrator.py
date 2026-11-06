"""Contrat de l'orchestrateur : découverte, tolérance aux pannes, conflits et rapport."""
import json

from meridian.application.code_index_orchestrator import OrchestrateurCodeIndex
from meridian.domain.code_index import CouvertureFichier, Observation


def _obs(provider, fichier, symbol="client"):
    return Observation(
        provider=provider, parser="faux", parser_version="1", file=fichier,
        language="python", kind="form", symbol=symbol, start=1, end=2,
    )


def _ecrire(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.jsp").write_text("<%\n")
    (tmp_path / "notes.txt").write_text("hors index\n")
    for nom in (".git", "node_modules", ".venv"):
        dossier = tmp_path / nom
        dossier.mkdir()
        (dossier / "ignore.py").write_text("x = 2\n")


class AdapterTout:
    provider = "alpha"

    def index(self, racine, *, fichiers=()):
        return [_obs(self.provider, fichier) for fichier in fichiers]

    def couverture(self, racine, *, fichiers=()):
        return [
            CouvertureFichier(file=fichier, language="python", parser="faux", statut="indexe")
            for fichier in fichiers
        ]


class AdapterPythonSeulement:
    provider = "python"

    def index(self, racine, *, fichiers=()):
        return [_obs(self.provider, fichier) for fichier in fichiers if fichier.endswith(".py")]

    def couverture(self, racine, *, fichiers=()):
        return []


class AdapterEnPanne:
    provider = "casse"

    def index(self, racine, *, fichiers=()):
        raise RuntimeError("panne simulée")

    def couverture(self, racine, *, fichiers=()):
        raise AssertionError("la couverture ne doit pas masquer l'échec d'indexation")


def test_succes_decouverte_filtre_et_rapport(tmp_path):
    _ecrire(tmp_path)
    orchestrateur = OrchestrateurCodeIndex([AdapterTout()], extensions={".py", ".jsp"})

    rapport = orchestrateur.rapport(str(tmp_path))

    assert rapport["providers"] == ["alpha"]
    assert rapport["fichiers_decouverts"] == ["a.py", "b.jsp"]
    assert {ligne["file"] for ligne in rapport["couvertures"]} == {"a.py", "b.jsp"}
    assert rapport["compteurs"]["indexe"] == 2
    assert len(rapport["observations"]) == 2
    assert rapport["erreurs"] == []


def test_decouvreur_injectable(tmp_path):
    _ecrire(tmp_path)
    appels = []

    def decouvreur(racine):
        appels.append(racine)
        return ["b.jsp"]

    orchestrateur = OrchestrateurCodeIndex([AdapterTout()], decouvreur=decouvreur)
    rapport = orchestrateur.rapport(str(tmp_path))

    assert appels == [str(tmp_path)]
    assert rapport["fichiers_decouverts"] == ["b.jsp"]
    assert rapport["compteurs"]["indexe"] == 1


def test_panne_d_un_adapter_produit_une_couverture_partielle(tmp_path):
    _ecrire(tmp_path)
    orchestrateur = OrchestrateurCodeIndex([AdapterEnPanne()], extensions={".py", ".jsp"})

    rapport = orchestrateur.rapport(str(tmp_path))

    assert [ligne["statut"] for ligne in rapport["couvertures"]] == ["partiel", "partiel"]
    assert all("casse" in ligne["raison"] for ligne in rapport["couvertures"])
    assert rapport["compteurs"]["partiel"] == 2
    assert rapport["erreurs"] == [{
        "provider": "casse",
        "phase": "index",
        "type": "RuntimeError",
        "message": "panne simulée",
    }]


def test_panne_n_empeche_pas_les_autres_adapters(tmp_path):
    _ecrire(tmp_path)
    orchestrateur = OrchestrateurCodeIndex(
        [AdapterPythonSeulement(), AdapterEnPanne()], extensions={".py", ".jsp"}
    )

    rapport = orchestrateur.rapport(str(tmp_path))
    statuts = {ligne["file"]: ligne["statut"] for ligne in rapport["couvertures"]}

    assert statuts == {"a.py": "indexe", "b.jsp": "partiel"}
    assert len(rapport["observations"]) == 1


def test_conflit_entre_providers_est_conserve(tmp_path):
    _ecrire(tmp_path)

    class AdapterBeta(AdapterTout):
        provider = "beta"

    orchestrateur = OrchestrateurCodeIndex(
        [AdapterTout(), AdapterBeta()], extensions={".py"}
    )

    observations = orchestrateur.index(str(tmp_path))
    rapport = orchestrateur.rapport(str(tmp_path))

    assert len(observations) == 1
    assert observations[0].status == "conflict"
    assert observations[0].attributes["providers"] == ["alpha", "beta"]
    assert rapport["couvertures"][0]["statut"] == "conflit"
    assert rapport["compteurs"]["conflit"] == 1


def test_fichier_non_supporte_reste_visible(tmp_path):
    _ecrire(tmp_path)
    orchestrateur = OrchestrateurCodeIndex([AdapterPythonSeulement()])

    rapport = orchestrateur.rapport(str(tmp_path))
    statuts = {ligne["file"]: ligne for ligne in rapport["couvertures"]}

    assert statuts["a.py"]["statut"] == "indexe"
    assert statuts["b.jsp"]["statut"] == "non_supporte"
    assert statuts["notes.txt"]["statut"] == "non_supporte"
    assert set(statuts) == {"a.py", "b.jsp", "notes.txt"}


def test_rapport_serialisable_en_json(tmp_path):
    _ecrire(tmp_path)
    orchestrateur = OrchestrateurCodeIndex(
        [AdapterTout(), AdapterEnPanne()], extensions={".py", ".jsp"}
    )

    rapport = orchestrateur.rapport(str(tmp_path))
    relu = json.loads(json.dumps(rapport, ensure_ascii=False))

    assert set(relu) == {
        "racine", "providers", "fichiers_decouverts", "observations",
        "couvertures", "compteurs", "erreurs",
    }
    assert sum(relu["compteurs"].values()) == len(relu["couvertures"])
    assert relu["providers"] == ["alpha", "casse"]
