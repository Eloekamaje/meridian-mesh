"""Faux collection Mongo partagé par les tests de la mesure automatique.

Le fake reste volontairement petit : il couvre les filtres réellement utilisés par les
adaptateurs (égalité, ``$gt``/``$gte``/``$lt``/``$lte``/``$in``/``$ne``/``$exists``), le tri
multi-clés, la limite et les upserts ``$set``/``$setOnInsert``/``$inc``.
"""
from __future__ import annotations

import copy

MANQUANT = object()


def _valeur(document, chemin):
    valeur = document
    for morceau in str(chemin).split("."):
        if not isinstance(valeur, dict) or morceau not in valeur:
            return MANQUANT
        valeur = valeur[morceau]
    return valeur


def _correspond(document, filtre):
    for cle, attendu in (filtre or {}).items():
        if cle == "$and":
            if not all(_correspond(document, partie) for partie in attendu):
                return False
            continue
        if cle == "$or":
            if not any(_correspond(document, partie) for partie in attendu):
                return False
            continue
        valeur = _valeur(document, cle)
        if (isinstance(attendu, dict)
                and any(str(operateur).startswith("$") for operateur in attendu)):
            for operateur, reference in attendu.items():
                if operateur == "$in" and (valeur is MANQUANT or valeur not in reference):
                    return False
                if operateur == "$nin" and valeur is not MANQUANT and valeur in reference:
                    return False
                if operateur == "$ne" and valeur is not MANQUANT and valeur == reference:
                    return False
                if operateur == "$exists" and (valeur is not MANQUANT) != bool(reference):
                    return False
                if operateur == "$gt" and not (valeur is not MANQUANT and valeur is not None
                                               and valeur > reference):
                    return False
                if operateur == "$gte" and not (valeur is not MANQUANT and valeur is not None
                                                and valeur >= reference):
                    return False
                if operateur == "$lt" and not (valeur is not MANQUANT and valeur is not None
                                               and valeur < reference):
                    return False
                if operateur == "$lte" and not (valeur is not MANQUANT and valeur is not None
                                                and valeur <= reference):
                    return False
            continue
        if attendu is None:
            if valeur is not MANQUANT and valeur is not None:
                return False
        elif valeur is MANQUANT or valeur != attendu:
            return False
    return True


def _appliquer(document, modification):
    for operateur, champs in modification.items():
        if operateur == "$set":
            document.update(copy.deepcopy(champs))
        elif operateur == "$setOnInsert":
            continue
        elif operateur == "$inc":
            for cle, valeur in champs.items():
                document[cle] = document.get(cle, 0) + valeur
        elif operateur == "$unset":
            for cle in champs:
                document.pop(cle, None)
        else:
            raise AssertionError(f"opérateur non simulé : {operateur}")


class CurseurMesure:
    def __init__(self, documents):
        self.documents = [copy.deepcopy(document) for document in documents]

    def sort(self, tri, sens=1):
        if isinstance(tri, str):
            tri = [(tri, sens)]
        elif isinstance(tri, tuple):
            tri = [tri]
        for champ, direction in reversed(list(tri)):
            self.documents.sort(
                key=lambda document: (
                    _valeur(document, champ) is not MANQUANT,
                    _valeur(document, champ),
                ),
                reverse=direction < 0,
            )
        return self

    def limit(self, nombre):
        self.documents = self.documents[: int(nombre)]
        return self

    async def to_list(self, nombre=None):
        if nombre is None:
            return copy.deepcopy(self.documents)
        return copy.deepcopy(self.documents[: int(nombre)])

    def __aiter__(self):
        self._iter = iter(self.documents)
        return self

    async def __anext__(self):
        try:
            return copy.deepcopy(next(self._iter))
        except StopIteration:
            raise StopAsyncIteration


class CollectionMesure:
    """Collection Mongo minimale, synchrone en interne mais API async (Motor)."""

    def __init__(self, documents=None):
        self.documents = [copy.deepcopy(document) for document in documents or []]
        self.appels = []
        self.index = []

    def find(self, filtre=None, projection=None):
        self.appels.append(("find", copy.deepcopy(filtre), projection))
        return CurseurMesure(
            [document for document in self.documents if _correspond(document, filtre or {})]
        )

    async def find_one(self, filtre=None, projection=None):
        self.appels.append(("find_one", copy.deepcopy(filtre), projection))
        for document in self.documents:
            if _correspond(document, filtre or {}):
                return copy.deepcopy(document)
        return None

    async def update_one(self, filtre, modification, upsert=False):
        self.appels.append(("update_one", copy.deepcopy(filtre), copy.deepcopy(modification),
                            upsert))
        for document in self.documents:
            if _correspond(document, filtre or {}):
                _appliquer(document, modification)
                return type("Resultat", (), {
                    "upserted_id": None, "matched_count": 1, "modified_count": 1,
                })()
        if not upsert:
            return type("Resultat", (), {
                "upserted_id": None, "matched_count": 0, "modified_count": 0,
            })()
        document = {}
        for cle, valeur in (filtre or {}).items():
            if cle.startswith("$"):
                continue
            if isinstance(valeur, dict) and any(str(k).startswith("$") for k in valeur):
                continue
            document[cle] = copy.deepcopy(valeur)
        document.update(copy.deepcopy((modification or {}).get("$setOnInsert") or {}))
        document.update(copy.deepcopy((modification or {}).get("$set") or {}))
        self.documents.append(document)
        return type("Resultat", (), {
            "upserted_id": document.get("_id"), "matched_count": 0, "modified_count": 0,
        })()

    async def create_index(self, cles, **options):
        self.index.append((cles, options))
        return options.get("name") or "index"
