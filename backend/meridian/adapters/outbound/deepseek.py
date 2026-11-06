"""Accès DeepSeek : Search & Fetch web et Vision, avec la clé de l'API existante.

Search/Fetch ne remplacent pas Confluence/SharePoint ni leurs ACL : ce sont des sources web
publiques. Vision sert aux images envoyées explicitement, jamais à un balayage silencieux.
"""
from __future__ import annotations

import base64
import os
import re

import requests

from meridian.domain import capacites

__all__ = ["fetch", "manifestes_web", "search", "vision"]

BASE = "https://api.deepseek.com"
_MODEL = "deepseek-flash"
_MAX_SOURCE = 20_000
_RE_URL = re.compile(r"https?://[^\s<>\"']{8,8192}", re.IGNORECASE)


def disponible() -> bool:
    return bool(os.getenv("DEEPSEEK_API_KEY", "").strip())


def disponible_web() -> bool:
    """Le web public n'est pas activé par défaut dans un profil Bedrock bancaire."""
    provider = os.getenv("WEB_PROVIDER", "auto").strip().lower()
    if provider in {"none", "off", "aucun"}:
        return False
    if provider == "deepseek":
        return disponible()
    return disponible() and os.getenv("JUMEAU_MODELE", "").strip().lower() != "bedrock"


def _cle() -> str:
    cle = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not cle:
        raise RuntimeError("DEEPSEEK_API_KEY absente")
    return cle


def _post(chemin: str, charge: dict, *, timeout: int = 20) -> dict:
    reponse = requests.post(
        BASE + chemin,
        headers={"Authorization": f"Bearer {_cle()}", "Content-Type": "application/json"},
        json=charge, timeout=timeout,
    )
    reponse.raise_for_status()
    return reponse.json()


def search(requete: str, *, nombre: int = 5, contenu: bool = False) -> dict:
    """Recherche web DeepSeek ; résultats bornés, jamais présentés comme connaissance d'entreprise."""
    texte = " ".join(str(requete or "").split())[:128]
    if not texte:
        raise ValueError("requête de recherche vide")
    nombre = max(1, min(50, int(nombre)))
    resultat = _post("/v1/tools/search", {
        "query": texte, "count": nombre, "need_content": bool(contenu)})
    return {
        "requete": texte,
        "resultats": [
            {
                "titre": str(item.get("title") or "")[:300],
                "url": str(item.get("url") or ""),
                "extrait": str(item.get("snippet") or "")[:600],
                "resume": str(item.get("summary") or "")[:1200],
                "contenu": str(item.get("content") or "")[:_MAX_SOURCE] if contenu else "",
                "site": str(item.get("site_name") or "")[:200],
                "date": item.get("date"),
                "autorite": item.get("authority"),
                "score": item.get("rerank_score"),
            }
            for item in (resultat.get("results") or [])[:nombre]
            if item.get("url")
        ],
    }


def fetch(url: str) -> dict:
    """Lit une page publique via DeepSeek Fetch ; l'URL est validée avant l'appel."""
    cible = str(url or "").strip()
    if not _RE_URL.fullmatch(cible):
        raise ValueError("URL HTTP(S) attendue")
    resultat = _post("/v1/tools/fetch", {"url": cible}, timeout=30)
    return {
        "url": cible,
        "titre": str(resultat.get("title") or "")[:300],
        "contenu": str(resultat.get("content") or "")[:_MAX_SOURCE],
    }


def vision(image: bytes, media_type: str = "image/jpeg", question: str = "") -> str:
    """Décrit une image via deepseek-flash Vision ; types OpenAI compatibles."""
    if media_type not in {"image/jpeg", "image/png", "image/gif", "image/webp"}:
        raise ValueError("format d'image non supporté")
    if not image or len(image) > 32 * 1024 * 1024:
        raise ValueError("image vide ou trop volumineuse")
    from openai import OpenAI
    client = OpenAI(api_key=_cle(), base_url=BASE)
    data = base64.b64encode(image).decode()
    reponse = client.chat.completions.create(
        model=os.getenv("DEEPSEEK_VISION_MODELE", _MODEL),
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": question or "Décris précisément cette image et lis son texte."},
                {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{data}"}},
            ],
        }],
    )
    return str(reponse.choices[0].message.content or "")


def manifestes_web() -> list[capacites.ManifesteOutil]:
    """Les deux outils web, déclarés read-only ; le harness applique budget et audit."""
    return [
        capacites.ManifesteOutil(
            nom="rechercher_web",
            version="1.0.0",
            description="Recherche des pages web publiques via DeepSeek Search, avec titres, URL, extraits et scores.",
            capacite="observer",
            types_objets_lus=("PageWeb",),
            schema_entree={"type": "object", "properties": {
                "requete": {"type": "string", "description": "requête web, 1 à 128 caractères"},
                "nombre": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
            }, "required": ["requete"], "additionalProperties": False},
            schema_sortie={"type": "object", "properties": {
                "requete": {"type": "string"}, "resultats": {"type": "array", "items": {"type": "object"}},
            }, "required": ["requete", "resultats"], "additionalProperties": False},
            lecture_seule=True, timeout_ms=30000, mode_preuve="DECLARED",
            source="manifeste", allowlist=("deepseek",),
        ),
        capacites.ManifesteOutil(
            nom="lire_page",
            version="1.0.0",
            description="Lit une page web publique en Markdown via DeepSeek Fetch ; ne contourne aucune ACL.",
            capacite="observer",
            types_objets_lus=("PageWeb",),
            schema_entree={"type": "object", "properties": {
                "url": {"type": "string", "description": "URL HTTP(S) publique"},
            }, "required": ["url"], "additionalProperties": False},
            schema_sortie={"type": "object", "properties": {
                "url": {"type": "string"}, "titre": {"type": "string"}, "contenu": {"type": "string"},
            }, "required": ["url", "titre", "contenu"], "additionalProperties": False},
            lecture_seule=True, timeout_ms=30000, mode_preuve="DECLARED",
            source="manifeste", allowlist=("deepseek",),
        ),
    ]
