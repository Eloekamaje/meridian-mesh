"""Nettoyage en base des travaux créés par les tests (l'API n'a pas de suppression)."""
import os

from dotenv import dotenv_values


def supprimer_cases(filtre: dict) -> int:
    from pymongo import MongoClient
    env = dotenv_values(os.path.join(os.path.dirname(__file__), "..", ".env"))
    db = MongoClient(env.get("MONGO_URL", "mongodb://localhost:27017"))[env.get("DB_NAME", "meridian_db")]
    return db.cases.delete_many(filtre).deleted_count


def _db():
    from pymongo import MongoClient
    env = dotenv_values(os.path.join(os.path.dirname(__file__), "..", ".env"))
    return MongoClient(env.get("MONGO_URL", "mongodb://localhost:27017"))[env.get("DB_NAME", "meridian_db")]


def supprimer_delegations(filtre: dict) -> int:
    return _db().delegations.delete_many(filtre).deleted_count


def remettre_initiatives(ids: list) -> None:
    """Une réponse à une proposition est définitive : les tests la remettent en attente avant et après."""
    _db().initiatives.update_many({"id": {"$in": ids}}, {"$set": {"statut": "en_attente"}, "$unset": {"reponse": ""}})


def supprimer_ecarts(filtre: dict) -> int:
    return _db().actualites_ecartees.delete_many(filtre).deleted_count


def supprimer_notifications(filtre: dict) -> int:
    return _db().notifications.delete_many(filtre).deleted_count
