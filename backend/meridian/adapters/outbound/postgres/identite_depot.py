"""Décision humaine de promotion d'un twin provisoire en application.

La promotion ne crée pas une nouvelle application : elle donne un nom et une mission à l'identité existante, sans
changer son id ni son tenant. Chaque décision laisse une ligne dans `identity_decision` ; aucune ingestion ni aucun
modèle ne peut la déclencher à la place d'un humain.
"""
from __future__ import annotations

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from meridian.domain import identite

ACTION = "promotion"
_SENTINELLE = "Application existante"


class PromotionRefusee(ValueError):
    """Identité proposée invalide : la promotion est refusée avant toute écriture."""


class JumeauDejaCanonique(PromotionRefusee):
    """Le twin n'est plus provisoire : il n'y a plus de promotion à décider."""


def _texte(valeur, champ) -> str:
    if not isinstance(valeur, str) or not valeur.strip():
        raise PromotionRefusee(f"{champ} vide : promotion refusée")
    return valeur.strip()


def _provisoire_valeur(valeur) -> bool:
    """Un placeholder est refusé dans les deux champs, quel que soit celui où il apparaît."""
    comme_nom, _ = identite.est_provisoire({"nom": valeur, "mission": _SENTINELLE, "statut": "actif"})
    comme_mission, _ = identite.est_provisoire({"nom": _SENTINELLE, "mission": valeur, "statut": "actif"})
    return comme_nom or comme_mission


def promouvoir(conn, tenant_id, jumeau_id, nom, mission, acteur, preuve=None) -> dict:
    """Renomme et dote de mission l'application portée par un twin provisoire, puis audite la décision.

    Refuse un tenant, un jumeau ou un acteur vide, un jumeau introuvable ou d'un autre tenant, un twin déjà
    canonique, et tout nom ou mission vide ou provisoire (`Nouveau jumeau`, `dfggg`, `à confirmer`…). Seuls le nom
    et la mission du jumeau changent : sources et Claims restent intacts.
    """
    tenant = _texte(tenant_id, "tenant_id")
    jid = _texte(jumeau_id, "jumeau_id")
    acteur_propre = _texte(acteur, "acteur")
    nom_propre = _texte(nom, "nom")
    mission_propre = _texte(mission, "mission")
    if _provisoire_valeur(nom_propre):
        raise PromotionRefusee("nom provisoire ou placeholder : promotion refusée")
    if _provisoire_valeur(mission_propre):
        raise PromotionRefusee("mission provisoire ou placeholder : promotion refusée")

    with conn.transaction():
        with conn.cursor(row_factory=dict_row) as cur:
            existant = cur.execute(
                "SELECT id, tenant_id, nom, mission FROM jumeau WHERE id = %s FOR UPDATE", (jid,)).fetchone()
        if existant is None:
            raise LookupError(jid)
        if existant["tenant_id"] != tenant:
            raise PermissionError(f"jumeau {jid} appartient à un autre tenant")
        provisoire, _ = identite.est_provisoire(existant)
        if not provisoire:
            raise JumeauDejaCanonique(f"jumeau {jid} déjà canonique : promotion sans objet")

        avant = {"nom": existant["nom"], "mission": existant["mission"]}
        apres = {"nom": nom_propre, "mission": mission_propre}
        conn.execute(
            "UPDATE jumeau SET nom = %s, mission = %s WHERE id = %s AND tenant_id = %s",
            (nom_propre, mission_propre, jid, tenant))
        conn.execute(
            "INSERT INTO identity_decision (tenant_id, jumeau_id, acteur, action, avant, apres, preuve) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (tenant, jid, acteur_propre, ACTION, Jsonb(avant), Jsonb(apres),
             Jsonb(preuve) if preuve is not None else None))

    return {
        "jumeau_id": jid,
        "nom": nom_propre,
        "mission": mission_propre,
        "statut": "actif",
        "avant": avant,
        "apres": apres,
    }
