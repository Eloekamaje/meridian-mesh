"""Lecteur Confluence Cloud (API REST v2) : premier vrai lecteur de documentation du jumeau.

Identifiants (e-mail + jeton d'API) lus dans Vault sous la forme « e-mail:jeton » ; ils ne quittent jamais le serveur.
Seul l'hôte autorisé (JUMEAU_CONFLUENCE_HOTE) est interrogé, en HTTPS, sans suivre de redirection. Le contenu lu est
du texte : le HTML de stockage n'est jamais exécuté.
"""
import base64
import json
import os
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import quote, urlencode

from jumeau import lecteurs
from jumeau.github import (DELAI, MAX_RESULTATS, Invalide, JetonRefuse, TropDeDemandes, _limiter, _memo,
                           _SansRedirection)
from jumeau.naissance import HOTE_VALIDE, _resultat, resoudre_secret

CLE_ESPACE = re.compile(r"[A-Za-z0-9_~-]{1,255}")
REF_PAGE = re.compile(r"\d{1,19}")
MAX_ESPACES = 250  # ponytail : les 250 premiers espaces ; recherche côté Confluence si un compte en voit davantage

_ouvrir = urllib.request.build_opener(_SansRedirection).open


def _hote():
    hote = os.environ.get("JUMEAU_CONFLUENCE_HOTE", "").lower()
    if not hote or not HOTE_VALIDE.fullmatch(hote):
        raise Invalide("hôte Confluence non configuré (JUMEAU_CONFLUENCE_HOTE, ex. banque.atlassian.net)")
    return hote


def identifiants(email, jeton):
    email, jeton = email.strip(), jeton.strip()
    if ":" in email or "@" not in email:
        raise Invalide("adresse e-mail attendue")
    return f"{email}:{jeton}"


def _get_avec(secret, chemin, **params):
    if not secret:
        raise Invalide("aucun jeton : Confluence demande une adresse e-mail et un jeton d'API")
    email, deux_points, jeton = secret.partition(":")
    if not (deux_points and email and jeton) or not secret.isascii() or not secret.isprintable() or " " in secret:
        raise Invalide("identifiants mal formés")
    _limiter(secret, "Confluence")
    url = f"https://{_hote()}{chemin}" + (f"?{urlencode(params)}" if params else "")
    requete = urllib.request.Request(url, headers={
        "Authorization": "Basic " + base64.b64encode(secret.encode()).decode(), "Accept": "application/json"})
    try:
        with _ouvrir(requete, timeout=DELAI) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise TropDeDemandes("quota Confluence atteint : réessayez dans une minute") from e
        if e.code in (401, 403):
            raise JetonRefuse("Confluence refuse ces identifiants") from e
        if e.code == 404:
            raise LookupError("introuvable") from e
        raise


def _get(reference, chemin, **params):
    return _get_avec(resoudre_secret(reference), chemin, **params)


def compte_du_jeton(secret):
    """Vérifie les identifiants auprès de Confluence avant de les conserver (un refus n'écrase rien)."""
    u = _get_avec(secret, "/wiki/rest/api/user/current")
    return {"login": secret.partition(":")[0], "nom": u.get("displayName") or secret.partition(":")[0]}


def _id_espace(reference, cle):
    if not CLE_ESPACE.fullmatch(cle or ""):
        raise Invalide("clé d'espace invalide")

    def chercher():
        trouve = [s for s in _get(reference, "/wiki/api/v2/spaces", keys=cle)["results"] if s["key"].lower() == cle.lower()]
        if not trouve:
            raise LookupError(f"espace {cle} introuvable")
        return trouve[0]["id"]
    return _memo(reference, ("id-espace", cle), chercher)


def espaces(reference, recherche=""):
    """Espaces lisibles avec ces identifiants, filtrés par `recherche` (liste lue une fois puis filtrée ici)."""
    tous = _memo(reference, "espaces", lambda: [
        {"cle": s["key"], "nom": s["name"]}
        for s in _get(reference, "/wiki/api/v2/spaces", limit=MAX_ESPACES, status="current")["results"]])
    motif = recherche.strip().lower()
    return [s for s in tous if motif in s["cle"].lower() or motif in s["nom"].lower()][:MAX_RESULTATS]


class _Texte(HTMLParser):
    """HTML de stockage → lignes : une par paragraphe, titre, élément de liste ou ligne de tableau."""
    BLOCS = {"p", "div", "br", "ul", "ol", "table", "tr", "pre", "blockquote", "li", "h1", "h2", "h3", "h4", "h5", "h6"}
    IGNORES = {"script", "style"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lignes, self._courante, self._ignore = [], [], 0

    def _clore(self):
        texte = " ".join("".join(self._courante).split()).strip(" |")
        if texte.strip("#- |"):  # ni titre ni puce sans texte
            self.lignes.append(texte)
        self._courante = []

    def handle_starttag(self, tag, attrs):
        if tag in self.IGNORES:
            self._ignore += 1
        if tag in self.BLOCS:
            self._clore()
            if tag == "li":
                self._courante.append("- ")
            elif tag[0] == "h" and tag[1:].isdigit():
                self._courante.append("#" * int(tag[1]) + " ")

    def handle_endtag(self, tag):
        if tag in self.IGNORES:
            self._ignore = max(0, self._ignore - 1)
        if tag in self.BLOCS:
            self._clore()
        elif tag in ("td", "th"):
            self._courante.append(" | ")

    def handle_data(self, data):
        if not self._ignore:
            self._courante.append(data)


def en_lignes(html):
    """Texte d'une page (HTML de stockage), analysé et jamais exécuté."""
    p = _Texte()
    p.feed(html or "")
    p.close()
    p._clore()
    return p.lignes


class LecteurConfluence(lecteurs.Lecteur):
    systeme = "confluence"

    def __init__(self, nom, espace, reference):
        super().__init__(nom, espace)
        self.reference = reference

    def version_courante(self):
        """Dernière modification de l'espace : page la plus récemment modifiée, sa version et sa date."""
        id_espace = _id_espace(self.reference, self.espace)
        r = _get(self.reference, f"/wiki/api/v2/spaces/{quote(str(id_espace))}/pages", sort="-modified-date", limit=1)
        if not r["results"]:
            return ""
        p = r["results"][0]
        return f"{p['id']}@{p['version']['number']}:{p['version'].get('createdAt', '')}"

    def _chercher(self, texte):
        if not CLE_ESPACE.fullmatch(self.espace):
            raise Invalide("clé d'espace invalide")
        motif = re.sub(r'["\\]', "", texte)
        cql = f'space="{self.espace}" and text ~ "{motif}"'
        for r in _get(self.reference, "/wiki/rest/api/search", cql=cql, limit=MAX_RESULTATS)["results"]:
            if (r.get("content") or {}).get("id"):
                yield {"ref": r["content"]["id"], "titre": r.get("title") or "",
                       "extrait": " ".join(en_lignes(re.sub(r"@@@(end)?hl@@@", "", r.get("excerpt") or "")))}

    def _lire(self, ref, version):
        if not REF_PAGE.fullmatch(ref):
            return None
        params = {"body-format": "storage", **({"version": version} if version else {})}
        try:
            p = _memo(self.reference, ("page", ref, version), lambda: _get(
                self.reference, f"/wiki/api/v2/pages/{ref}", **params))
            if str(p.get("spaceId")) != str(_id_espace(self.reference, self.espace)):
                return None  # une page d'un autre espace n'est pas une preuve de celui-ci
        except LookupError:
            return None
        return {"titre": p["title"], "version": p["version"]["number"], "lignes": en_lignes(p["body"]["storage"]["value"])}


lecteurs.FABRIQUES["CONFLUENCE"] = lambda s: LecteurConfluence(s["nom"], s["emplacement"], s["secret_ref"])


def source_de(config):
    """Ligne de la table `source` d'une source Confluence prête de la commande."""
    return {"type": "CONFLUENCE", "nom": f"confluence-{config['espace']}", "emplacement": config["espace"],
            "curseur": None, "url": f"https://{_hote()}/wiki/spaces/{config['espace']}", "secret_ref": config.get("secret")}


def tester(config):
    """Test réel : identifiants acceptés et espace lisible ? Premier échec rapporté."""
    espace = (config.get("espace") or "").strip()
    if not espace:
        return _resultat("configuration_incomplete", "Configuration incomplète", "Aucun espace choisi.", "Choisir un espace")
    if not config.get("secret"):
        return _resultat("autorisation_insuffisante", "Jeton introuvable", "Aucune connexion Confluence choisie.",
                         "Choisir ou déclarer une connexion")
    try:
        _id_espace(config["secret"], espace)
    except Invalide as e:
        return _resultat("configuration_incomplete", "Configuration incomplète", str(e), "Corriger la configuration")
    except JetonRefuse:
        return _resultat("autorisation_insuffisante", "Accès refusé", "Confluence refuse ces identifiants.",
                         "Déclarer à nouveau la connexion")
    except LookupError:
        return _resultat("perimetre_vide", "Espace introuvable", f"L'espace « {espace} » n'existe pas ou n'est pas lisible.",
                         "Corriger l'espace")
    except (RuntimeError, ValueError, OSError, TropDeDemandes):
        return _resultat("erreur_connexion", "Confluence injoignable", "Confluence n'a pas répondu.", "Vérifier le réseau")
    return _resultat("prete")
