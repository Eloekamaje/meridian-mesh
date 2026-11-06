"""Tests du sidecar JCL : jobs, étapes, DD, procédures, couverture et robustesse."""
from meridian.adapters.outbound.connectors.jcl import JclSidecar


JCL = """\
//PAYJOB   JOB (ACCT),'PAYROLL',CLASS=A,MSGCLASS=X
//* commentaire de job
//STEP1    EXEC PGM=PAYPROG,COND=(0,NE)
//INFILE   DD DSN=PAY.INPUT.FILE,DISP=SHR
//OUTFILE  DD DSN=PAY.OUTPUT.FILE,
//            DISP=(NEW,CATLG,DELETE)
//SYSIN    DD *
//NOTJCL   EXEC PGM=GHOST
ligne de donnees
/*
//STEP2    EXEC PROC=PAYPROC
//MYPROC   PROC
//         SET ENV=PROD
//         INCLUDE MEMBER=COMMON
// IF (STEP1.RC = 0) THEN
//STEP3    EXEC PGM=CONDPGM
// ELSE
//STEP4    EXEC PGM=OTHERPGM
// ENDIF
// PEND
"""


def _par_kind(observations, kind, symbol=None):
    return [o for o in observations if o.kind == kind and (symbol is None or o.symbol == symbol)]


def _souches(observations):
    return {(o.kind, o.symbol) for o in observations}


def test_extraction_jcl_complete(tmp_path):
    (tmp_path / "pay.jcl").write_text(JCL, encoding="utf-8")
    observations = JclSidecar().index(tmp_path)

    job = _par_kind(observations, "jcl_job", "PAYJOB")[0]
    assert job.start == job.end == 1
    assert job.provider == "jcl"
    assert job.parser == "jcl-structural"
    assert job.parser_version == "1.0"
    assert job.language == "jcl"
    assert job.file == "pay.jcl"
    assert job.attributes == {"job": "PAYJOB"}

    etape = _par_kind(observations, "jcl_step", "STEP1")[0]
    assert etape.start == 3
    assert etape.attributes == {
        "step": "STEP1", "job": "PAYJOB", "pgm": "PAYPROG", "cond": "(0,NE)"}
    programme = _par_kind(observations, "jcl_program", "PAYPROG")[0]
    assert programme.attributes == {
        "pgm": "PAYPROG", "step": "STEP1", "job": "PAYJOB", "cond": "(0,NE)"}

    infile = _par_kind(observations, "jcl_dd", "INFILE")[0]
    assert infile.attributes == {
        "dd": "INFILE", "job": "PAYJOB", "step": "STEP1",
        "dsn": "PAY.INPUT.FILE", "disp": "SHR"}
    dataset = _par_kind(observations, "jcl_dataset", "PAY.INPUT.FILE")[0]
    assert dataset.attributes == {
        "dsn": "PAY.INPUT.FILE", "dd": "INFILE", "job": "PAYJOB",
        "step": "STEP1", "disp": "SHR"}

    outfile = _par_kind(observations, "jcl_dataset", "PAY.OUTPUT.FILE")[0]
    assert (outfile.start, outfile.end) == (5, 6)
    assert outfile.attributes["disp"] == "(NEW,CATLG,DELETE)"

    assert not _par_kind(observations, "jcl_step", "NOTJCL")
    assert not _par_kind(observations, "jcl_program", "GHOST")

    etape2 = _par_kind(observations, "jcl_step", "STEP2")[0]
    assert etape2.attributes == {"step": "STEP2", "job": "PAYJOB", "proc": "PAYPROC"}
    invocation = _par_kind(observations, "jcl_proc", "PAYPROC")[0]
    assert invocation.attributes == {"proc": "PAYPROC", "step": "STEP2", "job": "PAYJOB"}
    definition = _par_kind(observations, "jcl_proc", "MYPROC")[0]
    assert definition.attributes == {"proc": "MYPROC"}

    variable = _par_kind(observations, "jcl_set", "ENV")[0]
    assert variable.attributes == {"set": "ENV", "value": "PROD", "job": "PAYJOB"}
    inclusion = _par_kind(observations, "jcl_include", "COMMON")[0]
    assert inclusion.attributes == {
        "include": "COMMON", "member": "COMMON", "job": "PAYJOB"}

    step3 = _par_kind(observations, "jcl_step", "STEP3")[0]
    assert step3.attributes["if"] == "(STEP1.RC = 0)"
    assert step3.attributes["if_branch"] == "then"
    step4 = _par_kind(observations, "jcl_step", "STEP4")[0]
    assert step4.attributes["if"] == "(STEP1.RC = 0)"
    assert step4.attributes["if_branch"] == "else"
    assert not {"IF", "ELSE", "ENDIF"} & {o.symbol for o in observations}

    kinds = {o.kind for o in observations}
    assert kinds == {
        "jcl_job", "jcl_step", "jcl_program", "jcl_proc",
        "jcl_dataset", "jcl_dd", "jcl_set", "jcl_include",
    }


def test_continuation_ne_devient_pas_une_instruction(tmp_path):
    contenu = """\
//STEP1    EXEC PGM=FIRST,
//            PARM='UN'
//STEP2    EXEC PGM=SECOND
"""
    (tmp_path / "suite.jcl").write_text(contenu, encoding="utf-8")
    observations = JclSidecar().index(tmp_path)

    etapes = _par_kind(observations, "jcl_step")
    assert [o.symbol for o in etapes] == ["STEP1", "STEP2"]
    assert etapes[0].end == 2
    assert etapes[0].attributes["pgm"] == "FIRST"
    assert _par_kind(observations, "jcl_program", "SECOND")


def test_indicateur_colonne_72_continue_instruction(tmp_path):
    premiere = "//STEP1    EXEC PGM=LONG"
    premiere = premiere.ljust(71) + ","
    contenu = premiere + "\n//            PARM='X'\n"
    (tmp_path / "col72.jcl").write_text(contenu, encoding="utf-8")
    observations = JclSidecar().index(tmp_path)

    etapes = _par_kind(observations, "jcl_step")
    assert len(etapes) == 1
    assert etapes[0].symbol == "STEP1"
    assert etapes[0].end == 2


def test_decouverte_des_extensions_jcl(tmp_path):
    for nom in ("a.jcl", "b.job", "c.proc", "d.prc", "e.txt"):
        (tmp_path / nom).write_text("//JOB1 JOB (A),'X'\n", encoding="utf-8")
    observations = JclSidecar().index(tmp_path)

    assert {o.file for o in observations} == {"a.jcl", "b.job", "c.proc", "d.prc"}


def test_xml_non_concerne_et_couverture(tmp_path):
    (tmp_path / "pay.jcl").write_text(JCL, encoding="utf-8")
    (tmp_path / "config.xml").write_text("<root/>", encoding="utf-8")
    sidecar = JclSidecar()

    assert {o.file for o in sidecar.index(tmp_path)} == {"pay.jcl"}
    lignes = sidecar.couverture(tmp_path, fichiers=["config.xml"])
    assert len(lignes) == 1
    assert lignes[0].statut == "non_supporte"
    assert lignes[0].parser == "jcl-structural"
    assert lignes[0].language == ""


def test_couverture_indexe_partiel_ignore(tmp_path):
    (tmp_path / "ok.jcl").write_text(JCL, encoding="utf-8")
    (tmp_path / "vide.job").write_text("//* rien\n", encoding="utf-8")
    (tmp_path / "config.xml").write_text("<x/>", encoding="utf-8")
    sidecar = JclSidecar()

    lignes = sidecar.couverture(
        tmp_path, fichiers=["ok.jcl", "vide.job", "absent.jcl", "config.xml"])
    statuts = {ligne.file: ligne.statut for ligne in lignes}
    assert statuts == {
        "ok.jcl": "indexe", "vide.job": "partiel",
        "absent.jcl": "ignore", "config.xml": "non_supporte",
    }


def test_fichiers_explicites_limitent_l_indexation(tmp_path):
    (tmp_path / "a.jcl").write_text("//A JOB (X),'A'\n", encoding="utf-8")
    (tmp_path / "b.jcl").write_text("//B JOB (X),'B'\n", encoding="utf-8")

    observations = JclSidecar().index(tmp_path, fichiers=["b.jcl"])
    assert {o.file for o in observations} == {"b.jcl"}
    assert _par_kind(observations, "jcl_job", "B")


def test_encodage_cp1252_et_latin1_non_fatal(tmp_path):
    (tmp_path / "enc.jcl").write_bytes("//* café\n//JOB1 JOB (A),'X'\n".encode("cp1252"))
    (tmp_path / "raw.jcl").write_bytes(b"//* \x81\n//JOB2 JOB (A),'Y'\n")
    observations = JclSidecar().index(tmp_path)

    assert _par_kind(observations, "jcl_job", "JOB1")
    assert _par_kind(observations, "jcl_job", "JOB2")


def test_fichier_invalide_non_fatal(tmp_path):
    (tmp_path / "bin.jcl").write_bytes(b"\x00\x01\xff\xfe\x00")
    sidecar = JclSidecar()

    observations = sidecar.index(tmp_path)
    assert isinstance(observations, list)
    assert sidecar.index(tmp_path, fichiers=["absent.jcl"]) == []
    lignes = sidecar.couverture(tmp_path)
    assert lignes[0].statut in {"partiel", "indexe", "ignore"}
