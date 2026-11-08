"""D8 : le Twin comme projection calculée de ses claims.

L'état du Twin n'est plus une ligne stockée qui peut diverger : il se déduit des
faits. ``jumeau`` reste la source d'identité (id, nom, équipe, type, tenant) ;
tout le reste — capacités réalisées, dépendances et dépendants, couverture de
compréhension, fraîcheur des preuves, état épistémique, contradictions — se
calcule depuis ``claim``, ``claim_preuve``, ``preuve`` et ``contradiction``,
borné, déterministe et strictement dans le tenant.

Un claim « confirmé » fait foi dans la projection : statut ``ACCEPTED`` (revue
humaine) ou mode ``CONFIRMED``, encore valide (``valide_jusqua IS NULL``) — la
même règle de lecture que le détecteur d'opportunités (D6). Les claims contestés
ou invalidés ne disparaissent pas : ils pèsent dans ``etat_epistemique`` et dans
``couverture``, jamais dans les listes de capacités ou de dépendances.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from psycopg.rows import dict_row

from meridian.domain import comprehension

__all__ = [
    "PREDICAT_CAPACITE",
    "PREDICATS_DEPENDANCE",
    "PREDICATS_IDENTITE",
    "LIMITE_TWINS_DEFAUT",
    "ProjectionInvalide",
    "projeter",
    "projection_tous",
    "ecarts",
]

# « Ce que le twin sait faire » : même prédicat que comprehension.QUESTIONS (question « sert »).
PREDICAT_CAPACITE = "REALISE_CAPACITE"

# Arêtes « je dépends de / j'appelle » — même liste que detecteur_opportunites.PREDICATS_DEPENDANCE.
PREDICATS_DEPENDANCE = ("DEPEND_DE", "DECLARE_DEPENDANCE", "APPELLE")

# Prédicats qui affirment un attribut déductible du twin, l'``objet`` portant la valeur.
# Quand un tel claim est confirmé, l'attribut stocké de ``jumeau`` n'est plus la vérité ;
# ``ecarts`` confronte les deux. nom et equipe ne figurent pas ici : identité, pas déduction.
PREDICATS_IDENTITE = {
    "A_POUR_TYPE": "type",
    "APPARTIENT_A_DOMAINE": "domaine",
    "A_POUR_MISSION": "mission",
}

LIMITE_TWINS_DEFAUT = 500
_LIMITE_CLAIMS = 5000
_LIMITE_LOCATORS = 20000
_LIMITE_CONTRADICTIONS = 1000

# Champs de la ligne ``jumeau`` rendus dans la vue : l'identité stockée, qui fait foi.
_CHAMPS_IDENTITE = (
    "id", "tenant_id", "nom", "equipe", "type", "domaine", "mission",
    "application_id", "perimetre", "perimetre_id", "cree_le",
)
# Champs confrontés par ``ecarts`` : attributs déductibles, jamais l'identité.
_CHAMPS_DEDUITS = ("type", "domaine", "mission")


class ProjectionInvalide(ValueError):
    """Un paramètre de projection ne respecte pas son contrat : rien n'est lu."""


def _tenant(valeur: Any) -> str:
    texte = str(valeur or "").strip()
    if not texte:
        raise ProjectionInvalide("tenant_id obligatoire")
    return texte[:128]


def _twin_id(valeur: Any) -> str:
    texte = str(valeur or "").strip()
    if not texte:
        raise ProjectionInvalide("twin_id obligatoire")
    return texte[:256]


def _borne(valeur: Any, minimum: int = 1, maximum: int = 1000) -> int:
    if isinstance(valeur, bool):
        raise ProjectionInvalide("limite doit être un entier positif")
    try:
        nombre = int(valeur)
    except (TypeError, ValueError) as exc:
        raise ProjectionInvalide("limite doit être un entier positif") from exc
    if nombre < minimum:
        raise ProjectionInvalide("limite doit être un entier positif")
    return min(nombre, maximum)


def _jsonable(valeur: Any) -> Any:
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    if isinstance(valeur, Decimal):
        return float(valeur)
    if isinstance(valeur, Mapping):
        return {str(cle): _jsonable(element) for cle, element in valeur.items()}
    if isinstance(valeur, (list, tuple)):
        return [_jsonable(element) for element in valeur]
    return valeur


def _confirmee(ligne: Mapping) -> bool:
    """Un claim confirmé fait foi : revue ACCEPTED ou mode CONFIRMED."""
    return ligne.get("statut") == "ACCEPTED" or ligne.get("mode") == "CONFIRMED"


# --- Lectures bornées, tenant-scopées ---


def _lire_twins(conn: Any, tenant: str, twin_id: str | None = None,
                limite: int = LIMITE_TWINS_DEFAUT) -> list[dict]:
    """Lignes ``jumeau`` du tenant : identité stockée, dans un ordre stable (nom, id)."""
    conditions, parametres = ["tenant_id = %s"], [tenant]
    if twin_id is not None:
        conditions.append("id = %s")
        parametres.append(twin_id)
    parametres.append(limite)
    with conn.cursor(row_factory=dict_row) as cur:
        return [dict(ligne) for ligne in cur.execute(
            "SELECT " + ", ".join(_CHAMPS_IDENTITE) + " FROM jumeau WHERE "
            + " AND ".join(conditions) + " ORDER BY nom, id LIMIT %s",
            parametres).fetchall()]


def _lire_claims_valides(conn: Any, tenant: str, limite: int = _LIMITE_CLAIMS) -> list[dict]:
    """Claims valides du tenant, avec le compte de preuves SUPPORT et la plus récente."""
    with conn.cursor(row_factory=dict_row) as cur:
        return [dict(ligne) for ligne in cur.execute(
            "SELECT c.id, c.jumeau_id AS twin_id, c.sujet, c.predicat, c.objet, c.type, "
            "       c.statut, c.mode, c.maturite, c.confiance::float AS confiance, "
            "       c.valide_depuis, c.enregistre_le, "
            "       coalesce(s.preuves, 0) AS nb_preuves, s.derniere_preuve "
            "FROM claim c "
            "LEFT JOIN LATERAL ("
            "    SELECT count(*) AS preuves, max(p.observee_le) AS derniere_preuve "
            "    FROM claim_preuve cp JOIN preuve p ON p.id = cp.preuve_id "
            "    WHERE cp.claim_id = c.id AND cp.role = 'SUPPORT') s ON true "
            "WHERE c.tenant_id = %s AND c.valide_jusqua IS NULL "
            "ORDER BY c.jumeau_id, c.id LIMIT %s",
            (tenant, limite)).fetchall()]


def _lire_locators(conn: Any, tenant: str, limite: int = _LIMITE_LOCATORS) -> dict:
    """claim_id → localisateurs des preuves SUPPORT des claims valides du tenant."""
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            "SELECT cp.claim_id, p.locator FROM claim_preuve cp "
            "JOIN preuve p ON p.id = cp.preuve_id "
            "JOIN claim c ON c.id = cp.claim_id "
            "WHERE c.tenant_id = %s AND c.valide_jusqua IS NULL AND cp.role = 'SUPPORT' "
            "ORDER BY cp.claim_id, p.id LIMIT %s",
            (tenant, limite)).fetchall()
    locators: dict[int, list[str]] = {}
    for ligne in lignes:
        locators.setdefault(int(ligne["claim_id"]), []).append(str(ligne["locator"]))
    return locators


def _lire_contradictions(conn: Any, tenant: str,
                         limite: int = _LIMITE_CONTRADICTIONS) -> dict:
    """jumeau_id → contradictions OUVERTES : total (borné) et ids des claims visés."""
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            "SELECT id, jumeau_id, claim_id FROM contradiction "
            "WHERE tenant_id = %s AND statut = 'OUVERTE' "
            "ORDER BY jumeau_id, id LIMIT %s",
            (tenant, limite)).fetchall()
    ouvertes: dict[str, dict] = {}
    for ligne in lignes:
        entree = ouvertes.setdefault(str(ligne["jumeau_id"]), {"total": 0, "claim_ids": set()})
        entree["total"] += 1
        if ligne["claim_id"] is not None:
            entree["claim_ids"].add(int(ligne["claim_id"]))
    return ouvertes


def _noms(conn: Any, tenant: str) -> dict[str, str]:
    """id → nom de chaque twin du tenant, pour résoudre les dépendances sans re-jointer."""
    with conn.cursor(row_factory=dict_row) as cur:
        return {str(ligne["id"]): str(ligne["nom"]) for ligne in cur.execute(
            "SELECT id, nom FROM jumeau WHERE tenant_id = %s ORDER BY id", (tenant,))}


# --- Assemblage ---


def _etat_epistemique(claims: list[dict], contradictions_ouvertes: int) -> dict:
    """Résumé épistémique déterministe : comptes par statut, confiance et maturité."""
    par_statut: dict[str, int] = {}
    confiances: list[float] = []
    maturite_max: str | None = None
    for claim in claims:
        statut = str(claim.get("statut") or "")
        par_statut[statut] = par_statut.get(statut, 0) + 1
        if claim.get("confiance") is not None:
            confiances.append(float(claim["confiance"]))
        maturite = str(claim.get("maturite") or "")
        if len(maturite) == 2 and maturite[0] == "M" and maturite[1].isdigit():
            if maturite_max is None or maturite > maturite_max:
                maturite_max = maturite
    total = len(claims)
    if total == 0:
        label = "INCONNU"
    elif contradictions_ouvertes > 0 or par_statut.get("CONTESTED"):
        label = "CONTESTE"
    elif par_statut.keys() == {"ACCEPTED"}:
        label = "CONSOLIDE"
    else:
        label = "EN_PROPOSITION"
    return {
        "claims_valides": total,
        "par_statut": {cle: par_statut[cle] for cle in sorted(par_statut)},
        "confiance_moyenne": round(sum(confiances) / len(confiances), 3) if confiances else None,
        "maturite_max": maturite_max,
        "label": label,
    }


def _couverture(claims: list[dict], claim_ids_contredits: set) -> dict:
    """Couverture des sept questions de compréhension, déduite des claims valides.

    Une question est ``contradicted`` si l'un de ses claims est visé par une
    contradiction ouverte — la règle de ``comprehension.statut_question``,
    appliquée question par question (une contradiction n'en contredit qu'une).
    """
    statuts = []
    for cle, _titre, predicat, _type in comprehension.QUESTIONS:
        ids_question = {int(c["id"]) for c in claims
                        if str(c.get("predicat") or "").upper() == (predicat or "")}
        visees = [claim_id for claim_id in sorted(claim_ids_contredits) if claim_id in ids_question]
        statuts.append(comprehension.statut_question(cle, claims, visees))
    bilan = comprehension.couverture(statuts)
    bilan["questions"] = {statut.cle: statut.statut for statut in statuts}
    return bilan


def _projection(twin: Mapping, claims: list[dict], contradictions: dict,
                noms: Mapping[str, str]) -> dict:
    """La vue calculée d'un twin : tout se déduit des claims, rien n'est stocké."""
    confirmes = [c for c in claims if _confirmee(c)]
    capacites = [
        {"claim_id": int(c["id"]), "objet": str(c["objet"]),
         "confiance": float(c["confiance"]) if c.get("confiance") is not None else None,
         "maturite": c.get("maturite"), "preuves": int(c.get("nb_preuves") or 0)}
        for c in confirmes if str(c.get("predicat") or "").upper() == PREDICAT_CAPACITE
    ]
    dependances = []
    for c in confirmes:
        if str(c.get("predicat") or "").upper() not in PREDICATS_DEPENDANCE:
            continue
        objet = str(c["objet"])
        entree = {"claim_id": int(c["id"]), "predicat": str(c["predicat"]), "objet": objet}
        if objet in noms and objet != twin["id"]:
            entree["twin"] = {"id": objet, "nom": noms[objet]}
        dependances.append(entree)
    dependants = []
    # Les dépendants ne se déduisent pas des claims du twin mais des claims des
    # autres twins qui le citent — calculés par l'appelant via ``_dependants``.
    fraicheur = max(
        (c["derniere_preuve"] for c in claims if c.get("derniere_preuve") is not None),
        default=None,
    )
    ouvertes = contradictions.get(str(twin["id"]), {"total": 0, "claim_ids": set()})
    return {
        "twin_id": str(twin["id"]),
        "identite": _jsonable({cle: twin.get(cle) for cle in _CHAMPS_IDENTITE}),
        "capacites": capacites,
        "dependances": dependances,
        "dependants": dependants,
        "couverture": _couverture(claims, ouvertes["claim_ids"]),
        "fraicheur_derniere_preuve": _jsonable(fraicheur),
        "etat_epistemique": _etat_epistemique(claims, int(ouvertes["total"])),
        "contradictions_ouvertes": int(ouvertes["total"]),
    }


def _dependants(claims: list[dict], noms: Mapping[str, str]) -> dict[str, list]:
    """twin_id → claims confirmés de dépendance des autres twins qui le citent."""
    par_cible: dict[str, list] = {}
    for c in claims:
        if not _confirmee(c) or str(c.get("predicat") or "").upper() not in PREDICATS_DEPENDANCE:
            continue
        cible = str(c["objet"])
        source = str(c["twin_id"])
        if cible == source or cible not in noms:
            continue
        par_cible.setdefault(cible, []).append({
            "claim_id": int(c["id"]), "predicat": str(c["predicat"]),
            "twin": {"id": source, "nom": noms.get(source, source)},
        })
    for entrees in par_cible.values():
        entrees.sort(key=lambda e: (e["twin"]["id"], e["claim_id"]))
    return par_cible


def _vue_tous(conn: Any, tenant: str, twins: list[dict]) -> list[dict]:
    """Assemble la projection de chaque twin : lectures bornées par tenant, jamais N requêtes."""
    claims = _lire_claims_valides(conn, tenant)
    locators = _lire_locators(conn, tenant)
    contradictions = _lire_contradictions(conn, tenant)
    noms = _noms(conn, tenant)
    dependants = _dependants(claims, noms)
    par_twin: dict[str, list] = {}
    for claim in claims:
        par_twin.setdefault(str(claim["twin_id"]), []).append(claim)
    vues = []
    for twin in twins:
        claims_twin = []
        for claim in par_twin.get(str(twin["id"]), []):
            # comprehension._preuves_de attend des mappings avec ``locator``.
            claims_twin.append({
                **claim,
                "preuves": [{"locator": loc}
                            for loc in locators.get(int(claim["id"]), [])],
            })
        vue = _projection(twin, claims_twin, contradictions, noms)
        vue["dependants"] = dependants.get(str(twin["id"]), [])
        vues.append(vue)
    return vues


def projeter(conn: Any, tenant_id: Any, twin_id: Any) -> dict | None:
    """La projection calculée d'un twin du tenant ; ``None`` s'il est inconnu du tenant.

    ``{capacites[], dependances[], dependants[], couverture,
    fraicheur_derniere_preuve, etat_epistemique, contradictions_ouvertes}`` —
    l'``identite`` jointe vient de ``jumeau`` (nom, équipe, type : la source
    reste la ligne stockée), tout le reste est déduit des claims.
    """
    tenant = _tenant(tenant_id)
    jid = _twin_id(twin_id)
    twins = _lire_twins(conn, tenant, jid, limite=1)
    if not twins:
        return None
    return _vue_tous(conn, tenant, twins)[0]


def projection_tous(conn: Any, tenant_id: Any, limite: Any = LIMITE_TWINS_DEFAUT) -> list[dict]:
    """La même vue pour tous les twins du tenant, bornée à ``limite``, pour le tableau."""
    tenant = _tenant(tenant_id)
    twins = _lire_twins(conn, tenant, limite=_borne(limite, maximum=1000))
    return _vue_tous(conn, tenant, twins)


def ecarts(conn: Any, tenant_id: Any, twin_id: Any) -> dict | None:
    """Où la ligne ``jumeau`` diverge de la projection : le stocké n'est plus la vérité.

    ``stocke`` rend les attributs déductibles lus dans ``jumeau`` ; ``calcule``
    rend ce que les claims confirmés affirment des mêmes attributs
    (``PREDICATS_IDENTITE``) et le ``sujet`` porté par les claims — une copie
    dénormalisée du nom, qui peut diverger après un renommage. ``divergence``
    énumère les champs où les deux côtés ont un avis et ne sont pas d'accord ;
    un champ sans claim confirmé n'est jamais une divergence (le stocké reste
    faute de mieux).
    """
    tenant = _tenant(tenant_id)
    jid = _twin_id(twin_id)
    twins = _lire_twins(conn, tenant, jid, limite=1)
    if not twins:
        return None
    twin = twins[0]
    claims = _lire_claims_valides(conn, tenant)
    claims_twin = [c for c in claims if str(c["twin_id"]) == jid]

    stocke = {champ: twin.get(champ) for champ in _CHAMPS_DEDUITS}
    calcule: dict[str, Any] = {}
    divergence = []
    for predicat, champ in sorted(PREDICATS_IDENTITE.items()):
        confirmes = [c for c in claims_twin if _confirmee(c)
                     and str(c.get("predicat") or "").upper() == predicat]
        if not confirmes:
            continue
        # Déterministe : le claim confirmé le plus récent (id max) fait foi.
        claim = max(confirmes, key=lambda c: int(c["id"]))
        valeur = str(claim["objet"])
        calcule[champ] = valeur
        if stocke.get(champ) != valeur:
            divergence.append({
                "champ": champ, "stocke": stocke.get(champ),
                "calcule": valeur, "claim_id": int(claim["id"]),
            })
    sujets = sorted({str(c["sujet"]) for c in claims_twin if str(c.get("sujet") or "")})
    calcule["sujet"] = sujets
    nom = str(twin.get("nom") or "")
    if sujets and any(sujet != nom for sujet in sujets):
        divergence.append({
            "champ": "sujet", "stocke": nom,
            "calcule": [sujet for sujet in sujets if sujet != nom],
            "claim_id": None,
        })
    return {
        "twin_id": jid,
        "stocke": _jsonable(stocke),
        "calcule": _jsonable(calcule),
        "divergence": divergence,
    }
