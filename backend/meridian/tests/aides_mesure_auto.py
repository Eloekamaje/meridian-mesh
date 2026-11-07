"""Faux collection Mongo partagé par les tests de la mesure automatique.

Le fake reste volontairement petit : il couvre les filtres réellement utilisés par les
adaptateurs (égalité, ``$gt``/``$gte``/``$lt``/``$lte``/``$in``/``$ne``/``$exists``), le tri
multi-clés, la limite et les upserts ``$set``/``$setOnInsert``/``$inc``.
"""
from __future__ import annotations

import copy
from datetime import date, datetime, timedelta

MANQUANT = object()


def url_test_autorisee(url) -> bool:
    """Refuse une URL Mongo de production pour les tests d'intégration."""
    texte = str(url or "").strip().lower()
    if not texte:
        return False
    if "localhost" in texte or "127.0.0.1" in texte or "[::1]" in texte:
        return True
    return any(marqueur in texte for marqueur in ("_test", "-test", "test_", "test-",
                                                  "/test", "testdb"))


def _type_mongo(valeur, type_attendu):
    if type_attendu == "string":
        return isinstance(valeur, str)
    if type_attendu == "date":
        return isinstance(valeur, (datetime, date))
    if type_attendu in {"int", "long"}:
        return isinstance(valeur, int) and not isinstance(valeur, bool)
    if type_attendu == "double":
        return isinstance(valeur, float)
    return False


def _valeur(document, chemin):
    valeur = document
    for morceau in str(chemin).split("."):
        if not isinstance(valeur, dict) or morceau not in valeur:
            return MANQUANT
        valeur = valeur[morceau]
    return valeur


def _evaluer_expr(expression, document):
    if isinstance(expression, str) and expression.startswith("$"):
        valeur = _valeur(document, expression[1:])
        return None if valeur is MANQUANT else valeur
    if not isinstance(expression, dict):
        return expression
    if "$convert" in expression:
        converti = expression["$convert"]
        valeur = _evaluer_expr(converti.get("input"), document)
        if valeur is None:
            return converti.get("onNull")
        if isinstance(valeur, datetime):
            return valeur
        if isinstance(valeur, date):
            return datetime.combine(valeur, datetime.min.time())
        if isinstance(valeur, str):
            try:
                return datetime.fromisoformat(valeur.replace("Z", "+00:00"))
            except ValueError:
                return converti.get("onError")
        return converti.get("onError")
    if "$gt" in expression or "$gte" in expression:
        operateur = "$gt" if "$gt" in expression else "$gte"
        gauche, droite = (_evaluer_expr(element, document) for element in expression[operateur])
        try:
            if gauche is None or droite is None:
                return False
            return gauche > droite if operateur == "$gt" else gauche >= droite
        except TypeError:
            return False
    if "$add" in expression:
        valeurs = [_evaluer_expr(element, document) for element in expression["$add"]]
        if any(valeur is None for valeur in valeurs):
            return None
        if isinstance(valeurs[0], datetime) and isinstance(valeurs[1], (int, float)):
            return valeurs[0] + timedelta(milliseconds=valeurs[1])
        return valeurs[0] + valeurs[1]
    if "$and" in expression:
        return all(_evaluer_expr(element, document) for element in expression["$and"])
    return False


def _correspond(document, filtre):
    for cle, attendu in (filtre or {}).items():
        if cle == "$expr":
            if not _evaluer_expr(attendu, document):
                return False
            continue
        if cle == "$and":
            if not all(_correspond(document, partie) for partie in attendu):
                return False
            continue
        if cle == "$or":
            if not any(_correspond(document, partie) for partie in attendu):
                return False
            continue
        if cle == "$nor":
            if any(_correspond(document, partie) for partie in attendu):
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
                if operateur == "$not":
                    if valeur is not MANQUANT and _correspond(
                            {cle: valeur}, {cle: reference}):
                        return False
                    continue
                if operateur == "$type":
                    types = reference if isinstance(reference, list) else [reference]
                    if not any(_type_mongo(valeur, type_) for type_ in types):
                        return False
                    continue
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
        def cle_tri(document, champ):
            valeur = _valeur(document, champ)
            if valeur is MANQUANT or valeur is None:
                return (0, "")
            if isinstance(valeur, (datetime, date)):
                return (1, valeur.isoformat())
            return (1, str(valeur))

        for champ, direction in reversed(list(tri)):
            self.documents.sort(
                key=lambda document: cle_tri(document, champ),
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


def _verifier_operateurs(modification):
    """Mongo refuse deux opérateurs sur le même champ (WriteError code 40)."""
    vus = {}
    for operateur, champs in (modification or {}).items():
        if operateur not in {"$set", "$setOnInsert", "$inc", "$unset"}:
            continue
        for cle in champs:
            if cle in vus:
                raise RuntimeError(
                    f"WriteError code 40 : champ {cle!r} dans {vus[cle]} et {operateur}")
            vus[cle] = operateur


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

    async def count_documents(self, filtre=None):
        self.appels.append(("count_documents", copy.deepcopy(filtre)))
        return sum(1 for document in self.documents
                   if _correspond(document, filtre or {}))

    async def update_one(self, filtre, modification, upsert=False):
        self.appels.append(("update_one", copy.deepcopy(filtre), copy.deepcopy(modification),
                            upsert))
        _verifier_operateurs(modification)
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
        _appliquer(document, modification or {})
        identifiant = document.get("_id")
        if identifiant is not None and any(
                existant.get("_id") == identifiant for existant in self.documents):
            raise RuntimeError("duplicate key")
        self.documents.append(document)
        return type("Resultat", (), {
            "upserted_id": document.get("_id"), "matched_count": 0, "modified_count": 0,
        })()

    async def create_index(self, cles, **options):
        self.index.append((cles, options))
        return options.get("name") or "index"
