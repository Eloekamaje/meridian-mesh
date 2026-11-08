"""Abduction déterministe (plan Cognition IA, D7).

Des hypothèses rivales qui s'excluent mutuellement, une preuve qui les départage,
une question à valeur maximale. Aucun LLM : les rivales naissent de gabarits +
données — ce module est la version **pur** (stdlib seule, sans base ni réseau)
des trois mondes que le détecteur ``contournement`` (B7) écrit en ligne dans
``detecteurs_besoins`` ; il pourra l'appeler à la place sans changer de périmètre.

- :func:`rivaliser` prend une contrainte (un écart, typiquement le dict rendu par
  ``_contradictions_assertions`` : ``subject``/``predicate``/``declared``/
  ``observed``/``excedent``) et rend 3-4 dicts **Hypothesis-compatibles** — les
  clés sont exactement les champs du modèle, les ``rival_ids`` sont croisés et
  chaque ``preuve_discriminante`` nomme l'observation qui distinguerait cette
  rivale des autres. Un indice qui mentionne un événement récent (déploiement,
  migration, correctif) ajoute une quatrième rivale « cause externe ».
- :func:`question_maximale` choisit la preuve discriminante **la plus partagée**
  puis la moins chère (heuristique documentée dans la fonction) : c'est la
  question dont la réponse tranche le plus de mondes pour le moindre effort.
- :func:`trancher` applique une observation : appuyer une rivale réfute les
  autres (exclusion mutuelle), réfuter une rivale laisse les autres vivantes.
- :func:`ou_question` rend le texte de la question socratique, prêt pour une
  réponse Flore ou le fil d'attention.

Tout est déterministe : mêmes entrées → mêmes identifiants (sha256 tronqué,
même schéma que ``detecteurs_besoins._id_stable`` pour rester idempotent si le
détecteur s'y branche un jour).
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
import hashlib
import re
import unicodedata
from typing import Any

__all__ = [
    "AbductionInvalide",
    "SEUIL_PARTAGE",
    "rivaliser",
    "question_maximale",
    "trancher",
    "ou_question",
]

# Deux preuves qui partagent au moins la moitié de leurs mots porteurs décrivent
# la même observation : une seule question les juge toutes les deux.
SEUIL_PARTAGE = 0.5

# Marqueurs de coût : une preuve qui exige une fenêtre temporelle ou une attente
# coûte plus cher qu'une observation ponctuelle (heuristique du moins cher).
_MARQUEURS_COUT = (
    "jours", "consecutif", "semaine", "fenetre", "attendre", "pendant",
    "historique", "tendance", "glissant",
)

# Un indice qui cite un événement récent autorise une quatrième rivale : l'écart
# vient peut-être du changement, pas du sujet observé.
_MARQUEURS_EVENEMENT = (
    "deploi", "migrat", "release", "correctif", "patch", "changement",
    "montee de version", "refonte",
)

_VIDES = frozenset((
    "avec", "dans", "elle", "elles", "entre", "est", "etre", "eux", "pour",
    "quel", "quoi", "sans", "sont", "sous", "leur", "leurs", "mais", "nous",
    "vous", "cette", "quelle", "quels", "quelles", "comment", "combien",
    "pourquoi", "quand", "aussi", "alors", "ainsi", "comme", "dont", "chez",
    "vers", "tous", "tout", "toute", "toutes", "avoir", "avons", "fait",
    "faire", "peut", "plus", "moins", "qui", "que", "des", "les", "une",
    "aux", "ont", "pas", "non", "sur", "par", "ces", "ses", "son", "nos",
    "vos", "mes", "tes", "lui", "car", "ete", "oui", "the", "and", "for",
))

# Les trois mondes rivaux du contournement (identiques à ceux de B7) : l'écart
# déclaré/observé vient du réel, de la référence ou de la mesure — jamais des
# trois à la fois. Une preuve distincte départage chaque monde.
_GABARITS = (
    ("usage_reel",
     "L'usage observé ({obs}) de {sujet} ({pred}) correspond à un besoin réel "
     "que le contrat déclaré ne couvre pas ({decl}).",
     "{obs} reste utilisé dans les flux réels pendant {jours} jours consécutifs"),
    ("reference_obsolete",
     "Le déclaré {decl} est obsolète : l'interface ou la capacité de {sujet} a "
     "changé sans mise à jour de la déclaration ({pred}).",
     "une révision du contrat ou du code fait reparaître {obs} dans le déclaré"),
    ("mesure_defaillante",
     "La mesure observée ({obs}) est défaillante ou hors périmètre : elle ne "
     "reflète pas l'usage réel de {sujet} ({pred}).",
     "une observation manuelle confirme l'absence de {obs} des flux réels"),
)

_GABARIT_EVENEMENT = (
    "evenement_recent",
    "L'écart sur {sujet} ({pred}) s'explique par un changement récent ({evt}) "
    "qui n'est pas encore propagé dans les données.",
    "la trace du changement ({evt}) précède la première observation de {obs}",
)


class AbductionInvalide(ValueError):
    """Une contrainte, une rivale ou une observation ne respecte pas le contrat."""


def _texte(valeur: Any, maximum: int = 1000) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def _normaliser(valeur: Any) -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or "").lower())
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return " ".join(texte.split())


def _id_stable(prefixe: str, *parties: Any) -> str:
    brut = "|".join(str(partie or "") for partie in parties)
    return f"{prefixe}-{hashlib.sha256(brut.encode('utf-8')).hexdigest()[:12]}"


def _tokens(valeur: Any) -> set[str]:
    """Mots porteurs d'un texte, ramenés à leur racine de 6 caractères.

    ≥3 caractères alphanumériques, hors mots vides ; la troncature à 6 lettres
    rapproche les flexions françaises (``observé``/``observation`` → ``observ``,
    ``déclaré``/``déclaration`` → ``declar``, ``manuel``/``manuelle`` →
    ``manuel``) sans stemmer complet à maintenir.
    """
    tokens = set()
    for token in re.split(r"[^a-z0-9]+", _normaliser(valeur)):
        if len(token) >= 3 and token not in _VIDES:
            tokens.add(token[:6])
    return tokens


def _champ(mapping: Mapping, *cles: str) -> Any:
    for cle in cles:
        valeur = mapping.get(cle)
        if valeur is not None and _texte(valeur) != "":
            return valeur
    return None


def _jointure(valeur: Any) -> str:
    """Rend un texte « a, b, c » depuis une liste, un ensemble ou un scalaire."""
    if valeur is None:
        return ""
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return ", ".join(_texte(element, 200) for element in valeur if _texte(element))
    return _texte(valeur)


def _etiquette(indice: Mapping) -> str:
    for cle in ("titre", "locator", "source", "predicat", "objet", "id"):
        valeur = _texte((indice or {}).get(cle), 120)
        if valeur:
            return valeur
    return ""


def _evenement_recent(indices: Iterable[Mapping] | None) -> str | None:
    """Premier indice citant un événement récent (déploiement, migration…)."""
    for indice in indices or ():
        if not isinstance(indice, Mapping):
            continue
        texte = _normaliser(" ".join(str(v) for v in dict(indice).values()))
        if any(marqueur in texte for marqueur in _MARQUEURS_EVENEMENT):
            return _etiquette(indice) or _texte(texte, 120)
    return None


def _sens_observation(valeur: Any) -> str:
    """Verdict d'une observation : ``appuie`` par défaut, ``refute`` sinon."""
    normalise = _normaliser(valeur)
    if normalise in {"refute", "infirme", "contredit", "absent", "non", "faux",
                     "negatif", "absence"}:
        return "refute"
    return "appuie"


# --- Génération des rivales ---


def rivaliser(
    contrainte: Any,
    indices: Iterable[Mapping] | None = None,
    *,
    fenetre_jours: int = 30,
) -> list[dict]:
    """Produit 3-4 hypothèses rivales (dicts Hypothesis-compatibles) qui s'excluent.

    ``contrainte`` est un mapping qui décrit l'écart ; les clés acceptées, par
    ordre de préférence : ``subject``|``sujet``, ``predicate``|``predicat``,
    ``declared``|``declare``, ``excedent``|``observed``|``observe``,
    ``signature``, ``tenant_id``, ``need_id``, ``situation_id``. Les gabarits
    restent les trois mondes de B7 ; un indice d'événement récent ajoute une
    quatrième rivale. Les ``rival_ids`` sont croisés après génération : chaque
    rivale nomme toutes les autres — elles s'excluent mutuellement.
    """
    c = dict(contrainte) if isinstance(contrainte, Mapping) else {}
    sujet = _texte(_champ(c, "subject", "sujet"), 200) or "le sujet concerné"
    predicat = _texte(_champ(c, "predicate", "predicat", "verbe"), 200) or "le lien concerné"
    declare = _jointure(_champ(c, "declared", "declare", "attendu")) or "le déclaré"
    observe = (
        _jointure(_champ(c, "excedent"))
        or _jointure(_champ(c, "observed", "observe"))
        or "l'usage observé"
    )
    signature = _texte(_champ(c, "signature"), 100) or "contournement"
    tenant = _texte(_champ(c, "tenant_id", "tenant"), 200)
    try:
        jours = max(1, min(int(fenetre_jours), 3650))
    except (TypeError, ValueError):
        jours = 30
    evenement = _evenement_recent(indices)

    gabarits = list(_GABARITS)
    if evenement:
        gabarits.append(_GABARIT_EVENEMENT)

    hypotheses: list[dict] = []
    sujet_detection = f"{sujet}|{predicat}"
    for rang, (_cle, enonce, preuve) in enumerate(gabarits):
        rivale = {
            "id": _id_stable("hyp", tenant, signature, sujet_detection, str(rang)),
            "famille": "investigation",
            "type": "HYPOTHESIS",
            "mode": "PROPOSED",
            "enonce": enonce.format(
                sujet=sujet, pred=predicat, obs=observe, decl=declare,
                evt=evenement or "", jours=jours),
            "statut": "EMISE",
            "rival_ids": [],
            "preuve_discriminante": preuve.format(
                obs=observe, decl=declare, sujet=sujet, pred=predicat,
                evt=evenement or "", jours=jours),
        }
        if tenant:
            rivale["tenant_id"] = tenant
        for lien in ("need_id", "situation_id"):
            valeur = _texte(_champ(c, lien), 200)
            if valeur:
                rivale[lien] = valeur
        hypotheses.append(rivale)

    for rivale in hypotheses:
        rivale["rival_ids"] = [
            autre["id"] for autre in hypotheses if autre["id"] != rivale["id"]]
    return hypotheses


# --- Question à valeur maximale ---


def _cout_preuve(preuve: Any) -> int:
    """Coût ordinal d'une preuve : 1 si l'observation exige une attente, 0 sinon."""
    return int(any(marqueur in _normaliser(preuve) for marqueur in _MARQUEURS_COUT))


def _familles_preuves(rivales: list[dict]) -> list[list[int]]:
    """Regroupe les rivales dont les preuves discriminantes décrivent la même
    observation (containment des mots porteurs ≥ ``SEUIL_PARTAGE``, union-find)."""
    tokens = [_tokens(rivale.get("preuve_discriminante")) for rivale in rivales]
    parent = list(range(len(rivales)))

    def racine(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(rivales)):
        for j in range(i + 1, len(rivales)):
            a, b = tokens[i], tokens[j]
            if not a or not b:
                continue
            if len(a & b) / min(len(a), len(b)) >= SEUIL_PARTAGE:
                parent[racine(j)] = racine(i)
    groupes: dict[int, list[int]] = {}
    for i in range(len(rivales)):
        if not tokens[i]:
            continue  # une rivale sans preuve ne peut pas être départagée
        groupes.setdefault(racine(i), []).append(i)
    return sorted(groupes.values(), key=lambda g: (min(g),))


def question_maximale(rivales: Iterable[Mapping]) -> dict:
    """La question dont la réponse élimine le plus de rivales.

    Heuristique (documentée, déterministe) :

    1. **La plus partagée** — deux preuves discriminantes qui partagent au moins
       ``SEUIL_PARTAGE`` de leurs mots porteurs décrivent *la même observation* ;
       une seule question juge alors toutes les rivales de la famille. Le score
       d'une famille est le nombre de rivales qu'elle départage.
    2. **La moins chère** — à couverture égale ou dans la famille gagnante, on
       retient la preuve au coût le plus bas : une observation ponctuelle avant
       une mesure sur ``N`` jours glissants (marqueurs : jours, fenêtre,
       tendance…). Départage final par rang d'apparition.

    Rend ``{question, preuve, couvre, score, familles}`` ; ``couvre`` liste les
    identifiants des rivales que l'observation tranche (appui ou réfutation).
    """
    vals = [dict(r) for r in (rivales or ()) if isinstance(r, Mapping)]
    if not vals:
        return {"question": "", "preuve": "", "couvre": [], "score": 0,
                "familles": []}
    familles = _familles_preuves(vals)
    if not familles:
        return {"question": "", "preuve": "", "couvre": [], "score": 0,
                "familles": []}

    def cle_famille(groupe: list[int]) -> tuple:
        couts = [
            (_cout_preuve(vals[i].get("preuve_discriminante")),
             len(_texte(vals[i].get("preuve_discriminante"))), i)
            for i in groupe
        ]
        cout_min = min(couts)
        return (-len(groupe), cout_min[0], cout_min[1], cout_min[2])

    gagnante = min(familles, key=cle_famille)
    choisi = min(
        gagnante,
        key=lambda i: (
            _cout_preuve(vals[i].get("preuve_discriminante")),
            len(_texte(vals[i].get("preuve_discriminante"))), i))
    preuve = _texte(vals[choisi].get("preuve_discriminante"))
    couvre = [
        _texte(vals[i].get("id")) or f"H{i + 1}" for i in gagnante]
    etiquettes = [f"H{i + 1}" for i in gagnante]
    question = (
        f"Qu'observe-t-on : {preuve} ? "
        f"— cette observation départage {len(couvre)} hypothèse(s) rivale(s) "
        f"({', '.join(etiquettes)})."
    )
    return {
        "question": question,
        "preuve": preuve,
        "couvre": couvre,
        "score": len(gagnante),
        "familles": [sorted(g) for g in familles],
        "hypothese_id": _texte(vals[choisi].get("id")),
    }


# --- Tranchée par l'observation ---


def _cible_par_texte(rivales: list[dict], texte: str) -> str | None:
    """La rivale dont la preuve discriminante recouvre le mieux le texte reçu."""
    mots = _tokens(texte)
    if not mots:
        return None
    meilleur, score = None, 0
    for rivale in rivales:
        recouvrement = len(mots & _tokens(rivale.get("preuve_discriminante")))
        if recouvrement > score:
            meilleur, score = _texte(rivale.get("id")), recouvrement
    return meilleur


def trancher(rivales: Iterable[Mapping], observation: Any) -> dict:
    """Applique une observation aux rivales ; rend les statuts recalculés.

    ``observation`` accepte ``{"appuie": id}`` / ``{"confirme": id}`` (appui),
    ``{"refute": id}`` / ``{"infirme": id}`` (réfutation), ``{"hypothese_id": id,
    "verdict": "…"}`` ou ``{"texte": "…", "verdict": "…"}`` — le texte est alors
    rattaché à la rivale dont la preuve discriminante recouvre le mieux ses mots.
    ``decisif=True`` promeut l'appui en ``RETENUE`` au lieu de ``TESTEE``.

    Exclusion mutuelle : une rivale appuyée réfute toutes les autres ; une
    rivale réfutée laisse les autres vivantes. Les dicts rendus sont des copies —
    les entrées ne sont pas mutées.
    """
    vals = [dict(r) for r in (rivales or ()) if isinstance(r, Mapping)]
    obs = dict(observation) if isinstance(observation, Mapping) else {}
    cible, sens = None, None
    for cle in ("appuie", "appuye", "confirme", "soutient"):
        if _texte(obs.get(cle)):
            cible, sens = _texte(obs[cle]), "appuie"
            break
    if cible is None:
        for cle in ("refute", "infirme", "contredit"):
            if _texte(obs.get(cle)):
                cible, sens = _texte(obs[cle]), "refute"
                break
    if cible is None and _texte(obs.get("hypothese_id") or obs.get("cible")):
        cible = _texte(obs.get("hypothese_id") or obs.get("cible"))
        sens = _sens_observation(obs.get("verdict") or obs.get("sens"))
    if cible is None and _texte(obs.get("texte")):
        cible = _cible_par_texte(vals, _texte(obs["texte"]))
        sens = _sens_observation(obs.get("verdict") or obs.get("sens"))
    if not cible:
        raise AbductionInvalide(
            "observation sans cible : appuie/refute/hypothese_id/texte attendu")
    ids = {_texte(r.get("id")) for r in vals}
    if cible not in ids:
        raise AbductionInvalide(f"rivale inconnue : {cible!r}")

    decisif = bool(obs.get("decisif"))
    resultat: list[dict] = []
    statuts: dict[str, str] = {}
    for rivale in vals:
        copie = dict(rivale)
        identifiant = _texte(copie.get("id"))
        if identifiant == cible:
            if sens == "appuie":
                copie["statut"] = "RETENUE" if decisif else "TESTEE"
            else:
                copie["statut"] = "REFUTEE"
        elif sens == "appuie":
            copie["statut"] = "REFUTEE"
        statuts[identifiant] = copie["statut"]
        resultat.append(copie)
    return {
        "rivales": resultat,
        "statuts": statuts,
        "appuyee": cible if sens == "appuie" else None,
        "refutee": cible if sens == "refute" else None,
        "refutees_par_exclusion": (
            sorted(ids - {cible}) if sens == "appuie" else []),
        "decisif": decisif,
    }


# --- Rendu de la question socratique ---


def ou_question(rivales: Iterable[Mapping]) -> str:
    """Texte de la question socratique, prêt pour une réponse Flore ou le fil.

    Rend une chaîne vide quand aucune preuve discriminante ne peut départager —
    une question vide n'est jamais posée.
    """
    vals = [dict(r) for r in (rivales or ()) if isinstance(r, Mapping)]
    verdict = question_maximale(vals)
    if not verdict["question"]:
        return ""
    enonces = [
        f"H{i + 1} {_texte(rivale.get('enonce'), 140) or '(sans énoncé)'}"
        for i, rivale in enumerate(vals)]
    return (
        "Hypothèses rivales : " + " | ".join(enonces)
        + ". Question à valeur maximale : " + verdict["question"]
    )
