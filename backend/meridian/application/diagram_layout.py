"""Primitives de layout déterministe pour les schémas Méridian.

Le compilateur `diagrammes.py` ne décide pas du sens : il reçoit une structure déjà vérifiée
(`boites`, `fleches`, `groupes`) et applique des règles de géométrie reproductibles :

- grille de 4 px ;
- connecteurs orthogonaux à coudes arrondis ;
- gaps aux croisements (bridge) ;
- labels masqués avec un espace visible au-dessus de la ligne ;
- zones et légende hors du dessin.
"""
from __future__ import annotations

import html
import math
from collections.abc import Iterable, Mapping, Sequence

GRID = 4
RADIUS = 8
LABEL_GAP = 8
MASK_HEIGHT = 14
HOP_GAP = 10


def snap(value) -> int:
    """Aligne une coordonnée structurelle sur la grille de 4 px."""
    return int(round(float(value) / GRID) * GRID)


def orthogonaux(points: Sequence[tuple[float, float]]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Segments d'un tracé orthogonal."""
    return list(zip(points, points[1:]))


def _est_horizontal(a, b) -> bool:
    return abs(a[1] - b[1]) < 0.01


def _est_vertical(a, b) -> bool:
    return abs(a[0] - b[0]) < 0.01


def croisements(traces: Sequence[Sequence[tuple[float, float]]]) -> list[tuple[int, int, float, float]]:
    """Croisements orthogonaux entre tracés, hors extrémités partagées."""
    resultat = []
    for i in range(len(traces)):
        for j in range(i + 1, len(traces)):
            for a, b in orthogonaux(list(traces[i])):
                for c, d in orthogonaux(list(traces[j])):
                    if _est_horizontal(a, b) and _est_vertical(c, d):
                        y, x = a[1], c[0]
                        if (min(a[0], b[0]) + 0.01 < x < max(a[0], b[0]) - 0.01
                                and min(c[1], d[1]) + 0.01 < y < max(c[1], d[1]) - 0.01):
                            resultat.append((i, j, x, y))
                    elif _est_vertical(a, b) and _est_horizontal(c, d):
                        x, y = a[0], c[1]
                        if (min(a[1], b[1]) + 0.01 < y < max(a[1], b[1]) - 0.01
                                and min(c[0], d[0]) + 0.01 < x < max(c[0], d[0]) - 0.01):
                            resultat.append((i, j, x, y))
    return resultat


def _couper(points: Sequence[tuple[float, float]], gaps: Iterable[tuple[float, float]]):
    """Découpe un tracé aux gaps demandés ; rend une liste de sous-tracés."""
    gaps = list(gaps)
    if not gaps:
        return [list(points)]
    sous_traces: list[list[tuple[float, float]]] = [[tuple(points[0])]]
    for a, b in orthogonaux(list(points)):
        decoupes = []
        horizontal = _est_horizontal(a, b)
        for gx, gy in gaps:
            if horizontal and abs(gy - a[1]) < 0.01 and min(a[0], b[0]) < gx < max(a[0], b[0]):
                decoupes.append(gx)
            if not horizontal and abs(gx - a[0]) < 0.01 and min(a[1], b[1]) < gy < max(a[1], b[1]):
                decoupes.append(gy)
        sens = 1 if (b[0] > a[0] if horizontal else b[1] > a[1]) else -1
        for valeur in sorted(set(decoupes), reverse=sens < 0):
            demi = HOP_GAP / 2
            debut = (valeur - sens * demi, a[1]) if horizontal else (a[0], valeur - sens * demi)
            fin = (valeur + sens * demi, a[1]) if horizontal else (a[0], valeur + sens * demi)
            if horizontal:
                debut = (max(min(a[0], b[0]), min(max(a[0], b[0]), debut[0])), a[1])
                fin = (max(min(a[0], b[0]), min(max(a[0], b[0]), fin[0])), a[1])
            else:
                debut = (a[0], max(min(a[1], b[1]), min(max(a[1], b[1]), debut[1])))
                fin = (a[0], max(min(a[1], b[1]), min(max(a[1], b[1]), fin[1])))
            sous_traces[-1].append(debut)
            sous_traces.append([fin])
        sous_traces[-1].append(tuple(b))
    return [trace for trace in sous_traces if len(trace) >= 2]


def _arrondi(trace: Sequence[tuple[float, float]], radius: float) -> str:
    if len(trace) < 2:
        return ""
    d = [f"M {trace[0][0]:.1f} {trace[0][1]:.1f}"]
    for i in range(1, len(trace) - 1):
        x0, y0 = trace[i - 1]
        x1, y1 = trace[i]
        x2, y2 = trace[i + 1]
        l1 = math.hypot(x1 - x0, y1 - y0)
        l2 = math.hypot(x2 - x1, y2 - y1)
        if l1 == 0 or l2 == 0:
            continue
        r = min(radius, l1 / 2, l2 / 2)
        bx, by = x1 - (x1 - x0) / l1 * r, y1 - (y1 - y0) / l1 * r
        ax, ay = x1 + (x2 - x1) / l2 * r, y1 + (y2 - y1) / l2 * r
        d.append(f"L {bx:.1f} {by:.1f}")
        d.append(f"Q {x1:.1f} {y1:.1f} {ax:.1f} {ay:.1f}")
    d.append(f"L {trace[-1][0]:.1f} {trace[-1][1]:.1f}")
    return " ".join(d)


def traces(points: Sequence[tuple[float, float]], *, radius: float = RADIUS,
           gaps: Iterable[tuple[float, float]] = ()) -> list[str]:
    """Un ou plusieurs `d` SVG : coudes arrondis et gaps aux croisements."""
    return [_arrondi(trace, radius) for trace in _couper(points, gaps)]


def simplifier(points: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    """Retire les points doublés ou alignés : un tracé orthogonal minimal."""
    sortie: list[tuple[float, float]] = []
    for point in points:
        point = (float(point[0]), float(point[1]))
        if sortie and abs(point[0] - sortie[-1][0]) < 0.01 and abs(point[1] - sortie[-1][1]) < 0.01:
            continue
        if len(sortie) >= 2:
            a, b = sortie[-2], sortie[-1]
            if ((abs(a[0] - b[0]) < 0.01 and abs(b[0] - point[0]) < 0.01)
                    or (abs(a[1] - b[1]) < 0.01 and abs(b[1] - point[1]) < 0.01)):
                sortie[-1] = point
                continue
        sortie.append(point)
    return sortie


def meilleur_segment(points: Sequence[tuple[float, float]]):
    """Le plus long segment du tracé ; les horizontaux passent avant les verticaux."""
    segments = orthogonaux(simplifier(points))
    if not segments:
        return None
    return max(segments, key=lambda s: (abs(s[0][0] - s[1][0]), abs(s[0][1] - s[1][1])))


def label_trace(points: Sequence[tuple[float, float]], texte, *, color, background,
                gap=LABEL_GAP, max_width: float | None = None) -> str:
    """Label posé à côté du plus long segment, avec masque et sans toucher la ligne."""
    segment = meilleur_segment(points)
    if not segment or not texte:
        return ""
    a, b = segment
    if abs(a[1] - b[1]) < 0.01:  # horizontal : au-dessus
        if max_width is None:
            max_width = max(40, abs(b[0] - a[0]) - 16)
        return label((a[0] + b[0]) / 2, a[1], texte, color=color, background=background,
                     side="above", gap=gap, max_width=max_width)
    return label(a[0], (a[1] + b[1]) / 2, texte, color=color, background=background,
                 side="right", gap=gap, max_width=max_width)


def englobante(rects: Sequence[Mapping], padding=16) -> tuple[int, int, int, int] | None:
    """Boîte englobante alignée sur la grille, avec marge."""
    rects = [r for r in rects if r]
    if not rects:
        return None
    gauche = min(float(r["x"]) for r in rects) - padding
    haut = min(float(r["y"]) for r in rects) - padding
    droite = max(float(r["x"]) + float(r["largeur"]) for r in rects) + padding
    bas = max(float(r["y"]) + float(r["hauteur"]) for r in rects) + padding
    return snap(gauche), snap(haut), snap(droite - gauche), snap(bas - haut)


def label(x, line_y, texte, *, color, background, side="above", gap=LABEL_GAP,
          max_width: float | None = None) -> str:
    """Label masqué, jamais posé sur la ligne : 8 px d'écart minimum.

    Quand la largeur disponible est insuffisante, le libellé passe sur deux lignes
    plutôt que d'être coupé au premier mot utile.
    """
    texte = str(texte or "")
    if not texte:
        return ""
    lignes = [texte]
    if max_width is not None and len(texte) * 5.4 + 12 > max_width:
        maximum = max(4, int((max_width - 12) / 5.4))
        if len(texte) > maximum:
            coupe = texte.rfind(" ", 0, maximum + 1)
            if coupe < maximum // 2:
                coupe = maximum
            premiere = texte[:coupe].rstrip()
            reste = texte[coupe:].lstrip()
            if len(reste) > maximum:
                reste = reste[: maximum - 1].rstrip() + "…"
            lignes = [premiere, reste] if reste else [premiere]
    largeur = max(32, max(len(ligne) for ligne in lignes) * 5.4 + 12)
    if max_width is not None:
        largeur = min(largeur, max(24.0, float(max_width)))
    interligne = 11
    hauteur = MASK_HEIGHT + (len(lignes) - 1) * interligne
    if side == "right":
        tx = x + gap
        anchor = "start"
        mask_x = tx - 4
        premiere_base = line_y - (len(lignes) - 1) * interligne / 2 + 3.5
        mask_y = premiere_base - 9
    elif side == "left":
        tx = x - gap
        anchor = "end"
        mask_x = tx - largeur + 4
        premiere_base = line_y - (len(lignes) - 1) * interligne / 2 + 3.5
        mask_y = premiere_base - 9
    elif side == "below":
        tx = x
        anchor = "middle"
        premiere_base = line_y + gap + 10
        mask_x = x - largeur / 2
        mask_y = line_y + gap
    else:
        tx = x
        anchor = "middle"
        premiere_base = line_y - gap - 4 - (len(lignes) - 1) * interligne
        mask_x = x - largeur / 2
        mask_y = premiere_base - 10
    textes = [f'<text x="{tx:.1f}" y="{premiere_base:.1f}" text-anchor="{anchor}" fill="{color}" '
              f'font-family="ui-sans-serif, system-ui, sans-serif" font-size="9.5">']
    for index, ligne in enumerate(lignes):
        decalage = 0 if index == 0 else interligne
        textes.append(f'<tspan x="{tx:.1f}" dy="{decalage}">{html.escape(ligne)}</tspan>')
    textes.append("</text>")
    return (
        f'<rect x="{mask_x:.1f}" y="{mask_y:.1f}" width="{largeur:.1f}" height="{hauteur}" '
        f'rx="2" fill="{background}"/>'
        + "".join(textes)
    )


def zone(x, y, w, h, texte, *, rule, fill, muted) -> str:
    return (
        f'<g data-zone="1"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" '
        f'fill="{fill}" stroke="{rule}" stroke-width="1" stroke-dasharray="4 4"/>'
        f'<text x="{x+14}" y="{y+18}" fill="{muted}" font-family="ui-sans-serif, system-ui, sans-serif" '
        f'font-size="9" letter-spacing="0.08em">{html.escape(texte)}</text></g>'
    )


def markers(etats: Mapping[str, tuple[str, float, str | None]]) -> str:
    sortie = []
    for etat, (couleur, _, _) in sorted(etats.items()):
        sortie.append(
            f'<marker id="fleche-{etat}" viewBox="0 0 8 8" markerWidth="8" markerHeight="8" '
            f'refX="8" refY="4" orient="auto" markerUnits="userSpaceOnUse">'
            f'<path d="M 0 0 L 8 4 L 0 8 Z" fill="{couleur}"/></marker>'
        )
    return "".join(sortie)


def legende(items: Sequence[tuple[str, str, str, str | None]], x, y, largeur, *,
            rule, muted, ink) -> str:
    """Bandeau horizontal hors du dessin. Chaque item est (libellé, état, couleur, pointillés)."""
    if not items:
        return ""
    sortie = [f'<line x1="{x}" y1="{y}" x2="{x + largeur}" y2="{y}" stroke="{rule}" stroke-width="1"/>']
    sortie.append(f'<text x="{x}" y="{y + 18}" fill="{muted}" font-family="ui-sans-serif, system-ui, sans-serif" '
                  f'font-size="9" letter-spacing="0.12em">LÉGENDE</text>')
    depart = x + 104
    pas = (largeur - 104) / max(1, len(items))
    for index, (texte, etat, couleur, dash) in enumerate(items):
        ix = depart + index * pas
        sortie.append(f'<line x1="{ix:.1f}" y1="{y + 14}" x2="{ix + 22:.1f}" y2="{y + 14}" '
                      f'stroke="{couleur}" stroke-width="1.6"'
                      + (f' stroke-dasharray="{dash}"' if dash else "")
                      + f' marker-end="url(#fleche-{html.escape(etat, quote=True)})"/>')
        sortie.append(f'<text x="{ix + 30:.1f}" y="{y + 18}" fill="{ink}" '
                      f'font-family="ui-sans-serif, system-ui, sans-serif" font-size="9">{html.escape(texte)}</text>')
    return "".join(sortie)
