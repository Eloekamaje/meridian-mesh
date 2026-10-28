"""Règle des prédicats métier prouvés par du code (plan L1bis.2, Sources v1 §2) : APPLIQUE_REGLE et DETIENT passent
M2 si une recette de FORME constate une décision (resp. une déclaration de donnée) dans les lignes citées ET si le
juge les dit appuyées. La forme seule ne suffit pas, le juge seul non plus."""
import asyncio
import subprocess

import pytest

from jumeau import connaissance, depot, recettes, recoupement
from jumeau.juge import Appui
from jumeau.tests.conftest import JUMEAU, besoin_pg

OK, ABSENTE = "ok", "absente"


@pytest.mark.parametrize("ligne", [
    "if solde < 0:", "elif x:", "match cmd:", "case 1:", "y = a if b else c", "raise ValueError('x')",
    "raise HTTPException(status_code=403)", "abort(403)", "throw new Error(x)", "return JSONResponse(s, 422)",
    "assert user.admin", "@validator('montant')", "@field_validator('montant')", "montant: int = Field(gt=0)",
    "CHECK (montant > 0)", "if (x) {", "const a = ok ? 1 : 2;",
])
def test_applique_regle_reconnait_une_decision(ligne):
    assert recettes.forme("APPLIQUE_REGLE", [ligne]) == OK


@pytest.mark.parametrize("lignes", [
    ["x = 1"], ["# if solde < 0: raise"], ["// if (x) throw"], ['msg = "if admin then raise"'],
    ["'''", "if x: raise", "'''"], ["/* if (x) { throw } */"], [], [""], ["return 200"], ["notify = verify(x)"],
])
def test_applique_regle_ignore_chaines_commentaires_et_absence(lignes):
    assert recettes.forme("APPLIQUE_REGLE", lignes) == ABSENTE


@pytest.mark.parametrize("ligne", [
    "class Compte(Base):", "class Compte(BaseModel):", "class Compte(models.Model):", "@dataclass",
    "CREATE TABLE compte (id int);", "id = sa.Column(sa.Integer)", "id = Column(Integer)",
    "nom = models.CharField(max_length=3)", "interface Compte {", "export type Compte = {",
    "op.create_table('compte')", "ALTER TABLE compte ADD COLUMN x int;",
])
def test_detient_reconnait_une_declaration_de_donnee(ligne):
    assert recettes.forme("DETIENT", [ligne]) == OK


@pytest.mark.parametrize("lignes", [
    ["x = 1"], ["# class Compte(Base):"], ['doc = "CREATE TABLE compte"'], ["if x: raise"], ["def f(): pass"], [],
])
def test_detient_ignore_chaines_commentaires_et_absence(lignes):
    assert recettes.forme("DETIENT", lignes) == ABSENTE


def test_forme_ne_porte_que_sur_deux_predicats():
    for p in ("SERT_ACTEUR", "REALISE_CAPACITE", "ECHANGE_AVEC", "RISQUE", "DEPEND_DE"):
        assert recettes.forme(p, ["if x: raise"]) is None


def test_la_forme_ne_decide_rien_sans_le_juge():
    f = connaissance.etabli_par_la_forme
    assert f("APPLIQUE_REGLE", OK, "selon") and f("detient", OK, "recoupe")
    assert not f("APPLIQUE_REGLE", OK, "en_partie") and not f("APPLIQUE_REGLE", OK, "non_appuye")
    assert not f("APPLIQUE_REGLE", ABSENTE, "selon") and not f("APPLIQUE_REGLE", None, "selon")
    assert not f("SERT_ACTEUR", OK, "selon") and not f("REALISE_CAPACITE", OK, "selon")


@besoin_pg
def test_sql_et_python_disent_la_meme_chose_sur_la_forme(conn):
    for p in ["APPLIQUE_REGLE", "DETIENT", "SERT_ACTEUR", "REALISE_CAPACITE", "ECHANGE_AVEC", "DEPEND_DE", "", None]:
        for forme in (OK, ABSENTE, None):
            for etat in ("selon", "recoupe", "en_partie", "non_appuye", "conteste", "verifie", "en_attente"):
                attendu = connaissance.etabli_par_la_forme(p, forme, etat)
                assert conn.execute("SELECT etabli_par_la_forme(%s, %s, %s)", (p, forme, etat)).fetchone()[0] is attendu


FICHIERS = {"regle.py": "x = 1\nif solde < 0:\n    raise ValueError('x')\n# if commentaire\n",
            "modele.py": "class Compte(Base):\n    id = Column(Integer)\n"}


def _depot(tmp_path):
    def git(*a):
        subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)
    git("init", "-q")
    for nom, texte in FICHIERS.items():
        (tmp_path / nom).write_text(texte)
    git("add", ".")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    return subprocess.run(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def _passe(conn, tmp_path, predicat, chemin, debut, fin, verdict):
    sha = _depot(tmp_path)
    depot.creer_jumeau(conn, JUMEAU)
    j = depot.jumeau_par_id(conn, "tbt")
    depot.declarer_source(conn, j, {"type": "GIT", "nom": "tbt", "emplacement": str(tmp_path), "curseur": sha})
    sid = depot.toutes_les_sources(conn, "tbt")[0]["id"]
    p = {"locator": f"git://tbt@{sha[:12]}:{chemin}#L{debut}-L{fin}", "chemin": chemin, "sha": sha,
         "ligne_debut": debut, "ligne_fin": fin, "hash": "h"}
    cid = depot.enregistrer_proposition(conn, j, sid, {"sujet": "TBT", "predicat": predicat, "objet": "le solde",
                                                       "type": "T", "confiance": 0.5}, p, {"extracteur": "test"})

    async def juger(modele, dossiers):
        return {d["id"]: Appui(id=d["id"], appui=verdict, concordance="une_seule_source", copie=False, raison="r")
                for d in dossiers}

    asyncio.run(recoupement.verifier(conn, j, juger=juger))
    maturite = conn.execute("SELECT maturite FROM claim WHERE id = %s", (cid,)).fetchone()[0]
    return maturite, recoupement.etats(conn, "tbt")[cid]


CAS = [  # predicat, chemin, lignes, juge -> maturité attendue, forme enregistrée
    ("APPLIQUE_REGLE", "regle.py", (2, 3), "oui", "M2", OK),
    ("APPLIQUE_REGLE", "regle.py", (2, 3), "partiel", "M1", OK),
    ("APPLIQUE_REGLE", "regle.py", (1, 1), "oui", "M1", ABSENTE),
    ("APPLIQUE_REGLE", "regle.py", (4, 4), "oui", "M1", ABSENTE),
    ("DETIENT", "modele.py", (1, 2), "oui", "M2", OK),
    ("DETIENT", "modele.py", (1, 2), "partiel", "M1", OK),
    ("DETIENT", "regle.py", (1, 1), "oui", "M1", ABSENTE),
    ("SERT_ACTEUR", "regle.py", (2, 3), "oui", "M1", None),
    ("REALISE_CAPACITE", "modele.py", (1, 2), "oui", "M1", None),
]


@besoin_pg
@pytest.mark.parametrize("predicat, chemin, lignes, verdict, maturite, forme", CAS)
def test_la_maturite_demande_la_forme_et_le_juge(conn, tmp_path, predicat, chemin, lignes, verdict, maturite, forme):
    obtenue, etat = _passe(conn, tmp_path, predicat, chemin, *lignes, verdict)
    assert obtenue == maturite and etat["forme"] == forme
    if forme == ABSENTE:
        assert "forme" in etat["raison"]  # l'état de vérification dit pourquoi M1
