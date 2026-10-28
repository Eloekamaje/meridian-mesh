"""Le Travail comme état de l'agent (Jumeau Harness §5.3) : Flore y planifie et y écrit, au format des Travaux.

Mêmes formes que les routes de cases_routes.py (questions, hypothèses, options, livrables, résumé) : ce que Flore
écrit apparaît dans l'interface existante du Travail. Chaque écriture laisse une trace dans l'historique.
"""
import uuid
from datetime import datetime, timezone

RISQUES = ("faible", "moyen", "eleve")
MAX_TITRE, MAX_TEXTE, MAX_CONTENU = 120, 1000, 4000
ECHANGES_AVANT_RAPPEL = 3  # un échange = question + réponse, soit 2 messages de la conversation
ECHANGES_SANS_PLAN = 2
MIN_OPTIONS, MAX_OPTIONS, MAX_OPTION = 2, 4, 80


def _texte(valeur, limite):
    valeur = (valeur or "").strip()
    if not valeur:
        raise ValueError("texte vide")
    return valeur[:limite]


class EcritureTravail:
    """Écritures de Flore dans un Travail : identifiants uniques, doublons ignorés, quantités bornées.

    Les ajouts passent par $push (atomique) : Flore peut écrire pendant qu'un membre ajoute lui aussi au Travail.
    """
    MAX_ETAPES = 12  # par appel de planifier

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
        """Ajoute les étapes (questions à lever) absentes, sans toucher aux existantes, résolues ou non."""
        case = await self.etat()
        connues = {q["texte"] for q in case.get("questions", [])}
        nouvelles = []
        for texte in (_texte(e, MAX_TEXTE) for e in etapes[:self.MAX_ETAPES]):
            if texte not in connues:
                connues.add(texte)
                nouvelles.append({"texte": texte, "resolue": False})
        modification = {"$push": {"questions": {"$each": nouvelles}}} if nouvelles else {}
        modification["$set"] = {"plan_au_message": len(case.get("conversation", []))}
        if prochaine_etape and prochaine_etape.strip():
            modification["$set"]["prochaine_etape"] = prochaine_etape.strip()[:MAX_TEXTE]
        await self._ecrire(modification, f"Plan mis à jour par Flore — {len(nouvelles)} étape(s) ajoutée(s)")

    async def resoudre(self, etape):
        r = await self.db.cases.update_one({"id": self.cid, "questions.texte": etape},
                                           {"$set": {"questions.$.resolue": True}})
        if r.modified_count:
            nb = len((await self.etat()).get("conversation", []))
            await self._ecrire({"$set": {"plan_au_message": nb}}, f"Étape levée par Flore — {etape[:80]}")
        return bool(r.matched_count)

    async def _ajouter(self, liste, cle, element, trace):
        """Ajoute `element` à `liste` sauf si un élément de même `cle` existe : renvoie celui qui fait foi."""
        existant = next((e for e in (await self.etat()).get(liste, []) if e.get(cle) == element[cle]), None)
        if existant:
            return existant
        await self._ecrire({"$push": {liste: element}}, trace)
        return element

    async def hypothese(self, texte):
        hyp = {"id": _identifiant("hyp"), "texte": _texte(texte, MAX_TEXTE), "statut": "a_valider",
               "quand": datetime.now(timezone.utc).isoformat()}
        return await self._ajouter("hypotheses", "texte", hyp, f"Hypothèse proposée par Flore — {hyp['texte'][:80]}")

    async def option(self, titre, description, risque):
        opt = {"id": _identifiant("opt"), "titre": _texte(titre, MAX_TITRE), "description": (description or "")[:MAX_CONTENU],
               "impacts": [], "risque": risque if risque in RISQUES else "moyen", "statut": "a_evaluer"}
        return await self._ajouter("options", "titre", opt, f"Option proposée par Flore — {opt['titre']}")

    async def livrable(self, titre, contenu):
        """Un livrable de même titre est mis à jour (nouvelle version), jamais dupliqué."""
        titre, contenu = _texte(titre, MAX_TITRE), _texte(contenu, MAX_CONTENU * 4)
        now = datetime.now(timezone.utc).isoformat()
        r = await self.db.cases.update_one({"id": self.cid, "livrables.titre": titre},
                                           {"$set": {"livrables.$.contenu": contenu, "livrables.$.cree_le": now}})
        if r.matched_count:
            await self._ecrire({}, f"Livrable mis à jour par Flore — {titre}")
            return {"titre": titre, "contenu": contenu, "cree_le": now}
        liv = {"id": _identifiant("liv"), "titre": titre, "contenu": contenu, "cree_le": now}
        await self._ecrire({"$push": {"livrables": liv}}, f"Livrable produit par Flore — {titre}")
        return liv

    async def precision(self, question, options):
        """Question à options posée à l'humain : en attente jusqu'à la fin de la réponse de Flore (retirer_precision)."""
        if not isinstance(options, list) or not MIN_OPTIONS <= len(options) <= MAX_OPTIONS:
            raise ValueError(f"{MIN_OPTIONS} à {MAX_OPTIONS} options attendues")
        propres = [_texte(o, MAX_OPTION + 1) for o in options]
        if any("\n" in o or len(o) > MAX_OPTION for o in propres):
            raise ValueError(f"une option tient en une ligne de {MAX_OPTION} caractères au plus")
        if len({o.lower() for o in propres}) < len(propres):
            raise ValueError("options en double")
        question = _texte(question, MAX_TEXTE)
        await self._ecrire({"$set": {"precision": {"question": question, "options": propres}}},
                           f"Précision demandée par Flore — {question[:80]}")

    async def retirer_precision(self):
        """La question en attente, retirée du Travail (une seule fois) : elle rejoint alors le message de Flore."""
        avant = await self.db.cases.find_one_and_update({"id": self.cid}, {"$unset": {"precision": ""}},
                                                        projection={"precision": 1, "_id": 0})
        return (avant or {}).get("precision")

    async def resume(self, texte):
        await self._ecrire({"$set": {"resume": _texte(texte, MAX_CONTENU)}}, "Résumé actualisé par Flore")


def _identifiant(prefixe):
    # Pas de « len + 1 » : deux écritures concurrentes ou une suppression produiraient des doublons.
    return f"{prefixe}-{uuid.uuid4().hex[:8]}"


def _rappel_plan(case, plan):
    """Rappel du harness : plan oublié (aucune étape levée ou ajoutée depuis un moment) ou absent."""
    nb = len(case.get("conversation") or [])
    if not plan:
        if nb // 2 >= ECHANGES_SANS_PLAN:
            return ["Pas encore de plan : si la demande demande plusieurs étapes, planifiez-la (planifier)."]
        return []
    if all(q.get("resolue") for q in plan) or case.get("plan_au_message") is None:
        return []
    immobile = (nb - case["plan_au_message"]) // 2
    if immobile >= ECHANGES_AVANT_RAPPEL:
        return [f"Rappel : le plan n'a pas bougé depuis {immobile} échanges ; "
                "levez les étapes faites (lever_etape) ou dites ce qui bloque."]
    return []


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
    lignes += _rappel_plan(case, plan)
    return "\n".join(lignes)
