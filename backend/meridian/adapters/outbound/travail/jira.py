"""Adapter Jira Cloud pour le port SourceTravail.

Il ne remplace pas le lecteur de preuve `connectors/jira.py` : il normalise le travail, les estimations,
les cycles et les dépendances. Aucun nom Jira n'entre dans le domaine.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from meridian.adapters.outbound.connectors import jira as lecture

CHAMPS_DEFAUT = (
    "summary,issuetype,status,priority,parent,labels,components,fixVersions,updated,created,"
    "resolution,timeoriginalestimate,timeestimate,timespent,issuelinks"
)
RE_INCIDENT = re.compile(r"incident|bug|defect|problem", re.I)


def _iso(valeur) -> str | None:
    if not valeur:
        return None
    return str(valeur)


def _secondes_heures(valeur) -> float | None:
    if valeur in (None, ""):
        return None
    try:
        return round(float(valeur) / 3600, 3)
    except (TypeError, ValueError):
        return None


def _premier(ligne: dict | None, cles: tuple[str, ...]):
    for cle in cles:
        valeur = (ligne or {}).get(cle)
        if valeur not in (None, ""):
            return valeur
    return None


class JiraTravail:
    provider = "jira"

    def __init__(self, configuration: dict | None = None, *, secret_ref: str | None = None):
        self.configuration = dict(configuration or {})
        self.secret_ref = secret_ref or self.configuration.get("secret_ref") or self.configuration.get("secret")
        self.projet = str(self.configuration.get("projet") or self.configuration.get("project") or "").strip()
        self.hote = self.configuration.get("hote")
        self.equipe = str(self.configuration.get("equipe_id") or self.configuration.get("equipe") or self.projet)
        self.champ_points = self.configuration.get("champ_points") or self.configuration.get("story_points_field")
        self.champ_cycle = self.configuration.get("champ_cycle") or self.configuration.get("sprint_field")
        self.board_id = self.configuration.get("board_id")
        self.categorie_defaut = self.configuration.get("categorie_charge") or "planifiee"
        self.inclure_assigne = bool(self.configuration.get("inclure_assigne", False))

    def capacites(self) -> dict[str, bool]:
        return {
            "equipes": True,
            "sprints": bool(self.board_id),
            "points": bool(self.champ_points),
            "heures": True,
            "worklogs": bool(self.configuration.get("worklogs")),
            "dependances": True,
            "releases": True,
            "historique": True,
        }

    def _get(self, chemin: str, **params):
        if not self.secret_ref:
            raise RuntimeError("source Jira sans secret")
        return lecture._get(self.secret_ref, self.hote, chemin, **params)

    def _jql(self, depuis: str | None = None) -> str:
        if not self.projet:
            raise ValueError("projet Jira requis")
        base = f'project = "{self.projet}"'
        if depuis:
            # le curseur est `updated|clé` : Jira ne filtre que sur la date, l'idempotence absorbe le reste.
            date = str(depuis).split("|", 1)[0]
            if date:
                base += f' AND updated >= "{date}"'
        return base + " ORDER BY updated ASC"

    def lister_equipes(self) -> list[dict[str, Any]]:
        if not self.projet:
            return []
        return [{"id": self.equipe, "nom": self.equipe, "externe_id": self.projet,
                 "source": "jira"}]

    def lister_elements(self, depuis: str | None = None, limite: int = 500) -> list[dict[str, Any]]:
        champs = CHAMPS_DEFAUT + (f",{self.champ_points}" if self.champ_points else "")
        if self.champ_cycle:
            champs += f",{self.champ_cycle}"
        elements = []
        token = None
        while len(elements) < limite:
            params = {"jql": self._jql(depuis), "fields": champs,
                      "maxResults": max(1, min(100, int(limite) - len(elements)))}
            if token:
                params["nextPageToken"] = token
            resultat = self._get("/rest/api/3/search/jql", **params)
            for ticket in resultat.get("issues", []):
                f = ticket.get("fields") or {}
                type_ = (f.get("issuetype") or {}).get("name") or "item"
                statut = (f.get("status") or {}).get("statusCategory", {}).get("key") \
                    or (f.get("status") or {}).get("name")
                estimation = None
                if self.champ_points and f.get(self.champ_points) is not None:
                    estimation = {"valeur": float(f[self.champ_points]), "unite": "points",
                                  "methode": "story_points"}
                elif f.get("timeoriginalestimate") is not None:
                    estimation = {"valeur": _secondes_heures(f.get("timeoriginalestimate")),
                                  "unite": "heures", "methode": "original_estimate"}
                versions = f.get("fixVersions") or []
                cycle = f.get(self.champ_cycle) if self.champ_cycle else None
                if isinstance(cycle, list):
                    cycle = cycle[0] if cycle else None
                assigne = None
                if self.inclure_assigne:
                    assigne = (f.get("assignee") or {}).get("accountId")
                elements.append({
                    "external_id": ticket.get("key"),
                    "titre": f.get("summary") or ticket.get("key"),
                    "type": type_,
                    "statut": statut,
                    "priorite": (f.get("priority") or {}).get("name") or "inconnue",
                    "equipe_id": self.equipe,
                    "parent_id": (f.get("parent") or {}).get("key"),
                    "cycle_id": str(cycle) if cycle is not None else None,
                    "release_id": (versions[0] or {}).get("id") or (versions[0] or {}).get("name")
                    if versions else None,
                    "categorie_charge": "non_planifiee" if RE_INCIDENT.search(type_) else self.categorie_defaut,
                    "estimation": estimation,
                    "assigne": assigne,
                    "url": f"https://{self.hote or 'jira'}/browse/{ticket.get('key')}",
                    "maj_source": _iso(f.get("updated")),
                    "donnees": {
                        "labels": f.get("labels") or [],
                        "components": [c.get("name") for c in (f.get("components") or [])],
                        "liens": f.get("issuelinks") or [],
                        "created": _iso(f.get("created")),
                        "resolution": (f.get("resolution") or {}).get("name"),
                    },
                })
            token = resultat.get("nextPageToken")
            if not token or resultat.get("isLast"):
                break
        return elements

    def lister_cycles(self) -> list[dict[str, Any]]:
        if not self.board_id:
            return []
        resultat = self._get(f"/rest/agile/1.0/board/{self.board_id}/sprint", maxResults=50)
        return [{
            "id": str(s.get("id")), "equipe_id": self.equipe, "nom": s.get("name"),
            "debut": (s.get("startDate") or "")[:10] or None,
            "fin": (s.get("endDate") or "")[:10] or None,
            "termine": s.get("state") == "closed",
        } for s in resultat.get("values", [])]

    def lister_releases(self) -> list[dict[str, Any]]:
        if not self.projet:
            return []
        resultat = self._get(f"/rest/api/3/project/{self.projet}/versions")
        return [{"id": str(v.get("id") or v.get("name")), "nom": v.get("name"),
                 "date_cible": (v.get("releaseDate") or "")[:10] or None,
                 "statut": "livree" if v.get("released") else "prevue"}
                for v in resultat if isinstance(v, dict)]

    def lister_dependances(self) -> list[dict[str, Any]]:
        dependances = []
        for element in self.lister_elements(None, 100):
            for lien in (element.get("donnees") or {}).get("liens", []):
                cible = (lien.get("outwardIssue") or lien.get("inwardIssue") or {}).get("key")
                if not cible:
                    continue
                type_ = (lien.get("type") or {}).get("name") or "lie"
                dependances.append({"source_element_id": element["external_id"],
                                    "cible_element_id": cible, "type": type_})
        return dependances

    def lister_temps(self) -> list[dict[str, Any]]:
        if not self.configuration.get("worklogs"):
            return []
        temps = []
        for element in self.lister_elements(None, 100):
            debut, total = 0, None
            while total is None or debut < total:
                try:
                    resultat = self._get(f"/rest/api/3/issue/{element['external_id']}/worklog",
                                         startAt=debut, maxResults=100)
                except Exception:
                    break
                total = int(resultat.get("total") or 0)
                for worklog in resultat.get("worklogs", []):
                    temps.append({
                        "id": f"{element['external_id']}:{worklog.get('id')}",
                        "element_id": element["external_id"], "equipe_id": self.equipe,
                        "date_travail": (worklog.get("started") or "")[:10],
                        "valeur": round(float(worklog.get("timeSpentSeconds") or 0) / 3600, 3),
                        "unite": "heures", "source": "jira",
                    })
                debut += len(resultat.get("worklogs", []))
                if not resultat.get("worklogs"):
                    break
        return temps


def source_de(config: dict) -> dict:
    projet = str(config.get("projet") or config.get("project") or "").strip()
    if not projet:
        raise ValueError("clé de projet Jira requise")
    return {"provider": "jira", "nom": f"jira-{projet}",
            "perimetre": projet, "secret_ref": config.get("secret") or config.get("secret_ref"),
            "configuration": {**config, "projet": projet},
            "capacites": JiraTravail(config, secret_ref=config.get("secret")).capacites()}
