"""Poids mesurés des signatures de besoins (plan Cognition IA, C5).

Le taux de confirmation de chaque signature de NEED (``contournement``,
``recurrence``, ``question_non_tranchee``…) module la confiance des NEED
suivants — le jumeau apprend quels signaux annoncent un vrai besoin, par la
mesure, pas par un texte interprétatif. Aucune IA, aucune requête réseau —
uniquement des requêtes SQL bornées via psycopg.

Mesure (:func:`taux_par_signature`) : pour chaque signature rencontrée dans les
NEED du tenant, les comptes par statut du cycle B6 plus le taux de confirmation.

- ``juges`` = ``CORROBORE`` + ``ADRESSE`` + ``REFUTE`` : les besoins dont le
  verdict est tombé. ``OUVERT`` et ``QUALIFIE`` attendent encore — ils
  n'entrent ni au numérateur ni au dénominateur.
- ``confirmes`` = ``CORROBORE`` + ``ADRESSE`` : le signal annonçait un vrai
  besoin.
- ``PERIME`` est compté à part, **hors des jugés** : un besoin périmé n'a été ni
  confirmé ni réfuté — le compter comme réfuté pénaliserait les signatures dont
  les besoins vieillissent sans verdict.
- ``taux_confirme`` = ``confirmes / juges``, ``None`` quand ``juges`` = 0 ;
  chaque taux est accompagné de son intervalle de confiance binomial de Wilson
  (``ic95``) — jamais un taux sans ``n``.

Poids (:func:`poids`) : facteur borné dans ``[POIDS_MIN, POIDS_MAX]``. Tant que
``juges < min_preuves`` (défaut 5) la mesure est trop pauvre : poids neutre
``1.0``. Au-delà, le facteur croît linéairement de ``1.0`` (taux 0.5) à
``POIDS_MAX`` (taux 1) et décroît jusqu'à ``POIDS_MIN`` (taux 0). Fonction
pure, testable sans base.

Application : :func:`detecteurs_besoins.detecter` accepte ``poids={signature:
facteur}`` — le NEED créé porte ``donnees.poids_signature`` et une
``confiance`` ajustée (``confiance_detecteur * poids``, bornée à [0, 1]).
:func:`poids_pour` borne et assainit chaque facteur lu.

Learning persisté (:func:`capitaliser_mesures`) : chaque signature jugée dont
la mesure diffère du dernier Learning signature produit un objet LEARNING
factuel (« signature contournement : 8 corroborés / 12 jugés = 0.67
IC95[0.39–0.86] ») avec ``donnees.signature``, ``donnees.taux``,
``donnees.n``. La mesure est la même → aucun nouvel enregistrement (dédup par
empreinte). L'objet est écrit via ``entreprise_depot.enregistrer_objet`` : le
modèle exige qu'un Learning soit relié à un OUTCOME ou une INVESTIGATION,
qu'une mesure de signature n'a pas — la validation du dépôt (famille, type,
mode, JSON, secrets) reste appliquée. Aucun Learning tant que ``juges`` = 0 :
un taux sans jugement n'est pas une mesure.

Fail-closed : toute erreur (lecture, écriture d'un Learning) remonte dans
``erreurs`` du rapport, jamais avalée.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any

from meridian.adapters.outbound.postgres import entreprise_depot
from meridian.domain import modele_entreprise as modele

__all__ = [
    "SignaturesInvalide",
    "STATUTS_CONFIRMES", "STATUTS_REFUTES", "STATUTS_JUGES", "STATUT_PERIME",
    "MIN_PREUVES_DEFAUT", "POIDS_MIN", "POIDS_MAX", "PIVOT_TAUX", "Z_IC95",
    "ORIGINE_MESURE",
    "intervalle_wilson", "taux_par_signature", "poids", "poids_pour",
    "confiance_ajustee", "capitaliser_mesures", "mesurer",
]

STATUTS_CONFIRMES = ("CORROBORE", "ADRESSE")
STATUTS_REFUTES = ("REFUTE",)
STATUTS_JUGES = STATUTS_CONFIRMES + STATUTS_REFUTES
STATUT_PERIME = "PERIME"

MIN_PREUVES_DEFAUT = 5
POIDS_MIN = 0.2
POIDS_MAX = 1.5
PIVOT_TAUX = 0.5            # un taux de confirmation de moitié est neutre
Z_IC95 = 1.96               # intervalle de Wilson à 95 %
ORIGINE_MESURE = "signatures_besoins"
_LIMITE_LECTURE = 1000


class SignaturesInvalide(ValueError):
    """Un paramètre de la mesure ne respecte pas son contrat."""


def _tenant(valeur: Any) -> str:
    texte = str(valeur or "").strip()
    if not texte:
        raise SignaturesInvalide("tenant_id obligatoire")
    return texte


def _texte(valeur: Any, maximum: int = 1000) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def _donnees(ligne: Any) -> dict:
    return dict(ligne.get("donnees") or {}) if isinstance(ligne, Mapping) else {}


def _instant(valeur: Any = None) -> datetime:
    if valeur is None:
        return datetime.now(timezone.utc)
    if isinstance(valeur, datetime):
        instant = valeur
    else:
        try:
            instant = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
        except ValueError as exc:
            raise SignaturesInvalide("maintenant : date ISO attendue") from exc
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant


def _id_stable(prefixe: str, *parties: Any) -> str:
    brut = "|".join(str(partie or "") for partie in parties)
    return f"{prefixe}-{hashlib.sha256(brut.encode('utf-8')).hexdigest()[:12]}"


def _statut(ligne: Mapping) -> str:
    return _texte(_donnees(ligne).get("statut")).upper()


def _signature(ligne: Mapping) -> str:
    return _texte(_donnees(ligne).get("signature"))


def _lire_needs(conn: Any, tenant: str) -> list[dict]:
    return entreprise_depot.lister_objets(conn, tenant, type_="NEED", limite=_LIMITE_LECTURE)


def _lire_learnings(conn: Any, tenant: str) -> list[dict]:
    return entreprise_depot.lister_objets(
        conn, tenant, type_="LEARNING", limite=_LIMITE_LECTURE)


# --- Mesure ---


def intervalle_wilson(confirmes: Any, juges: Any, z: float = Z_IC95) -> dict | None:
    """Intervalle de confiance binomial de Wilson ; ``None`` quand ``juges`` = 0.

    Jamais un taux sans n : la borne reste honnête sur les petits échantillons.
    """
    try:
        k, n = int(confirmes), int(juges)
    except (TypeError, ValueError) as exc:
        raise SignaturesInvalide("confirmes et juges doivent être des entiers") from exc
    if n <= 0:
        return None
    if k < 0 or k > n:
        raise SignaturesInvalide("confirmes doit être compris entre 0 et juges")
    zz = float(z) * float(z)
    centre = (k + zz / 2) / (n + zz)
    marge = float(z) * math.sqrt(k * (n - k) / n + zz / 4) / (n + zz)
    return {"bas": max(0.0, centre - marge), "haut": min(1.0, centre + marge),
            "z": float(z)}


def taux_par_signature(
    conn: Any, tenant_id: Any, *, needs: Iterable[Mapping] | None = None,
    z: float = Z_IC95,
) -> dict[str, dict]:
    """Comptes par statut et taux de confirmation de chaque signature de NEED.

    ``needs`` remplace la lecture en base quand il est fourni — mode READ sans
    fixture DB, comme :func:`detecteurs_besoins.detecter`. Rend
    ``{signature: {signature, total, comptes, confirmes, juges, perimes,
    taux_confirme, ic95}}`` ; ``taux_confirme`` et ``ic95`` sont ``None`` tant
    qu'aucun besoin de la signature n'est jugé.
    """
    tenant = _tenant(tenant_id)
    lignes = list(needs) if needs is not None else _lire_needs(conn, tenant)
    par_signature: dict[str, dict] = {}
    for ligne in lignes:
        signature = _signature(ligne)
        entree = par_signature.setdefault(signature, {
            "signature": signature,
            "total": 0,
            "comptes": {statut: 0 for statut in modele.STATUTS_NEED},
            "confirmes": 0, "juges": 0, "perimes": 0,
            "taux_confirme": None, "ic95": None,
        })
        entree["total"] += 1
        statut = _statut(ligne)
        if statut in entree["comptes"]:
            entree["comptes"][statut] += 1
        else:
            entree["comptes"]["AUTRE"] = entree["comptes"].get("AUTRE", 0) + 1
    for entree in par_signature.values():
        comptes = entree["comptes"]
        entree["confirmes"] = sum(comptes[s] for s in STATUTS_CONFIRMES)
        # PERIME est compté à part : hors des jugés, un besoin périmé n'est
        # ni une confirmation ni une réfutation du signal.
        entree["perimes"] = comptes[STATUT_PERIME]
        entree["juges"] = entree["confirmes"] + comptes["REFUTE"]
        if entree["juges"]:
            entree["taux_confirme"] = entree["confirmes"] / entree["juges"]
            entree["ic95"] = intervalle_wilson(
                entree["confirmes"], entree["juges"], z=z)
    return dict(sorted(par_signature.items()))


# --- Poids ---


def poids(
    signature: Any, stats: Mapping | None = None, *,
    min_preuves: int = MIN_PREUVES_DEFAUT,
) -> float:
    """Facteur de confiance d'une signature, borné dans ``[POIDS_MIN, POIDS_MAX]``.

    ``stats`` est l'entrée rendue par :func:`taux_par_signature` (ou tout
    mapping portant ``taux_confirme`` et ``juges``). Tant que
    ``juges < min_preuves`` la mesure est trop pauvre : ``1.0`` neutre. Ensuite
    le facteur croît de ``1.0`` (taux ``PIVOT_TAUX``) jusqu'à ``POIDS_MAX``
    (taux 1) et décroît jusqu'à ``POIDS_MIN`` (taux 0). Fonction pure.
    """
    _texte(signature)  # la signature borne la lecture, sans la valider
    if not isinstance(stats, Mapping):
        return 1.0
    try:
        juges = int(stats.get("juges") or 0)
    except (TypeError, ValueError):
        return 1.0
    taux = stats.get("taux_confirme")
    if taux is None or juges < max(1, int(min_preuves)):
        return 1.0
    taux = min(1.0, max(0.0, float(taux)))
    if taux >= PIVOT_TAUX:
        return min(POIDS_MAX, 1.0 + (taux - PIVOT_TAUX) * (POIDS_MAX - 1.0) / PIVOT_TAUX)
    return max(POIDS_MIN, 1.0 - (PIVOT_TAUX - taux) * (1.0 - POIDS_MIN) / PIVOT_TAUX)


def poids_pour(poids_par_signature: Any, signature: Any) -> float:
    """Facteur à appliquer pour ``signature`` depuis le dict ``{signature: w}``.

    ``None``, clé absente ou valeur non numérique → ``1.0`` neutre ; toute
    valeur reçue est re-bornée dans ``[POIDS_MIN, POIDS_MAX]`` — l'appelant ne
    fait jamais confiance aveuglément au poids fourni.
    """
    if not isinstance(poids_par_signature, Mapping):
        return 1.0
    try:
        facteur = float(poids_par_signature.get(_texte(signature), 1.0))
    except (TypeError, ValueError):
        return 1.0
    if not math.isfinite(facteur):
        return 1.0
    return min(POIDS_MAX, max(POIDS_MIN, facteur))


def confiance_ajustee(confiance_detecteur: Any, facteur: Any) -> float:
    """``confiance_detecteur * facteur``, bornée à ``[0.0, 1.0]`` (contrat du modèle)."""
    try:
        confiance = float(confiance_detecteur) * float(facteur)
    except (TypeError, ValueError):
        return 0.5
    if not math.isfinite(confiance):
        return 0.5
    return round(min(1.0, max(0.0, confiance)), 4)


# --- Learning persisté ---


def _empreinte(signature: str, stats: Mapping) -> str:
    """Empreinte de la mesure : seules les grandeurs jugées la définissent."""
    brut = json.dumps({
        "signature": signature,
        "confirmes": stats["confirmes"],
        "juges": stats["juges"],
        "perimes": stats["perimes"],
    }, sort_keys=True)
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()[:16]


def _est_mesure_signature(ligne: Mapping) -> bool:
    return _texte(_donnees(ligne).get("origine")) == ORIGINE_MESURE


def _derniere_mesure(learnings: Iterable[Mapping], signature: str) -> dict | None:
    """Le dernier Learning signature de cette signature, s'il existe."""
    candidats = [
        ligne for ligne in learnings or ()
        if _est_mesure_signature(ligne) and _signature(ligne) == signature
    ]
    if not candidats:
        return None

    def cle(ligne: Mapping) -> tuple[str, str]:
        donnees = _donnees(ligne)
        return (_texte(donnees.get("mesure_le") or ligne.get("cree_le")
                       or ligne.get("maj_le")), _texte(ligne.get("id")))

    return max(candidats, key=cle)


def _enonce_mesure(signature: str, stats: Mapping) -> str:
    """Énoncé factuel de la mesure — un enregistrement, pas une interprétation."""
    ic = stats.get("ic95")
    borne = (f" IC95[{ic['bas']:.2f}–{ic['haut']:.2f}]" if isinstance(ic, Mapping)
             else "")
    return (f"signature {signature} : {stats['confirmes']} corroborés / "
            f"{stats['juges']} jugés = {stats['taux_confirme']:.2f}{borne}")


def _payload_learning(tenant: str, signature: str, stats: Mapping,
                      facteur: float, instant: datetime) -> dict:
    empreinte = _empreinte(signature, stats)
    enonce = _enonce_mesure(signature, stats)
    return {
        "id": _id_stable("learnsig", tenant, signature, empreinte),
        "famille": "resultat_apprentissage",
        "type": "LEARNING",
        "mode": "INFERRED",
        "titre": enonce,
        "donnees": {
            "enonce": enonce,
            "statut": "PROPOSED",
            "origine": ORIGINE_MESURE,
            "signature": signature,
            "taux": stats["taux_confirme"],
            "n": stats["juges"],
            "confirmes": stats["confirmes"],
            "perimes": stats["perimes"],
            "comptes": dict(stats["comptes"]),
            "ic95": stats["ic95"],
            "poids": facteur,
            "empreinte": empreinte,
            "mesure_le": instant.isoformat(timespec="seconds"),
        },
    }


def capitaliser_mesures(
    conn: Any, tenant_id: Any, stats: Mapping | None = None, *,
    learnings: Iterable[Mapping] | None = None,
    persister: Callable | None = None,
    maintenant: Any = None,
    min_preuves: int = MIN_PREUVES_DEFAUT,
) -> dict:
    """Écrit un Learning de mesure par signature dont les stats ont changé.

    ``stats`` est le résultat de :func:`taux_par_signature` (recalculé si
    absent) ; ``learnings`` remplace la lecture en base ; ``persister`` écrit
    l'objet (défaut : :func:`entreprise_depot.enregistrer_objet`). Une signature
    sans besoin jugé ou sans signature ne produit rien ; la même mesure que le
    dernier Learning signature non plus (dédup par empreinte).

    Rapport : ``{tenant, ecrits, ignores, erreurs, totaux}`` — toute erreur
    d'écriture remonte dans ``erreurs``, jamais avalée.
    """
    tenant = _tenant(tenant_id)
    instant = _instant(maintenant)
    if stats is None:
        stats = taux_par_signature(conn, tenant)
    if persister is None:
        def persister(c, t, objet):
            return entreprise_depot.enregistrer_objet(c, t, objet)
    lignes = (list(learnings) if learnings is not None
              else _lire_learnings(conn, tenant))
    ecrits: list[dict] = []
    ignores: list[dict] = []
    erreurs: list[dict] = []
    for signature in sorted(stats):
        entree = stats[signature]
        if not signature:
            ignores.append({"signature": signature, "raison": "NEED sans signature"})
            continue
        if not entree["juges"]:
            ignores.append({"signature": signature,
                            "raison": "aucun besoin jugé : pas de mesure"})
            continue
        empreinte = _empreinte(signature, entree)
        derniere = _derniere_mesure(lignes, signature)
        if (derniere is not None
                and _texte(_donnees(derniere).get("empreinte")) == empreinte):
            ignores.append({"signature": signature,
                            "raison": "mesure identique au dernier Learning"})
            continue
        facteur = poids(signature, entree, min_preuves=min_preuves)
        try:
            ligne = persister(
                conn, tenant, _payload_learning(tenant, signature, entree,
                                                facteur, instant))
        except Exception as exc:  # fail-closed : les autres signatures continuent
            erreurs.append({"signature": signature, "erreur": str(exc)})
            continue
        ecrits.append({"signature": signature,
                       "id": _texte((ligne or {}).get("id")) or
                       _id_stable("learnsig", tenant, signature, empreinte),
                       "taux": entree["taux_confirme"], "n": entree["juges"]})
    return {
        "tenant": tenant,
        "ecrits": ecrits,
        "ignores": ignores,
        "erreurs": erreurs,
        "totaux": {"ecrits": len(ecrits), "ignores": len(ignores),
                   "erreurs": len(erreurs)},
    }


def mesurer(
    conn: Any, tenant_id: Any, *, needs: Iterable[Mapping] | None = None,
    learnings: Iterable[Mapping] | None = None,
    persister: Callable | None = None,
    maintenant: Any = None,
    min_preuves: int = MIN_PREUVES_DEFAUT,
    z: float = Z_IC95,
    ecrire_learnings: bool = True,
) -> dict:
    """Mesure complète d'une passe : stats, poids par signature, Learnings.

    Rend ``{tenant, stats, poids, learnings}`` — ``poids`` est le dict prêt à
    passer à :func:`detecteurs_besoins.detecter`. ``ecrire_learnings=False``
    borne la passe à la mesure (aucune écriture).
    """
    tenant = _tenant(tenant_id)
    stats = taux_par_signature(conn, tenant, needs=needs, z=z)
    facteurs = {
        signature: poids(signature, entree, min_preuves=min_preuves)
        for signature, entree in stats.items() if signature
    }
    if ecrire_learnings:
        rapport = capitaliser_mesures(
            conn, tenant, stats, learnings=learnings, persister=persister,
            maintenant=maintenant, min_preuves=min_preuves)
    else:
        rapport = {"tenant": tenant, "ecrits": [], "ignores": [], "erreurs": [],
                   "totaux": {"ecrits": 0, "ignores": 0, "erreurs": 0}}
    return {"tenant": tenant, "stats": stats, "poids": facteurs,
            "learnings": rapport}
