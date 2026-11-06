"""Authoring design-diagram pour les schémas du chat.

L'auteur dédié produit un HTML design-diagram éditorial, puis l'exporteur vendu extrait un SVG
autonome. C'est le chemin de qualité par défaut. Un cache disque indexé par hash de schéma
évite de réécrire un même diagramme après un redémarrage.

Mode `editorial` (défaut) : auteur LLM, timeout court, puis repli déterministe.
Mode `fast` : compilateur déterministe uniquement, quelques millisecondes.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from pydantic import BaseModel, Field
from strands import Agent

from meridian.adapters.outbound import diagram_export
from meridian.adapters.outbound.llm import agent
from meridian.application import diagrammes as fallback

journal = logging.getLogger("meridian.design_diagram")
_CACHE: dict[str, dict] = {}
_REFERENCES = Path(__file__).with_name("diagram_references")
_MAX_NOEUDS = 9
_MAX_ARETES = 12
_AUTHOR_NOEUDS = 9
_AUTHOR_ARETES = 12
_MODE_ENV = "JUMEAU_DESIGN_DIAGRAM_MODE"
_TIMEOUT_ENV = "JUMEAU_DESIGN_DIAGRAM_TIMEOUT"
_CACHE_ENV = "JUMEAU_DESIGN_DIAGRAM_CACHE"
_CACHE_VERSION = "4"
_DELAI_AUTEUR = 30.0
_MODES_RAPIDES = {"fast", "rapide", "deterministe", "déterministe"}


class HTMLDiagramme(BaseModel):
    html: str = Field(description="document HTML autonome contenant un seul SVG inline")


PROMPT = """Tu es l'auteur de diagrammes design-diagram de Méridian.

Tu produis un document HTML autonome, avec un seul SVG inline, destiné à être exporté en SVG.
Tu ne produis ni script, ni image externe, ni webfont, ni iframe.

Règles non négociables :
- budget : 9 nœuds maximum et 12 arêtes maximum ;
- chaque nœud DOIT être un groupe SVG `<g data-node-id="...">` (identifiant stable) ; c'est le contrat de clic du viewport ;
- chaque arête DOIT être un `<path>` avec `marker-end` ;
- si le schéma fourni dépasse ce budget, tu produis une vue d'ensemble : regroupe les composants,
  garde les 9 nœuds les plus structurants et les 12 liens essentiels ; ne dépasse jamais ;
- style sombre éditorial : papier #071019, encre #F2F6F8, muted #7C93A8, accent #60A5FA,
  règle rgba(255,255,255,0.12) ;
- pas d'ombre, pas de glow, pas de rounded-2xl ; rayons 6–8 px ;
- une ou deux focales maximum ;
- flèches orthogonales, libellés courts, légende en bas ;
- les flèches de légende ne doivent PAS utiliser `marker-end` : dessine de petits triangles ;
  seules les arêtes réelles du schéma comptent dans le budget de 12 ;
- titre lisible, sous-titre si utile, hypothèses/hors-scope si présents ;
- le SVG porte role="img", un <title> et un <desc> ;
- tout le contenu doit tenir dans le viewBox, sans débordement ;
- calcule la mise en page avant de dessiner : pour 7 nœuds ou plus, une colonne verticale
  principale, avec au moins 96 px par nœud, plus 120 px pour le titre et la légende ;
- une zone entoure ses membres avec 16 à 24 px de marge ; elle ne remplit jamais le viewBox ;
- deux nœuds ne se chevauchent pas, sauf containment explicite d'un conteneur ;
- les étiquettes d'arête restent dans le viewBox et ne chevauchent ni un nœud ni une autre
  étiquette ;
- un PLAN DE PLACEMENT IMPOSÉ accompagne le schéma : reprends ses ids, positions, tailles et
  son viewBox à l'identique (±8 px). Tu peux changer le style, les tags, les zones et la
  légende, pas la géométrie des nœuds ;
- affiche le titre du plan en haut, avec un eyebrow et un sous-titre court, dans la bande
  laissée libre au-dessus du premier nœud ;
- si le contenu ne tient pas, agrandis le viewBox ; ne coupe jamais un nœud ou la légende ;
- pas de HTML dans les libellés : échappe les textes.

Réponds uniquement avec le schéma `HTMLDiagramme`, sans commentaire.
"""


def _hash(schema) -> str:
    charge = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(charge.encode("utf-8")).hexdigest()[:20]


def _cle(schema) -> tuple[str, str]:
    empreinte = _hash(schema)
    return f"{_CACHE_VERSION}-{empreinte}", empreinte


def _cache_dir() -> Path:
    configure = os.environ.get(_CACHE_ENV)
    if configure:
        return Path(configure).expanduser()
    return Path.home() / ".cache" / "meridian" / "design-diagram"


def _chemin_cache(cle: str) -> Path:
    return _cache_dir() / f"{cle}.json"


def _lire_cache(cle: str, plan: dict | None = None) -> dict | None:
    chemin = _chemin_cache(cle)
    try:
        artefact = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(artefact, dict) or artefact.get("mode") != "auteur":
        return None
    svg = str(artefact.get("svg") or "")
    if (not _valider_svg(svg) or _problemes_geometrie(svg)
            or (plan is not None and _problemes_plan(svg, plan))):
        journal.warning("design-diagram : cache disque invalide, il est ignoré")
        try:
            chemin.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    return artefact


def _ecrire_cache(cle: str, artefact: dict) -> None:
    dossier = _cache_dir()
    try:
        dossier.mkdir(parents=True, exist_ok=True)
        chemin = _chemin_cache(cle)
        temporaire = chemin.with_suffix(".tmp")
        temporaire.write_text(json.dumps(artefact, ensure_ascii=False), encoding="utf-8")
        os.replace(temporaire, chemin)
    except OSError:
        journal.warning("design-diagram : cache disque non écrit", exc_info=True)


def _reduire(schema):
    """Ramène un schéma au budget 9/12 avant authoring (vue d'ensemble)."""
    if not isinstance(schema, dict):
        return schema
    boites = list(schema.get("boites") or ())
    fleches = list(schema.get("fleches") or ())
    if len(boites) <= _AUTHOR_NOEUDS and len(fleches) <= _AUTHOR_ARETES:
        return schema
    degre = {}
    for boite in boites:
        degre[str(boite.get("id"))] = 0
    for fleche in fleches:
        degre[str(fleche.get("de"))] = degre.get(str(fleche.get("de")), 0) + 1
        degre[str(fleche.get("vers"))] = degre.get(str(fleche.get("vers")), 0) + 1
    gardees = {str(boite.get("id")) for boite in sorted(
        boites, key=lambda b: (-degre.get(str(b.get("id")), 0), str(b.get("id"))))[:_AUTHOR_NOEUDS]}
    boites_reduites = [b for b in boites if str(b.get("id")) in gardees]
    fleches_reduites = [f for f in fleches
                        if str(f.get("de")) in gardees and str(f.get("vers")) in gardees][:_AUTHOR_ARETES]
    return {**schema, "boites": boites_reduites, "fleches": fleches_reduites,
            "_budget_reduit": {"noeuds_retires": len(boites) - len(boites_reduites),
                               "liens_retires": len(fleches) - len(fleches_reduites)}}


def _contenu(schema, plan=None) -> str:
    type_ = str(schema.get("type") or "architecture")
    reference = _REFERENCES / (
        "type-sequence.md" if type_ == "sequence" else "type-architecture.md")
    morceaux = [json.dumps(schema, ensure_ascii=False, sort_keys=True)[:16000]]
    if plan is None:
        plan = fallback.plan(schema)
    if plan:
        morceaux.append("--- PLAN DE PLACEMENT IMPOSÉ ---\n"
                        + json.dumps(plan, ensure_ascii=False, sort_keys=True))
    try:
        morceaux.append(reference.read_text(encoding="utf-8")[:18000])
        morceaux.append((_REFERENCES / "layout-budget.md").read_text(encoding="utf-8")[:8000])
        morceaux.append((_REFERENCES / "primitives-core.md").read_text(encoding="utf-8")[:10000])
    except OSError:
        pass
    return "\n\n--- RÉFÉRENCE DESIGN-DIAGRAM ---\n".join(morceaux)


def _partie_diagramme(svg: str) -> str:
    return re.split(r"<!--\s*l[ée]gende\b", svg, maxsplit=1,
                    flags=re.IGNORECASE)[0]


def _compter_svg(svg: str) -> tuple[int, int]:
    corps = _partie_diagramme(svg)
    return (len(re.findall(r"data-node-id", corps)),
            len(re.findall(r"marker-end", corps)))


def _valider_svg(svg: str) -> bool:
    if not svg or "<?xml" not in svg and not svg.lstrip().startswith("<svg"):
        return False
    if re.search(r"<(script|foreignObject|iframe)\b|\son[a-z]+\s*=", svg, re.IGNORECASE):
        return False
    try:
        racine = ET.fromstring(svg)
    except ET.ParseError:
        return False
    if racine.tag.split("}")[-1] != "svg":
        return False
    if racine.find("{http://www.w3.org/2000/svg}title") is None and racine.find("title") is None:
        return False
    if racine.find("{http://www.w3.org/2000/svg}desc") is None and racine.find("desc") is None:
        return False
    noeuds, aretes = _compter_svg(svg)
    return bool(noeuds) and noeuds <= _MAX_NOEUDS and aretes <= _MAX_ARETES


def _nombre_attribut(element, nom, defaut=0.0):
    valeur = element.attrib.get(nom)
    if valeur is None:
        return defaut
    try:
        return float(valeur)
    except ValueError:
        return None


def _rects_numeriques(racine):
    for element in racine.iter():
        if element.tag.split("}")[-1] != "rect":
            continue
        x = _nombre_attribut(element, "x", 0.0)
        y = _nombre_attribut(element, "y", 0.0)
        largeur = _nombre_attribut(element, "width", 0.0)
        hauteur = _nombre_attribut(element, "height", 0.0)
        if None in (x, y, largeur, hauteur) or largeur <= 0 or hauteur <= 0:
            continue
        yield element, x, y, largeur, hauteur


def _boites_noeuds(racine):
    boites = []
    for groupe in racine.iter():
        if groupe.tag.split("}")[-1] != "g" or not groupe.attrib.get("data-node-id"):
            continue
        rects = list(_rects_numeriques(groupe))
        if not rects:
            continue
        x = min(r[1] for r in rects)
        y = min(r[2] for r in rects)
        droite = max(r[1] + r[3] for r in rects)
        bas = max(r[2] + r[4] for r in rects)
        boites.append((groupe.attrib["data-node-id"], x, y, droite - x, bas - y))
    return boites


def _chevauche(a, b) -> bool:
    return (a[1] < b[1] + b[3] - 1 and b[1] < a[1] + a[3] - 1
            and a[2] < b[2] + b[4] - 1 and b[2] < a[2] + a[4] - 1)


def _contient(a, b) -> bool:
    return (a[1] <= b[1] + 1 and a[2] <= b[2] + 1
            and a[1] + a[3] >= b[1] + b[3] - 1 and a[2] + a[4] >= b[2] + b[4] - 1)


def _problemes_geometrie(svg: str) -> list[str]:
    """Refuse un SVG dont les nœuds, textes ou zones sortent du viewBox ou se chevauchent."""
    try:
        racine = ET.fromstring(svg)
    except ET.ParseError:
        return ["SVG illisible"]
    correspondance = re.match(
        r"\s*(-?[0-9.]+)\s+(-?[0-9.]+)\s+([0-9.]+)\s+([0-9.]+)",
        racine.attrib.get("viewBox") or "")
    if not correspondance:
        return ["viewBox absent ou invalide"]
    x0, y0, largeur, hauteur = (float(valeur) for valeur in correspondance.groups())
    if largeur <= 0 or hauteur <= 0:
        return ["viewBox vide"]

    problemes = []
    boites = _boites_noeuds(racine)
    if not boites:
        problemes.append("aucun nœud avec une boîte")
    for ident, x, y, w, h in boites:
        if x < x0 - 1 or y < y0 - 1 or x + w > x0 + largeur + 1 or y + h > y0 + hauteur + 1:
            problemes.append(f"nœud {ident} hors viewBox")
    for index, boite in enumerate(boites):
        for autre in boites[index + 1:]:
            if _chevauche(boite, autre) and not _contient(boite, autre) and not _contient(autre, boite):
                problemes.append(f"nœuds {boite[0]} et {autre[0]} se chevauchent")
    for element, x, y, w, h in _rects_numeriques(racine):
        if x < x0 - 1 or y < y0 - 1 or x + w > x0 + largeur + 1 or y + h > y0 + hauteur + 1:
            problemes.append("rectangle hors viewBox")
    for element in racine.iter():
        if element.tag.split("}")[-1] != "text":
            continue
        x = _nombre_attribut(element, "x", None)
        y = _nombre_attribut(element, "y", None)
        if y is not None and (y < y0 - 1 or y > y0 + hauteur + 1):
            problemes.append("texte hors viewBox")
        if x is not None and (x < x0 - 40 or x > x0 + largeur + 40):
            problemes.append("texte hors viewBox")
    return list(dict.fromkeys(problemes))[:6]


def _problemes_plan(svg: str, plan: dict) -> list[str]:
    """Le plan fixe la liste exacte des nœuds : l'auteur ne peut pas en supprimer."""
    try:
        racine = ET.fromstring(svg)
    except ET.ParseError:
        return ["SVG illisible"]
    ids_svg = {groupe.attrib["data-node-id"] for groupe in racine.iter()
               if groupe.tag.split("}")[-1] == "g" and groupe.attrib.get("data-node-id")}
    ids_plan = {str(boite.get("id")) for boite in plan.get("boites") or () if boite.get("id")}
    problemes = []
    manquants = sorted(ids_plan - ids_svg)
    en_trop = sorted(ids_svg - ids_plan)
    if manquants:
        problemes.append("nœuds manquants : " + ", ".join(manquants))
    if en_trop:
        problemes.append("nœuds hors plan : " + ", ".join(en_trop))
    return problemes


async def authoriser(schema, modele=None) -> dict | None:
    """Produit un artefact SVG design-diagram, ou None si l'auteur/export échoue."""
    if not isinstance(schema, dict) or schema.get("type") not in {"architecture", "flux", "sequence", "data-model"}:
        return None
    schema_auteur = _reduire(schema)
    plan = fallback.plan(schema_auteur)
    cle, empreinte = _cle(schema)
    if cle in _CACHE:
        return _CACHE[cle]
    en_cache = _lire_cache(cle, plan)
    if en_cache is not None:
        _CACHE[cle] = en_cache
        return en_cache
    configure = modele
    if configure is None:
        try:
            configure = agent.modele()
        except Exception:
            journal.warning("design-diagram : modèle indisponible", exc_info=True)
            return None
    try:
        a = Agent(model=configure, system_prompt=PROMPT, tools=[], callback_handler=None)
        contenu = _contenu(schema_auteur, plan)
        svg = ""
        for tentative in range(1):
            resultat = await a.invoke_async(contenu, structured_output_model=HTMLDiagramme)
            html = getattr(getattr(resultat, "structured_output", None), "html", "")
            if not html or "<svg" not in html.lower():
                return None
            if re.search(r"<(script|foreignObject|iframe)\b|\son[a-z]+\s*=", html, re.IGNORECASE):
                journal.warning("design-diagram : HTML actif refusé")
                return None
            svg = diagram_export.export_svg_document(
                html, Path("design-diagram-chat.html"), system_fonts=True)
            svg = svg.replace('<?xml version="1.0" encoding="UTF-8"?>\n', "")
            if _valider_svg(svg):
                problemes = _problemes_geometrie(svg)
                if not problemes and plan:
                    problemes = _problemes_plan(svg, plan)
                if not problemes:
                    break
            else:
                noeuds, aretes = _compter_svg(svg)
                problemes = [f"{noeuds} nœuds et {aretes} arêtes (maximum 9 et 12)"]
            journal.warning("design-diagram : sortie refusée (%s)", " ; ".join(problemes))
            contenu = (contenu + "\n\nLa sortie précédente est refusée : "
                       + " ; ".join(problemes[:6])
                       + ". Corrige la mise en page : tout doit tenir dans le viewBox avec 24 px de marge, "
                       "les nœuds ne se chevauchent pas, les textes et la légende restent dans le viewBox. "
                       "Réponds avec un HTML corrigé.")
        if (not _valider_svg(svg) or _problemes_geometrie(svg)
                or (plan is not None and _problemes_plan(svg, plan))):
            return None
        dimensions = re.search(r'viewBox="0 0 ([0-9.]+) ([0-9.]+)"', svg)
        largeur = int(float(dimensions.group(1))) if dimensions else 960
        hauteur = int(float(dimensions.group(2))) if dimensions else 600
        tete = re.search(r"<svg\b[^>]*>", svg)
        if tete and "width=" not in tete.group(0):
            svg = svg.replace(tete.group(0), tete.group(0).replace(
                "<svg", f'<svg width="{largeur}" height="{hauteur}"', 1), 1)
        artefact = {
            "type": "design-diagram", "mode": "auteur", "version": "1.0",
            "titre": str(schema.get("titre") or "Diagramme"),
            "hash": empreinte, "largeur": largeur, "hauteur": hauteur, "svg": svg,
            "budget_reduit": schema_auteur.get("_budget_reduit"),
        }
        _CACHE[cle] = artefact
        _ecrire_cache(cle, artefact)
        return artefact
    except Exception:
        journal.warning("design-diagram : authoring ou export impossible", exc_info=True)
        return None


async def enrichir_reponse(reponse: dict) -> dict:
    """Compile chaque schéma : éditorial par défaut, rapide sur demande, repli déterministe."""
    if not isinstance(reponse, dict):
        return reponse
    schemas = reponse.get("schemas") or ()
    editorial = _mode_editorial()
    artefacts = []
    for schema in schemas:
        artefact = None
        # Le rendu de séquence est plus fiable avec ses lignes de vie déterministes :
        # l'authoring éditorial est réservé aux architectures et aux flux.
        if editorial and isinstance(schema, dict) and schema.get("type") != "sequence":
            try:
                artefact = await asyncio.wait_for(authoriser(schema), timeout=_delai_auteur())
            except Exception:
                journal.warning("design-diagram : auteur interrompu, repli déterministe", exc_info=True)
                artefact = None
        if artefact is None:
            artefact = fallback.compiler(schema)
        if artefact:
            artefacts.append(artefact)
    if artefacts:
        reponse["diagrammes"] = artefacts
    return reponse


def _mode_editorial() -> bool:
    return str(os.environ.get(_MODE_ENV) or "").strip().lower() not in _MODES_RAPIDES


def _delai_auteur() -> float:
    try:
        return max(0.1, min(60.0, float(os.environ.get(_TIMEOUT_ENV) or _DELAI_AUTEUR)))
    except ValueError:
        return _DELAI_AUTEUR
