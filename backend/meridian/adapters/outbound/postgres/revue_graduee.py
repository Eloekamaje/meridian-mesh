"""Revue graduée par risque (plan Cognition IA, D3) — human-on-the-loop, révocable.

Toutes les propositions ne méritent pas la même revue. Ce module classe
déterministement chaque claim ``PROPOSED`` et chaque proposition
``objet_entreprise`` (``mode='PROPOSED'`` portant ``donnees.type_claim``) en
trois niveaux :

- ``BLOQUANT`` : la proposition touche un twin critique (domaines
  ``paiements``/``risque``, packs en lecture seule), un prédicat sensible
  (décision, suppression, sécurité), réécrit un claim ``INVALIDATED``, ou porte
  sur 3 twins ou plus. Elle reste ``PROPOSED``, marquée
  ``donnees.bloque='revue_requise'`` — la revue humaine est obligatoire.
- ``ATTENTION`` : un ``OBSERVED`` qui contredit un ``DECLARED`` encore valide
  (contournement), un périmètre de 2 twins, ou une preuve de source externe non
  vérifiée. Elle reste ``PROPOSED``, marquée ``donnees.revue_niveau``.
- ``AUTO_VISIBLE`` : périmètre étroit, preuve directe, rien de sensible. La
  proposition est auto-acceptée — la revue ``ACCEPTED`` est écrite (acteur
  ``revue_graduee``) **avant** le statut, comme toute revue — mais l'acceptation
  reste **révocable** pendant ``REVOCABLE_JOURS`` jours
  (``donnees.revocable_jusqua``) : une revue postérieure peut l'invalider via
  :func:`revoquer`, qui bascule le claim en ``CONTESTED`` et journalise.

Jamais de silencieux : chaque auto-accept et chaque révocation est tracée dans
``outil_audit`` (via :mod:`audit_harness`) et comptée dans le rapport rendu par
:func:`appliquer`. La répartition courante des niveaux se lit avec
:func:`niveaux` (comptes seuls, jamais de ratio sans n — même règle que C3).
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import re
from typing import Any
import unicodedata

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from meridian.adapters.outbound.postgres import audit_harness
from meridian.domain import packs_domaines

__all__ = [
    "ACTEUR",
    "ATTENTION",
    "AUTO_VISIBLE",
    "BLOQUANT",
    "PACKS_CRITIQUES",
    "REVOCABLE_JOURS",
    "RevocationRefusee",
    "RevueGradueeInvalide",
    "appliquer",
    "jumeau_critique",
    "marques_critiques",
    "niveau_revise",
    "niveaux",
    "revoquer",
]

AUTO_VISIBLE = "AUTO_VISIBLE"
ATTENTION = "ATTENTION"
BLOQUANT = "BLOQUANT"

ACTEUR = "revue_graduee"
REVOCABLE_JOURS = 30
JOURS_RECENTS_DEFAUT = 30
SEUIL_BLOQUANT_TWINS = 3
SEUIL_ATTENTION_TWINS = 2

# Packs de domaine en lecture seule dont le périmètre est critique : toute
# proposition qui touche un twin de ces domaines/applications exige une revue.
PACKS_CRITIQUES = ("paiements", "risque")
# Prédicats sensibles (décision, suppression, sécurité) — radicaux comparés en
# préfixe de token : DECI couvre DECIDE/DECISION, SUPPR couvre
# SUPPRIME/SUPPRESSION/SUPPRIMER, SECUR couvre SECURITE (et pas « INSECURITE »,
# qui ne commence pas par le radical).
MARQUEURS_SENSIBLES = ("DECI", "SUPPR", "SECUR")
# Une preuve « directe » vient du code ou de sa documentation ; les autres
# sources sont externes et doivent avoir été vérifiées pour passer seules.
SOURCES_DIRECTES = frozenset({"GIT", "DOCUMENTATION"})
VERIFICATIONS_SURES = ("verifie", "selon", "recoupe")
_CHAMPS_TWINS = ("twin_ids", "twins", "jumeau_ids", "application_ids")


class RevueGradueeInvalide(ValueError):
    """Un paramètre du routage ne respecte pas son contrat."""


class RevocationRefusee(PermissionError):
    """La révocation demandée est hors fenêtre ou ne vise pas un auto-accept."""


def _texte(valeur: Any) -> str:
    return " ".join(str(valeur or "").split()).strip()


def _tenant(valeur: Any) -> str:
    texte = _texte(valeur)
    if not texte:
        raise RevueGradueeInvalide("tenant_id obligatoire")
    return texte


def _maintenant(valeur: Any = None) -> datetime:
    if valeur is None:
        return datetime.now(timezone.utc)
    if isinstance(valeur, datetime):
        instant = valeur
    else:
        try:
            instant = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
        except ValueError as exc:
            raise RevueGradueeInvalide("maintenant : date ISO attendue") from exc
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant


def _dt(valeur: Any) -> datetime | None:
    if valeur is None:
        return None
    if isinstance(valeur, datetime):
        instant = valeur
    else:
        try:
            instant = datetime.fromisoformat(
                str(valeur).strip().replace("Z", "+00:00").replace(" ", "T"))
        except ValueError:
            return None
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant


def _normaliser(valeur: Any) -> str:
    """Minuscules sans accents ni séparateurs — la comparaison des domaines."""
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", texte.lower()).strip("_")


def _liste(valeur: Any) -> list:
    if valeur is None:
        return []
    if isinstance(valeur, (str, bytes)) or not isinstance(valeur, Iterable):
        return [valeur]
    return list(valeur)


def _donnees(element: Any) -> dict:
    donnees = element.get("donnees") if isinstance(element, Mapping) else None
    return dict(donnees) if isinstance(donnees, Mapping) else {}


# --- Twins critiques : les packs read-only dessinent le périmètre sensible ---


@lru_cache(maxsize=1)
def marques_critiques() -> dict:
    """Domaines et applications des packs ``paiements``/``risque``, normalisés.

    Lus dans les packs eux-mêmes (leur périmètre fait foi) ; repli sur la
    lecture actuelle des deux packs si le dossier est indisponible — jamais de
    silencieux : un twin « paiements » reste bloquant même sans fichiers.
    """
    domaines: set[str] = set()
    applications: set[str] = set()
    try:
        packs = packs_domaines.charger_packs()
    except Exception:  # noqa: BLE001 - le repli borne la criticité, il ne lève pas
        packs = ()
    for pack in packs:
        if pack.id not in PACKS_CRITIQUES:
            continue
        scope = pack.scope or {}
        domaines.update(_normaliser(v) for v in scope.get("domaines") or ())
        applications.update(_normaliser(v) for v in scope.get("applications") or ())
    if not domaines and not applications:
        domaines = {"paiement", "paiements", "risque", "conformite"}
        applications = {"paiements", "comptes", "conduit", "fraude"}
    return {"domaines": frozenset(domaines), "applications": frozenset(applications)}


def jumeau_critique(jumeau: Any, marques: Any = None) -> bool:
    """Vrai si le jumeau relève d'un pack critique (domaine ou application)."""
    if not isinstance(jumeau, Mapping):
        return False
    marques = marques or marques_critiques()
    if _normaliser(jumeau.get("domaine")) in marques["domaines"]:
        return True
    for cle in ("id", "application_id", "perimetre_id", "perimetre", "nom"):
        if _normaliser(jumeau.get(cle)) in marques["applications"]:
            return True
    identifiants = jumeau.get("identifiants")
    if isinstance(identifiants, Mapping):
        domaines = marques["domaines"] | marques["applications"]
        for cle in ("domaine", "application", "application_id"):
            if _normaliser(identifiants.get(cle)) in domaines:
                return True
    return False


# --- Niveau déterministe ---


def _twins(element: Any) -> set[str]:
    """Twins impactés par la proposition : portés par ``donnees`` + le twin porteur."""
    donnees = _donnees(element)
    ids: set[str] = set()
    for champ in _CHAMPS_TWINS:
        ids.update(str(v).strip() for v in _liste(donnees.get(champ)) if str(v).strip())
    for cle in ("jumeau_id", "twin_id"):
        valeur = element.get(cle) if isinstance(element, Mapping) else None
        valeur = valeur or donnees.get(cle)
        if _texte(valeur):
            ids.add(_texte(valeur))
    return ids


def niveau_revise(element: Any, contexte: Any = None) -> str:
    """``AUTO_VISIBLE`` / ``ATTENTION`` / ``BLOQUANT`` d'un claim ou d'une proposition.

    ``element`` est un mapping (ligne ``claim`` ou ``objet_entreprise``, ou la
    forme ``{sujet, predicat, objet, type, donnees}`` d'une proposition) ;
    ``contexte`` porte les faits lus en base par l'appelant :
    ``jumeau_critique``, ``invalide_remplace``, ``nb_twins``,
    ``contredit_declare``, ``source_externe_non_verifiee``. Déterministe : mêmes
    entrées, même niveau ; le bloquant l'emporte sur l'attention.
    """
    if not isinstance(element, Mapping):
        raise RevueGradueeInvalide("element : objet attendu")
    ctx = dict(contexte or {})
    donnees = _donnees(element)
    texte_sensible = " ".join(
        str(v or "") for v in (
            element.get("predicat"), element.get("type"),
            donnees.get("predicat"), donnees.get("type_claim"),
        )
    ).upper()
    jetons = re.split(r"[^A-Z0-9]+", texte_sensible)
    sensible = any(
        jeton.startswith(marqueur) for jeton in jetons for marqueur in MARQUEURS_SENSIBLES)
    twins = ctx.get("nb_twins")
    if twins is None:
        twins = len(_twins(element))
    if (ctx.get("jumeau_critique") or sensible or ctx.get("invalide_remplace")
            or twins >= SEUIL_BLOQUANT_TWINS):
        return BLOQUANT
    if (ctx.get("contredit_declare") or twins >= SEUIL_ATTENTION_TWINS
            or ctx.get("source_externe_non_verifiee")):
        return ATTENTION
    return AUTO_VISIBLE


# --- Contexte lu en base ---


def _assurer_colonnes(conn: Any) -> None:
    """La colonne ``donnees`` du claim, posée aussi par ``schema.sql`` (idempotent)."""
    conn.execute(
        "ALTER TABLE claim ADD COLUMN IF NOT EXISTS donnees jsonb NOT NULL DEFAULT '{}'::jsonb")


def _contexte_claim(conn: Any, ligne: Mapping, marques: Mapping) -> dict:
    """Faits déterministes lus en base pour un claim donné."""
    claim_id, jumeau_id = ligne["id"], ligne["jumeau_id"]
    jumeau = {
        "id": jumeau_id, "domaine": ligne.get("j_domaine"),
        "application_id": ligne.get("j_application_id"), "nom": ligne.get("j_nom"),
        "perimetre": ligne.get("j_perimetre"), "perimetre_id": ligne.get("j_perimetre_id"),
        "identifiants": ligne.get("j_identifiants"),
    }
    contredit = False
    if str(ligne.get("mode") or "").upper() == "OBSERVED":
        contredit = conn.execute(
            "SELECT 1 FROM claim WHERE jumeau_id = %s AND predicat = %s AND id <> %s "
            "AND valide_jusqua IS NULL AND mode = 'DECLARED' AND objet <> %s LIMIT 1",
            (jumeau_id, ligne["predicat"], claim_id, ligne["objet"])).fetchone() is not None
    invalide = conn.execute(
        "SELECT 1 FROM claim WHERE id <> %s AND valide_jusqua IS NULL AND statut = 'INVALIDATED' "
        "AND (id = %s OR (jumeau_id = %s AND predicat = %s)) LIMIT 1",
        (claim_id, ligne.get("remplace_id") or -1, jumeau_id, ligne["predicat"]),
    ).fetchone() is not None
    externe = conn.execute(
        "SELECT 1 FROM claim_preuve cp JOIN preuve p ON p.id = cp.preuve_id "
        "JOIN source so ON so.id = p.source_id "
        "WHERE cp.claim_id = %s AND cp.role = 'SUPPORT' AND so.type <> ALL(%s) LIMIT 1",
        (claim_id, sorted(SOURCES_DIRECTES))).fetchone() is not None
    verifiee = conn.execute(
        "SELECT 1 FROM verification WHERE claim_id = %s AND etat = ANY(%s) LIMIT 1",
        (claim_id, list(VERIFICATIONS_SURES))).fetchone() is not None
    return {
        "jumeau_critique": jumeau_critique(jumeau, marques),
        "invalide_remplace": invalide,
        "contredit_declare": contredit,
        "source_externe_non_verifiee": externe and not verifiee,
        "nb_twins": len(_twins(ligne)),
    }


def _contexte_proposition(conn: Any, tenant: str, ligne: Mapping, marques: Mapping) -> dict:
    """Faits pour une proposition ``objet_entreprise`` (jumeaux via ``donnees``)."""
    donnees = _donnees(ligne)
    twin_ids = sorted(_twins(ligne))
    critique = bool(donnees.get("domaine") and
                    _normaliser(donnees["domaine"]) in marques["domaines"])
    for twin_id in twin_ids:
        jumeau = conn.execute(
            "SELECT id, domaine, application_id, nom, perimetre, perimetre_id, identifiants "
            "FROM jumeau WHERE id = %s", (twin_id,)).fetchone()
        if jumeau is not None and jumeau_critique(dict(jumeau), marques):
            critique = True
            break
    contredit = False
    if str(ligne.get("mode") or "").upper() == "OBSERVED" and twin_ids:
        contredit = conn.execute(
            "SELECT 1 FROM objet_entreprise WHERE tenant_id = %s AND id <> %s "
            "AND mode = 'DECLARED' AND valide_jusqua IS NULL "
            "AND donnees->'twin_ids' ?| %s::text[] LIMIT 1",
            (tenant, ligne["id"], twin_ids)).fetchone() is not None
    remplace = _texte(donnees.get("remplace_id") or donnees.get("remplace"))
    invalide = bool(donnees.get("invalide_remplace"))
    if remplace and not invalide:
        invalide = conn.execute(
            "SELECT 1 FROM objet_entreprise WHERE tenant_id = %s AND id = %s "
            "AND donnees->>'statut' = 'INVALIDATED'",
            (tenant, remplace)).fetchone() is not None
    externe_non_verifiee = bool(donnees.get("source_externe_non_verifiee")) or (
        bool(_liste(donnees.get("sources_externes"))) and not donnees.get("verifie"))
    return {
        "jumeau_critique": critique,
        "invalide_remplace": invalide,
        "contredit_declare": contredit,
        "source_externe_non_verifiee": externe_non_verifiee,
        "nb_twins": len(twin_ids),
    }


# --- Audit ---


def _tracer(audit: Any, capacite: str, arguments: dict, maintenant: datetime) -> dict:
    """Une ligne d'audit ; rend le statut du sink (fail-soft, jamais levé)."""
    return audit.enregistrer({
        "outil": "revue_graduee", "capacite": capacite,
        "arguments": arguments, "statut": "ok", "quand": maintenant,
    })


# --- Routage ---


def _claims_a_router(conn: Any, tenant: str, depuis: datetime) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT c.id, c.jumeau_id, c.sujet, c.predicat, c.objet, c.type, c.mode, "
            "c.origine, c.remplace_id, c.donnees, c.enregistre_le, "
            "j.domaine AS j_domaine, j.application_id AS j_application_id, "
            "j.nom AS j_nom, j.perimetre AS j_perimetre, j.perimetre_id AS j_perimetre_id, "
            "j.identifiants AS j_identifiants "
            "FROM claim c JOIN jumeau j ON j.id = c.jumeau_id "
            "WHERE c.tenant_id = %s AND c.statut = 'PROPOSED' AND c.valide_jusqua IS NULL "
            "AND c.enregistre_le >= %s "
            "AND NOT EXISTS (SELECT 1 FROM revue r WHERE r.claim_id = c.id) "
            "AND NOT (c.donnees ? 'revue_niveau') ORDER BY c.id",
            (tenant, depuis)).fetchall()


def _propositions_a_router(conn: Any, tenant: str, depuis: datetime) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT id, type, mode, titre, donnees, cree_le FROM objet_entreprise "
            "WHERE tenant_id = %s AND mode = 'PROPOSED' AND valide_jusqua IS NULL "
            "AND cree_le >= %s AND donnees ? 'type_claim' "
            "AND NOT (donnees ? 'revue_niveau') ORDER BY id",
            (tenant, depuis)).fetchall()


def _router_claim(conn: Any, audit: Any, tenant: str, ligne: Mapping,
                  marques: Mapping, maintenant: datetime, rapport: dict) -> None:
    """Route un claim : accepte révocable, marque attention ou bloque. Tracé."""
    contexte = _contexte_claim(conn, ligne, marques)
    niveau = niveau_revise(ligne, contexte)
    claim_id = ligne["id"]
    detail = {"claim_id": claim_id, "jumeau_id": ligne["jumeau_id"], "niveau": niveau}
    if niveau == BLOQUANT:
        conn.execute(
            "UPDATE claim SET donnees = donnees || %s WHERE id = %s",
            (Jsonb({"revue_niveau": BLOQUANT, "bloque": "revue_requise",
                    "revue_le": maintenant.isoformat(timespec="seconds")}), claim_id))
        rapport["bloquants"] += 1
        detail["action"] = "bloque"
    elif niveau == ATTENTION:
        conn.execute(
            "UPDATE claim SET donnees = donnees || %s WHERE id = %s",
            (Jsonb({"revue_niveau": ATTENTION,
                    "attention": {"raison": "revue_attention",
                                  "depuis": maintenant.isoformat(timespec="seconds")},
                    "revue_le": maintenant.isoformat(timespec="seconds")}), claim_id))
        rapport["attentions"] += 1
        detail["action"] = "attention"
    else:
        preuve = conn.execute(
            "SELECT 1 FROM claim_preuve WHERE claim_id = %s AND role = 'SUPPORT' LIMIT 1",
            (claim_id,)).fetchone() is not None
        revocable = (maintenant + timedelta(days=REVOCABLE_JOURS)).isoformat(timespec="seconds")
        if not preuve:
            # Invariant : ACCEPTED exige une preuve SUPPORT — reste proposé, marqué.
            conn.execute(
                "UPDATE claim SET donnees = donnees || %s WHERE id = %s",
                (Jsonb({"revue_niveau": AUTO_VISIBLE, "attente": "sans_preuve_support",
                        "revue_le": maintenant.isoformat(timespec="seconds")}), claim_id))
            rapport["sans_preuve"] += 1
            detail["action"] = "attente_preuve"
        else:
            conn.execute(
                "INSERT INTO revue (tenant_id, claim_id, acteur, decision, motif, le) "
                "VALUES (%s, %s, %s, 'ACCEPTED', %s, %s)",
                (tenant, claim_id, ACTEUR,
                 f"auto-accepté AUTO_VISIBLE — révocable jusqu'au {revocable}",
                 maintenant))
            conn.execute(
                "UPDATE claim SET statut = 'ACCEPTED', donnees = donnees || %s WHERE id = %s",
                (Jsonb({"revue_niveau": AUTO_VISIBLE, "auto_accepte": True,
                        "revocable_jusqua": revocable,
                        "revue_le": maintenant.isoformat(timespec="seconds")}), claim_id))
            statut_audit = _tracer(
                audit, "auto_accept_claim",
                {"claim_id": claim_id, "jumeau_id": ligne["jumeau_id"],
                 "predicat": ligne["predicat"], "revocable_jusqua": revocable},
                maintenant)
            if statut_audit.get("statut") != "ok":
                rapport["audit_erreurs"] += 1
            rapport["auto_visibles"] += 1
            detail["action"] = "auto_accepte"
            detail["revocable_jusqua"] = revocable
    rapport["details"].append(detail)


def _router_proposition(conn: Any, audit: Any, tenant: str, ligne: Mapping,
                        marques: Mapping, maintenant: datetime, rapport: dict) -> None:
    """Route une proposition objet : CONFIRMED révocable, attention ou blocage."""
    contexte = _contexte_proposition(conn, tenant, ligne, marques)
    niveau = niveau_revise(ligne, contexte)
    objet_id = ligne["id"]
    detail = {"objet_id": objet_id, "type": ligne.get("type"), "niveau": niveau}
    compte = rapport["propositions"]
    if niveau == BLOQUANT:
        patch = {"revue_niveau": BLOQUANT, "bloque": "revue_requise",
                 "revue_le": maintenant.isoformat(timespec="seconds")}
        conn.execute(
            "UPDATE objet_entreprise SET donnees = donnees || %s, maj_le = %s "
            "WHERE tenant_id = %s AND id = %s",
            (Jsonb(patch), maintenant, tenant, objet_id))
        compte["bloquants"] += 1
        detail["action"] = "bloque"
    elif niveau == ATTENTION:
        patch = {"revue_niveau": ATTENTION,
                 "attention": {"raison": "revue_attention",
                               "depuis": maintenant.isoformat(timespec="seconds")},
                 "revue_le": maintenant.isoformat(timespec="seconds")}
        conn.execute(
            "UPDATE objet_entreprise SET donnees = donnees || %s, maj_le = %s "
            "WHERE tenant_id = %s AND id = %s",
            (Jsonb(patch), maintenant, tenant, objet_id))
        compte["attentions"] += 1
        detail["action"] = "attention"
    else:
        revocable = (maintenant + timedelta(days=REVOCABLE_JOURS)).isoformat(timespec="seconds")
        patch = {"revue_niveau": AUTO_VISIBLE, "auto_accepte": True,
                 "revocable_jusqua": revocable,
                 "revue_le": maintenant.isoformat(timespec="seconds")}
        conn.execute(
            "UPDATE objet_entreprise SET mode = 'CONFIRMED', donnees = donnees || %s, "
            "maj_le = %s WHERE tenant_id = %s AND id = %s",
            (Jsonb(patch), maintenant, tenant, objet_id))
        statut_audit = _tracer(
            audit, "auto_accept_objet",
            {"objet_id": objet_id, "type": ligne.get("type"),
             "revocable_jusqua": revocable}, maintenant)
        if statut_audit.get("statut") != "ok":
            rapport["audit_erreurs"] += 1
        compte["auto_visibles"] += 1
        detail["action"] = "auto_accepte"
        detail["revocable_jusqua"] = revocable
    rapport["details"].append(detail)


def appliquer(conn: Any, tenant_id: Any, *, maintenant: Any = None,
              jours: Any = JOURS_RECENTS_DEFAUT) -> dict:
    """Route les claims et propositions ``PROPOSED`` récents du tenant.

    Chaque élément est routé dans sa propre transaction : un élément en échec
    est compté dans ``erreurs`` sans bloquer les autres. Renvoie les comptes
    par niveau — rien n'est silencieux, tout auto-accept est tracé.
    """
    tenant = _tenant(tenant_id)
    instant = _maintenant(maintenant)
    jours_ = max(1, min(int(jours or JOURS_RECENTS_DEFAUT), 3660))
    depuis = instant - timedelta(days=jours_)
    rapport: dict = {
        "tenant": tenant,
        "maintenant": instant.isoformat(timespec="seconds"),
        "fenetre_jours": jours_,
        "traites": 0,
        "auto_visibles": 0, "attentions": 0, "bloquants": 0, "sans_preuve": 0,
        "propositions": {"auto_visibles": 0, "attentions": 0, "bloquants": 0},
        "audit_erreurs": 0, "erreurs": [], "details": [],
    }
    _assurer_colonnes(conn)
    audit = audit_harness.AuditPostgres(conn, tenant, ACTEUR)
    marques = marques_critiques()
    for ligne in _claims_a_router(conn, tenant, depuis):
        try:
            with conn.transaction():
                _router_claim(conn, audit, tenant, ligne, marques, instant, rapport)
        except Exception as exc:  # noqa: BLE001 - le routage d'un claim n'en bloque pas un autre
            rapport["erreurs"].append({"claim_id": ligne.get("id"), "erreur": type(exc).__name__})
        rapport["traites"] += 1
    for ligne in _propositions_a_router(conn, tenant, depuis):
        try:
            with conn.transaction():
                _router_proposition(conn, audit, tenant, ligne, marques, instant, rapport)
        except Exception as exc:  # noqa: BLE001
            rapport["erreurs"].append({"objet_id": ligne.get("id"), "erreur": type(exc).__name__})
        rapport["traites"] += 1
    return rapport


# --- Révocation ---


def _revoquer_claim(conn: Any, audit: Any, tenant: str, claim_id: int,
                    acteur: str, raison: str, maintenant: datetime) -> dict:
    ligne = conn.execute(
        "SELECT tenant_id, statut, jumeau_id, predicat, objet, donnees FROM claim "
        "WHERE id = %s AND valide_jusqua IS NULL FOR UPDATE", (claim_id,)).fetchone()
    if ligne is None or ligne[0] != tenant:
        raise LookupError(f"claim {claim_id} : inconnu du tenant")
    donnees = dict(ligne[5] or {})
    fin = _dt(donnees.get("revocable_jusqua"))
    if (ligne[1] != "ACCEPTED" or donnees.get("revue_niveau") != AUTO_VISIBLE
            or donnees.get("revoque_le") or fin is None):
        raise RevocationRefusee(f"claim {claim_id} : pas un auto-accept révocable")
    if fin <= maintenant:
        raise RevocationRefusee(
            f"claim {claim_id} : fenêtre révocable close le {fin.isoformat(timespec='seconds')}")
    conn.execute(
        "INSERT INTO revue (tenant_id, claim_id, acteur, decision, motif, le) "
        "VALUES (%s, %s, %s, 'CONTESTED', %s, %s)",
        (tenant, claim_id, acteur, f"révocation de l'auto-accept : {raison}", maintenant))
    conn.execute(
        "UPDATE claim SET statut = 'CONTESTED', donnees = donnees || %s WHERE id = %s",
        (Jsonb({"revoque_le": maintenant.isoformat(timespec="seconds"),
                "revoque_par": acteur, "revoque_raison": raison}), claim_id))
    statut_audit = _tracer(
        audit, "revocation_claim",
        {"claim_id": claim_id, "jumeau_id": ligne[2], "acteur": acteur, "raison": raison},
        maintenant)
    return {"claim_id": claim_id, "statut": "CONTESTED", "revoque": True,
            "audit": statut_audit.get("statut")}


def _revoquer_objet(conn: Any, audit: Any, tenant: str, objet_id: str,
                    acteur: str, raison: str, maintenant: datetime) -> dict:
    ligne = conn.execute(
        "SELECT mode, donnees FROM objet_entreprise WHERE tenant_id = %s AND id = %s "
        "AND valide_jusqua IS NULL FOR UPDATE", (tenant, objet_id)).fetchone()
    if ligne is None:
        raise LookupError(f"objet {objet_id} : inconnu du tenant")
    donnees = dict(ligne[1] or {})
    fin = _dt(donnees.get("revocable_jusqua"))
    if (ligne[0] != "CONFIRMED" or donnees.get("revue_niveau") != AUTO_VISIBLE
            or donnees.get("revoque_le") or fin is None):
        raise RevocationRefusee(f"objet {objet_id} : pas un auto-accept révocable")
    if fin <= maintenant:
        raise RevocationRefusee(
            f"objet {objet_id} : fenêtre révocable close le {fin.isoformat(timespec='seconds')}")
    conn.execute(
        "UPDATE objet_entreprise SET mode = 'PROPOSED', donnees = donnees || %s, maj_le = %s "
        "WHERE tenant_id = %s AND id = %s",
        (Jsonb({"revoque_le": maintenant.isoformat(timespec="seconds"),
                "revoque_par": acteur, "revoque_raison": raison,
                "statut_revue": "CONTESTED"}), maintenant, tenant, objet_id))
    statut_audit = _tracer(
        audit, "revocation_objet",
        {"objet_id": objet_id, "acteur": acteur, "raison": raison}, maintenant)
    return {"objet_id": objet_id, "statut": "CONTESTED", "revoque": True,
            "audit": statut_audit.get("statut")}


def revoquer(conn: Any, tenant_id: Any, claim_id: Any, acteur: Any, raison: Any,
             *, maintenant: Any = None) -> dict:
    """Révoque un auto-accept encore dans sa fenêtre : claim → ``CONTESTED``.

    ``claim_id`` numérique vise la table ``claim`` ; un identifiant texte vise
    ``objet_entreprise`` (la proposition repasse ``PROPOSED``, journalisée
    ``CONTESTED``). Lève :exc:`LookupError` si l'élément est inconnu du tenant,
    :exc:`RevocationRefusee` si ce n'est pas un auto-accept ou si la fenêtre est
    close. La révocation est écrite dans ``revue`` (claims) et ``outil_audit``.
    """
    tenant = _tenant(tenant_id)
    instant = _maintenant(maintenant)
    auteur = _texte(acteur)
    if not auteur:
        raise RevueGradueeInvalide("acteur obligatoire")
    motif = _texte(raison)
    if not motif:
        raise RevueGradueeInvalide("raison obligatoire")
    _assurer_colonnes(conn)
    audit = audit_harness.AuditPostgres(conn, tenant, ACTEUR)
    with conn.transaction():
        try:
            identifiant = int(claim_id)
        except (TypeError, ValueError):
            return _revoquer_objet(conn, audit, tenant, str(claim_id).strip(),
                                   auteur, motif, instant)
        return _revoquer_claim(conn, audit, tenant, identifiant, auteur, motif, instant)


# --- Répartition des niveaux (lecture) ---


def _repartition_claims(conn: Any, tenant: str, maintenant: datetime) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            "SELECT coalesce(donnees->>'revue_niveau', '') AS niveau, statut, "
            "donnees->>'revocable_jusqua' AS revocable, "
            "(donnees ? 'revoque_le') AS revoque, count(*) AS n "
            "FROM claim WHERE tenant_id = %s AND valide_jusqua IS NULL "
            "GROUP BY 1, statut, revocable, revoque",
            (tenant,)).fetchall()
    rep = {"total": 0, AUTO_VISIBLE: 0, ATTENTION: 0, BLOQUANT: 0,
           "auto_acceptes": 0, "revocables": 0, "revoques": 0, "sans_niveau": 0}
    for ligne in lignes:
        n = int(ligne.get("n") or 0)
        rep["total"] += n
        niveau = str(ligne.get("niveau") or "")
        if niveau in rep:
            rep[niveau] += n
        else:
            rep["sans_niveau"] += n
        if niveau == AUTO_VISIBLE and ligne.get("statut") == "ACCEPTED":
            rep["auto_acceptes"] += n
        if ligne.get("revoque"):
            rep["revoques"] += n
        elif (ligne.get("statut") == "ACCEPTED" and niveau == AUTO_VISIBLE
                and (fin := _dt(ligne.get("revocable"))) is not None and fin > maintenant):
            rep["revocables"] += n
    return rep


def _repartition_objets(conn: Any, tenant: str, maintenant: datetime) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            "SELECT coalesce(donnees->>'revue_niveau', '') AS niveau, mode, "
            "donnees->>'revocable_jusqua' AS revocable, "
            "(donnees ? 'revoque_le') AS revoque, count(*) AS n "
            "FROM objet_entreprise WHERE tenant_id = %s AND valide_jusqua IS NULL "
            "AND donnees ? 'type_claim' GROUP BY 1, mode, revocable, revoque",
            (tenant,)).fetchall()
    rep = {"total": 0, AUTO_VISIBLE: 0, ATTENTION: 0, BLOQUANT: 0,
           "auto_acceptes": 0, "revocables": 0, "revoques": 0, "sans_niveau": 0}
    for ligne in lignes:
        n = int(ligne.get("n") or 0)
        rep["total"] += n
        niveau = str(ligne.get("niveau") or "")
        if niveau in rep:
            rep[niveau] += n
        else:
            rep["sans_niveau"] += n
        if niveau == AUTO_VISIBLE and ligne.get("mode") == "CONFIRMED":
            rep["auto_acceptes"] += n
        if ligne.get("revoque"):
            rep["revoques"] += n
        elif (ligne.get("mode") == "CONFIRMED" and niveau == AUTO_VISIBLE
                and (fin := _dt(ligne.get("revocable"))) is not None and fin > maintenant):
            rep["revocables"] += n
    return rep


def niveaux(conn: Any, tenant_id: Any, *, maintenant: Any = None) -> dict:
    """Répartition des niveaux de revue du tenant — comptes seuls, jamais de ratio.

    ``claims`` et ``propositions`` portent chacun : ``total``, les trois niveaux,
    ``auto_acceptes``, ``revocables`` (auto-acceptés encore dans leur fenêtre),
    ``revoques`` et ``sans_niveau`` (jamais routés — revue humaine classique).
    """
    tenant = _tenant(tenant_id)
    instant = _maintenant(maintenant)
    _assurer_colonnes(conn)
    return {
        "tenant": tenant,
        "maintenant": instant.isoformat(timespec="seconds"),
        "revocable_jours": REVOCABLE_JOURS,
        "claims": _repartition_claims(conn, tenant, instant),
        "propositions": _repartition_objets(conn, tenant, instant),
    }
