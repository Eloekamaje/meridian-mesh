"""Lot 0 du plan de remédiation : une étiquette ne promet jamais plus que ce que le mécanisme a fait.

Chaque test de ce fichier échouait avant la correction : `relu` était posé en dur, `corrige` valait « il y a eu une
objection » et non « le texte a changé », une panne du relecteur passait pour une relecture, les réponses de
démonstration portaient des indicateurs inventés, et aucune latence de premier mot n'était mesurée.
"""
import asyncio
import json

from jumeau import contradicteur, flux, mesure, origine
from jumeau import flore
from jumeau.flore import etat_relecture, relire_sans_risque, reviser


# --- L0.1 : l'état de relecture dit ce qui s'est réellement passé -------------------------------------------------

def test_relu_seulement_quand_la_relecture_a_eu_lieu():
    assert etat_relecture({"ok": True, "etat": "relue"}, corrige=False) == "relue"
    assert etat_relecture({"ok": True, "etat": "indisponible"}, corrige=False) == "indisponible"
    assert etat_relecture({"ok": True, "etat": "verdict_illisible"}, corrige=False) == "verdict_illisible"


def test_une_relecture_qui_a_echoue_ne_s_affiche_pas_comme_une_relecture():
    async def scenario():
        import jumeau.flore as flore

        async def en_panne(*a, **k):
            raise RuntimeError("quota dépassé")

        vrai = flore.contradicteur.relire
        flore.contradicteur.relire = en_panne
        try:
            verdict = await relire_sans_risque("q", "texte", [], None, None)
        finally:
            flore.contradicteur.relire = vrai
        return verdict

    verdict = asyncio.run(scenario())
    assert verdict["etat"] == "indisponible"
    assert etat_relecture(verdict, corrige=False) == "indisponible"


def test_un_verdict_illisible_n_est_pas_une_approbation():
    verdict = contradicteur.analyser_verdict("je ne sais pas trop, mais ça me paraît bien")
    assert verdict["etat"] == "verdict_illisible"
    assert etat_relecture(verdict, corrige=False) == "verdict_illisible"
    assert contradicteur.analyser_verdict('{"ok": true, "problemes": []}')["etat"] == "relue"


# --- L0.2 : « corrigé » veut dire que le texte a changé ------------------------------------------------------------

class FauxAgent:
    def __init__(self, reponse=None, leve=False):
        self.reponse, self.leve, self.appels = reponse, leve, 0

    async def invoke_async(self, _):
        self.appels += 1
        if self.leve:
            raise RuntimeError("révision impossible")
        return self.reponse


def reviser_avec(verdict, agent):
    async def scenario():
        return await reviser(agent, "première réponse", verdict, mesure.Chrono(), None, "test")

    return asyncio.run(scenario())


def test_pas_de_revision_sans_objection():
    agent = FauxAgent(reponse="autre chose")
    assert reviser_avec({"ok": True, "etat": "relue"}, agent) == ("première réponse", False)
    assert agent.appels == 0


def test_une_revision_qui_echoue_n_est_pas_une_correction():
    texte, corrige = reviser_avec({"ok": False, "problemes": ["citation fausse"]}, FauxAgent(leve=True))
    assert texte == "première réponse" and corrige is False
    assert etat_relecture({"ok": False, "etat": "relue"}, corrige) == "objection_sans_effet"


def test_une_revision_sans_effet_n_est_pas_une_correction():
    texte, corrige = reviser_avec({"ok": False, "problemes": ["x"]}, FauxAgent(reponse="première réponse"))
    assert texte == "première réponse" and corrige is False


def test_une_correction_reelle_est_dite_corrigee_mais_non_relue():
    texte, corrige = reviser_avec({"ok": False, "problemes": ["x"]}, FauxAgent(reponse="réponse corrigée"))
    assert texte == "réponse corrigée" and corrige is True
    # Une correction n'est jamais relue : une seule révision au plus.
    assert etat_relecture({"ok": False, "etat": "relue"}, corrige) == "corrigee_non_relue"


# --- L0.5 : une réponse écrite d'avance se déclare --------------------------------------------------------------

def test_une_reponse_de_demonstration_se_declare_et_ne_montre_pas_de_chiffres_inventes():
    script = {"reponse": "…", "indicateurs": {"confiance": 84, "couverture": 76}}
    sortie = origine.marquer_origine(dict(script), "scenario")
    assert sortie["origine"] == "scenario"
    assert "indicateurs" not in sortie


def test_un_chiffre_ecrit_d_avance_ne_s_affiche_pour_aucun_chemin_scripte():
    for origine_ in ("registre", "recherche", "repli", "refus", "scenario"):
        sortie = origine.marquer_origine({"reponse": "…", "indicateurs": {"confiance": 80}}, origine_)
        assert "indicateurs" not in sortie, origine_


def test_une_reponse_calculee_ne_perd_pas_ses_indicateurs():
    calculee = {"reponse": "…", "indicateurs": {"confiance": 84}}
    assert origine.marquer_origine(calculee, "modele")["indicateurs"] == {"confiance": 84}


# --- L0.6 : la latence du premier mot est mesurée ----------------------------------------------------------------

def test_le_premier_texte_est_horodate_dans_les_durees():
    async def produire(emit):
        await emit({"type": "etape", "libelle": "Je regarde…"})
        await emit({"type": "texte", "delta": "Bon"})
        await emit({"type": "texte", "delta": "jour"})
        return {"reponse": "Bonjour", "durees": {"total": 0.0}}

    async def lire():
        reponse = flux.en_flux(produire)
        evenements = []
        async for morceau in reponse.body_iterator:
            evenements.append(json.loads(morceau[len("data: "):]))
        return evenements

    evenements = asyncio.run(lire())
    final = [e for e in evenements if e["type"] == "RUN_FINISHED"][0]["result"]
    assert "premier_texte" in final["durees"]
    assert final["durees"]["premier_texte"] >= 0


# --- L1.7 : le juge ne partage pas le modèle de l'auteur quand on le lui dit -----------------------------

def test_le_juge_prend_son_propre_modele(monkeypatch):
    from jumeau import agent as agent_mod

    vus = []

    class Faux:
        def __init__(self, model_id):
            self.model_id = model_id

    monkeypatch.setenv("JUMEAU_MODELE", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "cle")
    monkeypatch.delenv("JUMEAU_MODELE_JUGE", raising=False)
    monkeypatch.setattr("strands.models.openai.OpenAIModel", lambda client_args, model_id, **_: Faux(model_id))
    assert agent_mod.modele_juge().model_id == "deepseek-chat"          # à défaut : même modèle, dit ici
    monkeypatch.setenv("JUMEAU_MODELE_JUGE", "autre-famille")
    assert agent_mod.modele_juge().model_id == "autre-famille"          # séparé : l'auteur garde le sien
    assert agent_mod.modele().model_id == "deepseek-chat"
    vus.append(True)


# --- L2.4 : le premier mot est une mesure, pas une phrase de document --------------------------------------------------

def test_le_chronometre_releve_l_instant_du_premier_mot():
    chrono = mesure.Chrono()
    assert "premier_texte" not in chrono.bilan()
    chrono.texte()
    premier = chrono.bilan()["premier_texte"]
    assert premier >= 0
    chrono.texte()  # une seule fois : le second mot n'écrase pas la mesure
    assert chrono.bilan()["premier_texte"] == premier


def test_executer_horodate_le_premier_texte_du_flux():
    class AgentFlux:
        async def stream_async(self, _):
            await asyncio.sleep(0.02)
            for morceau in ("Bon", "jour"):
                yield {"data": morceau}
            yield {"result": "Bonjour"}

    chrono = mesure.Chrono()
    morceaux = []

    async def emit(e):
        morceaux.append(e)

    texte = asyncio.run(flore.executer(AgentFlux(), "q", emit, chrono))
    assert texte == "Bonjour"
    assert [m["delta"] for m in morceaux] == ["Bon", "jour"]
    assert chrono.bilan()["premier_texte"] >= 0.02


def test_executer_emet_chaque_outil_debut_arguments_resultat():
    """Ce que Flore a vraiment fait, outil par outil (P2, option A) : début, arguments complets, issue et durée."""
    class AgentOutils:
        async def stream_async(self, _):
            for partiel in ('{"che', '{"chemin": "a.py"}'):  # Strands répète l'appel pendant que ses arguments arrivent
                yield {"current_tool_use": {"toolUseId": "u1", "name": "lire_code", "input": partiel}}
            yield {"message": {"role": "assistant", "content": [
                {"text": "Je lis."}, {"toolUse": {"toolUseId": "u1", "name": "lire_code", "input": {"chemin": "a.py"}}}]}}
            yield {"message": {"role": "user", "content": [
                {"toolResult": {"toolUseId": "u1", "status": "success", "content": [{"text": "def f():\n" + "x" * 900}]}}]}}
            yield {"current_tool_use": {"toolUseId": "u2", "name": "inconnu", "input": {}}}
            yield {"message": {"role": "user", "content": [
                {"toolResult": {"toolUseId": "u2", "status": "error", "content": [{"text": "refus"}]}}]}}
            yield {"result": "fini"}

    evts = []

    async def emit(e):
        evts.append(e)

    assert asyncio.run(flore.executer(AgentOutils(), "q", emit, mesure.Chrono())) == "fini"
    u1 = [e for e in evts if e.get("id") == "u1"]
    assert u1[0] == {"type": "outil", "id": "u1", "nom": "lire_code", "libelle": flore.ETAPES["lire_code"], "etat": "en_cours"}
    assert u1[1] == {"type": "outil", "id": "u1", "arguments": {"chemin": "a.py"}}
    assert u1[2]["etat"] == "fait" and u1[2]["duree"] >= 0 and len(u1[2]["extrait"]) <= flore.EXTRAIT_OUTIL + 1
    assert len(u1) == 3  # annoncé une seule fois malgré les répétitions
    u2 = [e for e in evts if e.get("id") == "u2"]
    assert u2[0]["libelle"] is None and u2[-1]["etat"] == "erreur" and u2[-1]["extrait"] == "refus"
