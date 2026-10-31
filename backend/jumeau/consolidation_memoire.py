"""Consolidation de la mémoire organisationnelle : doublons et conflits proposés, jamais appliqués.

Le module est pur : il lit les mémoires fournies en argument, ne touche à aucune base, n'appelle
aucun réseau et n'écrit rien. Il propose des groupes de fusion et signale les conflits ; toute
application exige une approbation humaine explicite via :func:`approuver`, qui ne produit elle aussi
qu'un plan. Aucun contenu de mémoire n'est recopié dans la proposition : seules les références de
preuve sont conservées, après expurgation des secrets.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
import re
import unicodedata
from typing import Any

__all__ = [
    "MAX_CONFLITS",
    "MAX_GROUPES",
    "MAX_MEMOIRES",
    "Conflit",
    "GroupeFusion",
    "PropositionConsolidation",
    "approuver",
    "fusionner_memoires",
    "proposer",
]

MAX_GROUPES = 50
MAX_CONFLITS = 50
MAX_MEMOIRES = 2000
MAX_EVIDENCES = 20
TYPES_CONFLIT = frozenset({"valeur", "fait", "preference", "scope"})

_MARQUEURS_NEGATION = frozenset({
    "non", "pas", "jamais", "aucun", "aucune", "rien", "sans", "ni", "ne", "n", "no", "not", "never",
    "none",
})
_MARQUEURS_POSITIFS = frozenset({
    "oui", "toujours", "avec", "yes", "always", "true", "certainement", "surement", "sur",
})
_MARQUEURS_PREFERENCE = frozenset({
    "prefere", "preferer", "prefere", "aime", "adore", "deteste", "veut", "souhaite", "choisit",
    "privilegie", "evite", "prefer", "like", "dislike", "want", "wish", "choose",
})
_STOPWORDS = frozenset({
    "le", "la", "les", "l", "un", "une", "des", "de", "du", "d", "et", "ou", "a", "au", "aux",
    "en", "dans", "pour", "par", "sur", "est", "sont", "ete", "etre", "ce", "cette", "ces", "il",
    "elle", "on", "nous", "vous", "ils", "elles", "que", "qui", "quoi", "dont", "the", "an", "of",
    "and", "or", "to", "in", "on", "for", "by", "with", "is", "are", "was", "were", "be", "been",
    "it", "this", "that", "these", "those",
})
_RE_CLE_VALEUR = re.compile(r"^\s*([^:=]{1,80}?)\s*(?::|=)\s*(.+?)\s*$")
_RE_SECRET = re.compile(
    r"(?i)(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|client[_-]?secret|credential|"
    r"password|passwd|mot[ _-]?de[ _-]?passe|secret|token)\s*['\"]?\s*[:=]\s*['\"]?[^'\"\s]+"
)
_RE_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*")
_RE_URL_AUTH = re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@")
_RE_JETON = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_RE_PREFIXE_SECRET = re.compile(
    r"(?i)\b(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{8,}|xox[baprs]-[A-Za-z0-9-]{8,}|"
    r"AKIA[A-Z0-9]{12,})\b"
)
_RE_TOKEN_SENSIBLE = re.compile(
    r"(?i)\S*(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|client[_-]?secret|credential|"
    r"authorization|password|passwd|motdepasse|secret|token)(?:[:=_-]|\d|\b)\S*"
)
_RANG_GRAVITE = {"haute": 0, "moyenne": 1, "normale": 1, "basse": 2}


def _texte(valeur: Any) -> str:
    if valeur is None or isinstance(valeur, (bytes, bytearray, Mapping)):
        return ""
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return ""
    return str(valeur).strip()


def _texte_ou_liste(valeur: Any) -> str:
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return " ".join(filtre for filtre in (_texte(element) for element in valeur) if filtre)
    return _texte(valeur)


def _premier_texte(memoire: Any, noms: tuple[str, ...]) -> str:
    for source in _sources(memoire):
        for nom in noms:
            if isinstance(source, Mapping):
                valeur = source.get(nom)
            else:
                valeur = getattr(source, nom, None)
            texte = _texte_ou_liste(valeur)
            if texte:
                return texte
    return ""


def _normaliser_texte(valeur: Any) -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(caractere for caractere in texte if not unicodedata.combining(caractere)).lower()
    texte = "".join(caractere if caractere.isalnum() else " " for caractere in texte)
    return " ".join(texte.split())


def _cle_stable(valeur: Any) -> str:
    if valeur is None:
        return ""
    if isinstance(valeur, str):
        return _normaliser_texte(valeur)
    if isinstance(valeur, Mapping):
        try:
            return json.dumps(valeur, ensure_ascii=False, sort_keys=True, default=str)
        except (TypeError, ValueError):
            return _normaliser_texte(valeur)
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return "|".join(sorted(_cle_stable(element) for element in valeur))
    return _normaliser_texte(valeur)


def _assainir(valeur: Any, maximum: int = 300) -> str:
    if isinstance(valeur, Mapping):
        valeur = next((
            valeur.get(cle) for cle in ("id", "locator", "url", "path", "hash", "source")
            if _texte(valeur.get(cle))
        ), "")
    texte = " ".join(str(valeur or "").split())[:maximum]
    texte = _RE_BEARER.sub("Bearer ***", texte)
    texte = _RE_SECRET.sub("***", texte)
    texte = _RE_URL_AUTH.sub(r"\1***@", texte)
    texte = _RE_JETON.sub("***", texte)
    texte = _RE_PREFIXE_SECRET.sub("***", texte)
    return _RE_TOKEN_SENSIBLE.sub("***", texte)


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


def _sources(memoire: Any) -> list[Any]:
    sources = [memoire]
    for nom in ("donnees", "metadata", "meta"):
        bloc = memoire.get(nom) if isinstance(memoire, Mapping) else getattr(memoire, nom, None)
        if isinstance(bloc, Mapping):
            sources.append(bloc)
    return sources


def _valeur(memoire: Any, *noms: str, defaut: Any = None) -> Any:
    for source in _sources(memoire):
        if isinstance(source, Mapping):
            for nom in noms:
                if nom in source and source[nom] is not None:
                    return source[nom]
        else:
            for nom in noms:
                valeur = getattr(source, nom, None)
                if valeur is not None:
                    return valeur
    return defaut


def _identifiant(valeur: Any) -> str:
    if isinstance(valeur, Mapping):
        valeur = valeur.get("id")
    return _texte(valeur)


def _confiance(valeur: Any) -> float:
    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        return 0.5
    return min(1.0, max(0.0, nombre))


def _tokens(texte: str) -> frozenset[str]:
    return frozenset(_normaliser_texte(texte).split())


def _polarite(tokens: frozenset[str]) -> tuple[bool, bool]:
    return bool(tokens & _MARQUEURS_NEGATION), bool(tokens & _MARQUEURS_POSITIFS)


def _sujet(tokens: frozenset[str]) -> frozenset[str]:
    return tokens - _MARQUEURS_NEGATION - _MARQUEURS_POSITIFS - _STOPWORDS


def _jaccard(gauche: frozenset[str], droite: frozenset[str]) -> float:
    if not gauche or not droite:
        return 0.0
    union = gauche | droite
    if not union:
        return 0.0
    return len(gauche & droite) / len(union)


def _similarite(gauche: "_Entree", droite: "_Entree") -> float:
    if gauche.contenu == droite.contenu:
        return 1.0
    return max(
        _jaccard(gauche.tokens, droite.tokens),
        _jaccard(_sujet(gauche.tokens), _sujet(droite.tokens)),
    )


def _sujet_similaire(gauche: "_Entree", droite: "_Entree", seuil: float = 0.6) -> bool:
    gauche_sujet = _sujet(gauche.tokens)
    droite_sujet = _sujet(droite.tokens)
    if not gauche_sujet or not droite_sujet:
        return False
    return _jaccard(gauche_sujet, droite_sujet) >= seuil


def _couple_cle_valeur(memoire: Any, contenu: str) -> tuple[str, str]:
    cle = _cle_stable(_valeur(memoire, "cle", "key", "sujet", "topic", "propriete", "property", "attribut"))
    valeur = _cle_stable(_valeur(memoire, "valeur", "value", "objet"))
    if cle and valeur:
        return cle, valeur
    ligne = contenu.splitlines()[0].strip() if contenu else ""
    correspondance = _RE_CLE_VALEUR.match(ligne)
    if not correspondance:
        return "", ""
    cle = _cle_stable(correspondance.group(1))
    valeur = _cle_stable(correspondance.group(2))
    if not cle or not valeur or cle.startswith("http"):
        return "", ""
    return cle, valeur


def _est_preference(memoire: Any, tokens: frozenset[str]) -> bool:
    categorie = _normaliser_texte(_valeur(memoire, "type_memoire", "categorie", "category", "genre"))
    return "preference" in categorie or bool(tokens & _MARQUEURS_PREFERENCE)


def _evidences(memoire: Any) -> tuple[str, ...]:
    resultat: list[str] = []
    for nom in ("evidences", "preuves", "evidence", "sources", "source", "provenance", "locator", "url"):
        for element in _liste(_valeur(memoire, nom)):
            if isinstance(element, Mapping):
                valeurs = [element.get(cle) for cle in ("id", "locator", "url", "path", "hash", "source")]
                element = next((valeur for valeur in valeurs if _texte(valeur)), "")
            texte = _assainir(element)
            if texte and texte not in resultat:
                resultat.append(texte)
    return tuple(sorted(resultat)[:MAX_EVIDENCES])


@dataclass(frozen=True)
class GroupeFusion:
    """Groupe de doublons proposé à la fusion : une mémoire gardée, les autres retirées après accord."""

    keep_id: str
    remove_ids: tuple[str, ...] = ()
    raison: str = ""
    confiance: float = 1.0
    evidences: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        keep_id = _identifiant(self.keep_id)
        if not keep_id:
            raise ValueError("keep_id obligatoire")
        object.__setattr__(self, "keep_id", keep_id)
        object.__setattr__(self, "remove_ids", tuple(
            identifiant for identifiant in (_identifiant(valeur) for valeur in _liste(self.remove_ids))
            if identifiant and identifiant != keep_id
        ))
        object.__setattr__(self, "raison", _assainir(self.raison))
        object.__setattr__(self, "confiance", _confiance(self.confiance))
        object.__setattr__(self, "evidences", tuple(
            texte for texte in (_assainir(valeur) for valeur in _liste(self.evidences)) if texte
        )[:MAX_EVIDENCES])

    def as_dict(self) -> dict[str, Any]:
        """Vue sérialisable du groupe, sans contenu de mémoire."""
        return {
            "keep_id": self.keep_id,
            "remove_ids": list(self.remove_ids),
            "raison": self.raison,
            "confiance": self.confiance,
            "evidences": list(self.evidences),
        }


@dataclass(frozen=True)
class Conflit:
    """Désaccord entre mémoires du même scope : il est signalé, jamais fusionné automatiquement."""

    ids: tuple[str, ...] = ()
    raison: str = ""
    type: str = "fait"
    gravite: str = "moyenne"

    def __post_init__(self) -> None:
        identifiants = tuple(
            identifiant for identifiant in (_identifiant(valeur) for valeur in _liste(self.ids)) if identifiant
        )
        object.__setattr__(self, "ids", identifiants)
        object.__setattr__(self, "raison", _assainir(self.raison))
        type_conflit = _normaliser_texte(self.type) or "fait"
        if type_conflit not in TYPES_CONFLIT:
            raise ValueError("type de conflit invalide")
        object.__setattr__(self, "type", type_conflit)
        object.__setattr__(self, "gravite", _normaliser_texte(self.gravite) or "moyenne")

    def as_dict(self) -> dict[str, Any]:
        """Vue sérialisable du conflit, sans valeur ni contenu de mémoire."""
        return {
            "ids": list(self.ids),
            "raison": self.raison,
            "type": self.type,
            "gravite": self.gravite,
        }


@dataclass(frozen=True)
class PropositionConsolidation:
    """Proposition pure : groupes de fusion et conflits, accompagnés de leurs limites."""

    groupes: tuple[GroupeFusion, ...] = ()
    conflits: tuple[Conflit, ...] = ()
    limites: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "groupes", tuple(
            groupe if isinstance(groupe, GroupeFusion) else GroupeFusion(**groupe)
            for groupe in _liste(self.groupes)
        ))
        object.__setattr__(self, "conflits", tuple(
            conflit if isinstance(conflit, Conflit) else Conflit(**conflit)
            for conflit in _liste(self.conflits)
        ))
        object.__setattr__(self, "limites", tuple(
            texte for texte in (_assainir(limite) for limite in _liste(self.limites)) if texte
        ))

    def as_dict(self) -> dict[str, Any]:
        """Vue sérialisable et déterministe de la proposition."""
        return {
            "groupes": [groupe.as_dict() for groupe in self.groupes],
            "conflits": [conflit.as_dict() for conflit in self.conflits],
            "limites": list(self.limites),
        }


@dataclass(frozen=True)
class _Entree:
    id: str
    tenant: str
    scope: str
    classe: str
    contenu: str
    tokens: frozenset[str]
    cle: str
    valeur: str
    preference: bool
    evidences: tuple[str, ...]
    confiance: float


def _preparer(memoires: Any, tenant_id: Any, limites: list[str]) -> list[_Entree]:
    if isinstance(memoires, Mapping) or memoires is None:
        brutes = [] if memoires is None else [memoires]
    else:
        try:
            brutes = list(memoires)
        except TypeError:
            brutes = [memoires]
    filtre_tenant = _texte(tenant_id) if tenant_id is not None else ""
    entrees: list[_Entree] = []
    ignorees = 0
    filtrees = 0
    sans_tenant = 0
    for memoire in brutes:
        identifiant = _identifiant(_valeur(memoire, "id", "memoire_id", "memory_id", "identifiant"))
        contenu = _premier_texte(memoire, ("contenu", "content", "texte", "text"))
        if not contenu:
            contenu = _premier_texte(memoire, ("resume", "summary", "body", "corps"))
        if not contenu:
            contenu = _premier_texte(memoire, ("titre", "title", "nom"))
        tenant = _premier_texte(memoire, ("tenant_id", "tenant"))
        if not identifiant:
            ignorees += 1
            continue
        if filtre_tenant and tenant and tenant != filtre_tenant:
            filtrees += 1
            continue
        if filtre_tenant and not tenant:
            sans_tenant += 1
            tenant = filtre_tenant
        cle, valeur = _couple_cle_valeur(memoire, contenu)
        if not contenu:
            contenu = " ".join(element for element in (cle, valeur) if element)
        if not contenu:
            ignorees += 1
            continue
        tokens = _tokens(contenu)
        classe = _premier_texte(memoire, ("classe", "class", "classe_memoire"))
        if not classe:
            classe = _premier_texte(memoire, ("genre",))
        entrees.append(_Entree(
            id=identifiant,
            tenant=tenant,
            scope=_cle_stable(_valeur(memoire, "scope", "scope_id", "portee")),
            classe=_normaliser_texte(classe),
            contenu=_normaliser_texte(contenu),
            tokens=tokens,
            cle=cle,
            valeur=valeur,
            preference=_est_preference(memoire, tokens),
            evidences=_evidences(memoire),
            confiance=_confiance(_valeur(memoire, "confiance", "confidence")),
        ))
    entrees.sort(key=lambda entree: (
        entree.tenant, entree.scope, entree.classe, entree.id, entree.contenu, entree.evidences,
    ))
    vus: set[tuple[str, str]] = set()
    uniques: list[_Entree] = []
    for entree in entrees:
        if (entree.tenant, entree.id) in vus:
            ignorees += 1
            continue
        vus.add((entree.tenant, entree.id))
        uniques.append(entree)
    entrees = uniques
    if ignorees:
        limites.append(f"{ignorees} mémoire(s) ignorée(s) : identifiant, contenu ou doublon d'identifiant invalide")
    if filtrees:
        limites.append(f"{filtrees} mémoire(s) hors du tenant demandé non comparées")
    if sans_tenant:
        limites.append(f"{sans_tenant} mémoire(s) sans tenant comparées sous le tenant demandé")
    if filtre_tenant:
        limites.append(f"comparaison bornée au tenant {_assainir(filtre_tenant, 128)}")
    if len(entrees) > MAX_MEMOIRES:
        limites.append(f"mémoires tronquées à {MAX_MEMOIRES} pour borner la comparaison")
        entrees = entrees[:MAX_MEMOIRES]
    return entrees


def _detecter_conflit(gauche: _Entree, droite: _Entree) -> Conflit | None:
    identifiants = tuple(sorted({gauche.id, droite.id}))
    if gauche.cle and droite.cle and gauche.cle == droite.cle and gauche.valeur and droite.valeur:
        if gauche.valeur != droite.valeur:
            return Conflit(
                ids=identifiants,
                raison=f"conflit de valeur : valeurs différentes pour la même clé « {_assainir(gauche.cle, 80)} »",
                type="valeur",
                gravite="haute",
            )
    gauche_negative, _ = _polarite(gauche.tokens)
    droite_negative, _ = _polarite(droite.tokens)
    if gauche_negative == droite_negative:
        return None
    if not _sujet_similaire(gauche, droite):
        return None
    type_conflit = "preference" if gauche.preference or droite.preference else "fait"
    return Conflit(
        ids=identifiants,
        raison="conflit de polarité : sujet identique, affirmations opposées",
        type=type_conflit,
        gravite="basse" if type_conflit == "preference" else "moyenne",
    )


def _former_groupes(entrees: list[_Entree], conflits: list[Conflit], seuil: float) -> list[GroupeFusion]:
    paires_conflictuelles = {frozenset(conflit.ids) for conflit in conflits if len(conflit.ids) == 2}
    par_bucket: dict[tuple[str, str, str], list[_Entree]] = {}
    for entree in entrees:
        par_bucket.setdefault((entree.tenant, entree.scope, entree.classe), []).append(entree)
    groupes: list[GroupeFusion] = []
    for bucket in sorted(par_bucket):
        membres: list[list[_Entree]] = []
        for entree in par_bucket[bucket]:
            place = None
            for groupe in membres:
                if any(frozenset({entree.id, membre.id}) in paires_conflictuelles for membre in groupe):
                    continue
                if all(_similarite(entree, membre) >= seuil for membre in groupe):
                    place = groupe
                    break
            if place is None:
                membres.append([entree])
            else:
                place.append(entree)
        for groupe in membres:
            if len(groupe) < 2:
                continue
            garde = groupe[0]
            retires = groupe[1:]
            score = min(_similarite(garde, membre) for membre in retires)
            exact = all(membre.contenu == garde.contenu for membre in retires)
            raison = (
                "doublon exact après normalisation dans le même tenant, scope et classe"
                if exact else
                f"quasi-doublon (Jaccard >= {seuil:.2f}) dans le même tenant, scope et classe"
            )
            preuves = tuple(sorted({preuve for membre in groupe for preuve in membre.evidences})[:MAX_EVIDENCES])
            groupes.append(GroupeFusion(
                keep_id=garde.id,
                remove_ids=tuple(membre.id for membre in retires),
                raison=raison,
                confiance=round(score, 4),
                evidences=preuves,
            ))
    groupes.sort(key=lambda groupe: (groupe.keep_id, groupe.remove_ids))
    return groupes


def proposer(
    memoires: Any, *, tenant_id: Any = None, seuil_similarite: float = 0.9,
) -> PropositionConsolidation:
    """Propose des fusions de doublons et des conflits sans jamais modifier ni supprimer une mémoire.

    La normalisation ignore accents, casse et espaces. Deux mémoires ne sont comparées que si elles
    partagent le même tenant, le même scope et la même classe. Un doublon exact (texte normalisé
    identique) ou un quasi-doublon (Jaccard des tokens supérieur ou égal à ``seuil_similarite``) forme
    un groupe de fusion. Un désaccord de polarité ou une même clé portant deux valeurs différentes
    devient un conflit et n'est jamais fusionné. Le résultat est déterministe et borné.
    """
    if isinstance(seuil_similarite, bool):
        raise ValueError("seuil_similarite doit être un nombre entre 0 et 1")
    try:
        seuil = float(seuil_similarite)
    except (TypeError, ValueError) as exc:
        raise ValueError("seuil_similarite doit être un nombre entre 0 et 1") from exc
    if not 0.0 <= seuil <= 1.0:
        raise ValueError("seuil_similarite doit être compris entre 0 et 1")

    limites: list[str] = []
    entrees = _preparer(memoires, tenant_id, limites)
    if not entrees:
        limites.append("aucune mémoire exploitable : proposition vide")
        limites.append("proposition seule : aucune fusion ni suppression automatique")
        return PropositionConsolidation(limites=tuple(limites))

    conflits: list[Conflit] = []
    par_bucket: dict[tuple[str, str, str], list[_Entree]] = {}
    for entree in entrees:
        par_bucket.setdefault((entree.tenant, entree.scope, entree.classe), []).append(entree)
    for bucket in sorted(par_bucket):
        lignes = par_bucket[bucket]
        for indice, gauche in enumerate(lignes):
            for droite in lignes[indice + 1:]:
                conflit = _detecter_conflit(gauche, droite)
                if conflit is not None:
                    conflits.append(conflit)
    conflits.sort(key=lambda conflit: (
        _RANG_GRAVITE.get(conflit.gravite, 1), conflit.type, conflit.ids,
    ))
    groupes = _former_groupes(entrees, conflits, seuil)
    if len(conflits) > MAX_CONFLITS:
        limites.append(f"conflits tronqués à {MAX_CONFLITS} pour borner la proposition")
        conflits_affiches = conflits[:MAX_CONFLITS]
    else:
        conflits_affiches = conflits
    if len(groupes) > MAX_GROUPES:
        limites.append(f"groupes de fusion tronqués à {MAX_GROUPES} pour borner la proposition")
        groupes = groupes[:MAX_GROUPES]
    if not groupes and not conflits_affiches:
        limites.append("aucun doublon ni conflit détecté")
    limites.append("proposition seule : aucune fusion ni suppression automatique")
    return PropositionConsolidation(
        groupes=tuple(groupes), conflits=tuple(conflits_affiches), limites=tuple(limites),
    )


def _selection(ids: Any) -> list[str]:
    resultat: list[str] = []
    for element in _liste(ids):
        identifiant = _identifiant(element)
        if identifiant and identifiant not in resultat:
            resultat.append(identifiant)
    return sorted(resultat)


def _coerce_proposition(proposition: Any) -> PropositionConsolidation:
    if isinstance(proposition, PropositionConsolidation):
        return proposition
    if not isinstance(proposition, Mapping):
        raise TypeError("proposition : PropositionConsolidation ou mapping attendu")
    groupes = []
    for brut in _liste(proposition.get("groupes") or proposition.get("fusions")):
        if isinstance(brut, GroupeFusion):
            groupes.append(brut)
        elif isinstance(brut, Mapping):
            groupes.append(GroupeFusion(
                keep_id=brut.get("keep_id", brut.get("garder")),
                remove_ids=brut.get("remove_ids", brut.get("retirer")),
                raison=brut.get("raison", ""),
                confiance=brut.get("confiance", 1.0),
                evidences=brut.get("evidences", ()),
            ))
        else:
            raise TypeError("groupe de fusion invalide")
    conflits = []
    for brut in _liste(proposition.get("conflits")):
        if isinstance(brut, Conflit):
            conflits.append(brut)
        elif isinstance(brut, Mapping):
            conflits.append(Conflit(
                ids=brut.get("ids", ()),
                raison=brut.get("raison", ""),
                type=brut.get("type", "fait"),
                gravite=brut.get("gravite", "moyenne"),
            ))
        else:
            raise TypeError("conflit invalide")
    return PropositionConsolidation(
        groupes=tuple(groupes),
        conflits=tuple(conflits),
        limites=tuple(_liste(proposition.get("limites"))),
    )


def approuver(proposition: Any, *, acteur: Any, ids: Any = None) -> dict[str, Any]:
    """Rend un plan d'application pour les seuls groupes et conflits explicitement sélectionnés.

    ``acteur`` est obligatoire. Sans ``ids`` explicites, rien n'est approuvé : aucun groupe n'est
    retenu par défaut. Un groupe est sélectionné par l'un de ses identifiants, un conflit par l'un
    des identifiants qu'il oppose. Aucune écriture, fusion ou suppression n'est exécutée : le plan
    décrit seulement ce qu'un humain autorise et ce qui reste à trancher.
    """
    acteur_texte = _texte(acteur)
    if not acteur_texte:
        raise ValueError("acteur obligatoire")
    proposition_valide = _coerce_proposition(proposition)
    selection = set(_selection(ids))
    groupes: list[dict[str, Any]] = []
    conflits: list[dict[str, Any]] = []
    connus: set[str] = set()
    for groupe in proposition_valide.groupes:
        membres = {groupe.keep_id, *groupe.remove_ids}
        connus |= membres
        if not membres & selection:
            continue
        groupes.append({
            "garder": groupe.keep_id,
            "retirer": list(groupe.remove_ids),
            "keep_id": groupe.keep_id,
            "remove_ids": list(groupe.remove_ids),
            "raison": groupe.raison,
            "confiance": groupe.confiance,
            "evidences": list(groupe.evidences),
        })
    for conflit in proposition_valide.conflits:
        identifiants = set(conflit.ids)
        connus |= identifiants
        if not identifiants & selection:
            continue
        conflits.append({
            "ids": list(conflit.ids),
            "raison": conflit.raison,
            "type": conflit.type,
            "gravite": conflit.gravite,
            "action": "trancher",
        })
    ignores = sorted(selection - connus)
    limites = list(proposition_valide.limites)
    if not selection:
        limites.append("aucune sélection explicite : aucun groupe ni conflit approuvé")
    if ignores:
        limites.append(f"identifiants inconnus ignorés : {', '.join(ignores)}")
    limites.append("plan seul : aucune écriture, fusion ou suppression n'est exécutée")
    return {
        "acteur": acteur_texte,
        "groupes": groupes,
        "conflits": conflits,
        "ignores": ignores,
        "limites": limites,
        "ecritures": False,
    }


def fusionner_memoires(proposition: Any, *, acteur: Any, ids: Any = None) -> dict[str, Any]:
    """Alias pur de :func:`approuver` : rend un plan de fusion, sans jamais toucher à un store."""
    return approuver(proposition, acteur=acteur, ids=ids)
