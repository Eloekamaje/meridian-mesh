"""A4 — groundedness : une citation fabriquée est flaguée, jamais silencieusement acceptée."""
from meridian.application import contrat_groundedness
from meridian.application import groundedness as g
from meridian.adapters.outbound.postgres.connaissance import resoudre_citations as _resoudre


def _source_fausse(tmp_path):
    """Un vrai mini-dépôt git : `lire_au_sha(emplacement, curseur)` lit src/app.py au SHA."""
    import subprocess
    depot = tmp_path / "repo"
    (depot / "src").mkdir(parents=True)
    (depot / "src" / "app.py").write_text("\n".join(f"ligne {i}" for i in range(1, 101)))
    for cmd in (["init", "-q"], ["add", "."], ["-c", "user.email=t@t", "-c", "user.name=t",
                "commit", "-qm", "init"]):
        subprocess.run(["git", *cmd], cwd=depot, check=True, capture_output=True)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=depot,
                         check=True, capture_output=True, text=True).stdout.strip()
    return {"nom": "repo", "emplacement": str(depot), "curseur": sha}


def test_citation_fabriquee_flaggee(tmp_path):
    resoudre = _resoudre([_source_fausse(tmp_path)])
    rapport = g.noter("preuve : src/app.py#L999-L1000", resoudre)
    assert rapport["non_resolues"] == 1
    assert rapport["verifiees"] == 0
    assert rapport["detail"][0]["verdict"] == "non_resolu"


def test_citation_reelle_resolue(tmp_path):
    resoudre = _resoudre([_source_fausse(tmp_path)])
    rapport = g.noter("preuve : src/app.py#L10-L12", resoudre)
    assert rapport["verifiees"] == 1
    assert rapport["groundedness"] == 1.0


def test_fichier_absent_et_depot_inconnu(tmp_path):
    resoudre = _resoudre([_source_fausse(tmp_path)])
    assert g.noter("autre.py#L1", resoudre)["non_resolues"] == 1
    assert g.noter("inconnu:src/app.py#L1", resoudre)["non_resolues"] == 1


def test_extraire_les_trois_types():
    texte = (
        "Voir src/app.py#L10-L12 et repo:lib/util.py#L5, "
        "confluence://espace/page@1#L3-L4, pièce:plan-2024#risques"
    )
    cites = g.extraire(texte)
    types = {c["type"] for c in cites}
    assert "code" in types
    assert "piece" in types


def test_sans_resolveur_tout_est_indetermine():
    rapport = g.noter("src/app.py#L1")
    assert rapport["indetermines"] == 1
    assert rapport["verifiees"] == 0


def test_sans_citation_score_neutre():
    rapport = g.noter("réponse sans citation", _resoudre([]))
    assert rapport["total"] == 0
    assert rapport["groundedness"] == 1.0


# --- C7 — le contrat avec résolveur réel (sources du jumeau, dépôt git fixture) ---

def test_contrat_citation_reelle_verifiee(tmp_path):
    """Réponse citée contre un vrai dépôt : les citations sont vérifiées, pas de marqueur."""
    resoudre = _resoudre([_source_fausse(tmp_path)])
    reponse = contrat_groundedness.appliquer(
        {"reponse": "La validation vit dans src/app.py#L10-L12."}, resoudre=resoudre)
    assert reponse["groundedness"]["total"] == 1
    assert reponse["groundedness"]["verifiees"] == 1
    assert reponse["groundedness"]["non_resolues"] == 0
    assert "Citation non vérifiée" not in reponse["reponse"]


def test_contrat_citation_fabriquee_produit_le_marqueur(tmp_path):
    """Une citation fabriquée produit le marqueur « Citation non vérifiée » dans la réponse."""
    resoudre = _resoudre([_source_fausse(tmp_path)])
    reponse = contrat_groundedness.appliquer(
        {"reponse": "La validation vit dans src/app.py#L999."}, resoudre=resoudre)
    assert reponse["groundedness"]["non_resolues"] == 1
    assert "Citation non vérifiée" in reponse["reponse"]


def test_contrat_sans_resolveur_regime_non_verifiees():
    """Aucune source mobilisée : les citations sont comptées, jamais prétendues vérifiées."""
    reponse = contrat_groundedness.appliquer({"reponse": "Voir src/app.py#L10."})
    assert reponse["groundedness"]["verifiees"] is None
    assert reponse["groundedness"]["non_verifiees"] == 1
    assert "Citation non vérifiée" not in reponse["reponse"]
