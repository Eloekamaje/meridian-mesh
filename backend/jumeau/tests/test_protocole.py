"""Les événements internes de Flore, traduits en AG-UI (ag-ui-protocol 1.0) : un seul point de traduction."""
import json

from jumeau.protocole import Traducteur


def types(evts):
    return [e["type"] for e in evts]


def lus(t, *internes):
    return [json.loads(e.model_dump_json(by_alias=True, exclude_none=True)) for i in internes for e in t.traduire(i)]


def test_un_tour_complet_suit_l_ordre_ag_ui():
    t = Traducteur("t1", "r1")
    evts = [json.loads(e.model_dump_json(by_alias=True, exclude_none=True)) for e in t.debut()]
    evts += lus(t, {"type": "etape", "libelle": "Je regarde Conduit…"},
                {"type": "texte", "delta": "Bon"}, {"type": "texte", "delta": ""}, {"type": "texte", "delta": "jour"},
                {"type": "relecture"})
    evts += [json.loads(e.model_dump_json(by_alias=True, exclude_none=True)) for e in t.fin({"reponse": "Bonjour"})]
    assert types(evts) == ["RUN_STARTED", "STEP_STARTED", "TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT",
                           "TEXT_MESSAGE_CONTENT", "TEXT_MESSAGE_END", "CUSTOM", "STEP_FINISHED", "RUN_FINISHED"]
    assert evts[0]["threadId"] == "t1" and evts[0]["runId"] == "r1"
    assert evts[1]["stepName"] == evts[7]["stepName"] == "Je regarde Conduit…"
    assert evts[6]["name"] == "relecture" and evts[-1]["result"] == {"reponse": "Bonjour"}


def test_un_outil_debut_arguments_resultat():
    t = Traducteur("t", "r")
    evts = lus(t, {"type": "outil", "id": "u1", "nom": "lire_code", "libelle": "Je lis le code…", "etat": "en_cours"},
               {"type": "outil", "id": "u1", "arguments": {"chemin": "a.py"}},
               {"type": "outil", "id": "u1", "etat": "fait", "duree": 0.12, "extrait": "def f(): ..."})
    assert types(evts) == ["TOOL_CALL_START", "TOOL_CALL_ARGS", "TOOL_CALL_END", "TOOL_CALL_RESULT"]
    assert evts[0]["toolCallName"] == "lire_code" and evts[0]["metadata"] == {"libelle": "Je lis le code…"}
    assert json.loads(evts[1]["delta"]) == {"chemin": "a.py"}
    assert evts[3]["content"] == "def f(): ..." and evts[3]["metadata"] == {"etat": "fait", "duree": 0.12}


def test_un_resultat_sans_arguments_ferme_quand_meme_l_appel():
    t = Traducteur("t", "r")
    evts = lus(t, {"type": "outil", "id": "u1", "nom": "x", "etat": "en_cours"},
               {"type": "outil", "id": "u1", "etat": "erreur", "duree": 1.0, "extrait": ""})
    assert types(evts) == ["TOOL_CALL_START", "TOOL_CALL_END", "TOOL_CALL_RESULT"]


def test_erreur_et_evenement_inconnu():
    t = Traducteur("t", "r")
    assert lus(t, {"type": "inconnu", "x": 1}) == [{"type": "CUSTOM", "name": "inconnu", "value": {"type": "inconnu", "x": 1}}]
    assert [json.loads(e.model_dump_json(by_alias=True, exclude_none=True)) for e in t.erreur("Case introuvable")] == \
        [{"type": "RUN_ERROR", "message": "Case introuvable"}]


def test_l_outil_d_un_jumeau_porte_son_parent_et_la_mission_part_en_custom():
    t = Traducteur("t", "r")
    evts = lus(t, {"type": "outil", "id": "u1", "nom": "lire_code", "libelle": "Je lis…", "etat": "en_cours", "parent": "conduit"},
               {"type": "mission", "jumeau": "conduit", "etat": "fait", "confiance": "elevee", "preuves": 2, "constat": "c"})
    assert evts[0]["metadata"] == {"libelle": "Je lis…", "parent": "conduit"}
    assert evts[1]["type"] == "CUSTOM" and evts[1]["name"] == "mission" and evts[1]["value"]["jumeau"] == "conduit"
