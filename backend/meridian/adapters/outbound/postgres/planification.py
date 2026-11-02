"""Persistance Postgres du pilotage capacité/charge/prévision/budget.

Le module reste dans l'adapter Postgres : le domaine ne connaît ni SQL ni fournisseur. Toutes les
écritures sont tenant-scopées et idempotentes par clé canonique.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timezone
from typing import Any, Iterable

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from meridian.domain import planification as domaine


def maintenant() -> str:
    return datetime.now(timezone.utc).isoformat()


def _date(valeur):
    if isinstance(valeur, (date, datetime)):
        return valeur
    if valeur in (None, ""):
        return None
    return date.fromisoformat(str(valeur)[:10])


def _ligne(ligne) -> dict:
    return {cle: valeur for cle, valeur in ligne.items()}


def appliquer_schema(conn) -> None:
    from meridian.adapters.outbound.postgres import depot
    depot.appliquer_schema(conn)


def lister_sources(conn, tenant: str) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return [_ligne(l) for l in cur.execute(
            "SELECT tenant_id, id, provider, usage, prioritaire, nom, perimetre, secret_ref, configuration, curseur, "
            "capacites, etat, derniere_erreur, cree_le, maj_le FROM planification_source "
            "WHERE tenant_id = %s ORDER BY nom, id", (tenant,)).fetchall()]


def lire_source(conn, tenant: str, source_id: str) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        ligne = cur.execute(
            "SELECT * FROM planification_source WHERE tenant_id = %s AND id = %s",
            (tenant, source_id)).fetchone()
    return _ligne(ligne) if ligne else None


def creer_source(conn, tenant: str, source: dict) -> dict:
    identifiant = str(source.get("id") or uuid.uuid4().hex)
    conn.execute(
        "INSERT INTO planification_source "
        "(tenant_id, id, provider, usage, prioritaire, nom, perimetre, secret_ref, configuration, curseur, capacites, etat) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (tenant_id, id) DO UPDATE SET provider = EXCLUDED.provider, usage = EXCLUDED.usage, "
        "prioritaire = EXCLUDED.prioritaire, nom = EXCLUDED.nom, "
        "perimetre = EXCLUDED.perimetre, secret_ref = EXCLUDED.secret_ref, "
        "configuration = EXCLUDED.configuration, capacites = EXCLUDED.capacites, "
        "etat = EXCLUDED.etat, maj_le = now()",
        (tenant, identifiant, source.get("provider") or "csv", source.get("usage") or "travail",
         bool(source.get("prioritaire")), source.get("nom") or identifiant, source.get("perimetre"),
         source.get("secret_ref"),
         Jsonb(source.get("configuration") or {}), source.get("curseur"),
         Jsonb(source.get("capacites") or {}), source.get("etat") or "active"))
    return lire_source(conn, tenant, identifiant) or {}


def maj_source(conn, tenant: str, source_id: str, **champs) -> None:
    if not champs:
        return
    autorises = {"curseur", "capacites", "etat", "derniere_erreur", "configuration",
                 "verrou_proprietaire", "verrou_jusqu_a"}
    valeurs = {cle: valeur for cle, valeur in champs.items() if cle in autorises}
    if not valeurs:
        return
    colonnes = ", ".join(f"{cle} = %s" for cle in valeurs)
    params = [Jsonb(v) if cle in {"capacites", "configuration"} and v is not None else v
              for cle, v in valeurs.items()]
    conn.execute(f"UPDATE planification_source SET {colonnes}, maj_le = now() "
                 "WHERE tenant_id = %s AND id = %s", (*params, tenant, source_id))


def enregistrer_equipe(conn, tenant: str, equipe: dict) -> str:
    identifiant = str(equipe.get("id") or equipe.get("externe_id") or uuid.uuid4().hex)
    conn.execute(
        "INSERT INTO planification_equipe (tenant_id, id, nom, domaine, parent_id, source_id, externe_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (tenant_id, id) DO UPDATE SET "
        "nom = EXCLUDED.nom, domaine = coalesce(EXCLUDED.domaine, planification_equipe.domaine), "
        "parent_id = coalesce(EXCLUDED.parent_id, planification_equipe.parent_id), "
        "source_id = coalesce(EXCLUDED.source_id, planification_equipe.source_id), "
        "externe_id = coalesce(EXCLUDED.externe_id, planification_equipe.externe_id), maj_le = now()",
        (tenant, identifiant, equipe.get("nom") or identifiant, equipe.get("domaine"),
         equipe.get("parent_id"), equipe.get("source_id"), equipe.get("externe_id")))
    return identifiant


def equipes(conn, tenant: str) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return [_ligne(l) for l in cur.execute(
            "SELECT id, nom, domaine, parent_id, source_id, externe_id, cree_le, maj_le "
            "FROM planification_equipe WHERE tenant_id = %s ORDER BY nom, id", (tenant,)).fetchall()]


def enregistrer_element(conn, tenant: str, element: dict) -> str:
    external = str(element.get("external_id") or element.get("id"))
    source_id = str(element.get("source_id") or "source")
    identifiant = str(element.get("id") or f"{source_id}:{external}")
    estimation = element.get("estimation") or {}
    if isinstance(estimation, domaine.Estimation):
        estimation = {"valeur": estimation.valeur, "unite": estimation.unite,
                      "methode": estimation.methode}
    valeur = estimation.get("valeur")
    unite = estimation.get("unite")
    methode = estimation.get("methode")
    conn.execute(
        "INSERT INTO planification_element "
        "(tenant_id, id, source_id, external_id, equipe_id, parent_id, cycle_id, release_id, type, titre, "
        "statut, priorite, categorie_charge, estimation_valeur, estimation_unite, estimation_methode, "
        "assigne, url, actif, observe_le, maj_source, donnees) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (tenant_id, source_id, external_id) DO UPDATE SET "
        "equipe_id = coalesce(EXCLUDED.equipe_id, planification_element.equipe_id), "
        "parent_id = coalesce(EXCLUDED.parent_id, planification_element.parent_id), "
        "cycle_id = coalesce(EXCLUDED.cycle_id, planification_element.cycle_id), "
        "release_id = coalesce(EXCLUDED.release_id, planification_element.release_id), "
        "type = EXCLUDED.type, titre = EXCLUDED.titre, statut = EXCLUDED.statut, "
        "priorite = EXCLUDED.priorite, categorie_charge = EXCLUDED.categorie_charge, "
        "estimation_valeur = EXCLUDED.estimation_valeur, estimation_unite = EXCLUDED.estimation_unite, "
        "estimation_methode = EXCLUDED.estimation_methode, assigne = EXCLUDED.assigne, "
        "url = EXCLUDED.url, actif = EXCLUDED.actif, observe_le = now(), "
        "maj_source = EXCLUDED.maj_source, donnees = EXCLUDED.donnees, maj_le = now()",
        (tenant, identifiant, source_id, external, element.get("equipe_id"),
         element.get("parent_id"), element.get("cycle_id"), element.get("release_id"),
         element.get("type") or "item", element.get("titre") or external,
         domaine.normaliser_statut(element.get("statut")),
         str(element.get("priorite") or "inconnue").lower(),
         domaine.normaliser_categorie(element.get("categorie_charge")),
         valeur, unite, methode, element.get("assigne"), element.get("url"),
         bool(element.get("actif", True)), element.get("observe_le") or maintenant(),
         element.get("maj_source"), Jsonb(element.get("donnees") or {})))
    return identifiant


def desactiver_absents(conn, tenant: str, source_id: str, externes: list[str]) -> int:
    with conn.cursor() as cur:
        if externes:
            cur.execute(
                "UPDATE planification_element SET actif = false, maj_le = now() "
                "WHERE tenant_id = %s AND source_id = %s AND actif = true "
                "AND NOT (external_id = ANY(%s))", (tenant, source_id, externes))
        else:
            cur.execute(
                "UPDATE planification_element SET actif = false, maj_le = now() "
                "WHERE tenant_id = %s AND source_id = %s AND actif = true",
                (tenant, source_id))
        return cur.rowcount


def enregistrer_cycle(conn, tenant: str, cycle: dict) -> str:
    identifiant = str(cycle.get("id") or uuid.uuid4().hex)
    conn.execute(
        "INSERT INTO planification_cycle "
        "(tenant_id, id, equipe_id, nom, debut, fin, termine, capacite, unite, source_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (tenant_id, id) DO UPDATE SET "
        "equipe_id = EXCLUDED.equipe_id, nom = EXCLUDED.nom, debut = EXCLUDED.debut, fin = EXCLUDED.fin, "
        "termine = EXCLUDED.termine, capacite = EXCLUDED.capacite, unite = EXCLUDED.unite, maj_le = now()",
        (tenant, identifiant, cycle.get("equipe_id"), cycle.get("nom") or identifiant,
         _date(cycle.get("debut")), _date(cycle.get("fin")), bool(cycle.get("termine")),
         cycle.get("capacite"), cycle.get("unite"), cycle.get("source_id")))
    return identifiant


def enregistrer_release(conn, tenant: str, release: dict) -> str:
    identifiant = str(release.get("id") or uuid.uuid4().hex)
    conn.execute(
        "INSERT INTO planification_release (tenant_id, id, nom, date_cible, statut, source_id) "
        "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (tenant_id, id) DO UPDATE SET "
        "nom = EXCLUDED.nom, date_cible = EXCLUDED.date_cible, statut = EXCLUDED.statut, maj_le = now()",
        (tenant, identifiant, release.get("nom") or identifiant, _date(release.get("date_cible")),
         release.get("statut"), release.get("source_id")))
    return identifiant


def enregistrer_dependance(conn, tenant: str, dependance: dict) -> str:
    cle = f"{dependance.get('source_element_id')}:{dependance.get('cible_element_id')}:{dependance.get('type', 'lie')}"
    identifiant = str(dependance.get("id") or hashlib.sha256(cle.encode()).hexdigest()[:24])
    conn.execute(
        "INSERT INTO planification_dependance "
        "(tenant_id, id, source_element_id, cible_element_id, type, source_id) "
        "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (tenant_id, id) DO UPDATE SET "
        "type = EXCLUDED.type, maj_le = now()",
        (tenant, identifiant, dependance.get("source_element_id"), dependance.get("cible_element_id"),
         dependance.get("type") or "lie", dependance.get("source_id")))
    return identifiant


def enregistrer_capacite(conn, tenant: str, capacite: dict) -> str:
    identifiant = str(capacite.get("id") or uuid.uuid4().hex)
    conn.execute(
        "INSERT INTO planification_capacite "
        "(tenant_id, id, equipe_id, debut, fin, unite, valeur, confiance, source, fraicheur) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (tenant_id, id) DO UPDATE SET "
        "equipe_id = EXCLUDED.equipe_id, debut = EXCLUDED.debut, fin = EXCLUDED.fin, "
        "unite = EXCLUDED.unite, valeur = EXCLUDED.valeur, confiance = EXCLUDED.confiance, "
        "source = EXCLUDED.source, fraicheur = EXCLUDED.fraicheur, maj_le = now()",
        (tenant, identifiant, capacite.get("equipe_id"), _date(capacite.get("debut")),
         _date(capacite.get("fin")), capacite.get("unite"), capacite.get("valeur"),
         float(capacite.get("confiance") or 0.5), capacite.get("source"),
         capacite.get("fraicheur")))
    return identifiant


def elements(conn, tenant: str, *, equipe_id: str | None = None,
             debut: date | None = None, fin: date | None = None, actifs: bool = True) -> list[dict]:
    conditions = ["e.tenant_id = %s"]
    params: list[Any] = [tenant]
    if equipe_id:
        conditions.append("e.equipe_id = %s")
        params.append(equipe_id)
    if actifs:
        conditions.append("e.actif = true")
    if debut:
        conditions.append("coalesce(e.maj_source, e.observe_le)::date >= %s")
        params.append(debut)
    if fin:
        conditions.append("coalesce(e.maj_source, e.observe_le)::date <= %s")
        params.append(fin)
    with conn.cursor(row_factory=dict_row) as cur:
        return [_ligne(l) for l in cur.execute(
            "SELECT DISTINCT ON (e.equipe_id, e.external_id) e.* "
            "FROM planification_element e "
            "LEFT JOIN planification_source s ON s.tenant_id = e.tenant_id AND s.id = e.source_id "
            f"WHERE {' AND '.join(conditions)} "
            "ORDER BY e.equipe_id, e.external_id, s.prioritaire DESC NULLS LAST, e.source_id, e.id",
            params).fetchall()]


def elements_historique(conn, tenant: str, equipe_id: str | None = None) -> list[dict]:
    conditions = ["e.tenant_id = %s", "e.cycle_id IS NOT NULL"]
    params: list[Any] = [tenant]
    if equipe_id:
        conditions.append("e.equipe_id = %s")
        params.append(equipe_id)
    with conn.cursor(row_factory=dict_row) as cur:
        return [_ligne(l) for l in cur.execute(
            "SELECT DISTINCT ON (e.equipe_id, e.external_id, e.cycle_id) e.* "
            "FROM planification_element e "
            "LEFT JOIN planification_source s ON s.tenant_id = e.tenant_id AND s.id = e.source_id "
            f"WHERE {' AND '.join(conditions)} "
            "ORDER BY e.equipe_id, e.external_id, e.cycle_id, s.prioritaire DESC NULLS LAST, e.id",
            params).fetchall()]


def capacites(conn, tenant: str, equipe_id: str | None = None,
              debut: date | None = None, fin: date | None = None) -> list[dict]:
    conditions = ["tenant_id = %s"]
    params: list[Any] = [tenant]
    if equipe_id:
        conditions.append("equipe_id = %s")
        params.append(equipe_id)
    if debut:
        conditions.append("fin >= %s")
        params.append(debut)
    if fin:
        conditions.append("debut <= %s")
        params.append(fin)
    with conn.cursor(row_factory=dict_row) as cur:
        return [_ligne(l) for l in cur.execute(
            f"SELECT * FROM planification_capacite WHERE {' AND '.join(conditions)} "
            "ORDER BY equipe_id, debut", params).fetchall()]


def roles(conn, tenant: str, acteur: str | None = None) -> list[dict]:
    if acteur:
        with conn.cursor(row_factory=dict_row) as cur:
            return [_ligne(l) for l in cur.execute(
                "SELECT * FROM planification_role WHERE tenant_id = %s AND acteur = %s "
                "AND (fin IS NULL OR fin >= current_date) ORDER BY role, perimetre_type", (tenant, acteur)).fetchall()]
    with conn.cursor(row_factory=dict_row) as cur:
        return [_ligne(l) for l in cur.execute(
            "SELECT * FROM planification_role WHERE tenant_id = %s "
            "AND (fin IS NULL OR fin >= current_date) ORDER BY acteur, role", (tenant,)).fetchall()]


def affecter_role(conn, tenant: str, affectation: dict) -> str:
    identifiant = str(affectation.get("id") or uuid.uuid4().hex)
    conn.execute(
        "INSERT INTO planification_role "
        "(tenant_id, id, acteur, role, perimetre_type, perimetre_id, debut, fin, source) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (tenant_id, id) DO UPDATE SET "
        "acteur = EXCLUDED.acteur, role = EXCLUDED.role, perimetre_type = EXCLUDED.perimetre_type, "
        "perimetre_id = EXCLUDED.perimetre_id, debut = EXCLUDED.debut, fin = EXCLUDED.fin, "
        "source = EXCLUDED.source, maj_le = now()",
        (tenant, identifiant, affectation.get("acteur"), domaine.normaliser_role(affectation.get("role")),
         affectation.get("perimetre_type") or "tenant", affectation.get("perimetre_id"),
         _date(affectation.get("debut")), _date(affectation.get("fin")), affectation.get("source")))
    return identifiant


def enregistrer_prevision(conn, tenant: str, prevision: dict) -> str:
    identifiant = str(prevision.get("id") or uuid.uuid4().hex)
    conn.execute(
        "INSERT INTO planification_prevision "
        "(tenant_id, id, perimetre_type, perimetre_id, equipe_id, horizon, methode, version, "
        "entree_hash, seed, p50, p85, p95, confiance, hypotheses, exclusions, resultat) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (tenant, identifiant, prevision.get("perimetre_type") or "equipe",
         prevision.get("perimetre_id"), prevision.get("equipe_id"), prevision.get("horizon"),
         prevision.get("methode"), prevision.get("version") or "1.0.0",
         prevision.get("entree_hash"), prevision.get("seed"), prevision.get("p50"),
         prevision.get("p85"), prevision.get("p95"), float(prevision.get("confiance") or 0),
         Jsonb(prevision.get("hypotheses") or []), Jsonb(prevision.get("exclusions") or []),
         Jsonb(prevision.get("resultat") or {})))
    return identifiant


def budgets(conn, tenant: str, initiative_id: str | None = None) -> list[dict]:
    if initiative_id:
        with conn.cursor(row_factory=dict_row) as cur:
            return [_ligne(l) for l in cur.execute(
                "SELECT * FROM planification_budget WHERE tenant_id = %s AND initiative_id = %s",
                (tenant, initiative_id)).fetchall()]
    with conn.cursor(row_factory=dict_row) as cur:
        return [_ligne(l) for l in cur.execute(
            "SELECT * FROM planification_budget WHERE tenant_id = %s ORDER BY libelle", (tenant,)).fetchall()]


def enregistrer_budget(conn, tenant: str, budget: dict) -> str:
    identifiant = str(budget.get("id") or uuid.uuid4().hex)
    conn.execute(
        "INSERT INTO planification_budget "
        "(tenant_id, id, initiative_id, objet_source_type, objet_source_id, libelle, devise, enveloppe, periode, source) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (tenant_id, id) DO UPDATE SET "
        "initiative_id = EXCLUDED.initiative_id, objet_source_type = EXCLUDED.objet_source_type, "
        "objet_source_id = EXCLUDED.objet_source_id, libelle = EXCLUDED.libelle, "
        "devise = EXCLUDED.devise, enveloppe = EXCLUDED.enveloppe, periode = EXCLUDED.periode, "
        "source = EXCLUDED.source, maj_le = now()",
        (tenant, identifiant, budget.get("initiative_id"), budget.get("objet_source_type"),
         budget.get("objet_source_id"), budget.get("libelle") or identifiant,
         budget.get("devise") or "EUR", budget.get("enveloppe") or 0, budget.get("periode"),
         budget.get("source")))
    return identifiant


def enregistrer_cout(conn, tenant: str, cout: dict) -> str:
    identifiant = str(cout.get("id") or uuid.uuid4().hex)
    conn.execute(
        "INSERT INTO planification_cout "
        "(tenant_id, id, budget_id, equipe_id, periode, prevu, engage, reel, forecast, source) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (tenant_id, id) DO UPDATE SET "
        "budget_id = EXCLUDED.budget_id, equipe_id = EXCLUDED.equipe_id, periode = EXCLUDED.periode, "
        "prevu = EXCLUDED.prevu, engage = EXCLUDED.engage, reel = EXCLUDED.reel, "
        "forecast = EXCLUDED.forecast, source = EXCLUDED.source, maj_le = now()",
        (tenant, identifiant, cout.get("budget_id"), cout.get("equipe_id"), cout.get("periode"),
         cout.get("prevu") or 0, cout.get("engage") or 0, cout.get("reel") or 0,
         cout.get("forecast") or 0, cout.get("source")))
    return identifiant


def couts(conn, tenant: str, budget_id: str | None = None) -> list[dict]:
    if budget_id:
        with conn.cursor(row_factory=dict_row) as cur:
            return [_ligne(l) for l in cur.execute(
                "SELECT * FROM planification_cout WHERE tenant_id = %s AND budget_id = %s",
                (tenant, budget_id)).fetchall()]
    with conn.cursor(row_factory=dict_row) as cur:
        return [_ligne(l) for l in cur.execute(
            "SELECT * FROM planification_cout WHERE tenant_id = %s", (tenant,)).fetchall()]


def valeurs(conn, tenant: str, initiative_id: str | None = None) -> list[dict]:
    condition = "AND objet_source_id = %s" if initiative_id else ""
    params = [tenant] + ([initiative_id] if initiative_id else [])
    with conn.cursor(row_factory=dict_row) as cur:
        return [_ligne(l) for l in cur.execute(
            "SELECT id, tenant_id, libelle, type, statut, devise, unite, baseline, cible, observe, "
            "attribution, confiance, objet_source_type, objet_source_id FROM valeur "
            "WHERE tenant_id = %s " + condition + " ORDER BY libelle", params).fetchall()]


def hash_entree(valeur: Any) -> str:
    return hashlib.sha256(json.dumps(valeur, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def creer_sync_run(conn, tenant: str, source_id: str) -> str:
    identifiant = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO planification_sync_run (tenant_id, id, source_id, etat) "
        "VALUES (%s, %s, %s, 'EN_COURS')", (tenant, identifiant, source_id))
    return identifiant


def terminer_sync_run(conn, tenant: str, run_id: str, *, etat: str, lus: int = 0,
                      ecrits: int = 0, erreur: str | None = None,
                      metriques: dict | None = None) -> None:
    conn.execute(
        "UPDATE planification_sync_run SET etat = %s, fin = now(), lus = %s, ecrits = %s, "
        "erreur = %s, metriques = %s WHERE tenant_id = %s AND id = %s",
        (etat, lus, ecrits, (erreur or "")[:500] or None, Jsonb(metriques or {}), tenant, run_id))


def planification_sante(conn, tenant: str) -> dict:
    sources = []
    for source in lister_sources(conn, tenant):
        public = {cle: valeur for cle, valeur in source.items()
                  if cle not in {"secret_ref", "configuration"}}
        public["a_secret"] = bool(source.get("secret_ref"))
        sources.append(public)
    with conn.cursor(row_factory=dict_row) as cur:
        runs = [_ligne(l) for l in cur.execute(
            "SELECT DISTINCT ON (source_id) source_id, id, etat, debut, fin, lus, ecrits, erreur "
            "FROM planification_sync_run WHERE tenant_id = %s ORDER BY source_id, debut DESC",
            (tenant,)).fetchall()]
    return {"tenant": tenant, "sources": sources, "derniers_runs": runs}


def cycles(conn, tenant: str, equipe_id: str | None = None,
           termines: bool | None = None) -> list[dict]:
    conditions = ["tenant_id = %s"]
    params: list[Any] = [tenant]
    if equipe_id:
        conditions.append("equipe_id = %s")
        params.append(equipe_id)
    if termines is not None:
        conditions.append("termine = %s")
        params.append(bool(termines))
    with conn.cursor(row_factory=dict_row) as cur:
        return [_ligne(l) for l in cur.execute(
            f"SELECT * FROM planification_cycle WHERE {' AND '.join(conditions)} "
            "ORDER BY debut NULLS LAST, id", params).fetchall()]


def elements_historique(conn, tenant: str, equipe_id: str | None = None) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        if equipe_id:
            return [_ligne(l) for l in cur.execute(
                "SELECT * FROM planification_element WHERE tenant_id = %s AND equipe_id = %s "
                "AND cycle_id IS NOT NULL ORDER BY cycle_id, id", (tenant, equipe_id)).fetchall()]
        return [_ligne(l) for l in cur.execute(
            "SELECT * FROM planification_element WHERE tenant_id = %s AND cycle_id IS NOT NULL "
            "ORDER BY cycle_id, id", (tenant,)).fetchall()]


def dependances(conn, tenant: str) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return [_ligne(l) for l in cur.execute(
            "SELECT * FROM planification_dependance WHERE tenant_id = %s ORDER BY id",
            (tenant,)).fetchall()]


def plans(conn, tenant: str, equipe_id: str | None = None) -> list[dict]:
    if equipe_id:
        with conn.cursor(row_factory=dict_row) as cur:
            return [_ligne(l) for l in cur.execute(
                "SELECT * FROM planification_plan WHERE tenant_id = %s AND equipe_id = %s ORDER BY maj_le DESC",
                (tenant, equipe_id)).fetchall()]
    with conn.cursor(row_factory=dict_row) as cur:
        return [_ligne(l) for l in cur.execute(
            "SELECT * FROM planification_plan WHERE tenant_id = %s ORDER BY maj_le DESC",
            (tenant,)).fetchall()]


def previsions(conn, tenant: str, equipe_id: str | None = None) -> list[dict]:
    if equipe_id:
        with conn.cursor(row_factory=dict_row) as cur:
            return [_ligne(l) for l in cur.execute(
                "SELECT * FROM planification_prevision WHERE tenant_id = %s AND equipe_id = %s "
                "ORDER BY cree_le DESC", (tenant, equipe_id)).fetchall()]
    with conn.cursor(row_factory=dict_row) as cur:
        return [_ligne(l) for l in cur.execute(
            "SELECT * FROM planification_prevision WHERE tenant_id = %s ORDER BY cree_le DESC",
            (tenant,)).fetchall()]


def membres(conn, tenant: str, equipe_id: str | None = None) -> list[dict]:
    if equipe_id:
        with conn.cursor(row_factory=dict_row) as cur:
            return [_ligne(l) for l in cur.execute(
                "SELECT equipe_id, acteur, fte, role, source, maj_le FROM planification_membre "
                "WHERE tenant_id = %s AND equipe_id = %s ORDER BY acteur", (tenant, equipe_id)).fetchall()]
    with conn.cursor(row_factory=dict_row) as cur:
        return [_ligne(l) for l in cur.execute(
            "SELECT equipe_id, acteur, fte, role, source, maj_le FROM planification_membre "
            "WHERE tenant_id = %s ORDER BY equipe_id, acteur", (tenant,)).fetchall()]


def competences(conn, tenant: str, equipe_id: str | None = None) -> list[dict]:
    if equipe_id:
        with conn.cursor(row_factory=dict_row) as cur:
            return [_ligne(l) for l in cur.execute(
                "SELECT equipe_id, competence, niveau, source, maj_le FROM planification_competence "
                "WHERE tenant_id = %s AND equipe_id = %s ORDER BY competence", (tenant, equipe_id)).fetchall()]
    with conn.cursor(row_factory=dict_row) as cur:
        return [_ligne(l) for l in cur.execute(
            "SELECT equipe_id, competence, niveau, source, maj_le FROM planification_competence "
            "WHERE tenant_id = %s ORDER BY equipe_id, competence", (tenant,)).fetchall()]


def enregistrer_plan(conn, tenant: str, plan: dict, lignes: list[dict] | None = None) -> str:
    identifiant = str(plan.get("id") or uuid.uuid4().hex)
    conn.execute(
        "INSERT INTO planification_plan "
        "(tenant_id, id, nom, equipe_id, horizon, version, statut, auteur, hypotheses) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (tenant_id, id) DO UPDATE SET "
        "nom = EXCLUDED.nom, equipe_id = EXCLUDED.equipe_id, horizon = EXCLUDED.horizon, "
        "version = planification_plan.version + 1, statut = EXCLUDED.statut, auteur = EXCLUDED.auteur, "
        "hypotheses = EXCLUDED.hypotheses, maj_le = now()",
        (tenant, identifiant, plan.get("nom") or identifiant, plan.get("equipe_id"),
         plan.get("horizon"), int(plan.get("version") or 1), plan.get("statut") or "brouillon",
         plan.get("auteur"), Jsonb(plan.get("hypotheses") or [])))
    for ligne in lignes or []:
        conn.execute(
            "INSERT INTO planification_plan_ligne "
            "(tenant_id, plan_id, element_id, equipe_id, categorie, periode, valeur, unite) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (tenant_id, plan_id, element_id) "
            "DO UPDATE SET equipe_id = EXCLUDED.equipe_id, categorie = EXCLUDED.categorie, "
            "periode = EXCLUDED.periode, valeur = EXCLUDED.valeur, unite = EXCLUDED.unite",
            (tenant, identifiant, ligne.get("element_id"), ligne.get("equipe_id"),
             ligne.get("categorie") or "planifiee", ligne.get("periode"),
             ligne.get("valeur"), ligne.get("unite")))
    return identifiant


def plan(conn, tenant: str, plan_id: str) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        ligne = cur.execute(
            "SELECT * FROM planification_plan WHERE tenant_id = %s AND id = %s",
            (tenant, plan_id)).fetchone()
        if not ligne:
            return None
        resultat = _ligne(ligne)
        resultat["lignes"] = [_ligne(l) for l in cur.execute(
            "SELECT * FROM planification_plan_ligne WHERE tenant_id = %s AND plan_id = %s "
            "ORDER BY element_id", (tenant, plan_id)).fetchall()]
        return resultat



def enregistrer_membre(conn, tenant: str, membre: dict) -> str:
    equipe_id = str(membre.get("equipe_id") or "")
    acteur = str(membre.get("acteur") or "")
    if not equipe_id or not acteur:
        raise ValueError("membre sans équipe ou acteur")
    conn.execute(
        "INSERT INTO planification_membre (tenant_id, equipe_id, acteur, fte, role, source) "
        "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (tenant_id, equipe_id, acteur) DO UPDATE SET "
        "fte = EXCLUDED.fte, role = EXCLUDED.role, source = EXCLUDED.source, maj_le = now()",
        (tenant, equipe_id, acteur, membre.get("fte") or 1, membre.get("role"),
         membre.get("source") or "people"))
    return f"{equipe_id}:{acteur}"


def enregistrer_competence(conn, tenant: str, competence: dict) -> str:
    equipe_id = str(competence.get("equipe_id") or "")
    nom = str(competence.get("competence") or "")
    if not equipe_id or not nom:
        raise ValueError("compétence sans équipe ou nom")
    conn.execute(
        "INSERT INTO planification_competence (tenant_id, equipe_id, competence, niveau, source) "
        "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (tenant_id, equipe_id, competence) DO UPDATE SET "
        "niveau = EXCLUDED.niveau, source = EXCLUDED.source, maj_le = now()",
        (tenant, equipe_id, nom, int(competence.get("niveau") or 0),
         competence.get("source") or "people"))
    return f"{equipe_id}:{nom}"


def prevision(conn, tenant: str, prevision_id: str) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        ligne = cur.execute(
            "SELECT * FROM planification_prevision WHERE tenant_id = %s AND id = %s",
            (tenant, prevision_id)).fetchone()
    return _ligne(ligne) if ligne else None


def enregistrer_calibration(conn, tenant: str, prevision: dict, date_reelle: date) -> dict:
    identifiant = uuid.uuid4().hex
    p50 = prevision.get("p50")
    p85 = prevision.get("p85")
    p95 = prevision.get("p95")
    ecart = None
    try:
        ecart = (date_reelle - date.fromisoformat(str(p50)[:10])).days
    except (TypeError, ValueError):
        pass
    couvert = None
    try:
        couvert = date_reelle <= date.fromisoformat(str(p85)[:10])
    except (TypeError, ValueError):
        pass
    conn.execute(
        "INSERT INTO planification_calibration "
        "(tenant_id, id, prevision_id, date_reelle, p50, p85, p95, p85_couvert, ecart_jours) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (tenant, identifiant, prevision["id"], date_reelle, p50, p85, p95, couvert, ecart))
    return {"id": identifiant, "prevision_id": prevision["id"], "date_reelle": date_reelle.isoformat(),
            "p85_couvert": couvert, "ecart_jours": ecart}


def calibrations(conn, tenant: str) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return [_ligne(l) for l in cur.execute(
            "SELECT * FROM planification_calibration WHERE tenant_id = %s ORDER BY cree_le DESC",
            (tenant,)).fetchall()]


def enregistrer_webhook(conn, tenant: str, source_id: str, identifiant: str,
                        fournisseur: str | None = None) -> bool:
    """Vrai si l'événement est nouveau ; faux s'il a déjà été traité."""
    identifiant = str(identifiant or "").strip()
    if not identifiant:
        raise ValueError("identifiant de webhook requis")
    ligne = conn.execute(
        "INSERT INTO planification_webhook (tenant_id, id, source_id, fournisseur, identifiant) "
        "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING id",
        (tenant, uuid.uuid4().hex, source_id, fournisseur, identifiant)).fetchone()
    return ligne is not None


def enregistrer_absence(conn, tenant: str, absence: dict) -> str:
    identifiant = str(absence.get("id") or uuid.uuid4().hex)
    conn.execute(
        "INSERT INTO planification_absence "
        "(tenant_id, id, equipe_id, acteur, debut, fin, valeur, unite, source) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (tenant_id, id) DO UPDATE SET "
        "equipe_id = EXCLUDED.equipe_id, acteur = EXCLUDED.acteur, debut = EXCLUDED.debut, "
        "fin = EXCLUDED.fin, valeur = EXCLUDED.valeur, unite = EXCLUDED.unite, "
        "source = EXCLUDED.source, maj_le = now()",
        (tenant, identifiant, absence.get("equipe_id"), absence.get("acteur"),
         _date(absence.get("debut")), _date(absence.get("fin")),
         absence.get("valeur") or 0, absence.get("unite") or "jours", absence.get("source")))
    return identifiant


def absences(conn, tenant: str, equipe_id: str | None = None,
             debut: date | None = None, fin: date | None = None) -> list[dict]:
    conditions = ["tenant_id = %s"]
    params: list[Any] = [tenant]
    if equipe_id:
        conditions.append("equipe_id = %s")
        params.append(equipe_id)
    if debut:
        conditions.append("fin >= %s")
        params.append(debut)
    if fin:
        conditions.append("debut <= %s")
        params.append(fin)
    with conn.cursor(row_factory=dict_row) as cur:
        return [_ligne(l) for l in cur.execute(
            f"SELECT * FROM planification_absence WHERE {' AND '.join(conditions)} ORDER BY debut, id",
            params).fetchall()]


def enregistrer_allocation(conn, tenant: str, allocation: dict) -> str:
    identifiant = str(allocation.get("id") or uuid.uuid4().hex)
    conn.execute(
        "INSERT INTO planification_allocation "
        "(tenant_id, id, equipe_id, acteur, element_id, initiative_id, debut, fin, valeur, unite, source) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (tenant_id, id) DO UPDATE SET "
        "equipe_id = EXCLUDED.equipe_id, acteur = EXCLUDED.acteur, element_id = EXCLUDED.element_id, "
        "initiative_id = EXCLUDED.initiative_id, debut = EXCLUDED.debut, fin = EXCLUDED.fin, "
        "valeur = EXCLUDED.valeur, unite = EXCLUDED.unite, source = EXCLUDED.source, maj_le = now()",
        (tenant, identifiant, allocation.get("equipe_id"), allocation.get("acteur"),
         allocation.get("element_id"), allocation.get("initiative_id"),
         _date(allocation.get("debut")), _date(allocation.get("fin")),
         allocation.get("valeur") or 0, allocation.get("unite") or "pourcentage",
         allocation.get("source")))
    return identifiant


def allocations(conn, tenant: str, equipe_id: str | None = None) -> list[dict]:
    if equipe_id:
        with conn.cursor(row_factory=dict_row) as cur:
            return [_ligne(l) for l in cur.execute(
                "SELECT * FROM planification_allocation WHERE tenant_id = %s AND equipe_id = %s "
                "ORDER BY debut NULLS LAST, id", (tenant, equipe_id)).fetchall()]
    with conn.cursor(row_factory=dict_row) as cur:
        return [_ligne(l) for l in cur.execute(
            "SELECT * FROM planification_allocation WHERE tenant_id = %s "
            "ORDER BY equipe_id, debut NULLS LAST, id", (tenant,)).fetchall()]


def enregistrer_temps(conn, tenant: str, temps: dict) -> str:
    identifiant = str(temps.get("id") or uuid.uuid4().hex)
    conn.execute(
        "INSERT INTO planification_temps "
        "(tenant_id, id, source_id, element_id, equipe_id, acteur, date_travail, periode, valeur, unite, source) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (tenant_id, id) DO UPDATE SET "
        "element_id = EXCLUDED.element_id, equipe_id = EXCLUDED.equipe_id, acteur = EXCLUDED.acteur, "
        "date_travail = EXCLUDED.date_travail, periode = EXCLUDED.periode, valeur = EXCLUDED.valeur, "
        "unite = EXCLUDED.unite, source = EXCLUDED.source, maj_le = now()",
        (tenant, identifiant, temps.get("source_id"), temps.get("element_id"), temps.get("equipe_id"),
         temps.get("acteur"), _date(temps.get("date_travail")), temps.get("periode"),
         temps.get("valeur") or 0, temps.get("unite") or "heures", temps.get("source")))
    return identifiant


def temps(conn, tenant: str, equipe_id: str | None = None,
          debut: date | None = None, fin: date | None = None) -> list[dict]:
    conditions = ["tenant_id = %s"]
    params: list[Any] = [tenant]
    if equipe_id:
        conditions.append("equipe_id = %s")
        params.append(equipe_id)
    if debut:
        conditions.append("date_travail >= %s")
        params.append(debut)
    if fin:
        conditions.append("date_travail <= %s")
        params.append(fin)
    with conn.cursor(row_factory=dict_row) as cur:
        return [_ligne(l) for l in cur.execute(
            f"SELECT * FROM planification_temps WHERE {' AND '.join(conditions)} "
            "ORDER BY date_travail, id", params).fetchall()]


def enregistrer_taux(conn, tenant: str, taux: dict) -> str:
    identifiant = str(taux.get("id") or uuid.uuid4().hex)
    conn.execute(
        "INSERT INTO planification_taux "
        "(tenant_id, id, equipe_id, role, devise, cout_heure, debut, fin, source) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (tenant_id, id) DO UPDATE SET "
        "equipe_id = EXCLUDED.equipe_id, role = EXCLUDED.role, devise = EXCLUDED.devise, "
        "cout_heure = EXCLUDED.cout_heure, debut = EXCLUDED.debut, fin = EXCLUDED.fin, "
        "source = EXCLUDED.source, maj_le = now()",
        (tenant, identifiant, taux.get("equipe_id"), taux.get("role"), taux.get("devise") or "EUR",
         taux.get("cout_heure") or 0, _date(taux.get("debut")), _date(taux.get("fin")),
         taux.get("source")))
    return identifiant


def taux(conn, tenant: str, equipe_id: str | None = None) -> list[dict]:
    if equipe_id:
        with conn.cursor(row_factory=dict_row) as cur:
            return [_ligne(l) for l in cur.execute(
                "SELECT * FROM planification_taux WHERE tenant_id = %s AND equipe_id = %s ORDER BY id",
                (tenant, equipe_id)).fetchall()]
    with conn.cursor(row_factory=dict_row) as cur:
        return [_ligne(l) for l in cur.execute(
            "SELECT * FROM planification_taux WHERE tenant_id = %s ORDER BY equipe_id, id",
            (tenant,)).fetchall()]


def enregistrer_artefact(conn, tenant: str, artefact: dict) -> dict:
    from meridian.domain import artefacts
    propre = artefacts.valider(artefact)
    identifiant = str(propre.get("artefact_id") or propre.get("hash") or uuid.uuid4().hex)[:64]
    conn.execute(
        "INSERT INTO planification_artefact "
        "(tenant_id, id, type, titre, version, hash, source, donnees) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (tenant_id, id) DO UPDATE SET "
        "titre = EXCLUDED.titre, version = EXCLUDED.version, hash = EXCLUDED.hash, "
        "source = EXCLUDED.source, donnees = EXCLUDED.donnees",
        (tenant, identifiant, propre.get("type"), propre.get("titre"),
         propre.get("version") or "1.0", propre.get("hash") or "", propre.get("source"),
         Jsonb(propre)))
    return {**propre, "artefact_id": identifiant}


def artefact(conn, tenant: str, artefact_id: str) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        ligne = cur.execute(
            "SELECT donnees FROM planification_artefact WHERE tenant_id = %s AND id = %s",
            (tenant, artefact_id)).fetchone()
    return _ligne(ligne)["donnees"] if ligne else None


def artefacts(conn, tenant: str, type_: str | None = None) -> list[dict]:
    if type_:
        with conn.cursor(row_factory=dict_row) as cur:
            return [_ligne(l)["donnees"] for l in cur.execute(
                "SELECT donnees FROM planification_artefact WHERE tenant_id = %s AND type = %s "
                "ORDER BY cree_le DESC", (tenant, type_)).fetchall()]
    with conn.cursor(row_factory=dict_row) as cur:
        return [_ligne(l)["donnees"] for l in cur.execute(
            "SELECT donnees FROM planification_artefact WHERE tenant_id = %s "
            "ORDER BY cree_le DESC", (tenant,)).fetchall()]
