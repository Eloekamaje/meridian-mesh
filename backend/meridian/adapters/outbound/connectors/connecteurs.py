"""Connecteurs du catalogue : lesquels sont réellement branchés, et ce que dit un test de connexion.

Le catalogue en déclare treize ; sept alimentent un lecteur, le clone Git ou le tirage OTLP. Les autres figurent pour
la trajectoire, mais **aucun code ne les interroge** : annoncer « prête » pour eux était une promesse sans mécanisme
(plan de remédiation L2.5). Ce module existe hors de `server.py` pour que cette règle soit vérifiable sans démarrer
l'API.
"""
import re
from datetime import datetime, timezone

# Ces imports ne servent qu'à enregistrer les fabriques de lecteurs (effet de bord de meridian/adapters/outbound/connectors/lecteurs.py) : sans eux,
# « branché » dépendrait de ce que le processus a déjà importé — une réponse qui varie selon l'ordre des imports.
from meridian.adapters.outbound.connectors import confluence
from meridian.adapters.outbound.connectors import datadog
from meridian.adapters.outbound.connectors import jira
from meridian.adapters.outbound.connectors import servicenow  # noqa: F401
from meridian.adapters.outbound.connectors import lecteurs

# Connecteur → type de source qu'il alimente. « cmdb » est le même système que ServiceNow.
SYSTEME_DU_CONNECTEUR = {"github": "git", "confluence": "confluence", "jira": "jira",
                         "servicenow": "servicenow", "cmdb": "servicenow", "datadog": "datadog",
                         "otlp": "otlp"}

# Champs OTLP : l'URL et la référence du secret sont seuls requis ; le périmètre générique du catalogue ne s'applique
# pas (le flux est déjà circonscrit par l'endpoint et l'environnement).
ENVIRONNEMENTS_OTLP = ("production", "préproduction", "recette", "développement")
FREQUENCES_OTLP = ("horaire", "quotidienne", "hebdomadaire")
RE_SECRET_OTLP = re.compile(r"env:[A-Za-z_][A-Za-z0-9_]*|vault:[\w./-]+(?:#[\w./-]+)?")


def connecteur_branche(connecteur):
    """Le type de source que ce connecteur alimente, ou None s'il n'est pas implémenté."""
    systeme = SYSTEME_DU_CONNECTEUR.get(connecteur)
    return systeme if systeme and (systeme in ("git", "otlp") or systeme.upper() in lecteurs.FABRIQUES) else None


def champ_rempli(valeur):
    return any(x.get("depot") for x in valeur if isinstance(x, dict)) if isinstance(valeur, list) else bool(valeur)


def _hote_otlp(url):
    from meridian.adapters.outbound.connectors.connecteurs_runtime_pull import _nom_hote
    return _nom_hote(url)


def _hote_otlp_autorise(url):
    from meridian.adapters.outbound.connectors.connecteurs_runtime_pull import _hote_autorise
    return _hote_autorise(url)


def _reference_secret_valide(reference):
    if not isinstance(reference, str) or not RE_SECRET_OTLP.fullmatch(reference):
        return False
    if reference.startswith("vault:"):
        chemin = reference[6:].partition("#")[0]
        return bool(chemin) and ".." not in chemin.split("/")
    return True


def configuration_otlp(config, verifier_hote=True):
    """Configuration OTLP normalisée (url, secret_ref, environnement, fréquence) ou ValueError.

    `verifier_hote` applique l'allowlist `JUMEAU_OTLP_HOTES` (test de connexion) ; la déclaration d'une source déjà
    testée se contente de vérifier l'URL HTTPS publique, sans dépendre de l'environnement du processus de naissance.
    """
    config = config if isinstance(config, dict) else {}
    url = str(config.get("url") or "").strip()
    secret_ref = str(config.get("secret_ref") or "").strip()
    if not url or not secret_ref:
        raise ValueError("URL OTLP et référence de secret requises")
    _hote_otlp(url)
    if verifier_hote:
        _hote_otlp_autorise(url)
    if not _reference_secret_valide(secret_ref):
        raise ValueError("référence de secret attendue sous la forme env:NOM ou vault:chemin#clé")
    environnement = str(config.get("environnement") or "production").strip()
    if environnement not in ENVIRONNEMENTS_OTLP:
        raise ValueError(f"environnement OTLP inconnu : {environnement}")
    frequence = str(config.get("frequence") or "quotidienne").strip()
    if frequence not in FREQUENCES_OTLP:
        raise ValueError(f"fréquence OTLP inconnue : {frequence}")
    return {"url": url, "secret_ref": secret_ref, "environnement": environnement, "frequence": frequence}


def source_de_otlp(source):
    """Ligne de la table `source` d'une source OTLP prête : configuration sans secret brut, URL et référence seules."""
    config = source.get("config") if isinstance(source.get("config"), dict) else (source or {})
    configuration = configuration_otlp(config, verifier_hote=False)
    hote = _hote_otlp(configuration["url"])
    nom = str(source.get("nom") or "").strip() or f"otlp-{hote}"
    return {"type": "OTLP", "nom": nom, "emplacement": configuration["url"], "curseur": None,
            "url": configuration["url"], "secret_ref": configuration["secret_ref"],
            "configuration": configuration}


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
                     "Utiliser un connecteur branché (GitHub, Confluence, Jira, ServiceNow, Datadog, OTLP)")
    manquants = [ch["label"] for ch in (conn["champs"] if conn else [])
                 if ch.get("requis") and not champ_rempli((source.get("config") or {}).get(ch["cle"]))]
    if manquants:
        return echec("configuration_incomplete", "Configuration incomplète",
                     f"Champs requis manquants : {', '.join(manquants)}.", "Compléter la configuration")
    if source.get("connecteur") == "otlp":
        try:
            configuration_otlp(source.get("config"), verifier_hote=True)
        except (ValueError, OSError) as e:
            return echec("configuration_incomplete", "Configuration OTLP invalide", str(e),
                         "Corriger l'URL, la référence du secret ou JUMEAU_OTLP_HOTES")
    elif not source.get("perimetre"):
        return echec("perimetre_vide", "Périmètre vide",
                     "Aucun schéma, projet ou index n'est renseigné — la découverte ne rapporterait rien.",
                     "Définir le périmètre")
    if "legacy" in (((source.get("config") or {}).get("hote")) or ""):
        return echec("erreur_connexion", "Erreur de connexion",
                     "L'hôte ne répond pas (délai dépassé sur le port configuré).", "Vérifier le réseau et le port")
    return {"statut": "prete", "erreur": None, "dernier_test": {"date": maintenant, "resultat": "ok"}}
