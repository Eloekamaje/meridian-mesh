"""Persistance du graphe d'interfaces (Postgres), par tenant et sans fusion d'identité.

Un enregistrement rejoué met à jour les mêmes lignes ; une assertion n'est jamais fusionnée avec une autre : sa clé
unique porte le mode, la source, le locator, l'environnement et la preuve. Aucun secret d'URL n'entre en base.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from urllib.parse import parse_qsl, unquote_plus, urlsplit

from psycopg.rows import dict_row

from jumeau.interfaces import Assertion, Binding, Contract, InterfaceGraph, Operation

MODES = ("declared", "observed", "inferred")
_CHAMPS_CONTRACT = ("id", "format", "version", "digest", "locator", "application_id", "environment")
_CHAMPS_OPERATION = ("id", "contract_id", "protocol", "method", "path", "name", "version", "environment")
_CHAMPS_BINDING = ("id", "protocol", "url", "environment", "gateway")
_CHAMPS_ASSERTION = ("subject", "predicate", "object", "mode", "source", "locator", "environment", "confidence",
                     "evidence", "observed_at", "valid_from")
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


def _identifiants(application_ids) -> list[str]:
    if isinstance(application_ids, str):
        application_ids = [application_ids]
    return sorted({identifiant.strip() for identifiant in (application_ids or [])
                   if isinstance(identifiant, str) and identifiant.strip()})


def _contrats_visibles(graph, visibles: set[str]) -> dict[str, Contract]:
    return {contrat.id: contrat for contrat in graph.contracts if contrat.application_id in visibles}


def _references_operation(operation) -> set[str]:
    """Références qu'une assertion CONSOMME peut citer : identifiant, METHOD path (casse libre) ou chemin."""
    method = str(operation.method or "")
    return {reference for reference in (
        operation.id, f"{method} {operation.path}", f"{method.upper()} {operation.path}",
        f"{method.lower()} {operation.path}", operation.path) if reference}


def operations_publiques(graph, visibles) -> list[dict]:
    """Les opérations des seules applications visibles, avec leur application productrice."""
    visibles = set(_identifiants(visibles))
    contrats = _contrats_visibles(graph, visibles)
    operations = {}
    for operation in graph.operations:
        contrat = contrats.get(operation.contract_id)
        if contrat is None:
            continue
        operations.setdefault(operation.id, {
            "id": operation.id,
            "application_id": contrat.application_id,
            "method": operation.method,
            "path": operation.path,
            "protocol": operation.protocol,
            "environment": operation.environment,
            "name": operation.name,
        })
    return sorted(operations.values(),
                  key=lambda operation: (operation["application_id"], operation["method"], operation["path"],
                                         operation["id"]))


def _operation_citee(objet, references, producteurs, operations_par_app, exposees):
    """Une assertion CONSOMME peut citer l'id, METHOD path, le chemin, ou `<cible> : METHOD path` (runtime)."""
    if isinstance(objet, str) and " : " in objet:
        cible, reference = objet.split(" : ", 1)
        cible, reference = cible.strip(), reference.strip()
        candidates = [operation for operation in operations_par_app.get(cible, [])
                      if producteurs.get(operation.id) == cible and reference in _references_operation(operation)]
        # Deux contrats peuvent porter la même opération (code + runtime) : une production prouvée par EXPOSE
        # tranche ; sinon on ne choisit pas au hasard entre plusieurs candidats.
        prouvees = [operation for operation in candidates if operation.id in exposees]
        if len(prouvees) == 1:
            return prouvees[0]
        if len(candidates) == 1:
            return candidates[0]
        return None
    operation = references.get(objet)
    if operation is not None:
        return operation
    return None


def deriver_aretes(graph, visibles) -> list[dict]:
    """Dérive les arêtes CONSOMME → opération → application productrice via contrat/EXPOSE.

    Une assertion dont l'objet ne correspond à aucune opération connue ne produit rien : la cible n'est jamais
    inventée. Les applications hors périmètre (source, cible, opération) sont écartées. Une même arête
    `(source, cible, opération, mode, source d'assertion)` n'est rendue qu'une fois ; la preuve de meilleure
    confiance est conservée.
    """
    visibles = set(_identifiants(visibles))
    contrats = _contrats_visibles(graph, visibles)
    operations = {}
    for operation in sorted(graph.operations, key=lambda o: (o.id, o.contract_id, o.method or "", o.path or "")):
        if operation.contract_id in contrats:
            operations.setdefault(operation.id, operation)
    producteurs = {operation.id: contrats[operation.contract_id].application_id
                   for operation in operations.values()}
    operations_par_app: dict[str, list[Operation]] = {}
    for operation in operations.values():
        operations_par_app.setdefault(producteurs[operation.id], []).append(operation)
    def _format_de_source(source):
        valeur = str(source or "").strip().lower()
        if valeur in ("code", "openapi", "wsdl"):
            return valeur
        if valeur in ("gateway", "apm", "runtime", "datadog", "otel", "otlp"):
            return "runtime"
        return None

    exposees = set()
    for operation in operations.values():
        format_contrat = contrats[operation.contract_id].format
        for assertion in graph.assertions:
            if (assertion.predicate == "EXPOSE" and assertion.subject == producteurs[operation.id]
                    and assertion.object in _references_operation(operation)):
                format_source = _format_de_source(assertion.source)
                if format_source is None or format_source == format_contrat:
                    exposees.add(operation.id)
                    break

    references: dict[str, Operation] = {}
    ambigues = set()
    for operation in operations.values():
        for reference in _references_operation(operation):
            existante = references.get(reference)
            if existante is not None and existante.id != operation.id:
                ambigues.add(reference)
            else:
                references[reference] = operation
    for reference in ambigues:
        references.pop(reference, None)

    aretes: dict[tuple, dict] = {}
    for assertion in graph.assertions:
        if assertion.predicate != "CONSOMME" or assertion.subject not in visibles:
            continue
        operation = _operation_citee(assertion.object, references, producteurs, operations_par_app, exposees)
        if operation is None:
            continue
        cible = producteurs[operation.id]
        libelle = f"{operation.method} {operation.path}"
        cle = (assertion.subject, cible, libelle, assertion.mode, assertion.source)
        candidate = {
            "source": assertion.subject,
            "target": cible,
            "operation_id": operation.id,
            "operation": libelle,
            "mode": assertion.mode,
            "assertion_source": assertion.source,
            "confidence": float(assertion.confidence),
            "evidence": assertion.evidence,
        }
        existante = aretes.get(cle)
        if existante is None or (candidate["confidence"], candidate["evidence"] or "", candidate["operation_id"]) > (
                existante["confidence"], existante["evidence"] or "", existante["operation_id"]):
            aretes[cle] = candidate
    return sorted(aretes.values(), key=lambda arete: (arete["source"], arete["target"], arete["operation"],
                                                      arete["mode"], arete["assertion_source"],
                                                      arete["operation_id"]))


def impacts_des_runs(runs, visibles) -> list[dict]:
    """Les impacts des runs récents, bornés aux applications visibles (run et application impactée)."""
    visibles = set(_identifiants(visibles))
    impacts = []
    for run in runs or []:
        if not isinstance(run, dict) or run.get("application_id") not in visibles:
            continue
        for impact in run.get("impacts") or []:
            if not isinstance(impact, dict) or impact.get("application") not in visibles:
                continue
            impacts.append({
                "application": impact.get("application"),
                "operation": impact.get("operation"),
                "change_type": impact.get("change_type"),
                "severity": impact.get("severity"),
                "raison": impact.get("raison") or "",
                "evidence": impact.get("evidence") or [],
                "run_id": run.get("id"),
                "at": run.get("started_at"),
            })
    return sorted(impacts, key=lambda impact: (impact["at"] or "", impact["run_id"] or "", impact["application"] or "",
                                               impact["operation"] or "", impact["change_type"] or "",
                                               impact["severity"] or ""), reverse=True)


def runs_publiques(runs, visibles) -> list[dict]:
    """La vue publique d'un DiscoveryRun, sans changements ni erreur brute."""
    visibles = set(_identifiants(visibles))
    retenus = [{
        "id": run.get("id"),
        "application_id": run.get("application_id"),
        "status": run.get("status"),
        "started_at": run.get("started_at"),
        "stats": run.get("stats") or {},
    } for run in runs or [] if isinstance(run, dict) and run.get("application_id") in visibles]
    return sorted(retenus, key=lambda run: (run["started_at"] or "", run["id"] or ""), reverse=True)


def enregistrer(conn, tenant_id, graph, remplacer=False) -> dict:
    """Upsert idempotent du graphe ; refuse un tenant vide et toute URL de binding porteuse d'un secret.

    Avec `remplacer`, le périmètre du graphe (application, environnement, formats de contrats et sources
    d'assertions) est remplacé : les opérations du même contrat/format qui ne sont plus observées et les assertions
    de la même source qui ne sont plus déclarées sont supprimées. Les autres sources (APM, config, autres formats)
    restent intactes.
    """
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
        if remplacer:
            formats = sorted({contrat.format for contrat in graph.contracts})
            sources = {assertion.source for assertion in graph.assertions}
            if any(contrat.format == "code" for contrat in graph.contracts):
                sources.add("code")
            if any(contrat.format == "openapi" for contrat in graph.contracts):
                sources.add("openapi")
            applications = sorted({contrat.application_id for contrat in graph.contracts}
                                  | {assertion.subject for assertion in graph.assertions})
            environnements = sorted({contrat.environment for contrat in graph.contracts}
                                    | {assertion.environment for assertion in graph.assertions})
            if formats:
                conn.execute(
                    "DELETE FROM interface_operation WHERE tenant_id = %s AND contract_id IN "
                    "(SELECT id FROM interface_contract WHERE tenant_id = %s AND application_id = ANY(%s) "
                    "AND environment = ANY(%s) AND format = ANY(%s))",
                    (tenant, tenant, applications, environnements, formats))
                conn.execute(
                    "DELETE FROM interface_contract WHERE tenant_id = %s AND application_id = ANY(%s) "
                    "AND environment = ANY(%s) AND format = ANY(%s) AND NOT (id = ANY(%s))",
                    (tenant, applications, environnements, formats, [contrat.id for contrat in graph.contracts]))
            if sources:
                conn.execute(
                    "DELETE FROM interface_assertion WHERE tenant_id = %s AND subject = ANY(%s) "
                    "AND environment = ANY(%s) AND source = ANY(%s)",
                    (tenant, applications, environnements, sorted(sources)))
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


def _objet(classe, ligne, champs):
    return classe(**{champ: _valeur(ligne.get(champ)) for champ in champs})


def tenants_pour(conn, application_ids) -> list[str]:
    """Les tenants Postgres distincts des applications demandées, triés (pour refuser tout mélange)."""
    identifiants = _identifiants(application_ids)
    if not identifiants:
        return []
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT tenant_id FROM jumeau WHERE id = ANY(%s) ORDER BY tenant_id",
                    (identifiants,))
        return [ligne[0] for ligne in cur.fetchall()]


def derniers_runs(conn, tenant_id, application_id=None, limite=20) -> list[dict]:
    """Les derniers DiscoveryRun d'un tenant/application, du plus récent au plus ancien."""
    tenant = _tenant(tenant_id)
    with conn.cursor(row_factory=dict_row) as cur:
        if application_id is None:
            cur.execute("SELECT * FROM discovery_run WHERE tenant_id = %s ORDER BY started_at DESC LIMIT %s",
                        (tenant, max(1, min(int(limite), 100))))
        else:
            cur.execute("SELECT * FROM discovery_run WHERE tenant_id = %s AND application_id = %s "
                        "ORDER BY started_at DESC LIMIT %s",
                        (tenant, application_id, max(1, min(int(limite), 100))))
        return [_ligne(ligne) for ligne in cur.fetchall()]


def derniers_runs_pour(conn, tenant_id, application_ids, limite=20) -> list[dict]:
    """Les derniers runs de chaque application visible, avec au plus `limite` runs par application."""
    tenant = _tenant(tenant_id)
    identifiants = _identifiants(application_ids)
    if not identifiants:
        return []
    limite = max(1, min(int(limite), 100))
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT id, tenant_id, application_id, source, environment, started_at, ended_at, status, stats, "
            "changes, impacts, error FROM ("
            "SELECT *, row_number() OVER (PARTITION BY application_id ORDER BY started_at DESC, id DESC) AS rang "
            "FROM discovery_run WHERE tenant_id = %s AND application_id = ANY(%s)"
            ") AS runs WHERE rang <= %s ORDER BY started_at DESC, application_id, id",
            (tenant, identifiants, limite))
        return [_ligne(ligne) for ligne in cur.fetchall()]


def lire_graph(conn, tenant_id, application_id=None) -> InterfaceGraph:
    """Relit un graphe d'interfaces en objets typés, filtré par tenant puis, si fourni, par application.

    L'application filtre les contrats (`application_id`) et les assertions (`subject`). Les opérations suivent leurs
    contrats ; les bindings sont retenus par l'URL citée dans une assertion ou par l'environnement du contrat, comme
    dans `lire`. Les `Decimal` et les dates redeviennent des `float` et des chaînes ISO. Le caractère partiel d'un run
    n'étant pas persisté sur ces tables, il est rendu à `False` : l'état du run vit dans `discovery_run`.
    """
    tenant = _tenant(tenant_id)
    with conn.cursor(row_factory=dict_row) as cur:
        if application_id is None:
            cur.execute("SELECT * FROM interface_contract WHERE tenant_id = %s ORDER BY application_id, id",
                        (tenant,))
        else:
            cur.execute("SELECT * FROM interface_contract WHERE tenant_id = %s AND application_id = %s "
                        "ORDER BY application_id, id", (tenant, application_id))
        contracts = [_objet(Contract, ligne, _CHAMPS_CONTRACT) for ligne in cur.fetchall()]

        contrats = sorted({contrat.id for contrat in contracts})
        if contrats:
            cur.execute("SELECT * FROM interface_operation WHERE tenant_id = %s AND contract_id = ANY(%s) "
                        "ORDER BY contract_id, method, path, id", (tenant, contrats))
        else:
            cur.execute("SELECT * FROM interface_operation WHERE tenant_id = %s AND false", (tenant,))
        operations = [_objet(Operation, ligne, _CHAMPS_OPERATION) for ligne in cur.fetchall()]

        if application_id is None:
            cur.execute("SELECT * FROM interface_assertion WHERE tenant_id = %s "
                        "ORDER BY subject, predicate, object, id", (tenant,))
        else:
            cur.execute("SELECT * FROM interface_assertion WHERE tenant_id = %s AND subject = %s "
                        "ORDER BY subject, predicate, object, id", (tenant, application_id))
        assertions = [_objet(Assertion, ligne, _CHAMPS_ASSERTION) for ligne in cur.fetchall()]

        if application_id is None:
            cur.execute("SELECT * FROM interface_binding WHERE tenant_id = %s ORDER BY environment, url, id",
                        (tenant,))
        else:
            objets = sorted({assertion.object for assertion in assertions})
            environnements = sorted({assertion.environment for assertion in assertions}
                                    | {contrat.environment for contrat in contracts})
            cur.execute("SELECT * FROM interface_binding WHERE tenant_id = %s "
                        "AND (url = ANY(%s) OR environment = ANY(%s)) ORDER BY environment, url, id",
                        (tenant, objets, environnements))
        bindings = [_objet(Binding, ligne, _CHAMPS_BINDING) for ligne in cur.fetchall()]

    return InterfaceGraph(contracts=contracts, operations=operations, bindings=bindings, assertions=assertions)


def lire_graph_pour(conn, tenant_id, application_ids) -> InterfaceGraph:
    """Relit le graphe des seules applications demandées (contrats, opérations et assertions).

    Les bindings ne sont pas chargés : la vue Mesh n'en expose aucun. Une application hors liste ne peut donc
    entrer ni comme source d'assertion, ni comme productrice d'opération.
    """
    tenant = _tenant(tenant_id)
    identifiants = _identifiants(application_ids)
    if not identifiants:
        return InterfaceGraph()
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM interface_contract WHERE tenant_id = %s AND application_id = ANY(%s) "
                    "ORDER BY application_id, id", (tenant, identifiants))
        contracts = [_objet(Contract, ligne, _CHAMPS_CONTRACT) for ligne in cur.fetchall()]

        contrats = sorted({contrat.id for contrat in contracts})
        if contrats:
            cur.execute("SELECT * FROM interface_operation WHERE tenant_id = %s AND contract_id = ANY(%s) "
                        "ORDER BY contract_id, method, path, id", (tenant, contrats))
        else:
            cur.execute("SELECT * FROM interface_operation WHERE tenant_id = %s AND false", (tenant,))
        operations = [_objet(Operation, ligne, _CHAMPS_OPERATION) for ligne in cur.fetchall()]

        cur.execute("SELECT * FROM interface_assertion WHERE tenant_id = %s AND subject = ANY(%s) "
                    "ORDER BY subject, predicate, object, id", (tenant, identifiants))
        assertions = [_objet(Assertion, ligne, _CHAMPS_ASSERTION) for ligne in cur.fetchall()]

    return InterfaceGraph(contracts=contracts, operations=operations, assertions=assertions)
