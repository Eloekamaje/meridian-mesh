"""Spécialiste risque : qualifie les enjeux de sécurité, conformité et irréversibilité.

Il ne décide pas du risque acceptable et ne remplace pas une revue humaine. Il rend des propositions
typées `RISQUE` à partir de la demande et du cadre, avec une sévérité et une remédiation.
"""
from __future__ import annotations

from collections.abc import Mapping

from meridian.application import noyau_raisonnement
from meridian.domain.specialistes import ContexteSpecialiste, Proposition, ResultatSpecialiste

__all__ = ["SpecialisteRisque"]

_LIBELLES = {
    "donnees_personnelles": "données personnelles",
    "sante": "santé",
    "mineurs": "mineurs",
    "juridique": "juridique",
    "finance": "finance",
    "securite": "sécurité",
    "production": "production",
    "irreversible": "irréversibilité",
    "secret": "secret",
    "acces": "contrôle d'accès",
}


class SpecialisteRisque:
    nom = "risque"
    autorite = "proposition"

    def analyser(self, contexte: ContexteSpecialiste) -> ResultatSpecialiste:
        dossier = dict(contexte.dossier) if isinstance(contexte.dossier, Mapping) else {}
        question = contexte.question or dossier.get("question") or ""
        if not question:
            return ResultatSpecialiste(
                specialiste=self.nom, statut="partiel",
                propositions=[Proposition(
                    self.nom, "QUESTION", "Question absente",
                    resume="Aucune demande à qualifier pour la lentille risque.",
                    confiance=0.5)],
                limites=["question absente"],
            )
        demande = noyau_raisonnement.qualifier(question)
        propositions: list[Proposition] = []
        for categorie in demande.sensibilite:
            propositions.append(Proposition(
                self.nom, "RISQUE",
                f"Enjeu sensible : {_LIBELLES.get(categorie, categorie)}",
                resume=(
                    "La demande touche un domaine qui exige une revue de risque dédiée : "
                    "sécurité, conformité, vie privée ou sûreté."
                ),
                confiance=0.8,
                actions=("revoir_risque",),
                donnees={"categorie": categorie, "niveau_requis": "N4"},
            ))
        if demande.reversibilite == "irreversible":
            propositions.append(Proposition(
                self.nom, "RISQUE", "Action irréversible",
                resume="L'action envisagée exige une approbation humaine et un plan de rollback.",
                confiance=0.9,
                actions=("exiger_approbation", "preparer_rollback"),
                donnees={"niveau_requis": "N4", "reversibilite": demande.reversibilite},
            ))
        if not propositions:
            propositions.append(Proposition(
                self.nom, "CONSTAT", "Aucun risque spécifique détecté",
                resume="La demande ne déclenche pas de lentille de risque dédiée.",
                confiance=0.6,
            ))
        return ResultatSpecialiste(
            specialiste=self.nom,
            statut="ok",
            propositions=propositions,
            limites=["qualification initiale, pas une revue de sécurité complète"],
        )
