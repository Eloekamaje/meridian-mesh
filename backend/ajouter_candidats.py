"""Ajout idempotent du territoire « À confirmer » : 3 jumeaux candidats découverts,
2 relations supposées, et capacités métier sur quelques jumeaux de référence."""
import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient

JUMEAUX = [
    {"id": "cand-agregateur-flux", "nom": "Agrégateur de flux ?", "domaine": "À confirmer", "statut": "observation",
     "position": {"x": 1500, "y": 150}, "mission": "Service découvert dans les flux sortants de Paiements — nature à confirmer",
     "sante": "inconnue", "couverture": 18, "fraicheur": "il y a 2 j", "fraicheur_etat": "ok",
     "strates": {}, "sources": {}, "sources_detail": [], "proprietaire": "", "autonomie": "non qualifiée",
     "environnement": "production", "gouvernance": None, "candidat": True},
    {"id": "cand-passerelle-sepa", "nom": "Passerelle SEPA ?", "domaine": "À confirmer", "statut": "observation",
     "position": {"x": 1630, "y": 120}, "mission": "Relais de messages SEPA observé dans les logs réseau — non déclaré au référentiel",
     "sante": "inconnue", "couverture": 31, "fraicheur": "il y a 1 j", "fraicheur_etat": "ok",
     "strates": {}, "sources": {}, "sources_detail": [], "proprietaire": "", "autonomie": "non qualifiée",
     "environnement": "production", "gouvernance": None, "candidat": True},
    {"id": "cand-relais-notif", "nom": "Relais de notifications ?", "domaine": "À confirmer", "statut": "observation",
     "position": {"x": 1560, "y": 240}, "mission": "Point de sortie de notifications observé — propriétaire non identifié",
     "sante": "inconnue", "couverture": 12, "fraicheur": "il y a 3 j", "fraicheur_etat": "stale",
     "strates": {}, "sources": {}, "sources_detail": [], "proprietaire": "", "autonomie": "non qualifiée",
     "environnement": "production", "gouvernance": None, "candidat": True},
]

RELATIONS = [
    {"id": "r-cand-1", "source": "paiements", "cible": "cand-agregateur-flux", "type": "appelle", "active": True,
     "etat": "supposee", "decouverte_quand": "il y a 2 j", "source_decouverte": "traces Datadog",
     "confiance": 41, "claims": ["Appels sortants observés vers un hôte non référencé"], "observations_contraires": [], "evolution": []},
    {"id": "r-cand-2", "source": "cand-passerelle-sepa", "cible": "cand-agregateur-flux", "type": "echange", "active": True,
     "etat": "supposee", "decouverte_quand": "il y a 1 j", "source_decouverte": "logs réseau",
     "confiance": 34, "claims": ["Flux SEPA transité par un relais non déclaré"], "observations_contraires": [], "evolution": []},
    {"id": "r-cand-3", "source": "cand-agregateur-flux", "cible": "cand-relais-notif", "type": "alimente", "active": True,
     "etat": "supposee", "decouverte_quand": "il y a 3 j", "source_decouverte": "traces Datadog",
     "confiance": 28, "claims": ["Chaîne d'appels sortante prolongée vers un relais de notifications"], "observations_contraires": [], "evolution": []},
]

CAPACITES = {
    "paiements": ["Initier des paiements", "Contrôler et valider", "Gérer les devises", "Vérifier la conformité", "Rapprocher et lettrer"],
    "facturation": ["Émettre les factures", "Piloter la clôture", "Gérer les avoirs"],
    "comptes": ["Tenir les soldes", "Journaliser les mouvements"],
    "fraude": ["Scorer les transactions", "Bloquer les parcours à risque"],
    "support": ["Qualifier les demandes", "Escalader les incidents"],
}


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    for j in JUMEAUX:
        await db.jumeaux.update_one({"id": j["id"]}, {"$setOnInsert": j}, upsert=True)
    for r in RELATIONS:
        await db.relations.update_one({"id": r["id"]}, {"$setOnInsert": r}, upsert=True)
    for jid, caps in CAPACITES.items():
        await db.jumeaux.update_one({"id": jid}, {"$set": {"capacites": caps}})
    print("OK —", await db.jumeaux.count_documents({"candidat": True}), "jumeaux candidats")


asyncio.run(main())
