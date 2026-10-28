"""Lecteur ServiceNow (API Table) : comment l'application échoue (incidents, problèmes, changements).

Mêmes garde-fous que Jira : « utilisateur:mot de passe » d'un compte de service en lecture seule dans Vault, seule
l'instance autorisée (JUMEAU_SERVICENOW_HOTE) est interrogée, en HTTPS, sans redirection. Un périmètre est un
élément de configuration applicatif (CI) ; un enregistrement est lu en texte, sans appelant ni agent (seulement le
groupe d'affectation). Sa version est son nombre de modifications : ServiceNow ne sert pas les anciennes versions,
une citation périmée échoue donc à la vérification.
"""
import re
import urllib.request

from jumeau import atlassian, lecteurs
from jumeau.github import MAX_RESULTATS, Invalide, JetonRefuse, TropDeDemandes, _memo, _SansRedirection
from jumeau.naissance import _resultat, resoudre_secret

NOM_CI = re.compile(r"\w[\w .-]{0,79}")  # ni ^, ni =, ni deux-points : rien qui change une requête encodée
UTILISATEUR = re.compile(r"[\w.@-]{1,100}")
REF_ENREGISTREMENT = re.compile(r"(INC|PRB|CHG)\d{7,10}")
TABLES = {"INC": "incident", "PRB": "problem", "CHG": "change_request"}
PREFIXE, SERVICE = "sn-", "ServiceNow"
MAX_CI = 250  # ponytail : les 250 premiers CI applicatifs ; recherche côté ServiceNow si une instance en compte davantage
# Seuls ces champs sont demandés : jamais caller_id, opened_by, assigned_to… (données personnelles).
COMMUN = [("priority", "Priorité"), ("state", "État"), ("opened_at", "Ouvert le"), ("resolved_at", "Résolu le"),
          ("assignment_group", "Groupe d'affectation")]
CHAMPS = {"incident": [*COMMUN, ("close_notes", "Notes de clôture")],
          "problem": [*COMMUN, ("cause_notes", "Cause"), ("fix_notes", "Correctif"), ("close_notes", "Notes de clôture")],
          "change_request": [*COMMUN, ("type", "Type de changement"), ("risk", "Risque"), ("close_notes", "Notes de clôture")]}

_ouvrir = urllib.request.build_opener(_SansRedirection).open


def hote_autorise(hote=None):
    """Instance de la connexion, validée (*.service-now.com) ; JUMEAU_SERVICENOW_HOTE, si définie, la remplace."""
    return atlassian.choisir_hote(SERVICE, "JUMEAU_SERVICENOW_HOTE", "banque.service-now.com",
                                  atlassian.sous_domaine_de("service-now.com"), hote)


def identifiants(utilisateur, mot_de_passe):
    utilisateur, mot_de_passe = utilisateur.strip(), mot_de_passe.strip()
    if not UTILISATEUR.fullmatch(utilisateur):
        raise Invalide("nom d'utilisateur ServiceNow attendu")
    return f"{utilisateur}:{mot_de_passe}"


def _get_avec(secret, hote, chemin, **params):
    return atlassian.appeler(_ouvrir, SERVICE, lambda: hote_autorise(hote), secret, chemin, params)["result"]


def _table(secret, table, requete, champs, limite, hote=None):
    return _get_avec(secret, hote, f"/api/now/table/{table}", sysparm_query=requete, sysparm_fields=champs,
                     sysparm_limit=limite, sysparm_display_value="true")


def compte_du_jeton(secret, hote=None):
    """Identité du compte chez ServiceNow (sys_id), jamais le nom saisi seul ; aucun nom de personne conservé."""
    declare = secret.partition(":")[0]
    if not UTILISATEUR.fullmatch(declare):
        raise Invalide("nom d'utilisateur ServiceNow attendu")
    trouves = _table(secret, "sys_user", f"user_name={declare}", "sys_id,user_name", 1, hote)
    if not trouves or not trouves[0].get("sys_id") or (trouves[0].get("user_name") or "").lower() != declare.lower():
        raise Invalide("ServiceNow n'a pas identifié le compte de ces identifiants")
    return {"login": declare, "compte": trouves[0]["sys_id"], "nom": declare}


def _ci(nom):
    if not NOM_CI.fullmatch(nom or ""):
        raise Invalide("nom d'élément de configuration invalide")
    return nom


def perimetres(reference, recherche="", hote=None):
    """CI applicatifs lisibles avec ces identifiants, filtrés par `recherche`."""
    secret = resoudre_secret(reference)
    tous = _memo(reference, "ci", lambda: [
        {"cle": c["name"], "nom": c.get("short_description") or c["name"]}
        for c in _table(secret, "cmdb_ci_appl", "ORDERBYname", "name,short_description", MAX_CI, hote)
        if NOM_CI.fullmatch(c.get("name") or "")])
    motif = recherche.strip().lower()
    return [p for p in tous if motif in p["cle"].lower() or motif in p["nom"].lower()][:MAX_RESULTATS]


def _chiffres(date):
    return re.sub(r"\D", "", date or "")


class LecteurServiceNow(lecteurs.Lecteur):
    systeme = "servicenow"

    def __init__(self, nom, espace, reference, hote=None):
        super().__init__(nom, espace)
        self.reference, self.hote = reference, hote

    def _filtre(self):
        return f"cmdb_ci.name={_ci(self.espace)}"

    def _table(self, table, requete, champs, limite):
        return _table(resoudre_secret(self.reference), table, requete, champs, limite, self.hote)

    def version_courante(self):
        """Dernier enregistrement modifié de chaque table et sa date de mise à jour."""
        recents = [self._table(t, f"{self._filtre()}^ORDERBYDESCsys_updated_on", "number,sys_updated_on", 1)
                   for t in TABLES.values()]
        return ",".join(f"{r[0]['number']}@{_chiffres(r[0].get('sys_updated_on'))}" for r in recents if r)

    def _chercher(self, texte):
        motif = " ".join(re.sub(r"[^\w\s.]", " ", texte).split())  # ni ^, ni =, ni deux-points
        if not motif:
            return
        filtre = f"{self._filtre()}^short_descriptionLIKE{motif}^ORDERBYDESCopened_at"
        for table in TABLES.values():
            for e in self._table(table, filtre, "number,short_description", MAX_RESULTATS):
                yield {"ref": e["number"], "titre": e.get("short_description") or ""}

    def _lire(self, ref, version):
        # un enregistrement d'un autre CI n'est pas une preuve de celui-ci (et le filtre le dit à ServiceNow)
        if not REF_ENREGISTREMENT.fullmatch(ref):
            return None
        table = TABLES[ref[:3]]
        champs = CHAMPS[table]
        e = _memo(self.reference, ("enregistrement", ref), lambda: self._table(
            table, f"number={ref}^{self._filtre()}",
            ",".join(["number", "short_description", "cmdb_ci", "sys_mod_count", *(c for c, _ in champs)]), 1))
        if not e or (e[0].get("cmdb_ci") or "").lower() != self.espace.lower():
            return None
        e = e[0]
        lignes = [e.get("short_description") or "", f"Numéro : {e['number']}", f"Type : {table.replace('_request', '')}"]
        for cle, libelle in champs:
            valeur = e.get(cle)
            if isinstance(valeur, str):
                lignes += [f"{libelle} : {l}" for l in (" ".join(x.split()) for x in valeur.split("\n")) if l]
        return {"titre": f"{e['number']} {e.get('short_description') or ''}", "version": e.get("sys_mod_count") or "0",
                "lignes": lignes}


lecteurs.FABRIQUES["SERVICENOW"] = lambda s: LecteurServiceNow(s["nom"], s["emplacement"], s["secret_ref"], atlassian.hote_de_url(s.get("url")))


def source_de(config):
    """Ligne de la table `source` d'une source ServiceNow prête de la commande."""
    if not NOM_CI.fullmatch(config.get("ci") or ""):
        raise ValueError("nom d'élément de configuration invalide")
    return {"type": "SERVICENOW", "nom": f"servicenow-{config['ci']}", "emplacement": config["ci"], "curseur": None,
            "url": f"https://{hote_autorise(config.get('hote'))}/", "secret_ref": config.get("secret")}


def tester(config):
    """Test réel : identifiants acceptés, CI existant, incidents lisibles ? Premier échec rapporté."""
    ci = (config.get("ci") or "").strip()
    if not ci:
        return _resultat("configuration_incomplete", "Configuration incomplète", "Aucun élément de configuration choisi.", "Choisir un CI")
    if not config.get("secret"):
        return _resultat("autorisation_insuffisante", "Identifiants introuvables", "Aucune connexion ServiceNow choisie.",
                         "Choisir ou déclarer une connexion")
    try:
        secret, hote = resoudre_secret(config["secret"]), config.get("hote")
        existe = _table(secret, "cmdb_ci_appl", f"name={_ci(ci)}", "name", 1, hote)
        _table(secret, "incident", f"cmdb_ci.name={ci}", "number", 1, hote)
    except Invalide as e:
        return _resultat("configuration_incomplete", "Configuration incomplète", str(e), "Corriger la configuration")
    except JetonRefuse:
        return _resultat("autorisation_insuffisante", "Accès refusé", "ServiceNow refuse ces identifiants ou la lecture des incidents.",
                         "Déclarer à nouveau la connexion")
    except (RuntimeError, ValueError, LookupError, OSError, TropDeDemandes):
        return _resultat("erreur_connexion", "ServiceNow injoignable", "ServiceNow n'a pas répondu.", "Vérifier le réseau")
    if not existe:
        return _resultat("perimetre_vide", "CI introuvable", f"L'élément « {ci} » n'existe pas ou n'est pas lisible.", "Corriger le CI")
    return _resultat("prete")
