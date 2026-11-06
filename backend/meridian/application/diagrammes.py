"""Compilation des schémas de Flore en SVG autonome, stockable et rejouable.

Le schéma brut reste la source de vérité. Ce module en produit un artefact SVG déterministe,
sans script, sans ressource externe et avec un hash de source. Le rendu interactif du chat
(viewpoint, zoom, sélection) est branché sur cet artefact quand il est disponible.
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import html
import json
import math
import xml.etree.ElementTree as ET

from meridian.application import diagram_layout as layout

__all__ = ["compiler", "enrichir_reponse", "plan"]

_COULEURS = {
    "paper": "#071019",
    "ink": "#F2F6F8",
    "muted": "#7C93A8",
    "soft": "#94A3B8",
    "rule": "rgba(255,255,255,0.12)",
    "accent": "#60A5FA",
}
_ETATS = {
    "code": ("#60A5FA", 1.5, None),
    "valide": ("#4ADE80", 3.0, None),
    "verifie": ("#34D399", 2.0, None),
    "recoupe": ("#22D3EE", 2.0, None),
    "selon": ("#93C5FD", 1.5, None),
    "propose": ("#F2B84B", 1.5, "3 3"),
    "conteste": ("#F2B84B", 1.5, "6 3"),
    "inconnu": ("#7C93A8", 1.0, "3 3"),
}
_LEGENDES = {
    "code": "vérifié par le code",
    "valide": "validé",
    "verifie": "vérifié",
    "recoupe": "recoupé",
    "selon": "selon",
    "propose": "proposé",
    "conteste": "contesté",
    "inconnu": "inconnu",
}
_MARGE = 24
_HAUTEUR = 40
_ECART_X = 160
_ECART_Y = 24
_ECART_RANGS = 88
_MAX_NOEUDS = 12
_MAX_LIENS = 20


def _texte(valeur, maximum=80) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def _tronquer(valeur, maximum=40) -> str:
    texte = _texte(valeur, 100)
    return texte if len(texte) <= maximum else texte[: maximum - 1].rstrip() + "…"


def _lignes(libelle, maximum=36) -> list[str]:
    texte = _tronquer(libelle, maximum * 2)
    if len(texte) <= maximum:
        return [texte]
    coupe = texte.rfind(" ", 0, maximum + 1)
    if coupe < maximum // 2:
        coupe = maximum
    premiere = texte[:coupe].rstrip()
    reste = texte[coupe:].lstrip()
    if len(reste) > maximum:
        reste = reste[: maximum - 1].rstrip() + "…"
    return [premiere, reste] if reste else [premiere]


def _largeur(libelle) -> int:
    return max(120, min(320, 40 + max(len(ligne) for ligne in _lignes(libelle)) * 7))


def _texte_noeud(boite) -> str:
    lignes = _lignes(boite["libelle"])
    x = boite["x"] + 22
    debut = boite["cy"] if len(lignes) == 1 else boite["cy"] - 2
    attributs = (f'x="{x}" y="{debut}" fill="{_COULEURS["ink"]}" '
                 f'font-family="ui-sans-serif, system-ui, sans-serif" font-size="12"')
    if len(lignes) == 1:
        return f'<text {attributs} dominant-baseline="middle">{html.escape(lignes[0])}</text>'
    return (f'<text {attributs}>'
            f'<tspan x="{x}" y="{boite["cy"] - 2}">{html.escape(lignes[0])}</tspan>'
            f'<tspan x="{x}" y="{boite["cy"] + 10}">{html.escape(lignes[1])}</tspan></text>')


def _id(valeur) -> str:
    return _texte(valeur, 80)


def _hash(schema: Mapping) -> str:
    charge = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(charge.encode("utf-8")).hexdigest()[:16]


def _normaliser(schema: Mapping) -> tuple[list[dict], list[dict]]:
    boites, vus = [], set()
    for boite in schema.get("boites") or schema.get("composants") or ():
        if not isinstance(boite, Mapping):
            continue
        ident = _id(boite.get("id"))
        if not ident or ident in vus:
            continue
        vus.add(ident)
        boites.append({"id": ident, "libelle": _tronquer(boite.get("libelle") or boite.get("nom") or ident, 72)})
        if len(boites) >= _MAX_NOEUDS:
            break
    ids = {b["id"] for b in boites}
    liens, vus_liens = [], set()
    for lien in schema.get("fleches") or schema.get("liens") or ():
        if not isinstance(lien, Mapping):
            continue
        de, vers = _id(lien.get("de")), _id(lien.get("vers"))
        if de not in ids or vers not in ids or de == vers:
            continue
        cle = (de, vers, _texte(lien.get("libelle"), 100))
        if cle in vus_liens:
            continue
        vus_liens.add(cle)
        liens.append({
            "de": de, "vers": vers,
            "libelle": _tronquer(lien.get("libelle"), 64),
            "etat": lien.get("etat") if lien.get("etat") in _ETATS else "inconnu",
        })
        if len(liens) >= _MAX_LIENS:
            break
    return boites, liens


def _rangs(boites: list[dict], liens: list[dict]) -> dict[str, int]:
    ids = [b["id"] for b in boites]
    voisins = {ident: [] for ident in ids}
    entrant = {ident: 0 for ident in ids}
    for lien in liens:
        if lien["de"] not in voisins or lien["vers"] not in entrant or lien["de"] == lien["vers"]:
            continue
        voisins[lien["de"]].append(lien["vers"])
        entrant[lien["vers"]] += 1
    rangs = {ident: 0 for ident in ids}
    file = [ident for ident in ids if entrant[ident] == 0]
    traites = set()
    for ident in file:
        traites.add(ident)
        for voisin in voisins[ident]:
            rangs[voisin] = max(rangs[voisin], rangs[ident] + 1)
            entrant[voisin] -= 1
            if entrant[voisin] == 0:
                file.append(voisin)
    for ident in ids:
        if ident not in traites:
            rangs[ident] = max((rangs.get(v, 0) + 1 for v in ids if ident in voisins.get(v, ())), default=0)
    return rangs


def _legende_items(liens: list[dict]) -> list[tuple]:
    etats = {lien["etat"] for lien in liens}
    return [(_LEGENDES.get(etat, etat), etat, _ETATS[etat][0], _ETATS[etat][2])
            for etat in _ETATS if etat in etats]


def _chevauche(a, b) -> bool:
    return (a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
            and a[1] < b[1] + b[3] and b[1] < a[1] + a[3])


def _dans(boite, rect) -> bool:
    return (boite["x"] >= rect[0] and boite["x"] + boite["largeur"] <= rect[0] + rect[2]
            and boite["y"] >= rect[1] and boite["y"] + boite["hauteur"] <= rect[1] + rect[3])


def _zones_sures(par_id, groupes):
    """Ne garde que les zones disjointes qui n'enferment aucun nœud étranger."""
    candidates = []
    for groupe in groupes[:6]:
        ids = {str(ident) for ident in (groupe.get("ids") or ()) if str(ident) in par_id}
        if not ids:
            continue
        boite = layout.englobante([par_id[ident] for ident in ids], padding=16)
        if not boite:
            continue
        x, y, w, h = boite
        candidates.append((groupe, ids, (x, layout.snap(y - 12), w, layout.snap(h + 12))))
    retenues = []
    for index, (groupe, ids, rect) in enumerate(candidates):
        if any(_chevauche(rect, autre) for autre_index, (_, _, autre) in enumerate(candidates)
               if autre_index != index):
            continue
        if any(str(boite["id"]) not in ids and _dans(boite, rect) for boite in par_id.values()):
            continue
        retenues.append((groupe, ids, rect))
    return retenues


def _architecture(schema, boites, liens) -> dict:
    rangs = _rangs(boites, liens)
    par_rang: dict[int, list[dict]] = {}
    for boite in boites:
        par_rang.setdefault(rangs[boite["id"]], []).append(boite)
    groupes = [g for g in (schema.get("groupes") or ()) if isinstance(g, Mapping)]
    haut = 96 if groupes else 64

    # Une chaîne longue est repliée en grille : plus lisible qu'une seule colonne de 2000 px.
    ordre = sorted(par_rang)
    colonnes = 3 if len(boites) > 6 else max(1, min(3, len(boites)))
    position = {rang: divmod(index, colonnes) for index, rang in enumerate(ordre)}
    hauteur_rang = {rang: len(membres) * (_HAUTEUR + _ECART_Y) - _ECART_Y
                    for rang, membres in par_rang.items()}
    largeur_col: dict[int, int] = {}
    hauteur_rangée: dict[int, int] = {}
    for rang, membres in par_rang.items():
        ligne, colonne = position[rang]
        largeur_col[colonne] = max(largeur_col.get(colonne, 0),
                                   max(layout.snap(_largeur(b["libelle"])) for b in membres))
        hauteur_rangée[ligne] = max(hauteur_rangée.get(ligne, 0), hauteur_rang[rang])
    xs: dict[int, int] = {}
    x = layout.snap(_MARGE + 16)
    for colonne in sorted(largeur_col):
        xs[colonne] = x
        x = layout.snap(x + largeur_col[colonne] + _ECART_X)
    ys: dict[int, int] = {}
    y = layout.snap(haut)
    for ligne in sorted(hauteur_rangée):
        ys[ligne] = y
        y = layout.snap(y + hauteur_rangée[ligne] + _ECART_RANGS)
    for rang, membres in par_rang.items():
        ligne, colonne = position[rang]
        y = layout.snap(ys[ligne] + (hauteur_rangée[ligne] - hauteur_rang[rang]) / 2)
        for boite in membres:
            largeur = layout.snap(_largeur(boite["libelle"]))
            boite.update({"x": xs[colonne], "y": y, "largeur": largeur, "hauteur": _HAUTEUR,
                          "cx": xs[colonne] + largeur / 2, "cy": y + _HAUTEUR / 2,
                          "rang": rang, "ligne": ligne})
            y = layout.snap(y + _HAUTEUR + _ECART_Y)

    par_id = {b["id"]: b for b in boites}
    bas = max((b["y"] + b["hauteur"] for b in boites), default=0)
    routes = []
    canal = 0
    canaux: dict[tuple[int, int], int] = {}
    for lien in liens:
        de, vers = par_id[lien["de"]], par_id[lien["vers"]]
        droite, gauche = de["x"] + de["largeur"], vers["x"]
        if gauche > droite + 8 and abs(vers["cy"] - de["cy"]) < 0.01:
            points = [(droite, de["cy"]), (gauche, vers["cy"])]
            etiquette = layout.label_trace(points, lien["libelle"], color=_COULEURS["soft"],
                                           background=_COULEURS["paper"])
        elif gauche > droite + 8:
            bus = layout.snap(droite + 24)
            if bus > gauche - 24:
                bus = layout.snap((droite + gauche) / 2)
            points = [(droite, de["cy"]), (bus, de["cy"]), (bus, vers["cy"]), (gauche, vers["cy"])]
            etiquette = layout.label(bus, (de["cy"] + vers["cy"]) / 2, lien["libelle"],
                                     color=_COULEURS["soft"], background=_COULEURS["paper"],
                                     side="right", max_width=max(40, gauche - bus - 16))
        elif vers["ligne"] > de["ligne"]:
            cle = (de["ligne"], vers["ligne"])
            couloir = canaux.get(cle, 0)
            canaux[cle] = couloir + 1
            bas_ligne = max(b["y"] + b["hauteur"] for b in boites if b["ligne"] == de["ligne"])
            y = min(layout.snap(bas_ligne + 28 + couloir * 20), layout.snap(vers["y"] - 20))
            detour = 24
            points = [(droite, de["cy"]), (droite + detour, de["cy"]), (droite + detour, y),
                      (vers["cx"], y), (vers["cx"], vers["y"])]
            etiquette = layout.label_trace(points, lien["libelle"], color=_COULEURS["soft"],
                                           background=_COULEURS["paper"])
        else:
            y = layout.snap(bas + 32 + canal * 24)
            canal += 1
            detour = 32
            points = [(droite, de["cy"]), (droite + detour, de["cy"]),
                      (droite + detour, y), (max(_MARGE, gauche - detour), y),
                      (max(_MARGE, gauche - detour), vers["cy"]), (gauche, vers["cy"])]
            etiquette = layout.label_trace(points, lien["libelle"], color=_COULEURS["soft"],
                                           background=_COULEURS["paper"])
        routes.append((lien, layout.simplifier(
            [(layout.snap(px), layout.snap(py)) for px, py in points]), etiquette))

    gaps: dict[int, list[tuple[float, float]]] = {}
    for i, j, croisement_x, croisement_y in layout.croisements([points for _, points, _ in routes]):
        gaps.setdefault(j, []).append((croisement_x, croisement_y))

    fleches = []
    for index, (lien, points, etiquette) in enumerate(routes):
        couleur, epaisseur, pointille = _ETATS[lien["etat"]]
        d = " ".join(layout.traces(points, gaps=gaps.get(index, ())))
        dash = f' stroke-dasharray="{pointille}"' if pointille else ""
        fleches.append(f'<g data-edge="1"><path d="{d}" fill="none" stroke="{couleur}" stroke-width="{epaisseur}"'
                       f' stroke-linecap="round" stroke-linejoin="round"{dash} marker-end="url(#fleche-{lien["etat"]})"/>'
                       f'{etiquette}</g>')

    zones = []
    for groupe, ids, rect in _zones_sures(par_id, groupes):
        zx, zy, zw, zh = rect
        zones.append(layout.zone(zx, zy, zw, zh, _texte(groupe.get("libelle"), 32),
                                 rule=_COULEURS["rule"], fill="rgba(255,255,255,0.025)",
                                 muted=_COULEURS["muted"]))

    bas_contenu = max([b["y"] + b["hauteur"] for b in boites]
                      + [max(pt[1] for pt in points) for _, points, _ in routes] + [0])
    largeur = max([600] + [b["x"] + b["largeur"] for b in boites]
                  + [max(pt[0] for pt in points) for _, points, _ in routes]) + _MARGE
    largeur = int(math.ceil(largeur / layout.GRID) * layout.GRID)
    items = _legende_items(liens)
    y_legende = layout.snap(bas_contenu + 40)
    legende = layout.legende(items, _MARGE, y_legende, largeur - 2 * _MARGE,
                             rule=_COULEURS["rule"], muted=_COULEURS["muted"],
                             ink=_COULEURS["soft"])
    hauteur = int(math.ceil((y_legende + 40 if items else bas_contenu + _MARGE) / layout.GRID) * layout.GRID)

    noeuds = "".join(
        f'<g data-node-id="{html.escape(b["id"], quote=True)}"><rect x="{b["x"]}" y="{b["y"]}" width="{b["largeur"]}" height="{b["hauteur"]}" rx="6" fill="{_COULEURS["paper"]}" stroke="{_COULEURS["rule"]}"/>'
        f'<rect x="{b["x"]}" y="{b["y"] + 12}" width="3" height="16" rx="1.5" fill="{_COULEURS["accent"]}"/>'
        f'{_texte_noeud(b)}</g>'
        for b in boites
    )
    return {"largeur": largeur, "hauteur": hauteur, "noeuds": noeuds, "zones": "".join(zones),
            "fleches": "".join(fleches), "legende": legende, "titre": _texte(schema.get("titre"), 80)}


def _flux_vertical(schema, boites, liens) -> dict:
    """Flux long : une rangée par étape, de haut en bas, comme une chaîne de traitement."""
    rangs = _rangs(boites, liens)
    par_rang: dict[int, list[dict]] = {}
    for boite in boites:
        par_rang.setdefault(rangs[boite["id"]], []).append(boite)
    groupes = [g for g in (schema.get("groupes") or ()) if isinstance(g, Mapping)]
    haut = 104 if groupes else 88
    ecart_x, ecart_y = 48, 48
    hauteur_noeud = 56
    largeurs = {b["id"]: layout.snap(max(200, min(320, _largeur(b["libelle"])))) for b in boites}
    largeur_contenu = max(
        sum(largeurs[b["id"]] for b in membres) + ecart_x * (len(membres) - 1)
        for membres in par_rang.values())
    largeur = int(math.ceil(max(720, largeur_contenu + 2 * (_MARGE + 24)) / layout.GRID) * layout.GRID)

    y = layout.snap(haut)
    for rang in sorted(par_rang):
        membres = par_rang[rang]
        total = sum(largeurs[b["id"]] for b in membres) + ecart_x * (len(membres) - 1)
        x = layout.snap((largeur - total) / 2)
        for boite in membres:
            largeur_boite = largeurs[boite["id"]]
            boite.update({"x": x, "y": y, "largeur": largeur_boite, "hauteur": hauteur_noeud,
                          "cx": x + largeur_boite / 2, "cy": y + hauteur_noeud / 2, "rang": rang})
            x = layout.snap(x + largeur_boite + ecart_x)
        y = layout.snap(y + hauteur_noeud + ecart_y)
    bas = y - ecart_y

    par_id = {b["id"]: b for b in boites}
    routes = []
    coté = 0
    for lien in liens:
        de, vers = par_id[lien["de"]], par_id[lien["vers"]]
        if vers["rang"] == de["rang"] + 1:
            if abs(vers["cx"] - de["cx"]) < 4:
                points = [(de["cx"], de["y"] + de["hauteur"]), (vers["cx"], vers["y"])]
            else:
                y_canal = layout.snap(de["y"] + de["hauteur"] + ecart_y / 2)
                points = [(de["cx"], de["y"] + de["hauteur"]), (de["cx"], y_canal),
                          (vers["cx"], y_canal), (vers["cx"], vers["y"])]
        else:
            y_sortie = layout.snap(de["y"] + de["hauteur"] + 20)
            if vers["rang"] == 0:
                y_entree = layout.snap(vers["y"] + vers["hauteur"] + 20)
                arrivee = (vers["cx"], vers["y"] + vers["hauteur"])
            else:
                y_entree = layout.snap(vers["y"] - 20)
                arrivee = (vers["cx"], vers["y"])
            lane = layout.snap(max(b["x"] + b["largeur"] for b in boites) + 32 + coté * 20)
            coté += 1
            points = [(de["cx"], de["y"] + de["hauteur"]), (de["cx"], y_sortie),
                      (lane, y_sortie), (lane, y_entree), (vers["cx"], y_entree), arrivee]
        points = layout.simplifier([(layout.snap(px), layout.snap(py)) for px, py in points])
        routes.append((lien, points, de, vers))
        largeur = max(largeur, max(px for px, _ in points) + 160)

    routes_avec_labels = []
    for lien, points, de, vers in routes:
        if vers["rang"] == de["rang"] + 1:
            # Dans le couloir entre deux rangées : à droite ou à gauche de la ligne,
            # jamais au-dessus d'une carte.
            y_label = (de["y"] + de["hauteur"] + vers["y"]) / 2
            côté = "right" if de["cx"] < largeur / 2 else "left"
            disponible = largeur - de["cx"] - 24 if côté == "right" else de["cx"] - 24
            etiquette = layout.label(de["cx"], y_label, lien["libelle"], color=_COULEURS["soft"],
                                     background=_COULEURS["paper"], side=côté,
                                     max_width=max(80, disponible))
        else:
            verticales = [(a, b) for a, b in layout.orthogonaux(points) if abs(a[0] - b[0]) < 0.01]
            segment = max(verticales, key=lambda s: abs(s[0][1] - s[1][1]), default=None)
            if segment:
                etiquette = layout.label(segment[0][0], (segment[0][1] + segment[1][1]) / 2,
                                         lien["libelle"], color=_COULEURS["soft"],
                                         background=_COULEURS["paper"], side="right",
                                         max_width=max(80, largeur - segment[0][0] - 24))
            else:
                etiquette = layout.label_trace(points, lien["libelle"], color=_COULEURS["soft"],
                                               background=_COULEURS["paper"])
        routes_avec_labels.append((lien, points, etiquette))

    gaps: dict[int, list[tuple[float, float]]] = {}
    for i, j, croisement_x, croisement_y in layout.croisements(
            [points for _, points, _ in routes_avec_labels]):
        gaps.setdefault(j, []).append((croisement_x, croisement_y))

    fleches = []
    for index, (lien, points, etiquette) in enumerate(routes_avec_labels):
        couleur, epaisseur, pointille = _ETATS[lien["etat"]]
        d = " ".join(layout.traces(points, gaps=gaps.get(index, ())))
        dash = f' stroke-dasharray="{pointille}"' if pointille else ""
        fleches.append(f'<g data-edge="1"><path d="{d}" fill="none" stroke="{couleur}" stroke-width="{epaisseur}"'
                       f' stroke-linecap="round" stroke-linejoin="round"{dash} marker-end="url(#fleche-{lien["etat"]})"/>'
                       f'{etiquette}</g>')

    zones = []
    for groupe, ids, rect in _zones_sures(par_id, groupes):
        zx, zy, zw, zh = rect
        zones.append(layout.zone(zx, zy, zw, zh, _texte(groupe.get("libelle"), 32),
                                 rule=_COULEURS["rule"], fill="rgba(255,255,255,0.025)",
                                 muted=_COULEURS["muted"]))

    largeur = int(math.ceil(largeur / layout.GRID) * layout.GRID)
    bas_contenu = max([b["y"] + b["hauteur"] for b in boites]
                      + [max(py for _, py in points) for _, points, _ in routes_avec_labels] + [bas])
    items = _legende_items(liens)
    y_legende = layout.snap(bas_contenu + 40)
    legende = layout.legende(items, _MARGE, y_legende, largeur - 2 * _MARGE,
                             rule=_COULEURS["rule"], muted=_COULEURS["muted"],
                             ink=_COULEURS["soft"])
    hauteur = int(math.ceil((y_legende + 40 if items else bas_contenu + _MARGE)
                            / layout.GRID) * layout.GRID)
    noeuds = "".join(
        f'<g data-node-id="{html.escape(b["id"], quote=True)}"><rect x="{b["x"]}" y="{b["y"]}" width="{b["largeur"]}" height="{b["hauteur"]}" rx="6" fill="{_COULEURS["paper"]}" stroke="{_COULEURS["rule"]}"/>'
        f'<rect x="{b["x"] + 12}" y="{b["y"] + 10}" width="3" height="16" rx="1.5" fill="{_COULEURS["accent"]}"/>'
        f'{_texte_noeud(b)}</g>'
        for b in boites
    )
    return {"largeur": largeur, "hauteur": hauteur, "noeuds": noeuds, "zones": "".join(zones),
            "fleches": "".join(fleches), "legende": legende, "titre": _texte(schema.get("titre"), 80)}


def _sequence(schema, boites, liens) -> dict:
    x = layout.snap(_MARGE + 16)
    for boite in boites:
        largeur = layout.snap(_largeur(boite["libelle"]))
        boite.update({"x": x, "y": 64, "largeur": largeur, "hauteur": _HAUTEUR,
                      "cx": x + largeur / 2, "cy": 64 + _HAUTEUR / 2})
        x = layout.snap(x + largeur + 56)
    par_id = {b["id"]: b for b in boites}
    routes = []
    for i, lien in enumerate(liens):
        de, vers = par_id[lien["de"]], par_id[lien["vers"]]
        y = layout.snap(144 + i * 48)
        routes.append((lien, [(de["cx"], y), (vers["cx"], y)]))
    bas = max((points[0][1] for _, points in routes), default=144) + 40
    items = _legende_items(liens)
    y_legende = layout.snap(bas + 24)
    largeur = int(math.ceil((max((b["x"] + b["largeur"] for b in boites), default=600) + _MARGE)
                            / layout.GRID) * layout.GRID)
    messages = []
    for lien, points in routes:
        couleur, epaisseur, pointille = _ETATS[lien["etat"]]
        dash = f' stroke-dasharray="{pointille}"' if pointille else ""
        etiquette = layout.label_trace(points, lien["libelle"], color=_COULEURS["soft"],
                                       background=_COULEURS["paper"])
        messages.append(
            f'<g data-edge="1"><path d="{" ".join(layout.traces(points))}" fill="none" '
            f'stroke="{couleur}" stroke-width="{epaisseur}"{dash} marker-end="url(#fleche-{lien["etat"]})"/>'
            f'{etiquette}</g>'
        )
    acteurs = "".join(
        f'<g data-node-id="{html.escape(b["id"], quote=True)}"><line x1="{b["cx"]}" y1="{b["y"] + b["hauteur"]}" x2="{b["cx"]}" y2="{bas}" stroke="{_COULEURS["rule"]}" stroke-dasharray="3 4"/>'
        f'<rect x="{b["x"]}" y="{b["y"]}" width="{b["largeur"]}" height="{b["hauteur"]}" rx="6" fill="{_COULEURS["paper"]}" stroke="{_COULEURS["rule"]}"/>'
        f'<rect x="{b["x"]}" y="{b["y"] + 12}" width="3" height="16" rx="1.5" fill="{_COULEURS["accent"]}"/>'
        f'{_texte_noeud(b)}</g>'
        for b in boites
    )
    legende = layout.legende(items, _MARGE, y_legende, largeur - 2 * _MARGE,
                             rule=_COULEURS["rule"], muted=_COULEURS["muted"],
                             ink=_COULEURS["soft"])
    return {"largeur": largeur,
            "hauteur": int(math.ceil((y_legende + 40 if items else bas + _MARGE)
                                     / layout.GRID) * layout.GRID),
            "noeuds": acteurs, "zones": "", "fleches": "".join(messages), "legende": legende,
            "titre": _texte(schema.get("titre"), 80)}


def compiler(schema: Mapping | None) -> dict | None:
    if not isinstance(schema, Mapping) or schema.get("type") not in {"architecture", "flux", "sequence", "data-model"}:
        return None
    boites, liens = _normaliser(schema)
    if not boites or not liens:
        return None
    type_ = schema.get("type")
    if type_ == "sequence":
        disposition = _sequence(schema, boites, liens)
    elif type_ == "flux" and len(boites) >= 6:
        disposition = _flux_vertical(schema, boites, liens)
    else:
        disposition = _architecture(schema, boites, liens)
    titre = disposition["titre"] or "Schéma"
    description = f"Schéma « {titre} » : {len(boites)} nœud(s), {len(liens)} lien(s)."
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{html.escape(titre, quote=True)}" '
        f'viewBox="0 0 {disposition["largeur"]} {disposition["hauteur"]}" width="{disposition["largeur"]}" height="{disposition["hauteur"]}">'
        f'<title>{html.escape(titre)}</title><desc>{html.escape(description)}</desc>'
        f'<defs>{layout.markers(_ETATS)}</defs><rect width="100%" height="100%" fill="{_COULEURS["paper"]}"/>'
        f'<rect x="0.5" y="0.5" width="{disposition["largeur"] - 1}" height="{disposition["hauteur"] - 1}" rx="6" fill="none" stroke="{_COULEURS["rule"]}"/>'
        f'<text x="{_MARGE}" y="32" fill="{_COULEURS["ink"]}" font-family="ui-sans-serif, system-ui, sans-serif" font-size="13" font-weight="600">{html.escape(titre)}</text>'
        f'{disposition["zones"]}{disposition["fleches"]}{disposition["noeuds"]}{disposition["legende"]}</svg>'
    )
    return {
        "type": "design-diagram", "mode": "deterministe", "version": "1.0", "titre": titre,
        "largeur": disposition["largeur"], "hauteur": disposition["hauteur"],
        "hash": _hash(schema), "svg": svg,
    }


def enrichir_reponse(reponse: dict) -> dict:
    """Compile les schémas d'une réponse, sans modifier les schémas bruts."""
    if not isinstance(reponse, dict):
        return reponse
    schemas = reponse.get("schemas") or ()
    diagrammes = [d for d in (compiler(schema) for schema in schemas) if d]
    if diagrammes:
        reponse["diagrammes"] = diagrammes
    return reponse


def plan(schema: Mapping | None) -> dict | None:
    """Plan de placement des nœuds, pour un auteur qui ne décide que du style."""
    artefact = compiler(schema)
    if not artefact:
        return None
    try:
        racine = ET.fromstring(artefact["svg"])
    except ET.ParseError:
        return None
    libelles = {str(b.get("id")): b.get("libelle") or b.get("nom") or b.get("id")
                for b in (schema.get("boites") or schema.get("composants") or ())
                if isinstance(b, Mapping)}
    boites = []
    for groupe in racine.iter():
        if groupe.tag.split("}")[-1] != "g" or not groupe.attrib.get("data-node-id"):
            continue
        rects = []
        for rect in groupe.iter():
            if rect.tag.split("}")[-1] != "rect":
                continue
            try:
                x = float(rect.attrib.get("x") or 0)
                y = float(rect.attrib.get("y") or 0)
                largeur = float(rect.attrib.get("width") or 0)
                hauteur = float(rect.attrib.get("height") or 0)
            except ValueError:
                continue
            if largeur > 0 and hauteur > 0:
                rects.append((largeur * hauteur, x, y, largeur, hauteur))
        if not rects:
            continue
        _, x, y, largeur, hauteur = max(rects)
        ident = groupe.attrib["data-node-id"]
        boites.append({"id": ident, "libelle": str(libelles.get(ident) or ident),
                       "x": x, "y": y, "largeur": largeur, "hauteur": hauteur})
    return {"largeur": artefact["largeur"], "hauteur": artefact["hauteur"],
            "titre": str(schema.get("titre") or ""),
            "viewBox": f'0 0 {artefact["largeur"]} {artefact["hauteur"]}', "boites": boites}
