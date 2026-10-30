"""Évaluation hors ligne des choix d'outils et de la qualité des décisions.

Le module note un sélectionneur fourni contre un jeu d'or : aucun modèle, aucun réseau, aucune base.
Il sert de porte mesurable contre les régressions cognitives.

Politique de score d'un essai :
- un essai est exact si l'ensemble choisi égale l'ensemble attendu, ne contient aucun outil interdit
  et respecte les critères déclarés ;
- la couverture partielle vaut |choisis ∩ attendus| / |attendus| ; les outils en trop réduisent encore
  le score ; un outil interdit ou un critère non respecté met le score à zéro ;
- must_cite_preuve n'est exigé que si le sélectionneur fournit un texte : une sélection de tools seule
  n'affirme aucune preuve ;
- pass@k retient le meilleur essai parmi k essais ; `repetitions` répète ce groupe et le score du cas
  est la moyenne des meilleurs essais, tandis que le cas passe dès qu'un essai exact existe.

Les noms d'outils sont assainis avant d'entrer dans un résultat ; aucun secret n'est recopié.
"""
from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
import inspect
import json
import math
from pathlib import Path
import re
import sys
import time
from typing import Any

from jumeau.capacites import manifestes_integres

__all__ = [
    "CasInvalide",
    "CasOr",
    "ResultatCas",
    "JeuOr",
    "JEU_COGNITIF",
    "SCHEMA_CAS",
    "SCHEMA_JEU",
    "evaluer",
    "seuils",
    "valider",
    "main",
]

MAX_OCTETS_JEU = 1_000_000
MAX_CAS = 500
MAX_PROFONDEUR = 20
MAX_ESSAIS = 100
LONGUEUR_NOM = 160

_RE_AFFECTATION_SENSIBLE = re.compile(
    r"(?i)(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|client[_-]?secret|"
    r"password|passwd|mot[\s_-]*de[\s_-]*passe|secret|token)\s*[:=]\s*['\"]?"
    r"[A-Za-z0-9_./+~-]{6,}"
)
_RE_JETON_SENSIBLE = re.compile(
    r"(?i)(?:\bbearer\s+[A-Za-z0-9_.~+/=-]{12,}|\bsk-[A-Za-z0-9_-]{8,}|"
    r"\bgh[pousr]_[A-Za-z0-9]{10,}|\bxox[baprs]-[A-Za-z0-9-]{10,})"
)
_RE_CLE_SENSIBLE = re.compile(
    r"(?i)(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|client[_-]?secret|"
    r"password|passwd|mot[_-]?de[_-]?passe|secret|token|authorization|credential|"
    r"private[_-]?key|session[_-]?id|cookie)"
)
_RE_URL_AUTH = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s/@]+:[^\s/@]+@")
_RE_CITATION = re.compile(
    r"(?:(?!git)[a-z]+://[\w.-]+/[\w.-]+@[\w.-]+#L\d+(?:-L\d+)?|"
    r"(?:(?:git://[^\s@`]+@[0-9a-f]+:)|(?:[A-Za-z0-9_.-]+:))?"
    r"[A-Za-z_][\w./-]*\.[A-Za-z]\w*#L\d+(?:-L\d+)?)"
)
_RE_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")
_MOTS_ECRITURE = frozenset({
    "creer", "create", "ecrire", "write", "modifier", "update", "supprimer", "delete",
    "publier", "publish", "envoyer", "send", "executer", "execute", "ajouter", "add",
    "remplacer", "replace", "post", "put", "patch", "mettre", "ouvrir", "open",
    "fermer", "close", "demarrer", "start", "arreter", "stop",
})


class CasInvalide(ValueError):
    """Le cas ou le jeu ne respecte pas le schéma attendu."""


def _secret(texte: str) -> bool:
    return bool(_RE_AFFECTATION_SENSIBLE.search(texte) or _RE_JETON_SENSIBLE.search(texte)
                or _RE_URL_AUTH.search(texte))


def _assainir(valeur: Any, maximum: int = LONGUEUR_NOM) -> str:
    texte = str(valeur if valeur is not None else "")
    texte = _RE_CONTROLE.sub(" ", texte)
    texte = " ".join(texte.split())
    texte = _RE_URL_AUTH.sub("***@", texte)
    texte = _RE_AFFECTATION_SENSIBLE.sub("***", texte)
    texte = _RE_JETON_SENSIBLE.sub("***", texte)
    return texte[:maximum]


def _texte(valeur: Any, champ: str, maximum: int) -> str:
    if not isinstance(valeur, str):
        raise CasInvalide(f"{champ} : chaîne attendue")
    texte = " ".join(valeur.split())
    if not texte:
        raise CasInvalide(f"{champ} : valeur vide")
    if len(texte) > maximum:
        raise CasInvalide(f"{champ} : valeur trop longue")
    if _secret(texte):
        raise CasInvalide(f"{champ} : secret détecté")
    return texte


def _nom_outil(valeur: Any, champ: str) -> str:
    if not isinstance(valeur, str):
        raise CasInvalide(f"{champ} : chaîne attendue")
    nom = valeur.strip()
    if not nom:
        raise CasInvalide(f"{champ} : valeur vide")
    if len(nom) > LONGUEUR_NOM:
        raise CasInvalide(f"{champ} : nom trop long")
    if _RE_CONTROLE.search(nom) or any(caractere.isspace() for caractere in nom):
        raise CasInvalide(f"{champ} : nom d'outil invalide")
    if _secret(nom):
        raise CasInvalide(f"{champ} : secret détecté")
    return nom


def _liste_noms(valeur: Any, champ: str) -> tuple[str, ...]:
    if valeur is None:
        return ()
    if isinstance(valeur, str):
        valeurs = [valeur]
    elif isinstance(valeur, (list, tuple, set, frozenset)):
        valeurs = list(valeur)
    else:
        raise CasInvalide(f"{champ} : liste de noms attendue")
    noms: list[str] = []
    for element in valeurs:
        nom = _nom_outil(element, champ)
        if nom not in noms:
            noms.append(nom)
    return tuple(noms)


def _criteres(valeur: Any) -> dict:
    if valeur is None:
        return {}
    if not isinstance(valeur, Mapping):
        raise CasInvalide("criteres : objet attendu")
    resultat: dict = {}
    for cle, contenu in valeur.items():
        if not isinstance(cle, str) or not cle.strip():
            raise CasInvalide("criteres : clé invalide")
        nom = cle.strip()
        if _secret(nom) or _secret(str(contenu)):
            raise CasInvalide("criteres : secret détecté")
        if not isinstance(contenu, (bool, int, float, str, type(None))):
            raise CasInvalide(f"criteres.{nom} : valeur scalaire attendue")
        if isinstance(contenu, float) and not math.isfinite(contenu):
            raise CasInvalide(f"criteres.{nom} : nombre non fini")
        resultat[nom] = contenu
    return resultat


def _tags(valeur: Any) -> tuple[str, ...]:
    if valeur is None:
        return ()
    if isinstance(valeur, str):
        valeurs = [valeur]
    elif isinstance(valeur, (list, tuple, set, frozenset)):
        valeurs = list(valeur)
    else:
        raise CasInvalide("tags : liste de chaînes attendue")
    resultat: list[str] = []
    for element in valeurs:
        tag = _texte(element, "tags", 40)
        if tag not in resultat:
            resultat.append(tag)
    return tuple(resultat)


def _poids(valeur: Any) -> float:
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        raise CasInvalide("poids : nombre attendu")
    poids = float(valeur)
    if not math.isfinite(poids) or poids <= 0:
        raise CasInvalide("poids : nombre fini strictement positif attendu")
    return poids


@dataclass(frozen=True)
class CasOr:
    """Un cas du jeu d'or : outils attendus, outils interdits, critères et métadonnées."""

    id: str
    question: str
    outils_attendus: tuple[str, ...]
    outils_interdits: tuple[str, ...] = ()
    criteres: dict = field(default_factory=dict)
    poids: float = 1.0
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        identifiant = _texte(self.id, "id", 120)
        question = _texte(self.question, "question", 4000)
        attendus = _liste_noms(self.outils_attendus, "outils_attendus")
        interdits = _liste_noms(self.outils_interdits, "outils_interdits")
        if set(attendus) & set(interdits):
            raise CasInvalide(f"cas {identifiant} : un outil ne peut être attendu et interdit")
        object.__setattr__(self, "id", identifiant)
        object.__setattr__(self, "question", question)
        object.__setattr__(self, "outils_attendus", attendus)
        object.__setattr__(self, "outils_interdits", interdits)
        object.__setattr__(self, "criteres", _criteres(self.criteres))
        object.__setattr__(self, "poids", _poids(self.poids))
        object.__setattr__(self, "tags", _tags(self.tags))

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "question": self.question,
            "outils_attendus": list(self.outils_attendus),
            "outils_interdits": list(self.outils_interdits),
            "criteres": dict(self.criteres),
            "poids": self.poids,
            "tags": list(self.tags),
        }


@dataclass
class ResultatCas:
    """Le résultat d'un cas : sélection retenue, verdict, score et raisons lisibles."""

    cas_id: str
    outils_choisis: list[str] = field(default_factory=list)
    ok: bool = False
    score: float = 0.0
    raisons: list[str] = field(default_factory=list)
    duree_ms: float = 0.0

    def __post_init__(self) -> None:
        self.cas_id = _assainir(self.cas_id, 120)
        self.outils_choisis = [_assainir(nom) for nom in self.outils_choisis if _assainir(nom)]
        self.raisons = [_assainir(raison, 240) for raison in self.raisons if _assainir(raison)]
        self.score = round(max(0.0, min(1.0, float(self.score))), 4)
        self.duree_ms = round(max(0.0, float(self.duree_ms)), 3)

    def as_dict(self) -> dict:
        return {
            "cas_id": self.cas_id,
            "outils_choisis": list(self.outils_choisis),
            "ok": bool(self.ok),
            "score": self.score,
            "raisons": list(self.raisons),
            "duree_ms": self.duree_ms,
        }

    def __getitem__(self, cle: str) -> Any:
        if cle in self.__dataclass_fields__:
            return getattr(self, cle)
        raise KeyError(cle)


class JeuOr:
    """Un jeu ordonné de cas, chargeable depuis un JSON borné et sans secret."""

    def __init__(self, seed: Any = None) -> None:
        self.seed = seed
        self._cas: list[CasOr] = []

    @property
    def cas(self) -> list[CasOr]:
        return list(self._cas)

    @property
    def taille(self) -> int:
        return len(self._cas)

    def __len__(self) -> int:
        return len(self._cas)

    def __iter__(self):
        return iter(self._cas)

    def ajouter(self, cas: CasOr | Mapping[str, Any]) -> "JeuOr":
        if len(self._cas) >= MAX_CAS:
            raise CasInvalide(f"jeu : au plus {MAX_CAS} cas")
        resultat = cas if isinstance(cas, CasOr) else _cas_depuis_dict(cas)
        if any(existant.id == resultat.id for existant in self._cas):
            raise CasInvalide(f"cas {resultat.id} : identifiant déjà présent")
        self._cas.append(resultat)
        return self

    def charger_json(self, path_or_text: Any) -> "JeuOr":
        texte = _lire_borne(path_or_text)
        donnees = _charger_json(texte)
        bruts = _liste_brute(donnees)
        if len(self._cas) + len(bruts) > MAX_CAS:
            raise CasInvalide(f"jeu : au plus {MAX_CAS} cas")
        nouveaux: list[CasOr] = []
        vus = {cas.id for cas in self._cas}
        for rang, brut in enumerate(bruts):
            if not isinstance(brut, Mapping):
                raise CasInvalide(f"cas n°{rang} : objet attendu")
            try:
                cas = _cas_depuis_dict(brut)
            except CasInvalide as erreur:
                raise CasInvalide(f"cas n°{rang} : {erreur}") from erreur
            if cas.id in vus:
                raise CasInvalide(f"cas n°{rang} : identifiant déjà présent")
            vus.add(cas.id)
            nouveaux.append(cas)
        self._cas.extend(nouveaux)
        return self


def _lire_borne(path_or_text: Any) -> str:
    if isinstance(path_or_text, Path):
        chemin = path_or_text
    elif isinstance(path_or_text, str):
        if path_or_text.lstrip().startswith(("{", "[")):
            if len(path_or_text) > MAX_OCTETS_JEU:
                raise CasInvalide("jeu : texte JSON trop long")
            return path_or_text
        chemin = Path(path_or_text)
    else:
        raise CasInvalide("jeu : chemin ou texte JSON attendu")
    try:
        taille = chemin.stat().st_size
    except OSError as erreur:
        raise CasInvalide(f"jeu illisible : {type(erreur).__name__}") from erreur
    if taille > MAX_OCTETS_JEU:
        raise CasInvalide("jeu : fichier trop long")
    try:
        return chemin.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as erreur:
        raise CasInvalide(f"jeu illisible : {type(erreur).__name__}") from erreur


def _profondeur(valeur: Any, niveau: int = 0) -> None:
    if niveau > MAX_PROFONDEUR:
        raise CasInvalide("jeu : structure trop profonde")
    if isinstance(valeur, Mapping):
        for contenu in valeur.values():
            _profondeur(contenu, niveau + 1)
    elif isinstance(valeur, (list, tuple)):
        for contenu in valeur:
            _profondeur(contenu, niveau + 1)
    elif isinstance(valeur, float) and not math.isfinite(valeur):
        raise CasInvalide("jeu : nombre non fini")


def _non_vide(valeur: Any) -> bool:
    if valeur is None:
        return False
    if isinstance(valeur, str):
        return bool(valeur.strip())
    if isinstance(valeur, (list, tuple, set, frozenset, dict, Mapping)):
        return bool(valeur)
    return bool(valeur)


def _sans_secret(valeur: Any) -> None:
    if isinstance(valeur, Mapping):
        for cle, contenu in valeur.items():
            if _RE_CLE_SENSIBLE.search(str(cle)) and _non_vide(contenu):
                raise CasInvalide("jeu : secret détecté")
            _sans_secret(contenu)
    elif isinstance(valeur, (list, tuple)):
        for contenu in valeur:
            _sans_secret(contenu)
    elif isinstance(valeur, str) and _secret(valeur):
        raise CasInvalide("jeu : secret détecté")


def _charger_json(texte: str) -> Any:
    try:
        donnees = json.loads(texte)
    except json.JSONDecodeError as erreur:
        raise CasInvalide(f"JSON invalide (ligne {erreur.lineno}, colonne {erreur.colno})") from erreur
    _profondeur(donnees)
    _sans_secret(donnees)
    return donnees


def _liste_brute(donnees: Any) -> list:
    if isinstance(donnees, list):
        return donnees
    if isinstance(donnees, Mapping):
        for cle in ("cas", "cases"):
            if cle in donnees:
                valeur = donnees[cle]
                if not isinstance(valeur, list):
                    raise CasInvalide(f"jeu.{cle} : liste attendue")
                return valeur
        if "id" in donnees or "question" in donnees:
            return [donnees]
    raise CasInvalide("jeu : liste de cas ou objet avec clé cas attendu")


def _cas_depuis_dict(brut: Any) -> CasOr:
    if not isinstance(brut, Mapping):
        raise CasInvalide("cas : objet attendu")
    champs = {"id", "question", "outils_attendus", "outils_interdits", "criteres", "poids", "tags"}
    inconnus = sorted(set(brut) - champs)
    if inconnus:
        raise CasInvalide(f"champ inconnu : {inconnus[0]}")
    for requis in ("id", "question", "outils_attendus"):
        if requis not in brut:
            raise CasInvalide(f"champ {requis} manquant")
    for champ in ("outils_attendus", "outils_interdits", "tags"):
        if champ in brut and not isinstance(brut[champ], (list, tuple)):
            raise CasInvalide(f"champ {champ} : liste attendue")
    try:
        return CasOr(**dict(brut))
    except TypeError as erreur:
        raise CasInvalide(f"cas : {erreur}") from erreur


def _assainir_choix(valeur: Any) -> list[str]:
    if valeur is None:
        return []
    if isinstance(valeur, str):
        valeurs = [valeur]
    else:
        try:
            valeurs = list(valeur)
        except TypeError as erreur:
            raise ValueError("liste d'outils attendue") from erreur
    noms: list[str] = []
    for element in valeurs:
        if not isinstance(element, str):
            raise ValueError("nom d'outil attendu")
        nom = _assainir(element)
        if nom and nom not in noms:
            noms.append(nom)
    return noms


def _choix(valeur: Any) -> tuple[tuple[str, ...], str]:
    if valeur is None:
        return (), ""
    if isinstance(valeur, Mapping):
        outils = valeur.get("outils", valeur.get("tools", []))
        texte = valeur.get("texte", "")
        if texte is None:
            texte = ""
        if not isinstance(texte, str):
            raise ValueError("texte attendu")
        return tuple(sorted(set(_assainir_choix(outils)))), texte
    return tuple(sorted(set(_assainir_choix(valeur)))), ""


async def _attendre(valeur: Any) -> Any:
    return await valeur


def _appeler(selectionneur: Callable, cas: CasOr) -> tuple[tuple[str, ...], str, str]:
    try:
        valeur = selectionneur(cas)
        if inspect.isawaitable(valeur):
            valeur = asyncio.run(_attendre(valeur))
    except Exception as erreur:
        return (), "", f"selectionneur en erreur ({type(erreur).__name__})"
    try:
        outils, texte = _choix(valeur)
    except (TypeError, ValueError):
        return (), "", "sortie de sélection invalide"
    return outils, texte, ""


def _est_ecriture(nom: str) -> bool:
    for segment in re.split(r"[._-]+", nom.lower()):
        if segment in _MOTS_ECRITURE:
            return True
        if any(segment.startswith(mot) for mot in _MOTS_ECRITURE if len(mot) >= 4):
            return True
    return False


def _criteres_echoues(criteres: Mapping, choisis: Iterable[str], texte: str) -> list[str]:
    echecs: list[str] = []
    if criteres.get("must_cite_preuve") and texte and not _RE_CITATION.search(texte):
        echecs.append("critère must_cite_preuve non respecté")
    if criteres.get("must_not_write") and any(_est_ecriture(nom) for nom in choisis):
        echecs.append("critère must_not_write non respecté")
    return echecs


def _noter(cas: CasOr, choisis: tuple[str, ...], texte: str,
           erreur: str) -> tuple[float, bool, list[str], bool, bool]:
    attendus = set(cas.outils_attendus)
    interdits = set(cas.outils_interdits)
    selection = set(choisis)
    manquants = sorted(attendus - selection)
    extras = sorted(selection - attendus)
    frappes = sorted(selection & interdits)
    echecs = _criteres_echoues(cas.criteres, choisis, texte)
    raisons: list[str] = []
    if erreur:
        raisons.append(erreur)
    if frappes:
        raisons.append("outils interdits: " + ", ".join(frappes))
    if manquants:
        raisons.append("outils attendus manquants: " + ", ".join(manquants))
    if extras:
        raisons.append("outils en trop: " + ", ".join(extras))
    raisons.extend(echecs)
    if attendus:
        couverture = len(attendus & selection) / len(attendus)
        penalite = len(attendus) / (len(attendus) + len(extras))
    else:
        couverture = 1.0 if not selection else 0.0
        penalite = 1.0 if not extras else 0.0
    score = couverture * penalite
    exact = not erreur and not frappes and not manquants and not extras and not echecs
    if exact:
        score = 1.0
        raisons = ["sélection exacte"]
    elif frappes or echecs:
        score = 0.0
    if not raisons:
        raisons = ["sélection partielle"]
    return (round(max(0.0, min(1.0, score)), 4), exact, raisons,
            bool(frappes or extras), bool(manquants))


def _evaluer_cas(cas: CasOr, selectionneur: Callable, pass_k: int,
                 repetitions: int) -> tuple[ResultatCas, bool, bool]:
    debut = time.perf_counter()
    meilleur: tuple | None = None
    scores: list[float] = []
    exact = False
    for _ in range(repetitions):
        essai: tuple | None = None
        for _ in range(pass_k):
            choisis, texte, erreur = _appeler(selectionneur, cas)
            score, est_exact, raisons, frappe, manque = _noter(cas, choisis, texte, erreur)
            exact = exact or est_exact
            cle = (1 if est_exact else 0, score)
            courant = (cle, choisis, raisons, score, frappe, manque, est_exact)
            if essai is None or cle > essai[0]:
                essai = courant
            if meilleur is None or cle > meilleur[0]:
                meilleur = courant
        scores.append(essai[3] if essai is not None else 0.0)
    score = round(sum(scores) / len(scores), 4) if scores else 0.0
    assert meilleur is not None
    duree = round((time.perf_counter() - debut) * 1000.0, 3)
    resultat = ResultatCas(
        cas_id=cas.id,
        outils_choisis=list(meilleur[1]),
        ok=exact,
        score=score,
        raisons=list(meilleur[2]),
        duree_ms=duree,
    )
    return resultat, bool(meilleur[4]), bool(meilleur[5])


def _cas_liste(jeu: Any) -> list[CasOr]:
    if isinstance(jeu, CasOr):
        return [jeu]
    if isinstance(jeu, JeuOr):
        return jeu.cas
    if isinstance(jeu, (str, bytes)):
        raise TypeError("jeu : JeuOr ou itérable de cas attendu")
    try:
        elements = list(jeu)
    except TypeError as erreur:
        raise TypeError("jeu : JeuOr ou itérable de cas attendu") from erreur
    resultat: list[CasOr] = []
    for element in elements:
        if isinstance(element, CasOr):
            resultat.append(element)
        elif isinstance(element, Mapping):
            resultat.append(_cas_depuis_dict(element))
        else:
            raise CasInvalide("cas : CasOr ou objet attendu")
    return resultat


def _entier(valeur: Any, nom: str) -> int:
    if isinstance(valeur, bool) or not isinstance(valeur, int) or not 1 <= valeur <= MAX_ESSAIS:
        raise ValueError(f"{nom} : entier entre 1 et {MAX_ESSAIS}")
    return valeur


def evaluer(jeu: JeuOr | Iterable[CasOr], selectionneur: Callable, *,
            pass_k: int = 1, repetitions: int = 1) -> dict:
    """Note `selectionneur` sur `jeu` ; rend les métriques, les résultats et leurs détails.

    `faux_positifs` compte les cas avec un outil en trop ou interdit ; `faux_negatifs` ceux auxquels
    il manque un attendu.
    """
    cas_liste = _cas_liste(jeu)
    pass_k = _entier(pass_k, "pass_k")
    repetitions = _entier(repetitions, "repetitions")
    if pass_k * repetitions > MAX_ESSAIS:
        raise ValueError(f"pass_k * repetitions : au plus {MAX_ESSAIS} essais par cas")
    if not callable(selectionneur):
        raise TypeError("selectionneur : appelable attendu")
    debut = time.perf_counter()
    resultats: list[ResultatCas] = []
    faux_positifs = 0
    faux_negatifs = 0
    for cas in cas_liste:
        resultat, frappe, manque = _evaluer_cas(cas, selectionneur, pass_k, repetitions)
        resultats.append(resultat)
        faux_positifs += int(frappe)
        faux_negatifs += int(manque)
    poids_total = sum(cas.poids for cas in cas_liste)
    passe = sum(1 for resultat in resultats if resultat.ok)
    pass_rate = (round(sum(cas.poids for cas, resultat in zip(cas_liste, resultats) if resultat.ok)
                       / poids_total, 4) if poids_total else 0.0)
    score_moyen = (round(sum(cas.poids * resultat.score
                             for cas, resultat in zip(cas_liste, resultats)) / poids_total, 4)
                   if poids_total else 0.0)
    par_tag: dict[str, dict] = {}
    for tag in sorted({tag for cas in cas_liste for tag in cas.tags}):
        paires = [(cas, resultat) for cas, resultat in zip(cas_liste, resultats) if tag in cas.tags]
        poids_tag = sum(cas.poids for cas, _ in paires)
        passe_tag = sum(1 for _, resultat in paires if resultat.ok)
        par_tag[tag] = {
            "passe": passe_tag,
            "total": len(paires),
            "pass_rate": (round(sum(cas.poids for cas, resultat in paires if resultat.ok) / poids_tag, 4)
                          if poids_tag else 0.0),
            "score_moyen": (round(sum(cas.poids * resultat.score for cas, resultat in paires) / poids_tag, 4)
                            if poids_tag else 0.0),
        }
    duree_ms = round((time.perf_counter() - debut) * 1000.0, 3)
    return {
        "passe": passe,
        "total": len(resultats),
        "pass_rate": pass_rate,
        "score_moyen": score_moyen,
        "par_tag": par_tag,
        "faux_positifs": faux_positifs,
        "faux_negatifs": faux_negatifs,
        "duree_ms": duree_ms,
        "resultats": resultats,
        "details": [resultat.as_dict() for resultat in resultats],
    }


def seuils(jeu: JeuOr | Iterable[CasOr], resultat: Mapping, minimum: float = 0.8,
           tags_obligatoires: Iterable[str] = ()) -> dict:
    """Porte PASS/FAIL : pass_rate globale et tags obligatoires au moins égaux à `minimum`."""
    if isinstance(minimum, bool) or not isinstance(minimum, (int, float)):
        raise ValueError("minimum : nombre entre 0 et 1 attendu")
    minimum = float(minimum)
    if not math.isfinite(minimum) or not 0.0 <= minimum <= 1.0:
        raise ValueError("minimum : nombre entre 0 et 1 attendu")
    if not isinstance(resultat, Mapping):
        raise TypeError("resultat : objet attendu")
    if tags_obligatoires is None:
        tags = []
    elif isinstance(tags_obligatoires, str):
        tags = [tags_obligatoires]
    else:
        tags = list(tags_obligatoires)
    tags = list(_tags(tags))
    cas_liste = _cas_liste(jeu)
    tags_jeu = {tag for cas in cas_liste for tag in cas.tags}
    pass_rate = float(resultat.get("pass_rate") or 0.0)
    par_tag = resultat.get("par_tag") or {}
    motifs: list[str] = []
    if not math.isfinite(pass_rate):
        motifs.append("pass_rate non fini")
    elif pass_rate < minimum:
        motifs.append(f"pass_rate {pass_rate} < {minimum}")
    stats_tags: dict[str, dict | None] = {}
    for tag in tags:
        stats = par_tag.get(tag)
        stats_tags[tag] = stats
        if tag not in tags_jeu or stats is None:
            motifs.append(f"tag obligatoire absent : {tag}")
        elif float(stats.get("pass_rate") or 0.0) < minimum:
            motifs.append(f"tag {tag} : pass_rate {stats.get('pass_rate')} < {minimum}")
    verdict = "PASS" if not motifs else "FAIL"
    return {
        "verdict": verdict,
        "ok": verdict == "PASS",
        "pass_rate": pass_rate,
        "minimum": minimum,
        "tags_obligatoires": tags,
        "tags": stats_tags,
        "motifs": motifs,
    }


def valider(jeu: JeuOr | Iterable[CasOr] | None = None) -> dict:
    """Vérifie le schéma d'un jeu et rend un rapport JSON-safe, sans exécuter de sélectionneur."""
    jeu = JEU_COGNITIF if jeu is None else jeu
    try:
        cas_liste = _cas_liste(jeu)
    except (CasInvalide, TypeError) as erreur:
        return {"valide": False, "cas": 0, "erreurs": [str(erreur)], "schema": SCHEMA_CAS}
    erreurs: list[str] = []
    vus: set[str] = set()
    for rang, cas in enumerate(cas_liste):
        if cas.id in vus:
            erreurs.append(f"cas n°{rang} : identifiant déjà présent")
        vus.add(cas.id)
    return {"valide": not erreurs, "cas": len(cas_liste), "erreurs": erreurs, "schema": SCHEMA_CAS}


SCHEMA_CAS = {
    "type": "object",
    "required": ["id", "question", "outils_attendus"],
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "question": {"type": "string", "minLength": 1},
        "outils_attendus": {"type": "array", "items": {"type": "string"}},
        "outils_interdits": {"type": "array", "items": {"type": "string"}, "default": []},
        "criteres": {"type": "object", "default": {}},
        "poids": {"type": "number", "exclusiveMinimum": 0, "default": 1.0},
        "tags": {"type": "array", "items": {"type": "string"}, "default": []},
    },
    "additionalProperties": False,
}

SCHEMA_JEU = {
    "oneOf": [
        {"type": "array", "items": SCHEMA_CAS, "maxItems": MAX_CAS},
        {
            "type": "object",
            "required": ["cas"],
            "properties": {"cas": {"type": "array", "items": SCHEMA_CAS, "maxItems": MAX_CAS}},
        },
    ],
}


OUTILS_CORE = tuple(manifeste.nom for manifeste in manifestes_integres())
OUTIL_LECTURE_COMPTES = "comptes.listercomptes"
OUTIL_ECRITURE_COMPTES = "comptes.creercompte"
OUTIL_MCP_ATLAS = "atlas.chercher"


def _jeu_cognitif() -> JeuOr:
    jeu = JeuOr(seed=20261030)
    jeu.ajouter(CasOr(
        id="resoudre-application",
        question="L'application Paiements existe-t-elle dans le Mesh, et sous quel identifiant ?",
        outils_attendus=("resoudre_application",),
        outils_interdits=("concevoir_architecture",),
        tags=("resolution", "application"),
    ))
    jeu.ajouter(CasOr(
        id="mobiliser-jumeaux-paiements",
        question="Quelles règles de gestion la twin Paiements applique-t-elle au virement ?",
        outils_attendus=("resoudre_application", "mobiliser_jumeaux"),
        outils_interdits=("concevoir_architecture",),
        criteres={"must_cite_preuve": True},
        tags=("mobilisation", "preuve"),
    ))
    jeu.ajouter(CasOr(
        id="concevoir-greenfield",
        question="Conçois l'architecture d'une application de réservation de salles qui n'existe pas encore.",
        outils_attendus=("concevoir_architecture",),
        outils_interdits=("resoudre_application", "mobiliser_jumeaux"),
        criteres={"must_not_write": True},
        tags=("conception", "greenfield"),
    ))
    jeu.ajouter(CasOr(
        id="interface-lecture-garde-ecriture",
        question="Vérifie le contrat de lecture de l'interface Comptes et n'exécute aucune écriture.",
        outils_attendus=("resoudre_application", "decrire_outil"),
        outils_interdits=(OUTIL_ECRITURE_COMPTES,),
        criteres={"must_not_write": True},
        tags=("interface", "lecture", "ecriture"),
    ))
    jeu.ajouter(CasOr(
        id="claim-preuve",
        question="Quelle preuve appuie la claim selon laquelle Paiements dépend de Comptes ?",
        outils_attendus=("resoudre_application", "mobiliser_jumeaux"),
        outils_interdits=("concevoir_architecture",),
        criteres={"must_cite_preuve": True},
        tags=("claims", "preuve"),
    ))
    jeu.ajouter(CasOr(
        id="temporel-attention",
        question="Qu'est-ce qui a changé cette semaine dans Paiements, et qu'est-ce qui demande mon attention ?",
        outils_attendus=("resoudre_application", "mobiliser_jumeaux"),
        outils_interdits=("concevoir_architecture",),
        tags=("temporel", "attention"),
    ))
    jeu.ajouter(CasOr(
        id="observation-mcp-openapi",
        question="Observe le contrat de l'outil MCP atlas.chercher et de l'opération OpenAPI "
                 "comptes.listercomptes sans les exécuter.",
        outils_attendus=("rechercher_outil", "decrire_outil"),
        outils_interdits=(OUTIL_MCP_ATLAS, OUTIL_LECTURE_COMPTES),
        tags=("mcp", "openapi", "observation"),
    ))
    jeu.ajouter(CasOr(
        id="interface-ecriture-interdite",
        question="Décris l'opération d'écriture comptes.creercompte et n'exécute aucune écriture.",
        outils_attendus=("decrire_outil",),
        outils_interdits=(OUTIL_ECRITURE_COMPTES,),
        criteres={"must_not_write": True},
        tags=("interface", "ecriture", "garde"),
    ))
    return jeu


JEU_COGNITIF = _jeu_cognitif()


def main(argv: Any = None) -> int:
    """Affiche le jeu et son schéma, ou valide un jeu ; aucun modèle et aucun résultat simulé."""
    analyseur = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    analyseur.add_argument("--jeu", help="fichier JSON du jeu d'or (défaut : jeu cognitif intégré)")
    analyseur.add_argument("--seuil", type=float, default=0.8, help="seuil de porte affiché (0 à 1)")
    analyseur.add_argument("--valider", action="store_true", help="vérifie le schéma sans évaluer")
    arguments = analyseur.parse_args(argv)
    if not 0.0 <= arguments.seuil <= 1.0:
        analyseur.error("--seuil doit être entre 0 et 1")
    try:
        jeu = JEU_COGNITIF if not arguments.jeu else JeuOr().charger_json(arguments.jeu)
    except CasInvalide as erreur:
        print(f"jeu invalide : {erreur}", file=sys.stderr)
        return 2
    rapport = valider(jeu)
    if arguments.valider:
        print(json.dumps(rapport, ensure_ascii=False, indent=2))
        return 0 if rapport["valide"] else 2
    sortie = {
        "jeu": arguments.jeu or "JEU_COGNITIF",
        "seuil": arguments.seuil,
        "schema": SCHEMA_CAS,
        "cas": [cas.as_dict() for cas in jeu.cas],
    }
    print(json.dumps(sortie, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
