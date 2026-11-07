"""Fakes partagés par les tests du pont Travail → canonique.

Le pont a deux stores : une collection Mongo (`pont_canonique`) et Postgres (`objet_entreprise`).
Ces fakes restent volontairement petits mais respectent les opérateurs réellement utilisés :
`$setOnInsert`, `$set`, `$inc`, `$unset`, `$and`, `$or`, `$in`, `$lte`, `$gt` et `find_one_and_update`.
Postgres est simulé avec de vraies transactions imbriquées (snapshot/rollback) pour prouver qu'un
échec au troisième objet ne laisse aucune écriture partielle.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from types import SimpleNamespace

MANQUANT = object()


def _valeur(document, chemin):
    valeur = document
    for morceau in str(chemin).split("."):
        if isinstance(valeur, dict):
            if morceau not in valeur:
                return MANQUANT
            valeur = valeur[morceau]
        else:
            return MANQUANT
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
        if isinstance(attendu, dict) and any(str(operateur).startswith("$") for operateur in attendu):
            if "$in" in attendu and valeur not in attendu["$in"]:
                return False
            if "$nin" in attendu and valeur in attendu["$nin"]:
                return False
            if "$ne" in attendu and valeur == attendu["$ne"]:
                return False
            if "$exists" in attendu and (valeur is not MANQUANT) != bool(attendu["$exists"]):
                return False
            if "$gt" in attendu and not (valeur is not MANQUANT and valeur is not None
                                         and valeur > attendu["$gt"]):
                return False
            if "$gte" in attendu and not (valeur is not MANQUANT and valeur is not None
                                          and valeur >= attendu["$gte"]):
                return False
            if "$lt" in attendu and not (valeur is not MANQUANT and valeur is not None
                                         and valeur < attendu["$lt"]):
                return False
            if "$lte" in attendu and not (valeur is not MANQUANT and valeur is not None
                                          and valeur <= attendu["$lte"]):
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
        elif operateur == "$unset":
            for cle in champs:
                document.pop(cle, None)
        elif operateur == "$inc":
            for cle, valeur in champs.items():
                document[cle] = document.get(cle, 0) + valeur
        elif operateur == "$push":
            for cle, valeur in champs.items():
                document.setdefault(cle, []).append(copy.deepcopy(valeur))
        else:
            raise AssertionError(f"opérateur non simulé : {operateur}")


class CurseurPont:
    def __init__(self, documents):
        self.documents = [copy.deepcopy(document) for document in documents]

    def sort(self, tri, sens=1):
        if isinstance(tri, str):
            tri = [(tri, sens)]
        elif isinstance(tri, tuple):
            tri = [tri]
        for champ, sens in reversed(list(tri)):
            self.documents.sort(
                key=lambda document: (document.get(champ) is None, document.get(champ)), reverse=sens < 0)
        return self

    def limit(self, nombre):
        self.documents = self.documents[: int(nombre)]
        return self

    async def to_list(self, nombre=None):
        documents = self.documents if nombre is None else self.documents[: int(nombre)]
        return copy.deepcopy(documents)

    def __aiter__(self):
        self._iter = iter(self.documents)
        return self

    async def __anext__(self):
        try:
            return copy.deepcopy(next(self._iter))
        except StopIteration:
            raise StopAsyncIteration


class CollectionPont:
    """Collection Mongo minimale, synchrone en interne mais API async (Motor)."""

    def __init__(self, documents=None):
        self.documents = [copy.deepcopy(document) for document in documents or []]
        self.appels = []

    def _id(self):
        return f"oid-{len(self.documents) + 1}"

    def find(self, filtre=None, projection=None):
        self.appels.append(("find", copy.deepcopy(filtre), projection))
        return CurseurPont([d for d in self.documents if _correspond(d, filtre)])

    async def find_one(self, filtre=None, projection=None):
        self.appels.append(("find_one", copy.deepcopy(filtre), projection))
        return next((copy.deepcopy(d) for d in self.documents if _correspond(d, filtre)), None)

    async def count_documents(self, filtre):
        self.appels.append(("count_documents", copy.deepcopy(filtre)))
        return sum(1 for d in self.documents if _correspond(d, filtre))

    async def update_one(self, filtre, modification, upsert=False):
        self.appels.append(("update_one", copy.deepcopy(filtre), copy.deepcopy(modification), upsert))
        for document in self.documents:
            if _correspond(document, filtre):
                _appliquer(document, modification)
                return SimpleNamespace(matched_count=1, modified_count=1, upserted_id=None)
        if upsert:
            document = {cle: copy.deepcopy(valeur) for cle, valeur in (filtre or {}).items()
                        if not isinstance(valeur, dict)}
            document.setdefault("_id", self._id())
            if "$setOnInsert" in modification:
                document.update(copy.deepcopy(modification["$setOnInsert"]))
            _appliquer(document, modification)
            self.documents.append(document)
            return SimpleNamespace(matched_count=0, modified_count=0, upserted_id=document["_id"])
        return SimpleNamespace(matched_count=0, modified_count=0, upserted_id=None)

    async def update_many(self, filtre, modification, upsert=False):
        self.appels.append(("update_many", copy.deepcopy(filtre), copy.deepcopy(modification), upsert))
        touches = 0
        for document in self.documents:
            if _correspond(document, filtre):
                _appliquer(document, modification)
                touches += 1
        if touches:
            return SimpleNamespace(matched_count=touches, modified_count=touches, upserted_id=None)
        if upsert:
            return await self.update_one(filtre, modification, upsert=True)
        return SimpleNamespace(matched_count=0, modified_count=0, upserted_id=None)

    async def find_one_and_update(self, filtre, modification, projection=None, sort=None,
                                  upsert=False, return_document=False):
        self.appels.append(("find_one_and_update", copy.deepcopy(filtre), copy.deepcopy(modification)))
        documents = [d for d in self.documents if _correspond(d, filtre)]
        if sort:
            tri = [(sort, 1)] if isinstance(sort, str) else (
                [sort] if isinstance(sort, tuple) else list(sort))
            for champ, sens in reversed(tri):
                documents.sort(
                    key=lambda document: (document.get(champ) is None, document.get(champ)),
                    reverse=sens < 0)
        if not documents:
            if not upsert:
                return None
            document = {cle: copy.deepcopy(valeur) for cle, valeur in (filtre or {}).items()
                        if not isinstance(valeur, dict)}
            document.setdefault("_id", self._id())
            if "$setOnInsert" in modification:
                document.update(copy.deepcopy(modification["$setOnInsert"]))
            _appliquer(document, modification)
            self.documents.append(document)
            return copy.deepcopy(document)
        document = documents[0]
        avant = copy.deepcopy(document)
        _appliquer(document, modification)
        return copy.deepcopy(document if return_document else avant)


class TransactionPont:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        self.conn._snapshots.append(copy.deepcopy(self.conn.stock))
        return self

    def __exit__(self, exc_type, exc, tb):
        snapshot = self.conn._snapshots.pop()
        if exc_type is not None:
            self.conn.stock.clear()
            self.conn.stock.update(snapshot)
        return False


def _parametre(valeur):
    if hasattr(valeur, "obj"):
        return valeur.obj
    return valeur


class CurseurPostgres:
    def __init__(self, conn):
        self.conn = conn
        self.resultat = None
        self.lignes = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, requete, parametres=None):
        parametres = parametres or ()
        requete = " ".join(str(requete).split())
        self.resultat = None
        self.lignes = []
        if requete.startswith("SELECT set_config"):
            self.resultat = (parametres[0] if parametres else "",)
            return self
        if requete.startswith("SELECT current_schema()"):
            self.resultat = ("public",)
            return self
        if requete.startswith("SELECT * FROM objet_entreprise WHERE tenant_id = %s AND id = %s"):
            self.resultat = copy.deepcopy(self.conn.stock.get((parametres[0], parametres[1])))
            return self
        if requete.startswith("INSERT INTO objet_entreprise"):
            ligne = {
                "id": parametres[0],
                "tenant_id": parametres[1],
                "famille": parametres[2],
                "type": parametres[3],
                "mode": parametres[4],
                "titre": parametres[5],
                "donnees": _parametre(parametres[6]),
                "version": parametres[7],
                "observe_le": parametres[8] or self.conn.NOW,
                "valide_depuis": parametres[9] or self.conn.NOW,
                "valide_jusqua": parametres[10],
                "cree_le": parametres[12] or self.conn.NOW,
                "maj_le": self.conn.NOW,
            }
            self.conn.stock[(ligne["tenant_id"], ligne["id"])] = ligne
            self.conn.ecritures.append(("INSERT", ligne["tenant_id"], ligne["id"]))
            self.resultat = copy.deepcopy(ligne)
            return self
        if requete.startswith("UPDATE objet_entreprise SET"):
            ligne = self.conn.stock[(parametres[9], parametres[10])]
            ligne.update({
                "famille": parametres[0],
                "type": parametres[1],
                "mode": parametres[2],
                "titre": parametres[3],
                "donnees": _parametre(parametres[4]),
                "version": parametres[5],
                "observe_le": parametres[6] or ligne["observe_le"],
                "valide_depuis": parametres[7] or ligne["valide_depuis"],
                "valide_jusqua": parametres[8],
                "maj_le": self.conn.NOW,
            })
            self.conn.ecritures.append(("UPDATE", parametres[9], parametres[10]))
            self.resultat = copy.deepcopy(ligne)
            return self
        raise AssertionError(f"requête inattendue : {requete}")

    def fetchone(self):
        return self.resultat

    def fetchall(self):
        if self.lignes:
            return self.lignes
        return [] if self.resultat is None else [self.resultat]


class ConnexionPont:
    """Connexion Postgres factice : transactions imbriquées avec rollback réel."""

    NOW = "2026-11-06T12:00:00+00:00"

    def __init__(self):
        self.stock = {}
        self.ecritures = []
        self._snapshots = []

    def transaction(self):
        return TransactionPont(self)

    def cursor(self, row_factory=None):
        return CurseurPostgres(self)

    def execute(self, requete, parametres=None):
        return CurseurPostgres(self).execute(requete, parametres)


def instant(valeur="2026-11-06T12:00:00+00:00"):
    return valeur


def document_evenement(**champs):
    """Document d'outbox de test, sans dépendre du module de production."""
    base = {
        "_id": "evt-0000000000000000000000000001",
        "tenant_id": "banque",
        "operation": "situation.maj",
        "canonical_ids": ["sit-1"],
        "payload": {},
        "source": {"collection": "situations", "id": "sit-1"},
        "etat": "pending",
        "tentatives": 0,
        "prochaine_tentative": None,
        "derniere_erreur": None,
        "cree_le": instant(),
        "maj_le": instant(),
        "locked_until": None,
        "lock_token": None,
        "fencing_token": 0,
    }
    base.update(champs)
    return base


def maintenant_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
