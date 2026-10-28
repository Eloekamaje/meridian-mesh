"""Connecteurs du catalogue : lesquels sont réellement branchés, et ce que dit un test de connexion.

Le catalogue en déclare douze ; six alimentent un lecteur ou le clone Git. Les autres figurent pour la trajectoire,
mais **aucun code ne les interroge** : annoncer « prête » pour eux était une promesse sans mécanisme (plan de
remédiation L2.5). Ce module existe hors de `server.py` pour que cette règle soit vérifiable sans démarrer l'API.
"""
from datetime import datetime, timezone

# Ces imports ne servent qu'à enregistrer les fabriques de lecteurs (effet de bord de jumeau/lecteurs.py) : sans eux,
# « branché » dépendrait de ce que le processus a déjà importé — une réponse qui varie selon l'ordre des imports.
from jumeau import confluence, datadog, jira, servicenow  # noqa: F401
from jumeau import lecteurs

# Connecteur → type de source qu'il alimente. « cmdb » est le même système que ServiceNow.
SYSTEME_DU_CONNECTEUR = {"github": "git", "confluence": "confluence", "jira": "jira",
                         "servicenow": "servicenow", "cmdb": "servicenow", "datadog": "datadog"}


def connecteur_branche(connecteur):
    """Le type de source que ce connecteur alimente, ou None s'il n'est pas implémenté."""
    systeme = SYSTEME_DU_CONNECTEUR.get(connecteur)
    return systeme if systeme and (systeme == "git" or systeme.upper() in lecteurs.FABRIQUES) else None


def champ_rempli(valeur):
    return any(x.get("depot") for x in valeur if isinstance(x, dict)) if isinstance(valeur, list) else bool(valeur)


def test_simule(source, catalogue):
    """Test de connexion déterministe, sans réseau : non branché, configuration incomplète, périmètre vide, hôte
    injoignable, sinon prête. Seuls les connecteurs branchés peuvent être prêts."""
    conn = next((c for c in catalogue if c["id"] == source.get("connecteur")), None)
    maintenant = datetime.now(timezone.utc).strftime("%d/%m %H:%M")

    def echec(statut, titre, detail, action):
        return {"statut": statut, "erreur": {"titre": titre, "detail": detail, "action": action},
                "dernier_test": {"date": maintenant, "resultat": "echec" if statut != "non_branche" else "non_branche"}}

    if not connecteur_branche(source.get("connecteur")):
        return echec("non_branche", "Connecteur non branché",
                     "Ce connecteur figure au catalogue mais aucun lecteur ne l'interroge encore : aucune donnée "
                     "ne serait lue.",
                     "Utiliser un connecteur branché (GitHub, Confluence, Jira, ServiceNow, Datadog)")
    manquants = [ch["label"] for ch in (conn["champs"] if conn else [])
                 if ch.get("requis") and not champ_rempli((source.get("config") or {}).get(ch["cle"]))]
    if manquants:
        return echec("configuration_incomplete", "Configuration incomplète",
                     f"Champs requis manquants : {', '.join(manquants)}.", "Compléter la configuration")
    if not source.get("perimetre"):
        return echec("perimetre_vide", "Périmètre vide",
                     "Aucun schéma, projet ou index n'est renseigné — la découverte ne rapporterait rien.",
                     "Définir le périmètre")
    if "legacy" in (((source.get("config") or {}).get("hote")) or ""):
        return echec("erreur_connexion", "Erreur de connexion",
                     "L'hôte ne répond pas (délai dépassé sur le port configuré).", "Vérifier le réseau et le port")
    return {"statut": "prete", "erreur": None, "dernier_test": {"date": maintenant, "resultat": "ok"}}
