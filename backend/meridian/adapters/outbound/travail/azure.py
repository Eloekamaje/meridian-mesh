"""Adapter Azure DevOps (Services) pour le port SourceTravail.

Lecture seule, PAT résolu par référence ; WIQL pour le delta, batch pour les champs, liens explicites
pour les dépendances. Aucun secret n'est conservé dans la source.
"""
from __future__ import annotations

import base64
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from meridian.adapters.outbound.connectors import auth_source
from meridian.adapters.outbound.connectors.github import _SansRedirection

CHAMPS = (
    "System.Id,System.Title,System.WorkItemType,System.State,System.Priority,System.Parent,"
    "System.IterationPath,System.AreaPath,System.Tags,System.ChangedDate,System.CreatedDate,"
    "Microsoft.VSTS.Scheduling.StoryPoints,Microsoft.VSTS.Scheduling.OriginalEstimate,"
    "System.AssignedTo,Microsoft.VSTS.Scheduling.CompletedWork"
)
RE_ID = re.compile(r"/(\d+)$")
HOTES = {"dev.azure.com", "visualstudio.com"}


def _date_curseur(depuis: str | None) -> str | None:
    if not depuis:
        return None
    return str(depuis).split("|", 1)[0][:10] or None


def _statut(valeur: str | None) -> str:
    texte = str(valeur or "").strip().lower()
    if texte in {"done", "closed", "resolved", "completed"}:
        return "termine"
    if texte in {"removed", "cancelled", "canceled"}:
        return "annule"
    if texte in {"active", "in progress", "committed", "doing"}:
        return "en_cours"
    if texte in {"new", "proposed", "approved", "to do", "backlog"}:
        return "a_faire"
    return "inconnu"


def _nombre(valeur):
    try:
        return float(valeur)
    except (TypeError, ValueError):
        return None


def _id_lien(url: str | None):
    m = RE_ID.search(str(url or ""))
    return m.group(1) if m else None


class AzureDevOpsTravail:
    provider = "azure_devops"

    def __init__(self, configuration: dict | None = None, *, secret_ref: str | None = None):
        self.configuration = dict(configuration or {})
        self.secret_ref = secret_ref or self.configuration.get("secret_ref") or self.configuration.get("secret")
        self.organisation = str(self.configuration.get("organisation") or self.configuration.get("organization") or "").strip()
        self.projet = str(self.configuration.get("projet") or self.configuration.get("project") or "").strip()
        self.equipe = str(self.configuration.get("equipe_id") or self.configuration.get("team") or self.projet)
        self.base = str(self.configuration.get("base_url") or "https://dev.azure.com").rstrip("/")
        self.hote = urllib.parse.urlparse(self.base).hostname or ""
        self.champ_points = self.configuration.get("champ_points") or "Microsoft.VSTS.Scheduling.StoryPoints"
        self.categorie_defaut = self.configuration.get("categorie_charge") or "planifiee"
        self._verifier_hote()

    def _verifier_hote(self):
        parties = urllib.parse.urlparse(self.base)
        autorises = {h.strip().lower() for h in str(self.configuration.get("hotes_autorises") or "").split(",") if h.strip()}
        autorises |= HOTES
        if parties.scheme != "https" or not parties.hostname or parties.username or parties.password:
            raise ValueError("URL Azure DevOps invalide ou non HTTPS")
        if parties.hostname.lower() not in autorises and not parties.hostname.lower().endswith(".visualstudio.com"):
            raise ValueError(f"hôte Azure DevOps non autorisé : {parties.hostname}")
        if not self.organisation or not self.projet:
            raise ValueError("organisation et projet Azure DevOps requis")

    def _jeton(self):
        jeton = auth_source.PATSource(self.secret_ref).token()
        if not jeton:
            raise RuntimeError("source Azure DevOps sans PAT")
        return jeton

    def _appeler(self, methode: str, chemin: str, *, params=None, corps=None):
        url = self.base + "/" + chemin.lstrip("/")
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = None if corps is None else json.dumps(corps).encode()
        entetes = {"Authorization": "Basic " + base64.b64encode(f":{self._jeton()}".encode()).decode(),
                   "Accept": "application/json"}
        if data is not None:
            entetes["Content-Type"] = "application/json"
        requete = urllib.request.Request(url, data=data, headers=entetes, method=methode)
        with urllib.request.build_opener(_SansRedirection).open(requete, timeout=30) as reponse:
            return json.loads(reponse.read().decode("utf-8"))

    def _chemin(self, suffixe: str):
        return f"{urllib.parse.quote(self.organisation)}/{urllib.parse.quote(self.projet)}/{suffixe.lstrip('/')}"

    def capacites(self) -> dict[str, bool]:
        return {"equipes": True, "sprints": bool(self.equipe), "points": bool(self.champ_points),
                "heures": True,
                "worklogs": bool(self.configuration.get("worklogs") or self.configuration.get("actuals")),
                "dependances": True, "releases": False, "historique": True}

    def lister_equipes(self):
        return [{"id": self.equipe, "nom": self.equipe, "externe_id": self.projet, "source": "azure_devops"}]

    def _ids(self, depuis: str | None, limite: int) -> list[int]:
        date = _date_curseur(depuis)
        where = "[System.TeamProject] = @project"
        if date:
            where += f" AND [System.ChangedDate] >= '{date}'"
        ids: list[int] = []
        saut = 0
        while len(ids) < limite:
            taille = max(1, min(200, limite - len(ids)))
            corps = {"query": f"SELECT [System.Id] FROM WorkItems WHERE {where} ORDER BY [System.ChangedDate] ASC"}
            resultat = self._appeler("POST", self._chemin("_apis/wit/wiql"),
                                     params={"api-version": "7.0", "$top": taille, "$skip": saut},
                                     corps=corps)
            page = [int(item["id"]) for item in resultat.get("workItems", [])]
            ids.extend(page)
            if len(page) < taille:
                break
            saut += len(page)
        return ids[:limite]

    def lister_elements(self, depuis: str | None = None, limite: int = 500):
        ids = self._ids(depuis, limite)
        if not ids:
            return []
        champs = CHAMPS + ("," + self.champ_points if self.champ_points not in CHAMPS else "")
        resultat = self._appeler(
            "GET", self._chemin("_apis/wit/workitems"),
            params={"ids": ",".join(str(i) for i in ids), "fields": champs,
                    "$expand": "relations", "api-version": "7.0"})
        elements = []
        for item in resultat.get("value", []):
            f = item.get("fields") or {}
            identifiant = str(item.get("id"))
            relations = item.get("relations") or []
            parent_id = None
            liens = []
            for relation in relations:
                cible = _id_lien(relation.get("url"))
                if not cible:
                    continue
                type_ = str(relation.get("rel") or "")
                if type_.endswith("Hierarchy-Reverse"):
                    parent_id = cible
                elif "Dependency" in type_ or type_.endswith("Related"):
                    liens.append({"target_id": cible, "type": type_.rsplit(".", 1)[-1]})
            points = _nombre(f.get(self.champ_points))
            estimation = ({"valeur": points, "unite": "points", "methode": "story_points"}
                          if points is not None else None)
            if estimation is None:
                heures = _nombre(f.get("Microsoft.VSTS.Scheduling.OriginalEstimate"))
                if heures is not None:
                    estimation = {"valeur": heures, "unite": "heures", "methode": "original_estimate"}
            elements.append({
                "external_id": identifiant, "titre": f.get("System.Title") or identifiant,
                "type": f.get("System.WorkItemType") or "item",
                "statut": _statut(f.get("System.State")),
                "priorite": f.get("System.Priority") or "inconnue",
                "equipe_id": self.equipe, "parent_id": parent_id,
                "cycle_id": f.get("System.IterationPath") or None,
                "release_id": None,
                "categorie_charge": self.categorie_defaut,
                "estimation": estimation,
                "assigne": None,
                "url": f"{self.base}/{urllib.parse.quote(self.organisation)}/{urllib.parse.quote(self.projet)}/_workitems/edit/{identifiant}",
                "maj_source": f.get("System.ChangedDate"),
                "donnees": {"liens": liens, "area": f.get("System.AreaPath"),
                            "tags": f.get("System.Tags"), "created": f.get("System.CreatedDate"),
                            "completed_work": _nombre(f.get("Microsoft.VSTS.Scheduling.CompletedWork"))},
            })
        return elements

    def lister_cycles(self):
        if not self.equipe:
            return []
        try:
            resultat = self._appeler(
                "GET", self._chemin(f"{urllib.parse.quote(self.equipe)}/_apis/work/teamsettings/iterations"),
                params={"api-version": "7.0"})
        except Exception:
            return []
        return [{"id": str(i.get("id") or i.get("name")), "equipe_id": self.equipe,
                 "nom": i.get("name"), "debut": (i.get("attributes") or {}).get("startDate", "")[:10] or None,
                 "fin": (i.get("attributes") or {}).get("finishDate", "")[:10] or None,
                 "termine": bool((i.get("attributes") or {}).get("finishDate"))}
                for i in resultat.get("value", [])]

    def lister_releases(self):
        return []

    def lister_dependances(self):
        dependances = []
        for element in self.lister_elements(None, 100):
            for lien in (element.get("donnees") or {}).get("liens", []):
                dependances.append({"source_element_id": element["external_id"],
                                    "cible_element_id": lien["target_id"],
                                    "type": lien["type"]})
        return dependances

    def lister_temps(self):
        if not self.configuration.get("worklogs") and not self.configuration.get("actuals"):
            return []
        temps = []
        for element in self.lister_elements(None, 200):
            heures = _nombre((element.get("donnees") or {}).get("completed_work"))
            if heures is None or heures <= 0:
                continue
            temps.append({"id": f"{element['external_id']}:completed", "element_id": element["external_id"],
                          "equipe_id": self.equipe, "date_travail": (element.get("maj_source") or "")[:10],
                          "valeur": heures, "unite": "heures", "source": "azure_devops"})
        return temps


def source_de(config: dict) -> dict:
    organisation = str(config.get("organisation") or config.get("organization") or "").strip()
    projet = str(config.get("projet") or config.get("project") or "").strip()
    if not organisation or not projet:
        raise ValueError("organisation et projet Azure DevOps requis")
    return {"provider": "azure_devops", "nom": f"azure-{organisation}-{projet}",
            "perimetre": projet, "secret_ref": config.get("secret") or config.get("secret_ref"),
            "configuration": {**config, "organisation": organisation, "projet": projet},
            "capacites": AzureDevOpsTravail(config, secret_ref=config.get("secret")).capacites()}
