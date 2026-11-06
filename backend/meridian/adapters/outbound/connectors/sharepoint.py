"""Lecteur SharePoint / Microsoft Graph : recherche et lecture de documents d'entreprise.

La source est un site SharePoint (`emplacement` = hôte, `url` = URL du site). Les identifiants
viennent de l'environnement (`SHAREPOINT_TENANT_ID`, `SHAREPOINT_CLIENT_ID`,
`SHAREPOINT_CLIENT_SECRET`) ou du secret référencé par la source. Aucun jeton n'est rendu au
modèle : le lecteur ne rend que le texte, sa version et un locator vérifiable.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from meridian.adapters.outbound.connectors import lecteurs
from meridian.adapters.outbound.connectors.naissance import resoudre_secret
from meridian.adapters.outbound.connectors.github import MAX_RESULTATS, Invalide, JetonRefuse, TropDeDemandes, _SansRedirection

GRAPH = "https://graph.microsoft.com/v1.0"
_HOTE = "graph.microsoft.com"
_ouvrir = urllib.request.build_opener(_SansRedirection).open
_MEMO: dict[tuple[str, str], str] = {}
_REF = re.compile(r"[A-Za-z0-9_-]{8,200}")
_VERSION = re.compile(r"[A-Za-z0-9_.-]{1,80}")


class _TexteHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lignes, self._courante, self._ignore = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self._ignore += 1
        if tag in {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._clore()

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self._ignore = max(0, self._ignore - 1)
        if tag in {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._clore()

    def handle_data(self, data):
        if not self._ignore:
            self._courante.append(data)

    def _clore(self):
        texte = " ".join("".join(self._courante).split()).strip()
        if texte:
            self.lignes.append(texte)
        self._courante = []


def _lignes_html(html: str) -> list[str]:
    p = _TexteHTML()
    p.feed(html or "")
    p.close()
    p._clore()
    return p.lignes


def _lignes_document(data: bytes, nom: str) -> list[str]:
    suffixe = (nom.rsplit(".", 1)[-1] if "." in nom else "").lower()
    if suffixe == "pdf":
        from io import BytesIO
        from pypdf import PdfReader
        return [" ".join((page.extract_text() or "").split()) for page in PdfReader(BytesIO(data)).pages if (page.extract_text() or "").strip()]
    if suffixe in {"docx", "doc"}:
        from io import BytesIO
        from docx import Document
        document = Document(BytesIO(data))
        return [" ".join(p.text.split()) for p in document.paragraphs if p.text.strip()]
    if suffixe in {"xlsx", "xlsm"}:
        from io import BytesIO
        from openpyxl import load_workbook
        classeur = load_workbook(BytesIO(data), read_only=True, data_only=True)
        lignes = []
        for feuille in classeur.worksheets:
            for ligne in feuille.iter_rows(values_only=True):
                texte = " | ".join("" if c is None else str(c) for c in ligne).strip()
                if texte.strip(" |"):
                    lignes.append(texte)
        return lignes
    texte = data.decode("utf-8", errors="replace")
    if suffixe in {"html", "htm"}:
        return _lignes_html(texte)
    return [ligne.strip() for ligne in texte.splitlines() if ligne.strip()]


def _oauth() -> str:
    jeton = os.getenv("SHAREPOINT_TOKEN", "").strip()
    if jeton:
        return jeton
    tenant = os.getenv("SHAREPOINT_TENANT_ID", "").strip()
    client = os.getenv("SHAREPOINT_CLIENT_ID", "").strip()
    secret = os.getenv("SHAREPOINT_CLIENT_SECRET", "").strip()
    if not (tenant and client and secret):
        raise Invalide("SharePoint : SHAREPOINT_TENANT_ID, CLIENT_ID et CLIENT_SECRET sont requis")
    corps = urllib.parse.urlencode({
        "client_id": client, "client_secret": secret,
        "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials",
    }).encode()
    requete = urllib.request.Request(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data=corps, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with _ouvrir(requete, timeout=10) as reponse:
        data = json.loads(reponse.read(1_000_000))
    return data["access_token"]


def _appeler(chemin: str, *, params=None, data=None) -> dict:
    url = GRAPH + chemin + (("?" + urllib.parse.urlencode(params)) if params else "")
    requete = urllib.request.Request(url, data=data, headers={
        "Authorization": f"Bearer {_oauth()}", "Accept": "application/json"})
    try:
        with _ouvrir(requete, timeout=15) as reponse:
            corps = reponse.read(8_000_000)
        return json.loads(corps)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise JetonRefuse("SharePoint refuse le jeton") from e
        if e.code == 429:
            raise TropDeDemandes("quota SharePoint atteint") from e
        if e.code == 404:
            raise LookupError("SharePoint : document introuvable") from e
        raise


def _telecharger(chemin: str) -> bytes:
    requete = urllib.request.Request(GRAPH + chemin, headers={"Authorization": f"Bearer {_oauth()}"})
    try:
        with _ouvrir(requete, timeout=15) as reponse:
            return reponse.read(20_000_000)
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            cible = e.headers.get("Location") or ""
            hote = urllib.parse.urlparse(cible).hostname or ""
            if hote.endswith(".sharepoint.com") or hote.endswith(".microsoft.com"):
                requete = urllib.request.Request(cible, headers={"Accept": "*/*"})
                with _ouvrir(requete, timeout=15) as reponse:
                    return reponse.read(20_000_000)
            raise Invalide("SharePoint : redirection de téléchargement non autorisée") from e
        if e.code == 401:
            raise JetonRefuse("SharePoint refuse le jeton") from e
        if e.code == 429:
            raise TropDeDemandes("quota SharePoint atteint") from e
        if e.code == 404:
            raise LookupError("SharePoint : document introuvable") from e
        raise


def _site_id(espace: str, url: str = "") -> str:
    direct = os.getenv("SHAREPOINT_SITE_ID", "").strip()
    if direct:
        return direct
    hote = espace.strip()
    if not re.fullmatch(r"[A-Za-z0-9.-]{3,255}", hote or ""):
        raise Invalide("site SharePoint invalide")
    chemin = urllib.parse.urlparse(url or "").path.strip("/")
    cle = (hote, chemin)
    if cle not in _MEMO:
        resultat = _appeler(f"/sites/{urllib.parse.quote(hote, safe='')}:/{chemin or ''}")
        _MEMO[cle] = resultat["id"]
    return _MEMO[cle]


def _ref(identifiant: str) -> str:
    return base64.urlsafe_b64encode(str(identifiant).encode()).decode().rstrip("=")


def _identifiant(ref: str) -> str:
    try:
        return base64.urlsafe_b64decode(ref + "=" * (-len(ref) % 4)).decode()
    except Exception:
        raise Invalide("référence SharePoint invalide")


def _version(item: dict) -> str:
    brut = str(item.get("eTag") or item.get("lastModifiedDateTime") or item.get("id") or "")
    return hashlib.sha256(brut.encode()).hexdigest()[:16]


class LecteurSharePoint(lecteurs.Lecteur):
    systeme = "sharepoint"

    def __init__(self, nom, espace, reference=None, url=""):
        super().__init__(nom, espace)
        self.reference, self.url = reference, url

    def version_courante(self):
        site = _site_id(self.espace, self.url)
        resultat = _appeler(f"/sites/{urllib.parse.quote(site, safe='')}/drive/root/children",
                            params={"$top": 1, "$orderby": "lastModifiedDateTime desc"})
        return _version((resultat.get("value") or [{}])[0])

    def parcourir(self, limite=500):
        """Éléments du drive racine, dossiers parcourus récursivement et bornés."""
        site = _site_id(self.espace, self.url)
        a_voir = [f"/sites/{urllib.parse.quote(site, safe='')}/drive/root/children"]
        vus = 0
        while a_voir and vus < limite:
            chemin = a_voir.pop(0)
            data = _appeler(chemin, params={"$top": 100})
            for item in data.get("value") or []:
                if vus >= limite:
                    break
                if item.get("folder"):
                    a_voir.append(f"/sites/{urllib.parse.quote(site, safe='')}/drive/items/{urllib.parse.quote(str(item['id']), safe='')}/children")
                elif item.get("file") or item.get("id"):
                    yield _ref(item["id"])
                    vus += 1

    def _chercher(self, texte):
        site = _site_id(self.espace, self.url)
        resultat = _appeler(f"/sites/{urllib.parse.quote(site, safe='')}/drive/root/search(q='{urllib.parse.quote(texte)}')",
                            params={"$top": MAX_RESULTATS})
        for item in resultat.get("value") or []:
            if item.get("id"):
                yield {"ref": _ref(item["id"]), "titre": item.get("name") or "",
                       "extrait": item.get("name") or ""}

    def _lire(self, ref, version):
        if not _REF.fullmatch(ref):
            return None
        site = _site_id(self.espace, self.url)
        identifiant = _identifiant(ref)
        item = _appeler(f"/sites/{urllib.parse.quote(site, safe='')}/drive/items/{urllib.parse.quote(identifiant, safe='')}")
        actuelle = _version(item)
        if version and str(version) != actuelle:
            return None
        data = _telecharger(
            f"/sites/{urllib.parse.quote(site, safe='')}/drive/items/{urllib.parse.quote(identifiant, safe='')}/content")
        return {"titre": item.get("name") or "", "version": actuelle,
                "lignes": _lignes_document(data, item.get("name") or "")}


lecteurs.FABRIQUES["SHAREPOINT"] = lambda s: LecteurSharePoint(
    s["nom"], s["emplacement"], s.get("secret_ref"), s.get("url") or "")
