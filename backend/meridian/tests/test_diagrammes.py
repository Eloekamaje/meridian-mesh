"""Compilation des schémas en SVG autonome."""
from meridian.application import diagrammes


def _schema():
    return {
        "type": "architecture", "titre": "Paiements",
        "boites": [{"id": "api", "libelle": "API"}, {"id": "db", "libelle": "Base"}],
        "fleches": [{"de": "api", "vers": "db", "libelle": "écrit", "etat": "code"}],
    }


def test_un_schema_produit_un_svg_autonome_et_hashé():
    artefact = diagrammes.compiler(_schema())
    assert artefact["type"] == "design-diagram"
    assert artefact["largeur"] > 0 and artefact["hauteur"] > 0
    assert artefact["hash"]
    assert "<svg" in artefact["svg"]
    assert 'data-node-id="api"' in artefact["svg"]
    assert "marker-end" in artefact["svg"]


def test_les_libelles_sont_echappes():
    schema = _schema()
    schema["boites"][0]["libelle"] = "<script>alert(1)</script>"
    svg = diagrammes.compiler(schema)["svg"]
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg


def test_les_schemas_vides_ou_inconnus_sont_ignores():
    assert diagrammes.compiler(None) is None
    assert diagrammes.compiler({"type": "inconnu", "boites": [], "fleches": []}) is None


def test_une_reponse_est_enrichie_sans_modifier_les_schemas():
    reponse = {"schemas": [_schema()], "reponse": "ok"}
    enrichie = diagrammes.enrichir_reponse(dict(reponse))
    assert enrichie["schemas"] == reponse["schemas"]
    assert len(enrichie["diagrammes"]) == 1
    assert enrichie["diagrammes"][0]["hash"]


def test_une_sequence_compile_ses_acteurs_et_messages():
    schema = {"type": "sequence", "titre": "Flux",
              "boites": [{"id": "a", "libelle": "A"}, {"id": "b", "libelle": "B"}],
              "fleches": [{"de": "a", "vers": "b", "libelle": "appelle", "etat": "code"}]}
    artefact = diagrammes.compiler(schema)
    assert artefact["type"] == "design-diagram"
    assert 'data-node-id="a"' in artefact["svg"]
    assert "appelle" in artefact["svg"]


def test_un_modele_de_donnees_compile_comme_une_architecture():
    schema = {"type": "data-model", "titre": "Abonnements",
              "boites": [{"id": "membre", "libelle": "Membre"}, {"id": "abonnement", "libelle": "Abonnement"}],
              "fleches": [{"de": "abonnement", "vers": "membre", "libelle": "suit", "etat": "code"}]}
    artefact = diagrammes.compiler(schema)
    assert artefact and "<svg" in artefact["svg"]
    assert 'data-node-id="membre"' in artefact["svg"]


def test_une_chaine_longue_est_repliee_en_grille():
    schema = {
        "type": "flux", "titre": "Chaîne",
        "boites": [{"id": f"n{i}", "libelle": f"Étape {i}"} for i in range(9)],
        "fleches": [{"de": f"n{i}", "vers": f"n{i + 1}", "libelle": "puis", "etat": "code"}
                    for i in range(8)],
    }
    artefact = diagrammes.compiler(schema)
    assert artefact["largeur"] <= 1200
    assert artefact["hauteur"] > artefact["largeur"] / 3


def test_les_zones_disjointes_sont_dessinees_et_les_chevauchements_ignores():
    schema = _schema()
    schema.update({
        "boites": [{"id": "api", "libelle": "API"}, {"id": "db", "libelle": "Base"},
                   {"id": "ui", "libelle": "Caisse"}, {"id": "audit", "libelle": "Audit"}],
        "fleches": [{"de": "ui", "vers": "api", "libelle": "demande", "etat": "code"},
                    {"de": "api", "vers": "db", "libelle": "écrit", "etat": "code"},
                    {"de": "api", "vers": "audit", "libelle": "trace", "etat": "code"}],
        "groupes": [{"libelle": "Entrée", "ids": ["ui"]},
                    {"libelle": "Cœur", "ids": ["db", "audit"]}],
    })
    svg = diagrammes.compiler(schema)["svg"]
    assert svg.count('data-zone="1"') == 2
    assert "Entrée" in svg and "Cœur" in svg

    chevauchants = {**schema, "groupes": [
        {"libelle": "Tout", "ids": ["api", "db", "ui", "audit"]},
        {"libelle": "Base", "ids": ["db"]},
    ]}
    assert 'data-zone="1"' not in diagrammes.compiler(chevauchants)["svg"]


def test_un_libelle_de_noeud_long_est_replie_dans_la_boite():
    schema = _schema()
    schema["boites"][0]["libelle"] = "Un libellé de nœud vraiment très long qui doit tenir"
    svg = diagrammes.compiler(schema)["svg"]
    assert "vraiment très" in svg
    assert "doit tenir" in svg
    assert svg.count("<tspan") >= 2


def test_le_plan_reprend_les_positions_du_compilateur():
    schema = {
        "type": "flux", "titre": "Chaîne",
        "boites": [{"id": f"n{i}", "libelle": f"Étape {i}"} for i in range(9)],
        "fleches": [{"de": f"n{i}", "vers": f"n{i + 1}", "libelle": "puis", "etat": "code"}
                    for i in range(8)],
    }
    plan = diagrammes.plan(schema)
    assert plan is not None
    assert len(plan["boites"]) == 9
    assert plan["viewBox"] == f'0 0 {plan["largeur"]} {plan["hauteur"]}'
    assert [b["id"] for b in plan["boites"]] == [f"n{i}" for i in range(9)]
