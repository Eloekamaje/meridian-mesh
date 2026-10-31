"""Context Pack borné : ce qui entre dans une réponse, ce qui reste dehors, et son empreinte.

Le pack ne contient ni prompt complet ni secret : il sélectionne des propositions, preuves,
entités et limites déjà produites par le dossier. Il est borné, déterministe et fingerprinté pour
qu'une réponse puisse être rejouée et comparée.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

__all__ = ["ContextePack", "construire"]

_MAX_TEXTE = 500
_RE_SECRET = re.compile(
    r"(?i)(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|client[_-]?secret|"
    r"password|passwd|secret|token)\s*[:=]\s*['\"]?[A-Za-z0-9_./+~-]{6,}"
)


def _texte(valeur, maximum=_MAX_TEXTE) -> str:
    texte = " ".join(str(valeur or "").split())[:maximum]
    return _RE_SECRET.sub("***", texte)


def _liste(valeur) -> list:
    if valeur is None:
        return []
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return list(valeur)
    return [valeur]


def _ids(valeurs) -> tuple[str, ...]:
    resultat = []
    for valeur in _liste(valeurs):
        if isinstance(valeur, Mapping):
            valeur = valeur.get("id")
        texte = _texte(valeur, 160)
        if texte and texte not in resultat:
            resultat.append(texte)
    return tuple(resultat)


def _faits(dossier: Mapping) -> list[dict]:
    resultat = []
    for fait in dossier.get("propositions") or ():
        if not isinstance(fait, Mapping):
            continue
        resultat.append({
            "specialiste": _texte(fait.get("specialiste"), 80),
            "type": _texte(fait.get("type"), 40).upper(),
            "titre": _texte(fait.get("titre"), 240),
            "resume": _texte(fait.get("resume"), 1000),
            "preuves": list(_ids(fait.get("preuves"))),
            "confiance": float(fait.get("confiance") or 0.0),
        })
    return resultat


def _entites(dossier: Mapping) -> tuple[str, ...]:
    valeurs = []
    for fait in dossier.get("propositions") or ():
        if isinstance(fait, Mapping):
            donnees = fait.get("donnees")
            if isinstance(donnees, Mapping):
                for cle in ("twin_id", "application_id", "situation_id", "source", "cible"):
                    valeur = donnees.get(cle)
                    if valeur:
                        valeurs.append(valeur)
    return _ids(valeurs)


def _fingerprint(tenant: str, question: str, profil_id: str, faits, preuves) -> str:
    charge = json.dumps(
        {"tenant": tenant, "question": question, "profil": profil_id,
         "faits": [(f["type"], f["titre"], f["resume"]) for f in faits],
         "preuves": list(preuves)},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(charge.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ContextePack:
    tenant: str
    question: str
    profil_id: str
    autorite: str
    entites: tuple[str, ...] = ()
    faits: tuple[dict, ...] = ()
    preuves: tuple[str, ...] = ()
    contraintes: tuple[str, ...] = ()
    inconnues: tuple[str, ...] = ()
    fingerprint: str = ""
    budget: dict = field(default_factory=dict)
    limites: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "tenant": self.tenant,
            "question": self.question,
            "profil_id": self.profil_id,
            "autorite": self.autorite,
            "entites": list(self.entites),
            "faits": [dict(fait) for fait in self.faits],
            "preuves": list(self.preuves),
            "contraintes": list(self.contraintes),
            "inconnues": list(self.inconnues),
            "fingerprint": self.fingerprint,
            "budget": dict(self.budget),
            "limites": list(self.limites),
        }


def construire(question: str, profil: Any, dossier: Mapping, *,
               max_faits: int = 12, max_preuves: int = 20,
               max_entites: int = 20) -> ContextePack:
    """Sélectionne et borne le contexte ; lève sur un dossier non mapping."""
    if not isinstance(dossier, Mapping):
        raise TypeError("dossier : objet attendu")
    try:
        budget_faits = max(1, min(int(max_faits), 100))
        budget_preuves = max(1, min(int(max_preuves), 200))
        budget_entites = max(1, min(int(max_entites), 200))
    except (TypeError, ValueError) as exc:
        raise ValueError("budgets de contexte invalides") from exc
    faits = sorted(
        _faits(dossier),
        key=lambda fait: (-fait["confiance"], fait["type"], fait["titre"]))[:budget_faits]
    preuves = _ids([preuve for fait in faits for preuve in fait["preuves"]])[:budget_preuves]
    entites = _entites(dossier)[:budget_entites]
    contraintes = tuple(_texte(valeur, 500) for valeur in _liste(dossier.get("limites"))
                        if _texte(valeur, 500))
    inconnues = tuple(fait["titre"] for fait in faits
                      if fait["type"] in {"QUESTION", "HYPOTHESE"})
    profil_id = _texte(getattr(profil, "id", ""), 80) or "generaliste"
    autorite = _texte(getattr(profil, "autorite", "lecture"), 20) or "lecture"
    tenant = _texte(dossier.get("tenant"), 128) or "local"
    limites = []
    if len(_faits(dossier)) > budget_faits:
        limites.append(f"faits tronqués à {budget_faits}")
    if len(_ids([p for f in _faits(dossier) for p in f["preuves"]])) > budget_preuves:
        limites.append(f"preuves tronquées à {budget_preuves}")
    if not faits:
        limites.append("aucun fait disponible : contexte borné et vide")
    return ContextePack(
        tenant=tenant,
        question=_texte(question, 4000),
        profil_id=profil_id,
        autorite=autorite,
        entites=entites,
        faits=tuple(faits),
        preuves=preuves,
        contraintes=contraintes,
        inconnues=inconnues,
        fingerprint=_fingerprint(tenant, _texte(question, 4000), profil_id, faits, preuves),
        budget={"faits": budget_faits, "preuves": budget_preuves, "entites": budget_entites},
        limites=tuple(limites),
    )
