"""Persistance des objets d'entreprise (P0-A) : familles, types, modes, temporalité et tenant.

Un objet est identifié par `(tenant_id, id)` : deux tenants peuvent décrire le même identifiant sans se voir.
L'écriture est un upsert versionné ; une version inférieure à celle déjà stockée est refusée. Les données sont
du JSON strict, sans secret. Aucun accès réseau ni agent n'est effectué ici.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, time
from decimal import Decimal
import json
import unicodedata
from urllib.parse import parse_qsl, unquote_plus, urlsplit

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from meridian.domain.modele_entreprise import FAMILLES, MODES, TYPES_PAR_FAMILLE

_FAMILLES = frozenset(FAMILLES)
_MODES = frozenset(MODES)
_TYPES_PAR_FAMILLE = {famille: frozenset(types) for famille, types in TYPES_PAR_FAMILLE.items()}
_TYPES_CONNUS = frozenset(type_ for types in _TYPES_PAR_FAMILLE.values() for type_ in types)
_CHAMPS_OBJET = frozenset({
    "id", "tenant_id", "famille", "type", "mode", "titre", "donnees", "version",
    "observe_le", "valide_depuis", "valide_jusqua", "cree_le", "maj_le",
})

_MARQUEURS_SECRETS = ("password", "passwd", "secret", "token", "credential", "authorization")
_CLES_SECRETES = frozenset({
    "pwd", "pass", "auth", "key", "apikey", "api_key", "api-key", "access_key", "accesskey",
    "private_key", "privatekey", "client_secret", "clientsecret", "bearer", "password", "passwd",
})


class ObjetInvalide(ValueError):
    """Objet d'entreprise refusé avant toute écriture."""


class VersionRefusee(ObjetInvalide):
    """La version proposée recule par rapport à celle déjà stockée."""


def _normaliser(valeur, *, minuscule: bool = False) -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = "".join(c if c.isalnum() else "_" for c in texte).strip("_")
    while "__" in texte:
        texte = texte.replace("__", "_")
    return texte.lower() if minuscule else texte.upper()


def _texte_obligatoire(valeur, champ: str) -> str:
    if valeur is None:
        raise ObjetInvalide(f"{champ} obligatoire")
    texte = str(valeur).strip()
    if not texte:
        raise ObjetInvalide(f"{champ} obligatoire")
    return texte


def _tenant(tenant_id) -> str:
    return _texte_obligatoire(tenant_id, "tenant_id")


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
    if parties.username is not None or parties.password is not None or "@" in parties.netloc:
        return True
    return any(_cle_sensible(cle) and valeur not in ("", "***")
               for cle, valeur in parse_qsl(parties.query, keep_blank_values=True))


def _verifier_secrets(valeur, chemin: str = "donnees") -> None:
    if isinstance(valeur, Mapping):
        for cle, element in valeur.items():
            if _cle_sensible(cle) and element not in (None, "", "***"):
                raise ObjetInvalide(f"{chemin} : clé sensible refusée ({cle})")
            _verifier_secrets(element, f"{chemin}.{cle}")
    elif isinstance(valeur, (list, tuple)):
        for rang, element in enumerate(valeur):
            _verifier_secrets(element, f"{chemin}[{rang}]")
    elif isinstance(valeur, str) and _url_porte_un_secret(valeur):
        raise ObjetInvalide(f"{chemin} : URL ou secret refusé")


def _donnees_json(valeur) -> object:
    if valeur is None:
        return {}
    _verifier_secrets(valeur)
    try:
        return json.loads(json.dumps(valeur, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ObjetInvalide("donnees non sérialisables en JSON") from exc


def _version(valeur) -> int | None:
    if valeur is None:
        return None
    if isinstance(valeur, bool):
        raise ObjetInvalide("version doit être un entier positif")
    try:
        version = int(valeur)
    except (TypeError, ValueError) as exc:
        raise ObjetInvalide("version doit être un entier positif") from exc
    if version < 1 or (isinstance(valeur, float) and version != valeur):
        raise ObjetInvalide("version doit être un entier positif")
    return version


def _instant(valeur, champ: str):
    if valeur is None:
        return None
    if isinstance(valeur, datetime):
        return valeur
    if isinstance(valeur, date):
        return datetime.combine(valeur, time.min)
    if isinstance(valeur, str):
        texte = valeur.strip()
        if not texte:
            return None
        try:
            return datetime.fromisoformat(texte.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ObjetInvalide(f"{champ} doit être une date ISO") from exc
    raise ObjetInvalide(f"{champ} doit être une date ISO")


def _verifier_periode(debut, fin) -> None:
    if debut is None or fin is None:
        return
    try:
        incoherente = fin < debut
    except TypeError:
        return
    if incoherente:
        raise ObjetInvalide("valide_jusqua précède valide_depuis")


def _verifier_famille_type(famille: str, type_: str) -> None:
    famille = _normaliser(famille, minuscule=True)
    type_ = _normaliser(type_)
    if famille not in _FAMILLES:
        raise ObjetInvalide(f"famille inconnue : {famille!r}")
    if type_ not in _TYPES_CONNUS:
        raise ObjetInvalide(f"type inconnu : {type_!r}")
    if type_ not in _TYPES_PAR_FAMILLE[famille]:
        raise ObjetInvalide(f"type {type_} hors de la famille {famille}")


def _objet_saisi(objet) -> dict:
    depuis_modele = False
    if not isinstance(objet, Mapping):
        for nom in ("to_dict", "as_dict"):
            convertisseur = getattr(objet, nom, None)
            if callable(convertisseur):
                objet = convertisseur()
                depuis_modele = True
                break
    if not isinstance(objet, Mapping):
        raise ObjetInvalide("objet d'entreprise attendu")
    saisi = {"id": _texte_obligatoire(objet.get("id"), "id")}
    if "famille" in objet:
        famille = _normaliser(objet.get("famille"), minuscule=True)
        if famille not in _FAMILLES:
            raise ObjetInvalide(f"famille inconnue : {famille!r}")
        saisi["famille"] = famille
    if "type" in objet:
        type_ = _normaliser(objet.get("type"))
        if type_ not in _TYPES_CONNUS:
            raise ObjetInvalide(f"type inconnu : {type_!r}")
        saisi["type"] = type_
    if "mode" in objet:
        mode = _normaliser(objet.get("mode"))
        if mode:
            if mode not in _MODES:
                raise ObjetInvalide(f"mode inconnu : {mode!r}")
            saisi["mode"] = mode
        elif depuis_modele:
            saisi["mode"] = "DECLARED"
        else:
            raise ObjetInvalide(f"mode inconnu : {mode!r}")
    if "titre" in objet:
        saisi["titre"] = "" if objet.get("titre") is None else str(objet["titre"]).strip()
    if "donnees" in objet:
        saisi["donnees"] = _donnees_json(objet["donnees"])
    else:
        complement = {cle: valeur for cle, valeur in objet.items() if cle not in _CHAMPS_OBJET}
        if complement:
            saisi["donnees"] = _donnees_json(complement)
    if "version" in objet:
        saisi["version"] = _version(objet["version"])
    for champ in ("observe_le", "valide_depuis", "valide_jusqua", "cree_le"):
        if champ in objet:
            saisi[champ] = _instant(objet[champ], champ)
    return saisi


def _valeur(valeur):
    if isinstance(valeur, Decimal):
        return float(valeur)
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    return valeur


def _ligne(ligne) -> dict:
    return {cle: _valeur(valeur) for cle, valeur in ligne.items()}


def enregistrer_objet(conn, tenant_id, objet) -> dict:
    """Upsert un objet d'entreprise pour un tenant ; rend la ligne stockée.

    La version augmente d'elle-même quand elle n'est pas fournie ; une version inférieure à celle déjà stockée est
    refusée (`VersionRefusee`). `cree_le` est immuable après la création. `valide_jusqua` peut être remis à NULL en
    le passant explicitement. Les données doivent être du JSON strict et ne porter aucun secret.
    """
    tenant = _tenant(tenant_id)
    saisi = _objet_saisi(objet)

    with conn.transaction():
        with conn.cursor(row_factory=dict_row) as cur:
            existant = cur.execute(
                "SELECT * FROM objet_entreprise WHERE tenant_id = %s AND id = %s FOR UPDATE",
                (tenant, saisi["id"])).fetchone()

            if existant is None:
                for champ in ("famille", "type", "mode"):
                    if champ not in saisi:
                        raise ObjetInvalide(f"{champ} obligatoire")
                famille, type_, mode = saisi["famille"], saisi["type"], saisi["mode"]
                _verifier_famille_type(famille, type_)
                version = saisi.get("version") or 1
                titre = saisi.get("titre", "")
                donnees = saisi.get("donnees", {})
                observe_le = saisi.get("observe_le")
                valide_depuis = saisi.get("valide_depuis")
                valide_jusqua = saisi.get("valide_jusqua")
                cree_le = saisi.get("cree_le")
                _verifier_periode(valide_depuis, valide_jusqua)
                ligne = cur.execute(
                    "INSERT INTO objet_entreprise "
                    "(id, tenant_id, famille, type, mode, titre, donnees, version, observe_le, valide_depuis, "
                    "valide_jusqua, cree_le) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, coalesce(%s, now()), "
                    "coalesce(%s, least(now(), coalesce(%s, now()))), %s, coalesce(%s, now())) RETURNING *",
                    (saisi["id"], tenant, famille, type_, mode, titre, Jsonb(donnees), version,
                     observe_le, valide_depuis, valide_jusqua, valide_jusqua, cree_le)).fetchone()
            else:
                famille = saisi.get("famille", existant["famille"])
                type_ = saisi.get("type", existant["type"])
                mode = saisi.get("mode", existant["mode"])
                _verifier_famille_type(famille, type_)
                version = saisi.get("version")
                if version is None:
                    version = existant["version"] + 1
                elif version < existant["version"]:
                    raise VersionRefusee(
                        f"version {version} inférieure à la version stockée {existant['version']}")
                titre = saisi.get("titre", existant["titre"])
                donnees = saisi.get("donnees", existant["donnees"])
                observe_le = saisi.get("observe_le") or existant["observe_le"]
                valide_depuis = saisi.get("valide_depuis") or existant["valide_depuis"]
                valide_jusqua = (saisi["valide_jusqua"] if "valide_jusqua" in saisi
                                 else existant["valide_jusqua"])
                _verifier_periode(valide_depuis, valide_jusqua)
                ligne = cur.execute(
                    "UPDATE objet_entreprise SET famille = %s, type = %s, mode = %s, titre = %s, donnees = %s, "
                    "version = %s, observe_le = %s, valide_depuis = %s, valide_jusqua = %s, maj_le = now() "
                    "WHERE tenant_id = %s AND id = %s RETURNING *",
                    (famille, type_, mode, titre, Jsonb(donnees), version, observe_le, valide_depuis,
                     valide_jusqua, tenant, saisi["id"])).fetchone()

    return _ligne(ligne)


def lire_objet(conn, tenant_id, objet_id) -> dict | None:
    """Lit un objet du tenant ; `None` s'il n'existe pas dans ce tenant."""
    tenant = _tenant(tenant_id)
    identifiant = _texte_obligatoire(objet_id, "id")
    with conn.cursor(row_factory=dict_row) as cur:
        ligne = cur.execute(
            "SELECT * FROM objet_entreprise WHERE tenant_id = %s AND id = %s",
            (tenant, identifiant)).fetchone()
    return _ligne(ligne) if ligne is not None else None


def lister_objets(conn, tenant_id, famille=None, type_=None, mode=None, limite=100) -> list[dict]:
    """Liste les objets d'un tenant, filtrés par famille, type et mode, dans un ordre stable."""
    tenant = _tenant(tenant_id)
    conditions, parametres = ["tenant_id = %s"], [tenant]
    if famille is not None:
        valeur = _normaliser(famille, minuscule=True)
        if valeur not in _FAMILLES:
            raise ObjetInvalide(f"famille inconnue : {famille!r}")
        conditions.append("famille = %s")
        parametres.append(valeur)
    if type_ is not None:
        valeur = _normaliser(type_)
        if valeur not in _TYPES_CONNUS:
            raise ObjetInvalide(f"type inconnu : {type_!r}")
        conditions.append("type = %s")
        parametres.append(valeur)
    if mode is not None:
        valeur = _normaliser(mode)
        if valeur not in _MODES:
            raise ObjetInvalide(f"mode inconnu : {mode!r}")
        conditions.append("mode = %s")
        parametres.append(valeur)
    if isinstance(limite, bool):
        raise ObjetInvalide("limite doit être un entier positif")
    try:
        borne = max(1, min(int(limite), 1000))
    except (TypeError, ValueError) as exc:
        raise ObjetInvalide("limite doit être un entier positif") from exc
    parametres.append(borne)
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            "SELECT * FROM objet_entreprise WHERE " + " AND ".join(conditions) +
            " ORDER BY famille, type, id LIMIT %s", parametres).fetchall()
    return [_ligne(ligne) for ligne in lignes]
