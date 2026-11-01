"""Résolveur de contexte : surface, entités, domaine, temps, utilisateur et permissions.

Le résolveur ne devine jamais un identifiant : chaque sélection est explicite, validée puis
tracée dans un :class:`ContexteResolu`. Il expose aussi une divulgation progressive du Context
Pack (résumé, détail, expansion ciblée) sans jamais fabriquer de fait ni modifier le pack source.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import date as _Date, datetime as _DateTime
import re
from typing import Any
import unicodedata

from jumeau import contexte as contexte_module

__all__ = [
    "ContexteInvalide",
    "ContexteResolu",
    "SURFACES",
    "SurfaceInconnue",
    "construire_pack",
    "detail",
    "expandre",
    "fingerprint",
    "resoudre",
    "resume",
]

SURFACES = ("atlas", "twin", "situation", "work", "global")

_SURFACES = frozenset(SURFACES)
_SELECTEURS = {
    "atlas": frozenset({"twin_id", "domaine"}),
    "twin": frozenset({"twin_id"}),
    "situation": frozenset({"situation_id"}),
    "work": frozenset({"work_id"}),
    "global": frozenset(),
}
_REQUIS = {"twin": "twin_id", "situation": "situation_id", "work": "work_id"}
_MAX_ID = 200
_MAX_TENANT = 64
_MAX_TEXTE = 320
_RE_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")
_RE_ESPACE = re.compile(r"\s")
_RE_TENANT = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


class ContexteInvalide(ValueError):
    """Un paramètre de contexte est manquant, contradictoire ou hors surface."""


class SurfaceInconnue(ContexteInvalide):
    """La surface demandée ne fait pas partie de :data:`SURFACES`."""


@dataclass(frozen=True)
class ContexteResolu:
    """Contexte explicitement résolu, prêt à borner un Context Pack."""

    tenant: str
    surface: str
    entites: tuple[str, ...] = ()
    domaine: str | None = None
    periode: str | None = None
    utilisateur: str | None = None
    scope: str = "tenant"
    source: str = ""

    def as_dict(self) -> dict:
        """Rend le contexte sérialisable en JSON, sans objet interne."""
        return {
            "tenant": self.tenant,
            "surface": self.surface,
            "entites": list(self.entites),
            "domaine": self.domaine,
            "periode": self.periode,
            "utilisateur": self.utilisateur,
            "scope": self.scope,
            "source": self.source,
        }


def _identifiant(valeur: Any, champ: str, *, obligatoire: bool = True) -> str | None:
    if valeur is None:
        if obligatoire:
            raise ContexteInvalide(f"{champ} obligatoire pour cette surface")
        return None
    if not isinstance(valeur, str):
        raise ContexteInvalide(f"{champ} : chaîne attendue")
    texte = valeur.strip()
    if not texte:
        raise ContexteInvalide(f"{champ} ne peut pas être vide")
    if len(texte) > _MAX_ID:
        raise ContexteInvalide(f"{champ} : {_MAX_ID} caractères au maximum")
    if _RE_ESPACE.search(texte) or _RE_CONTROLE.search(texte):
        raise ContexteInvalide(f"{champ} : identifiant invalide")
    return texte


def _tenant(valeur: Any) -> str:
    """Valide et canonise le tenant comme un slug, sans repli silencieux."""
    if not isinstance(valeur, str):
        raise ContexteInvalide("tenant_id : chaîne attendue")
    texte = unicodedata.normalize("NFKD", valeur.strip())
    texte = "".join(caractere for caractere in texte if not unicodedata.combining(caractere)).lower()
    if not texte:
        raise ContexteInvalide("tenant_id ne peut pas être vide")
    if len(texte) > _MAX_TENANT:
        raise ContexteInvalide(f"tenant_id : {_MAX_TENANT} caractères au maximum")
    if _RE_TENANT.fullmatch(texte) is None:
        raise ContexteInvalide(
            "tenant_id : slug attendu (minuscules, chiffres, séparateurs . _ -, sans séparateur aux extrémités)")
    return texte


def _texte_optionnel(valeur: Any, champ: str) -> str | None:
    if valeur is None:
        return None
    if not isinstance(valeur, str):
        raise ContexteInvalide(f"{champ} : chaîne attendue")
    texte = valeur.strip()
    if not texte:
        raise ContexteInvalide(f"{champ} ne peut pas être vide")
    if len(texte) > _MAX_TEXTE:
        raise ContexteInvalide(f"{champ} : {_MAX_TEXTE} caractères au maximum")
    if _RE_CONTROLE.search(texte):
        raise ContexteInvalide(f"{champ} : caractère de contrôle interdit")
    return texte


def _surface(valeur: Any) -> str:
    if not isinstance(valeur, str):
        raise SurfaceInconnue("surface : chaîne attendue")
    texte = valeur.strip().lower()
    if texte not in _SURFACES:
        raise SurfaceInconnue(
            f"surface inconnue : {valeur!r} (attendues : {', '.join(SURFACES)})")
    return texte


def _periode(valeur: Any) -> str | None:
    """Valide une date ISO (ou un instant ISO) et rend une date ``AAAA-MM-JJ``."""
    if valeur is None:
        return None
    if isinstance(valeur, _DateTime):
        return valeur.date().isoformat()
    if isinstance(valeur, _Date):
        return valeur.isoformat()
    if not isinstance(valeur, str):
        raise ContexteInvalide("date : date ISO attendue")
    texte = valeur.strip()
    if not texte:
        raise ContexteInvalide("date ne peut pas être vide")
    try:
        return _Date.fromisoformat(texte).isoformat()
    except ValueError:
        try:
            return _DateTime.fromisoformat(texte.replace("Z", "+00:00")).date().isoformat()
        except ValueError as exc:
            raise ContexteInvalide(
                "date : date ISO attendue au format AAAA-MM-JJ") from exc


def _source_selection(surface: str, twin_id: str | None, situation_id: str | None,
                      work_id: str | None, domaine: str | None) -> str:
    """Nomme le sélecteur explicite qui a produit le contexte."""
    if surface == "global":
        return "global"
    if surface == "atlas":
        selecteurs = [nom for nom, valeur in (("twin_id", twin_id), ("domaine", domaine)) if valeur]
        return "+".join(selecteurs) if selecteurs else "atlas"
    if surface == "twin":
        return "twin_id"
    if surface == "situation":
        return "situation_id"
    return "work_id" if work_id else surface


def resoudre(tenant_id: str, surface: str, *, twin_id: str | None = None,
             situation_id: str | None = None, work_id: str | None = None,
             domaine: str | None = None, date: str | _Date | _DateTime | None = None,
             utilisateur: str | None = None, perimetre: str | None = None) -> ContexteResolu:
    """Résout un contexte à partir d'une surface et d'un identifiant explicitement fourni.

    Aucun identifiant n'est déduit d'un autre champ : ``twin`` exige ``twin_id``,
    ``situation`` exige ``situation_id`` et ``work`` exige ``work_id``. ``global``
    n'accepte aucun sélecteur d'entité ; ``atlas`` accepte ``domaine`` et/ou
    ``twin_id``. Un identifiant absent, vide, mal formé ou rattaché à une autre
    surface lève :class:`ContexteInvalide`.
    """
    tenant = _tenant(tenant_id)
    surf = _surface(surface)
    valeurs = {
        "twin_id": _identifiant(twin_id, "twin_id", obligatoire=False),
        "situation_id": _identifiant(situation_id, "situation_id", obligatoire=False),
        "work_id": _identifiant(work_id, "work_id", obligatoire=False),
    }
    domaine_valide = _texte_optionnel(domaine, "domaine")
    periode = _periode(date)
    utilisateur_valide = _texte_optionnel(utilisateur, "utilisateur")
    perimetre_valide = _texte_optionnel(perimetre, "perimetre")

    if surf in _REQUIS:
        champ = _REQUIS[surf]
        if valeurs[champ] is None:
            raise ContexteInvalide(f"surface {surf} : {champ} obligatoire")

    hors_surface = [
        nom for nom, valeur in valeurs.items()
        if valeur is not None and nom not in _SELECTEURS[surf]
    ]
    if domaine_valide is not None and "domaine" not in _SELECTEURS[surf]:
        hors_surface.append("domaine")
    if hors_surface:
        raise ContexteInvalide(
            f"surface {surf} : sélecteur(s) non applicable(s) : {', '.join(sorted(hors_surface))}")

    entites = tuple(
        valeur for valeur in (valeurs["twin_id"], valeurs["situation_id"], valeurs["work_id"])
        if valeur)
    return ContexteResolu(
        tenant=tenant,
        surface=surf,
        entites=entites,
        domaine=domaine_valide,
        periode=periode,
        utilisateur=utilisateur_valide,
        scope=perimetre_valide or "tenant",
        source=_source_selection(
            surf, valeurs["twin_id"], valeurs["situation_id"], valeurs["work_id"],
            domaine_valide),
    )


def _contexte_dict(contexte: Any) -> dict:
    if isinstance(contexte, ContexteResolu):
        return contexte.as_dict()
    if isinstance(contexte, Mapping):
        resultat = dict(contexte)
    elif hasattr(contexte, "as_dict"):
        resultat = contexte.as_dict()
    else:
        raise ContexteInvalide("contexte : ContexteResolu attendu")
    if not isinstance(resultat, Mapping):
        raise ContexteInvalide("contexte : objet attendu")
    return dict(resultat)


def _pack_dict(pack: Any) -> dict:
    if isinstance(pack, Mapping):
        resultat = dict(pack)
    elif hasattr(pack, "as_dict"):
        resultat = pack.as_dict()
    else:
        raise ContexteInvalide("pack : Context Pack attendu")
    if not isinstance(resultat, Mapping):
        raise ContexteInvalide("pack : objet attendu")
    interne = resultat.get("pack")
    if isinstance(interne, Mapping):
        return dict(interne)
    if hasattr(interne, "as_dict"):
        return dict(interne.as_dict())
    return dict(resultat)


def _question(contexte: dict) -> str:
    morceaux = [f"surface={contexte.get('surface')}"]
    entites = contexte.get("entites") or ()
    if entites:
        morceaux.append("entités=" + ", ".join(str(valeur) for valeur in entites))
    if contexte.get("domaine"):
        morceaux.append(f"domaine={contexte['domaine']}")
    if contexte.get("periode"):
        morceaux.append(f"période={contexte['periode']}")
    return "Contexte résolu : " + " ; ".join(morceaux)


def construire_pack(contexte: Any, dossier: Mapping, profil: Any, *, max_faits: int = 12,
                    max_preuves: int = 20, max_entites: int = 20,
                    max_tokens: int = 4000, proximite: Mapping | None = None) -> dict:
    """Construit un Context Pack borné pour un contexte résolu.

    Le dossier reste intact. S'il ne porte pas de tenant, une copie reçoit le tenant
    résolu ; s'il porte un autre tenant, la construction est refusée pour empêcher
    tout mélange de périmètres. La question vient du dossier ou, à défaut, du
    contexte lui-même. ``max_tokens`` borne en plus les compteurs faits/preuves/entités ;
    ``proximite`` transmet les scores de graphe optionnels. Les entités résolues servent
    d'ancrage de proximité et les inconnues, contradictions, preuves périmées et le
    caractère partiel du pack sont conservés explicitement.
    """
    contexte_brut = _contexte_dict(contexte)
    tenant = _tenant(contexte_brut.get("tenant"))
    surface = _surface(contexte_brut.get("surface"))
    contexte_brut["tenant"] = tenant
    contexte_brut["surface"] = surface
    if not isinstance(dossier, Mapping):
        raise ContexteInvalide("dossier : objet attendu")
    tenant_dossier = dossier.get("tenant")
    if tenant_dossier:
        try:
            tenant_dossier_normalise = _tenant(tenant_dossier)
        except ContexteInvalide as exc:
            raise ContexteInvalide("dossier hors du tenant résolu") from exc
        if tenant_dossier_normalise != tenant:
            raise ContexteInvalide("dossier hors du tenant résolu")
        donnees = dossier if tenant_dossier == tenant else {**dossier, "tenant": tenant}
    else:
        donnees = {**dossier, "tenant": tenant}
    question = dossier.get("question")
    if not isinstance(question, str) or not question.strip():
        question = _question(contexte_brut)
    entites_resolues = tuple(
        str(entite) for entite in (contexte_brut.get("entites") or ()) if str(entite))
    pack = contexte_module.construire(
        question, profil, donnees, max_faits=max_faits, max_preuves=max_preuves,
        max_entites=max_entites, max_tokens=max_tokens, entites=entites_resolues,
        proximite=proximite)
    return {
        "contexte": dict(contexte_brut),
        "pack": pack.as_dict(),
        "surface": surface,
        "periode": contexte_brut.get("periode"),
    }


def _faits(pack: dict) -> list:
    faits = pack.get("faits") or ()
    return list(faits) if isinstance(faits, Iterable) and not isinstance(faits, (str, bytes)) else []


def _preuves(pack: dict) -> list:
    preuves = pack.get("preuves") or ()
    return list(preuves) if isinstance(preuves, Iterable) and not isinstance(preuves, (str, bytes)) else []


def _fait_compact(fait: Any) -> dict:
    if not isinstance(fait, Mapping):
        return {"resume": str(fait)[:200]}
    resume = " ".join(str(fait.get("resume") or "").split())[:200]
    return {
        "specialiste": fait.get("specialiste", ""),
        "type": fait.get("type", ""),
        "titre": fait.get("titre", ""),
        "resume": resume,
        "preuves": list(fait.get("preuves") or ()),
        "confiance": fait.get("confiance", 0.0),
    }


def fingerprint(pack: Any) -> str:
    """Rend l'empreinte déjà portée par le pack, sans en recalculer une autre."""
    resultat = _pack_dict(pack)
    empreinte = resultat.get("fingerprint")
    if not isinstance(empreinte, str) or not empreinte:
        raise ContexteInvalide("pack : fingerprint absent")
    return empreinte


def resume(pack: Any, limite: int = 5) -> dict:
    """Rend une vue courte du pack : quelques faits compacts et son empreinte."""
    resultat = deepcopy(_pack_dict(pack))
    try:
        maximum = max(0, min(int(limite), 100))
    except (TypeError, ValueError) as exc:
        raise ContexteInvalide("limite : entier attendu") from exc
    faits = _faits(resultat)
    resultat["faits"] = [_fait_compact(fait) for fait in faits[:maximum]]
    resultat["total_faits"] = len(faits)
    resultat["limite"] = maximum
    resultat["tronque"] = len(faits) > maximum
    resultat["fingerprint"] = fingerprint(pack)
    return resultat


def detail(pack: Any) -> dict:
    """Rend tous les faits et preuves du pack, sans troncature de divulgation."""
    resultat = deepcopy(_pack_dict(pack))
    resultat["fingerprint"] = fingerprint(pack)
    return resultat


def _ids_demandes(ids: Any) -> list[str]:
    if ids is None:
        return []
    if isinstance(ids, str):
        valeurs = [ids]
    elif isinstance(ids, Mapping):
        valeurs = list(ids)
    elif isinstance(ids, Iterable):
        valeurs = list(ids)
    else:
        valeurs = [ids]
    resultat: list[str] = []
    for valeur in valeurs:
        if isinstance(valeur, Mapping):
            valeur = valeur.get("id")
        texte = str(valeur or "").strip()
        if texte and texte not in resultat:
            resultat.append(texte)
    return resultat


def _fait_concerne(fait: Any, demandes: set[str]) -> bool:
    if not isinstance(fait, Mapping):
        return str(fait) in demandes
    for champ in ("id", "fact_id", "preuve_id", "evidence_id"):
        if str(fait.get(champ) or "") in demandes:
            return True
    preuves = fait.get("preuves") or ()
    if isinstance(preuves, (str, bytes)):
        preuves = [preuves]
    return any(str(preuve) in demandes for preuve in preuves)


def expandre(pack: Any, ids: Any) -> dict:
    """Rend uniquement les faits et preuves qui correspondent aux identifiants demandés.

    Les identifiants inconnus sont ignorés : aucune preuve ni aucun fait n'est créé.
    Le pack source n'est jamais modifié et conserve son empreinte.
    """
    resultat = deepcopy(_pack_dict(pack))
    demandes = _ids_demandes(ids)
    ensemble = set(demandes)
    resultat["faits"] = [fait for fait in _faits(resultat) if _fait_concerne(fait, ensemble)]
    resultat["preuves"] = [preuve for preuve in _preuves(resultat) if str(preuve) in ensemble]
    resultat["fingerprint"] = fingerprint(pack)
    return resultat
