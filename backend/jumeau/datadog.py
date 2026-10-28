"""Lecteur Datadog : comment l'application se comporte réellement (volumes, erreurs, latence, appels vers d'autres services).

Mêmes garde-fous que Jira : seul l'hôte autorisé (JUMEAU_DATADOG_HOTE, ex. api.datadoghq.eu) est interrogé, en HTTPS,
sans redirection ; clé d'API et clé d'application vivent dans Vault (« clé_api:clé_app »). Un périmètre est un service
APM. Un document est une journée UTC terminée : sa version est sa date, une journée passée donne toujours les mêmes
chiffres, donc une citation reste vérifiable.
"""
import datetime
import json
import os
import re
import urllib.error
import urllib.request
from urllib.parse import urlencode

from jumeau import lecteurs
from jumeau.atlassian import MAX_REPONSE
from jumeau.github import DELAI, MAX_RESULTATS, Invalide, JetonRefuse, TropDeDemandes, _limiter, _memo, _SansRedirection
from jumeau.naissance import hote_public, _resultat, resoudre_secret

CLE = re.compile(r"[A-Za-z0-9]{8,80}")
NOM_SERVICE = re.compile(r"[A-Za-z0-9][\w.-]{0,99}")
JOUR = re.compile(r"\d{4}-\d{2}-\d{2}")
PREFIXE, SERVICE = "dd-", "Datadog"
MAX_SERVICES = 100  # ponytail : les 100 premiers services du catalogue ; recherche côté Datadog au-delà
MAX_LIENS = 50  # services listés par sens d'appel
DOCUMENTS = ("comportement", "dependances")

_ouvrir = urllib.request.build_opener(_SansRedirection).open


def identifiants(cle_api, cle_app):
    """Les deux clés en un secret « clé_api:clé_app » pour Vault."""
    cle_api, cle_app = cle_api.strip(), cle_app.strip()
    if not (CLE.fullmatch(cle_api) and CLE.fullmatch(cle_app)):
        raise Invalide("clé d'API et clé d'application attendues (lettres et chiffres)")
    return f"{cle_api}:{cle_app}"


def _hote():
    hote = os.environ.get("JUMEAU_DATADOG_HOTE", "").lower()
    if not hote or not hote_public(hote):
        raise Invalide("hôte Datadog non configuré (JUMEAU_DATADOG_HOTE, ex. api.datadoghq.eu)")
    return hote


def _aujourdhui():
    return datetime.datetime.now(datetime.timezone.utc).date()


def _appeler(secret, chemin, params=None, corps=None):
    """GET (ou POST JSON si `corps`) sur l'hôte autorisé ; erreurs typées, jamais les clés dans un message."""
    cle_api, deux_points, cle_app = (secret or "").partition(":")
    if not (deux_points and CLE.fullmatch(cle_api) and CLE.fullmatch(cle_app)):
        raise Invalide("aucune clé : Datadog demande une clé d'API et une clé d'application")
    _limiter(secret, SERVICE)
    url = f"https://{_hote()}{chemin}" + (f"?{urlencode(params)}" if params else "")
    en_tetes = {"DD-API-KEY": cle_api, "DD-APPLICATION-KEY": cle_app, "Accept": "application/json"}
    if corps is not None:
        en_tetes["Content-Type"] = "application/json"
    requete = urllib.request.Request(url, headers=en_tetes, data=json.dumps(corps).encode() if corps is not None else None)
    try:
        with _ouvrir(requete, timeout=DELAI) as r:
            lu = r.read(MAX_REPONSE + 1)
        if len(lu) > MAX_REPONSE:
            raise ValueError("réponse de Datadog trop volumineuse")
        return json.loads(lu)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise TropDeDemandes("quota Datadog atteint : réessayez dans une minute") from e
        if e.code in (401, 403):
            raise JetonRefuse("Datadog refuse ces clés") from e
        if e.code == 404:
            raise LookupError("introuvable") from e
        raise


def compte_du_jeton(secret):
    """Vérifie les clés auprès de Datadog avant de les conserver : l'identité est celle de l'utilisateur de la clé
    d'application, jamais une saisie."""
    d = _appeler(secret, "/api/v2/current_user").get("data") or {}
    email = ((d.get("attributes") or {}).get("email") or "").lower()
    if not d.get("id") or not email:
        raise Invalide("Datadog n'a pas identifié le propriétaire de ces clés")
    return {"login": email, "compte": str(d["id"]), "nom": d["attributes"].get("name") or email}


def _service(nom):
    if not NOM_SERVICE.fullmatch(nom or ""):
        raise Invalide("nom de service invalide")
    return nom


def perimetres(reference, recherche=""):
    """Services du catalogue Datadog lisibles avec ces clés, filtrés par `recherche`."""
    tous = _memo(reference, "services", lambda: [
        {"cle": n, "nom": n} for n in sorted({
            ((d.get("attributes") or {}).get("schema") or {}).get("dd-service") or ""
            for d in _appeler(resoudre_secret(reference), "/api/v2/services/definitions",
                              {"page[size]": MAX_SERVICES}).get("data", [])} - {""}) if NOM_SERVICE.fullmatch(n)])
    motif = recherche.strip().lower()
    return [s for s in tous if motif in s["cle"].lower()][:MAX_RESULTATS]


def _fenetre(jour):
    debut = datetime.datetime.combine(jour, datetime.time(), datetime.timezone.utc)
    return debut, debut + datetime.timedelta(days=1)


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _agreger(secret, service, jour, erreurs=False):
    """(requêtes, latence p95 en ms) du service sur la journée ; seuls les spans d'entrée du service comptent."""
    debut, fin = _fenetre(jour)
    requete = f"service:{service} @_top_level:1" + (" status:error" if erreurs else "")
    corps = {"data": {"type": "aggregate_request", "attributes": {
        "compute": [{"aggregation": "count", "type": "total"}, {"aggregation": "pc95", "metric": "@duration", "type": "total"}],
        "filter": {"from": _iso(debut), "to": _iso(fin), "query": requete}}}}
    buckets = _appeler(secret, "/api/v2/spans/analytics/aggregate", corps=corps).get("data") or []
    calcul = ((buckets[0].get("attributes") or {}).get("compute") or {}) if buckets else {}
    return int(calcul.get("c0") or 0), float(calcul.get("c1") or 0) / 1e6


def _mesure(reference, service, jour):
    """{requetes, erreurs, p95} du jour ; LookupError si le service n'a eu aucune requête ce jour-là."""
    def calcul():
        secret = resoudre_secret(reference)
        requetes, p95 = _agreger(secret, _service(service), jour)
        return {"requetes": requetes, "erreurs": _agreger(secret, service, jour, erreurs=True)[0] if requetes else 0, "p95": p95}
    m = _memo(reference, ("mesure", service, jour), calcul)
    if not m["requetes"]:
        raise LookupError("aucune requête observée")
    return m


def _variation(actuel, avant, forme, ecart=False):
    if avant is None:
        return f"{forme(actuel)} (semaine précédente : aucune donnée)"
    pct = f", {(actuel - avant) / avant * 100:+.1f} %" if ecart and avant else ""
    return f"{forme(actuel)} (semaine précédente : {forme(avant)}{pct})".replace(".", ",")


def _lignes_comportement(reference, service, jour):
    m = _mesure(reference, service, jour)
    try:
        p = _mesure(reference, service, jour - datetime.timedelta(days=7))
    except LookupError:
        p = None
    taux = lambda x: x["erreurs"] / x["requetes"] * 100
    avant = lambda f: p and f(p)
    return [f"Service {service}, journée du {jour} (UTC)",
            "Requêtes : " + _variation(m["requetes"], avant(lambda x: x["requetes"]), str, ecart=True),
            "Taux d'erreurs : " + _variation(taux(m), avant(taux), lambda v: f"{v:.2f} %"),
            "Latence p95 : " + _variation(m["p95"], avant(lambda x: x["p95"]), lambda v: f"{v:.0f} ms")]


def _lignes_dependances(reference, service, jour):
    debut, fin = _fenetre(jour)
    def calcul():
        return _appeler(resoudre_secret(reference), "/api/v1/service_dependencies", {
            "env": os.environ.get("JUMEAU_DATADOG_ENV", "prod"), "start": int(debut.timestamp()), "end": int(fin.timestamp())})
    tout = _memo(reference, ("dependances", jour), calcul)
    if service not in tout:
        raise LookupError("service inconnu")
    appelles = sorted(set((tout[service] or {}).get("calls") or []) - {service})[:MAX_LIENS]
    appelants = sorted(n for n, d in tout.items() if n != service and service in ((d or {}).get("calls") or []))[:MAX_LIENS]
    return [*(f"Appelle {n}" for n in appelles), *(f"Appelé par {n}" for n in appelants)] or ["Aucun appel observé"]


class LecteurDatadog(lecteurs.Lecteur):
    systeme = "datadog"

    def __init__(self, nom, espace, reference):
        super().__init__(nom, espace)
        self.reference = reference

    def _derniere_journee(self):
        return _aujourdhui() - datetime.timedelta(days=1)

    def version_courante(self):
        """Dernière journée complète : elle avance chaque jour."""
        return str(self._derniere_journee())

    def _jour(self, version):
        if version is None:
            return self._derniere_journee()
        try:
            jour = datetime.date.fromisoformat(version) if JOUR.fullmatch(version) else None
        except ValueError:
            jour = None
        return jour if jour and jour < _aujourdhui() else None  # une journée en cours n'est pas encore un fait

    def _moniteurs(self, texte):
        params = {"monitor_tags": f"service:{_service(self.espace)}", "name": texte, "page_size": MAX_RESULTATS}
        return _appeler(resoudre_secret(self.reference), "/api/v1/monitor", params)

    def _chercher(self, texte):
        motif = texte.lower()
        if not motif:
            return
        for ref in DOCUMENTS:
            try:
                doc = self._lire(ref, None)
            except LookupError:
                continue
            trouvees = [l for l in doc["lignes"] if motif in l.lower()] if doc else []
            if trouvees:
                yield {"ref": ref, "titre": f"{ref} {doc['version']}", "extrait": trouvees[0]}
        for m in self._moniteurs(texte):  # un moniteur se lit dans le comportement du service
            yield {"ref": "comportement", "titre": f"Moniteur : {m.get('name', '')}", "extrait": str(m.get("overall_state", ""))}

    def _lire(self, ref, version):
        service = _service(self.espace)
        jour = self._jour(version)
        if ref not in DOCUMENTS or jour is None:
            return None
        lignes = _lignes_comportement if ref == "comportement" else _lignes_dependances
        try:
            return {"titre": f"{ref} {service} {jour}", "version": str(jour), "lignes": lignes(self.reference, service, jour)}
        except LookupError:
            return None


lecteurs.FABRIQUES["DATADOG"] = lambda s: LecteurDatadog(s["nom"], s["emplacement"], s["secret_ref"])


def source_de(config):
    """Ligne de la table `source` d'une source Datadog prête de la commande."""
    if not NOM_SERVICE.fullmatch(config.get("service") or ""):
        raise ValueError("nom de service Datadog invalide")
    return {"type": "DATADOG", "nom": f"datadog-{config['service']}", "emplacement": config["service"], "curseur": None,
            "url": f"https://app.{_hote().removeprefix('api.')}/apm/services/{config['service']}", "secret_ref": config.get("secret")}


def tester(config):
    """Test réel : clés acceptées et service observé hier ? Premier échec rapporté."""
    service = (config.get("service") or "").strip()
    if not service:
        return _resultat("configuration_incomplete", "Configuration incomplète", "Aucun service choisi.", "Choisir un service")
    if not config.get("secret"):
        return _resultat("autorisation_insuffisante", "Clés introuvables", "Aucune connexion Datadog choisie.",
                         "Choisir ou déclarer une connexion")
    try:
        _mesure(config["secret"], service, _aujourdhui() - datetime.timedelta(days=1))
    except Invalide as e:
        return _resultat("configuration_incomplete", "Configuration incomplète", str(e), "Corriger la configuration")
    except JetonRefuse:
        return _resultat("autorisation_insuffisante", "Accès refusé", "Datadog refuse ces clés.", "Déclarer à nouveau la connexion")
    except LookupError:
        return _resultat("perimetre_vide", "Service sans trafic", f"Aucune requête observée hier pour « {service} ».", "Corriger le service")
    except (RuntimeError, ValueError, OSError, TropDeDemandes):
        return _resultat("erreur_connexion", "Datadog injoignable", "Datadog n'a pas répondu.", "Vérifier le réseau")
    return _resultat("prete")
