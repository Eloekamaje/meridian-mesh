"""Le Travail comme état de l'agent (Jumeau Harness §5.3) : Flore y planifie et y écrit, au format des Travaux.

Mêmes formes que les routes de cases_routes.py (questions, hypothèses, options, livrables, résumé) : ce que Flore
écrit apparaît dans l'interface existante du Travail. Chaque écriture laisse une trace dans l'historique.
"""
from datetime import datetime, timezone

RISQUES = ("faible", "moyen", "eleve")
MAX_TITRE, MAX_TEXTE, MAX_CONTENU = 120, 1000, 4000


def _texte(valeur, limite):
    valeur = (valeur or "").strip()
    if not valeur:
        raise ValueError("texte vide")
    return valeur[:limite]


class EcritureTravail:
    def __init__(self, db, cid):
        self.db, self.cid = db, cid

    async def etat(self):
        return await self.db.cases.find_one({"id": self.cid}, {"_id": 0}) or {}

    async def _ecrire(self, modification, trace):
        now = datetime.now(timezone.utc).isoformat()
        modification.setdefault("$set", {})["maj_le"] = now
        modification.setdefault("$push", {})["historique"] = {"quand": now, "texte": trace}
        await self.db.cases.update_one({"id": self.cid}, modification)

    async def planifier(self, etapes, prochaine_etape):
        """Ajoute les étapes (questions à lever) absentes ; garde celles qui existent, résolues ou non."""
        questions = list((await self.etat()).get("questions", []))
        connues = {q["texte"] for q in questions}
        questions += [{"texte": t, "resolue": False} for t in (_texte(e, MAX_TEXTE) for e in etapes) if t not in connues]
        modification = {"$set": {"questions": questions}}
        if prochaine_etape and prochaine_etape.strip():
            modification["$set"]["prochaine_etape"] = prochaine_etape.strip()[:MAX_TEXTE]
        await self._ecrire(modification, f"Plan mis à jour par Flore — {len(questions)} étape(s)")

    async def resoudre(self, etape):
        r = await self.db.cases.update_one({"id": self.cid, "questions.texte": etape},
                                           {"$set": {"questions.$.resolue": True}})
        if r.modified_count:
            await self._ecrire({}, f"Étape levée par Flore — {etape[:80]}")
        return bool(r.matched_count)

    async def hypothese(self, texte):
        n = len((await self.etat()).get("hypotheses", [])) + 1
        hyp = {"id": f"hyp-{n}", "texte": _texte(texte, MAX_TEXTE), "statut": "a_valider",
               "quand": datetime.now(timezone.utc).isoformat()}
        await self._ecrire({"$push": {"hypotheses": hyp}}, f"Hypothèse proposée par Flore — {hyp['texte'][:80]}")
        return hyp

    async def option(self, titre, description, risque):
        n = len((await self.etat()).get("options", [])) + 1
        opt = {"id": f"opt-{n}", "titre": _texte(titre, MAX_TITRE), "description": (description or "")[:MAX_CONTENU],
               "impacts": [], "risque": risque if risque in RISQUES else "moyen", "statut": "a_evaluer"}
        await self._ecrire({"$push": {"options": opt}}, f"Option proposée par Flore — {opt['titre']}")
        return opt

    async def livrable(self, titre, contenu):
        n = len((await self.etat()).get("livrables", [])) + 1
        liv = {"id": f"liv-{n}", "titre": _texte(titre, MAX_TITRE), "contenu": _texte(contenu, MAX_CONTENU * 4),
               "cree_le": datetime.now(timezone.utc).isoformat()}
        await self._ecrire({"$push": {"livrables": liv}}, f"Livrable produit par Flore — {liv['titre']}")
        return liv

    async def resume(self, texte):
        await self._ecrire({"$set": {"resume": _texte(texte, MAX_CONTENU)}}, "Résumé actualisé par Flore")


def etat_texte(case):
    """État du Travail pour le contexte de Flore : objectif, plan, hypothèses, options, livrables."""
    lignes = [f"Travail : {case.get('titre', '')}", f"Objectif : {case.get('objectif') or 'non précisé'}"]
    plan = case.get("questions") or []
    if plan:
        lignes.append("Plan :")
        lignes += [f"  [{'x' if q.get('resolue') else ' '}] {q['texte']}" for q in plan]
    if case.get("prochaine_etape"):
        lignes.append(f"Prochaine étape : {case['prochaine_etape']}")
    for cle, titre, champ in (("hypotheses", "Hypothèses", "texte"), ("options", "Options", "titre"),
                              ("livrables", "Livrables", "titre"), ("decisions", "Décisions", "texte")):
        elements = case.get(cle) or []
        if elements:
            lignes.append(f"{titre} : " + " ; ".join(
                e[champ] + (f" ({e['statut']})" if e.get("statut") else "") for e in elements))
    if case.get("resume"):
        lignes.append(f"Résumé actuel : {case['resume']}")
    return "\n".join(lignes)
