"""Primitives de layout : grille, tracés orthogonaux, croisements, labels, zones."""
from meridian.application import diagram_layout as layout


def _attribut(svg: str, balise: str, nom: str) -> float:
    import re
    match = re.search(rf'<{balise}\b[^>]*\b{nom}="(-?[0-9.]+)"', svg)
    assert match, f"{nom} absent de {svg}"
    return float(match.group(1))


def test_snap_aligne_sur_la_grille_de_4_px():
    assert layout.snap(0) == 0
    assert layout.snap(9) == 8
    assert layout.snap(15) == 16
    assert layout.snap(100) == 100


def test_simplifier_retire_doublons_et_points_alignes():
    points = [(0, 0), (8, 0), (16, 0), (16, 0), (16, 12)]
    assert layout.simplifier(points) == [(0.0, 0.0), (16.0, 0.0), (16.0, 12.0)]


def test_un_trace_orthogonal_a_des_coudes_arrondis():
    d = layout.traces([(0, 0), (40, 0), (40, 40)])[0]
    assert d.startswith("M 0.0 0.0")
    assert "L 32.0 0.0" in d
    assert "Q 40.0 0.0 40.0 8.0" in d
    assert d.endswith("L 40.0 40.0")
    assert " L 40.0 0.0 L" not in d


def test_un_croisement_produit_un_gap_et_deux_sous_traces():
    croises = layout.croisements([[(0, 0), (100, 0)], [(50, -50), (50, 50)]])
    assert croises == [(0, 1, 50.0, 0.0)]

    morceaux = layout.traces([(50, -50), (50, 50)], gaps=[(50, 0)])
    assert len(morceaux) == 2
    assert morceaux[0].endswith("L 50.0 -5.0")
    assert morceaux[1].startswith("M 50.0 5.0")


def test_pas_de_gap_sans_croisement_interieur():
    assert layout.croisements([[(0, 0), (100, 0)], [(0, 0), (0, 50)]]) == []
    assert len(layout.traces([(0, 0), (100, 0)])) == 1


def test_un_label_horizontal_est_masque_au_dessus_de_la_ligne():
    svg = layout.label(50, 100, "écrit", color="#94A3B8", background="#071019")
    y = _attribut(svg, "rect", "y")
    hauteur = _attribut(svg, "rect", "height")
    assert y + hauteur <= 100 - layout.LABEL_GAP
    assert 'text-anchor="middle"' in svg


def test_un_label_vertical_laisse_un_ecart_a_droite():
    svg = layout.label(50, 100, "écrit", color="#94A3B8", background="#071019", side="right")
    x = _attribut(svg, "text", "x")
    assert x >= 50 + layout.LABEL_GAP


def test_un_label_a_gauche_laisse_un_ecart():
    svg = layout.label(100, 100, "écrit", color="#94A3B8", background="#071019", side="left")
    assert 'text-anchor="end"' in svg
    x = _attribut(svg, "text", "x")
    assert x <= 100 - layout.LABEL_GAP


def test_un_label_long_passe_sur_deux_lignes_au_lieu_d_etre_tronque():
    svg = layout.label(50, 100, "un libellé vraiment trop long", color="#94A3B8",
                       background="#071019", max_width=80)
    assert svg.count("<tspan") == 2
    hauteur = _attribut(svg, "rect", "height")
    assert hauteur > layout.MASK_HEIGHT
    assert _attribut(svg, "rect", "y") + hauteur <= 100 - layout.LABEL_GAP


def test_label_trace_choisit_le_plus_long_segment():
    horizontal = layout.meilleur_segment([(0, 0), (100, 0), (100, 40)])
    assert horizontal == ((0.0, 0.0), (100.0, 0.0))
    svg = layout.label_trace([(0, 0), (100, 0), (100, 40)], "écrit",
                             color="#94A3B8", background="#071019")
    assert 'text-anchor="middle"' in svg


def test_englobante_ajoute_la_marge_et_aligne():
    rects = [{"x": 40, "y": 60, "largeur": 120, "hauteur": 40},
             {"x": 220, "y": 100, "largeur": 120, "hauteur": 40}]
    assert layout.englobante(rects, padding=16) == (24, 44, 332, 112)


def test_une_zone_porte_sa_regle_et_son_libelle():
    svg = layout.zone(40, 60, 200, 120, "Entrée", rule="#fff", fill="none", muted="#999")
    assert 'data-zone="1"' in svg
    assert 'stroke-dasharray="4 4"' in svg
    assert "Entrée" in svg


def test_la_legende_reference_les_marqueurs_par_etat():
    items = [("vérifié par le code", "code", "#60A5FA", None),
             ("proposé", "propose", "#F2B84B", "3 3")]
    svg = layout.legende(items, 24, 600, 900, rule="#fff", muted="#999", ink="#eee")
    assert "LÉGENDE" in svg
    assert "url(#fleche-code)" in svg
    assert "url(#fleche-propose)" in svg
    assert "url(#fleche-vérifié" not in svg
    assert 'stroke-dasharray="3 3"' in svg


def test_les_marqueurs_couvrent_tous_les_etats():
    etats = {"code": ("#60A5FA", 1.5, None), "propose": ("#F2B84B", 1.5, "3 3")}
    svg = layout.markers(etats)
    assert 'id="fleche-code"' in svg
    assert 'id="fleche-propose"' in svg
