"""Port du graph store du Mesh : les relations et parcours ne sont pas une projection Postgres.

Postgres possède l'identité canonique du Twin, les Claims, les preuves et les décisions. Le graph store
possède la topologie : nœuds Twin référencés par id, relations, domaines, capacités, processus, parcours,
situations et impacts. Aucun objet n'est copié intégralement entre les deux stores.

`GrapheMemoire` est l'adaptateur de test/développement. Les adaptateurs Neo4j et Neptune implémentent le même
protocole sans changer le domaine métier.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Protocol, runtime_checkable

MAX_PROFONDEUR = 8
TYPES_TWIN = {"APPLICATION", "PROCESS", "CAPABILITY", "JOURNEY", "ORGANIZATION", "PRODUCT", "DATA_DOMAIN"}
ETATS_RELATION = {"supposee", "observee", "validation", "confirmee", "contestee", "obsolete"}


def _texte(valeur, champ, obligatoire=True):
    texte = str(valeur or "").strip()
    if obligatoire and not texte:
        raise ValueError(f"{champ} vide")
    return texte


def _profondeur(valeur):
    return max(1, min(int(valeur), MAX_PROFONDEUR))


@dataclass(frozen=True)
class NoeudTwin:
    id: str
    tenant_id: str
    type: str = "APPLICATION"
    label: str = ""
    proprietes: dict = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "id", _texte(self.id, "id"))
        object.__setattr__(self, "tenant_id", _texte(self.tenant_id, "tenant_id"))
        if self.type not in TYPES_TWIN:
            raise ValueError(f"type de Twin inconnu : {self.type}")
        object.__setattr__(self, "label", _texte(self.label or self.id, "label"))
        if not isinstance(self.proprietes, dict):
            raise ValueError("proprietes : objet attendu")


@dataclass(frozen=True)
class Arete:
    id: str
    tenant_id: str
    source: str
    target: str
    type: str = "structurante"
    etat: str = "supposee"
    confiance: float = 0.5
    valid_from: str | None = None
    valid_to: str | None = None
    preuve_ids: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "id", _texte(self.id, "id"))
        object.__setattr__(self, "tenant_id", _texte(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "source", _texte(self.source, "source"))
        object.__setattr__(self, "target", _texte(self.target, "target"))
        if self.etat not in ETATS_RELATION:
            raise ValueError(f"état de relation inconnu : {self.etat}")
        if not 0 <= float(self.confiance) <= 1:
            raise ValueError("confiance hors bornes")
        if self.source == self.target:
            raise ValueError("une relation ne peut pas boucler sur elle-même")
        object.__setattr__(self, "preuve_ids", tuple(str(x) for x in (self.preuve_ids or ())))

    def active(self) -> bool:
        return self.valid_to is None


@runtime_checkable
class GraphStore(Protocol):
    def upsert_twin(self, noeud: NoeudTwin) -> NoeudTwin: ...
    def upsert_relation(self, arete: Arete) -> Arete: ...
    def voisins(self, tenant_id: str, twin_id: str, profondeur: int = 1, sens: str = "sortant") -> list[dict]: ...
    def chemins(self, tenant_id: str, source: str, cible: str, profondeur: int = 6) -> list[list[str]]: ...
    def impact(self, tenant_id: str, twin_id: str, profondeur: int = 3) -> dict: ...


class GrapheMemoire:
    """Adaptateur déterministe du port, pour tests et développement local."""

    def __init__(self):
        self.noeuds: dict[tuple[str, str], NoeudTwin] = {}
        self.aretes: dict[tuple[str, str], Arete] = {}

    def upsert_twin(self, noeud: NoeudTwin) -> NoeudTwin:
        if not isinstance(noeud, NoeudTwin):
            raise ValueError("NoeudTwin attendu")
        precedent = self.noeuds.get((noeud.tenant_id, noeud.id))
        if precedent is not None and precedent.type != noeud.type:
            raise ValueError("le type d'un Twin ne change pas")
        self.noeuds[(noeud.tenant_id, noeud.id)] = noeud
        return noeud

    def upsert_relation(self, arete: Arete) -> Arete:
        if not isinstance(arete, Arete):
            raise ValueError("Arete attendue")
        for extrémité in (arete.source, arete.target):
            if (arete.tenant_id, extrémité) not in self.noeuds:
                raise ValueError(f"Twin absent du graphe : {extrémité}")
        self.aretes[(arete.tenant_id, arete.id)] = arete
        return arete

    def _aretes(self, tenant_id, sens="sortant"):
        for arete in self.aretes.values():
            if arete.tenant_id != tenant_id or not arete.active():
                continue
            if sens in ("sortant", "les_deux") and arete.source:
                yield arete, "sortant"
            if sens in ("entrant", "les_deux") and arete.target:
                yield arete, "entrant"

    def voisins(self, tenant_id: str, twin_id: str, profondeur: int = 1, sens: str = "sortant") -> list[dict]:
        tenant, depart = _texte(tenant_id, "tenant_id"), _texte(twin_id, "twin_id")
        if sens not in ("sortant", "entrant", "les_deux"):
            raise ValueError("sens attendu : sortant, entrant ou les_deux")
        profondeur = _profondeur(profondeur)
        resultats, vus = [], {(tenant, depart)}
        frontiere = [(depart, 1, [depart])]
        while frontiere:
            courant, niveau, chemin = frontiere.pop(0)
            if niveau > profondeur:
                continue
            for arete, direction in self._aretes(tenant, sens):
                voisin = arete.target if direction == "sortant" and arete.source == courant else (
                    arete.source if direction == "entrant" and arete.target == courant else None)
                if not voisin or (tenant, voisin) in vus:
                    continue
                vus.add((tenant, voisin))
                nouveau = chemin + [voisin]
                resultats.append({"id": voisin, "profondeur": niveau, "chemin": nouveau,
                                  "relation": arete.id, "etat": arete.etat})
                frontiere.append((voisin, niveau + 1, nouveau))
        return sorted(resultats, key=lambda x: (x["profondeur"], x["id"]))

    def chemins(self, tenant_id: str, source: str, cible: str, profondeur: int = 6) -> list[list[str]]:
        tenant, depart, arrivee = _texte(tenant_id, "tenant_id"), _texte(source, "source"), _texte(cible, "cible")
        profondeur = _profondeur(profondeur)
        chemins, frontiere = [], [(depart, [depart])]
        while frontiere:
            courant, chemin = frontiere.pop(0)
            if courant == arrivee:
                chemins.append(chemin)
                continue
            if len(chemin) > profondeur:
                continue
            for arete, direction in self._aretes(tenant, "sortant"):
                if direction != "sortant" or arete.source != courant or arete.target in chemin:
                    continue
                frontiere.append((arete.target, chemin + [arete.target]))
        return sorted(chemins, key=lambda c: (len(c), c))

    def impact(self, tenant_id: str, twin_id: str, profondeur: int = 3) -> dict:
        return {"aval": self.voisins(tenant_id, twin_id, profondeur, "sortant"),
                "amont": self.voisins(tenant_id, twin_id, profondeur, "entrant")}

    def as_dict(self) -> dict:
        return {"noeuds": [asdict(n) for n in self.noeuds.values()],
                "aretes": [asdict(a) for a in self.aretes.values()]}
