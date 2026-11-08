"""Métriques de la revue humaine (plan Cognition IA, C3).

La revue tranche les Claims ``PROPOSED`` : la table ``revue`` garde chaque
décision (``ACCEPTED`` / ``CONTESTED``), immuable, avant le changement de
statut du claim. Ce module mesure ce que la revue produit — jamais un
nombre sans ``n``, même règle que C4 (:mod:`calibration`) et C5
(:mod:`signatures_besoins`, dont l'intervalle de Wilson est réutilisé).

Vocabulaire mesuré : le schéma ne connaît que deux décisions de revue.
« Corrigé » n'existe pas comme verdict : il est mesuré par ce que la revue
a laissé — une revue ``CONTESTED`` dont le claim est désormais
``SUPERSEDED`` (une version corrigée l'a remplacé) ; toute autre revue
``CONTESTED`` est un refus (claim ``CONTESTED`` ou ``INVALIDATED``).

- ``acceptes`` : revue ``ACCEPTED``.
- ``corriges`` : revue ``CONTESTED`` et claim ``SUPERSEDED``.
- ``refuses`` : revue ``CONTESTED`` et claim non ``SUPERSEDED``.

Plusieurs revues peuvent viser un même claim (``depot.reviser`` sans
``proposee_de`` n'interdit pas une seconde revue) : le verdict compté est
la **dernière** revue de la fenêtre — c'est elle qui laisse le statut —
tandis que le délai de revue court de l'enregistrement du claim à sa
**première** revue. ``total`` compte les lignes de revue lues ; ``n``
compte les claims décidés (un par claim) — ``n = acceptes + corriges +
refuses``.

Repli : un claim dont le statut a quitté ``PROPOSED`` sans aucune ligne de
revue (données antérieures à l'instrumentation, écritures hors
``depot.reviser``) est tout de même mesuré, classé par son statut courant
(``ACCEPTED`` → accepté, ``SUPERSEDED`` → corrigé, ``CONTESTED`` /
``INVALIDATED`` → refusé). Il n'a pas de date de revue : placé au jour de
``enregistre_le``, exclu du délai médian, compté dans ``sans_revue``.

Fail-soft : revue vide → comptes à 0 et taux à ``None`` (``n < minimum``,
défaut 5) ; jamais d'erreur sur une mesure absente. Lecture seule,
bornée au tenant et à la fenêtre ; compatible psycopg et sqlite (tests).
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
import statistics
from typing import Any

from meridian.adapters.outbound.postgres import signatures_besoins

try:
    from psycopg.rows import dict_row as _dict_row
except ImportError:  # pragma: no cover - psycopg est une dépendance applicative
    _dict_row = None

__all__ = [
    "MetriquesRevueInvalide",
    "MIN_MESURE",
    "metriques",
]

MIN_MESURE = 5          # comme C5 : pas de taux publié sous ce seuil
_JOURS_DEFAUT = 30
_JOURS_MAX = 366
_STATUTS_REFUSES = ("CONTESTED", "INVALIDATED")


class MetriquesRevueInvalide(ValueError):
    """Un paramètre de la mesure ne respecte pas son contrat."""


def _tenant(valeur: Any) -> str:
    texte = str(valeur or "").strip()
    if not texte:
        raise MetriquesRevueInvalide("tenant_id obligatoire")
    return texte


def _entier(valeur: Any, champ: str, *, minimum: int, maximum: int) -> int:
    if isinstance(valeur, bool):
        raise MetriquesRevueInvalide(f"{champ} : entier attendu")
    try:
        nombre = int(valeur)
    except (TypeError, ValueError) as exc:
        raise MetriquesRevueInvalide(f"{champ} : entier attendu") from exc
    return max(minimum, min(nombre, maximum))


def _maintenant(valeur: Any = None) -> datetime:
    if valeur is None:
        return datetime.now(timezone.utc)
    if isinstance(valeur, datetime):
        instant = valeur
    else:
        try:
            instant = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
        except ValueError as exc:
            raise MetriquesRevueInvalide("maintenant : date ISO attendue") from exc
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant


def _dt(valeur: Any) -> datetime | None:
    """``datetime`` ou ISO → ``datetime`` UTC ; ``None`` si illisible (fail-soft)."""
    if valeur is None:
        return None
    if isinstance(valeur, datetime):
        instant = valeur
    elif isinstance(valeur, date):
        instant = datetime(valeur.year, valeur.month, valeur.day)
    else:
        try:
            instant = datetime.fromisoformat(
                str(valeur).strip().replace("Z", "+00:00").replace(" ", "T"))
        except ValueError:
            return None
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant


def _est_sqlite(conn: Any) -> bool:
    return type(conn).__module__.split(".", 1)[0] == "sqlite3"


def _sql(conn: Any, requete: str) -> str:
    return requete.replace("%s", "?") if _est_sqlite(conn) else requete


def _cursor(conn: Any) -> Any:
    if _dict_row is not None:
        try:
            return conn.cursor(row_factory=_dict_row)
        except TypeError:
            pass
    return conn.cursor()


def _toutes(conn: Any, requete: str, parametres: tuple = ()) -> list[Any]:
    cur = _cursor(conn)
    try:
        cur.execute(_sql(conn, requete), parametres)
        return list(cur.fetchall())
    finally:
        fermer = getattr(cur, "close", None)
        if callable(fermer):
            fermer()


def _champ(ligne: Any, nom: str, rang: int) -> Any:
    if isinstance(ligne, Mapping):
        return ligne.get(nom)
    return ligne[rang]


# --- Lectures bornées ---


def _lire_revues(conn: Any, tenant: str, debut: datetime, fin: datetime) -> list[dict]:
    """Revues de la fenêtre, par claim croissant puis chronologique."""
    lignes = _toutes(
        conn,
        "SELECT r.id AS revue_id, r.claim_id, r.decision, r.le, "
        "c.statut AS claim_statut, c.enregistre_le AS claim_cree "
        "FROM revue r LEFT JOIN claim c ON c.id = r.claim_id "
        "WHERE r.tenant_id = %s AND r.le >= %s AND r.le <= %s "
        "ORDER BY r.claim_id, r.le, r.id",
        (tenant, debut, fin),
    )
    revues: list[dict] = []
    for ligne in lignes:
        le = _dt(_champ(ligne, "le", 3))
        if le is None or le < debut or le > fin:
            continue
        revues.append({
            "revue_id": _champ(ligne, "revue_id", 0),
            "claim_id": _champ(ligne, "claim_id", 1),
            "decision": str(_champ(ligne, "decision", 2) or "").upper(),
            "le": le,
            "claim_statut": str(_champ(ligne, "claim_statut", 4) or "").upper(),
            "claim_cree": _dt(_champ(ligne, "claim_cree", 5)),
        })
    return revues


def _lire_sans_revue(
    conn: Any, tenant: str, debut: datetime, fin: datetime,
) -> list[dict]:
    """Claims du tenant sortis de ``PROPOSED`` sans aucune revue (repli)."""
    lignes = _toutes(
        conn,
        "SELECT c.id, c.statut, c.enregistre_le FROM claim c "
        "WHERE c.tenant_id = %s AND c.statut <> 'PROPOSED' "
        "AND c.enregistre_le >= %s AND c.enregistre_le <= %s "
        "AND NOT EXISTS (SELECT 1 FROM revue r WHERE r.claim_id = c.id) "
        "ORDER BY c.id",
        (tenant, debut, fin),
    )
    claims: list[dict] = []
    for ligne in lignes:
        cree = _dt(_champ(ligne, "enregistre_le", 2))
        if cree is None or cree < debut or cree > fin:
            continue
        claims.append({
            "claim_id": _champ(ligne, "id", 0),
            "statut": str(_champ(ligne, "statut", 1) or "").upper(),
            "cree": cree,
        })
    return claims


def _compter_en_attente(conn: Any, tenant: str) -> int:
    """Claims encore ``PROPOSED`` sans revue : le stock en attente, toutes dates."""
    lignes = _toutes(
        conn,
        "SELECT count(*) AS n FROM claim c WHERE c.tenant_id = %s "
        "AND c.statut = 'PROPOSED' "
        "AND NOT EXISTS (SELECT 1 FROM revue r WHERE r.claim_id = c.id)",
        (tenant,),
    )
    if not lignes:
        return 0
    try:
        return int(_champ(lignes[0], "n", 0) or 0)
    except (TypeError, ValueError):
        return 0


# --- Mesure ---


def _verdict(decision: str, statut: str) -> str:
    """``accepte`` / ``corrige`` / ``refuse`` d'une revue ou d'un statut seul.

    La décision de la revue fait foi ; le statut du claim ne sert qu'à
    distinguer un contesté corrigé (``SUPERSEDED``) d'un refus, puis à
    classer les claims sans revue (repli).
    """
    if decision == "ACCEPTED":
        return "accepte"
    if decision == "CONTESTED":
        return "corrige" if statut == "SUPERSEDED" else "refuse"
    # Repli ou décision inconnue : le statut du claim fait foi.
    if statut == "ACCEPTED":
        return "accepte"
    if statut == "SUPERSEDED":
        return "corrige"
    return "refuse"        # CONTESTED / INVALIDATED / inconnu : pas retenu


def _jour(instant: datetime) -> str:
    return instant.date().isoformat()


def metriques(
    conn: Any,
    tenant_id: Any,
    *,
    jours: Any = _JOURS_DEFAUT,
    minimum: Any = MIN_MESURE,
    maintenant: Any = None,
) -> dict:
    """Métriques de la revue humaine du tenant sur ``jours`` jours glissants.

    Rend ``{tenant, jours, minimum, fenetre, n, total, acceptes, corriges,
    refuses, taux_accepte, taux_corrige, taux_refuse, ic95,
    delai_revu_median_heures, en_attente, sans_revue, par_jour}``.

    ``n`` = claims décidés dans la fenêtre ; ``taux_*`` et ``ic95`` sont
    ``None`` tant que ``n < minimum`` — jamais un ratio sans n.
    ``delai_revu_median_heures`` est la médiane des délais
    ``première revue − enregistrement du claim`` ; ``None`` sans délai
    mesurable. ``par_jour`` couvre chaque jour de la fenêtre, zéros compris.
    """
    tenant = _tenant(tenant_id)
    jours_ = _entier(jours, "jours", minimum=1, maximum=_JOURS_MAX)
    minimum_ = _entier(minimum, "minimum", minimum=1, maximum=1000000)
    fin = _maintenant(maintenant)
    debut = fin - timedelta(days=jours_)

    revues = _lire_revues(conn, tenant, debut, fin)
    par_claim: dict[Any, list[dict]] = {}
    for revue in revues:
        par_claim.setdefault(revue["claim_id"], []).append(revue)

    comptes = {"accepte": 0, "corrige": 0, "refuse": 0}
    delais: list[float] = []
    par_jour: dict[str, dict] = {}
    for claim_revues in par_claim.values():
        premiere, derniere = claim_revues[0], claim_revues[-1]
        verdict = _verdict(derniere["decision"], derniere["claim_statut"])
        comptes[verdict] += 1
        jour = par_jour.setdefault(_jour(derniere["le"]), {
            "jour": _jour(derniere["le"]),
            "total": 0, "acceptes": 0, "corriges": 0, "refuses": 0,
        })
        jour["total"] += 1
        jour[f"{verdict}s"] += 1
        cree = premiere["claim_cree"]
        if cree is not None:
            heures = (premiere["le"] - cree).total_seconds() / 3600.0
            if heures >= 0:  # une revue ne précède pas l'enregistrement
                delais.append(heures)

    sans_revue = 0
    for claim in _lire_sans_revue(conn, tenant, debut, fin):
        verdict = _verdict("", claim["statut"])
        comptes[verdict] += 1
        sans_revue += 1
        jour = par_jour.setdefault(_jour(claim["cree"]), {
            "jour": _jour(claim["cree"]),
            "total": 0, "acceptes": 0, "corriges": 0, "refuses": 0,
        })
        jour["total"] += 1
        jour[f"{verdict}s"] += 1

    n = comptes["accepte"] + comptes["corrige"] + comptes["refuse"]
    mesure = n >= minimum_
    ic95 = {
        verdict: (signatures_besoins.intervalle_wilson(comptes[verdict], n)
                  if mesure else None)
        for verdict in ("accepte", "corrige", "refuse")
    }

    jours_couverts: list[dict] = []
    jour = debut.date()
    fin_jour = fin.date()
    while jour <= fin_jour:
        cle = jour.isoformat()
        jours_couverts.append(par_jour.get(cle, {
            "jour": cle, "total": 0, "acceptes": 0, "corriges": 0, "refuses": 0,
        }))
        jour += timedelta(days=1)

    return {
        "tenant": tenant,
        "jours": jours_,
        "minimum": minimum_,
        "fenetre": {"debut": debut.isoformat(timespec="seconds"),
                    "fin": fin.isoformat(timespec="seconds")},
        "n": n,
        "total": len(revues),
        "acceptes": comptes["accepte"],
        "corriges": comptes["corrige"],
        "refuses": comptes["refuse"],
        "taux_accepte": comptes["accepte"] / n if mesure else None,
        "taux_corrige": comptes["corrige"] / n if mesure else None,
        "taux_refuse": comptes["refuse"] / n if mesure else None,
        "ic95": ic95,
        "delai_revu_median_heures": (
            round(statistics.median(delais), 2) if delais else None),
        "en_attente": _compter_en_attente(conn, tenant),
        "sans_revue": sans_revue,
        "par_jour": jours_couverts,
    }
