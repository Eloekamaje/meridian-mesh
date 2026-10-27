"""Construction de l'agent du jumeau (sans appel au modèle)."""
import pytest

from jumeau import agent

CONTEXTE = {
    "jumeau": {"id": "tbt", "tenant_id": "banque", "nom": "TBT", "equipe": "equipe-tbt"},
    "source": {"id": 1, "nom": "tbt-repo", "emplacement": "/d", "curseur": "a" * 40,
               "copie": "/copies/tbt", "index_code": "proj-tbt"},
    "claims": [{"predicat": "EXPOSE", "objet": "GET /health", "statut": "ACCEPTED"}],
    "acteur": "alice",
    "profil": {"nom": "J. Morel", "role": "Équipe Support"},
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


def test_prompt_systeme_porte_l_identite_la_charte_et_l_interlocuteur():
    prompt = agent.prompt_systeme(CONTEXTE)
    assert "TBT" in prompt and "equipe-tbt" in prompt
    assert "J. Morel" in prompt and "Équipe Support" in prompt
    assert "GET /health ✓" in prompt
    assert agent.CHARTE.read_text(encoding="utf-8").strip()[:60] in prompt
    assert "#L" in prompt  # exigence de citation
    assert "jamais" in prompt.lower()


def test_la_charte_impose_le_vouvoiement_et_le_langage_metier():
    charte = agent.CHARTE.read_text(encoding="utf-8").lower()
    assert "vouvo" in charte and "jargon" in charte and "règles internes" in charte


def test_agent_a_les_outils_attendus_et_aucun_outil_de_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "SESSIONS", tmp_path)
    a = agent.construire(CONTEXTE, dsn="postgresql://inutilise", session="test", modele=modele_factice())
    noms = set(a.tool_names)
    assert noms == {"mes_connaissances", "architecture", "chercher_texte", "chercher_symbole",
                    "tracer_appels", "lire_code", "proposer_connaissance", "consulter_methode",
                    "historique_du_code", "ce_qui_a_change"}
    assert not any("valid" in n or "decid" in n for n in noms)


OUTILS_TRAVAIL = {"planifier", "lever_etape", "proposer_hypothese", "proposer_option", "deposer_livrable",
                  "actualiser_resume"}


def test_dans_un_travail_flore_recoit_les_outils_du_travail_et_son_etat(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "SESSIONS", tmp_path)
    ctx = {**CONTEXTE, "travail": "Travail : Retirer TBT\nPlan :\n  [ ] Qui appelle TBT ?"}
    a = agent.construire(ctx, dsn="postgresql://inutilise", session="t", modele=modele_factice(), ecriture=object())
    assert OUTILS_TRAVAIL <= set(a.tool_names)
    assert "Qui appelle TBT ?" in a.system_prompt and "État du Travail" in a.system_prompt


def test_hors_travail_pas_d_outils_d_ecriture(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "SESSIONS", tmp_path)
    a = agent.construire(CONTEXTE, dsn="postgresql://inutilise", session="t", modele=modele_factice())
    assert not OUTILS_TRAVAIL & set(a.tool_names)


def test_modele_deepseek_exige_une_cle(monkeypatch):
    monkeypatch.setenv("JUMEAU_MODELE", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        agent.modele()


def test_valeur_bornee_et_non_vide():
    # Par MCP, les arguments sont des champs JSON : un texte commençant par « - » n'est plus une option.
    assert agent.valeur_sure("  --project autre ") == "--project autre"
    for mauvaise in ("x" * 300, "   "):
        with pytest.raises(ValueError):
            agent.valeur_sure(mauvaise)


def test_les_outils_de_code_passent_par_mcp_avec_le_projet_du_jumeau(monkeypatch):
    appels = []
    monkeypatch.setattr(agent.cbm, "appeler", lambda outil, **args: appels.append((outil, args)) or "ok")
    outils = {t.tool_name: t for t in agent.outils(CONTEXTE, "dsn", "m", agent.Budget())}
    outils["chercher_texte"](texte="autorisations")
    outils["tracer_appels"](fonction="autorisations", sens="inbound")
    assert appels == [("search_code", {"project": "proj-tbt", "pattern": "autorisations", "limit": 10}),
                      ("trace_path", {"project": "proj-tbt", "function_name": "autorisations",
                                      "direction": "inbound", "depth": 2})]


def test_fils_sur_s3_quand_un_compartiment_est_configure(monkeypatch, tmp_path):
    cree = {}

    class S3Factice:
        def __init__(self, **kwargs):
            cree.update(kwargs)
    monkeypatch.setattr(agent, "S3SessionManager", S3Factice)
    monkeypatch.setenv("JUMEAU_SESSIONS_S3", "meridian-fils/flore")
    agent.gestionnaire_session("fil-1")
    assert (cree["session_id"], cree["bucket"], cree["prefix"]) == ("fil-1", "meridian-fils", "flore")
    monkeypatch.delenv("JUMEAU_SESSIONS_S3")
    monkeypatch.setattr(agent, "SESSIONS", tmp_path)
    assert type(agent.gestionnaire_session("fil-1")).__name__ == "FileSessionManager"


def test_budget_d_outils_par_reponse():
    budget = agent.Budget(outils=2, propositions=1)
    assert budget.outil() and budget.outil() and not budget.outil()
    assert budget.proposition() and not budget.proposition()


def test_l_exploration_n_epuise_jamais_le_budget_d_ecriture_du_travail():
    budget = agent.Budget(outils=1, ecritures=2)
    assert budget.outil() and not budget.outil()
    assert budget.ecriture() and budget.ecriture() and not budget.ecriture()


def test_erreur_d_outil_generique(monkeypatch):
    def echec(*_, **__):
        raise RuntimeError("/home/secret/chemin stderr")
    monkeypatch.setattr(agent.cbm, "appeler", echec)
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
