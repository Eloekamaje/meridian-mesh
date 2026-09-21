"""Nettoyage en base des travaux créés par les tests (l'API n'a pas de suppression)."""
import os

from dotenv import dotenv_values


def supprimer_cases(filtre: dict) -> int:
    from pymongo import MongoClient
    env = dotenv_values(os.path.join(os.path.dirname(__file__), "..", ".env"))
    db = MongoClient(env.get("MONGO_URL", "mongodb://localhost:27017"))[env.get("DB_NAME", "meridian_db")]
    return db.cases.delete_many(filtre).deleted_count
