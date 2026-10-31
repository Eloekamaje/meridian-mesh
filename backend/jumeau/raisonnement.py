"""Trace de raisonnement auditable : plan, spécialistes, preuves, alternatives, abstention.

Ce module ne produit pas de chaîne de pensée privée. Il expose uniquement les étapes vérifiables :
quel spécialiste a été mobilisé, avec quel statut, quelles preuves, quelles alternatives et quelle
décision a été proposée. La trace est stable et fingerprintée pour l'audit et le rejeu.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from collections.abc import Mapping
from typing import Any

__all__ = ["TraceRaisonnement", "construire"]


def _texte(valeur, maximum=1000) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def _ids(valeurs) -> tuple[str, ...]:
    resultat = []
    for valeur in valeurs or ():
        if isinstance(valeur, Mapping):
            valeur = valeur.get("id")
        texte = _texte(valeur, 160)
        if texte and texte not in resultat:
            resultat.append(texte)
    return tuple(resultat)


def _trace_id(question, contexte_fingerprint, composition, etapes) -> str:
    charge = json.dumps(
        {"question": question, "contexte": contexte_fingerprint,
         "methodes": composition.get("methodes") or [],
         "specialistes": composition.get("specialistes") or [],
         "etapes": [(e.get("specialiste"), e.get("statut")) for e in etapes]},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "tr-" + hashlib.sha256(charge.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class TraceRaisonnement:
    trace_id: str
    question: str
    profil_id: str
    autorite: str
    contexte_fingerprint: str
    composition: dict = field(default_factory=dict)
    etapes: tuple[dict, ...] = ()
    preuves: tuple[str, ...] = ()
    alternatives: tuple[dict, ...] = ()
    contradictions: tuple[str, ...] = ()
    incertitudes: tuple[str, ...] = ()
    decision_support: dict = field(default_factory=dict)
    limites: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "question": self.question,
            "profil_id": self.profil_id,
            "autorite": self.autorite,
            "contexte_fingerprint": self.contexte_fingerprint,
            "composition": dict(self.composition),
            "etapes": [dict(etape) for etape in self.etapes],
            "preuves": list(self.preuves),
            "alternatives": [dict(option) for option in self.alternatives],
            "contradictions": list(self.contradictions),
            "incertitudes": list(self.incertitudes),
            "decision_support": dict(self.decision_support),
            "limites": list(self.limites),
        }


def construire(question: str, profil: Any, plan: Any, contexte: Any, dossier: Mapping,
               reponse: Mapping | None = None) -> TraceRaisonnement:
    """Construit la trace vérifiable d'une réponse, sans exposer de raisonnement caché."""
    if not isinstance(dossier, Mapping):
        raise TypeError("dossier : objet attendu")
    reponse = reponse if isinstance(reponse, Mapping) else {}
    contexte_dict = contexte.as_dict() if hasattr(contexte, "as_dict") else (contexte or {})
    composition = {
        "methodes": [getattr(m, "id", str(m)) for m in getattr(plan, "methodes", ())],
        "competences": [getattr(c, "id", str(c)) for c in getattr(plan, "competences", ())],
        "specialistes": list(getattr(plan, "specialistes_socle", ())),
    }
    etapes = []
    for resultat in dossier.get("specialistes") or ():
        if not isinstance(resultat, Mapping):
            continue
        etapes.append({
            "specialiste": _texte(resultat.get("specialiste"), 80),
            "statut": _texte(resultat.get("statut"), 20),
            "propositions": len(resultat.get("propositions") or ()),
            "limites": [_texte(valeur, 300) for valeur in resultat.get("limites") or ()],
        })
    faits = [fait for fait in dossier.get("propositions") or () if isinstance(fait, Mapping)]
    contradictions = [
        _texte(fait.get("titre"), 240) for fait in faits
        if "contradiction" in _texte(fait.get("titre"), 240).lower()
        or "contradict" in _texte(fait.get("resume"), 1000).lower()
    ]
    incertitudes = [_texte(fait.get("titre"), 240) for fait in faits
                    if _texte(fait.get("type"), 40).upper() in {"QUESTION", "HYPOTHESE"}]
    preuves = _ids([preuve for fait in faits for preuve in (fait.get("preuves") or ())])
    decision = reponse.get("decision_support") if isinstance(reponse.get("decision_support"), Mapping) else {}
    options = tuple(decision.get("options") or ())
    profil_id = _texte(getattr(profil, "id", ""), 80) or "generaliste"
    autorite = _texte(getattr(profil, "autorite", "lecture"), 20) or "lecture"
    fingerprint = _texte(contexte_dict.get("fingerprint"), 128) if isinstance(contexte_dict, Mapping) else ""
    limites = tuple(dict.fromkeys(
        [_texte(valeur, 500) for valeur in (contexte_dict.get("limites") or ())]
        + [_texte(valeur, 500) for valeur in (dossier.get("limites") or ())]
        + [limite for etape in etapes for limite in etape.get("limites", ())]))
    return TraceRaisonnement(
        trace_id=_trace_id(question, fingerprint, composition, etapes),
        question=_texte(question, 4000),
        profil_id=profil_id,
        autorite=autorite,
        contexte_fingerprint=fingerprint,
        composition=composition,
        etapes=tuple(etapes),
        preuves=preuves,
        alternatives=options,
        contradictions=tuple(dict.fromkeys(contradictions)),
        incertitudes=tuple(dict.fromkeys(incertitudes)),
        decision_support=dict(decision),
        limites=limites,
    )
