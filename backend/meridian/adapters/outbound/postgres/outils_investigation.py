"""Outils read-only de la boucle d'enquête, adossés aux objets déjà persistés.

Les outils ne lisent ni dépôt ni serveur : ils travaillent sur les `Binding` et les
`ManifesteNaissance` chargés par l'appelant. Ils rendent des candidats structurés,
avec preuves et raison ; ils ne confirment rien.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import urlsplit

from meridian.application import decouverte_liens as resolution
from meridian.domain.decouverte_liens import Binding, CandidatResolution
from meridian.domain.naissance_relationnelle import Consommation, ManifesteNaissance

__all__ = [
    "OutilAPM",
    "OutilBindings",
    "OutilCMDB",
    "OutilCode",
    "OutilGateway",
    "OutilManifestes",
    "OutilPortail",
    "OutilRuntime",
    "OutilServiceNow",
    "OutilVide",
]

_RE_PROPRIETE = re.compile(r"^\$\{([^}]+)\}$")


def _texte(valeur) -> str:
    return " ".join(str(valeur or "").split())


def _reference(valeur) -> str:
    texte = _texte(valeur).strip("'\"").rstrip("/")
    trouve = _RE_PROPRIETE.match(texte)
    return trouve.group(1).strip() if trouve else texte


def _candidat(twin_id: str, service: str, confidence: float, reason: str,
              evidence_ids) -> CandidatResolution:
    return CandidatResolution(
        twin_id=twin_id, service=service, confidence=confidence,
        reason=reason, evidence_ids=tuple(evidence_ids or ()), source="RULES")


def _twin_pour(valeurs, cmdb) -> dict | None:
    for valeur in valeurs or ():
        cible = _texte(valeur).casefold().strip()
        if not cible:
            continue
        for entree in cmdb or ():
            for nom in ("service", "application_id", "twin_id"):
                candidat = _texte(entree.get(nom)).casefold()
                if candidat and (cible == candidat or cible in candidat or candidat in cible):
                    return entree
    return None


class OutilBindings:
    """Résout une référence par la chaîne propriété → URL → route → service."""

    def __init__(self, bindings, environment: str = "inconnu"):
        self.bindings = [b if isinstance(b, Binding) else Binding.depuis_dict(b)
                         for b in (bindings or ())]
        self.environment = environment

    def appeler(self, arguments: dict) -> dict:
        reference = _reference(arguments.get("reference")
                               or arguments.get("missing_evidence"))
        if not reference:
            return {"resume": "aucune référence à résoudre", "candidats": [],
                    "evidence_ids": []}
        consommation = Consommation(
            kind="HTTP", logical_ref=reference, environment=self.environment)
        resultat = resolution.resoudre_destination(
            consommation, self.bindings, environment=self.environment)
        candidats = []
        if resultat.resolved:
            candidats.append(_candidat(
                resultat.target_twin_id, resultat.target_service, 0.75,
                "résolution par la chaîne de bindings", resultat.evidence_ids))
        for candidat in resultat.candidates:
            twin_id = _texte(candidat.get("twin_id"))
            if not twin_id or any(c.twin_id == twin_id for c in candidats):
                continue
            candidats.append(_candidat(
                twin_id, _texte(candidat.get("service")), 0.5,
                "candidat de binding ambigu", candidat.get("evidence_ids") or ()))
        return {
            "resume": resultat.missing_evidence or resultat.status,
            "candidats": [c.as_dict() for c in candidats[:5]],
            "evidence_ids": list(resultat.evidence_ids),
        }


class OutilManifestes:
    """Cherche un Twin dont une exposition ou une consommation correspond à la référence."""

    def __init__(self, manifests):
        self.manifests = [m if isinstance(m, ManifesteNaissance) else ManifesteNaissance.depuis_dict(m)
                          for m in (manifests or ())]

    def appeler(self, arguments: dict) -> dict:
        reference = _reference(arguments.get("reference")
                               or arguments.get("missing_evidence")).casefold()
        if not reference:
            return {"resume": "aucune référence à chercher", "candidats": [],
                    "evidence_ids": []}
        candidats = []
        preuves = []
        for manifeste in self.manifests:
            for exposition in manifeste.exposures:
                operation = _texte(exposition.operation).casefold()
                if not operation:
                    continue
                if operation == reference or operation in reference or reference in operation:
                    candidats.append(_candidat(
                        manifeste.twin_id, "", 0.65,
                        f"exposition {exposition.operation} correspond à la référence",
                        exposition.evidence_ids))
                    preuves.extend(exposition.evidence_ids)
                    break
            if len(candidats) >= 5:
                break
        return {
            "resume": f"{len(candidats)} exposition(s) correspondante(s)",
            "candidats": [c.as_dict() for c in candidats[:5]],
            "evidence_ids": list(dict.fromkeys(preuves)),
        }


class OutilCode:
    """Cherche une référence dans un instantané de fichiers, sans exécuter de code."""

    def __init__(self, fichiers: Mapping | None = None):
        self.fichiers = dict(fichiers or {})

    def appeler(self, arguments: dict) -> dict:
        reference = _reference(arguments.get("reference")
                               or arguments.get("missing_evidence")).casefold()
        if not reference:
            return {"resume": "aucune référence à chercher", "candidats": [],
                    "evidence_ids": []}
        jetons = [jeton for jeton in re.split(r"[^a-z0-9_.-]+", reference)
                  if len(jeton) >= 4]
        preuves = []
        for fichier, texte in self.fichiers.items():
            for numero, ligne in enumerate(str(texte).splitlines(), 1):
                baisse = ligne.casefold()
                if reference in baisse or any(jeton in baisse for jeton in jetons):
                    preuves.append(f"{fichier}:{numero}")
                    if len(preuves) >= 10:
                        break
            if len(preuves) >= 10:
                break
        return {
            "resume": f"{len(preuves)} ligne(s) de code correspondante(s)",
            "candidats": [], "evidence_ids": preuves,
        }


class OutilCMDB:
    """Cherche un service, un hôte ou un Twin dans un extrait de CMDB."""

    def __init__(self, entrees=None):
        self.entrees = [dict(entree) for entree in (entrees or ())
                        if isinstance(entree, dict)]

    def appeler(self, arguments: dict) -> dict:
        reference = _reference(arguments.get("reference")
                               or arguments.get("missing_evidence")).casefold()
        if not reference:
            return {"resume": "aucune référence à chercher", "candidats": [],
                    "evidence_ids": []}
        candidats = []
        preuves = []
        for entree in self.entrees:
            champs = [str(entree.get(nom) or "").casefold()
                      for nom in ("service", "host", "twin_id", "application_id")]
            if not any(champ and (reference in champ or champ in reference)
                       for champ in champs):
                continue
            twin_id = str(entree.get("twin_id") or "").strip()
            if not twin_id:
                continue
            preuve = str(entree.get("evidence_id") or "").strip()
            candidats.append(_candidat(
                twin_id, str(entree.get("service") or ""), 0.7,
                "correspondance CMDB", (preuve,) if preuve else ()))
            if preuve:
                preuves.append(preuve)
            if len(candidats) >= 5:
                break
        return {
            "resume": f"{len(candidats)} correspondance(s) CMDB",
            "candidats": [c.as_dict() for c in candidats],
            "evidence_ids": list(dict.fromkeys(preuves)),
        }


class OutilGateway:
    """Suit une route de passerelle jusqu'au service puis au Twin, si le binding le permet."""

    def __init__(self, bindings):
        self.bindings = [b if isinstance(b, Binding) else Binding.depuis_dict(b)
                         for b in (bindings or ())]

    def appeler(self, arguments: dict) -> dict:
        reference = _reference(arguments.get("reference")
                               or arguments.get("missing_evidence"))
        if not reference:
            return {"resume": "aucune référence à suivre", "candidats": [],
                    "evidence_ids": []}
        chemin = urlsplit(reference).path if "://" in reference else reference
        chemin = "/" + str(chemin or "").strip("/")
        services = {binding.nom.casefold(): binding.valeur
                    for binding in self.bindings if binding.kind == "SERVICE"}
        for binding in self.bindings:
            if binding.kind != "GATEWAY_ROUTE":
                continue
            route = "/" + binding.nom.strip("/")
            if chemin != route and not chemin.startswith(route + "/"):
                continue
            twin = services.get(binding.valeur.casefold())
            if not twin:
                return {
                    "resume": f"route {binding.nom} trouvée, service "
                              f"{binding.valeur} non rattaché à un Twin",
                    "candidats": [], "evidence_ids": list(binding.evidence_ids),
                }
            candidat = _candidat(
                twin, binding.valeur, 0.7,
                f"route {binding.nom} → service {binding.valeur}",
                binding.evidence_ids)
            return {
                "resume": f"route {binding.nom} correspond",
                "candidats": [candidat.as_dict()],
                "evidence_ids": list(binding.evidence_ids),
            }
        return {"resume": "aucune route de passerelle correspondante",
                "candidats": [], "evidence_ids": []}


class OutilServiceNow:
    """Réutilise le lecteur ServiceNow existant pour proposer des CI applicatifs.

    `perimetres` peut être un appelable `recherche -> [{cle, nom}]` ou une liste
    déjà chargée. Un CI n'est proposé comme Twin que s'il correspond au registre ;
    sinon il reste une preuve, jamais un Twin inventé.
    """

    def __init__(self, perimetres, cmdb=None):
        self.perimetres = perimetres
        self.cmdb = list(cmdb or ())

    def appeler(self, arguments: dict) -> dict:
        reference = _reference(arguments.get("reference")
                               or arguments.get("missing_evidence"))
        try:
            trouves = (self.perimetres(reference) if callable(self.perimetres)
                       else self.perimetres)
        except Exception as exc:  # noqa: BLE001 - une source externe ne tue pas l'enquête
            return {"resume": f"ServiceNow indisponible ({type(exc).__name__})",
                    "candidats": [], "evidence_ids": []}
        candidats = []
        preuves = []
        for item in (trouves or ())[:5]:
            if not isinstance(item, dict):
                continue
            ci = _texte(item.get("cle") or item.get("nom"))
            if not ci:
                continue
            preuve = f"servicenow:ci:{ci}"
            preuves.append(preuve)
            twin = _twin_pour((ci, item.get("nom")), self.cmdb)
            if twin is None:
                continue
            candidats.append(_candidat(
                str(twin.get("twin_id")), ci, 0.7,
                f"CI ServiceNow {ci} rattaché au Twin {twin.get('twin_id')}",
                (preuve,)))
        if not candidats:
            registre = OutilCMDB(self.cmdb).appeler(arguments)
            return {
                "resume": registre["resume"] if not preuves else
                          f"{len(preuves)} CI ServiceNow, aucun Twin rattaché",
                "candidats": registre["candidats"],
                "evidence_ids": list(dict.fromkeys([*preuves, *registre["evidence_ids"]])),
            }
        return {
            "resume": f"{len(candidats)} CI ServiceNow rattaché(s)",
            "candidats": [c.as_dict() for c in candidats],
            "evidence_ids": list(dict.fromkeys(preuves)),
        }


class OutilAPM:
    """Réutilise le lecteur Datadog existant : dépendances observées d'un service.

    `dependances` est un appelable sans argument qui rend les lignes du document
    `dependances` (« Appelle X », « Appelé par X »). Une cible n'est proposée que si
    elle se rattache au registre ; sinon elle reste une preuve.
    """

    def __init__(self, dependances, cmdb=None):
        self.dependances = dependances
        self.cmdb = list(cmdb or ())

    def appeler(self, arguments: dict) -> dict:
        try:
            lignes = self.dependances() if callable(self.dependances) else self.dependances
        except Exception as exc:  # noqa: BLE001 - une source APM ne tue pas l'enquête
            return {"resume": f"APM indisponible ({type(exc).__name__})",
                    "candidats": [], "evidence_ids": []}
        candidats = []
        preuves = []
        for ligne in (lignes or ())[:20]:
            trouve = re.match(r"^(Appelle|Appelé par)\s+(.+)$", _texte(ligne), re.I)
            if not trouve:
                continue
            cible = trouve.group(2).strip()
            if not cible or cible.casefold() == "aucun appel observé":
                continue
            preuve = f"datadog:dependances:{cible}"
            preuves.append(preuve)
            twin = _twin_pour((cible,), self.cmdb)
            if twin is None:
                continue
            candidats.append(_candidat(
                str(twin.get("twin_id")), cible, 0.7,
                f"dépendance APM observée vers {cible}", (preuve,)))
        return {
            "resume": f"{len(preuves)} dépendance(s) APM, {len(candidats)} rattachée(s)",
            "candidats": [c.as_dict() for c in candidats],
            "evidence_ids": list(dict.fromkeys(preuves)),
        }


class OutilRuntime:
    """Réutilise les assertions `observed` du connecteur runtime APM/gateway.

    Le graphe est déjà produit par `connecteurs_runtime` ; l'outil ne fait que
    chercher une assertion `CONSOMME` correspondant à la référence et rattacher la
    cible au registre. Une cible non rattachée reste une preuve.
    """

    def __init__(self, graphe, cmdb=None):
        self.assertions = tuple(getattr(graphe, "assertions", ()) or ())
        self.cmdb = list(cmdb or ())

    def appeler(self, arguments: dict) -> dict:
        reference = _reference(arguments.get("reference")
                               or arguments.get("missing_evidence")).casefold()
        candidats = []
        preuves = []
        for assertion in self.assertions:
            if str(getattr(assertion, "predicate", "")).upper() != "CONSOMME":
                continue
            objet = _texte(getattr(assertion, "object", ""))
            if reference and reference not in objet.casefold():
                continue
            cible, separateur, _ = objet.partition(" : ")
            if not separateur:
                cible = ""
            preuve = f"runtime:{getattr(assertion, 'locator', '')}:{objet}"
            preuves.append(preuve)
            twin = _twin_pour((cible,), self.cmdb) if cible else None
            if twin is None:
                continue
            candidats.append(_candidat(
                str(twin.get("twin_id")), cible, 0.7,
                f"appel runtime observé vers {cible}", (preuve,)))
        return {
            "resume": f"{len(preuves)} observation(s) runtime, "
                      f"{len(candidats)} rattachée(s)",
            "candidats": [c.as_dict() for c in candidats],
            "evidence_ids": list(dict.fromkeys(preuves)),
        }


class OutilPortail:
    """Lit un extrait de portail API : opération, owner et implémentation déclarés."""

    def __init__(self, entrees=None, cmdb=None):
        self.entrees = [dict(entree) for entree in (entrees or ())
                        if isinstance(entree, dict)]
        self.cmdb = list(cmdb or ())

    def appeler(self, arguments: dict) -> dict:
        reference = _reference(arguments.get("reference")
                               or arguments.get("missing_evidence")).casefold()
        if not reference:
            return {"resume": "aucune référence à chercher", "candidats": [],
                    "evidence_ids": []}
        candidats = []
        preuves = []
        for entree in self.entrees:
            operation = _texte(entree.get("operation")).casefold()
            service = _texte(entree.get("service")).casefold()
            api_id = _texte(entree.get("api_id")).casefold()
            if not any(reference in valeur or valeur in reference
                       for valeur in (operation, service, api_id) if valeur):
                continue
            twin = _texte(entree.get("owner_twin_id")
                          or entree.get("implementation_twin_id"))
            if not twin:
                continue
            brut = _texte(entree.get("evidence_id") or entree.get("api_id") or twin)
            preuve = brut if brut.startswith("portail:") else f"portail:{brut}"
            preuves.append(preuve)
            candidats.append(_candidat(
                twin, _texte(entree.get("service")), 0.75,
                "portail API : propriétaire/implémentation déclaré", (preuve,)))
            if len(candidats) >= 5:
                break
        return {
            "resume": f"{len(candidats)} entrée(s) de portail correspondante(s)",
            "candidats": [c.as_dict() for c in candidats],
            "evidence_ids": list(dict.fromkeys(preuves)),
        }


class OutilVide:
    """Outil explicitement vide : la source n'est pas encore branchée."""

    def __init__(self, raison: str = "source non branchée"):
        self.raison = raison

    def appeler(self, arguments: dict) -> dict:
        return {"resume": self.raison, "candidats": [], "evidence_ids": []}
