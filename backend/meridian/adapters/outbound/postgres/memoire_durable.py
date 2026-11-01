"""Mémoire durable par tenant : portée, consentement, rétention, export et suppression.

Cette couche conserve les souvenirs opérationnels d'un utilisateur, d'une session,
d'un Twin ou d'une situation. Elle ne remplace ni ``memoire_org`` (annotation
organisationnelle) ni les Claims (mémoire sémantique) : elle porte le souvenir
durable avec sa portée, sa provenance, son consentement et son expiration.

Toute lecture et toute écriture est bornée au tenant. Les secrets bruts sont
refusés à l'écriture (clés sensibles et jetons dans le texte) et retirés à
l'export. La rétention est explicite : ``creer`` pose une expiration à 30 jours
par défaut et ``purger`` supprime les entrées échues ; ``chercher`` ignore les
entrées échues en attendant leur purge, tandis que ``lire``, ``lister`` et
``exporter`` les montrent encore pour l'administration et la portabilité.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import json
import math
import re
import unicodedata
import uuid
from urllib.parse import parse_qsl, unquote_plus, urlsplit

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from meridian.domain import tenant as tenant_module

__all__ = [
    "CLASSES",
    "DUREE_CONSERVATION",
    "MemoireDurableInvalide",
    "SCOPES",
    "SCOPE_USER",
    "chercher",
    "consentir",
    "creer",
    "exporter",
    "lire",
    "lister",
    "purger",
    "supprimer",
]

SCOPES = ("user", "session", "twin", "situation")
CLASSES = ("session", "preference", "contexte", "decision", "apprentissage")
SCOPE_USER = "user"
DUREE_CONSERVATION = timedelta(days=30)

_CHAMPS = (
    "id", "tenant_id", "scope", "scope_id", "classe", "contenu", "provenance",
    "consentement", "consenti_le", "expire_le", "confiance", "donnees", "cree_le", "maj_le",
)
_SELECT = ", ".join(_CHAMPS)
_INSERT = (
    f"INSERT INTO memoire_durable ({_SELECT}) "
    f"VALUES ({', '.join(['%s'] * len(_CHAMPS))}) "
    "ON CONFLICT (tenant_id, id) DO NOTHING "
    f"RETURNING {_SELECT}"
)
_MAX_LECTURE = 1000
_MAX_CANDIDATS = 1000
_TAILLE_MAX_ID = 128
_TAILLE_MAX_PROVENANCE = 4000

_MARQUEURS_SECRETS = ("password", "passwd", "secret", "token", "credential", "authorization")
_CLES_SECRETES = frozenset({
    "pwd", "pass", "auth", "key", "apikey", "api_key", "api-key", "access_key", "accesskey",
    "private_key", "privatekey", "client_secret", "clientsecret", "bearer", "password", "passwd",
})
_RE_AFFECTATION_SENSIBLE = re.compile(
    r"(?i)(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|client[_-]?secret|"
    r"password|passwd|mot[\s_-]*de[\s_-]*passe|secret|token)\s*[:=]\s*['\"]?[A-Za-z0-9_./+~-]{6,}"
)
_RE_JETON_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_.~+/=-]{12,}")
_RE_URL = re.compile(r"(?i)^[a-z][a-z0-9+.\-]*://")
_RE_URL_IDENTIFIANTS = re.compile(r"(?i)\b[a-z][a-z0-9+.\-]*://[^/\s:@]+:[^/\s@]*@")


class MemoireDurableInvalide(ValueError):
    """Une entrée de mémoire durable ne respecte pas son contrat."""


def _tenant(tenant_id) -> str:
    try:
        return tenant_module.exiger_tenant(tenant_id).id
    except tenant_module.TenantError as exc:
        raise MemoireDurableInvalide(str(exc)) from exc


def _texte(valeur) -> str:
    return "" if valeur is None else str(valeur).strip()


def _texte_obligatoire(valeur, champ: str) -> str:
    texte = _texte(valeur)
    if not texte:
        raise MemoireDurableInvalide(f"{champ} obligatoire")
    _verifier_sans_secret(texte, champ)
    return texte


def _valeur_fermee(valeur, champ: str, valeurs) -> str:
    texte = _texte_obligatoire(valeur, champ).lower()
    if texte not in valeurs:
        raise MemoireDurableInvalide(
            f"{champ} inconnu : {valeur!r} (attendus : {', '.join(valeurs)})"
        )
    return texte


def _consentement(valeur) -> bool:
    if valeur is None:
        return False
    if isinstance(valeur, bool):
        return valeur
    if isinstance(valeur, int) and valeur in (0, 1):
        return bool(valeur)
    raise MemoireDurableInvalide("consentement doit être un booléen")


def _confiance(valeur) -> float:
    if isinstance(valeur, bool):
        raise MemoireDurableInvalide("confiance doit être un nombre entre 0 et 1")
    try:
        nombre = float(valeur)
    except (TypeError, ValueError) as exc:
        raise MemoireDurableInvalide("confiance doit être un nombre entre 0 et 1") from exc
    if not math.isfinite(nombre) or not 0.0 <= nombre <= 1.0:
        raise MemoireDurableInvalide("confiance doit être comprise entre 0 et 1")
    return nombre


def _limite(valeur, maximum: int = _MAX_LECTURE) -> int:
    if isinstance(valeur, bool):
        raise MemoireDurableInvalide("limite doit être un entier positif")
    try:
        borne = int(valeur)
    except (TypeError, ValueError) as exc:
        raise MemoireDurableInvalide("limite doit être un entier positif") from exc
    return max(1, min(borne, maximum))


def _instant(valeur, champ: str, defaut=None):
    if valeur is None:
        return defaut
    if isinstance(valeur, datetime):
        instant = valeur
    elif isinstance(valeur, date):
        instant = datetime.combine(valeur, time.min)
    elif isinstance(valeur, str):
        texte = valeur.strip()
        if not texte:
            return defaut
        try:
            instant = datetime.fromisoformat(texte.replace("Z", "+00:00"))
        except ValueError as exc:
            raise MemoireDurableInvalide(f"{champ} doit être une date ISO") from exc
    else:
        raise MemoireDurableInvalide(f"{champ} doit être une date ISO")
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant


def _cle_sensible(cle) -> bool:
    normalisee = unquote_plus(str(cle)).strip().lower()
    if normalisee.endswith(("_ref", "-ref", "_reference", "-reference")):
        return False
    compacte = normalisee.replace("-", "_")
    if compacte in _CLES_SECRETES:
        return True
    if compacte.endswith("_key"):
        return True
    return any(marque in compacte for marque in _MARQUEURS_SECRETS)


def _url_porte_un_secret(url: str) -> bool:
    try:
        parties = urlsplit(url)
    except (ValueError, UnicodeError):
        return True
    if parties.password is not None:
        return True
    if parties.username is not None or "@" in parties.netloc:
        return True
    return any(
        _cle_sensible(cle) and valeur not in ("", "***")
        for cle, valeur in parse_qsl(parties.query, keep_blank_values=True)
    )


def _verifier_sans_secret(valeur, chemin: str) -> None:
    if isinstance(valeur, Mapping):
        for cle, element in valeur.items():
            if _cle_sensible(cle) and element not in (None, "", "***"):
                raise MemoireDurableInvalide(f"{chemin} : clé sensible refusée ({cle})")
            _verifier_sans_secret(element, f"{chemin}.{cle}")
    elif isinstance(valeur, (list, tuple)):
        for rang, element in enumerate(valeur):
            _verifier_sans_secret(element, f"{chemin}[{rang}]")
    elif isinstance(valeur, str):
        if (_RE_AFFECTATION_SENSIBLE.search(valeur) or _RE_JETON_BEARER.search(valeur)
                or _RE_URL_IDENTIFIANTS.search(valeur)):
            raise MemoireDurableInvalide(f"{chemin} : secret détecté")
        if _RE_URL.match(valeur) and _url_porte_un_secret(valeur):
            raise MemoireDurableInvalide(f"{chemin} : URL ou secret refusé")


def _donnees_json(valeur):
    if valeur is None:
        return {}
    if not isinstance(valeur, (Mapping, list, tuple, str, int, float, bool)):
        raise MemoireDurableInvalide("donnees doit être une valeur JSON")
    _verifier_sans_secret(valeur, "donnees")
    try:
        return json.loads(json.dumps(valeur, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise MemoireDurableInvalide("donnees non sérialisables en JSON") from exc


def _valeur(valeur):
    if isinstance(valeur, Decimal):
        return float(valeur)
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    return valeur


def _ligne(ligne) -> dict:
    return {cle: _valeur(ligne[cle]) for cle in _CHAMPS if cle in ligne}


def _normaliser_texte(valeur) -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c)).lower()
    texte = "".join(c if c.isalnum() else " " for c in texte)
    return " ".join(texte.split())


def _horodatage(valeur) -> float:
    if isinstance(valeur, datetime):
        instant = valeur
    elif isinstance(valeur, str):
        try:
            instant = datetime.fromisoformat(valeur.replace("Z", "+00:00"))
        except ValueError:
            return 0.0
    else:
        return 0.0
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.timestamp()


def _rediger(valeur):
    if isinstance(valeur, Mapping):
        return {
            str(cle): _rediger(element)
            for cle, element in valeur.items()
            if not _cle_sensible(cle)
        }
    if isinstance(valeur, (list, tuple)):
        return [_rediger(element) for element in valeur]
    if isinstance(valeur, str):
        texte = _RE_AFFECTATION_SENSIBLE.sub("[secret]", valeur)
        texte = _RE_JETON_BEARER.sub("[secret]", texte)
        texte = _RE_URL_IDENTIFIANTS.sub("[secret]", texte)
        if _RE_URL.match(texte) and _url_porte_un_secret(texte):
            return "[url refusée]"
        return texte
    return _valeur(valeur)


def _conditions(tenant: str, scope=None, scope_id=None, classe=None) -> tuple[list[str], list]:
    conditions, parametres = ["tenant_id = %s"], [tenant]
    if scope is not None:
        conditions.append("scope = %s")
        parametres.append(_valeur_fermee(scope, "scope", SCOPES))
    if scope_id is not None:
        conditions.append("scope_id = %s")
        parametres.append(_texte_obligatoire(scope_id, "scope_id"))
    if classe is not None:
        conditions.append("classe = %s")
        parametres.append(_valeur_fermee(classe, "classe", CLASSES))
    return conditions, parametres


def creer(
    conn, tenant_id, *, id=None, scope, scope_id, classe, contenu, provenance,
    consentement=False, confiance=0.5, expire_le=None, donnees=None,
) -> dict:
    """Crée une entrée de mémoire durable et rend la ligne stockée.

    ``id`` est conservé s'il est fourni, sinon un identifiant UUID stable est
    généré. Le scope ``user`` exige un consentement explicite (``consentement``
    vrai), daté à la création. L'expiration vaut maintenant + 30 jours par défaut
    et ne peut pas être passée. Un identifiant déjà présent pour le même tenant
    est refusé sans écraser l'entrée existante ; le même identifiant reste
    disponible dans un autre tenant.
    """
    tenant = _tenant(tenant_id)
    maintenant = datetime.now(timezone.utc)
    identifiant = f"memoire-{uuid.uuid4().hex}" if id is None else _texte_obligatoire(id, "id")
    if len(identifiant) > _TAILLE_MAX_ID:
        raise MemoireDurableInvalide(f"id : {_TAILLE_MAX_ID} caractères au maximum")

    scope_propre = _valeur_fermee(scope, "scope", SCOPES)
    scope_id_propre = _texte_obligatoire(scope_id, "scope_id")
    classe_propre = _valeur_fermee(classe, "classe", CLASSES)
    contenu_propre = _texte_obligatoire(contenu, "contenu")
    provenance_propre = _texte_obligatoire(provenance, "provenance")
    consentement_propre = _consentement(consentement)
    if scope_propre == SCOPE_USER and not consentement_propre:
        raise MemoireDurableInvalide("scope user : consentement explicite requis")
    confiance_propre = _confiance(confiance)

    expiration = _instant(expire_le, "expire_le", defaut=maintenant + DUREE_CONSERVATION)
    if expiration <= maintenant:
        raise MemoireDurableInvalide("expire_le ne peut pas être passée")
    consenti_le = maintenant if consentement_propre else None
    donnees_propres = _donnees_json(donnees)

    parametres = (
        identifiant, tenant, scope_propre, scope_id_propre, classe_propre, contenu_propre,
        provenance_propre, consentement_propre, consenti_le, expiration, confiance_propre,
        Jsonb(donnees_propres), maintenant, maintenant,
    )
    with conn.cursor(row_factory=dict_row) as cur:
        ligne = cur.execute(_INSERT, parametres).fetchone()
    if ligne is None:
        raise MemoireDurableInvalide(
            f"memoire {identifiant} existe déjà pour le tenant {tenant} ; l'écrasement est refusé"
        )
    return _ligne(ligne)


def lire(conn, tenant_id, id) -> dict | None:
    """Lit une entrée du tenant ; ``None`` si elle est absente ou dans un autre tenant."""
    tenant = _tenant(tenant_id)
    identifiant = _texte_obligatoire(id, "id")
    with conn.cursor(row_factory=dict_row) as cur:
        ligne = cur.execute(
            f"SELECT {_SELECT} FROM memoire_durable WHERE tenant_id = %s AND id = %s",
            (tenant, identifiant),
        ).fetchone()
    return _ligne(ligne) if ligne is not None else None


def lister(
    conn, tenant_id, *, scope=None, scope_id=None, classe=None, limite=200,
) -> list[dict]:
    """Liste les entrées du tenant, filtrées et bornées, de la plus récente à la plus ancienne.

    Les entrées échues restent visibles ici tant qu'elles n'ont pas été purgées :
    cette vue sert à l'administration et à la vérification de la rétention.
    """
    tenant = _tenant(tenant_id)
    conditions, parametres = _conditions(tenant, scope=scope, scope_id=scope_id, classe=classe)
    parametres.append(_limite(limite))
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            f"SELECT {_SELECT} FROM memoire_durable WHERE " + " AND ".join(conditions) +
            " ORDER BY cree_le DESC, id LIMIT %s",
            parametres,
        ).fetchall()
    return [_ligne(ligne) for ligne in lignes]


def _texte_recherche(ligne) -> str:
    donnees = ligne.get("donnees")
    try:
        donnees_texte = json.dumps(donnees, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        donnees_texte = str(donnees)
    return _normaliser_texte(" ".join((
        str(ligne.get("contenu") or ""),
        str(ligne.get("provenance") or ""),
        str(ligne.get("scope_id") or ""),
        str(ligne.get("classe") or ""),
        donnees_texte,
    )))


def chercher(
    conn, tenant_id, requete, *, scope=None, scope_id=None, limite=20,
) -> list[dict]:
    """Cherche lexicalement dans les entrées non échues du tenant, sans modèle ni réseau.

    La comparaison ignore accents et casse. Tous les mots utiles de la requête
    doivent être présents ; le classement privilégie la phrase exacte, puis le
    nombre d'occurrences, la confiance, la récence et l'identifiant. Une requête
    vide rend ``[]``. Les entrées dont ``expire_le`` est dépassée sont ignorées
    même si elles n'ont pas encore été purgées.
    """
    tenant = _tenant(tenant_id)
    texte = _texte(requete)
    if not texte:
        return []
    requete_normalisee = _normaliser_texte(texte)
    tokens = set(requete_normalisee.split())
    tokens_utiles = {token for token in tokens if len(token) > 2} or tokens

    conditions, parametres = _conditions(tenant, scope=scope, scope_id=scope_id)
    conditions.append("(expire_le IS NULL OR expire_le > %s)")
    parametres.append(datetime.now(timezone.utc))
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            f"SELECT {_SELECT} FROM memoire_durable WHERE " + " AND ".join(conditions) +
            " ORDER BY maj_le DESC, id LIMIT %s",
            (*parametres, _MAX_CANDIDATS),
        ).fetchall()

    classes: list[tuple] = []
    for ligne_brute in lignes:
        ligne = _ligne(ligne_brute)
        texte_ligne = _texte_recherche(ligne)
        tokens_ligne = set(texte_ligne.split())
        if tokens_utiles and not tokens_utiles.issubset(tokens_ligne):
            continue
        occurrences = sum(texte_ligne.count(token) for token in tokens_utiles)
        phrase_exacte = 1 if requete_normalisee and requete_normalisee in texte_ligne else 0
        classes.append((
            0 if phrase_exacte else 1,
            -occurrences,
            -_confiance(ligne.get("confiance") or 0.0),
            -_horodatage(ligne.get("maj_le")),
            str(ligne.get("id") or ""),
            ligne,
        ))
    classes.sort(key=lambda element: element[:-1])
    return [element[-1] for element in classes[: _limite(limite)]]


def exporter(conn, tenant_id, *, scope=None, scope_id=None) -> list[dict]:
    """Exporte les entrées du tenant, sans secret, pour la portabilité des données.

    Les entrées échues sont incluses tant qu'elles n'ont pas été purgées. Par
    défense en profondeur, les clés sensibles sont retirées et les jetons ou
    affectations de secrets sont remplacés par ``[secret]``.
    """
    tenant = _tenant(tenant_id)
    conditions, parametres = _conditions(tenant, scope=scope, scope_id=scope_id)
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            f"SELECT {_SELECT} FROM memoire_durable WHERE " + " AND ".join(conditions) +
            " ORDER BY cree_le, id",
            parametres,
        ).fetchall()
    return [_rediger(dict(ligne)) for ligne in lignes]


def supprimer(conn, tenant_id, id) -> bool:
    """Supprime une entrée du tenant ; rend ``True`` seulement si une ligne a été supprimée."""
    tenant = _tenant(tenant_id)
    identifiant = _texte_obligatoire(id, "id")
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM memoire_durable WHERE tenant_id = %s AND id = %s",
            (tenant, identifiant),
        )
        return cur.rowcount > 0


def purger(conn, tenant_id, maintenant=None) -> int:
    """Supprime les entrées échues du tenant et rend le nombre de lignes supprimées.

    ``maintenant`` permet de simuler une date de purge dans les tests ou un
    traitement différé ; par défaut, l'instant UTC courant est utilisé.
    """
    tenant = _tenant(tenant_id)
    instant = _instant(maintenant, "maintenant", defaut=datetime.now(timezone.utc))
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM memoire_durable "
            "WHERE tenant_id = %s AND expire_le IS NOT NULL AND expire_le <= %s",
            (tenant, instant),
        )
        return cur.rowcount


def consentir(conn, tenant_id, id, acteur) -> dict | None:
    """Enregistre le consentement d'une entrée et journalise l'acteur dans la provenance.

    Le consentement est idempotent : ``consenti_le`` conserve la première date et
    le nom de l'acteur n'est ajouté qu'une fois. ``None`` est rendu si l'entrée
    n'existe pas dans ce tenant ; aucun effet inter-tenant n'est possible.
    """
    tenant = _tenant(tenant_id)
    identifiant = _texte_obligatoire(id, "id")
    acteur_propre = _texte_obligatoire(acteur, "acteur")
    instant = datetime.now(timezone.utc)
    marqueur = f"consentement: {acteur_propre}"
    with conn.cursor(row_factory=dict_row) as cur:
        ligne = cur.execute(
            "UPDATE memoire_durable SET "
            "consentement = true, "
            "consenti_le = coalesce(consenti_le, %s), "
            "provenance = CASE WHEN strpos(provenance, %s) > 0 THEN provenance "
            "ELSE left(provenance || ' | ' || %s, %s) END, "
            "maj_le = %s "
            "WHERE tenant_id = %s AND id = %s "
            f"RETURNING {_SELECT}",
            (instant, marqueur, marqueur, _TAILLE_MAX_PROVENANCE, instant, tenant, identifiant),
        ).fetchone()
    return _ligne(ligne) if ligne is not None else None
