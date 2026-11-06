from meridian.adapters.outbound.connectors.ingerer import _filtrer_routes_couvertes


def test_les_routes_enquete_remplacent_les_routes_cbm_sans_prefixe():
    cbm = [{"predicat": "EXPOSE", "objet": "GET /contacts"},
           {"predicat": "EXPOSE", "objet": "GET /api/health"},
           {"predicat": "DEPEND_DE", "objet": "fastapi"}]
    enquete = [{"predicat": "EXPOSE", "objet": "GET /api/contacts"},
               {"predicat": "EXPOSE", "objet": "GET /api/health"}]
    assert _filtrer_routes_couvertes(cbm, enquete) == [
        {"predicat": "DEPEND_DE", "objet": "fastapi"},
    ]
