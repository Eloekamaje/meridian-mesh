"""Conversation : logique pure sur une liste de messages (contrat Conversation v1). Aucune base, aucune mutation :
chaque fonction rend de nouvelles listes et de nouveaux dicts."""
import copy
from datetime import datetime, timezone

# Ce qui, d'un message de Flore, appartient à une version (les champs du haut sont ceux de la version active).
NON_VERSION = ("role", "versions", "version", "retour")
# Au-delà des champs du contrat, la réponse du modèle peut porter ces compléments (affichés tels quels).
COMPLEMENTS = ("propositions", "action", "relu", "jumeaux_participants", "decisions", "precision", "kpis",
               "tableauComparatif", "documentCanvas", "activite", "a_approuver")


def _maintenant():
    return datetime.now(timezone.utc).isoformat()


def _version(reponse):
    texte = reponse.get("reponse", reponse.get("texte")) or ""
    version = {
        "texte": texte, "preuves": reponse.get("preuves") or [], "contributions": reponse.get("contributions") or [],
        "comportement": reponse.get("comportement"), "relecture_etat": reponse.get("relecture_etat") or "relue",
        "corrige": bool(reponse.get("corrige")), "origine": reponse.get("origine"),
        "durees": reponse.get("durees") or {}, "quand": reponse.get("quand") or _maintenant(),
        "interrompu": bool(reponse.get("interrompu")),
    }
    version.update({k: reponse[k] for k in COMPLEMENTS if reponse.get(k) is not None})
    return version


def message_flore(reponse):
    """Le message de Flore au format du contrat, depuis la réponse de `generer_reponse_flore` (version 0)."""
    version = _version(reponse)
    return {"role": "flore", **version, "versions": [copy.deepcopy(version)], "version": 0}


def message_interrompu(texte_partiel, activite=None):
    """Ce que Flore avait écrit quand l'interlocuteur a arrêté, et ce qu'elle avait fait jusque-là (outils faits ou
    en cours) : jamais relu, jamais complété."""
    return message_flore({"reponse": texte_partiel, "interrompu": True, "relecture_etat": "non_relue",
                          "activite": activite or None})


def _versions(message):
    """Les versions d'un message, y compris un message ancien qui n'en a pas (il devient sa version 0)."""
    if message.get("versions"):
        return list(message["versions"])
    return [{k: v for k, v in message.items() if k not in NON_VERSION}]


def _verifier_flore(message):
    if message.get("role") != "flore":
        raise ValueError("Ce message n'est pas une réponse de Flore")


def ajouter_version(message, reponse):
    """La nouvelle réponse devient une nouvelle version, active, de ce message."""
    _verifier_flore(message)
    anciennes = _versions(message)
    nouvelle = message_flore(reponse)
    return {**nouvelle, "versions": anciennes + [nouvelle["versions"][0]], "version": len(anciennes)}


def choisir_version(message, index):
    _verifier_flore(message)
    versions = _versions(message)
    if not isinstance(index, int) or not 0 <= index < len(versions):
        raise ValueError(f"Cette version n'existe pas (index {index}, {len(versions)} version(s))")
    return {**{k: v for k, v in message.items() if k not in ("retour",)}, **versions[index],
            "versions": versions, "version": index}


def _verifier_question(messages, n):
    if not isinstance(n, int) or not 0 <= n < len(messages):
        raise ValueError(f"Le message {n} n'existe pas ({len(messages)} message(s))")
    if messages[n].get("role") != "utilisateur":
        raise ValueError("Ce message n'est pas une question")


def _branches_a_jour(messages, n):
    """Les branches, avec la courante (affichée) rangée telle qu'elle est maintenant."""
    q = messages[n]
    branches = list(q.get("branches") or [])
    courante = q.get("branche", len(branches) - 1) if branches else 0
    if not branches:
        branches = [None]
    branches[courante] = {"texte": q.get("texte", ""), "suite": list(messages[n + 1:])}
    return branches, courante


def ranger_branche_et_modifier(messages, n, texte):
    """La suite actuelle part dans `branches` avec l'ancien texte ; la question prend le nouveau texte, sans suite."""
    _verifier_question(messages, n)
    texte = (texte or "").strip()
    if not texte:
        raise ValueError("Le nouveau texte de la question est vide")
    branches, _ = _branches_a_jour(messages, n)
    branches.append({"texte": texte, "suite": []})
    question = {**messages[n], "texte": texte, "branches": branches, "branche": len(branches) - 1}
    return list(messages[:n]) + [question]


def choisir_branche(messages, n, index):
    """La branche choisie (texte et suite) est restaurée ; la courante est rangée."""
    _verifier_question(messages, n)
    branches, _ = _branches_a_jour(messages, n) if messages[n].get("branches") else (None, None)
    if not branches:
        raise ValueError("Cette question n'a pas de branche")
    if not isinstance(index, int) or not 0 <= index < len(branches):
        raise ValueError(f"Cette branche n'existe pas (index {index}, {len(branches)} branche(s))")
    choisie = branches[index]
    question = {**messages[n], "texte": choisie["texte"], "branches": branches, "branche": index}
    return list(messages[:n]) + [question] + list(choisie["suite"])


def normaliser(message):
    """Un message de Flore enregistré avant les versions prend la forme du contrat (il devient sa version 0)."""
    if message.get("role") != "flore" or message.get("versions"):
        return dict(message)
    base = {"interrompu": False, **message}
    return {**base, "versions": _versions(base), "version": 0}


def correspond(titre, messages, q):
    """La recherche : sous-chaîne, insensible à la casse, jamais une expression régulière."""
    q = (q or "").strip().casefold()
    if not q:
        return True
    return any(q in (t or "").casefold() for t in [titre] + [m.get("texte") for m in messages])


def decider_proposition(message, claim, valeur, par, quand=None):
    """L'approbation en ligne d'une connaissance proposée par Flore pendant ce tour : la décision est inscrite UNE
    fois, dans le message et dans sa version active (les boutons disparaissent). Lève LookupError si la proposition
    n'est pas dans ce message, ValueError si elle est déjà tranchée ou si le message n'est pas de Flore."""
    _verifier_flore(message)
    props = message.get("a_approuver") or []
    i = next((k for k, p in enumerate(props) if p.get("claim") == claim), None)
    if i is None:
        raise LookupError(claim)
    if props[i].get("decision"):
        raise ValueError("Proposition déjà tranchée")
    decision = {"valeur": valeur, "par": par, "quand": quand or _maintenant()}
    nouvelles = [*props[:i], {**props[i], "decision": decision}, *props[i + 1:]]
    versions = list(message.get("versions") or [])
    k = message.get("version", 0)
    if 0 <= k < len(versions):
        versions = [*versions[:k], {**versions[k], "a_approuver": nouvelles}, *versions[k + 1:]]
    return {**message, "a_approuver": nouvelles, "versions": versions}
