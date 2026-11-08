"""Dérivation de l'état produit à partir des capacités et de leurs liens.

Le modèle ne choisit pas les statuts : il raconte. Un statut est calculé à partir de la chaîne
exposition -> consommation -> câblage -> donnée. La règle est volontairement explicite :

- ``absent`` : la capacité n'est pas atteignable depuis le produit (pas de route, pas de service,
  handler vide, composant stub, page non câblée).
- ``partiel`` : la capacité est atteignable mais pas réelle (données de démonstration).
- ``inconnu`` : un maillon existe mais sa preuve n'est pas tenue (en partie, non appuyée, incertaine).
- ``ok`` : toute la chaîne est présente et tenue.

Le module ne connaît aucune application : il reçoit des capacités et des liens, et rend les états.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

NON_TENUES = ("non_appuye", "en_partie", "incertain")
CABLAGES_ABSENTS = ("HANDLER_VIDE", "STUB", "CABLAGE_ABSENT")
CABLAGES_PARTIELS = ("DONNEES_FIXES",)


@dataclass(frozen=True)
class Lien:
    de: str
    vers: str
    type: str
    preuve: str = ""
    etat: str = ""
    predicat: str = ""
    appel: str = ""


@dataclass(frozen=True)
class EtatCapacite:
    id: str
    libelle: str
    statut: str
    preuves: tuple[str, ...] = ()
    manques: tuple[str, ...] = ()
    expose: bool | None = None
    consomme: bool | None = None
    cablage: bool | None = None
    donnee: bool | None = None
    exposition_fondement: str = ""
    donnee_fondement: str = ""
    exposition_appel: str = ""
    donnee_appel: str = ""

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "libelle": self.libelle,
            "statut": self.statut,
            "preuves": list(self.preuves),
            "manques": list(self.manques),
            "expose": self.expose,
            "consomme": self.consomme,
            "cablage": self.cablage,
            "donnee": self.donnee,
            "exposition_fondement": self.exposition_fondement,
            "donnee_fondement": self.donnee_fondement,
            "exposition_appel": self.exposition_appel,
            "donnee_appel": self.donnee_appel,
        }


def deriver(capacites, liens, claims=None, donnees_requises=None):
    """Rend un état par capacité à partir de la chaîne des liens.

    `capacites` : [{"id": "...", "libelle": "..."}]. `liens` : [Lien(...)] ou dicts équivalents.
    `claims` : {id: claim} pour lire l'état de vérification quand le lien ne le porte pas.
    `donnees_requises` : ids des capacités qui exigent une donnée ; par défaut toutes.
    """
    claims = {str(k): v for k, v in (claims or {}).items() if isinstance(v, Mapping)}
    liens = tuple(lien for lien in (_lien(valeur) for valeur in liens or ()) if lien is not None)
    capacites = [c for c in capacites or () if isinstance(c, Mapping) and c.get("id")]
    ids = {str(c["id"]) for c in capacites}
    requises = ids if donnees_requises is None else {str(i) for i in donnees_requises}
    return [_etat(c, liens, claims, str(c["id"]) in requises) for c in capacites]


def projeter(etats, titre="État produit", limite=6):
    """Projette des états dérivés en schéma : deux groupes, une boîte par capacité, API et données.

    Aucune application, aucun libellé ni statut n'est codé en dur : la projection ne fait que rendre
    les états reçus. Une capacité sans exposition n'a pas de flèche vers l'API ; une donnée absente
    laisse la boîte « Données » en `inconnu`.
    """
    etats = [e for e in (_etat_depuis(valeur) for valeur in etats or ()) if e is not None][:limite]
    boites = [{"id": f"cap-{e.id}", "libelle": e.libelle, "statut": e.statut} for e in etats]
    boites += [
        {"id": "api", "libelle": "API", "statut": _statut_api(etats)},
        {"id": "donnees", "libelle": "Données", "statut": _statut_donnees(etats)},
    ]
    groupes = [
        {"libelle": "Front-end", "ids": [b["id"] for b in boites[:len(etats)]]},
        {"libelle": "Backend", "ids": ["api", "donnees"]},
    ]
    fleches = [
        {"de": f"cap-{e.id}", "vers": "api", "libelle": "appelle",
         "fondement": e.exposition_fondement, "appel": e.exposition_appel}
        for e in etats if e.expose and e.exposition_fondement
    ]
    donnee = next((e for e in etats if e.donnee and e.donnee_fondement), None)
    if donnee is not None:
        fleches.append({"de": "api", "vers": "donnees", "libelle": "lit / écrit",
                        "fondement": donnee.donnee_fondement, "appel": donnee.donnee_appel})
    return {"type": "architecture", "titre": titre, "boites": boites,
            "groupes": groupes, "fleches": fleches}


def _etat(capacite, liens, claims, donnee_requise):
    cap_id = str(capacite["id"])
    libelle = _libelle(capacite)
    exposition = _cible(liens, cap_id, "EXPOSE_PAR")
    consommation = _cible(liens, cap_id, "CONSOMME")
    cablage = _cible(liens, cap_id, "CABLAGE")
    donnee = _cible(liens, cap_id, "DETIENT")
    preuves = _preuves(claims, (exposition, consommation, cablage, donnee))
    expose = _tient(exposition, claims) if exposition is not None else None
    consomme = _tient(consommation, claims) if consommation is not None else None
    cablage_ok = _tient(cablage, claims) and _predicat(cablage, claims) not in CABLAGES_ABSENTS
    donnee_ok = _tient(donnee, claims) if donnee_requise else None
    base = {
        "id": cap_id, "libelle": libelle, "preuves": preuves,
        "expose": expose, "consomme": consomme, "cablage": cablage_ok, "donnee": donnee_ok,
        "exposition_fondement": _fondement(exposition),
        "donnee_fondement": _fondement(donnee),
        "exposition_appel": exposition.appel if exposition else "",
        "donnee_appel": donnee.appel if donnee else "",
    }
    if exposition is None:
        return EtatCapacite(**base, statut="absent", manques=("exposition",))
    if not expose:
        return EtatCapacite(**base, statut="inconnu", manques=("exposition non tenue",))
    if consommation is None:
        return EtatCapacite(**base, statut="absent", manques=("consommation",))
    if not consomme:
        return EtatCapacite(**base, statut="inconnu", manques=("consommation non tenue",))
    predicat = _predicat(cablage, claims)
    if cablage is None or not _tient(cablage, claims) or predicat in CABLAGES_ABSENTS:
        return EtatCapacite(**base, statut="absent", manques=("câblage UI",))
    if predicat in CABLAGES_PARTIELS:
        return EtatCapacite(**base, statut="partiel", manques=("données réelles",))
    if donnee_requise and (donnee is None or not _tient(donnee, claims)):
        return EtatCapacite(**base, statut="inconnu", manques=("donnée",))
    return EtatCapacite(**base, statut="ok", manques=())


def _cible(liens, de, type_):
    return next((lien for lien in liens if lien.de == de and lien.type == type_), None)


def _tient(lien, claims):
    if lien is None:
        return False
    if lien.etat:
        return lien.etat not in NON_TENUES
    claim = claims.get(str(lien.vers))
    if claim is None:
        return bool(lien.preuve)
    if claim.get("statut") == "CONTESTED":
        return False
    etat = (claim.get("verification") or {}).get("etat")
    return bool(etat) and etat not in NON_TENUES


def _predicat(lien, claims):
    if lien is None:
        return ""
    if lien.predicat:
        return lien.predicat
    return str((claims.get(str(lien.vers)) or {}).get("predicat") or "")


def _fondement(lien):
    if lien is None:
        return ""
    return f"c:{lien.vers}" if str(lien.vers).isdigit() else lien.preuve


def _preuves(claims, liens):
    sortie = []
    for lien in liens:
        if lien is None:
            continue
        if lien.preuve:
            sortie.append(lien.preuve)
        claim = claims.get(str(lien.vers))
        if claim:
            preuves = claim.get("preuves") or claim.get("preuve")
            if isinstance(preuves, str):
                preuves = (preuves,)
            sortie.extend(str(p) for p in preuves or ())
    return tuple(dict.fromkeys(sortie))


def _statut_api(etats):
    valeurs = [e.expose for e in etats if e.expose is not None]
    if not valeurs:
        return "absent"
    if all(valeurs):
        return "ok"
    if any(valeurs):
        return "partiel"
    return "absent"


def _statut_donnees(etats):
    valeurs = [e.donnee for e in etats if e.donnee is not None]
    if not valeurs:
        return "inconnu"
    return "ok" if all(valeurs) else "inconnu"


def _etat_depuis(valeur):
    if isinstance(valeur, EtatCapacite):
        return valeur
    if not isinstance(valeur, Mapping) or not valeur.get("id"):
        return None
    return EtatCapacite(
        id=str(valeur["id"]), libelle=_libelle(valeur),
        statut=str(valeur.get("statut") or "inconnu"),
        preuves=tuple(str(p) for p in valeur.get("preuves") or ()),
        manques=tuple(str(m) for m in valeur.get("manques") or ()),
        expose=valeur.get("expose"), consomme=valeur.get("consomme"),
        cablage=valeur.get("cablage"), donnee=valeur.get("donnee"),
        exposition_fondement=str(valeur.get("exposition_fondement") or ""),
        donnee_fondement=str(valeur.get("donnee_fondement") or ""),
        exposition_appel=str(valeur.get("exposition_appel") or ""),
        donnee_appel=str(valeur.get("donnee_appel") or ""),
    )


def _libelle(capacite):
    return " ".join(str(capacite.get("libelle") or capacite.get("nom") or capacite.get("id") or "").split())


def _lien(valeur):
    if isinstance(valeur, Lien):
        return valeur
    if not isinstance(valeur, Mapping):
        return None
    de, vers, type_ = valeur.get("de"), valeur.get("vers"), valeur.get("type")
    if not de or not vers or not type_:
        return None
    return Lien(str(de), str(vers), str(type_), str(valeur.get("preuve") or ""),
                str(valeur.get("etat") or ""), str(valeur.get("predicat") or ""),
                str(valeur.get("appel") or ""))
