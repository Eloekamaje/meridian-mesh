"""DeepSeek Search/Fetch : outils réels, réponses bornées, pas de faux embeddings."""
from meridian.adapters.outbound import deepseek


class _Reponse:
    def __init__(self, data): self.data = data
    def raise_for_status(self): return None
    def json(self): return self.data


def test_search_borne_et_normalise(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    monkeypatch.setattr(deepseek.requests, "post", lambda *a, **k: _Reponse({"results": [{
        "title": "T", "url": "https://example.test/a", "snippet": "S", "summary": "R",
        "content": "C", "site_name": "Example", "authority": 3, "rerank_score": 2.5,
    }]}))
    resultat = deepseek.search("question", nombre=1)
    assert resultat["resultats"][0]["titre"] == "T"
    assert resultat["resultats"][0]["url"] == "https://example.test/a"


def test_fetch_refuse_une_url_non_http(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    try:
        deepseek.fetch("file:///etc/passwd")
    except ValueError as e:
        assert "URL" in str(e)
    else:
        raise AssertionError("URL non HTTP acceptée")


def test_les_manifestes_web_sont_read_only():
    manifestes = deepseek.manifestes_web()
    assert {m.nom for m in manifestes} == {"rechercher_web", "lire_page"}
    assert all(m.lecture_seule for m in manifestes)


def test_le_web_deepseek_est_desactive_en_mode_bedrock(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    monkeypatch.setenv("JUMEAU_MODELE", "bedrock")
    monkeypatch.delenv("WEB_PROVIDER", raising=False)
    assert deepseek.disponible_web() is False
    monkeypatch.setenv("WEB_PROVIDER", "deepseek")
    assert deepseek.disponible_web() is True
