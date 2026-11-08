"""Détecteurs déterministes de besoins ouverts (plan Cognition IA, B7).

Trois signatures, aucune IA, aucune requête réseau — uniquement des requêtes SQL bornées via psycopg :

- ``question_non_tranchee`` : une réponse de Flore non concluante (absence bornée, ambiguïté, repli,
  statut de clarification ou texte « non observé ») produit un UNKNOWN avec une intention de résolution
  dans la mémoire prospective. Les réponses sont lues dans la table ``travail`` (miroir Postgres des
  conversations) : ``donnees->'conversation'``. Un appelant qui lit directement Mongo ``cases`` peut
  injecter ``reponses=[...]`` à la place.
- ``contournement`` : sur un même couple ``(subject, predicate)`` de ``interface_assertion``, un objet
  ``observed`` absent de l'ensemble ``declared`` signale un contournement — on émet trois HYPOTHESIS
  rivales (EMISE) puis un NEED qui les relie.
- ``recurrence`` : au moins ``seuil_recurrence`` SITUATION canoniques sur un même twin dans une fenêtre
  glissante de ``fenetre_jours`` jours produisent un NEED.

Quotas et dédup : au plus ``quota`` objets par détecteur et par run ; un NEED déjà présent avec la même
``signature`` et le même ``sujet_detection`` (dans ``donnees``), quel que soit son statut, n'est pas
recréé — un détecteur ne rouvre jamais silencieusement un besoin REFUTE ou PERIME. Même règle pour un
UNKNOWN dont la question normalisée existe déjà. Les identifiants sont déterministes : un second run ne
crée rien.

Fail-closed : un besoin refusé par le dépôt ou le trigger ``need_exige_refutation`` remonte dans
``erreurs`` du rapport, jamais avalé.

Poids mesurés (C5) : ``detecter`` accepte ``poids={signature: facteur}`` — le dict rendu par
:func:`signatures_besoins.mesurer`. Chaque NEED créé porte alors ``donnees.poids_signature`` et une
``confiance`` ajustée (``CONFIANCE_DETECTEUR * poids``, bornée à [0, 1]) ; un poids absent, inconnu
ou non numérique vaut 1.0 neutre. Le poids ne s'applique qu'aux NEED — un UNKNOWN mesure une
question, pas un signal de signature.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timedelta, timezone
import hashlib
import unicodedata
from typing import Any

import psycopg
from psycopg.rows import dict_row

from meridian.adapters.outbound.postgres import (
    boucle, entreprise_depot, memoire_prospective, signatures_besoins,
)
from meridian.domain import memoire_prospective as domaine_prospectif

__all__ = [
    "SIGNATURES",
    "QUOTA_DEFAUT",
    "FENETRE_JOURS_DEFAUT",
    "SEUIL_RECURRENCE",
    "ECHEANCE_INTENTION_JOURS",
    "CONFIANCE_DETECTEUR",
    "detecter",
]

SIGNATURES = ("question_non_tranchee", "contournement", "recurrence")
QUOTA_DEFAUT = 10
FENETRE_JOURS_DEFAUT = 30
SEUIL_RECURRENCE = 3
ECHEANCE_INTENTION_JOURS = 14
CONFIANCE_DETECTEUR = 0.5   # confiance de base d'un NEED détecté (avant poids C5)
_LIMITE_LECTURE = 500
_ABSENT = object()

# Formulations bornées produites par la couche identité/flore : une absence n'est
# jamais une preuve d'inexistence, elle laisse la question ouverte.
_MARQUEURS_TEXTE = (
    "non observé dans",
    "preuve d'absence",
    "aucun twin dans le périmètre",
    "assez de connaissances pour répondre",
    "pas pu interpréter",
)


class DetectionInvalide(ValueError):
    """Un paramètre du détecteur ne respecte pas son contrat."""


def _tenant(valeur: Any) -> str:
    texte = str(valeur or "").strip()
    if not texte:
        raise DetectionInvalide("tenant_id obligatoire")
    return texte


def _borne(valeur: Any, champ: str, minimum: int = 1, maximum: int = 1000) -> int:
    if isinstance(valeur, bool):
        raise DetectionInvalide(f"{champ} doit être un entier positif")
    try:
        nombre = int(valeur)
    except (TypeError, ValueError) as exc:
        raise DetectionInvalide(f"{champ} doit être un entier positif") from exc
    if nombre < minimum:
        raise DetectionInvalide(f"{champ} doit être un entier positif")
    return min(nombre, maximum)


def _instant(valeur: Any = None) -> datetime:
    if valeur is None:
        return datetime.now(timezone.utc)
    if isinstance(valeur, datetime):
        instant = valeur
    else:
        try:
            instant = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
        except ValueError as exc:
            raise DetectionInvalide("maintenant : date ISO attendue") from exc
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant


def _texte(valeur: Any, maximum: int = 1000) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def _normaliser(valeur: Any) -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or "").lower())
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return " ".join(texte.split())


def _id_stable(prefixe: str, *parties: Any) -> str:
    brut = "|".join(str(partie or "") for partie in parties)
    return f"{prefixe}-{hashlib.sha256(brut.encode('utf-8')).hexdigest()[:12]}"


def _donnees(ligne: Any) -> dict:
    return dict(ligne.get("donnees") or {}) if isinstance(ligne, Mapping) else {}


# --- Sources bornées ---


def _lire_needs_existants(conn: Any, tenant: str) -> list[dict]:
    return entreprise_depot.lister_objets(conn, tenant, type_="NEED", limite=1000)


def _lire_unknowns_existants(conn: Any, tenant: str) -> list[dict]:
    return entreprise_depot.lister_objets(conn, tenant, type_="UNKNOWN", limite=1000)


def _lire_reponses_flore(conn: Any, tenant: str) -> list[dict]:
    """Paires ``{question, ...message_flore}`` des travaux récents (miroir Postgres de ``cases``).

    La table ``travail`` n'est montée que par le proxy de cases ; son absence rend une liste
    vide plutôt qu'une erreur : le détecteur n'invente pas de conversation.
    """
    try:
        with conn.transaction():  # savepoint : une table absente ne casse pas la transaction de l'appelant
            with conn.cursor(row_factory=dict_row) as cur:
                lignes = cur.execute(
                    "SELECT id, donnees FROM travail WHERE tenant_id = %s "
                    "AND donnees ? 'conversation' ORDER BY maj_le DESC LIMIT %s",
                    (tenant, _LIMITE_LECTURE)).fetchall()
    except psycopg.errors.UndefinedTable:
        return []
    reponses: list[dict] = []
    for ligne in lignes:
        travail = ligne.get("donnees") or {}
        conversation = travail.get("conversation") or []
        for rang, message in enumerate(conversation):
            if not isinstance(message, Mapping) or message.get("role") != "flore":
                continue
            question = ""
            for precedent in reversed(conversation[:rang]):
                if isinstance(precedent, Mapping) and precedent.get("role") == "utilisateur":
                    question = _texte(precedent.get("texte") or precedent.get("reponse"))
                    break
            reponses.append({
                **dict(message),
                "question": question or _texte(
                    (message.get("resolution") or {}).get("question")
                    if isinstance(message.get("resolution"), Mapping) else None),
                "travail_id": ligne.get("id"),
                "message_index": rang,
            })
    return reponses


def _lire_assertions(conn: Any, tenant: str) -> list[dict]:
    try:
        with conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                return [dict(ligne) for ligne in cur.execute(
                    "SELECT id, subject, predicate, object, mode, source, environment, observed_at "
                    "FROM interface_assertion WHERE tenant_id = %s "
                    "ORDER BY subject, predicate, mode, object LIMIT %s",
                    (tenant, _LIMITE_LECTURE)).fetchall()]
    except psycopg.errors.UndefinedTable:
        return []


def _lire_situations(conn: Any, tenant: str, depuis: datetime) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return [dict(ligne) for ligne in cur.execute(
            "SELECT * FROM objet_entreprise WHERE tenant_id = %s AND type = 'SITUATION' "
            "AND observe_le >= %s AND (valide_jusqua IS NULL OR valide_jusqua >= %s) "
            "ORDER BY observe_le DESC LIMIT %s",
            (tenant, depuis, depuis, _LIMITE_LECTURE)).fetchall()]


def _memoire_prospective_montee(conn: Any, tenant: str) -> bool:
    """La table ``memoire_prospective`` répond-elle ? Toute erreur rend ``False``."""
    try:
        with conn.transaction():
            memoire_prospective.lister(conn, tenant, limite=1)
        return True
    except Exception:
        return False


# --- Dédup ---


def _sujets_needs(needs: Iterable[Mapping], signature: str) -> dict[str, str]:
    """``sujet_detection`` → statut, pour la signature donnée (tous statuts confondus)."""
    sujets: dict[str, str] = {}
    for ligne in needs or ():
        donnees = _donnees(ligne)
        if _texte(donnees.get("signature")) != signature:
            continue
        sujet = _texte(donnees.get("sujet_detection"))
        if sujet:
            sujets.setdefault(sujet, _texte(donnees.get("statut")) or "?")
    return sujets


def _questions_unknowns(unknowns: Iterable[Mapping]) -> dict[str, str]:
    """Question normalisée → statut, pour les UNKNOWN du tenant (tous statuts confondus)."""
    questions: dict[str, str] = {}
    for ligne in unknowns or ():
        donnees = _donnees(ligne)
        question = _normaliser(donnees.get("question"))
        if question:
            questions.setdefault(question, _texte(donnees.get("statut")) or "?")
    return questions


# --- Détecteur 1 : question_non_tranchee ---


def _non_concluante(message: Mapping) -> str | None:
    """Rend la raison pour laquelle une réponse de Flore n'est pas concluante, sinon ``None``."""
    resolution = message.get("resolution")
    if isinstance(resolution, Mapping):
        statut_resolution = _texte(resolution.get("statut")).lower()
        if resolution.get("absent") or statut_resolution == "absent":
            return "absence concluante (resolution.absent)"
        if resolution.get("ambigu") or statut_resolution == "ambigu":
            return "identité non tranchée (resolution.ambigu)"
    if message.get("limite"):
        return "limite déclarée par la réponse"
    statut = _texte(message.get("raisonnement_statut") or message.get("statut")).lower()
    if statut in {"clarification_requise", "partiel", "echec"}:
        return f"réponse {statut}"
    if _texte(message.get("origine")).lower() == "repli":
        return "réponse de repli (origine=repli)"
    texte = str(message.get("texte") or message.get("reponse") or "")
    for marqueur in _MARQUEURS_TEXTE:
        if marqueur in texte:
            return f"texte non concluant : « {marqueur} »"
    return None


def _intention_resolution(
    creer_intention: Callable | None, conn: Any, tenant: str, unknown_id: str,
    question: str, travail_id: str, maintenant: datetime, echeance_jours: int,
) -> str | None:
    """Crée l'intention datée de résolution de l'Unknown ; ``None`` si le store est absent."""
    if creer_intention is None:
        return None
    echeance = (maintenant + timedelta(days=echeance_jours)).isoformat(timespec="seconds")
    intention = domaine_prospectif.Intention(
        tenant_id=tenant,
        objet=_texte(f"Résoudre la question non tranchée : {question}", 1000),
        echeance=echeance,
        scope="tenant",
        scope_id="",
        source="detecteur:question_non_tranchee",
        owner="flore",
        priorite="normale",
        evidence_ids=(unknown_id,),
        donnees={"unknown_id": unknown_id, "signature": "question_non_tranchee",
                 "travail_id": travail_id},
        id=_id_stable("intention", tenant, "question_non_tranchee", _normaliser(question)),
    )
    ligne = creer_intention(conn, intention)
    return _texte((ligne or {}).get("id")) or intention.id


def _detecter_question_non_tranchee(
    conn: Any, tenant: str, reponses: Iterable[Mapping], unknowns: list[dict],
    persister: Callable, creer_intention: Callable | None, quota: int,
    echeance_jours: int, maintenant: datetime,
    crees: list, ignores: list, erreurs: list,
) -> None:
    questions_connues = _questions_unknowns(unknowns)
    produits = 0
    for reponse in reponses or ():
        if produits >= quota:
            break
        raison = _non_concluante(reponse)
        if raison is None:
            continue
        question = _texte(reponse.get("question"))
        if not question:
            ignores.append({"signature": "question_non_tranchee", "sujet": "",
                            "raison": "non concluante sans question associée"})
            continue
        cle = _normaliser(question)
        if cle in questions_connues:
            ignores.append({"signature": "question_non_tranchee", "sujet": question[:120],
                            "raison": f"unknown déjà présent (statut {questions_connues[cle]})"})
            continue
        unknown_id = _id_stable("unk", tenant, "question_non_tranchee", cle)
        travail_id = _texte(reponse.get("travail_id"))
        intention_id = None
        try:
            intention_id = _intention_resolution(
                creer_intention, conn, tenant, unknown_id, question,
                travail_id, maintenant, echeance_jours)
        except Exception as exc:  # l'UNKNOWN reste créé ; l'échec d'intention est visible
            erreurs.append({"signature": "question_non_tranchee", "sujet": question[:120],
                            "erreur": f"intention refusée : {exc}"})
        try:
            indice = reponse.get("message_index")
            suffixe = f"#{indice}" if indice is not None else ""
            unknown = boucle.Unknown(
                id=unknown_id, tenant_id=tenant, question=question,
                bloque=f"réponse Flore non concluante : {raison}",
                origine="flore", statut="OUVERT",
                tentatives=[_texte(
                    f"tour flore {travail_id or 'sans travail'}{suffixe} : {raison}", 500)],
            )
            payload = dict(unknown.to_dict())
            payload["sujet_detection"] = cle
            payload["intention_id"] = intention_id
            if travail_id:
                payload["travail_id"] = travail_id
            persister(conn, tenant, payload)
        except Exception as exc:
            erreurs.append({"signature": "question_non_tranchee", "sujet": question[:120],
                            "erreur": str(exc)})
            continue
        questions_connues[cle] = "OUVERT"
        produits += 1
        crees.append({"signature": "question_non_tranchee", "sujet": question[:120],
                      "id": unknown_id, "type": "UNKNOWN", "intention_id": intention_id})


# --- Détecteur 2 : contournement ---


def _contradictions_assertions(assertions: Iterable[Mapping]) -> list[dict]:
    """Couples (subject, predicate) dont l'observé n'est pas entièrement couvert par le déclaré."""
    groupes: dict[tuple[str, str], dict[str, set[str]]] = {}
    for ligne in assertions or ():
        sujet, predicat = _texte(ligne.get("subject")), _texte(ligne.get("predicate"))
        objet, mode = _texte(ligne.get("object")), _texte(ligne.get("mode")).lower()
        if not (sujet and predicat and objet and mode):
            continue
        groupe = groupes.setdefault((sujet, predicat), {"declared": set(), "observed": set()})
        if mode in groupe:
            groupe[mode].add(objet)
    contradictions = []
    for (sujet, predicat), groupe in sorted(groupes.items()):
        excedent = groupe["observed"] - groupe["declared"]
        if groupe["declared"] and excedent:
            contradictions.append({
                "subject": sujet, "predicate": predicat,
                "declared": sorted(groupe["declared"]),
                "observed": sorted(groupe["observed"]),
                "excedent": sorted(excedent),
            })
    return contradictions


def _detecter_contournement(
    conn: Any, tenant: str, assertions: Iterable[Mapping], needs: list[dict],
    persister: Callable, quota: int, fenetre_jours: int,
    poids_signatures: Mapping | None,
    crees: list, ignores: list, erreurs: list,
) -> None:
    sujets_connus = _sujets_needs(needs, "contournement")
    produits = 0
    for contradiction in _contradictions_assertions(assertions):
        if produits >= quota:
            break
        sujet, predicat = contradiction["subject"], contradiction["predicate"]
        sujet_detection = f"{sujet}|{predicat}"
        if sujet_detection in sujets_connus:
            ignores.append({"signature": "contournement", "sujet": sujet_detection,
                            "raison": f"need déjà présent (statut {sujets_connus[sujet_detection]})"})
            continue
        observe = ", ".join(contradiction["excedent"])
        declare = ", ".join(contradiction["declared"])
        gabarits = [
            ("L'usage observé ({obs}) de {sujet} ({pred}) correspond à un besoin réel "
             "que le contrat déclaré ne couvre pas ({decl}).",
             "{obs} reste utilisé dans les flux réels pendant {jours} jours consécutifs"),
            ("Le déclaré {decl} est obsolète : l'interface ou la capacité de {sujet} a "
             "changé sans mise à jour de la déclaration ({pred}).",
             "une révision du contrat ou du code fait reparaître {obs} dans le déclaré"),
            ("La mesure observée ({obs}) est défaillante ou hors périmètre : elle ne "
             "reflète pas l'usage réel de {sujet} ({pred}).",
             "une observation manuelle confirme l'absence de {obs} des flux réels"),
        ]
        try:
            hypotheses = []
            for rang, (enonce, preuve) in enumerate(gabarits):
                hyp_id = _id_stable(
                    "hyp", tenant, "contournement", sujet_detection, str(rang))
                hypotheses.append(boucle.Hypothesis(
                    id=hyp_id, tenant_id=tenant,
                    enonce=enonce.format(sujet=sujet, pred=predicat, obs=observe,
                                         decl=declare),
                    statut="EMISE",
                    preuve_discriminante=preuve.format(
                        obs=observe, jours=fenetre_jours)))
            for rang, hypothese in enumerate(hypotheses):
                hypothese.rival_ids = [
                    autre.id for autre in hypotheses if autre.id != hypothese.id]
            need_id = _id_stable("need", tenant, "contournement", sujet_detection)
            facteur = signatures_besoins.poids_pour(poids_signatures, "contournement")
            need = boucle.Need(
                id=need_id, tenant_id=tenant,
                titre=f"Contournement {sujet} · {predicat}",
                confiance=signatures_besoins.confiance_ajustee(
                    CONFIANCE_DETECTEUR, facteur),
                exigence="l'usage observé et le comportement déclaré coïncident",
                ecart=f"Sur {sujet} ({predicat}), l'observé « {observe} » n'est couvert "
                      f"par aucun déclaré ({declare}).",
                statut="OUVERT", signature="contournement",
                refutable_par=(
                    f"pendant {fenetre_jours} jours consécutifs, toutes les assertions "
                    f"'observed' de ({sujet}, {predicat}) restent incluses dans "
                    "l'ensemble 'declared'"),
                hypothese_ids=[hypothese.id for hypothese in hypotheses],
                twin_ids=[sujet],
                preuves=[{"source": "interface_assertion",
                          "subject": sujet, "predicate": predicat,
                          "declared": contradiction["declared"],
                          "observed": contradiction["observed"]}],
            )
            payload = dict(need.to_dict())
            payload["sujet_detection"] = sujet_detection
            payload["poids_signature"] = facteur
            payload["confiance_detecteur"] = CONFIANCE_DETECTEUR
            persister(conn, tenant, [
                dict(hypothese.to_dict()) for hypothese in hypotheses] + [payload])
        except Exception as exc:
            erreurs.append({"signature": "contournement", "sujet": sujet_detection,
                            "erreur": str(exc)})
            continue
        sujets_connus[sujet_detection] = "OUVERT"
        produits += 1
        crees.append({"signature": "contournement", "sujet": sujet_detection,
                      "id": need_id, "type": "NEED",
                      "hypothese_ids": [hypothese.id for hypothese in hypotheses]})


# --- Détecteur 3 : recurrence ---


def _twin_ids_situation(ligne: Mapping) -> list[str]:
    donnees = _donnees(ligne)
    return [str(t).strip() for t in (donnees.get("twin_ids") or []) if str(t).strip()]


def _detecter_recurrence(
    conn: Any, tenant: str, situations: Iterable[Mapping], needs: list[dict],
    persister: Callable, quota: int, seuil: int, fenetre_jours: int,
    poids_signatures: Mapping | None,
    crees: list, ignores: list, erreurs: list,
) -> None:
    par_twin: dict[str, list[Mapping]] = {}
    for ligne in situations or ():
        for twin_id in _twin_ids_situation(ligne):
            par_twin.setdefault(twin_id, []).append(ligne)
    sujets_connus = _sujets_needs(needs, "recurrence")
    produits = 0
    for twin_id in sorted(par_twin):
        if produits >= quota:
            break
        groupe = par_twin[twin_id]
        if len(groupe) < seuil:
            continue
        sujet_detection = f"twin:{twin_id}"
        if sujet_detection in sujets_connus:
            ignores.append({"signature": "recurrence", "sujet": sujet_detection,
                            "raison": f"need déjà présent (statut {sujets_connus[sujet_detection]})"})
            continue
        situation_ids = [str(l.get("id") or "") for l in groupe if l.get("id")]
        try:
            need_id = _id_stable("need", tenant, "recurrence", sujet_detection)
            facteur = signatures_besoins.poids_pour(poids_signatures, "recurrence")
            need = boucle.Need(
                id=need_id, tenant_id=tenant,
                titre=f"Situations récurrentes sur {twin_id}",
                confiance=signatures_besoins.confiance_ajustee(
                    CONFIANCE_DETECTEUR, facteur),
                exigence="le twin ne produit pas de situation récurrente",
                ecart=(f"{len(groupe)} situations canoniques impliquent {twin_id} "
                       f"en {fenetre_jours} jours glissants."),
                statut="OUVERT", signature="recurrence",
                refutable_par=(
                    f"moins de {seuil} situations canoniques sur {twin_id} pendant "
                    f"deux fenêtres glissantes consécutives de {fenetre_jours} jours"),
                situation_id=situation_ids[0] or None,
                twin_ids=[twin_id],
                preuves=[{"situation_ids": situation_ids,
                          "fenetre_jours": fenetre_jours}],
            )
            payload = dict(need.to_dict())
            payload["sujet_detection"] = sujet_detection
            payload["situation_ids"] = situation_ids
            payload["poids_signature"] = facteur
            payload["confiance_detecteur"] = CONFIANCE_DETECTEUR
            persister(conn, tenant, payload)
        except Exception as exc:
            erreurs.append({"signature": "recurrence", "sujet": sujet_detection,
                            "erreur": str(exc)})
            continue
        sujets_connus[sujet_detection] = "OUVERT"
        produits += 1
        crees.append({"signature": "recurrence", "sujet": sujet_detection,
                      "id": need_id, "type": "NEED", "situations": len(groupe)})


# --- Orchestration ---


def detecter(
    conn: Any, tenant_id: Any, *, signature: str | None = None,
    quota: int = QUOTA_DEFAUT, fenetre_jours: int = FENETRE_JOURS_DEFAUT,
    seuil_recurrence: int = SEUIL_RECURRENCE,
    echeance_jours: int = ECHEANCE_INTENTION_JOURS,
    maintenant: Any = None,
    reponses: Iterable[Mapping] | None = None,
    assertions: Iterable[Mapping] | None = None,
    situations: Iterable[Mapping] | None = None,
    needs: Iterable[Mapping] | None = None,
    unknowns: Iterable[Mapping] | None = None,
    poids: Mapping | None = None,
    persister: Callable | None = None,
    creer_intention: Callable | None = _ABSENT,
) -> dict:
    """Joue les détecteurs déterministes de besoins et rend le rapport du run.

    ``signature`` borne le run à un seul détecteur (les trois sinon). Les paramètres
    ``reponses``, ``assertions``, ``situations``, ``needs`` et ``unknowns`` remplacent
    la lecture en base quand ils sont fournis — c'est le mode READ sans fixture DB.
    ``poids`` est le dict ``{signature: facteur}`` rendu par
    :func:`signatures_besoins.mesurer` (C5) : chaque NEED créé porte
    ``donnees.poids_signature`` et ``confiance = CONFIANCE_DETECTEUR * poids`` bornée
    à [0, 1] ; ``None`` ou signature absente → facteur 1.0 neutre.
    ``persister(conn, tenant, objet_ou_liste)`` écrit dans ``objet_entreprise``
    (défaut : :func:`boucle.enregistrer_boucle`) ; ``creer_intention(conn, intention)``
    écrit dans ``memoire_prospective`` (défaut : :func:`memoire_prospective.creer`,
    ``None`` explicite désactive la création d'intentions).

    Rapport : ``{tenant, crees, ignores, erreurs, totaux}``. Toute erreur d'écriture
    (trigger ``need_exige_refutation`` compris) est visible dans ``erreurs``.
    """
    tenant = _tenant(tenant_id)
    quota = _borne(quota, "quota", maximum=100)
    fenetre_jours = _borne(fenetre_jours, "fenetre_jours", maximum=3650)
    seuil = _borne(seuil_recurrence, "seuil_recurrence", minimum=2, maximum=50)
    echeance_jours = _borne(echeance_jours, "echeance_jours", maximum=365)
    instant = _instant(maintenant)
    signatures = SIGNATURES if signature is None else (_texte(signature),)
    inconnues = set(signatures) - set(SIGNATURES)
    if inconnues:
        raise DetectionInvalide(
            f"signature inconnue : {sorted(inconnues)!r} (connues : {list(SIGNATURES)})")
    if persister is None:
        def persister(c, t, objets):
            return boucle.enregistrer_boucle(c, t, objets)
    lignes_needs = list(needs) if needs is not None else _lire_needs_existants(conn, tenant)
    lignes_unknowns = (
        list(unknowns) if unknowns is not None else _lire_unknowns_existants(conn, tenant))
    crees: list[dict] = []
    ignores: list[dict] = []
    erreurs: list[dict] = []
    if "question_non_tranchee" in signatures:
        if creer_intention is _ABSENT:
            creer_intention = (
                memoire_prospective.creer
                if _memoire_prospective_montee(conn, tenant) else None)
        lot = list(reponses) if reponses is not None else _lire_reponses_flore(conn, tenant)
        _detecter_question_non_tranchee(
            conn, tenant, lot, lignes_unknowns, persister, creer_intention,
            quota, echeance_jours, instant, crees, ignores, erreurs)
    if "contournement" in signatures:
        lot = list(assertions) if assertions is not None else _lire_assertions(conn, tenant)
        _detecter_contournement(
            conn, tenant, lot, lignes_needs, persister, quota, fenetre_jours,
            poids, crees, ignores, erreurs)
    if "recurrence" in signatures:
        lot = list(situations) if situations is not None else _lire_situations(
            conn, tenant, instant - timedelta(days=fenetre_jours))
        _detecter_recurrence(
            conn, tenant, lot, lignes_needs, persister, quota, seuil,
            fenetre_jours, poids, crees, ignores, erreurs)
    return {
        "tenant": tenant,
        "crees": crees,
        "ignores": ignores,
        "erreurs": erreurs,
        "totaux": {"crees": len(crees), "ignores": len(ignores), "erreurs": len(erreurs)},
    }
