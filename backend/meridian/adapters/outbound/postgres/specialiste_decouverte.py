"""Spécialiste de découverte des interfaces : proposer une couverture sans rien inventer.

Le spécialiste lit un graphe d'interfaces déjà persisté (jamais le réseau), compile ses opérations en
manifestes avec `interface_outils`, puis rend des propositions traçables : opérations à couvrir en
lecture ou en écriture, Twins typés explicitement cités mais absents du graphe, et modèle de synthèse.
Il n'écrit rien, n'appelle aucun outil et ne déduit jamais une opération, une spécification ou un type
de Twin à partir d'un nom.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from meridian.application import interface_outils
from meridian.adapters.outbound.postgres import interfaces_depot
from meridian.domain.specialistes import ContexteSpecialiste, Proposition, ResultatSpecialiste

__all__ = ["SpecialisteDecouverte"]

NOM = "decouverte"
AUTORITE = "proposition"
ACTION_OBSERVER = "observer_interface"
ACTION_CREER_TWIN = "creer_twin"
ACTION_SPECIFICATION = "demander_specification"
_CAPACITES = frozenset({"observer", "agir"})
_LONGUEUR_ID = 160
_LONGUEUR_TEXTE = 300


def _champ(objet: Any, nom: str, defaut: Any = None) -> Any:
    if isinstance(objet, Mapping):
        return objet.get(nom, defaut)
    return getattr(objet, nom, defaut)


def _texte(valeur: Any, maximum: int = _LONGUEUR_TEXTE) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def _identifiant(valeur: Any) -> str | None:
    texte = _texte(valeur, _LONGUEUR_ID)
    return texte or None


def _liste(valeur: Any) -> list:
    if valeur is None:
        return []
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return list(valeur)
    return [valeur]


def _uniques(valeurs) -> tuple[str, ...]:
    vus, sortie = set(), []
    for valeur in valeurs:
        texte = _identifiant(valeur)
        if texte and texte not in vus:
            vus.add(texte)
            sortie.append(texte)
    return tuple(sortie)


def _decouper_graph(graph: Any) -> tuple[list, list, list, list, bool, list]:
    if graph is None:
        return [], [], [], [], False, []
    if isinstance(graph, (list, tuple)):
        return list(graph), [], [], [], False, []
    if isinstance(graph, Mapping):
        operations = graph.get("operations")
        if operations is None and any(cle in graph for cle in ("method", "path", "name")):
            operations = [graph]
        return (
            list(operations or []),
            list(graph.get("contracts") or []),
            list(graph.get("bindings") or []),
            list(graph.get("assertions") or []),
            bool(graph.get("partial")),
            list(graph.get("diagnostics") or []),
        )
    return (
        list(getattr(graph, "operations", None) or []),
        list(getattr(graph, "contracts", None) or []),
        list(getattr(graph, "bindings", None) or []),
        list(getattr(graph, "assertions", None) or []),
        bool(getattr(graph, "partial", False)),
        list(getattr(graph, "diagnostics", None) or []),
    )


def _index_contrats(contrats: list) -> dict[str, Any]:
    index = {}
    for contrat in contrats:
        identifiant = _identifiant(_champ(contrat, "id"))
        if identifiant is not None:
            index[identifiant] = contrat
    return index


def _references_operation(operation: Any) -> set[str]:
    methode = _texte(_champ(operation, "method"), 20)
    action = _texte(_champ(operation, "path") or _champ(operation, "action") or _champ(operation, "name"))
    references = {_identifiant(_champ(operation, "id")), action}
    if methode and action:
        references.add(f"{methode} {action}")
        references.add(f"{methode.upper()} {action}")
    return {reference for reference in references if reference}


def _preuves_operation(operation: Any, contrat: Any, assertions: list,
                       application: str | None) -> tuple[str, ...]:
    preuves = [_identifiant(_champ(operation, "id"))]
    if contrat is not None:
        preuves.append(_identifiant(_champ(contrat, "id")))
        preuves.append(_identifiant(_champ(contrat, "locator")))
    references = _references_operation(operation)
    for assertion in assertions:
        if _texte(_champ(assertion, "predicate"), 40).upper() != "EXPOSE":
            continue
        sujet = _identifiant(_champ(assertion, "subject"))
        if application is not None and sujet is not None and sujet != application:
            continue
        if _identifiant(_champ(assertion, "object")) not in references:
            continue
        preuves.append(_identifiant(_champ(assertion, "locator")))
        preuves.append(_identifiant(_champ(assertion, "evidence")))
    return _uniques(preuves)


def _proposition_operation(operation: Any, manifeste: Any, contrat: Any, assertions: list,
                           application: str | None, graph_partiel: bool) -> tuple[Proposition, dict]:
    methode = _texte(_champ(operation, "method"), 20)
    chemin = _texte(_champ(operation, "path") or _champ(operation, "action"), 200)
    nom = _texte(_champ(operation, "name"), 160)
    libelle = " ".join(partie for partie in (methode, chemin) if partie).strip() or nom or "opération"
    titre = f"Opération {libelle}"
    if nom and nom != libelle:
        titre = f"{titre} — {nom}"
    operation_id = _identifiant(_champ(operation, "id"))
    contrat_id = _identifiant(_champ(contrat, "id")) or _identifiant(_champ(operation, "contract_id"))
    application_operation = (
        _identifiant(_champ(contrat, "application_id")) if contrat is not None else None) or application
    environnement = (
        _identifiant(_champ(operation, "environment"))
        or (_identifiant(_champ(contrat, "environment")) if contrat is not None else None))
    protocole = _identifiant(_champ(operation, "protocol"))
    preuves = _preuves_operation(operation, contrat, assertions, application_operation)
    capacite = _texte(_champ(manifeste, "capacite"), 20).lower() if manifeste is not None else ""

    donnees = {
        "application_id": application_operation,
        "operation_id": operation_id,
        "operation": libelle,
        "contract_id": contrat_id,
        "protocol": protocole,
        "method": methode or None,
        "path": chemin or None,
        "name": nom or None,
        "environment": environnement,
        "couverture": "non_couverte",
        "couverture_source": "contexte",
        "origine": "graphe_interfaces",
    }
    if capacite not in _CAPACITES:
        fiche = {
            "operation_id": operation_id,
            "operation": libelle,
            "name": nom or None,
            "capacite": None,
            "lecture_seule": None,
            "approbation_requise": None,
        }
        donnees.update({
            "capacite": None,
            "lecture_seule": None,
            "approbation_requise": None,
            "posture": "inconnue",
            "manifeste": None,
        })
        proposition = Proposition(
            specialiste=NOM,
            type="CONSTAT",
            titre=f"Posture inconnue : {libelle}",
            resume=(f"L'opération {libelle} existe dans le graphe, mais aucun manifeste ne permet de dire "
                    "si elle observe ou agit. Aucune posture n'est inventée : demander la spécification."),
            preuves=preuves,
            confiance=0.4 if graph_partiel else 0.5,
            actions=(ACTION_SPECIFICATION,),
            donnees=donnees,
        )
        return proposition, fiche

    lecture = capacite == "observer"
    effets = _uniques(_liste(_champ(manifeste, "effets_de_bord")))
    donnees.update({
        "capacite": capacite,
        "lecture_seule": lecture,
        "approbation_requise": not lecture,
        "effets_de_bord": list(effets),
        "mode_preuve": _identifiant(_champ(manifeste, "mode_preuve")),
        "manifeste": _identifiant(_champ(manifeste, "nom")),
    })
    if lecture:
        resume = (f"Opération {libelle} déclarée dans le graphe ; posture observer (lecture seule). "
                  "Elle n'est pas couverte par un outil déclaré dans ce contexte : "
                  "l'observer d'abord, sans écriture.")
        actions = (ACTION_OBSERVER,)
        confiance = 0.55 if graph_partiel else 0.8
    else:
        resume = (f"Opération {libelle} déclarée dans le graphe ; posture agir (écriture). "
                  "Elle n'est pas couverte par un outil déclaré dans ce contexte ; "
                  "approbation requise avant toute action.")
        actions = (ACTION_OBSERVER, ACTION_SPECIFICATION)
        confiance = 0.5 if graph_partiel else 0.7
    fiche = {
        "operation_id": operation_id,
        "operation": libelle,
        "name": nom or None,
        "capacite": capacite,
        "lecture_seule": lecture,
        "approbation_requise": not lecture,
    }
    proposition = Proposition(
        specialiste=NOM,
        type="PROPOSITION",
        titre=titre,
        resume=resume,
        preuves=preuves,
        confiance=confiance,
        actions=actions,
        donnees=donnees,
    )
    return proposition, fiche


def _fiche_contrat(contrat: Any, operations: list) -> dict:
    contrat_id = _identifiant(_champ(contrat, "id"))
    nombre = sum(1 for operation in operations
                 if _identifiant(_champ(operation, "contract_id")) == contrat_id)
    return {
        "id": contrat_id,
        "format": _identifiant(_champ(contrat, "format")),
        "version": _identifiant(_champ(contrat, "version")),
        "application_id": _identifiant(_champ(contrat, "application_id")),
        "environment": _identifiant(_champ(contrat, "environment")),
        "locator": _identifiant(_champ(contrat, "locator")),
        "operations": nombre,
    }


def _fiche_binding(binding: Any) -> dict:
    return {
        "id": _identifiant(_champ(binding, "id")),
        "protocol": _identifiant(_champ(binding, "protocol")),
        "environment": _identifiant(_champ(binding, "environment")),
        "gateway": _identifiant(_champ(binding, "gateway")),
    }


def _rang_priorite(capacite: str | None) -> int:
    if capacite == "observer":
        return 0
    if capacite == "agir":
        return 2
    return 1


def _proposition_modele(application: str | None, contrats: list, operations: list, bindings: list,
                        fiches: list, graph_partiel: bool, diagnostics: list) -> Proposition:
    lectures = [fiche for fiche in fiches if fiche["capacite"] == "observer"]
    ecritures = [fiche for fiche in fiches if fiche["capacite"] == "agir"]
    inconnues = [fiche for fiche in fiches if fiche["capacite"] is None]
    priorite = sorted(
        fiches,
        key=lambda fiche: (_rang_priorite(fiche["capacite"]), fiche["operation_id"] or "",
                           fiche["operation"] or ""))
    approbations = [fiche["operation_id"] for fiche in ecritures if fiche["operation_id"]]
    preuves = _uniques(
        [_champ(contrat, "id") for contrat in contrats]
        + [_champ(contrat, "locator") for contrat in contrats])
    donnees = {
        "application_id": application,
        "contrats": len(contrats),
        "operations": len(operations),
        "bindings": len(bindings),
        "nombre_contrats": len(contrats),
        "nombre_operations": len(operations),
        "nombre_bindings": len(bindings),
        "lectures": len(lectures),
        "ecritures": len(ecritures),
        "postures_inconnues": len(inconnues),
        "approbation_requise": bool(ecritures),
        "operations_a_observer": [fiche["operation_id"] for fiche in lectures if fiche["operation_id"]],
        "operations_sous_approbation": approbations,
        "priorite_observation": priorite,
        "detail_operations": fiches,
        "detail_contrats": [_fiche_contrat(contrat, operations) for contrat in contrats],
        "detail_bindings": [_fiche_binding(binding) for binding in bindings],
        "lecture_seule": True,
        "graphe_partiel": graph_partiel,
    }
    if diagnostics:
        donnees["diagnostics"] = [_texte(diagnostic, 200) for diagnostic in diagnostics if _texte(diagnostic, 200)]
    resume = (f"{len(contrats)} contrat(s), {len(operations)} opération(s) "
              f"({len(lectures)} lecture(s), {len(ecritures)} écriture(s)), {len(bindings)} binding(s).")
    if inconnues:
        resume = f"{resume} {len(inconnues)} posture(s) inconnue(s)."
    if lectures:
        resume = f"{resume} Priorité d'observation : les lectures d'abord."
    if ecritures:
        resume = f"{resume} Les écritures sont flaguées « approbation requise » avant toute action."
    else:
        resume = f"{resume} Aucune écriture déclarée."
    if graph_partiel:
        resume = f"{resume} Graphe partiel : la couverture reste bornée aux preuves lues."
    titre = f"Modèle d'interfaces : {application}" if application else "Modèle d'interfaces"
    actions = (ACTION_OBSERVER,) if operations else (ACTION_SPECIFICATION,)
    if ecritures:
        actions = (ACTION_OBSERVER, ACTION_SPECIFICATION)
    return Proposition(
        specialiste=NOM,
        type="MODELE",
        titre=titre,
        resume=resume,
        preuves=preuves,
        confiance=0.85 if operations else 0.4,
        actions=actions,
        donnees=donnees,
    )


def _propositions_interface(graph: Any, contexte: ContexteSpecialiste,
                            application: str | None) -> tuple[list[Proposition], list[str], bool]:
    operations, contrats, bindings, assertions, graph_partiel, diagnostics = _decouper_graph(graph)
    limites: list[str] = []
    partiel = graph_partiel
    if graph_partiel:
        detail = "; ".join(_texte(diagnostic, 200) for diagnostic in diagnostics if _texte(diagnostic, 200))
        limites.append("graphe d'interfaces partiel" + (f" : {detail}" if detail else ""))
    if not operations:
        partiel = True
        limites.append("graphe d'interfaces vide : aucune opération prouvée, aucune opération inventée")
    if operations and not contrats:
        partiel = True
        limites.append("aucun contrat lisible pour les opérations du graphe, aucune donnée inventée")

    manifestes: list = []
    if operations:
        manifestes = list(interface_outils.manifests_depuis_interface(
            graph, tenant=contexte.tenant, perimetre=application) or [])
        if len(manifestes) < len(operations):
            partiel = True
            limites.append(
                f"manifestes insuffisants : posture inconnue pour {len(operations) - len(manifestes)} opération(s)")

    index = _index_contrats(contrats)
    propositions: list[Proposition] = []
    fiches: list[dict] = []
    for rang, operation in enumerate(operations):
        contrat = index.get(_identifiant(_champ(operation, "contract_id")))
        manifeste = manifestes[rang] if rang < len(manifestes) else None
        proposition, fiche = _proposition_operation(
            operation, manifeste, contrat, assertions, application, graph_partiel)
        propositions.append(proposition)
        fiches.append(fiche)
        if fiche["capacite"] is None:
            partiel = True

    propositions.append(_proposition_modele(
        application, contrats, operations, bindings, fiches, graph_partiel, diagnostics))
    return propositions, limites, partiel


def _twins_connus(store: Any, tenant: str) -> set[str] | None:
    """Identifiants des Twins du tenant lus dans un GraphStore, ou `None` si le store est illisible."""
    try:
        if isinstance(store, Mapping):
            valeurs = list(store.get("noeuds") or [])
        elif isinstance(store, (list, tuple, set, frozenset)):
            valeurs = list(store)
        else:
            noeuds = getattr(store, "noeuds", None)
            if isinstance(noeuds, Mapping):
                valeurs = list(noeuds.values())
            elif isinstance(noeuds, (list, tuple, set, frozenset)):
                valeurs = list(noeuds)
            else:
                as_dict = getattr(store, "as_dict", None)
                if not callable(as_dict):
                    return None
                etat = None
                for arguments in ((tenant,), ()):
                    try:
                        etat = as_dict(*arguments)
                        break
                    except TypeError:
                        continue
                if not isinstance(etat, Mapping):
                    return None
                valeurs = list(etat.get("noeuds") or [])
    except Exception:  # noqa: BLE001 - un store indisponible ne doit pas faire tomber le spécialiste
        return None
    identifiants = set()
    for noeud in valeurs:
        identifiant = _identifiant(_champ(noeud, "id"))
        noeud_tenant = _champ(noeud, "tenant_id")
        if identifiant is not None and (noeud_tenant is None or str(noeud_tenant) == tenant):
            identifiants.add(identifiant)
    return identifiants


def _propositions_twins(contexte: ContexteSpecialiste, application: str | None,
                        applications_connues: set[str]) -> tuple[list[Proposition], list[str], bool]:
    situation = _identifiant(getattr(contexte, "situation_id", None))
    candidats: dict[str, str] = {}
    for twin_id in getattr(contexte, "twin_ids", ()) or ():
        identifiant = _identifiant(twin_id)
        if identifiant is not None:
            candidats.setdefault(identifiant, "contexte.twin_ids")
    interdits = set(applications_connues)
    if application is not None:
        interdits.add(application)
    candidats = {identifiant: source for identifiant, source in candidats.items() if identifiant not in interdits}
    if not candidats:
        return [], [], False

    store = getattr(contexte, "store", None)
    if store is None:
        return [], ["existence typée des Twins cités non vérifiée : aucun store de graphe fourni, "
                    "aucun type inventé"], True
    connus = _twins_connus(store, contexte.tenant)
    if connus is None:
        return [], ["existence typée des Twins cités non vérifiée : store de graphe illisible, "
                    "aucun type inventé"], True

    propositions = []
    for identifiant, source in sorted(candidats.items()):
        if identifiant in connus:
            continue
        propositions.append(Proposition(
            specialiste=NOM,
            type="PROPOSITION",
            titre=f"Twin typé manquant : {identifiant}",
            resume=(f"Le contexte cite explicitement {identifiant} ({source}), absent du graphe consulté. "
                    "Aucun type n'est déduit de l'identifiant : préciser le type et la mission avant création."),
            preuves=(f"{source}={identifiant}",),
            confiance=0.6,
            actions=(ACTION_CREER_TWIN, ACTION_SPECIFICATION),
            donnees={
                "twin_id": identifiant,
                "situation_id": situation,
                "type_suggere": None,
                "source": source,
                "preuve_absence": "graphe de Twins consulté",
                "lecture_seule": True,
            },
        ))
    return propositions, [], False


class SpecialisteDecouverte:
    """Propose une couverture d'interfaces à partir du seul graphe déjà persisté, sans écriture."""

    nom = NOM
    autorite = AUTORITE

    def analyser(self, contexte: ContexteSpecialiste) -> ResultatSpecialiste:
        if not isinstance(contexte, ContexteSpecialiste):
            return ResultatSpecialiste(
                specialiste=self.nom, statut="erreur", erreur="TypeError",
                limites=["ContexteSpecialiste attendu"])
        try:
            return self._analyser(contexte)
        except Exception as exc:  # noqa: BLE001 - le dossier ne tombe pas avec un spécialiste
            return ResultatSpecialiste(
                specialiste=self.nom,
                statut="erreur",
                erreur=type(exc).__name__,
                limites=["lecture du graphe d'interfaces en échec : aucune proposition inventée"],
            )

    def _analyser(self, contexte: ContexteSpecialiste) -> ResultatSpecialiste:
        application = _identifiant(contexte.application_id)
        conn = getattr(contexte, "conn", None)
        limites: list[str] = []
        partiel = False
        graph = None

        if application is None:
            partiel = True
            limites.append("application_id absent : aucun graphe d'interfaces lu, aucune donnée inventée")
        elif conn is None:
            partiel = True
            limites.append("connexion absente : graphe d'interfaces non lu, aucune donnée inventée")
        else:
            graph = interfaces_depot.lire_graph(conn, contexte.tenant, application)

        propositions: list[Proposition] = []
        applications_connues: set[str] = set()
        if graph is not None:
            propositions_interface, limites_interface, partiel_interface = _propositions_interface(
                graph, contexte, application)
            propositions.extend(propositions_interface)
            limites.extend(limites_interface)
            partiel = partiel or partiel_interface
            _, contrats, _, _, _, _ = _decouper_graph(graph)
            applications_connues = {
                identifiant for identifiant in
                (_identifiant(_champ(contrat, "application_id")) for contrat in contrats)
                if identifiant is not None
            }
        elif application is not None and conn is not None:
            partiel = True
            limites.append("graphe d'interfaces absent : aucune opération prouvée, aucune opération inventée")

        propositions_twins, limites_twins, partiel_twins = _propositions_twins(
            contexte, application, applications_connues)
        propositions.extend(propositions_twins)
        limites.extend(limites_twins)
        partiel = partiel or partiel_twins

        return ResultatSpecialiste(
            specialiste=self.nom,
            statut="partiel" if partiel else "ok",
            propositions=propositions,
            limites=limites,
        )
