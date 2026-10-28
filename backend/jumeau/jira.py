"""Lecteur Jira Cloud (API REST v3) : la trajectoire de l'application (pourquoi elle a changé, ce qui est prévu).

Mêmes garde-fous que Confluence : identifiants « e-mail:jeton » dans Vault, seul l'hôte autorisé (JUMEAU_JIRA_HOTE)
est interrogé, en HTTPS, sans redirection. Un périmètre est un projet ; un ticket est lu en texte (la description
ADF est parcourue, jamais interprétée) et sa version est sa date de mise à jour : si le ticket a changé, une
citation ancienne ne se vérifie plus.
"""
import os
import re
import urllib.request

from jumeau import atlassian, lecteurs
from jumeau.github import MAX_RESULTATS, Invalide, JetonRefuse, TropDeDemandes, _memo, _SansRedirection
from jumeau.naissance import hote_public, _resultat, resoudre_secret

CLE_PROJET = re.compile(r"[A-Z][A-Z0-9_]{1,19}")
REF_TICKET = re.compile(r"[A-Z][A-Z0-9_]{1,19}-\d{1,9}")
PREFIXE, SERVICE = "jr-", "Jira"
MAX_PROJETS = 100  # plafond de project/search (swagger Jira v3) ; ponytail : les 100 premiers projets ; recherche côté Jira si un compte en voit davantage
PROFONDEUR_ADF = 20  # un document plus imbriqué n'est pas lu plus loin

_ouvrir = urllib.request.build_opener(_SansRedirection).open
identifiants = atlassian.identifiants


def _hote():
    hote = os.environ.get("JUMEAU_JIRA_HOTE", "").lower()
    if not hote or not hote_public(hote):
        raise Invalide("hôte Jira non configuré (JUMEAU_JIRA_HOTE, ex. banque.atlassian.net)")
    return hote


def _get_avec(secret, chemin, **params):
    return atlassian.appeler(_ouvrir, SERVICE, _hote, secret, chemin, params)


def _get(reference, chemin, **params):
    return _get_avec(resoudre_secret(reference), chemin, **params)


def compte_du_jeton(secret):
    """Vérifie les identifiants auprès de Jira avant de les conserver (un refus n'écrase rien)."""
    return atlassian.compte(_get_avec(secret, "/rest/api/3/myself"), secret, "emailAddress")


def _projet(cle):
    if not CLE_PROJET.fullmatch(cle or ""):
        raise Invalide("clé de projet invalide")
    return cle


def perimetres(reference, recherche=""):
    """Projets lisibles avec ces identifiants, filtrés par `recherche`."""
    tous = _memo(reference, "projets", lambda: [
        {"cle": p["key"], "nom": p["name"]}
        for p in _get(reference, "/rest/api/3/project/search", maxResults=MAX_PROJETS)["values"]])
    motif = recherche.strip().lower()
    return [p for p in tous if motif in p["cle"].lower() or motif in p["nom"].lower()][:MAX_RESULTATS]


def _texte(noeud):
    """Texte en ligne d'un nœud ADF."""
    type_, attrs = noeud.get("type"), noeud.get("attrs") or {}
    if type_ == "text":
        return noeud.get("text", "")
    if type_ == "hardBreak":
        return "\n"
    if type_ == "mention":
        return "[personne]"  # jamais le nom d'une personne mentionnée
    if type_ == "emoji":
        return attrs.get("shortName", "")
    if type_ == "inlineCard":
        return attrs.get("url", "")
    return "".join(_texte(e) for e in noeud.get("content", []) if isinstance(e, dict))


def en_lignes(adf, profondeur=0):
    """Document ADF → lignes : une par paragraphe, titre, puce ou ligne de tableau. Média et nœuds inconnus sont ignorés."""
    if not isinstance(adf, dict) or profondeur > PROFONDEUR_ADF:
        return []
    type_, enfants = adf.get("type"), [e for e in adf.get("content", []) if isinstance(e, dict)]

    def lignes(texte, prefixe=""):
        return [prefixe + l for l in (" ".join(x.split()) for x in texte.split("\n")) if l]
    if type_ in ("paragraph", "codeBlock"):
        return lignes(_texte(adf))
    if type_ == "heading":
        return lignes(_texte(adf), "#" * int((adf.get("attrs") or {}).get("level", 1)) + " ")
    if type_ == "tableRow":
        return lignes(" | ".join(" ".join(en_lignes(c, profondeur + 1)) for c in enfants))
    suite = [l for e in enfants for l in en_lignes(e, profondeur + 1)]
    return [f"- {suite[0]}", *suite[1:]] if type_ == "listItem" and suite else suite


def _version(ticket):
    return re.sub(r"\D", "", ticket["fields"].get("updated") or "")  # la date de mise à jour, sans ponctuation


class LecteurJira(lecteurs.Lecteur):
    systeme = "jira"

    def __init__(self, nom, espace, reference):
        super().__init__(nom, espace)
        self.reference = reference

    def _jql(self, filtre=""):
        return f'project = "{_projet(self.espace)}"' + filtre

    def version_courante(self):
        """Dernier ticket modifié du projet et sa date de mise à jour."""
        r = _get(self.reference, "/rest/api/3/search/jql", jql=self._jql() + " ORDER BY updated DESC",
                 fields="updated", maxResults=1)
        return f"{r['issues'][0]['key']}@{_version(r['issues'][0])}" if r["issues"] else ""

    def _chercher(self, texte):
        motif = " ".join(re.sub(r"[^\w\s.]", " ", texte).split())  # ni guillemet, ni barre oblique, ni opérateur
        if not motif:
            return
        r = _get(self.reference, "/rest/api/3/search/jql", jql=self._jql(f' AND text ~ "{motif}"'),
                 fields="summary", maxResults=MAX_RESULTATS)
        for t in r["issues"]:
            yield {"ref": t["key"], "titre": t["fields"].get("summary") or ""}

    def _lire(self, ref, version):
        # un ticket d'un autre projet n'est pas une preuve de celui-ci (et on ne l'interroge même pas)
        if not REF_TICKET.fullmatch(ref) or not ref.startswith(f"{_projet(self.espace)}-"):
            return None
        try:
            t = _memo(self.reference, ("ticket", ref), lambda: _get(
                self.reference, f"/rest/api/3/issue/{ref}",
                fields="summary,issuetype,status,project,updated,description,comment"))
        except LookupError:
            return None
        f = t["fields"]
        if (f.get("project") or {}).get("key") != self.espace:  # ticket déplacé : l'ancienne clé le désigne encore
            return None
        lignes = [f.get("summary") or "", f"Type : {(f.get('issuetype') or {}).get('name', '')}",
                  f"Statut : {(f.get('status') or {}).get('name', '')}", *en_lignes(f.get("description"))]
        for c in (f.get("comment") or {}).get("comments", []):
            lignes += ["Commentaire :", *en_lignes(c.get("body"))]  # sans l'auteur : on garde le fait, pas la personne
        # Jira ne sert que le ticket tel qu'il est : une citation d'une version passée échoue à la vérification.
        return {"titre": f"{t['key']} {f.get('summary') or ''}", "version": _version(t), "lignes": lignes}


lecteurs.FABRIQUES["JIRA"] = lambda s: LecteurJira(s["nom"], s["emplacement"], s["secret_ref"])


def source_de(config):
    """Ligne de la table `source` d'une source Jira prête de la commande."""
    if not CLE_PROJET.fullmatch(config.get("projet") or ""):
        raise ValueError("clé de projet Jira invalide")
    return {"type": "JIRA", "nom": f"jira-{config['projet']}", "emplacement": config["projet"],
            "curseur": None, "url": f"https://{_hote()}/projects/{config['projet']}", "secret_ref": config.get("secret")}


def tester(config):
    """Test réel : identifiants acceptés et projet lisible ? Premier échec rapporté."""
    projet = (config.get("projet") or "").strip()
    if not projet:
        return _resultat("configuration_incomplete", "Configuration incomplète", "Aucun projet choisi.", "Choisir un projet")
    if not config.get("secret"):
        return _resultat("autorisation_insuffisante", "Jeton introuvable", "Aucune connexion Jira choisie.",
                         "Choisir ou déclarer une connexion")
    try:
        _get(config["secret"], f"/rest/api/3/project/{_projet(projet)}")
    except Invalide as e:
        return _resultat("configuration_incomplete", "Configuration incomplète", str(e), "Corriger la configuration")
    except JetonRefuse:
        return _resultat("autorisation_insuffisante", "Accès refusé", "Jira refuse ces identifiants.",
                         "Déclarer à nouveau la connexion")
    except LookupError:
        return _resultat("perimetre_vide", "Projet introuvable", f"Le projet « {projet} » n'existe pas ou n'est pas lisible.",
                         "Corriger le projet")
    except (RuntimeError, ValueError, OSError, TropDeDemandes):
        return _resultat("erreur_connexion", "Jira injoignable", "Jira n'a pas répondu.", "Vérifier le réseau")
    return _resultat("prete")
