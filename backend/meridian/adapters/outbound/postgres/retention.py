"""Politique de rétention explicite et purge à blanc, bornées au tenant.

Le module ne remplace pas les mécanismes de suppression de ``memoire_durable`` :
il donne une vue d'ensemble des classes de données, compte ce qui a expiré et
ne supprime, en mode réel, que les lignes réellement mutables et échues. Les
Claims et les Preuves sont immuables ; les Learnings, les Outcomes et les
prédictions non résolues sont seulement signalés. Aucune requête ne traverse
la frontière du tenant, et une table absente est rendue comme une limite au
lieu de faire échouer le rapport.
"""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

try:
    from psycopg.rows import dict_row as _dict_row
except ImportError:
    _dict_row = None

from meridian.domain import tenant as tenant_module

__all__ = [
    "POLITIQUES",
    "Politique",
    "as_dict",
    "exporter_politique",
    "purger",
    "rapport",
]

_AN = 365


@dataclass(frozen=True)
class Politique:
    """Une classe de rétention : table, durée, immuabilité et supprimabilité."""

    nom: str
    table: str
    jours: int
    immuable: bool = False
    supprimable: bool = True
    classe: str | None = None
    type_objet: str | None = None
    colonne_expiration: str | None = None
    colonne_creation: str = "cree_le"
    condition_suppression: str | None = None
    plafond_age: bool = True
    description: str = ""

    @property
    def retention_jours(self) -> int:
        """Alias de ``jours`` pour les appelants qui nomment la durée en clair."""
        return self.jours

    def as_dict(self) -> dict:
        """Rend la politique sérialisable, avec les alias français et anglais."""
        return {
            "nom": self.nom,
            "table": self.table,
            "jours": self.jours,
            "retention_jours": self.jours,
            "duree_jours": self.jours,
            "days": self.jours,
            "immuable": self.immuable,
            "immutable": self.immuable,
            "supprimable": self.supprimable,
            "classe": self.classe,
            "type_objet": self.type_objet,
            "colonne_expiration": self.colonne_expiration,
            "colonne_creation": self.colonne_creation,
            "condition_suppression": self.condition_suppression,
            "plafond_age": self.plafond_age,
            "description": self.description,
        }

    def __getitem__(self, cle: str) -> Any:
        if cle == "retention_jours" or cle == "duree_jours" or cle == "days":
            return self.jours
        if cle == "immutable":
            return self.immuable
        if cle not in self.as_dict():
            raise KeyError(cle)
        return getattr(self, cle)

    def get(self, cle: str, defaut: Any = None) -> Any:
        try:
            return self[cle]
        except KeyError:
            return defaut

    def __contains__(self, cle: object) -> bool:
        return cle in self.as_dict()

    def keys(self) -> tuple[str, ...]:
        return tuple(self.as_dict())

    def values(self) -> tuple[Any, ...]:
        return tuple(self.as_dict().values())

    def items(self) -> tuple[tuple[str, Any], ...]:
        return tuple(self.as_dict().items())

    def __iter__(self):
        return iter(self.as_dict())

    def __len__(self) -> int:
        return len(self.as_dict())


POLITIQUES: dict[str, Politique] = {
    "memoire_durable": Politique(
        nom="memoire_durable",
        table="memoire_durable",
        jours=30,
        classe=None,
        colonne_expiration="expire_le",
        colonne_creation="cree_le",
        plafond_age=False,
        description="Souvenirs durables hors session : l'expiration explicite fait foi.",
    ),
    "session": Politique(
        nom="session",
        table="memoire_durable",
        jours=7,
        classe="session",
        colonne_expiration="expire_le",
        colonne_creation="cree_le",
        plafond_age=True,
        description="Mémoire de session, plus courte que la mémoire durable.",
    ),
    "claim": Politique(
        nom="claim",
        table="claim",
        jours=10 * _AN,
        immuable=True,
        supprimable=False,
        colonne_creation="enregistre_le",
        description="Claims immuables : conservés comme mémoire sémantique, jamais purgés.",
    ),
    "preuve": Politique(
        nom="preuve",
        table="preuve",
        jours=10 * _AN,
        immuable=True,
        supprimable=False,
        colonne_creation="observee_le",
        description="Preuves immuables : aucune suppression sans trace n'est permise.",
    ),
    "learning": Politique(
        nom="learning",
        table="objet_entreprise",
        jours=5 * _AN,
        supprimable=False,
        type_objet="LEARNING",
        colonne_creation="cree_le",
        description="Learnings d'entreprise : rétention longue, jamais purgés par ce module.",
    ),
    "outcome": Politique(
        nom="outcome",
        table="objet_entreprise",
        jours=5 * _AN,
        supprimable=False,
        type_objet="OUTCOME",
        colonne_creation="cree_le",
        description="Outcomes observés : rétention longue, jamais purgés par ce module.",
    ),
    "prediction": Politique(
        nom="prediction",
        table="prediction_calibration",
        jours=_AN,
        colonne_creation="cree_le",
        condition_suppression="outcome IS NOT NULL",
        description="Calibration : seules les prédictions résolues de plus d'un an sont purgeables.",
    ),
}


def _tenant(tenant_id: Any) -> str:
    try:
        return tenant_module.exiger_tenant(tenant_id).id
    except tenant_module.TenantError as exc:
        raise ValueError(str(exc)) from exc


def _est_sqlite(conn: Any) -> bool:
    return type(conn).__module__.split(".", 1)[0] == "sqlite3"


def _sql(conn: Any, requete: str) -> str:
    return requete.replace("%s", "?") if _est_sqlite(conn) else requete


def _cursor(conn: Any) -> Any:
    if _dict_row is not None:
        try:
            return conn.cursor(row_factory=_dict_row)
        except TypeError:
            pass
    return conn.cursor()


def _fermer(cur: Any) -> None:
    fermer = getattr(cur, "close", None)
    if callable(fermer):
        fermer()


@contextmanager
def _point(conn: Any):
    if _est_sqlite(conn):
        yield
        return
    transaction = getattr(conn, "transaction", None)
    if callable(transaction):
        with transaction():
            yield
        return
    yield


def _lignes(conn: Any, requete: str, parametres: tuple = ()) -> list[dict]:
    cur = _cursor(conn)
    try:
        cur.execute(_sql(conn, requete), parametres)
        lignes = cur.fetchall()
        noms = [description[0] for description in (cur.description or ())]
    finally:
        _fermer(cur)
    resultat = []
    for ligne in lignes:
        if isinstance(ligne, Mapping):
            resultat.append(dict(ligne))
        else:
            resultat.append({noms[i]: ligne[i] for i in range(min(len(noms), len(ligne)))})
    return resultat


def _une(conn: Any, requete: str, parametres: tuple = ()) -> dict:
    lignes = _lignes(conn, requete, parametres)
    return lignes[0] if lignes else {}


def _champ(ligne: Mapping, nom: str) -> Any:
    return ligne.get(nom)


def _instant(valeur: Any) -> datetime | None:
    if valeur is None:
        return None
    if isinstance(valeur, datetime):
        instant = valeur
    elif isinstance(valeur, date):
        instant = datetime.combine(valeur, time.min, tzinfo=timezone.utc)
    elif isinstance(valeur, str):
        texte = valeur.strip()
        if not texte:
            return None
        try:
            instant = datetime.fromisoformat(texte.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(timezone.utc)


def _maintenant(valeur: Any = None) -> datetime:
    if valeur is None:
        return datetime.now(timezone.utc)
    instant = _instant(valeur)
    if instant is None:
        raise ValueError("maintenant doit être une date ISO ou un datetime")
    return instant


def _iso(valeur: datetime | None) -> str | None:
    return valeur.astimezone(timezone.utc).isoformat() if valeur is not None else None


def _date(conn: Any, expression: str) -> str:
    return f"datetime({expression})" if _est_sqlite(conn) else expression


def _est_structure(exc: Exception) -> bool:
    sqlstate = getattr(exc, "sqlstate", None) or getattr(exc, "pgcode", None)
    if sqlstate in {"42P01", "42703"}:
        return True
    texte = str(exc).lower()
    marqueurs = (
        "no such table",
        "no such column",
        "does not exist",
        "undefinedtable",
        "undefinedcolumn",
    )
    return any(marqueur in texte for marqueur in marqueurs)


def _filtre(politique: Politique) -> tuple[list[str], list[Any]]:
    if politique.nom == "session":
        return ["classe = %s"], ["session"]
    if politique.nom == "memoire_durable":
        return ["(classe IS NULL OR classe <> %s)"], ["session"]
    if politique.type_objet:
        return ["UPPER(type) = %s"], [politique.type_objet]
    return [], []


def _expiration_sql(
    conn: Any, politique: Politique, maintenant: datetime
) -> tuple[str, list[Any]]:
    def date(expression: str) -> str:
        return _date(conn, expression)

    morceaux: list[str] = []
    parametres: list[Any] = []
    if politique.colonne_expiration:
        colonne = politique.colonne_expiration
        morceaux.append(
            f"{date(colonne)} IS NOT NULL AND {date(colonne)} <= {date('%s')}"
        )
        parametres.append(maintenant)
    if politique.plafond_age:
        cutoff = maintenant - timedelta(days=politique.jours)
        colonne = politique.colonne_creation
        morceaux.append(
            f"{date(colonne)} IS NOT NULL AND {date(colonne)} <= {date('%s')}"
        )
        parametres.append(cutoff)
    expression = "(" + " OR ".join(morceaux) + ")" if morceaux else "1 = 0"
    return expression, parametres


def _prochaines_sql(
    conn: Any, politique: Politique, maintenant: datetime
) -> tuple[list[str], list[Any]]:
    def date(expression: str) -> str:
        return _date(conn, expression)

    expressions: list[str] = []
    parametres: list[Any] = []
    if politique.colonne_expiration:
        colonne = politique.colonne_expiration
        expressions.append(
            f"MIN(CASE WHEN {date(colonne)} > {date('%s')} THEN {date(colonne)} END) "
            "AS prochaine_expiration"
        )
        parametres.append(maintenant)
    if politique.plafond_age:
        cutoff = maintenant - timedelta(days=politique.jours)
        colonne = politique.colonne_creation
        expressions.append(
            f"MIN(CASE WHEN {date(colonne)} > {date('%s')} THEN {date(colonne)} END) "
            "AS prochain_age"
        )
        parametres.append(cutoff)
    return expressions, parametres


def _prochaine(politique: Politique, ligne: Mapping) -> datetime | None:
    candidats: list[datetime] = []
    if politique.colonne_expiration:
        expiration = _instant(_champ(ligne, "prochaine_expiration"))
        if expiration is not None:
            candidats.append(expiration)
    if politique.plafond_age:
        création = _instant(_champ(ligne, "prochain_age"))
        if création is not None:
            candidats.append(création + timedelta(days=politique.jours))
    return min(candidats) if candidats else None


def _finaliser(
    politique: Politique,
    total: int,
    expirees: int,
    supprimables: int,
    immuables: int,
    prochaine: datetime | None,
    *,
    disponible: bool = True,
    limite: str | None = None,
) -> dict:
    return {
        "nom": politique.nom,
        "table": politique.table,
        "jours": politique.jours,
        "immuable": politique.immuable,
        "supprimable": politique.supprimable,
        "total": total,
        "expirees": expirees,
        "supprimables": supprimables,
        "immuables": immuables,
        "prochaine_expiration": _iso(prochaine),
        "disponible": disponible,
        "limite": limite,
    }


def _zero(politique: Politique, limite: str | None = None) -> dict:
    return _finaliser(
        politique, 0, 0, 0, 0, None, disponible=limite is None, limite=limite
    )


def _mesurer_sql(
    conn: Any, tenant: str, politique: Politique, maintenant: datetime
) -> dict:
    expire, parametres_expire = _expiration_sql(conn, politique, maintenant)
    prochaines, parametres_prochaines = _prochaines_sql(conn, politique, maintenant)
    condition = (
        (politique.condition_suppression or "1 = 1") if politique.supprimable else "1 = 0"
    )
    immuables = "COUNT(*)" if politique.immuable else "0"
    selection = [
        "COUNT(*) AS total",
        f"COALESCE(SUM(CASE WHEN {expire} THEN 1 ELSE 0 END), 0) AS expirees",
        f"COALESCE(SUM(CASE WHEN ({expire}) AND ({condition}) THEN 1 ELSE 0 END), 0) AS supprimables",
        f"{immuables} AS immuables",
    ]
    selection.extend(prochaines)
    conditions, parametres_filtre = _filtre(politique)
    where = ["tenant_id = %s"] + conditions
    parametres = (
        parametres_expire + parametres_expire + parametres_prochaines + [tenant] + parametres_filtre
    )
    ligne = _une(
        conn,
        "SELECT " + ", ".join(selection) + f" FROM {politique.table} WHERE "
        + " AND ".join(where),
        tuple(parametres),
    )
    return _finaliser(
        politique,
        int(_champ(ligne, "total") or 0),
        int(_champ(ligne, "expirees") or 0),
        int(_champ(ligne, "supprimables") or 0),
        int(_champ(ligne, "immuables") or 0),
        _prochaine(politique, ligne),
    )


def _correspond(politique: Politique, ligne: Mapping) -> bool:
    classe = _champ(ligne, "classe")
    if politique.classe is not None:
        if classe is None or str(classe) != politique.classe:
            return False
    if politique.nom == "memoire_durable" and classe is not None:
        if str(classe) == "session":
            return False
    if politique.type_objet is not None:
        type_objet = _champ(ligne, "type")
        if type_objet is None or str(type_objet).upper() != politique.type_objet:
            return False
    return True


def _condition_remplie(politique: Politique, ligne: Mapping) -> bool:
    if politique.condition_suppression == "outcome IS NOT NULL":
        return _champ(ligne, "outcome") is not None
    return True


def _expire_ligne(politique: Politique, ligne: Mapping, maintenant: datetime) -> bool:
    if politique.colonne_expiration:
        expiration = _instant(_champ(ligne, politique.colonne_expiration))
        if expiration is not None and expiration <= maintenant:
            return True
    if politique.plafond_age:
        création = _instant(_champ(ligne, politique.colonne_creation))
        if création is not None and création + timedelta(days=politique.jours) <= maintenant:
            return True
    return False


def _prochaine_ligne(
    politique: Politique, ligne: Mapping, maintenant: datetime
) -> datetime | None:
    candidats: list[datetime] = []
    if politique.colonne_expiration:
        expiration = _instant(_champ(ligne, politique.colonne_expiration))
        if expiration is not None and expiration > maintenant:
            candidats.append(expiration)
    if politique.plafond_age:
        cutoff = maintenant - timedelta(days=politique.jours)
        création = _instant(_champ(ligne, politique.colonne_creation))
        if création is not None and création > cutoff:
            candidats.append(création + timedelta(days=politique.jours))
    return min(candidats) if candidats else None


def _mesurer_python(
    conn: Any, tenant: str, politique: Politique, maintenant: datetime
) -> dict:
    lignes = _lignes(
        conn,
        f"SELECT * FROM {politique.table} WHERE tenant_id = %s",
        (tenant,),
    )
    total = expirees = supprimables = 0
    prochaines: list[datetime] = []
    for ligne in lignes:
        if not _correspond(politique, ligne):
            continue
        total += 1
        if _expire_ligne(politique, ligne, maintenant):
            expirees += 1
            if politique.supprimable and _condition_remplie(politique, ligne):
                supprimables += 1
        prochaine = _prochaine_ligne(politique, ligne, maintenant)
        if prochaine is not None:
            prochaines.append(prochaine)
    return _finaliser(
        politique,
        total,
        expirees,
        supprimables,
        total if politique.immuable else 0,
        min(prochaines) if prochaines else None,
    )


def _mesurer(
    conn: Any, tenant: str, politique: Politique, maintenant: datetime
) -> tuple[dict, str | None]:
    try:
        with _point(conn):
            return _mesurer_sql(conn, tenant, politique, maintenant), None
    except Exception as exc:
        if not _est_structure(exc):
            raise
    try:
        with _point(conn):
            return _mesurer_python(conn, tenant, politique, maintenant), None
    except Exception as exc:
        if not _est_structure(exc):
            raise
        return _zero(politique, str(exc)), str(exc)


def _supprimer(
    conn: Any, tenant: str, politique: Politique, maintenant: datetime
) -> int:
    if not politique.supprimable:
        return 0
    expire, parametres_expire = _expiration_sql(conn, politique, maintenant)
    conditions, parametres_filtre = _filtre(politique)
    where = ["tenant_id = %s"] + conditions + [expire]
    parametres = [tenant] + parametres_filtre + parametres_expire
    if politique.condition_suppression:
        where.append(f"({politique.condition_suppression})")
    with _point(conn):
        cur = _cursor(conn)
        try:
            cur.execute(
                _sql(conn, f"DELETE FROM {politique.table} WHERE " + " AND ".join(where)),
                tuple(parametres),
            )
            nombre = cur.rowcount
        finally:
            _fermer(cur)
    return max(int(nombre or 0), 0)


def _erreur(nom: str, exc: Exception) -> dict:
    return {"classe": nom, "erreur": str(exc)}


def rapport(conn: Any, tenant_id: Any) -> dict:
    """Compte les lignes de chaque classe et repère celles qui ont expiré.

    Le rapport est borné au tenant. Une table ou une colonne absente produit une
    classe à zéro avec une limite explicite, sans interrompre les autres
    classes. ``immuables`` compte les lignes des classes immuables (Claims et
    Preuves) ; ``prochaine_expiration`` est la plus proche échéance connue.
    """
    tenant = _tenant(tenant_id)
    maintenant = _maintenant()
    classes: dict[str, dict] = {}
    limites: list[dict] = []
    erreurs: list[dict] = []
    for nom, politique in POLITIQUES.items():
        try:
            metriques, limite = _mesurer(conn, tenant, politique, maintenant)
        except Exception as exc:
            metriques, limite = _zero(politique, str(exc)), None
            erreurs.append(_erreur(nom, exc))
        classes[nom] = metriques
        if limite is not None:
            limites.append({"classe": nom, "table": politique.table, "motif": limite})
    expirees = sum(metriques["expirees"] for metriques in classes.values())
    supprimables = sum(metriques["supprimables"] for metriques in classes.values())
    immuables = sum(metriques["immuables"] for metriques in classes.values())
    ignorees = sum(
        metriques["expirees"] - metriques["supprimables"]
        if metriques["supprimable"]
        else metriques["expirees"]
        for metriques in classes.values()
    )
    prochaines = [
        _instant(metriques["prochaine_expiration"])
        for metriques in classes.values()
        if metriques["prochaine_expiration"] is not None
    ]
    prochaines = [instant for instant in prochaines if instant is not None]
    resultat = {
        "tenant_id": tenant,
        "maintenant": _iso(maintenant),
        "classes": classes,
        "par_classe": classes,
        "total": sum(metriques["total"] for metriques in classes.values()),
        "expirees": expirees,
        "supprimables": supprimables,
        "immuables": immuables,
        "immuables_ignorees": ignorees,
        "prochaine_expiration": _iso(min(prochaines) if prochaines else None),
        "limites": limites,
        "erreurs": erreurs,
        "limite": bool(limites),
        "complet": not limites and not erreurs,
    }
    resultat.update(classes)
    return resultat


def purger(
    conn: Any, tenant_id: Any, *, dry_run: bool = True, maintenant: Any = None
) -> dict:
    """Purge à blanc par défaut ; en réel, ne supprime que le mutable échu.

    Seules les lignes de ``memoire_durable`` (session comprise) et les
    prédictions de calibration résolues et âgées de plus d'un an peuvent être
    supprimées. Les Claims, Preuves, Learnings et Outcomes sont seulement
    comptés dans ``immuables_ignorees``. Le tenant est présent dans chaque
    condition SQL ; aucune ligne d'un autre tenant n'est lue ni supprimée.
    """
    tenant = _tenant(tenant_id)
    instant = _maintenant(maintenant)
    resultat = {
        "supprimees": 0,
        "auraient_ete_supprimees": 0,
        "immuables_ignorees": 0,
        "erreurs": [],
    }
    for nom, politique in POLITIQUES.items():
        try:
            metriques, _ = _mesurer(conn, tenant, politique, instant)
        except Exception as exc:
            resultat["erreurs"].append(_erreur(nom, exc))
            continue
        if politique.supprimable:
            candidats = metriques["supprimables"]
            resultat["immuables_ignorees"] += metriques["expirees"] - candidats
            if dry_run:
                resultat["auraient_ete_supprimees"] += candidats
            elif candidats:
                try:
                    resultat["supprimees"] += _supprimer(conn, tenant, politique, instant)
                except Exception as exc:
                    if not _est_structure(exc):
                        resultat["erreurs"].append(_erreur(nom, exc))
        else:
            resultat["immuables_ignorees"] += metriques["expirees"]
    return resultat


def exporter_politique() -> dict:
    """Exporte toutes les politiques sous forme de dictionnaire sérialisable."""
    return {nom: politique.as_dict() for nom, politique in POLITIQUES.items()}


def as_dict(politique: Any = None) -> dict:
    """Rend une politique, son nom, ou l'ensemble des politiques en dictionnaire."""
    if politique is None:
        return exporter_politique()
    if isinstance(politique, str):
        return POLITIQUES[politique].as_dict()
    if isinstance(politique, Politique):
        return politique.as_dict()
    raise TypeError("politique attendue : Politique, nom connu ou None")
