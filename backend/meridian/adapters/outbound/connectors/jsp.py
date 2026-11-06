"""Sidecar JSP : extraction structurelle des pages, sans exécution ni Java généré."""
from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from meridian.domain.code_index import CouvertureFichier, Observation

__all__ = ["JspSidecar"]

PROVIDER = "jsp"
PARSER = "jsp-structural"
PARSER_VERSION = "1"
EXTENSIONS = (".jsp", ".jspf", ".tag")
LANGAGE = "jsp"


def _balise(nom: str) -> re.Pattern:
    return re.compile(rf"<{nom}(?=[\s/>])(?P<attrs>(?:[^>\"']|\"[^\"]*\"|'[^']*')*)>", re.I | re.S)


_MOTIFS = (
    ("jsp_include", re.compile(r"<%\s*@\s*include\b(?P<attrs>.*?)%>", re.I | re.S)),
    ("jsp_taglib", re.compile(r"<%\s*@\s*taglib\b(?P<attrs>.*?)%>", re.I | re.S)),
    ("jsp_include", _balise(r"jsp:include")),
    ("jsp_include", _balise(r"s:include")),
    ("jsp_forward", _balise(r"jsp:forward")),
    ("jsp_forward", _balise(r"s:forward")),
    ("jsp_include", _balise(r"c:import")),
    ("jsp_link", _balise(r"c:url")),
    ("jsp_link", _balise(r"c:redirect")),
    ("jsp_form", _balise(r"form")),
    ("jsp_form", _balise(r"html:form")),
    ("jsp_form", _balise(r"s:form")),
    ("jsp_bean", _balise(r"jsp:useBean")),
    ("jsp_link", _balise(r"a")),
    ("jsp_link", _balise(r"area")),
    ("jsp_link", _balise(r"html:link")),
    ("jsp_link", _balise(r"s:a")),
    ("jsp_link", _balise(r"s:url")),
)
_MOTIF_ATTRIBUT = re.compile(
    r"([A-Za-z_:][\w:.-]*)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'>]+))", re.S)
_MOTIF_COMMENTAIRE = re.compile(r"<%--.*?--%>", re.S)
_MOTIF_COMMENTAIRE_HTML = re.compile(r"<!--.*?-->", re.S)
_MOTIF_SCRIPTLET = re.compile(r"<%(?!@).*?%>", re.S)


def _ligne(texte: str, position: int) -> int:
    return texte.count("\n", 0, max(0, position)) + 1


def _masquer(texte: str, motif: re.Pattern) -> str:
    return motif.sub(lambda trouve: re.sub(r"[^\n]", " ", trouve.group(0)), texte)


def _masquer_code(texte: str) -> str:
    texte = _masquer(_masquer(texte, _MOTIF_COMMENTAIRE), _MOTIF_COMMENTAIRE_HTML)
    return _masquer(texte, _MOTIF_SCRIPTLET)


def _attributs(brut: str) -> dict:
    resultat = {}
    for trouve in _MOTIF_ATTRIBUT.finditer(brut or ""):
        valeur = next((v for v in trouve.groups()[1:] if v is not None), "")
        resultat[trouve.group(1).lower()] = valeur.strip()
    return resultat


def _cible(kind: str, attributs: dict) -> str:
    if kind == "jsp_form":
        return attributs.get("action", "")
    if kind == "jsp_include":
        return (attributs.get("file") or attributs.get("page") or attributs.get("url")
                or attributs.get("value") or "")
    if kind == "jsp_forward":
        return attributs.get("page") or attributs.get("action") or ""
    if kind == "jsp_link":
        return (attributs.get("href") or attributs.get("value") or attributs.get("url")
                or attributs.get("action") or attributs.get("page") or "")
    return ""


def _symbole(kind: str, attributs: dict, cible: str) -> str:
    if kind == "jsp_taglib":
        return attributs.get("prefix") or attributs.get("uri") or ""
    if kind == "jsp_form":
        return attributs.get("name") or attributs.get("id") or cible
    if kind == "jsp_bean":
        return attributs.get("id") or attributs.get("class") or cible
    return cible


def _observer(fichier: str, texte: str, debut_position: int, fin_position: int, kind: str,
              attributs: dict) -> Observation:
    debut = _ligne(texte, debut_position)
    fin = _ligne(texte, max(debut_position, fin_position - 1))
    cible = _cible(kind, attributs)
    attributs = dict(attributs)
    if cible and kind in {"jsp_form", "jsp_include", "jsp_forward", "jsp_link"}:
        attributs.setdefault("target", cible)
    symbole = _symbole(kind, attributs, cible) or f"{kind}:{debut}"
    return Observation(
        provider=PROVIDER, parser=PARSER, parser_version=PARSER_VERSION, file=fichier,
        language=LANGAGE, kind=kind, symbol=symbole, start=debut, end=fin,
        attributes=attributs, confidence=1.0, status="extracted",
    )


def _extraire(fichier: str, texte: str) -> list[Observation]:
    masque = _masquer_code(texte)
    trouvailles = []
    for kind, motif in _MOTIFS:
        for trouve in motif.finditer(masque):
            trouvailles.append((trouve.start(), trouve.end(), kind, _attributs(trouve.group("attrs"))))
    trouvailles.sort(key=lambda item: (item[0], item[1], item[2]))
    return [_observer(fichier, masque, debut, fin, kind, attributs)
            for debut, fin, kind, attributs in trouvailles]


def _resoudre(racine: str, fichier: str) -> Path:
    chemin = Path(fichier)
    return chemin if chemin.is_absolute() else Path(racine) / chemin


def _relatif(racine: str, chemin: Path) -> str:
    try:
        return chemin.resolve().relative_to(Path(racine).resolve()).as_posix()
    except (OSError, ValueError):
        return chemin.as_posix()


def _decouvrir(racine: str) -> list[Path]:
    base = Path(racine)
    if not base.is_dir():
        return []
    return sorted(chemin for chemin in base.rglob("*")
                  if chemin.is_file() and chemin.suffix.lower() in EXTENSIONS)


def _est_jsp(fichier: str) -> bool:
    return Path(fichier).suffix.lower() in EXTENSIONS


def _cibles(racine: str, fichiers: Sequence[str]) -> list[str]:
    if fichiers:
        return sorted({_relatif(racine, _resoudre(racine, fichier)) for fichier in fichiers})
    return [_relatif(racine, chemin) for chemin in _decouvrir(racine)]


def _lire(chemin: Path) -> str:
    return chemin.read_text(encoding="utf-8-sig", errors="replace")


class JspSidecar:
    """Indexe les constructions JSP utiles sans compiler ni exécuter la page."""

    provider = PROVIDER
    extensions = EXTENSIONS
    parser = PARSER
    parser_version = PARSER_VERSION

    def index(self, racine: str, fichiers: Sequence[str] = ()) -> list[Observation]:
        """Observations structurelles des fichiers JSP demandés ou découverts sous la racine."""
        observations = []
        for fichier in _cibles(racine, fichiers):
            if not _est_jsp(fichier):
                continue
            try:
                texte = _lire(_resoudre(racine, fichier))
            except OSError:
                continue
            observations.extend(_extraire(fichier, texte))
        return sorted(observations, key=lambda o: (o.file, o.start, o.kind, o.symbol))

    def couverture(self, racine: str, fichiers: Sequence[str] = ()) -> list[CouvertureFichier]:
        """Une ligne de couverture par fichier, y compris les fichiers illisibles ou non JSP."""
        resultat = []
        for fichier in _cibles(racine, fichiers):
            if not _est_jsp(fichier):
                resultat.append(CouvertureFichier(
                    file=fichier, language="", parser=PARSER, statut="non_supporte",
                    raison="extension JSP non prise en charge"))
                continue
            try:
                _lire(_resoudre(racine, fichier))
            except OSError as erreur:
                resultat.append(CouvertureFichier(
                    file=fichier, language=LANGAGE, parser=PARSER, statut="partiel",
                    raison=f"fichier illisible : {erreur}"))
                continue
            resultat.append(CouvertureFichier(
                file=fichier, language=LANGAGE, parser=PARSER, statut="indexe", raison=""))
        return resultat
