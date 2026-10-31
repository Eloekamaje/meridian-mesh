"""Récupération unifiée de la mémoire : durable, organisationnelle, learnings et Claims.

Le module relie les souvenirs déjà persistés en une liste de candidats classés, sans modèle
ni réseau. Chaque lecture reste bornée au tenant ; les contenus, provenances et données sont
expurgés des secrets avant de pouvoir enrichir un Context Pack. Le classement est déterministe :
phrase exacte, couverture lexicale, autorité de la source, correspondance de portée, confiance
et récence.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
import re
import unicodedata
from typing import Any

from jumeau import connaissance, depot, entreprise_depot, memoire_durable, tenant as tenant_module

__all__ = [
    "CandidatMemoire",
    "RetrievalMemoireInvalide",
    "enrichir_pack",
    "recuperer",
]

SOURCES = ("durable", "annotation", "learning", "claim")
_MAX_DURABLE = 100
_MAX_OBJETS = 200
_MAX_CLAIMS = 100
_MAX_CANDIDATS = 100
_MAX_AJOUTS = 100
_AUTORITE = {"claim": 1.0, "learning": 0.9, "annotation": 0.6, "durable": 0.5}
_CONFIANCE_DEFAUT = {"durable": 0.5, "annotation": 0.5, "learning": 0.8, "claim": 0.5}
_ORDRE_SOURCE = {"claim": 0, "learning": 1, "annotation": 2, "durable": 3}

_MARQUEURS_SECRETS = ("password", "passwd", "secret", "token", "credential", "authorization")
_CLES_SECRETES = frozenset({
    "pwd", "pass", "auth", "key", "apikey", "api_key", "api-key", "access_key", "accesskey",
    "private_key", "privatekey", "client_secret", "clientsecret", "bearer", "password", "passwd",
})
_RE_AFFECTATION = re.compile(
    r"(?i)(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|client[_-]?secret|"
    r"credential|password|passwd|mot[\s_-]*de[\s_-]*passe|secret|token)\s*[:=]\s*['\"]?"
    r"[A-Za-z0-9_./+~-]{6,}"
)
_RE_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_.~+/=-]{12,}")
_RE_URL_AUTH = re.compile(r"(?i)([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@")
_RE_JETON = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_RE_PREFIXE = re.compile(
    r"(?i)\b(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{8,}|"
    r"xox[baprs]-[A-Za-z0-9-]{8,}|AKIA[A-Z0-9]{12,})\b"
)


class RetrievalMemoireInvalide(ValueError):
    """Un paramètre de récupération est invalide."""


@dataclass(frozen=True)
class CandidatMemoire:
    """Un souvenir candidat, rangé et assaini, prêt à enrichir un Context Pack."""

    id: str
    source: str
    classe: str
    contenu: str
    provenance: str
    scope: str = ""
    scope_id: str = ""
    confiance: float = 0.0
    preuves: tuple[str, ...] = ()
    score: float = 0.0
    raisons: tuple[str, ...] = ()
    donnees: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        """Rend une copie JSON-compatible, sans partager les structures internes."""
        return {
            "id": self.id,
            "source": self.source,
            "classe": self.classe,
            "contenu": self.contenu,
            "provenance": self.provenance,
            "scope": self.scope,
            "scope_id": self.scope_id,
            "confiance": self.confiance,
            "preuves": list(self.preuves),
            "score": self.score,
            "raisons": list(self.raisons),
            "donnees": deepcopy(self.donnees),
        }


def _tenant(tenant_id: Any) -> str:
    try:
        return tenant_module.exiger_tenant(tenant_id).id
    except tenant_module.TenantError as exc:
        raise RetrievalMemoireInvalide(str(exc)) from exc


def _texte(valeur: Any, maximum: int = 2000) -> str:
    if valeur is None or isinstance(valeur, (Mapping, list, tuple, set, frozenset)):
        return ""
    return str(valeur).strip()[:maximum]


def _liste(valeur: Any) -> list[Any]:
    if valeur is None:
        return []
    if isinstance(valeur, (str, bytes, bytearray, Mapping)):
        return [valeur]
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return list(valeur)
    if isinstance(valeur, Iterable):
        return list(valeur)
    return [valeur]


def _liste_ids(valeur: Any) -> list[str]:
    resultat: list[str] = []
    for element in _liste(valeur):
        if isinstance(element, Mapping):
            element = element.get("id")
        texte = _texte(element, 200)
        if texte and texte not in resultat:
            resultat.append(texte)
    return resultat


def _donnees(ligne: Any) -> Mapping[str, Any]:
    if not isinstance(ligne, Mapping):
        return {}
    donnees = ligne.get("donnees")
    return donnees if isinstance(donnees, Mapping) else {}


def _ids_lies(ligne: Any, *noms: str) -> list[str]:
    resultat: list[str] = []
    if not isinstance(ligne, Mapping):
        return resultat
    for nom in noms:
        for conteneur in (_donnees(ligne), ligne):
            if isinstance(conteneur, Mapping) and nom in conteneur:
                for identifiant in _liste_ids(conteneur[nom]):
                    if identifiant not in resultat:
                        resultat.append(identifiant)
    return resultat


def _normaliser(valeur: Any) -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(caractere for caractere in texte if not unicodedata.combining(caractere)).lower()
    texte = "".join(caractere if caractere.isalnum() else " " for caractere in texte)
    return " ".join(texte.split())


def _tokens_utiles(question: Any) -> set[str]:
    tokens = set(_normaliser(question).split())
    return {token for token in tokens if len(token) > 2} or tokens


def _couverture(tokens: set[str], texte: str) -> int:
    if not tokens:
        return 0
    return len(tokens & set(texte.split()))


def _json_stable(valeur: Any) -> str:
    try:
        return json.dumps(valeur, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return str(valeur)


def _cle_sensible(cle: Any) -> bool:
    normalisee = str(cle).strip().lower()
    if normalisee.endswith(("_ref", "-ref", "_reference", "-reference")):
        return False
    compacte = normalisee.replace("-", "_")
    if compacte in _CLES_SECRETES or compacte.endswith("_key"):
        return True
    return any(marque in compacte for marque in _MARQUEURS_SECRETS)


def _assainir_texte(valeur: Any, maximum: int = 2000) -> str:
    texte = " ".join(str(valeur or "").split())[:maximum]
    texte = _RE_BEARER.sub("***", texte)
    texte = _RE_AFFECTATION.sub("***", texte)
    texte = _RE_URL_AUTH.sub(r"\1***@", texte)
    texte = _RE_JETON.sub("***", texte)
    return _RE_PREFIXE.sub("***", texte)


def _assainir_donnees(valeur: Any, profondeur: int = 0) -> Any:
    if profondeur > 8:
        return ""
    if isinstance(valeur, Mapping):
        resultat: dict[str, Any] = {}
        for cle, element in valeur.items():
            nom = str(cle)
            if _cle_sensible(nom):
                continue
            resultat[nom] = _assainir_donnees(element, profondeur + 1)
        return resultat
    if isinstance(valeur, (list, tuple, set, frozenset)):
        elements = [_assainir_donnees(element, profondeur + 1) for element in valeur]
        if isinstance(valeur, (set, frozenset)):
            elements.sort(key=lambda element: _json_stable(element))
        return elements
    if isinstance(valeur, str):
        return _assainir_texte(valeur)
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    if isinstance(valeur, Decimal):
        return float(valeur)
    if isinstance(valeur, float) and not math.isfinite(valeur):
        return 0.0
    if valeur is None or isinstance(valeur, (bool, int, float)):
        return valeur
    return _assainir_texte(valeur)


def _instant(valeur: Any) -> float:
    if isinstance(valeur, datetime):
        instant = valeur
    elif isinstance(valeur, date):
        instant = datetime(valeur.year, valeur.month, valeur.day, tzinfo=timezone.utc)
    elif isinstance(valeur, str) and valeur.strip():
        try:
            instant = datetime.fromisoformat(valeur.strip().replace("Z", "+00:00"))
        except ValueError:
            return 0.0
    else:
        return 0.0
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.timestamp()


def _recence_ligne(ligne: Any) -> float:
    valeurs: list[float] = []
    for conteneur in (_donnees(ligne), ligne):
        if not isinstance(conteneur, Mapping):
            continue
        for champ in ("maj_le", "cree_le", "observe_le", "valide_depuis", "enregistre_le"):
            instant = _instant(conteneur.get(champ))
            if instant:
                valeurs.append(instant)
    return max(valeurs, default=0.0)


def _nombre(valeur: Any, defaut: float = 0.0) -> float:
    if isinstance(valeur, bool):
        return defaut
    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        return defaut
    return nombre if math.isfinite(nombre) else defaut


def _confiance(valeur: Any, defaut: float = 0.5) -> float:
    nombre = _nombre(valeur, defaut)
    return max(0.0, min(nombre, 1.0))


def _preuves(*valeurs: Any) -> tuple[str, ...]:
    resultat: list[str] = []
    for valeur in valeurs:
        for element in _liste(valeur):
            if isinstance(element, Mapping):
                element = (element.get("locator") or element.get("id")
                           or element.get("preuve_id") or element.get("url"))
            texte = _assainir_texte(_texte(element, 500), 500)
            if texte and texte not in resultat:
                resultat.append(texte)
    return tuple(resultat)


def _limite(valeur: Any) -> int:
    if isinstance(valeur, bool):
        raise RetrievalMemoireInvalide("limite doit être un entier positif")
    try:
        borne = int(valeur)
    except (TypeError, ValueError) as exc:
        raise RetrievalMemoireInvalide("limite doit être un entier positif") from exc
    if borne < 1:
        raise RetrievalMemoireInvalide("limite doit être un entier positif")
    return min(borne, _MAX_CANDIDATS)


def _scope(valeur: Any) -> str | None:
    if valeur is None:
        return None
    texte = _texte(valeur, 80).lower()
    if texte not in memoire_durable.SCOPES:
        raise RetrievalMemoireInvalide(
            f"scope inconnu : {valeur!r} (attendus : {', '.join(memoire_durable.SCOPES)})"
        )
    return texte


def _portee(
    liens_situations: set[str], liens_twins: set[str], twin_ids: set[str],
    situation_id: str | None, defaut: str,
) -> tuple[str, str]:
    if situation_id and situation_id in liens_situations:
        return "situation", situation_id
    if liens_situations:
        return "situation", sorted(liens_situations)[0]
    communs = sorted(twin_ids & liens_twins)
    if communs:
        return "twin", communs[0]
    if liens_twins:
        return "twin", sorted(liens_twins)[0]
    return defaut, ""


def _candidats_durables(
    conn: Any, tenant: str, tokens: set[str], scope: str | None, scope_id: str | None,
) -> list[dict]:
    lignes = memoire_durable.lister(
        conn, tenant, scope=scope, scope_id=scope_id, limite=_MAX_DURABLE)
    maintenant = datetime.now(timezone.utc).timestamp()
    resultat: list[dict] = []
    for ligne in lignes or []:
        if not isinstance(ligne, Mapping):
            continue
        expiration = _instant(ligne.get("expire_le"))
        if expiration and expiration <= maintenant:
            continue
        donnees = _donnees(ligne)
        contenu = _texte(ligne.get("contenu"))
        provenance = _texte(ligne.get("provenance"))
        texte = _normaliser(" ".join((
            contenu, provenance, _texte(ligne.get("classe")),
            _texte(ligne.get("scope_id")), _json_stable(donnees),
        )))
        if tokens and not _couverture(tokens, texte):
            continue
        resultat.append({
            "id": _texte(ligne.get("id")),
            "source": "durable",
            "classe": _texte(ligne.get("classe")) or "contexte",
            "contenu": _assainir_texte(contenu),
            "provenance": _assainir_texte(provenance),
            "scope": _texte(ligne.get("scope")) or "session",
            "scope_id": _texte(ligne.get("scope_id")),
            "confiance": _confiance(ligne.get("confiance"), _CONFIANCE_DEFAUT["durable"]),
            "preuves": _preuves(donnees.get("preuve_ids"), donnees.get("preuves"),
                                donnees.get("preuve")),
            "donnees": _assainir_donnees(donnees),
            "recence": _recence_ligne(ligne),
        })
    return resultat


def _candidats_annotations(
    conn: Any, tenant: str, tokens: set[str], twin_ids: set[str], situation_id: str | None,
) -> list[dict]:
    lignes = entreprise_depot.lister_objets(
        conn, tenant, type_="ANNOTATION", limite=_MAX_OBJETS)
    resultat: list[dict] = []
    for ligne in lignes or []:
        if not isinstance(ligne, Mapping):
            continue
        donnees = _donnees(ligne)
        contenu = _texte(donnees.get("contenu")) or _texte(ligne.get("titre"))
        if not contenu:
            continue
        liens_twins = set(_ids_lies(ligne, "twin_ids", "source_twin_ids"))
        liens_situations = set(_ids_lies(
            ligne, "situation_id", "situation_ids", "source_situation_ids"))
        texte = _normaliser(" ".join((
            _texte(ligne.get("titre")), contenu, _texte(donnees.get("genre")),
            _texte(donnees.get("source")), " ".join(sorted(liens_twins)),
            " ".join(sorted(liens_situations)), _json_stable(donnees),
        )))
        if tokens and not _couverture(tokens, texte):
            continue
        scope, scope_id = _portee(
            liens_situations, liens_twins, twin_ids, situation_id, "annotation")
        resultat.append({
            "id": _texte(ligne.get("id")),
            "source": "annotation",
            "classe": _texte(donnees.get("genre")) or "annotation",
            "contenu": _assainir_texte(contenu),
            "provenance": _assainir_texte(_texte(donnees.get("source")) or "annotation"),
            "scope": scope,
            "scope_id": scope_id,
            "confiance": _confiance(donnees.get("confiance"), _CONFIANCE_DEFAUT["annotation"]),
            "preuves": _preuves(donnees.get("preuve_ids"), donnees.get("preuves"),
                                donnees.get("preuve")),
            "donnees": _assainir_donnees(donnees),
            "recence": _recence_ligne(ligne),
        })
    return resultat


def _candidats_learnings(
    conn: Any, tenant: str, tokens: set[str], twin_ids: set[str], situation_id: str | None,
) -> list[dict]:
    lignes = entreprise_depot.lister_objets(conn, tenant, type_="LEARNING", limite=_MAX_OBJETS)
    resultat: list[dict] = []
    for ligne in lignes or []:
        if not isinstance(ligne, Mapping):
            continue
        donnees = _donnees(ligne)
        contenu = (_texte(donnees.get("enonce")) or _texte(donnees.get("resume"))
                   or _texte(ligne.get("titre")))
        if not contenu:
            continue
        liens_twins = set(_ids_lies(ligne, "twin_ids", "source_twin_ids"))
        liens_situations = set(_ids_lies(
            ligne, "situation_id", "situation_ids", "source_situation_ids"))
        ancre = bool(situation_id and situation_id in liens_situations)
        ancre = ancre or bool(twin_ids & liens_twins)
        texte = _normaliser(" ".join((
            _texte(ligne.get("titre")), contenu, _texte(donnees.get("acteur")),
            " ".join(sorted(liens_twins)), " ".join(sorted(liens_situations)),
            _json_stable(donnees),
        )))
        if tokens and not _couverture(tokens, texte) and not ancre:
            continue
        scope, scope_id = _portee(
            liens_situations, liens_twins, twin_ids, situation_id, "learning")
        resultat.append({
            "id": _texte(ligne.get("id")),
            "source": "learning",
            "classe": "apprentissage",
            "contenu": _assainir_texte(contenu),
            "provenance": _assainir_texte(
                _texte(donnees.get("acteur")) or _texte(donnees.get("initiative_id")) or "learning"),
            "scope": scope,
            "scope_id": scope_id,
            "confiance": _confiance(donnees.get("confiance"), _CONFIANCE_DEFAUT["learning"]),
            "preuves": _preuves(donnees.get("preuve_ids"), donnees.get("preuves"),
                                donnees.get("preuve")),
            "donnees": _assainir_donnees(donnees),
            "recence": _recence_ligne(ligne),
        })
    return resultat


def _twin_autorise(conn: Any, tenant: str, twin_id: str) -> bool:
    try:
        ligne = depot.jumeau_par_id(conn, twin_id)
    except AttributeError:
        return True
    if not isinstance(ligne, Mapping):
        return False
    return _texte(ligne.get("tenant_id")) == tenant


def _candidats_claims(conn: Any, tenant: str, twin_ids: list[str]) -> list[dict]:
    resultat: list[dict] = []
    for twin_id in twin_ids:
        if not _twin_autorise(conn, tenant, twin_id):
            continue
        lignes = connaissance.connaissances(conn, twin_id, limite=_MAX_CLAIMS)
        for claim in lignes or []:
            if not isinstance(claim, Mapping):
                continue
            sujet = _texte(claim.get("sujet"))
            predicat = _texte(claim.get("predicat"))
            objet = _texte(claim.get("objet"))
            contenu = " ".join(element for element in (sujet, predicat, objet) if element)
            if not contenu:
                continue
            classe = (_texte(claim.get("type")) or predicat or "claim").lower()
            resultat.append({
                "id": _texte(claim.get("id")) or f"{twin_id}:{predicat}:{objet}",
                "source": "claim",
                "classe": classe,
                "contenu": _assainir_texte(contenu),
                "provenance": _assainir_texte(f"claim:{twin_id}"),
                "scope": "twin",
                "scope_id": twin_id,
                "confiance": _confiance(claim.get("confiance"), _CONFIANCE_DEFAUT["claim"]),
                "preuves": _preuves(claim.get("preuve"), claim.get("preuves"),
                                    claim.get("preuve_ids")),
                "donnees": _assainir_donnees({
                    "predicat": predicat,
                    "type": claim.get("type"),
                    "statut": claim.get("statut"),
                    "maturite": claim.get("maturite"),
                    "verification": claim.get("verification"),
                    "jumeau_id": twin_id,
                }),
                "recence": _recence_ligne(claim),
            })
    return resultat


def _meilleur_brut(gauche: Mapping, droite: Mapping) -> bool:
    cle_gauche = (
        _confiance(gauche.get("confiance"), 0.5),
        _nombre(gauche.get("recence"), 0.0),
        len(_texte(gauche.get("contenu"))),
    )
    cle_droite = (
        _confiance(droite.get("confiance"), 0.5),
        _nombre(droite.get("recence"), 0.0),
        len(_texte(droite.get("contenu"))),
    )
    return cle_gauche > cle_droite


def _dedupliquer(bruts: list[dict]) -> list[dict]:
    meilleurs: dict[tuple[str, str], dict] = {}
    for brut in bruts:
        cle = (brut["source"], _texte(brut.get("id")))
        actuel = meilleurs.get(cle)
        if actuel is None or _meilleur_brut(brut, actuel):
            meilleurs[cle] = brut
    return list(meilleurs.values())


def _classer(
    bruts: list[dict], question: str, *, scope: str | None, scope_id: str | None,
    twin_ids: set[str], situation_id: str | None, limite: int,
) -> list[CandidatMemoire]:
    if not bruts:
        return []
    normalisee = _normaliser(question)
    tokens = _tokens_utiles(question)
    recences = [_nombre(brut.get("recence"), 0.0) for brut in bruts]
    maximum = max(recences, default=0.0)
    classes: list[CandidatMemoire] = []
    for brut in bruts:
        texte = _normaliser(" ".join((
            _texte(brut.get("contenu")), _texte(brut.get("provenance")),
            _texte(brut.get("classe")), _texte(brut.get("scope")),
            _texte(brut.get("scope_id")), _json_stable(brut.get("donnees")),
        )))
        couverts = _couverture(tokens, texte)
        couverture = couverts / len(tokens) if tokens else 0.0
        phrase = bool(normalisee) and normalisee in texte
        autorite = _AUTORITE.get(brut["source"], 0.4)
        portee = 1.0 if scope and brut.get("scope") == scope else 0.0
        portee_id = 1.0 if scope_id and brut.get("scope_id") == scope_id else 0.0
        contexte = 0.0
        if situation_id and brut.get("scope") == "situation" and brut.get("scope_id") == situation_id:
            contexte = 1.0
        elif brut.get("scope") == "twin" and brut.get("scope_id") in twin_ids:
            contexte = 1.0
        elif brut.get("scope_id") and brut.get("scope_id") in twin_ids:
            contexte = 1.0
        confiance = _confiance(brut.get("confiance"), _CONFIANCE_DEFAUT.get(brut["source"], 0.5))
        recence = (_nombre(brut.get("recence"), 0.0) / maximum) if maximum else 0.0
        score = round(
            3.0 * (1.0 if phrase else 0.0) + 2.5 * couverture + 1.2 * autorite
            + 1.0 * portee + 0.8 * portee_id + 0.7 * contexte
            + 1.0 * confiance + 0.5 * recence,
            6,
        )
        raisons: list[str] = []
        if phrase:
            raisons.append("phrase exacte")
        if tokens:
            raisons.append(f"couverture {couverts}/{len(tokens)}")
        raisons.append(f"source {brut['source']}")
        if portee:
            raisons.append(f"portée {scope}")
        if portee_id:
            raisons.append("portée id exacte")
        if contexte:
            raisons.append("contexte twin/situation")
        raisons.append(f"confiance {confiance:.2f}")
        if recence > 0:
            raisons.append("récence")
        classes.append(CandidatMemoire(
            id=_texte(brut.get("id")),
            source=brut["source"],
            classe=_texte(brut.get("classe")),
            contenu=_texte(brut.get("contenu")),
            provenance=_texte(brut.get("provenance")),
            scope=_texte(brut.get("scope")),
            scope_id=_texte(brut.get("scope_id")),
            confiance=confiance,
            preuves=tuple(brut.get("preuves") or ()),
            score=score,
            raisons=tuple(raisons),
            donnees=dict(brut.get("donnees") or {}),
        ))
    classes.sort(key=lambda candidat: (
        -candidat.score, _ORDRE_SOURCE.get(candidat.source, 9), candidat.id, candidat.source))
    return classes[:limite]


def recuperer(
    conn: Any, tenant_id: Any, *, question: Any = "", twin_ids: Any = (),
    situation_id: Any = None, scope: Any = None, scope_id: Any = None, limite: Any = 12,
) -> list[CandidatMemoire]:
    """Récupère et classe les souvenirs pertinents du tenant, sans modèle ni réseau.

    Les entrées durables sont lues via :func:`jumeau.memoire_durable.lister` avec la portée
    demandée, puis filtrées sur ``expire_le`` et sur la question. Les annotations et les
    learnings sont lus dans le dépôt d'entreprise ; un learning ancré sur la situation ou un
    Twin reste candidat même sans recouvrement lexical. Les Claims ne sont lus que pour des
    ``twin_ids`` explicites, après vérification que chaque Twin appartient au tenant. Les
    doublons ``(source, id)`` sont fusionnés, les secrets sont retirés et le résultat est
    borné par ``limite``.
    """
    tenant = _tenant(tenant_id)
    texte_question = _texte(question, 4000)
    twins_liste = _liste_ids(twin_ids)
    twins = set(twins_liste)
    situation = _texte(situation_id, 200) or None
    scope_valide = _scope(scope)
    scope_id_valide = _texte(scope_id, 200) or None
    borne = _limite(limite)
    tokens = _tokens_utiles(texte_question)

    bruts: list[dict] = []
    bruts.extend(_candidats_durables(conn, tenant, tokens, scope_valide, scope_id_valide))
    bruts.extend(_candidats_annotations(conn, tenant, tokens, twins, situation))
    bruts.extend(_candidats_learnings(conn, tenant, tokens, twins, situation))
    bruts.extend(_candidats_claims(conn, tenant, twins_liste))
    return _classer(
        _dedupliquer(bruts), texte_question, scope=scope_valide, scope_id=scope_id_valide,
        twin_ids=twins, situation_id=situation, limite=borne,
    )


def _pack_en_dict(pack: Any) -> dict:
    if isinstance(pack, Mapping):
        return deepcopy(dict(pack))
    convertisseur = getattr(pack, "as_dict", None)
    if callable(convertisseur):
        return deepcopy(convertisseur())
    if hasattr(pack, "__dict__"):
        return deepcopy(vars(pack))
    raise TypeError("pack : ContextPack, espace de noms ou dict attendu")


def _candidat_en_dict(candidat: Any) -> dict | None:
    if isinstance(candidat, CandidatMemoire):
        donnees = candidat.as_dict()
    elif isinstance(candidat, Mapping):
        donnees = deepcopy(dict(candidat))
    else:
        convertisseur = getattr(candidat, "as_dict", None)
        if not callable(convertisseur):
            return None
        donnees = deepcopy(convertisseur())
    identifiant = _texte(donnees.get("id"), 200)
    contenu = _assainir_texte(donnees.get("contenu"))
    if not identifiant or not contenu:
        return None
    brut = donnees.get("donnees")
    return {
        "id": identifiant,
        "source": _texte(donnees.get("source"), 40).lower() or "durable",
        "classe": _assainir_texte(donnees.get("classe"), 200),
        "contenu": contenu,
        "provenance": _assainir_texte(donnees.get("provenance"), 400),
        "scope": _texte(donnees.get("scope"), 80),
        "scope_id": _texte(donnees.get("scope_id"), 200),
        "confiance": _confiance(donnees.get("confiance"), 0.5),
        "preuves": list(_preuves(donnees.get("preuves"))),
        "score": _nombre(donnees.get("score"), 0.0),
        "raisons": [
            _assainir_texte(raison, 200) for raison in _liste(donnees.get("raisons"))
            if _texte(raison)
        ],
        "donnees": _assainir_donnees(brut if isinstance(brut, Mapping) else {}),
    }


def _fingerprint_memoire(memoire: list[dict]) -> str:
    charge = sorted(
        (str(element.get("id") or ""), str(element.get("contenu") or ""))
        for element in memoire
    )
    texte = json.dumps(charge, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def enrichir_pack(pack: Any, candidats: Any, *, max_ajouts: Any = 6) -> dict:
    """Rend une copie du pack enrichie d'une liste ``memoire`` bornée et empreintée.

    ``pack`` peut être un :class:`jumeau.contexte.ContextePack`, un espace de noms ou un
    dictionnaire ; la source n'est jamais mutée. ``candidats`` peut contenir des
    :class:`CandidatMemoire` ou des dictionnaires équivalents. Les secrets sont retirés une
    seconde fois et ``fingerprint_memoire`` est un SHA-256 stable des identifiants et contenus
    retenus, indépendant de l'ordre des candidats.
    """
    if isinstance(max_ajouts, bool):
        raise RetrievalMemoireInvalide("max_ajouts doit être un entier positif ou nul")
    try:
        ajouts = int(max_ajouts)
    except (TypeError, ValueError) as exc:
        raise RetrievalMemoireInvalide("max_ajouts doit être un entier positif ou nul") from exc
    if ajouts < 0:
        raise RetrievalMemoireInvalide("max_ajouts doit être un entier positif ou nul")
    ajouts = min(ajouts, _MAX_AJOUTS)

    base = _pack_en_dict(pack)
    memoire: list[dict] = []
    vus: set[tuple[str, str]] = set()
    for candidat in _liste(candidats):
        if len(memoire) >= ajouts:
            break
        converti = _candidat_en_dict(candidat)
        if converti is None:
            continue
        cle = (converti["source"], converti["id"])
        if cle in vus:
            continue
        vus.add(cle)
        memoire.append(converti)
    base["memoire"] = memoire
    base["fingerprint_memoire"] = _fingerprint_memoire(memoire)
    return base
