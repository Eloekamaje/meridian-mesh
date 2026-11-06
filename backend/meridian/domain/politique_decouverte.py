"""Politique des sources autorisées pour la découverte.

Toutes les sources ne se valent pas en risque :

- niveau 0 : code, configuration, contrats, Helm — déjà dans les dépôts/artefacts ;
- niveau 1 : Kubernetes, gateway, traces — métadonnées d'exécution ;
- niveau 2 : CMDB, portail API — référentiels d'entreprise ;
- niveau 3 : serveur, export WebSphere — accès exceptionnel.

Une politique est explicite, datée, attribuée et révisable. Le niveau 3 exige une
approbation nommée. Aucune source inconnue n'est autorisée par défaut.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone

__all__ = [
    "NIVEAUX_SOURCES",
    "SOURCES_CONNUES",
    "SOURCES_PAR_DEFAUT",
    "PolitiqueSources",
]

NIVEAUX_SOURCES = {
    0: ("code", "config", "contrats", "helm"),
    1: ("kubernetes", "gateway", "traces"),
    2: ("cmdb", "portail_api"),
    3: ("serveur", "export_websphere"),
}
SOURCES_CONNUES = frozenset(
    source for sources in NIVEAUX_SOURCES.values() for source in sources)
SOURCES_PAR_DEFAUT = frozenset(NIVEAUX_SOURCES[0])

_ALIAS = {
    "contracts": "contrats",
    "api_portal": "portail_api",
    "portail": "portail_api",
    "k8s": "kubernetes",
    "websphere": "export_websphere",
    "server": "serveur",
}


def _source(valeur) -> str:
    texte = str(valeur or "").strip().lower().replace("-", "_").replace(" ", "_")
    texte = _ALIAS.get(texte, texte)
    if texte not in SOURCES_CONNUES:
        raise ValueError(f"source inconnue : {valeur!r}")
    return texte


def _niveaux(valeurs) -> tuple[int, ...]:
    resultat = []
    for valeur in valeurs or ():
        try:
            niveau = int(valeur)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"niveau de source invalide : {valeur!r}") from exc
        if niveau not in NIVEAUX_SOURCES:
            raise ValueError(f"niveau de source inconnu : {niveau}")
        resultat.append(niveau)
    return tuple(sorted(set(resultat)))


def _instant(valeur) -> str:
    if valeur is None or str(valeur).strip() == "":
        return ""
    if isinstance(valeur, datetime):
        return valeur.astimezone(timezone.utc).isoformat()
    texte = str(valeur).strip()
    try:
        datetime.fromisoformat(texte.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("date ISO attendue") from exc
    return texte


@dataclass(frozen=True)
class PolitiqueSources:
    tenant_id: str
    niveaux: tuple[int, ...] = (0,)
    sources_explicites: tuple[str, ...] = ()
    approuve_par: str = ""
    approuve_le: str = ""
    motif: str = ""

    def __post_init__(self):
        tenant = " ".join(str(self.tenant_id or "").split())
        if not tenant:
            raise ValueError("tenant_id obligatoire")
        object.__setattr__(self, "tenant_id", tenant)
        niveaux = _niveaux(self.niveaux)
        sources = tuple(dict.fromkeys(_source(x) for x in (self.sources_explicites or ())))
        if 3 in niveaux and not str(self.approuve_par or "").strip():
            raise ValueError("le niveau 3 exige une approbation nommée")
        object.__setattr__(self, "niveaux", niveaux)
        object.__setattr__(self, "sources_explicites", sources)
        object.__setattr__(self, "approuve_par", " ".join(str(self.approuve_par or "").split()))
        object.__setattr__(self, "approuve_le", _instant(self.approuve_le))
        object.__setattr__(self, "motif", " ".join(str(self.motif or "").split()))

    @property
    def sources_autorisees(self) -> frozenset[str]:
        sources = set()
        for niveau in self.niveaux:
            sources.update(NIVEAUX_SOURCES[niveau])
        sources.update(self.sources_explicites)
        return frozenset(sources)

    @property
    def niveau_max(self) -> int:
        return max(self.niveaux) if self.niveaux else -1

    def autorise(self, source: str) -> bool:
        try:
            return _source(source) in self.sources_autorisees
        except ValueError:
            return False

    def avec_niveaux(self, niveaux, *, approuve_par: str = "",
                     approuve_le: str = "", motif: str = "") -> "PolitiqueSources":
        return replace(self, niveaux=tuple(niveaux),
                       approuve_par=approuve_par or self.approuve_par,
                       approuve_le=approuve_le or self.approuve_le,
                       motif=motif or self.motif)

    def as_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id, "niveaux": list(self.niveaux),
            "sources_explicites": list(self.sources_explicites),
            "sources_autorisees": sorted(self.sources_autorisees),
            "approuve_par": self.approuve_par, "approuve_le": self.approuve_le,
            "motif": self.motif,
        }

    @classmethod
    def depuis_dict(cls, valeur) -> "PolitiqueSources":
        if not isinstance(valeur, dict):
            raise ValueError("politique de sources : objet attendu")
        return cls(**{cle: valeur.get(cle) for cle in (
            "tenant_id", "niveaux", "sources_explicites", "approuve_par",
            "approuve_le", "motif")})
