"""Création, lecture et connaissance des Twins non applicatifs.

Un Twin non applicatif (PROCESS, CAPABILITY, JOURNEY, ORGANIZATION, PRODUCT, DATA_DOMAIN) vit dans la table
`jumeau`, comme une application : même identité, même tenant, mêmes Claims. Ce module ne crée aucune table et ne
change pas le modèle « 1 Twin ↔ 1 entité » ; il ajoute seulement une porte d'écriture explicite pour les types qui
n'étaient jusqu'ici créés que par l'ingestion ou la promotion.

Une application est normalement créée par les flux d'identité existants (`depot.enregistrer`, `depot.creer_jumeau`)
puis promue par `identite_depot.promouvoir`. `creer_twin` tolère la création d'une APPLICATION uniquement lorsque
l'identifiant est encore absent ; il ne transforme jamais une APPLICATION existante en un autre type et ne transforme
jamais un autre Twin en APPLICATION.

Les Claims sont écrits par l'API publique de `depot` (`enregistrer_proposition`) : tout Claim porte une preuve
immuable et un mode de connaissance validé par `modele_entreprise`. Aucun secret brut n'est accepté.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
import math
import re
import unicodedata
from urllib.parse import parse_qsl, unquote_plus, urlsplit

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from jumeau import depot
from jumeau.modele_entreprise import MODES, TYPES_TWIN

__all__ = [
    "TwinInvalide",
    "TwinIntrouvable",
    "TwinTenantRefuse",
    "creer_twin",
    "lire_twin",
    "lister_twins",
    "creer_claim",
    "claims_du_twin",
]

ACTION_CREATION = "creation_twin"
TYPES_SOURCE = frozenset({"GIT", "DOCUMENTATION", "CONFLUENCE", "JIRA", "SERVICENOW", "DATADOG", "OTLP"})

_MARQUEURS_SECRETS = ("password", "passwd", "secret", "token", "credential", "authorization")
_CLES_SECRETES = frozenset({
    "pwd", "pass", "auth", "key", "apikey", "api_key", "api-key", "access_key", "accesskey",
    "private_key", "privatekey", "client_secret", "clientsecret", "bearer", "password", "passwd",
})
_SCHEMES_IDENTIFIANTS = frozenset({
    "git", "declaration", "confluence", "jira", "servicenow", "datadog", "otlp",
})

_CHAMPS_CLAIM = """
SELECT c.id, c.tenant_id, c.jumeau_id AS twin_id, c.sujet, c.predicat, c.objet, c.type,
       c.statut, c.maturite, c.mode, c.confiance::float AS confiance, c.valide_depuis,
       c.enregistre_le, c.origine, c.version,
       (SELECT coalesce(json_agg(json_build_object(
            'id', p.id, 'type', p.type, 'locator', p.locator, 'chemin', p.chemin, 'sha', p.sha,
            'ligne_debut', p.ligne_debut, 'ligne_fin', p.ligne_fin, 'hash', p.hash, 'role', cp.role)
            ORDER BY p.id), '[]')
        FROM claim_preuve cp JOIN preuve p ON p.id = cp.preuve_id
        WHERE cp.claim_id = c.id) AS preuves,
       (SELECT p.activite->>'texte'
        FROM claim_preuve cp JOIN preuve p ON p.id = cp.preuve_id
        WHERE cp.claim_id = c.id ORDER BY p.id DESC LIMIT 1) AS texte
FROM claim c
"""


class TwinInvalide(ValueError):
    """Le Twin ou son Claim ne respecte pas un invariant : rien n'est écrit."""


class TwinIntrouvable(LookupError):
    """Le Twin demandé n'existe pas dans le tenant ; lecture et écriture sont refusées."""


class TwinTenantRefuse(TwinInvalide, TwinIntrouvable, PermissionError):
    """Un identifiant existe déjà sous un autre tenant : l'écriture est refusée."""


def _texte(valeur, champ: str) -> str:
    if valeur is None:
        raise TwinInvalide(f"{champ} obligatoire")
    texte = str(valeur).strip()
    if not texte:
        raise TwinInvalide(f"{champ} obligatoire")
    return texte


def _texte_optionnel(valeur) -> str | None:
    if valeur is None:
        return None
    texte = str(valeur).strip()
    return texte or None


def _normaliser_majuscules(valeur) -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = "".join(c if c.isalnum() else "_" for c in texte).strip("_")
    while "__" in texte:
        texte = texte.replace("__", "_")
    return texte.upper()


def _type_twin(valeur) -> str:
    type_propre = _normaliser_majuscules(valeur)
    if type_propre not in TYPES_TWIN:
        raise TwinInvalide(
            f"type de Twin inconnu : {valeur!r} (attendus : {', '.join(TYPES_TWIN)})")
    return type_propre


def _mode(valeur) -> str:
    mode_propre = _normaliser_majuscules(valeur)
    if mode_propre not in MODES:
        raise TwinInvalide(f"mode inconnu : {valeur!r} (attendus : {', '.join(MODES)})")
    return mode_propre


def _confiance(valeur) -> float:
    if isinstance(valeur, bool):
        raise TwinInvalide("confiance doit être un nombre entre 0 et 1")
    try:
        nombre = float(valeur)
    except (TypeError, ValueError) as exc:
        raise TwinInvalide("confiance doit être un nombre entre 0 et 1") from exc
    if not math.isfinite(nombre) or not 0.0 <= nombre <= 1.0:
        raise TwinInvalide("confiance doit être comprise entre 0 et 1")
    return nombre


def _limite(valeur, maximum: int = 1000) -> int:
    if isinstance(valeur, bool):
        raise TwinInvalide("limite doit être un entier positif")
    try:
        borne = int(valeur)
    except (TypeError, ValueError) as exc:
        raise TwinInvalide("limite doit être un entier positif") from exc
    return max(1, min(borne, maximum))


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
    if parties.username is not None and parties.scheme.lower() not in _SCHEMES_IDENTIFIANTS:
        return True
    return any(_cle_sensible(cle) and valeur not in ("", "***")
               for cle, valeur in parse_qsl(parties.query, keep_blank_values=True))


def _verifier_sans_secret(valeur, chemin: str) -> None:
    if isinstance(valeur, Mapping):
        for cle, element in valeur.items():
            if _cle_sensible(cle) and element not in (None, "", "***"):
                raise TwinInvalide(f"{chemin} : clé sensible refusée ({cle})")
            _verifier_sans_secret(element, f"{chemin}.{cle}")
    elif isinstance(valeur, (list, tuple)):
        for rang, element in enumerate(valeur):
            _verifier_sans_secret(element, f"{chemin}[{rang}]")
    elif isinstance(valeur, str) and _url_porte_un_secret(valeur):
        raise TwinInvalide(f"{chemin} : URL ou secret refusé")


def _jsonable(valeur):
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    if isinstance(valeur, Decimal):
        return float(valeur)
    if isinstance(valeur, Mapping):
        return {str(cle): _jsonable(element) for cle, element in valeur.items()}
    if isinstance(valeur, (list, tuple)):
        return [_jsonable(element) for element in valeur]
    return valeur


def _json_strict(valeur, champ: str):
    try:
        return json.loads(json.dumps(valeur, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise TwinInvalide(f"{champ} non sérialisable en JSON") from exc


def _ligne_twin(ligne) -> dict:
    return {cle: _jsonable(valeur) for cle, valeur in ligne.items()}


def _ligne_claim(ligne) -> dict:
    return {cle: _jsonable(valeur) for cle, valeur in ligne.items()}


def _twin_par_id(conn, twin_id: str, *, verrou: bool = False) -> dict | None:
    suffixe = " FOR UPDATE" if verrou else ""
    with conn.cursor(row_factory=dict_row) as cur:
        ligne = cur.execute(
            "SELECT id, tenant_id, nom, equipe, type, domaine, mission, cree_le FROM jumeau "
            "WHERE id = %s" + suffixe, (twin_id,)).fetchone()
    return _ligne_twin(ligne) if ligne is not None else None


def _twin_du_tenant(conn, tenant: str, twin_id: str, *, verrou: bool = False) -> dict:
    ligne = _twin_par_id(conn, twin_id, verrou=verrou)
    if ligne is None:
        raise TwinIntrouvable(twin_id)
    if ligne["tenant_id"] != tenant:
        raise TwinTenantRefuse(twin_id)
    return ligne


def _champs_sans_secret(*champs) -> None:
    for nom, valeur in champs:
        if valeur is not None:
            _verifier_sans_secret(valeur, nom)


def creer_twin(conn, tenant_id, twin_id, type_twin, nom, *, mission=None, domaine=None,
               equipe="à confirmer", acteur, preuve=None) -> dict:
    """Crée un Twin typé, ou rend l'identité existante si le même id a déjà le même type.

    Le tenant, l'id, le type et l'acteur sont obligatoires ; toute création écrit une ligne d'audit
    `identity_decision` (action `creation_twin`, avant/apres, acteur et preuve éventuelle). Un id déjà présent
    n'est jamais modifié : son type, son nom, sa mission et son domaine sont préservés, ce qui rend la création
    idempotente. Un changement de type est refusé, y compris pour une APPLICATION : ce module ne remplace jamais
    une APPLICATION existante par un autre type. Une APPLICATION n'est acceptée que si son id est encore absent ;
    les flux d'identité existants restent la voie normale pour créer et promouvoir les applications.
    """
    tenant = _texte(tenant_id, "tenant_id")
    jid = _texte(twin_id, "twin_id")
    type_propre = _type_twin(type_twin)
    nom_propre = _texte(nom, "nom")
    acteur_propre = _texte(acteur, "acteur")
    equipe_propre = _texte(equipe, "equipe")
    mission_propre = _texte_optionnel(mission)
    domaine_propre = _texte_optionnel(domaine)
    _champs_sans_secret(("nom", nom_propre), ("mission", mission_propre), ("domaine", domaine_propre),
                        ("equipe", equipe_propre))
    preuve_json = None if preuve is None else _json_strict(_jsonable(preuve), "preuve")
    if preuve_json is not None:
        _verifier_sans_secret(preuve_json, "preuve")

    with conn.transaction():
        existant = _twin_par_id(conn, jid, verrou=True)
        if existant is not None:
            if existant["tenant_id"] != tenant:
                raise TwinTenantRefuse(f"twin {jid} appartient à un autre tenant")
            if existant["type"] != type_propre:
                raise TwinInvalide(
                    f"twin {jid} déjà {existant['type']} : changement de type refusé")
            return existant
        with conn.cursor(row_factory=dict_row) as cur:
            ligne = cur.execute(
                "INSERT INTO jumeau (id, tenant_id, nom, equipe, type, domaine, mission) "
                "VALUES (%s, %s, %s, %s, %s, coalesce(%s, 'À confirmer'), %s) "
                "RETURNING id, tenant_id, nom, equipe, type, domaine, mission, cree_le",
                (jid, tenant, nom_propre, equipe_propre, type_propre, domaine_propre,
                 mission_propre)).fetchone()
        resultat = _ligne_twin(ligne)
        conn.execute(
            "INSERT INTO identity_decision (tenant_id, jumeau_id, acteur, action, avant, apres, preuve) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (tenant, jid, acteur_propre, ACTION_CREATION, Jsonb({}), Jsonb(resultat),
             Jsonb(preuve_json) if preuve_json is not None else None))
    return resultat


def lire_twin(conn, tenant_id, twin_id) -> dict | None:
    """Lit un Twin du tenant ; `None` s'il n'existe pas dans ce tenant."""
    tenant = _texte(tenant_id, "tenant_id")
    jid = _texte(twin_id, "twin_id")
    with conn.cursor(row_factory=dict_row) as cur:
        ligne = cur.execute(
            "SELECT id, tenant_id, nom, equipe, type, domaine, mission, cree_le FROM jumeau "
            "WHERE tenant_id = %s AND id = %s", (tenant, jid)).fetchone()
    return _ligne_twin(ligne) if ligne is not None else None


def lister_twins(conn, tenant_id, type_twin=None, limite=200) -> list[dict]:
    """Liste les Twins d'un tenant, filtrés par type et bornés, dans un ordre stable (nom, id)."""
    tenant = _texte(tenant_id, "tenant_id")
    conditions, parametres = ["tenant_id = %s"], [tenant]
    if type_twin is not None:
        conditions.append("type = %s")
        parametres.append(_type_twin(type_twin))
    parametres.append(_limite(limite))
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            "SELECT id, tenant_id, nom, equipe, type, domaine, mission, cree_le FROM jumeau "
            "WHERE " + " AND ".join(conditions) + " ORDER BY nom, id LIMIT %s",
            parametres).fetchall()
    return [_ligne_twin(ligne) for ligne in lignes]


def _source_existante(conn, source_id, tenant: str) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        ligne = cur.execute(
            "SELECT id, tenant_id, jumeau_id, type, nom, emplacement, curseur FROM source "
            "WHERE id = %s", (source_id,)).fetchone()
    if ligne is None:
        raise TwinInvalide(f"source introuvable : {source_id}")
    if ligne["tenant_id"] != tenant:
        raise TwinTenantRefuse(f"source {source_id} appartient à un autre tenant")
    return dict(ligne)


def _source_du_twin(conn, tenant: str, twin_id: str, nom: str, type_source: str,
                    emplacement: str, curseur=None) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        ligne = cur.execute(
            "INSERT INTO source (tenant_id, jumeau_id, type, nom, emplacement, curseur) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (jumeau_id, nom) DO UPDATE SET nom = EXCLUDED.nom "
            "RETURNING id, tenant_id, jumeau_id, type, nom, emplacement, curseur",
            (tenant, twin_id, type_source, nom, emplacement, curseur)).fetchone()
    if ligne["tenant_id"] != tenant:
        raise TwinTenantRefuse(f"source {nom} appartient à un autre tenant")
    return dict(ligne)


def _resoudre_source(conn, tenant: str, twin: dict, source, acteur: str) -> dict:
    if isinstance(source, Mapping):
        _verifier_sans_secret(source, "source")
        identifiant = source.get("id") or source.get("source_id")
        if identifiant is not None:
            if isinstance(identifiant, bool):
                raise TwinInvalide("source.id doit être un entier positif")
            try:
                return _source_existante(conn, int(identifiant), tenant)
            except (TypeError, ValueError) as exc:
                raise TwinInvalide("source.id doit être un entier positif") from exc
        nom = _texte(source.get("nom", source.get("name")), "source.nom")
        type_source = _normaliser_majuscules(source.get("type") or "DOCUMENTATION")
        if type_source not in TYPES_SOURCE:
            raise TwinInvalide(f"type de source inconnu : {source.get('type')!r}")
        emplacement = _texte(
            source.get("emplacement") or source.get("url") or nom, "source.emplacement")
        return _source_du_twin(conn, tenant, twin["id"], nom, type_source, emplacement,
                               _texte_optionnel(source.get("curseur")))
    if isinstance(source, bool):
        raise TwinInvalide("source : identifiant, nom ou objet attendu")
    if isinstance(source, int):
        if source < 1:
            raise TwinInvalide("source.id doit être un entier positif")
        return _source_existante(conn, source, tenant)
    if isinstance(source, str):
        nom = _texte(source, "source")
        _verifier_sans_secret(nom, "source")
        return _source_du_twin(conn, tenant, twin["id"], nom, "DOCUMENTATION", nom)
    raise TwinInvalide("source : identifiant, nom ou objet attendu")


def _lignes_locator(locator: str, defaut: int = 1) -> tuple[int, int]:
    trouve = re.search(r"#L(\d+)(?:-L(\d+))?$", locator or "")
    if not trouve:
        return defaut, defaut
    debut = int(trouve.group(1))
    return debut, int(trouve.group(2) or debut)


def _entier_ligne(donnees: Mapping, noms, defaut: int) -> int:
    valeur = defaut
    for nom in noms:
        if nom in donnees and donnees[nom] is not None:
            valeur = donnees[nom]
            break
    if isinstance(valeur, bool):
        raise TwinInvalide("ligne_debut et ligne_fin doivent être des entiers")
    try:
        return int(valeur)
    except (TypeError, ValueError) as exc:
        raise TwinInvalide("ligne_debut et ligne_fin doivent être des entiers") from exc


def _preuve_normalisee(preuve, source: dict, acteur: str, texte: str | None) -> dict:
    if preuve is None:
        raise TwinInvalide("preuve obligatoire")
    if isinstance(preuve, Mapping):
        donnees = dict(preuve)
        _verifier_sans_secret(donnees, "preuve")
        locator = _texte_optionnel(donnees.get("locator") or donnees.get("reference"))
        chemin = _texte_optionnel(donnees.get("chemin") or donnees.get("path")) or source["nom"]
        sha = _texte_optionnel(donnees.get("sha") or donnees.get("version")) or ""
        if any(cle in donnees for cle in ("ligne_debut", "debut", "ligne_fin", "fin")):
            debut = _entier_ligne(donnees, ("ligne_debut", "debut"), 1)
            fin = _entier_ligne(donnees, ("ligne_fin", "fin"), debut)
        else:
            debut, fin = _lignes_locator(locator or "")
        if debut < 1 or fin < debut:
            raise TwinInvalide("preuve : lignes invalides")
        citation = _texte_optionnel(donnees.get("citation") or donnees.get("texte")) or texte or ""
        empreinte = _texte_optionnel(donnees.get("hash")) or hashlib.sha256(
            (citation or locator or "").encode("utf-8")).hexdigest()
        if not locator:
            indices = any(donnees.get(cle) for cle in (
                "locator", "reference", "citation", "texte", "chemin", "path", "sha", "version", "hash"))
            if not citation and not indices:
                raise TwinInvalide("preuve : locator ou citation obligatoire")
            locator = f"{source['nom']}://{chemin}#L{debut}-L{fin}"
        activite = donnees.get("activite") or {}
        if not isinstance(activite, Mapping):
            raise TwinInvalide("preuve.activite doit être un objet")
        activite = dict(activite)
        activite.setdefault("extracteur", "twins_types")
        activite.setdefault("acteur", acteur)
        if texte:
            activite["texte"] = texte
        activite = _json_strict(_jsonable(activite), "preuve.activite")
        _verifier_sans_secret(activite, "preuve.activite")
        return {
            "type": _texte_optionnel(donnees.get("type")) or "DOCUMENTATION",
            "locator": locator,
            "chemin": chemin,
            "sha": sha,
            "ligne_debut": debut,
            "ligne_fin": fin,
            "hash": empreinte,
            "activite": activite,
        }
    if isinstance(preuve, str):
        contenu = _texte(preuve, "preuve")
        _verifier_sans_secret(contenu, "preuve")
        digest = hashlib.sha256(contenu.encode("utf-8")).hexdigest()
        if "://" in contenu or "#L" in contenu:
            locator, chemin = contenu, source["nom"]
        else:
            locator = f"declaration://{source['nom']}/{digest}#L1-L1"
            chemin = source["nom"]
        debut, fin = _lignes_locator(locator)
        activite = _json_strict({
            "extracteur": "twins_types",
            "acteur": acteur,
            "texte": texte or contenu,
        }, "preuve.activite")
        return {
            "type": "DOCUMENTATION",
            "locator": locator,
            "chemin": chemin,
            "sha": digest[:12],
            "ligne_debut": debut,
            "ligne_fin": fin,
            "hash": digest,
            "activite": activite,
        }
    raise TwinInvalide("preuve : objet ou chaîne attendue")


def _claims(conn, tenant: str, twin_id: str, *, claim_id=None, limite=None) -> list[dict]:
    conditions, parametres = ["c.tenant_id = %s", "c.jumeau_id = %s"], [tenant, twin_id]
    if claim_id is not None:
        conditions.append("c.id = %s")
        parametres.append(claim_id)
    else:
        conditions.append("c.valide_jusqua IS NULL")
    requete = _CHAMPS_CLAIM + " WHERE " + " AND ".join(conditions) + " ORDER BY c.id"
    if limite is not None:
        requete += " LIMIT %s"
        parametres.append(limite)
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(requete, parametres).fetchall()
    return [_ligne_claim(ligne) for ligne in lignes]


def creer_claim(conn, tenant_id, twin_id, predicat, objet, *, source, preuve, mode="DECLARED",
                confiance=0.5, acteur, texte=None) -> dict:
    """Attache un Claim prouvé à un Twin du même tenant, via l'API publique de `depot`.

    Le Twin doit exister dans le tenant. `source` accepte un id de source, un nom de source (créée en
    DOCUMENTATION si elle manque) ou un objet décrivant la source ; `preuve` accepte un objet de preuve ou une
    chaîne de citation. Une preuve non vide est obligatoire, son mode doit appartenir à `modele_entreprise.MODES`,
    et ni la source, ni la preuve, ni le texte ne peuvent porter un secret brut. `texte` est conservé dans
    l'activité de la preuve. Le Claim naît PROPOSED, origine CONVERSATION, et son type est le type générique CLAIM.
    """
    tenant = _texte(tenant_id, "tenant_id")
    jid = _texte(twin_id, "twin_id")
    predicat_propre = _texte(predicat, "predicat")
    objet_propre = _texte(objet, "objet")
    acteur_propre = _texte(acteur, "acteur")
    mode_propre = _mode(mode)
    confiance_propre = _confiance(confiance)
    texte_propre = _texte_optionnel(texte)
    _champs_sans_secret(("predicat", predicat_propre), ("objet", objet_propre), ("texte", texte_propre))
    if source is None or isinstance(source, bool) or not isinstance(source, (Mapping, int, str)):
        raise TwinInvalide("source : identifiant, nom ou objet attendu")
    if preuve is None or not isinstance(preuve, (Mapping, str)):
        raise TwinInvalide("preuve : objet ou chaîne attendue")
    if isinstance(source, Mapping):
        _verifier_sans_secret(source, "source")
    elif isinstance(source, str):
        _verifier_sans_secret(source, "source")
    if isinstance(preuve, str):
        _verifier_sans_secret(_texte(preuve, "preuve"), "preuve")

    with conn.transaction():
        twin = _twin_du_tenant(conn, tenant, jid)
        source_ligne = _resoudre_source(conn, tenant, twin, source, acteur_propre)
        preuve_dict = _preuve_normalisee(preuve, source_ligne, acteur_propre, texte_propre)
        jumeau = {"id": twin["id"], "tenant_id": tenant, "nom": twin["nom"]}
        claim_id = depot.enregistrer_proposition(
            conn, jumeau, source_ligne["id"],
            {"sujet": twin["nom"], "predicat": predicat_propre, "objet": objet_propre,
             "type": "CLAIM", "confiance": confiance_propre},
            preuve_dict, preuve_dict["activite"])
        conn.execute(
            "UPDATE claim SET mode = %s WHERE id = %s AND tenant_id = %s AND jumeau_id = %s "
            "AND statut = 'PROPOSED' AND origine = 'CONVERSATION'",
            (mode_propre, claim_id, tenant, jid))
        lignes = _claims(conn, tenant, jid, claim_id=claim_id)
    if not lignes:
        raise TwinIntrouvable(claim_id)
    return lignes[0]


def claims_du_twin(conn, tenant_id, twin_id, limite=100) -> list[dict]:
    """Claims valides attachés à un Twin du tenant, preuves comprises, dans un ordre stable (id)."""
    tenant = _texte(tenant_id, "tenant_id")
    jid = _texte(twin_id, "twin_id")
    borne = _limite(limite)
    with conn.transaction():
        _twin_du_tenant(conn, tenant, jid)
        return _claims(conn, tenant, jid, limite=borne)
