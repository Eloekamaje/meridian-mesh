"""Persistance du graphe d'interfaces (Postgres), par tenant et sans fusion d'identité.

Un enregistrement rejoué met à jour les mêmes lignes ; une assertion n'est jamais fusionnée avec une autre : sa clé
unique porte le mode, la source, le locator, l'environnement et la preuve. Aucun secret d'URL n'entre en base.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from urllib.parse import parse_qsl, unquote_plus, urlsplit

from psycopg.rows import dict_row

MODES = ("declared", "observed", "inferred")
_MARQUEURS_SECRETS = ("password", "passwd", "secret", "token", "credential", "authorization")
_CLES_SECRETES = frozenset({"pwd", "pass", "auth", "apikey", "api_key", "api-key", "access_key",
                            "private_key", "key"})


def _tenant(tenant_id) -> str:
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("tenant_id vide : opération refusée")
    return tenant_id.strip()


def _cle_sensible(cle: str) -> bool:
    normalisee = unquote_plus(cle).strip().lower()
    return (normalisee in _CLES_SECRETES or normalisee.endswith(("_key", "-key"))
            or any(marque in normalisee for marque in _MARQUEURS_SECRETS))


def _url_porte_un_secret(url) -> bool:
    if not isinstance(url, str):
        return True
    try:
        parties = urlsplit(url)
    except (ValueError, UnicodeError):
        return True
    if "@" in parties.netloc or parties.username is not None or parties.password is not None:
        return True
    return any(_cle_sensible(cle) and valeur not in ("", "***")
               for cle, valeur in parse_qsl(parties.query, keep_blank_values=True))


def _valeur(valeur):
    if isinstance(valeur, Decimal):
        return float(valeur)
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    return valeur


def _ligne(ligne) -> dict:
    return {cle: _valeur(valeur) for cle, valeur in ligne.items()}


def _texte_temporel(valeur):
    if valeur is None:
        return None
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    return str(valeur)


def enregistrer(conn, tenant_id, graph) -> dict:
    """Upsert idempotent du graphe ; refuse un tenant vide et toute URL de binding porteuse d'un secret."""
    tenant = _tenant(tenant_id)
    if graph is None:
        raise ValueError("graphe d'interfaces absent")
    for binding in graph.bindings:
        if _url_porte_un_secret(binding.url):
            raise ValueError("binding refusé : URL non assainie (identifiants ou secret)")
    for assertion in graph.assertions:
        if assertion.mode not in MODES:
            raise ValueError(f"mode d'assertion invalide : {assertion.mode!r}")

    with conn.transaction():
        for contrat in graph.contracts:
            conn.execute(
                "INSERT INTO interface_contract "
                "(id, tenant_id, application_id, format, version, digest, locator, environment) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (tenant_id, id) DO UPDATE SET application_id = EXCLUDED.application_id, "
                "format = EXCLUDED.format, version = EXCLUDED.version, digest = EXCLUDED.digest, "
                "locator = EXCLUDED.locator, environment = EXCLUDED.environment",
                (contrat.id, tenant, contrat.application_id, contrat.format, contrat.version, contrat.digest,
                 contrat.locator, contrat.environment))
        for operation in graph.operations:
            conn.execute(
                "INSERT INTO interface_operation "
                "(id, tenant_id, contract_id, protocol, method, path, name, version, environment) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (tenant_id, id) DO UPDATE SET contract_id = EXCLUDED.contract_id, "
                "protocol = EXCLUDED.protocol, method = EXCLUDED.method, path = EXCLUDED.path, "
                "name = EXCLUDED.name, version = EXCLUDED.version, environment = EXCLUDED.environment",
                (operation.id, tenant, operation.contract_id, operation.protocol, operation.method, operation.path,
                 operation.name, operation.version, operation.environment))
        for binding in graph.bindings:
            conn.execute(
                "INSERT INTO interface_binding (id, tenant_id, protocol, url, environment, gateway) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (tenant_id, id) DO UPDATE SET protocol = EXCLUDED.protocol, url = EXCLUDED.url, "
                "environment = EXCLUDED.environment, gateway = EXCLUDED.gateway",
                (binding.id, tenant, binding.protocol, binding.url, binding.environment, binding.gateway))
        for assertion in graph.assertions:
            conn.execute(
                "INSERT INTO interface_assertion "
                "(tenant_id, subject, predicate, object, mode, source, locator, environment, confidence, evidence, "
                "observed_at, valid_from) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (tenant_id, subject, predicate, object, mode, source, locator, environment, evidence) "
                "DO UPDATE SET confidence = EXCLUDED.confidence, "
                "observed_at = coalesce(EXCLUDED.observed_at, interface_assertion.observed_at), "
                "valid_from = coalesce(EXCLUDED.valid_from, interface_assertion.valid_from)",
                (tenant, assertion.subject, assertion.predicate, assertion.object, assertion.mode, assertion.source,
                 assertion.locator, assertion.environment, assertion.confidence, assertion.evidence,
                 _texte_temporel(assertion.observed_at), _texte_temporel(assertion.valid_from)))

    return {
        "contracts": len({contrat.id for contrat in graph.contracts}),
        "operations": len({operation.id for operation in graph.operations}),
        "bindings": len({binding.id for binding in graph.bindings}),
        "assertions": len({(a.subject, a.predicate, a.object, a.mode, a.source, a.locator, a.environment,
                            a.evidence) for a in graph.assertions}),
    }


def compter(conn, tenant_id) -> dict:
    """Nombre de lignes de chaque table d'interfaces pour un tenant."""
    tenant = _tenant(tenant_id)
    compte = {}
    for cle, table in (("contracts", "interface_contract"), ("operations", "interface_operation"),
                       ("bindings", "interface_binding"), ("assertions", "interface_assertion")):
        compte[cle] = conn.execute(f"SELECT count(*) FROM {table} WHERE tenant_id = %s", (tenant,)).fetchone()[0]
    return compte


def lire(conn, tenant_id, application_id=None, predicat=None) -> dict:
    """Relit les assertions filtrées et les contrats, opérations et bindings qui leur sont rattachés."""
    tenant = _tenant(tenant_id)
    with conn.cursor(row_factory=dict_row) as cur:
        requete = "SELECT * FROM interface_assertion WHERE tenant_id = %s"
        parametres = [tenant]
        if application_id is not None:
            requete += " AND subject = %s"
            parametres.append(application_id)
        if predicat is not None:
            requete += " AND predicate = %s"
            parametres.append(predicat)
        cur.execute(requete + " ORDER BY id", parametres)
        assertions = [_ligne(ligne) for ligne in cur.fetchall()]

        if application_id is not None:
            applications = {application_id, *(a["subject"] for a in assertions)}
        elif predicat is not None:
            applications = {a["subject"] for a in assertions}
        else:
            applications = None

        if applications is None:
            cur.execute("SELECT * FROM interface_contract WHERE tenant_id = %s ORDER BY application_id, id",
                        (tenant,))
        else:
            cur.execute("SELECT * FROM interface_contract WHERE tenant_id = %s AND application_id = ANY(%s) "
                        "ORDER BY application_id, id", (tenant, sorted(applications)))
        contracts = [_ligne(ligne) for ligne in cur.fetchall()]

        if applications is None:
            cur.execute("SELECT * FROM interface_operation WHERE tenant_id = %s "
                        "ORDER BY contract_id, method, path, id", (tenant,))
        else:
            contrats = sorted({contrat["id"] for contrat in contracts})
            cur.execute("SELECT * FROM interface_operation WHERE tenant_id = %s AND contract_id = ANY(%s) "
                        "ORDER BY contract_id, method, path, id", (tenant, contrats))
        operations = [_ligne(ligne) for ligne in cur.fetchall()]

        if applications is None:
            cur.execute("SELECT * FROM interface_binding WHERE tenant_id = %s ORDER BY environment, url, id",
                        (tenant,))
        else:
            objets = sorted({a["object"] for a in assertions})
            environnements = sorted({a["environment"] for a in assertions}
                                    | {contrat["environment"] for contrat in contracts})
            cur.execute("SELECT * FROM interface_binding WHERE tenant_id = %s "
                        "AND (url = ANY(%s) OR environment = ANY(%s)) ORDER BY environment, url, id",
                        (tenant, objets, environnements))
        bindings = [_ligne(ligne) for ligne in cur.fetchall()]

    return {"contracts": contracts, "operations": operations, "bindings": bindings, "assertions": assertions}
