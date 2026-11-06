"""Partage de connaissance côté Postgres : `claim_share` et projection autorisée.

Le Claim reste privé par défaut. `accorder` est le seul acte qui ouvre une lecture ; `autoriser`
est la seule fonction qui décide de la projection. Aucun appelant ne doit réimplémenter la règle.
"""
from __future__ import annotations

from psycopg.rows import dict_row

from meridian.domain import partage as domaine

__all__ = [
    "accorder",
    "autoriser_claim",
    "claims_visibles",
    "decider_revue",
    "lister_a_reviser",
    "partages_du_claim",
    "projeter_claim",
    "revoquer",
]


def _claim(conn, tenant_id: str, claim_id: int):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """SELECT id, tenant_id, jumeau_id, sujet, predicat, objet, type, statut, maturite,
                      confiance::float AS confiance, confidentialite, valide_depuis, valide_jusqua
               FROM claim WHERE tenant_id = %s AND id = %s""",
            (tenant_id, claim_id),
        ).fetchone()


def _preuves(conn, claim_id: int):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """SELECT p.id, p.locator, p.chemin, p.sha, p.ligne_debut, p.ligne_fin, p.hash,
                      p.confidentialite
               FROM claim_preuve cp JOIN preuve p ON p.id = cp.preuve_id
               WHERE cp.claim_id = %s ORDER BY p.id""",
            (claim_id,),
        ).fetchall()


def _partages(conn, tenant_id: str, claim_id: int):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """SELECT id, claim_id, scope_type, scope_id, projection, granted_by, reviewed_by,
                      valid_from, valid_to, revoked_at, revoked_by, reason
               FROM claim_share WHERE tenant_id = %s AND claim_id = %s ORDER BY id""",
            (tenant_id, claim_id),
        ).fetchall()


def accorder(
    conn,
    tenant_id: str,
    claim_id: int,
    scope_type: str,
    scope_id: str,
    projection: str = "SUMMARY",
    *,
    granted_by: str,
    reviewed_by: str | None = None,
    valid_from=None,
    valid_to=None,
    reason: str | None = None,
):
    """Ouvre une lecture d'un Claim à un scope. Refuse tout ce qui élargit la confidentialité."""
    type_ = str(scope_type or "").strip().upper()
    niveau = str(projection or "").strip().upper()
    scope = str(scope_id or "").strip()
    acteur = str(granted_by or "").strip()
    if type_ not in domaine.SCOPES:
        raise domaine.PartageInvalide(
            f"scope_type inconnu : {scope_type!r} (attendus : {', '.join(domaine.SCOPES)})"
        )
    if type_ == "EXTERNAL" and not domaine.external_autorise():
        raise domaine.PartageInvalide(
            "publication EXTERNAL désactivée (JUMEAU_EXTERNAL_PUBLICATION)"
        )
    if niveau not in domaine.PROJECTIONS:
        raise domaine.PartageInvalide(
            f"projection inconnue : {projection!r} (attendues : {', '.join(domaine.PROJECTIONS)})"
        )
    if not scope:
        raise domaine.PartageInvalide("scope_id obligatoire")
    if not acteur:
        raise domaine.PartageInvalide("granted_by obligatoire")
    if type_ == "TENANT" and scope != tenant_id:
        raise domaine.PartageInvalide("un partage TENANT ne peut viser que son propre tenant")
    claim = _claim(conn, tenant_id, claim_id)
    if claim is None:
        raise domaine.PartageInvalide(f"claim inconnu : {claim_id}")
    preuves = _preuves(conn, claim_id)
    effective = domaine.confidentialite_effective(claim, preuves)
    if effective == "SECRET":
        raise domaine.PartageInvalide("un Claim SECRET ne peut jamais être partagé")
    if effective == "CONFIDENTIAL":
        if niveau != "SUMMARY":
            raise domaine.PartageInvalide("un Claim CONFIDENTIAL ne peut être partagé qu'en SUMMARY")
        if not str(reviewed_by or "").strip():
            raise domaine.PartageInvalide("un partage CONFIDENTIAL exige une revue")
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """INSERT INTO claim_share
                 (tenant_id, claim_id, scope_type, scope_id, projection, granted_by, reviewed_by,
                  valid_from, valid_to, reason)
               VALUES (%s, %s, %s, %s, %s, %s, %s, coalesce(%s, now()), %s, %s)
               RETURNING id, claim_id, scope_type, scope_id, projection, granted_by, reviewed_by,
                         valid_from, valid_to, revoked_at, revoked_by, reason, created_at""",
            (tenant_id, claim_id, type_, scope, niveau, acteur, reviewed_by, valid_from, valid_to, reason),
        ).fetchone()


def revoquer(conn, tenant_id: str, share_id: int, revoked_by: str, reason: str | None = None) -> bool:
    """Révoque un partage ; l'historique de la ligne reste lisible."""
    acteur = str(revoked_by or "").strip()
    if not acteur:
        raise domaine.PartageInvalide("revoked_by obligatoire")
    with conn.cursor() as cur:
        resultat = cur.execute(
            """UPDATE claim_share SET revoked_at = now(), revoked_by = %s, reason = coalesce(%s, reason)
               WHERE id = %s AND tenant_id = %s AND revoked_at IS NULL""",
            (acteur, reason, share_id, tenant_id),
        )
        return resultat.rowcount > 0


def partages_du_claim(conn, tenant_id: str, claim_id: int):
    return _partages(conn, tenant_id, claim_id)


def autoriser_claim(
    conn, tenant_id: str, claim_id: int, consommateur: domaine.Consommateur, *,
    reference=None,
) -> str | None:
    claim = _claim(conn, tenant_id, claim_id)
    if claim is None:
        return None
    return domaine.autoriser(
        claim, _preuves(conn, claim_id), _partages(conn, tenant_id, claim_id), consommateur,
        reference=reference,
    )


def projeter_claim(
    conn, tenant_id: str, claim_id: int, consommateur: domaine.Consommateur, *,
    reference=None,
):
    claim = _claim(conn, tenant_id, claim_id)
    if claim is None:
        return None
    preuves = _preuves(conn, claim_id)
    niveau = domaine.autoriser(
        claim, preuves, _partages(conn, tenant_id, claim_id), consommateur, reference=reference,
    )
    return domaine.projeter(claim, preuves, niveau)


PREDICATS_CARTE = ("REALISE_CAPACITE", "EXPOSE", "ECHANGE_AVEC")


def _share_actif(conn, tenant_id: str, claim_id: int, scope_type: str, scope_id: str) -> bool:
    with conn.cursor() as cur:
        return cur.execute(
            "SELECT id FROM claim_share WHERE tenant_id = %s AND claim_id = %s AND scope_type = %s "
            "AND scope_id = %s AND revoked_at IS NULL AND (valid_to IS NULL OR valid_to > now()) LIMIT 1",
            (tenant_id, claim_id, scope_type, scope_id),
        ).fetchone() is not None


def _est_confidentiel(conn, tenant_id: str, claim_id: int) -> bool:
    claim = _claim(conn, tenant_id, claim_id)
    if claim is None:
        return False
    return domaine.confidentialite_effective(claim, _preuves(conn, claim_id)) == "CONFIDENTIAL"


def publier_carte(
    conn,
    tenant_id: str,
    jumeau_id: str,
    *,
    granted_by: str,
    scope_type: str = "TENANT",
    scope_id: str | None = None,
    reviewed_by: str | None = None,
):
    """Publie les Claims de la carte en SUMMARY ; les preuves restent dans le Twin.

    Les Claims `SECRET` sont ignorés ; les `CONFIDENTIAL` ne passent qu'avec `reviewed_by`.
    Une publication déjà active n'est pas dupliquée.
    """
    type_ = str(scope_type or "").strip().upper()
    if type_ not in domaine.SCOPES:
        raise domaine.PartageInvalide(
            f"scope_type inconnu : {scope_type!r} (attendus : {', '.join(domaine.SCOPES)})"
        )
    if type_ == "EXTERNAL" and not domaine.external_autorise():
        raise domaine.PartageInvalide(
            "publication EXTERNAL désactivée (JUMEAU_EXTERNAL_PUBLICATION)"
        )
    scope = str(scope_id or (tenant_id if type_ == "TENANT" else "")).strip()
    if not scope:
        raise domaine.PartageInvalide("scope_id obligatoire")
    acteur = str(granted_by or "").strip()
    if not acteur:
        raise domaine.PartageInvalide("granted_by obligatoire")
    if reviewed_by and str(reviewed_by).strip() == acteur:
        raise domaine.PartageInvalide("reviewed_by doit être distinct de granted_by")
    with conn.cursor(row_factory=dict_row) as cur:
        claims = cur.execute(
            "SELECT id FROM claim WHERE tenant_id = %s AND jumeau_id = %s AND predicat = ANY(%s) "
            "AND valide_jusqua IS NULL AND statut <> 'CONTESTED' ORDER BY id",
            (tenant_id, jumeau_id, list(PREDICATS_CARTE)),
        ).fetchall()
    publies = deja = 0
    ignores = []
    for claim in claims:
        if _share_actif(conn, tenant_id, claim["id"], type_, scope):
            deja += 1
            continue
        try:
            partage_cree = accorder(
                conn, tenant_id, claim["id"], type_, scope, "SUMMARY",
                granted_by=acteur, reviewed_by=reviewed_by, reason="carte de catalogue",
            )
        except domaine.PartageInvalide as erreur:
            ignores.append({"claim_id": claim["id"], "raison": str(erreur)})
            continue
        publies += 1
        if str(reviewed_by or "").strip() and _est_confidentiel(conn, tenant_id, claim["id"]):
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO publication_review
                         (tenant_id, share_id, reviewer, decision, reason)
                       VALUES (%s, %s, %s, 'APPROVED', %s)""",
                    (tenant_id, partage_cree["id"], str(reviewed_by).strip(),
                     "publication CONFIDENTIAL de la carte"),
                )
    return {"publies": publies, "deja": deja, "ignores": ignores}


def depublier_carte(
    conn,
    tenant_id: str,
    jumeau_id: str,
    *,
    revoked_by: str,
    scope_type: str = "TENANT",
    scope_id: str | None = None,
):
    """Retire les partages de carte ; les partages EVIDENCE accordés autrement restent."""
    type_ = str(scope_type or "").strip().upper()
    if type_ not in domaine.SCOPES:
        raise domaine.PartageInvalide(
            f"scope_type inconnu : {scope_type!r} (attendus : {', '.join(domaine.SCOPES)})"
        )
    scope = str(scope_id or (tenant_id if type_ == "TENANT" else "")).strip()
    if not scope:
        raise domaine.PartageInvalide("scope_id obligatoire")
    acteur = str(revoked_by or "").strip()
    if not acteur:
        raise domaine.PartageInvalide("revoked_by obligatoire")
    with conn.cursor() as cur:
        ids = [ligne[0] for ligne in cur.execute(
            "SELECT s.id FROM claim_share s JOIN claim c ON c.id = s.claim_id "
            "WHERE s.tenant_id = %s AND s.scope_type = %s AND s.scope_id = %s AND s.revoked_at IS NULL "
            "AND s.reason = 'carte de catalogue' "
            "AND c.tenant_id = %s AND c.jumeau_id = %s AND c.predicat = ANY(%s)",
            (tenant_id, type_, scope, tenant_id, jumeau_id, list(PREDICATS_CARTE)),
        ).fetchall()]
    for share_id in ids:
        revoquer(conn, tenant_id, share_id, acteur, "dépublication de la carte")
    return {"revoques": len(ids)}


def claims_visibles(
    conn,
    tenant_id: str,
    consommateur: domaine.Consommateur,
    *,
    jumeau_id: str | None = None,
    predicat: str | None = None,
    recherche: str | None = None,
    limite: int = 80,
):
    """Claims lisibles par ce consommateur, déjà projetés.

    L'owner voit ses propres Claims ; les autres passent par un partage actif. Le filtre SQL
    est volontairement doublé par `autoriser` : la règle de projection reste unique.
    """
    borne = max(1, min(int(limite), 500))
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            """SELECT c.id, c.tenant_id, c.jumeau_id, c.sujet, c.predicat, c.objet, c.type,
                      c.statut, c.maturite, c.confiance::float AS confiance, c.confidentialite,
                      c.valide_depuis, c.valide_jusqua
               FROM claim c
               WHERE c.tenant_id = %s AND c.valide_jusqua IS NULL
                 AND (%s::text IS NULL OR c.jumeau_id = %s)
                 AND (%s::text IS NULL OR c.predicat = %s)
                 AND (%s::text IS NULL OR c.objet ILIKE '%%' || %s || '%%')
                 AND (
                   c.jumeau_id = %s
                   OR EXISTS (
                     SELECT 1 FROM claim_share s
                     WHERE s.tenant_id = c.tenant_id AND s.claim_id = c.id
                       AND s.revoked_at IS NULL
                       AND (s.valid_to IS NULL OR s.valid_to > now())
                       AND (
                         (s.scope_type = 'TENANT' AND s.scope_id = %s)
                         OR (s.scope_type = 'TEAM' AND s.scope_id = %s)
                         OR (s.scope_type = 'TWIN' AND s.scope_id = %s)
                         OR (s.scope_type = 'PORTFOLIO' AND s.scope_id = %s)
                         OR (s.scope_type = 'EXTERNAL' AND s.scope_id = %s)
                       )
                   )
                 )
               ORDER BY c.predicat, c.objet LIMIT %s""",
            (tenant_id, jumeau_id, jumeau_id, predicat, predicat, recherche, recherche,
             consommateur.twin_id, consommateur.tenant_id,
             consommateur.team_id, consommateur.twin_id, consommateur.portfolio_id,
             consommateur.external_id, borne),
        ).fetchall()
    resultat = []
    for claim in lignes:
        preuves = _preuves(conn, claim["id"])
        niveau = domaine.autoriser(
            claim, preuves, _partages(conn, tenant_id, claim["id"]), consommateur,
        )
        vue = domaine.projeter(claim, preuves, niveau)
        if vue is not None:
            resultat.append(vue)
    return resultat


def lister_a_reviser(conn, tenant_id: str, jumeau_id: str | None = None):
    """Partages de carte actifs en attente de revue, dont la confidentialité effective est CONFIDENTIAL.

    La confidentialité effective est celle du domaine : le maximum entre le Claim et ses preuves.
    Les partages INTERNAL, déjà revus, révoqués ou expirés ne sont pas proposés.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            """SELECT s.id, s.claim_id, c.objet, c.confidentialite, s.scope_type, s.scope_id,
                      s.granted_by
               FROM claim_share s JOIN claim c ON c.id = s.claim_id
               WHERE s.tenant_id = %s AND c.tenant_id = %s
                 AND s.reason = 'carte de catalogue'
                 AND s.revoked_at IS NULL
                 AND s.valid_from <= now()
                 AND (s.valid_to IS NULL OR s.valid_to > now())
                 AND coalesce(btrim(s.reviewed_by), '') = ''
                 AND (%s::text IS NULL OR c.jumeau_id = %s)
               ORDER BY s.id""",
            (tenant_id, tenant_id, jumeau_id, jumeau_id),
        ).fetchall()
    a_reviser = []
    for ligne in lignes:
        confidentialite = domaine.confidentialite_effective(
            ligne, _preuves(conn, ligne["claim_id"])
        )
        if confidentialite != "CONFIDENTIAL":
            continue
        a_reviser.append({
            "id": ligne["id"],
            "claim_id": ligne["claim_id"],
            "objet": ligne["objet"],
            "confidentialite": confidentialite,
            "scope_type": ligne["scope_type"],
            "scope_id": ligne["scope_id"],
            "granted_by": ligne["granted_by"],
        })
    return a_reviser


def decider_revue(
    conn,
    tenant_id: str,
    share_id: int,
    *,
    reviewer: str,
    decision: str,
    reason: str | None = None,
):
    """Décide d'une publication en attente : APPROVED rend le partage lisible, REJECTED le révoque.

    Une revue à quatre yeux interdit au demandeur d'approuver ou de rejeter son propre partage.
    La décision est toujours tracée dans `publication_review`, même quand elle révoque le partage.
    """
    acteur = str(reviewer or "").strip()
    if not acteur:
        raise domaine.PartageInvalide("reviewer obligatoire")
    decision_ = str(decision or "").strip().upper()
    if decision_ not in ("APPROVED", "REJECTED"):
        raise domaine.PartageInvalide(
            f"décision inconnue : {decision!r} (attendues : APPROVED, REJECTED)"
        )
    with conn.cursor(row_factory=dict_row) as cur:
        partage = cur.execute(
            """SELECT id, claim_id, granted_by, reviewed_by, revoked_at
               FROM claim_share WHERE tenant_id = %s AND id = %s""",
            (tenant_id, share_id),
        ).fetchone()
        if partage is None:
            raise domaine.PartageInvalide(f"partage inconnu : {share_id}")
        if acteur == str(partage["granted_by"] or "").strip():
            raise domaine.PartageInvalide("revue à quatre yeux : reviewer distinct de granted_by")
        if partage["revoked_at"] is not None:
            raise domaine.PartageInvalide(f"partage révoqué : {share_id}")
        if str(partage["reviewed_by"] or "").strip():
            raise domaine.PartageInvalide(f"partage déjà revu : {share_id}")
        revue = cur.execute(
            """INSERT INTO publication_review
                 (tenant_id, share_id, reviewer, decision, reason)
               VALUES (%s, %s, %s, %s, %s)
               RETURNING id, reviewed_at""",
            (tenant_id, share_id, acteur, decision_, reason),
        ).fetchone()
        if decision_ == "APPROVED":
            cur.execute(
                "UPDATE claim_share SET reviewed_by = %s WHERE id = %s AND tenant_id = %s",
                (acteur, share_id, tenant_id),
            )
        else:
            cur.execute(
                """UPDATE claim_share SET revoked_at = now(), revoked_by = %s,
                          reason = coalesce(%s, 'revue rejetée')
                   WHERE id = %s AND tenant_id = %s""",
                (acteur, reason, share_id, tenant_id),
            )
    return {
        "review_id": revue["id"],
        "share_id": partage["id"],
        "claim_id": partage["claim_id"],
        "decision": decision_,
        "reviewer": acteur,
        "granted_by": partage["granted_by"],
        "reason": reason,
        "revoked": decision_ == "REJECTED",
        "reviewed_at": revue["reviewed_at"],
    }
