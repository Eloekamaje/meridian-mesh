"""Spécialiste critique : challenge un livrable sans le réécrire.

Le critique ne reçoit pas les tokens internes de l'auteur. Il lit le dossier borné et le livrable,
applique la grille structurelle du noyau, puis rend des findings actionnables. Son autorité reste
`proposition` : il ne corrige pas, ne décide pas et n'écrit rien.
"""
from __future__ import annotations

from types import SimpleNamespace
from collections.abc import Mapping

from meridian.application import noyau_raisonnement
from meridian.domain.specialistes import ContexteSpecialiste, Proposition, ResultatSpecialiste

__all__ = ["SpecialisteCritique"]


def _mapping(valeur) -> dict:
    return dict(valeur) if isinstance(valeur, Mapping) else {}


def _demande(dossier: Mapping) -> SimpleNamespace:
    demande = _mapping(dossier.get("demande"))
    return SimpleNamespace(
        but=str(demande.get("but") or "concevoir"),
        sensibilite=tuple(demande.get("sensibilite") or ()),
        niveau=str(dossier.get("niveau") or demande.get("niveau") or "N3"),
        reversibilite=str(demande.get("reversibilite") or "couteuse"),
        autorite=str(demande.get("autorite") or "proposition"),
    )


class SpecialisteCritique:
    nom = "critique"
    autorite = "proposition"

    def analyser(self, contexte: ContexteSpecialiste) -> ResultatSpecialiste:
        dossier = _mapping(contexte.dossier)
        reponse = _mapping(contexte.reponse) or _mapping(dossier.get("reponse"))
        if not reponse:
            return ResultatSpecialiste(
                specialiste=self.nom, statut="partiel",
                propositions=[Proposition(
                    self.nom, "QUESTION", "Aucun livrable à critiquer",
                    resume="Le dossier ne contient pas de réponse ou de proposition à challenger.",
                    confiance=0.9,
                )],
                limites=["livrable absent"],
            )
        faux_dossier = SimpleNamespace(
            niveau=str(dossier.get("niveau") or "N3"),
            demande=_demande(dossier),
            options=tuple(dossier.get("options") or ()),
            reponse=reponse,
        )
        critique = noyau_raisonnement.critiquer_reponse(faux_dossier, reponse)
        propositions = []
        for finding in critique.findings:
            propositions.append(Proposition(
                self.nom,
                "RISQUE" if finding.severite in {"majeure", "critique"} else "CONSTAT",
                finding.constat,
                resume=f"[{finding.severite}] {finding.remediation}",
                confiance=0.9 if finding.severite == "critique" else (
                    0.8 if finding.severite == "majeure" else 0.6),
                actions=("corriger_livrable",),
                donnees={
                    "finding_id": finding.id,
                    "severite": finding.severite,
                    "rubrique": finding.rubrique,
                    "preuve": finding.preuve,
                    "remediation": finding.remediation,
                },
            ))
        if not propositions:
            propositions.append(Proposition(
                self.nom, "CONSTAT", "Aucun finding structurel bloquant",
                resume="La critique structurelle ne détecte pas de manque majeur dans le livrable.",
                confiance=0.7,
            ))
        return ResultatSpecialiste(
            specialiste=self.nom,
            statut="ok",
            propositions=propositions,
            limites=["critique structurelle : la validation sémantique profonde reste humaine"] if critique.verdict != "pass" else [],
        )
