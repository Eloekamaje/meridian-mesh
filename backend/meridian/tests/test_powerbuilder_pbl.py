"""Extraction binaire PBL : échantillon public, troncature, Unicode et couverture.

L'échantillon ``wiz_setup.pbl`` provient de
https://github.com/gmai2006/powerbuilder-pbl-dump (test/pbl_files), publié
sous licence MIT (Copyright (c) 2020 gmai2006). Il est versionné dans le
dépôt : les tests ne font aucun appel réseau.
"""
from __future__ import annotations

import shutil
import struct
from pathlib import Path

from meridian.adapters.outbound.connectors.powerbuilder import (
    PowerBuilderSidecar,
    extraire_pbl,
)

FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures" / "legacy_corpus" / "pbl" / "wiz_setup.pbl"
)
SOURCES = {
    ".sra", ".srd", ".srf", ".srj", ".srm", ".srp", ".srq", ".srs",
    ".sru", ".srw", ".srx",
}


def _pbl_unicode(texte: str, nom: str = "w_uni.srw",
                 commentaire: str = "créé") -> bytes:
    """Construit une bibliothèque Unicode minimale (en-tête 1024, NOD* 3072)."""
    commentaire_brut = commentaire.encode("utf-16le")
    contenu = commentaire_brut + texte.encode("utf-16le")
    morceaux = []
    offsets = []
    reste = contenu
    position = 4608
    while reste:
        morceaux.append(reste[:502])
        offsets.append(position)
        reste = reste[502:]
        position += 512

    donnees = bytearray(4608 + 512 * len(morceaux))
    donnees[0:4] = b"HDR*"
    donnees[4:30] = "PowerBuilder\x00".encode("utf-16le")
    donnees[32:36] = "06".encode("utf-16le")
    donnees[36:40] = "00".encode("utf-16le")
    donnees[44:46] = b"\x01\x00"
    donnees[1024:1028] = b"FRE*"

    nom_brut = (nom + "\x00").encode("utf-16le")
    entree = (
        b"ENT*" + "0600".encode("utf-16le")
        + struct.pack("<II", 4608, len(contenu))
        + struct.pack("<I", 0)
        + struct.pack("<HH", len(commentaire), len(nom_brut))
        + nom_brut
    )
    nod = bytearray(3072)
    nod[0:4] = b"NOD*"
    struct.pack_into("<III", nod, 4, 0, 0, 0)
    struct.pack_into("<HHHH", nod, 16, 3040 - len(entree), 32, 1, 32)
    nod[32:32 + len(entree)] = entree
    donnees[1536:4608] = nod

    for offset, morceau in zip(offsets, morceaux):
        bloc = bytearray(512)
        bloc[0:4] = b"DAT*"
        suivant = offset + 512 if offset + 512 < 4608 + 512 * len(morceaux) else 0
        struct.pack_into("<I", bloc, 4, suivant)
        struct.pack_into("<H", bloc, 8, len(morceau))
        bloc[10:10 + len(morceau)] = morceau
        donnees[offset:offset + 512] = bloc
    return bytes(donnees)


def test_extraction_reelle_de_l_echantillon():
    objets = extraire_pbl(FIXTURE)

    assert len(objets) == 3
    assert {objet["nom"] for objet in objets} == {
        "step1_seasons.sru", "step1_seasons_obj.sru", "wiz_setup.srw"}
    assert all(objet["extension"] in SOURCES for objet in objets)
    assert all(objet["texte"].strip() for objet in objets)
    assert not any(objet.get("erreur") for objet in objets)

    fenetre = next(objet for objet in objets if objet["nom"] == "wiz_setup.srw")
    assert fenetre["extension"] == ".srw"
    assert fenetre["objet"] == "wiz_setup"
    assert fenetre["commentaire"] == "Setup wizard"
    assert "Setup wizard" not in fenetre["texte"]
    assert "global type wiz_setup from w_wizmain" in fenetre["texte"]
    assert fenetre["octets"] == 1587
    assert fenetre["unicode"] is False
    assert fenetre["offsets"] == [22528, 23040, 23552, 24064]


def test_pbl_corrompu_retourne_une_erreur_structuree(tmp_path):
    corrompu = tmp_path / "corrompu.pbl"
    corrompu.write_bytes(b"\x00\x01PB\xff\xfe\x00legacy")

    objets = extraire_pbl(corrompu)

    assert len(objets) == 1
    assert objets[0]["erreur"]
    assert objets[0]["fatal"] is True
    assert objets[0]["texte"] == ""
    assert objets[0]["nom"] == "corrompu.pbl"


def test_fichier_absent_non_fatal(tmp_path):
    objets = extraire_pbl(tmp_path / "absent.pbl")

    assert len(objets) == 1
    assert "lecture impossible" in objets[0]["erreur"]
    assert objets[0]["fatal"] is True


def test_pbl_tronque_est_partiel_et_non_fatal(tmp_path):
    tronque = tmp_path / "tronque.pbl"
    tronque.write_bytes(FIXTURE.read_bytes()[:22560])

    objets = extraire_pbl(tronque)

    assert {objet["nom"] for objet in objets} >= {
        "step1_seasons.sru", "step1_seasons_obj.sru"}
    assert all(objet["texte"].strip() for objet in objets if not objet.get("erreur"))
    erreurs = [objet for objet in objets if objet.get("erreur")]
    assert erreurs
    assert all(objet["fatal"] is False for objet in erreurs)

    lignes = {ligne.file: ligne for ligne in PowerBuilderSidecar().couverture(
        tmp_path, fichiers=["tronque.pbl"])}
    assert lignes["tronque.pbl"].statut == "partiel"
    assert "extraction partielle" in lignes["tronque.pbl"].raison


def test_index_pbl_prefixe_les_fichiers_et_analyse_les_sources(tmp_path):
    shutil.copyfile(FIXTURE, tmp_path / "wiz_setup.pbl")
    sidecar = PowerBuilderSidecar()

    observations = sidecar.index(tmp_path)

    fichiers = {observation.file for observation in observations}
    assert fichiers == {
        "pbl://wiz_setup.pbl/step1_seasons.sru",
        "pbl://wiz_setup.pbl/step1_seasons_obj.sru",
        "pbl://wiz_setup.pbl/wiz_setup.srw",
    }
    objet = next(observation for observation in observations
                 if observation.file.endswith("/wiz_setup.srw")
                 and observation.kind == "pb_object")
    assert objet.symbol == "wiz_setup"
    assert objet.parser == "powerbuilder-structural"
    assert objet.language == "powerbuilder"
    assert not any("step1_seasons.udo" in fichier for fichier in fichiers)

    lignes = {ligne.file: ligne for ligne in sidecar.couverture(tmp_path)}
    assert lignes["wiz_setup.pbl"].statut == "indexe"
    assert lignes["wiz_setup.pbl"].language == "powerbuilder"
    assert lignes["wiz_setup.pbl"].parser == "powerbuilder-structural"


def test_pbl_unicode_extrait_le_texte(tmp_path):
    texte = "global type w_uni from window\nend type\n"
    chemin = tmp_path / "unicode.pbl"
    chemin.write_bytes(_pbl_unicode(texte))

    objets = extraire_pbl(chemin)

    assert len(objets) == 1
    objet = objets[0]
    assert objet["nom"] == "w_uni.srw"
    assert objet["unicode"] is True
    assert objet["commentaire"] == "créé"
    assert objet["texte"] == texte
    assert not objet.get("erreur")

    observations = PowerBuilderSidecar().index(tmp_path, fichiers=["unicode.pbl"])
    assert {observation.file for observation in observations} == {
        "pbl://unicode.pbl/w_uni.srw"}
    assert any(observation.kind == "pb_object" and observation.symbol == "w_uni"
               for observation in observations)


def test_srd_datawindow_est_une_source_texte_indexable(tmp_path):
    (tmp_path / "d_dates.srd").write_text(
        "HA$PBExportHeader$d_dates.srd\n"
        "$PBExportComments$\n"
        "release 9;\n"
        'table(column=(type=date updatewhereclause=yes name=datefrom '
        'dbname="datefrom" ))\n',
        encoding="utf-8")

    sidecar = PowerBuilderSidecar()
    lignes = {ligne.file: ligne for ligne in sidecar.couverture(
        tmp_path, fichiers=["d_dates.srd"])}
    assert lignes["d_dates.srd"].statut == "indexe"
    assert lignes["d_dates.srd"].language == "powerbuilder"
