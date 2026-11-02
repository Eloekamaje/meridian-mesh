"""Adapter Linear (GraphQL) pour le port SourceTravail.

Lecture seule, jeton résolu par référence, pagination bornée. Le modèle reste canonique.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from meridian.adapters.outbound.connectors import auth_source
from meridian.adapters.outbound.connectors.github import _SansRedirection

REQUETE_ISSUES = """
query Issues($team: String!, $after: String, $updated: DateTime) {
  issues(first: 100, after: $after, filter: {team: {id: {eq: $team}}, updatedAt: {gt: $updated}}) {
    nodes {
      id identifier title priority estimate
      state { name type }
      cycle { id name startsAt endsAt }
      parent { id identifier }
      relations { nodes { type relatedIssue { id identifier } } }
      updatedAt createdAt
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""
REQUETE_CYCLES = """
query Cycles($team: String!) {
  team(id: $team) { cycles(first: 50) { nodes { id name startsAt endsAt completedAt } } }
}
"""


def _statut(type_):
    return {"completed": "termine", "canceled": "annule", "started": "en_cours",
            "unstarted": "a_faire", "backlog": "a_faire"}.get(str(type_ or "").lower(), "inconnu")


class LinearTravail:
    provider = "linear"

    def __init__(self, configuration: dict | None = None, *, secret_ref: str | None = None):
        self.configuration = dict(configuration or {})
        self.secret_ref = secret_ref or self.configuration.get("secret_ref") or self.configuration.get("secret")
        self.equipe = str(self.configuration.get("equipe_id") or self.configuration.get("team") or "").strip()
        self.base = str(self.configuration.get("base_url") or "https://api.linear.app/graphql")
        parties = urllib.parse.urlparse(self.base)
        autorises = {h.strip().lower() for h in str(self.configuration.get("hotes_autorises") or "").split(",") if h.strip()}
        autorises.add("api.linear.app")
        if parties.scheme != "https" or not parties.hostname or parties.hostname.lower() not in autorises:
            raise ValueError("endpoint Linear invalide ou non autorisé")
        if not self.equipe:
            raise ValueError("équipe Linear requise")

    def capacites(self):
        return {"equipes": True, "sprints": True, "points": True, "heures": False,
                "worklogs": False, "dependances": True, "releases": False, "historique": True}

    def _appeler(self, requete, variables):
        if not self.secret_ref:
            raise RuntimeError("source Linear sans jeton")
        jeton = auth_source.PATSource(self.secret_ref).token()
        if not jeton:
            raise RuntimeError("jeton Linear introuvable")
        data = json.dumps({"query": requete, "variables": variables}).encode()
        requete_http = urllib.request.Request(
            self.base, data=data, method="POST",
            headers={"Authorization": jeton, "Content-Type": "application/json", "Accept": "application/json"})
        with urllib.request.build_opener(_SansRedirection).open(requete_http, timeout=30) as reponse:
            charge = json.loads(reponse.read().decode("utf-8"))
        if charge.get("errors"):
            raise RuntimeError("Linear a refusé la requête")
        return charge.get("data") or {}

    def lister_equipes(self):
        return [{"id": self.equipe, "nom": self.equipe, "source": "linear"}]

    def lister_elements(self, depuis=None, limite=500):
        elements, after = [], None
        while len(elements) < limite:
            data = self._appeler(REQUETE_ISSUES, {"team": self.equipe, "after": after,
                                                  "updated": (str(depuis).split("|", 1)[0] if depuis else None)})
            page = (data.get("issues") or {})
            for issue in page.get("nodes") or []:
                relations = ((issue.get("relations") or {}).get("nodes") or [])
                liens = [{"target_id": (r.get("relatedIssue") or {}).get("identifier"),
                          "type": r.get("type")} for r in relations if (r.get("relatedIssue") or {}).get("identifier")]
                cycle = issue.get("cycle") or {}
                estimation = ({"valeur": float(issue["estimate"]), "unite": "points", "methode": "linear_estimate"}
                              if issue.get("estimate") is not None else None)
                elements.append({
                    "external_id": issue.get("identifier") or issue.get("id"),
                    "titre": issue.get("title") or issue.get("identifier"),
                    "type": "issue", "statut": _statut((issue.get("state") or {}).get("type")),
                    "priorite": str(issue.get("priority") or "inconnue"),
                    "equipe_id": self.equipe,
                    "parent_id": (issue.get("parent") or {}).get("identifier"),
                    "cycle_id": cycle.get("id"), "release_id": None,
                    "categorie_charge": "planifiee", "estimation": estimation,
                    "maj_source": issue.get("updatedAt"),
                    "donnees": {"liens": liens, "created": issue.get("createdAt"),
                                "state": (issue.get("state") or {}).get("name")},
                })
                if len(elements) >= limite:
                    break
            infos = page.get("pageInfo") or {}
            if not infos.get("hasNextPage") or not infos.get("endCursor"):
                break
            after = infos["endCursor"]
        return elements

    def lister_cycles(self):
        data = self._appeler(REQUETE_CYCLES, {"team": self.equipe})
        cycles = (((data.get("team") or {}).get("cycles") or {}).get("nodes") or [])
        return [{"id": str(c.get("id")), "equipe_id": self.equipe, "nom": c.get("name"),
                 "debut": (c.get("startsAt") or "")[:10] or None,
                 "fin": (c.get("endsAt") or "")[:10] or None,
                 "termine": bool(c.get("completedAt"))} for c in cycles]

    def lister_releases(self):
        return []

    def lister_dependances(self):
        dependances = []
        for element in self.lister_elements(None, 100):
            for lien in (element.get("donnees") or {}).get("liens", []):
                dependances.append({"source_element_id": element["external_id"],
                                    "cible_element_id": lien["target_id"], "type": lien["type"]})
        return dependances

    def lister_temps(self):
        return []


def source_de(config: dict) -> dict:
    equipe = str(config.get("equipe_id") or config.get("team") or "").strip()
    if not equipe:
        raise ValueError("équipe Linear requise")
    return {"provider": "linear", "nom": f"linear-{equipe}", "perimetre": equipe,
            "secret_ref": config.get("secret") or config.get("secret_ref"),
            "configuration": {**config, "equipe_id": equipe},
            "capacites": LinearTravail(config, secret_ref=config.get("secret")).capacites()}
