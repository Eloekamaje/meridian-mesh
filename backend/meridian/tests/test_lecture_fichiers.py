"""Règles partagées de lecture : binaire, décodage et parcours."""
from __future__ import annotations

from meridian.adapters.outbound.connectors.decouverte_composants import lire_fichiers
from meridian.adapters.outbound.connectors.lecture_fichiers import (
    decoder_texte,
    est_binaire,
)


def test_est_binaire_refuse_nul_et_octets_de_controle():
    assert not est_binaire(b"")
    assert not est_binaire("café".encode())
    assert est_binaire(b"avant\x00apres")
    assert est_binaire(bytes(range(1, 32)) * 10)


def test_decoder_texte_respecte_le_repli_latin1():
    assert decoder_texte(b"caf\xe9") == "café"
    assert decoder_texte(b"caf\xe9", latin1=False) is None


def test_lire_fichiers_ignore_binaire_non_utf8_et_dossiers_techniques(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.java").write_text("class App {}\n", encoding="utf-8")
    (tmp_path / "src" / "latin1.java").write_bytes(b"class Caf\xe9 {}\n")
    (tmp_path / "src" / "controle.java").write_bytes(bytes(range(1, 32)) * 10)
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "ignore.js").write_text("fetch('/ignore')\n")

    fichiers, diagnostics = lire_fichiers(tmp_path)

    assert set(fichiers) == {"src/App.java"}
    assert any("latin1.java" in diagnostic and "UTF-8" in diagnostic
               for diagnostic in diagnostics)
    assert not any("controle.java" in diagnostic for diagnostic in diagnostics)
