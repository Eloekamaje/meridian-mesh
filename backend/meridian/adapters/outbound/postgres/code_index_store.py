"""Persistance de l'index legacy fédéré : observations, couverture et liens.

Le magasin ne crée aucun Claim : il remplace, pour un couple ``(tenant_id,
jumeau_id)``, les lignes produites par les sidecars puis les relit. Toute
lecture filtre le tenant **et** le jumeau ; aucune suppression ne sort de ce
couple.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from meridian.application.code_links import Link, STATUTS_LIEN
from meridian.domain.code_index import STATUTS as STATUTS_COUVERTURE
from meridian.domain.code_index import CouvertureFichier, Observation

__all__ = [
    "LIMITE_DEFAUT",
    "LIMITE_MAX",
    "lire_couverture",
    "lire_liens",
    "lire_observations",
    "lire_observations_liens",
    "remplacer",
    "remplacer_source",
    "resume",
]

STATUTS_OBSERVATION = ("extracted", "inferred", "ambiguous", "conflict")
LIMITE_DEFAUT = 100
LIMITE_MAX = 1000
KINDS_LIENS = (
    "cbm_route", "spring_route", "jaxrs_route", "web_servlet",
    "cbm_relation_http_calls", "cbm_env", "jee_injection",
)
LIMITE_LIENS = 20000
SOURCE_VALIDE = re.compile(r"(?!\.+$)[A-Za-z0-9._-]+\Z")

_SQL_OBSERVATION = (
    "INSERT INTO code_observation (tenant_id, jumeau_id, provider, parser, parser_version, file, "
    "language, kind, symbol, start_line, end_line, commit_sha, attributes, confidence, status, "
    "fingerprint) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)

_SQL_COUVERTURE = (
    "INSERT INTO code_coverage (tenant_id, jumeau_id, file, language, parser, status, reason) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s)"
)

_SQL_LIEN = (
    "INSERT INTO code_link (tenant_id, jumeau_id, kind, source_file, source_symbol, target_file, "
    "target_symbol, attributes, confidence, status, evidence, fingerprint) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)

_COLONNES_OBSERVATION = (
    "provider, parser, parser_version, file, language, kind, symbol, start_line, end_line, "
    "commit_sha, attributes, confidence, status, fingerprint, updated_at"
)

_COLONNES_LIEN = (
    "kind, source_file, source_symbol, target_file, target_symbol, attributes, confidence, "
    "status, evidence, fingerprint, updated_at"
)


def _identifiant(valeur, nom: str) -> str:
    if not isinstance(valeur, str) or not valeur.strip():
        raise ValueError(f"{nom} vide : opération refusée")
    return valeur.strip()


def _objet_json(valeur) -> dict:
    if valeur is None:
        return {}
    if isinstance(valeur, str):
        try:
            valeur = json.loads(valeur)
        except (TypeError, ValueError):
            return {}
    if not isinstance(valeur, Mapping):
        return {}
    return dict(valeur)


def _empreinte(*parties) -> str:
    charge = json.dumps(list(parties), ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(charge.encode("utf-8")).hexdigest()


def _observation(objet) -> Observation:
    if isinstance(objet, Observation):
        return objet
    if not isinstance(objet, Mapping):
        raise TypeError("observation attendue : Observation ou dict")
    return Observation(
        provider=objet.get("provider", ""),
        parser=objet.get("parser", ""),
        parser_version=objet.get("parser_version", ""),
        file=objet.get("file") or objet.get("fichier") or "",
        language=objet.get("language", ""),
        kind=objet.get("kind", ""),
        symbol=objet.get("symbol", ""),
        start=objet.get("start", objet.get("start_line", 0)),
        end=objet.get("end", objet.get("end_line", 0)),
        commit=objet.get("commit", objet.get("commit_sha", "")),
        attributes=_objet_json(objet.get("attributes")),
        confidence=objet.get("confidence", 1.0),
        status=objet.get("status", "extracted"),
    )


def _couverture(objet) -> CouvertureFichier:
    if isinstance(objet, CouvertureFichier):
        return objet
    if not isinstance(objet, Mapping):
        raise TypeError("couverture attendue : CouvertureFichier ou dict")
    return CouvertureFichier(
        file=objet.get("file") or objet.get("fichier") or "",
        language=objet.get("language", ""),
        parser=objet.get("parser", ""),
        statut=objet.get("statut", objet.get("status", "non_supporte")),
        raison=objet.get("raison", objet.get("reason", "")),
    )


def _lien(objet) -> Link:
    if isinstance(objet, Link):
        return objet
    if not isinstance(objet, Mapping):
        raise TypeError("lien attendu : Link ou dict")
    return Link(
        kind=objet.get("kind", ""),
        source_file=objet.get("source_file", ""),
        source_symbol=objet.get("source_symbol", ""),
        target_file=objet.get("target_file", ""),
        target_symbol=objet.get("target_symbol", ""),
        attributes=_objet_json(objet.get("attributes")),
        confidence=objet.get("confidence", 1.0),
        status=objet.get("status", "linked"),
        evidence=_objet_json(objet.get("evidence")),
    )


def _source(valeur) -> str:
    """Composant de chemin stable qui sépare deux dépôts d'un même jumeau."""
    source = _identifiant(valeur, "source")
    if not SOURCE_VALIDE.fullmatch(source):
        raise ValueError("source invalide : lettres, chiffres, '.', '_' et '-' attendus")
    return source


def _chemin_source(source: str, chemin: str) -> str:
    chemin = str(chemin or "").strip().replace("\\", "/").lstrip("/")
    if not chemin:
        return ""
    prefixe = source + "/"
    return chemin if chemin.startswith(prefixe) else prefixe + chemin


def _observation_source(source: str, observation: Observation) -> Observation:
    return Observation(
        provider=observation.provider, parser=observation.parser,
        parser_version=observation.parser_version,
        file=_chemin_source(source, observation.file), language=observation.language,
        kind=observation.kind, symbol=observation.symbol,
        start=observation.start, end=observation.end, commit=observation.commit,
        attributes=_preuve_source(source, observation.attributes), confidence=observation.confidence,
        status=observation.status,
    )


def _couverture_source(source: str, couverture: CouvertureFichier) -> CouvertureFichier:
    return CouvertureFichier(
        file=_chemin_source(source, couverture.file), language=couverture.language,
        parser=couverture.parser, statut=couverture.statut, raison=couverture.raison,
    )


def _preuve_source(source: str, valeur):
    """Namespace les chemins structurés d'une preuve sans toucher à son texte libre."""
    if isinstance(valeur, list):
        return [_preuve_source(source, element) for element in valeur]
    if not isinstance(valeur, Mapping):
        return valeur
    resultat = {}
    for cle, element in valeur.items():
        if cle in {"file", "source_file", "target_file"} and isinstance(element, str):
            resultat[cle] = _chemin_source(source, element)
        else:
            resultat[cle] = _preuve_source(source, element)
    return resultat


def _lien_source(source: str, lien: Link) -> Link:
    return Link(
        kind=lien.kind,
        source_file=_chemin_source(source, lien.source_file),
        source_symbol=lien.source_symbol,
        target_file=_chemin_source(source, lien.target_file),
        target_symbol=lien.target_symbol,
        attributes=_preuve_source(source, lien.attributes), confidence=lien.confidence, status=lien.status,
        evidence=_preuve_source(source, lien.evidence),
    )


def _uniques(objets: Iterable, cle) -> list:
    vus: dict = {}
    for objet in objets or ():
        vus[cle(objet)] = objet
    return list(vus.values())


def _cle_observation(observation: Observation) -> tuple:
    return (observation.provider, observation.file, observation.kind,
            observation.symbol, observation.start, observation.end)


def _cle_couverture(couverture: CouvertureFichier) -> str:
    return couverture.file


def _cle_lien(lien: Link) -> tuple:
    return (lien.kind, lien.source_file, lien.source_symbol,
            lien.target_file, lien.target_symbol)


def _ligne_observation(tenant: str, jumeau: str, observation: Observation) -> tuple:
    fingerprint = _empreinte("observation", *_cle_observation(observation))
    return (tenant, jumeau, observation.provider, observation.parser,
            observation.parser_version, observation.file, observation.language,
            observation.kind, observation.symbol, observation.start, observation.end,
            observation.commit, Jsonb(observation.attributes), observation.confidence,
            observation.status, fingerprint)


def _ligne_couverture(tenant: str, jumeau: str, couverture: CouvertureFichier) -> tuple:
    return (tenant, jumeau, couverture.file, couverture.language, couverture.parser,
            couverture.statut, couverture.raison)


def _ligne_lien(tenant: str, jumeau: str, lien: Link) -> tuple:
    fingerprint = _empreinte("link", *_cle_lien(lien))
    return (tenant, jumeau, lien.kind, lien.source_file, lien.source_symbol,
            lien.target_file, lien.target_symbol, Jsonb(lien.attributes),
            lien.confidence, lien.status, Jsonb(lien.evidence), fingerprint)


def _inserer(conn, sql: str, lignes: list[tuple]) -> int:
    if not lignes:
        return 0
    with conn.cursor() as cur:
        cur.executemany(sql, lignes)
    return len(lignes)


def _limite(limite) -> int:
    if isinstance(limite, bool):
        raise ValueError("limite invalide")
    try:
        valeur = int(limite)
    except (TypeError, ValueError) as exc:
        raise ValueError("limite invalide") from exc
    if valeur < 1 or valeur > LIMITE_MAX:
        raise ValueError(f"limite doit être comprise entre 1 et {LIMITE_MAX}")
    return valeur


def _valeur(valeur):
    if isinstance(valeur, Decimal):
        return float(valeur)
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    return valeur


def _lignes(rows) -> list[dict]:
    return [{cle: _valeur(valeur) for cle, valeur in ligne.items()} for ligne in rows]


def remplacer(conn, tenant_id, jumeau_id, observations=(), couvertures=(), liens=()) -> dict:
    """Remplace toutes les lignes du couple tenant/jumeau, dans une seule transaction."""
    tenant = _identifiant(tenant_id, "tenant_id")
    jumeau = _identifiant(jumeau_id, "jumeau_id")
    observations = _uniques((_observation(objet) for objet in observations or ()),
                            _cle_observation)
    couvertures = _uniques((_couverture(objet) for objet in couvertures or ()),
                           _cle_couverture)
    liens = _uniques((_lien(objet) for objet in liens or ()), _cle_lien)

    with conn.transaction():
        conn.execute("DELETE FROM code_link WHERE tenant_id = %s AND jumeau_id = %s",
                     (tenant, jumeau))
        conn.execute("DELETE FROM code_observation WHERE tenant_id = %s AND jumeau_id = %s",
                     (tenant, jumeau))
        conn.execute("DELETE FROM code_coverage WHERE tenant_id = %s AND jumeau_id = %s",
                     (tenant, jumeau))
        _inserer(conn, _SQL_OBSERVATION,
                 [_ligne_observation(tenant, jumeau, observation) for observation in observations])
        _inserer(conn, _SQL_COUVERTURE,
                 [_ligne_couverture(tenant, jumeau, couverture) for couverture in couvertures])
        _inserer(conn, _SQL_LIEN,
                 [_ligne_lien(tenant, jumeau, lien) for lien in liens])

    return {"observations": len(observations), "couvertures": len(couvertures),
            "liens": len(liens)}


def remplacer_source(conn, tenant_id, jumeau_id, source, observations=(), couvertures=(), liens=()) -> dict:
    """Remplace uniquement l'index d'un dépôt, sans effacer les autres dépôts du jumeau.

    Les chemins persistés sont préfixés par le nom stable de la source. Cette portée évite aussi
    que deux dépôts contenant tous deux ``src/Main.java`` entrent en collision dans les contraintes
    historiques de l'index, qui sont définies au niveau du jumeau.
    """
    tenant = _identifiant(tenant_id, "tenant_id")
    jumeau = _identifiant(jumeau_id, "jumeau_id")
    source = _source(source)
    prefixe = source + "/"
    observations = _uniques(
        (_observation_source(source, _observation(objet)) for objet in observations or ()),
        _cle_observation)
    couvertures = _uniques(
        (_couverture_source(source, _couverture(objet)) for objet in couvertures or ()),
        _cle_couverture)
    liens = _uniques(
        (_lien_source(source, _lien(objet)) for objet in liens or ()), _cle_lien)

    with conn.transaction():
        conn.execute(
            "DELETE FROM code_link WHERE tenant_id = %s AND jumeau_id = %s "
            "AND (left(source_file, length(%s)) = %s OR left(target_file, length(%s)) = %s)",
            (tenant, jumeau, prefixe, prefixe, prefixe, prefixe))
        conn.execute(
            "DELETE FROM code_observation WHERE tenant_id = %s AND jumeau_id = %s "
            "AND left(file, length(%s)) = %s",
            (tenant, jumeau, prefixe, prefixe))
        conn.execute(
            "DELETE FROM code_coverage WHERE tenant_id = %s AND jumeau_id = %s "
            "AND left(file, length(%s)) = %s",
            (tenant, jumeau, prefixe, prefixe))
        _inserer(conn, _SQL_OBSERVATION,
                 [_ligne_observation(tenant, jumeau, observation) for observation in observations])
        _inserer(conn, _SQL_COUVERTURE,
                 [_ligne_couverture(tenant, jumeau, couverture) for couverture in couvertures])
        _inserer(conn, _SQL_LIEN,
                 [_ligne_lien(tenant, jumeau, lien) for lien in liens])

    return {"observations": len(observations), "couvertures": len(couvertures),
            "liens": len(liens)}


def lire_couverture(conn, tenant_id, jumeau_id, statut=None, limite=LIMITE_DEFAUT) -> list[dict]:
    """Couverture explicite du couple, filtrée par statut et bornée."""
    tenant = _identifiant(tenant_id, "tenant_id")
    jumeau = _identifiant(jumeau_id, "jumeau_id")
    maximum = _limite(limite)
    sql = ("SELECT file, language, parser, status, reason, updated_at FROM code_coverage "
           "WHERE tenant_id = %s AND jumeau_id = %s")
    params = [tenant, jumeau]
    if statut is not None and str(statut).strip():
        sql += " AND status = %s"
        params.append(str(statut).strip())
    sql += " ORDER BY file LIMIT %s"
    params.append(maximum)
    with conn.cursor(row_factory=dict_row) as cur:
        return _lignes(cur.execute(sql, tuple(params)).fetchall())


def lire_observations(conn, tenant_id, jumeau_id, kind=None, fichier=None,
                      limite=LIMITE_DEFAUT) -> list[dict]:
    """Observations du couple, filtrées par type et fichier, dans l'ordre du fichier."""
    tenant = _identifiant(tenant_id, "tenant_id")
    jumeau = _identifiant(jumeau_id, "jumeau_id")
    maximum = _limite(limite)
    sql = f"SELECT {_COLONNES_OBSERVATION} FROM code_observation WHERE tenant_id = %s AND jumeau_id = %s"
    params = [tenant, jumeau]
    if kind is not None and str(kind).strip():
        sql += " AND kind = %s"
        params.append(str(kind).strip())
    if fichier is not None and str(fichier).strip():
        sql += " AND file = %s"
        params.append(str(fichier).strip())
    sql += " ORDER BY file, start_line, kind, symbol LIMIT %s"
    params.append(maximum)
    with conn.cursor(row_factory=dict_row) as cur:
        return _lignes(cur.execute(sql, tuple(params)).fetchall())


def lire_observations_liens(conn, tenant_id, jumeau_ids=(), limite=LIMITE_LIENS
                            ) -> tuple[list[tuple[str, Observation]], bool]:
    """Observations utiles au moteur de liens, pour plusieurs jumeaux d'un tenant.

    Ne lit que les types qui portent une route, un appel HTTP ou une URL de
    configuration. Rend `(jumeau_id, Observation)` et un booléen qui signale
    explicitement que le plafond a été atteint, pour que l'appelant le journalise.
    """
    tenant = _identifiant(tenant_id, "tenant_id")
    ids = tuple(dict.fromkeys(
        str(valeur).strip() for valeur in jumeau_ids or () if str(valeur).strip()))
    if not ids:
        return [], False
    maximum = max(1, min(int(limite), LIMITE_LIENS))
    sql = (
        "SELECT jumeau_id, provider, parser, parser_version, file, language, kind, symbol, "
        "start_line, end_line, commit_sha, attributes, confidence, status, fingerprint "
        "FROM code_observation WHERE tenant_id = %s AND jumeau_id = ANY(%s) "
        "AND kind = ANY(%s) ORDER BY jumeau_id, file, start_line, kind, symbol LIMIT %s"
    )
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            sql, (tenant, list(ids), list(KINDS_LIENS), maximum + 1)).fetchall()
    tronque = len(lignes) > maximum
    return [(ligne["jumeau_id"], _observation(ligne)) for ligne in lignes[:maximum]], tronque


def lire_liens(conn, tenant_id, jumeau_id, kind=None, limite=LIMITE_DEFAUT) -> list[dict]:
    """Liens prouvés du couple, filtrés par famille et bornés."""
    tenant = _identifiant(tenant_id, "tenant_id")
    jumeau = _identifiant(jumeau_id, "jumeau_id")
    maximum = _limite(limite)
    sql = f"SELECT {_COLONNES_LIEN} FROM code_link WHERE tenant_id = %s AND jumeau_id = %s"
    params = [tenant, jumeau]
    if kind is not None and str(kind).strip():
        sql += " AND kind = %s"
        params.append(str(kind).strip())
    sql += " ORDER BY kind, source_file, source_symbol, target_file, target_symbol LIMIT %s"
    params.append(maximum)
    with conn.cursor(row_factory=dict_row) as cur:
        return _lignes(cur.execute(sql, tuple(params)).fetchall())


def _compte(rows, defauts: Iterable[str] = ()) -> dict:
    resultat = {cle: 0 for cle in defauts}
    for ligne in rows:
        resultat[str(ligne["cle"])] = int(ligne["nombre"])
    return dict(sorted(resultat.items()))


def _total(compteurs: dict) -> int:
    return sum(compteurs.values())


def resume(conn, tenant_id, jumeau_id) -> dict:
    """Compteurs par statut et provider, par famille de lien, et fichiers couverts."""
    tenant = _identifiant(tenant_id, "tenant_id")
    jumeau = _identifiant(jumeau_id, "jumeau_id")
    with conn.cursor(row_factory=dict_row) as cur:
        observations_statut = cur.execute(
            "SELECT status AS cle, count(*) AS nombre FROM code_observation "
            "WHERE tenant_id = %s AND jumeau_id = %s GROUP BY status ORDER BY status",
            (tenant, jumeau)).fetchall()
        observations_provider = cur.execute(
            "SELECT provider AS cle, count(*) AS nombre FROM code_observation "
            "WHERE tenant_id = %s AND jumeau_id = %s GROUP BY provider ORDER BY provider",
            (tenant, jumeau)).fetchall()
        couverture_statut = cur.execute(
            "SELECT status AS cle, count(*) AS nombre FROM code_coverage "
            "WHERE tenant_id = %s AND jumeau_id = %s GROUP BY status ORDER BY status",
            (tenant, jumeau)).fetchall()
        couverture_total = cur.execute(
            "SELECT count(*) AS nombre FROM code_coverage WHERE tenant_id = %s AND jumeau_id = %s",
            (tenant, jumeau)).fetchone()
        liens_kind = cur.execute(
            "SELECT kind AS cle, count(*) AS nombre FROM code_link "
            "WHERE tenant_id = %s AND jumeau_id = %s GROUP BY kind ORDER BY kind",
            (tenant, jumeau)).fetchall()
        liens_statut = cur.execute(
            "SELECT status AS cle, count(*) AS nombre FROM code_link "
            "WHERE tenant_id = %s AND jumeau_id = %s GROUP BY status ORDER BY status",
            (tenant, jumeau)).fetchall()

    observations = _compte(observations_statut, STATUTS_OBSERVATION)
    couverture = _compte(couverture_statut, STATUTS_COUVERTURE)
    liens = _compte(liens_statut, STATUTS_LIEN)
    fichiers = int((couverture_total or {}).get("nombre") or 0)
    return {
        "observations": {
            "total": _total(observations),
            "par_statut": observations,
            "par_provider": _compte(observations_provider),
        },
        "couverture": {
            "total": fichiers,
            "par_statut": couverture,
            "fichiers_couverts": fichiers,
            "fichiers_indexes": couverture.get("indexe", 0),
        },
        "liens": {
            "total": _total(liens),
            "par_kind": _compte(liens_kind),
            "par_statut": liens,
        },
    }
