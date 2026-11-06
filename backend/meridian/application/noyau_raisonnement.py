"""Noyau de raisonnement : qualification, cadrage, plan, critique et gates.

Le noyau est volontairement déterministe et sans appel réseau. Les contenus génératifs sont injectés par
des callbacks ; la politique, les niveaux, les gates et la critique de structure restent testables sans
modèle. Cela permet de brancher DeepSeek, Bedrock ou un modèle local sans déplacer la discipline dans un
prompt.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
import inspect
import re
import unicodedata

from meridian.application import contexte_raisonnement as passerelle_contexte
from meridian.application import epistemie as epistemie_application
from meridian.application import gates_tour
from meridian.application import evaluation_raisonnement
from meridian.domain import dossier_raisonnement as domaine

__all__ = [
    "analyser_reponse",
    "cadrer",
    "critiquer_reponse",
    "evaluer_gates",
    "executer_tour",
    "planifier",
    "qualifier",
    "questions_manquantes",
]

_AUTORITES = ("lecture", "proposition", "approbation", "decision", "action")
_ORDRES = {
    "N0": 0, "N1": 1, "N2": 2, "N3": 3, "N4": 4,
    "faible": 0, "modere": 1, "eleve": 2, "critique": 3,
}

_ACTION = (
    "corrige", "corriger", "supprime", "supprimer", "deploie", "deployer", "execute",
    "executer", "envoie", "envoyer", "publie", "publier", "migre", "migrer",
    "installe", "installer", "cree", "creer", "modifie", "modifier", "redemarre",
    "redemarrer", "rollback", "restaure", "restaurer",
)
_CONCEPTION = (
    "concois", "concevoir", "conception", "architecture", "architectural", "dessine",
    "dessiner", "schema", "diagramme", "diagrame", "diagrammes", "maquette", "prototype",
    "plateforme", "systeme cible",
    "modele cible", "application cible", "nouvelle application", "nouveau service",
)
# Dessiner une application existante est une illustration, pas une conception greenfield.
_EXISTANT = (
    "l application", "de l application", "application existante", "application actuelle",
    "du systeme", "telle qu elle", "tel qu il", "en place",
)
_NOUVEAU = (
    "pour une application", "nouvelle application", "nouveau service", "application cible",
    "concevoir", "conception", "from scratch", "greenfield", "maquette", "prototype", "cible",
)
_DECISION = (
    "dois-je", "dois je", "faut-il", "faut il", "choisir", "choix", "decision",
    "decider", "arbitrage", "arbitrer", "recommand", "options", "alternative",
    "vaut-il mieux", "vaut il mieux",
)
_DIAGNOSTIC = (
    "pourquoi", "incident", "panne", "erreur", "echec", "latence", "regression",
    "dysfonctionnement", "ne fonctionne pas", "casse", "bloque",
)
_PLAN = (
    "plan", "planifier", "roadmap", "jalon", "livrer", "livraison", "planning",
    "echeancier", "backlog", "sprint",
)
_VERIFICATION = (
    "verifie", "verifier", "audit", "auditer", "conforme", "conformite", "controle",
    "controler", "valide", "valider", "revue",
)
_EXPLICATION = (
    "explique", "expliquer", "comment", "qu'est-ce", "qu est ce", "difference",
    "pourquoi", "definition", "fonctionne",
)

_SENSIBLE = {
    "donnees personnelles": "donnees_personnelles",
    "personnelle": "donnees_personnelles",
    "rgpd": "donnees_personnelles",
    "sante": "sante",
    "medical": "sante",
    "mineur": "mineurs",
    "enfant": "mineurs",
    "juridique": "juridique",
    "contrat": "juridique",
    "paiement": "finance",
    "financ": "finance",
    "budget": "finance",
    "securite": "securite",
    "faille": "securite",
    "production": "production",
    "irreversible": "irreversible",
    "secret": "secret",
    "acces": "acces",
    "authentification": "acces",
    "mot de passe": "acces",
}
_IRREVERSIBLE = (
    "supprime", "supprimer", "deploie", "deployer", "migre", "migrer", "publie",
    "publier", "envoie", "envoyer", "redemarre", "redemarrer", "rollback",
    "restaure", "restaurer", "production", "irreversible",
)
_CHIFFRES = re.compile(r"(?<!\w)(?:\d+(?:[.,]\d+)?\s*(?:%|€|\$|k€|k\$|jours?|semaines?|mois|ans?|ms|s))\b")


def _normaliser(valeur) -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return " ".join(texte.lower().replace("'", " ").replace("’", " ").split())


def _contient(texte: str, indices) -> bool:
    return any(indice in texte for indice in indices)


def _illustration_existante(normalise: str, contexte: Mapping) -> bool:
    """Vrai si le dessin porte sur une application existante, pas sur une cible greenfield."""
    if _contient(normalise, _NOUVEAU):
        return False
    if contexte.get("twin_ids") or contexte.get("selection") or contexte.get("jumeaux"):
        return True
    return _contient(normalise, _EXISTANT)


def _texte(valeur, maximum=4000) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def _textes(valeurs) -> tuple[str, ...]:
    if valeurs is None:
        return ()
    if isinstance(valeurs, str):
        valeurs = [valeurs]
    resultat: list[str] = []
    for valeur in valeurs:
        texte = _texte(valeur)
        if texte and texte not in resultat:
            resultat.append(texte)
    return tuple(resultat)


def _mapping(valeur) -> dict:
    return dict(valeur) if isinstance(valeur, Mapping) else {}


def _liste_mapping(valeurs) -> list[dict]:
    if valeurs is None:
        return []
    if isinstance(valeurs, Mapping):
        return [dict(valeurs)]
    if isinstance(valeurs, str):
        return []
    try:
        return [dict(v) for v in valeurs if isinstance(v, Mapping)]
    except TypeError:
        return []


def _niveau_demande(question: str, contexte: Mapping | None = None) -> tuple[str, str, float, str, list[str], list[str]]:
    """Retourne (niveau, but, ambiguïté, réversibilité, sensibilités, raisons)."""
    contexte = _mapping(contexte)
    normalise = _normaliser(question)
    # Une question sur l'interaction (« pourquoi tu ne l'as pas dessiné ? ») est une
    # explication méta : elle ne devient pas une conception N3 à cause du verbe « dessiner ».
    if _texte(contexte.get("acte"), 20).lower() == "meta":
        return "N1", "expliquer", 0.05, "reversible", [], [
            "question sur l'interaction précédente"]
    but = _texte(contexte.get("but"), 40).lower()
    if not but:
        if _contient(normalise, _ACTION):
            but = "agir"
        elif _contient(normalise, _CONCEPTION):
            but = "concevoir"
        elif _contient(normalise, _DECISION):
            but = "decider"
        elif _contient(normalise, _DIAGNOSTIC):
            but = "diagnostiquer"
        elif _contient(normalise, _PLAN):
            but = "planifier"
        elif _contient(normalise, _VERIFICATION):
            but = "verifier"
        elif _contient(normalise, _EXPLICATION):
            but = "expliquer"
        else:
            but = "repondre"
    if but == "concevoir" and _illustration_existante(normalise, contexte):
        but = "expliquer"

    sensibilites = []
    for indice, categorie in _SENSIBLE.items():
        if indice in normalise and categorie not in sensibilites:
            sensibilites.append(categorie)

    explicite = _texte(contexte.get("niveau"), 4).upper()
    if explicite in domaine.NIVEAUX:
        niveau = explicite
        raisons = ["niveau imposé par l'appelant"]
    elif but == "agir":
        irreversible = _contient(normalise, _IRREVERSIBLE) or contexte.get("reversible") is False
        niveau = "N4" if irreversible else "N3"
        raisons = ["action à effet externe"]
        if irreversible:
            raisons.append("action potentiellement irréversible")
    elif but in {"concevoir", "decider", "planifier"}:
        niveau = "N3" if but != "planifier" else "N2"
        if but == "concevoir":
            niveau = "N3"
        raisons = [f"traitement de {but}"]
    elif but == "diagnostiquer":
        niveau = "N3" if ("production" in normalise or "client" in normalise) else "N2"
        raisons = ["diagnostic à partir d'observations"]
    elif but == "verifier":
        niveau = "N2"
        raisons = ["vérification avec risque de faux positif"]
    elif but == "expliquer":
        niveau = "N1"
        raisons = ["explication générale"]
    else:
        niveau = "N0"
        raisons = ["réponse directe sans enjeu détecté"]

    if sensibilites and _ORDRES[niveau] < 3:
        niveau = "N3"
        raisons.append("domaine sensible détecté")

    if contexte.get("autorite") in ("decision", "action") and _ORDRES[niveau] < 3:
        niveau = "N3"
        raisons.append("autorité de décision demandée")

    reversible = _texte(contexte.get("reversibilite"), 20).lower()
    if reversible not in domaine.REVERSIBILITES:
        reversible = "irreversible" if _contient(normalise, _IRREVERSIBLE) else "couteuse"
        if but in {"repondre", "expliquer"}:
            reversible = "reversible"

    if _ORDRES[niveau] >= 3:
        champs = ("perimetre", "contraintes", "criteres_succes", "utilisateurs", "echelle")
        presents = sum(1 for champ in champs if _mapping(contexte).get(champ))
        ambiguite = 0.35 + max(0, 4 - presents) * 0.12
        if len(question.split()) < 8:
            ambiguite += 0.1
    elif niveau == "N2":
        ambiguite = 0.3
    else:
        ambiguite = 0.05
    return niveau, but, min(0.95, ambiguite), reversible, sensibilites, raisons


def questions_manquantes(demande: domaine.Demande, contexte: Mapping | None = None) -> tuple[str, ...]:
    """Questions génériques dont la réponse change effectivement le traitement."""
    contexte = _mapping(contexte)
    if contexte.get("sans_questions") or demande.niveau == "N0":
        return ()
    questions: list[str] = []
    champs = {cle: bool(valeur) for cle, valeur in contexte.items()}
    if demande.niveau in {"N3", "N4"}:
        if not champs.get("perimetre"):
            questions.append("Quel est le périmètre exact, et qu'est-ce qui est exclu ?")
        if not champs.get("utilisateurs"):
            questions.append("Quels utilisateurs ou parties prenantes sont concernés ?")
        if not champs.get("contraintes"):
            questions.append("Quelles contraintes sont non négociables : temps, budget, sécurité, réglementation ?")
        if not champs.get("criteres_succes"):
            questions.append("Quels critères permettront de dire que la réponse est bonne ?")
        if demande.but in {"concevoir", "decider"} and not champs.get("options_ecartees"):
            questions.append("Quelles options ont déjà été écartées, et pourquoi ?")
    elif demande.niveau == "N2":
        if not champs.get("contraintes"):
            questions.append("Quelle contrainte principale faut-il respecter ?")
        if not champs.get("criteres_succes"):
            questions.append("Quel résultat attendez-vous en priorité ?")
    limite = {"N2": 3, "N3": 4, "N4": 5}.get(demande.niveau, 0)
    return tuple(questions[:limite])


def _objet_demande(question: str) -> str:
    """Extrait un objet d'entreprise explicite (processus, application, service…) de la question."""
    correspondance = re.search(
        r"(?i)\b(processus|application|service|syst[eè]me|plateforme|parcours|capacit[eé]|produit|domaine)"
        r"\s+(?:de\s+|des\s+|du\s+|d['’]\s*)?([^?.!,;]{3,120})",
        str(question or ""),
    )
    if not correspondance:
        return ""
    return _texte(correspondance.group(2).strip(), 240)


def qualifier(question: str, contexte: Mapping | None = None) -> domaine.Demande:
    contexte = _mapping(contexte)
    niveau, but, ambiguite, reversible, sensibilites, raisons = _niveau_demande(question, contexte)
    enjeu = _texte(contexte.get("enjeu"), 20).lower()
    if enjeu not in domaine.ENJEUX:
        enjeu = {"N0": "faible", "N1": "faible", "N2": "modere",
                 "N3": "eleve", "N4": "critique"}.get(niveau, "faible")
    autorite = _texte(contexte.get("autorite"), 20).lower()
    if autorite not in _AUTORITES:
        autorite = "proposition" if niveau in {"N3", "N4"} else "lecture"
    demande = domaine.Demande(
        question=question,
        objet=_texte(contexte.get("objet") or _objet_demande(question), 240),
        but=but,
        niveau=niveau,
        enjeu=enjeu,
        ambiguite=ambiguite,
        reversibilite=reversible,
        sensibilite=tuple(sensibilites),
        autorite=autorite,
        raisons=tuple(raisons),
    )
    return domaine.Demande(
        **{**demande.as_dict(), "questions": questions_manquantes(demande, contexte)},
    )


def cadrer(demande: domaine.Demande, contexte: Mapping | None = None) -> domaine.Cadre:
    contexte = _mapping(contexte)
    questions = list(demande.questions)
    sans_questions = bool(contexte.get("sans_questions"))
    reponses = _textes(contexte.get("reponses_utilisateur"))
    bloquantes = tuple(questions) if demande.niveau in {"N3", "N4"} and not sans_questions else ()
    non_bloquantes = tuple(questions) if not bloquantes and not sans_questions else ()
    hypotheses = []
    for hypothese in contexte.get("hypotheses") or ():
        if isinstance(hypothese, Mapping):
            hypotheses.append(domaine.Hypothese(**_mapping(hypothese)))
        else:
            hypotheses.append(domaine.Hypothese(texte=str(hypothese)))
    if not hypotheses:
        if reponses:
            hypotheses.append(domaine.Hypothese(
                "Les éléments non précisés restent des hypothèses à valider.",
                impact="peut changer la solution sans invalider la demande",
                test="confirmer les contraintes et le résultat attendu",
            ))
        else:
            hypotheses.append(domaine.Hypothese(
                "Le périmètre et les contraintes ne sont pas confirmés.",
                impact="peut changer la solution et le niveau de risque",
                test="faire valider le périmètre et les contraintes par le commanditaire",
            ))
            if demande.but == "concevoir":
                hypotheses.append(domaine.Hypothese(
                    "Le besoin est une conception, pas seulement un dessin.",
                    impact="détermine le livrable attendu",
                    test="faire choisir entre schéma, architecture cible et décision",
                ))
    if contexte.get("inconnues") is not None:
        inconnues = _textes(contexte.get("inconnues"))
    elif demande.niveau in {"N3", "N4"}:
        champs = (("perimetre", "Périmètre"), ("contraintes", "Contraintes"),
                  ("criteres_succes", "Critères de succès"),
                  ("utilisateurs", "Parties prenantes"))
        inconnues = tuple(libelle for cle, libelle in champs if not contexte.get(cle))
    else:
        inconnues = ()
    risques = list(_textes(contexte.get("risques")))
    if demande.but in {"concevoir", "decider", "agir"}:
        risques.extend([
            "sur-conception ou complexité non justifiée",
            "hypothèses non validées",
        ])
    for sensibilite in demande.sensibilite:
        risques.append(f"risque spécifique au domaine : {sensibilite}")
    return domaine.Cadre(
        objectif=_texte(contexte.get("objectif")) or demande.question,
        perimetre=_texte(contexte.get("perimetre"), 1000),
        contraintes=_textes(contexte.get("contraintes")),
        criteres_succes=_textes(contexte.get("criteres_succes")),
        parties_prenantes=_textes(contexte.get("parties_prenantes") or contexte.get("utilisateurs")),
        hypotheses=tuple(hypotheses),
        inconnues=inconnues,
        risques=tuple(dict.fromkeys(risques)),
        questions_bloquantes=bloquantes,
        questions_non_bloquantes=non_bloquantes,
    )


def planifier(demande: domaine.Demande, cadre: domaine.Cadre, plan_composition=None) -> domaine.PlanRaisonnement:
    operations = {
        "repondre": ("qualifier", "verifier", "expliquer"),
        "expliquer": ("qualifier", "expliquer"),
        "explorer": ("qualifier", "chercher", "comparer"),
        "diagnostiquer": ("observer", "inferer", "verifier", "critiquer"),
        "concevoir": ("cadrer", "generer", "comparer", "critiquer", "decider"),
        "decider": ("cadrer", "comparer", "critiquer", "decider"),
        "planifier": ("cadrer", "decomposer", "planifier", "critiquer"),
        "verifier": ("observer", "verifier", "critiquer"),
        "agir": ("cadrer", "planifier_action", "agir", "verifier"),
    }.get(demande.but, ("qualifier", "repondre"))
    critique = "aucune"
    if demande.niveau == "N3":
        critique = "separee"
    elif demande.niveau == "N4":
        critique = "croisee"
    seuil = "observed" if demande.but in {"diagnostiquer", "verifier"} else (
        "proposed" if demande.but in {"concevoir", "decider", "planifier"} else "declared")
    methodes = ()
    competences = ()
    if demande.but == "concevoir":
        methodes = ("conception",)
        competences = ("formuler_probleme", "comparer_options", "critiquer_conception", "planifier_validation")
    elif demande.but == "decider":
        methodes = ("adr",)
        competences = ("faciliter_decision", "comparer_options", "evaluer_risque", "planifier_validation")
    elif demande.but in {"diagnostiquer", "verifier"}:
        methodes = ("postmortem",) if demande.but == "diagnostiquer" else ("capa",)
        competences = ("verifier_preuve", "detecter_contradiction", "evaluer_risque")
    if plan_composition is not None:
        methodes = tuple(
            getattr(methode, "id", methode) for methode in getattr(plan_composition, "methodes", ())
        ) or methodes
        competences = tuple(
            getattr(competence, "id", competence)
            for competence in getattr(plan_composition, "competences", ())
        ) or competences
    specialistes = ("preuve", "critique") if demande.niveau in {"N3", "N4"} else ("preuve",)
    if plan_composition is not None:
        specialistes = tuple(getattr(plan_composition, "specialistes", ())) or specialistes
    return domaine.PlanRaisonnement(
        niveau=demande.niveau,
        operations=operations,
        methodes=methodes,
        competences=competences,
        specialistes=specialistes,
        seuil_preuve=seuil,
        niveau_critique=critique,
        budget={
            "clarifications": 2,
            "critiques": 2,
            "appels_outils": 12,
            "secondes": 90 if demande.niveau in {"N3", "N4"} else 30,
        },
        conditions_arret=(
            "question bloquante non résolue",
            "budget épuisé",
            "critique majeure non résolue",
        ) if demande.niveau in {"N2", "N3", "N4"} else ("budget épuisé",),
        justification=(
            f"but={demande.but}",
            f"niveau={demande.niveau}",
            f"critique={critique}",
        ),
    )


def _options_reponse(reponse: Mapping) -> list[dict]:
    decision = _mapping(reponse.get("decision_support") or reponse.get("decision"))
    options = reponse.get("options") or decision.get("options") or ()
    return _liste_mapping(options)


def _schemas_reponse(reponse: Mapping) -> list[Mapping]:
    schemas = reponse.get("schemas") or ()
    if isinstance(schemas, Mapping):
        return [schemas]
    try:
        return [s for s in schemas if isinstance(s, Mapping)]
    except TypeError:
        return []


def _a_des_preuves(reponse: Mapping) -> bool:
    for cle in ("preuves", "citations", "sources"):
        if reponse.get(cle):
            return True
    socle = _mapping(reponse.get("socle"))
    return bool(socle.get("preuves") or socle.get("faits"))


def critiquer_reponse(
    dossier: domaine.DossierRaisonnement,
    reponse: Mapping | str,
) -> domaine.Critique:
    """Critique structurelle indépendante du modèle. Elle ne réécrit jamais le livrable."""
    reponse = {"reponse": reponse} if isinstance(reponse, str) else _mapping(reponse)
    texte = _texte(reponse.get("reponse") or reponse.get("texte"))
    findings: list[domaine.Finding] = []
    options = _options_reponse(reponse)
    if dossier.niveau in {"N3", "N4"}:
        if len(options) < 2:
            findings.append(domaine.Finding(
                "Le livrable ne présente pas au moins deux options réelles.",
                severite="majeure", rubrique="options",
                preuve=f"{len(options)} option(s) détectée(s)",
                remediation="produire deux options comparables, dont l'option de ne rien faire si pertinente",
            ))
        validation = reponse.get("validation") or reponse.get("plan_validation")
        if not validation:
            findings.append(domaine.Finding(
                "Le livrable ne porte pas de plan de validation.",
                severite="majeure", rubrique="validation",
                remediation="transformer les hypothèses en tests, mesures ou expériences",
            ))
    cadre_epistemique = getattr(dossier, "question_frame", None)
    if cadre_epistemique and cadre_epistemique.bloquantes:
        findings.append(domaine.Finding(
            "La réponse s'appuie sur un présupposé matériel non vérifié.",
            severite="critique", rubrique="premisse",
            preuve="; ".join(p.texte for p in cadre_epistemique.bloquantes),
            remediation="vérifier le présupposé ou demander confirmation avant de répondre",
        ))
    if any(b.statut == "CONTREDIT" for b in getattr(dossier, "beliefs", ())):
        findings.append(domaine.Finding(
            "Une croyance contredite n'est pas exposée comme telle.",
            severite="majeure", rubrique="contradiction",
            remediation="conserver la contradiction et expliquer son effet sur la conclusion",
        ))
    if dossier.demande and dossier.demande.but == "concevoir" and not reponse.get("hypotheses"):
        findings.append(domaine.Finding(
            "La conception ne déclare pas ses hypothèses.",
            severite="majeure", rubrique="hypotheses",
            remediation="lister les hypothèses et le test qui permettrait de les réfuter",
        ))
    if dossier.demande and dossier.demande.sensibilite:
        risques = reponse.get("risques") or _mapping(reponse.get("cadre")).get("risques")
        if not risques:
            findings.append(domaine.Finding(
                "Un domaine sensible est détecté mais les risques ne sont pas exposés.",
                severite="majeure", rubrique="risque",
                preuve=", ".join(dossier.demande.sensibilite),
                remediation="ajouter les risques de sécurité, conformité et sûreté du domaine",
            ))
    for schema in _schemas_reponse(reponse):
        boites = schema.get("boites") or schema.get("composants") or schema.get("nodes") or ()
        fleches = schema.get("fleches") or schema.get("liens") or schema.get("edges") or ()
        try:
            nb_boites, nb_fleches = len(boites), len(fleches)
        except TypeError:
            nb_boites = nb_fleches = 0
        if nb_boites > 9 or nb_fleches > 12:
            severe = nb_boites > 12 or nb_fleches > 20
            findings.append(domaine.Finding(
                "Le schéma dépasse le budget de lisibilité recommandé (9 nœuds, 12 arêtes).",
                severite="majeure" if severe else "avertissement", rubrique="schema",
                preuve=f"{nb_boites} nœuds, {nb_fleches} arêtes",
                remediation="scinder en vue d'ensemble et vues spécialisées",
            ))
    if texte and _CHIFFRES.search(texte) and not _a_des_preuves(reponse):
        findings.append(domaine.Finding(
            "Le livrable contient un chiffre sans source ou hypothèse explicite.",
            severite="avertissement", rubrique="preuve",
            remediation="relier le chiffre à une source, ou le requalifier en hypothèse",
        ))
    if options:
        for option in options:
            if not option.get("risques"):
                findings.append(domaine.Finding(
                    "Une option ne porte pas ses risques.",
                    severite="majeure", rubrique="options",
                    preuve=_texte(option.get("titre") or option.get("label") or option.get("id"), 120),
                    remediation="ajouter les risques et inconvénients de chaque option",
                ))
    verdict = "fail" if any(f.severite == "critique" for f in findings) else (
        "conditional" if any(f.severite == "majeure" for f in findings) else "pass")
    return domaine.Critique(
        cible="livrable",
        findings=tuple(findings),
        verdict=verdict,
        reviewer="noyau-structurel",
        independance="separee" if dossier.niveau == "N3" else (
            "croisee" if dossier.niveau == "N4" else "aucune"),
    )


def evaluer_gates(dossier):
    """Alias historique : un seul évaluateur vit dans :mod:`gates_tour`."""
    return gates_tour.evaluer(dossier)


def _extraire_options(reponse: Mapping) -> tuple[domaine.Option, ...]:
    resultat = []
    for option in _options_reponse(reponse):
        if not isinstance(option, Mapping):
            continue
        titre = option.get("titre") or option.get("label") or option.get("choix") or option.get("id")
        if not titre:
            continue
        resultat.append(domaine.Option(
            titre=titre,
            description=option.get("description") or option.get("resume") or "",
            avantages=_textes(option.get("avantages")),
            inconvenients=_textes(option.get("inconvenients")),
            risques=_textes(option.get("risques")),
            cout=option.get("cout") or "",
            reversible=option.get("reversible"),
            conditions_validite=_textes(option.get("conditions_validite")),
            source=option.get("source") or "proposee",
            id=option.get("id") or "",
        ))
    return tuple(resultat)


def _extraire_decision(reponse: Mapping) -> domaine.Decision | None:
    decision = _mapping(reponse.get("decision"))
    if not decision:
        support = _mapping(reponse.get("decision_support"))
        if support.get("recommandation"):
            decision = {
                "choix": support.get("recommandation"),
                "justification": "",
                "autorite": support.get("autorite") or "proposition",
                "conditions_retournement": support.get("conditions_de_retournement") or (),
            }
    if not decision:
        return None
    choix = decision.get("choix") or decision.get("recommandation")
    if not choix:
        return None
    return domaine.Decision(
        choix=choix,
        justification=decision.get("justification") or "",
        options_ecartees=_textes(decision.get("options_ecartees")),
        consequences=_textes(decision.get("consequences")),
        proprietaire=decision.get("proprietaire") or "",
        autorite=decision.get("autorite") or "proposition",
        conditions_retournement=_textes(decision.get("conditions_retournement")),
        plan_validation=_textes(decision.get("plan_validation")),
    )


def _extraire_validation(reponse: Mapping) -> tuple[domaine.Validation, ...]:
    valeurs = reponse.get("validation") or reponse.get("plan_validation") or ()
    if isinstance(valeurs, Mapping):
        valeurs = [valeurs]
    resultat = []
    for valeur in valeurs:
        if isinstance(valeur, Mapping) and (valeur.get("hypothese") or valeur.get("hypothesis")):
            resultat.append(domaine.Validation(
                hypothese=valeur.get("hypothese") or valeur.get("hypothesis"),
                methode=valeur.get("methode") or "test",
                critere=valeur.get("critere") or "",
                echeance=valeur.get("echeance") or "",
                proprietaire=valeur.get("proprietaire") or "",
                resultat=valeur.get("resultat") or "",
            ))
    return tuple(resultat)


def preparer_dossier(
    question: str,
    *,
    contexte: Mapping | None = None,
    pack_contexte=None,
    dossier_specialistes=None,
    plan_composition=None,
    trace_id: str = "",
    tenant: str = "",
    travail_id: str = "",
) -> domaine.DossierRaisonnement:
    """Prépare le dossier avant la génération, avec le contexte et les constats déjà disponibles."""
    contexte = _mapping(contexte)
    demande = qualifier(question, contexte)
    cadre = cadrer(demande, contexte)
    plan = planifier(demande, cadre, plan_composition)
    dossier = domaine.DossierRaisonnement(
        question=question, tenant=tenant, travail_id=travail_id,
        demande=demande, cadre=cadre, plan=plan, trace_id=trace_id,
    )
    passerelle_contexte.attacher(
        dossier, pack=pack_contexte, specialistes=dossier_specialistes,
        contexte=contexte, trace_id=trace_id)
    contexte_epistemique = dict(contexte)
    contexte_epistemique.setdefault("objet", demande.objet)
    cadre_epistemique = epistemie_application.analyser_question(
        question, contexte_epistemique, constats=dossier.constats,
        contradictions=contexte.get("contradictions") or (),
    )
    if cadre_epistemique.questions_bloquantes and not contexte.get("sans_questions"):
        dossier.cadre = domaine.Cadre(**{
            **cadre.as_dict(),
            "questions_bloquantes": tuple(cadre_epistemique.questions_bloquantes),
            "questions_non_bloquantes": tuple(cadre.questions_non_bloquantes),
        })
    dossier.question_frame = cadre_epistemique
    dossier.source_plan = epistemie_application.planifier_sources(cadre_epistemique, contexte)
    actuelles = epistemie_application.beliefs_depuis_constats(dossier.constats)
    heritees = []
    for valeur in contexte.get("beliefs") or ():
        try:
            heritees.append(domaine.Belief(**_mapping(valeur)))
        except (TypeError, ValueError):
            continue
    par_id = {belief.id: belief for belief in (*actuelles, *heritees)}
    dossier.beliefs = tuple(par_id.values())
    revisions = []
    for valeur in contexte.get("revisions") or ():
        try:
            revisions.append(domaine.BeliefRevision(**_mapping(valeur)))
        except (TypeError, ValueError):
            continue
    dossier.revisions = tuple(revisions)
    return dossier


def completer_dossier(
    dossier: domaine.DossierRaisonnement,
    reponse: Mapping | str,
    *,
    strict: bool = False,
) -> domaine.DossierRaisonnement:
    """Complète un dossier préparé avec la réponse, la critique structurelle et les gates."""
    reponse_dict = {"reponse": reponse} if isinstance(reponse, str) else _mapping(reponse)
    dossier.reponse = reponse_dict
    dossier.options = _extraire_options(reponse_dict)
    dossier.decision = _extraire_decision(reponse_dict)
    dossier.validation = _extraire_validation(reponse_dict)
    dossier.critiques = (critiquer_reponse(dossier, reponse_dict),)
    dossier.gates = evaluer_gates(dossier)
    if any(g.bloquante for g in dossier.gates):
        dossier.statut = "partiel" if not strict else "refus"
    elif dossier.decision:
        dossier.statut = "decision"
    elif dossier.demande and dossier.demande.but in {"concevoir", "decider", "planifier"}:
        dossier.statut = "proposition"
    else:
        dossier.statut = "reponse"
    dossier.reponse = {
        **reponse_dict,
        "raisonnement": dossier.as_dict(),
        "raisonnement_statut": dossier.statut,
        "critique": dossier.critiques[0].as_dict(),
        "questions": list(dossier.demande.questions) if dossier.demande else [],
        "evaluation_raisonnement": evaluation_raisonnement.evaluer(dossier),
    }
    return dossier


def analyser_reponse(
    question: str,
    reponse: Mapping | str,
    *,
    contexte: Mapping | None = None,
    pack_contexte=None,
    dossier_specialistes=None,
    plan_composition=None,
    trace_id: str = "",
    tenant: str = "",
    travail_id: str = "",
) -> domaine.DossierRaisonnement:
    """Construit un dossier pour une réponse déjà produite, sans rappeler de modèle."""
    dossier = preparer_dossier(
        question, contexte=contexte, pack_contexte=pack_contexte,
        dossier_specialistes=dossier_specialistes, plan_composition=plan_composition,
        trace_id=trace_id, tenant=tenant, travail_id=travail_id)
    return completer_dossier(dossier, reponse, strict=False)


async def _appeler(fonction: Callable, *arguments):
    valeur = fonction(*arguments)
    return await valeur if inspect.isawaitable(valeur) else valeur


async def executer_tour(
    question: str,
    generer: Callable[..., object],
    *,
    contexte: Mapping | None = None,
    pack_contexte=None,
    dossier_specialistes=None,
    plan_composition=None,
    critique: Callable[[domaine.DossierRaisonnement], object] | None = None,
    tenant: str = "",
    travail_id: str = "",
    strict: bool = True,
) -> domaine.DossierRaisonnement:
    """Exécute un tour complet : qualification, clarification, génération, critique, gates.

    `generer` reçoit le cadre et le plan. Un callback qui n'accepte qu'un argument reçoit le cadre.
    La fonction ne décide pas à la place de l'humain : elle prépare un dossier et applique les gates.
    """
    dossier = preparer_dossier(
        question, contexte=contexte, pack_contexte=pack_contexte,
        dossier_specialistes=dossier_specialistes, plan_composition=plan_composition,
        tenant=tenant, travail_id=travail_id)
    demande, cadre, plan = dossier.demande, dossier.cadre, dossier.plan
    if cadre.questions_bloquantes:
        dossier.statut = "clarification_requise"
        dossier.reponse = {
            "comportement": "clarifier",
            "reponse": (
                "Avant de traiter cette demande, il me manque des éléments qui changent la réponse.\n\n"
                + "\n".join(f"- {q}" for q in cadre.questions_bloquantes)
            ),
            "questions": list(cadre.questions_bloquantes),
            "raisonnement": dossier.as_dict(),
            "raisonnement_statut": "clarification_requise",
        }
        dossier.gates = evaluer_gates(dossier)
        return dossier

    try:
        reponse = await _appeler(generer, cadre, plan)
    except TypeError:
        reponse = await _appeler(generer, cadre)
    reponse_dict = {"reponse": reponse} if isinstance(reponse, str) else _mapping(reponse)
    if not reponse_dict:
        dossier.statut = "echec"
        dossier.gates = (domaine.Gate("G-KRN-99", "génération disponible", "echec", "aucune réponse"),)
        return dossier

    dossier.reponse = reponse_dict
    dossier.options = _extraire_options(reponse_dict)
    dossier.decision = _extraire_decision(reponse_dict)
    dossier.validation = _extraire_validation(reponse_dict)
    dossier.critiques = (critiquer_reponse(dossier, reponse_dict),)
    if critique is not None:
        supplement = await _appeler(critique, dossier)
        if isinstance(supplement, domaine.Critique):
            dossier.critiques = dossier.critiques + (supplement,)
        elif isinstance(supplement, Mapping):
            dossier.critiques = dossier.critiques + (domaine.Critique(**supplement),)
    dossier.gates = evaluer_gates(dossier)
    if any(g.bloquante for g in dossier.gates):
        dossier.statut = "partiel" if not strict else "refus"
    elif dossier.decision:
        dossier.statut = "decision"
    elif demande.but in {"concevoir", "decider", "planifier"}:
        dossier.statut = "proposition"
    else:
        dossier.statut = "reponse"
    dossier.reponse = {
        **reponse_dict,
        "raisonnement": dossier.as_dict(),
        "raisonnement_statut": dossier.statut,
        "critique": dossier.critiques[0].as_dict(),
        "questions": list(demande.questions),
        "evaluation_raisonnement": evaluation_raisonnement.evaluer(dossier),
    }
    return dossier
