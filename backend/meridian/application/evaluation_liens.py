"""Évaluation des liens contre un jeu d'or.

Le module ne lit ni base ni réseau : il compare un `RapportLiens` à des attentes
labellisées et rend précision, rappel, f1, fausses certitudes, couverture des
preuves, questions, externes et contradictions.

Une fausse certitude est un lien `confirme` sans preuve, avec une preuve manquante,
ou une relation Mesh non éligible confirmée. C'est la métrique qui doit rester à zéro.
"""
from __future__ import annotations

from dataclasses import dataclass

from meridian.domain.liens_composants import LienPropose, RapportLiens

__all__ = [
    "JeuOrLiens",
    "LienAttendu",
    "QuestionAttendue",
    "ResultatEvaluation",
    "evaluer_liens",
]


def _texte(valeur) -> str:
    return " ".join(str(valeur or "").split())


def _cle_operation(valeur) -> str:
    return _texte(valeur).casefold()


def _cle_lien(lien: LienPropose) -> tuple:
    return (lien.consommateur_composant_id, lien.fournisseur_composant_id,
            _cle_operation(lien.operation), lien.nature, lien.environment)


@dataclass(frozen=True)
class LienAttendu:
    consommateur: str
    fournisseur: str
    operation: str
    nature: str = "mesh"
    environment: str = "prod"

    def __post_init__(self):
        for nom in ("consommateur", "fournisseur", "operation"):
            valeur = _texte(getattr(self, nom))
            if not valeur:
                raise ValueError(f"{nom} obligatoire")
            object.__setattr__(self, nom, valeur)
        object.__setattr__(self, "nature", _texte(self.nature).lower() or "mesh")
        object.__setattr__(self, "environment", _texte(self.environment).lower() or "prod")

    def cle(self) -> tuple:
        return (self.consommateur, self.fournisseur, _cle_operation(self.operation),
                self.nature, self.environment)

    def libelle(self) -> str:
        return f"{self.consommateur} → {self.fournisseur} · {self.operation}"


@dataclass(frozen=True)
class QuestionAttendue:
    type: str
    sujet: str
    environment: str = "prod"

    def __post_init__(self):
        for nom in ("type", "sujet"):
            valeur = _texte(getattr(self, nom))
            if not valeur:
                raise ValueError(f"{nom} obligatoire")
            object.__setattr__(self, nom, valeur)
        object.__setattr__(self, "environment", _texte(self.environment).lower() or "prod")

    def cle(self) -> tuple:
        return (self.type.upper(), _cle_operation(self.sujet), self.environment)


@dataclass(frozen=True)
class JeuOrLiens:
    liens: tuple[LienAttendu, ...] = ()
    questions: tuple[QuestionAttendue, ...] = ()
    externes: tuple[str, ...] = ()
    contradictions: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "liens", tuple(self.liens or ()))
        object.__setattr__(self, "questions", tuple(self.questions or ()))
        object.__setattr__(self, "externes", tuple(
            _texte(x).casefold() for x in (self.externes or ()) if _texte(x)))
        contradictions = []
        for couple in self.contradictions or ():
            if not isinstance(couple, (tuple, list)) or len(couple) != 2:
                raise ValueError("contradiction attendue : (consommateur, operation)")
            consommateur, operation = _texte(couple[0]), _texte(couple[1])
            if not consommateur or not operation:
                raise ValueError("contradiction attendue : (consommateur, operation)")
            contradictions.append((consommateur, _cle_operation(operation)))
        object.__setattr__(self, "contradictions", tuple(contradictions))

    def as_dict(self) -> dict:
        return {
            "liens": [{"consommateur": x.consommateur, "fournisseur": x.fournisseur,
                       "operation": x.operation, "nature": x.nature,
                       "environment": x.environment} for x in self.liens],
            "questions": [{"type": x.type, "sujet": x.sujet,
                           "environment": x.environment} for x in self.questions],
            "externes": list(self.externes),
            "contradictions": [list(x) for x in self.contradictions],
        }


@dataclass(frozen=True)
class ResultatEvaluation:
    vrais_positifs: int
    faux_positifs: int
    faux_negatifs: int
    precision: float
    rappel: float
    f1: float
    fausses_certitudes: int
    taux_preuves: float
    ambiguites: int
    couverts: tuple[str, ...] = ()
    manquants: tuple[str, ...] = ()
    surplus: tuple[str, ...] = ()
    questions_trouvees: int = 0
    questions_manquantes: int = 0
    externes_trouves: int = 0
    externes_manquants: int = 0
    contradictions_trouvees: int = 0
    contradictions_manquantes: int = 0

    def as_dict(self) -> dict:
        return {
            "vrais_positifs": self.vrais_positifs,
            "faux_positifs": self.faux_positifs,
            "faux_negatifs": self.faux_negatifs,
            "precision": self.precision,
            "rappel": self.rappel,
            "f1": self.f1,
            "fausses_certitudes": self.fausses_certitudes,
            "taux_preuves": self.taux_preuves,
            "ambiguites": self.ambiguites,
            "couverts": list(self.couverts),
            "manquants": list(self.manquants),
            "surplus": list(self.surplus),
            "questions_trouvees": self.questions_trouvees,
            "questions_manquantes": self.questions_manquantes,
            "externes_trouves": self.externes_trouves,
            "externes_manquants": self.externes_manquants,
            "contradictions_trouvees": self.contradictions_trouvees,
            "contradictions_manquantes": self.contradictions_manquantes,
        }

    def resume(self) -> str:
        return (
            f"{self.vrais_positifs} vrai(s) positif(s), {self.faux_positifs} faux positif(s), "
            f"{self.faux_negatifs} faux négatif(s) ; précision {self.precision:.2f}, "
            f"rappel {self.rappel:.2f}, f1 {self.f1:.2f} ; "
            f"{self.fausses_certitudes} fausse(s) certitude(s), "
            f"preuves {self.taux_preuves:.2f}, {self.ambiguites} ambiguïté(s)."
        )


def _taux(numerateur: int, denominateur: int) -> float:
    return round(numerateur / denominateur, 4) if denominateur else 0.0


def _fausse_certitude(lien: LienPropose) -> bool:
    if lien.state != "confirme":
        return False
    if not lien.preuves or lien.missing_evidence:
        return True
    return lien.nature == "mesh" and not lien.eligible


def evaluer_liens(rapport: RapportLiens, jeu: JeuOrLiens) -> ResultatEvaluation:
    """Compare un rapport au jeu d'or, sans jamais exécuter de modèle."""
    attendus = {lien.cle(): lien for lien in jeu.liens}
    # Les dépendances externes ont leur propre mesure : elles ne polluent pas la
    # précision/rappel des liens internes et Mesh.
    tous_les_liens = list(rapport.liens)
    liens = [lien for lien in tous_les_liens if lien.nature != "externe"]
    observes = {_cle_lien(lien): lien for lien in liens}
    communs = set(attendus) & set(observes)
    manquants = set(attendus) - set(observes)
    surplus = set(observes) - set(attendus)

    fausses_certitudes = sum(1 for lien in tous_les_liens if _fausse_certitude(lien))
    taux_preuves = _taux(sum(1 for lien in tous_les_liens if lien.preuves),
                         len(tous_les_liens))

    questions_attendues = {question.cle() for question in jeu.questions}
    questions_observees = {
        (question.type, _cle_operation(question.sujet), question.environment)
        for question in rapport.questions
    }
    externes_observes = {
        lien.fournisseur_service.casefold() for lien in rapport.externes
        if lien.fournisseur_service
    }
    contradictions_observees = {
        (lien.consommateur_composant_id, _cle_operation(lien.operation))
        for lien in rapport.contradictions
    }

    return ResultatEvaluation(
        vrais_positifs=len(communs), faux_positifs=len(surplus),
        faux_negatifs=len(manquants),
        precision=_taux(len(communs), len(communs) + len(surplus)),
        rappel=_taux(len(communs), len(communs) + len(manquants)),
        f1=_taux(2 * len(communs),
                 2 * len(communs) + len(surplus) + len(manquants)),
        fausses_certitudes=fausses_certitudes, taux_preuves=taux_preuves,
        ambiguites=sum(1 for question in rapport.questions if question.type == "AMBIGU"),
        couverts=tuple(sorted(attendus[cle].libelle() for cle in communs)),
        manquants=tuple(sorted(attendus[cle].libelle() for cle in manquants)),
        surplus=tuple(sorted(
            f"{observes[cle].consommateur_composant_id} → "
            f"{observes[cle].fournisseur_composant_id or observes[cle].fournisseur_service} "
            f"· {observes[cle].operation}" for cle in surplus)),
        questions_trouvees=len(questions_attendues & questions_observees),
        questions_manquantes=len(questions_attendues - questions_observees),
        externes_trouves=len(set(jeu.externes) & externes_observes),
        externes_manquants=len(set(jeu.externes) - externes_observes),
        contradictions_trouvees=len(set(jeu.contradictions) & contradictions_observees),
        contradictions_manquantes=len(set(jeu.contradictions) - contradictions_observees),
    )
