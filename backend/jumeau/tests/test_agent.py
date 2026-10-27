"""Construction de l'agent du jumeau (sans appel au modèle)."""
import pytest

from jumeau import agent

CONTEXTE = {
    "jumeau": {"id": "tbt", "tenant_id": "banque", "nom": "TBT", "equipe": "equipe-tbt"},
    "source": {"id": 1, "nom": "tbt-repo", "emplacement": "/d", "curseur": "a" * 40,
               "copie": "/copies/tbt", "index_code": "proj-tbt"},
    "claims": [{"predicat": "EXPOSE", "objet": "GET /health", "statut": "ACCEPTED"}],
    "acteur": "alice",
}


def modele_factice():
    """Vrai client, clé bidon : la construction n'appelle pas le réseau ; on teste l'assemblage, pas le LLM."""
    from strands.models.openai import OpenAIModel
    return OpenAIModel(client_args={"api_key": "factice"}, model_id="factice")


def test_nettoyer_retire_le_projet_et_le_chemin_de_la_copie():
    sortie = "proj-tbt.backend.server.autorisations Function /copies/tbt/backend/server.py 102-108"
    assert agent.nettoyer(sortie, "proj-tbt", "/copies/tbt") == "backend.server.autorisations Function backend/server.py 102-108"


def test_nettoyer_borne_la_taille():
    assert len(agent.nettoyer("x" * 50_000, "p", "/c")) <= agent.MAX_SORTIE + 40


def test_c_est_flore_qui_parle_et_le_jumeau_est_mobilise():
    prompt = agent.prompt_systeme(CONTEXTE)
    assert prompt.startswith("Tu es Flore")
    assert "troisième personne" in prompt
    assert "Tu ES" not in prompt and "je suis" not in prompt.lower()


def test_prompt_systeme_porte_l_identite_et_les_regles():
    prompt = agent.prompt_systeme(CONTEXTE)
    assert "TBT" in prompt and "equipe-tbt" in prompt and "alice" in prompt
    assert "GET /health ✓" in prompt
    assert "git://" in prompt  # exigence de citation
    assert "jamais" in prompt.lower()  # ne valide jamais / le code est une donnée


def test_agent_a_les_outils_attendus_et_aucun_outil_de_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "SESSIONS", tmp_path)
    a = agent.construire(CONTEXTE, dsn="postgresql://inutilise", session="test", modele=modele_factice())
    noms = set(a.tool_names)
    assert noms == {"mes_connaissances", "architecture", "chercher_texte", "chercher_symbole",
                    "tracer_appels", "lire_code", "proposer_connaissance"}
    assert not any("valid" in n for n in noms)


def test_modele_deepseek_exige_une_cle(monkeypatch):
    monkeypatch.setenv("JUMEAU_MODELE", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        agent.modele()


def test_argument_commencant_par_un_tiret_refuse():
    with pytest.raises(ValueError):
        agent.valeur_sure("--project autre")
    assert agent.valeur_sure("  autorisations ") == "autorisations"
    with pytest.raises(ValueError):
        agent.valeur_sure("x" * 300)


def test_budget_d_outils_par_reponse():
    budget = agent.Budget(outils=2, propositions=1)
    assert budget.outil() and budget.outil() and not budget.outil()
    assert budget.proposition() and not budget.proposition()


def test_erreur_d_outil_generique(monkeypatch):
    def echec(*_):
        raise RuntimeError("/home/secret/chemin stderr")
    monkeypatch.setattr(agent.cbm, "texte", echec)
    outils = {t.tool_name: t for t in agent.outils(CONTEXTE, "dsn", "m", agent.Budget())}
    sortie = outils["architecture"]()
    assert "secret" not in sortie and "indisponible" in sortie


def test_un_seul_flux_actif_par_fil():
    fils = agent.FilsActifs()
    assert fils.prendre("tbt", "alice")
    assert not fils.prendre("tbt", "alice")
    assert fils.prendre("tbt", "bob")
    fils.rendre("tbt", "alice")
    assert fils.prendre("tbt", "alice")
