"""Progression d'un tour Flore : libellés, suivi d'outils et activité, sans transport.

Ces types sont partagés par les adapters LLM et le flux SSE ; ils ne dépendent ni de FastAPI
ni d'un client.
"""
from __future__ import annotations

import time

LIBELLES_OUTILS = {
    "mes_connaissances": "Je consulte ce que l'on sait de l'application…",
    "architecture": "Je regarde de quoi l'application est faite…",
    "chercher_texte": "Je cherche dans le code…", "chercher_symbole": "Je cherche dans le code…",
    "tracer_appels": "Je regarde qui appelle quoi…",
    "suivre_appels": "Je suis l'enchaînement dans le code…",
    "lire_code": "Je lis le code concerné…",
    "historique_du_code": "Je regarde l'histoire du code…", "ce_qui_a_change": "Je regarde ce qui a changé…",
    "chercher_dans": "Je cherche dans la documentation et les outils de l'équipe…",
    "lire_dans": "Je lis la documentation concernée…",
    "lire_piece": "Je lis la pièce jointe…", "chercher_pieces": "Je cherche dans les pièces jointes…",
    "lire_table": "Je lis un tableau de la pièce…",
    "dessiner_schema": "Je dessine le schéma…",
    "consulter_jumeau": "Je consulte l'application concernée…",
    "montrer_sur_atlas": "Je prépare la carte…",
    "consulter_methode": "Je choisis comment m'y prendre…",
    "proposer_connaissance": "Je consigne ce que j'ai appris…",
    "eprouver_hypothese": "Je mets une hypothèse à l'épreuve…",
    "proposer_hypothese": "Je pose une hypothèse à vérifier…",
    "recouper_connaissance": "Je recoupe avec une autre source…",
}

EXTRAIT_OUTIL = 300  # caractères du résultat d'un outil montrés à l'écran (le reste est dans la réponse, cité)


def _extrait(resultat):
    """Le début du résultat d'un outil, en texte : une donnée lue, affichée comme telle, jamais une instruction."""
    texte = " ".join(b["text"] for b in resultat.get("content") or [] if isinstance(b, dict) and isinstance(b.get("text"), str))
    return texte if len(texte) <= EXTRAIT_OUTIL else texte[:EXTRAIT_OUTIL] + "…"


class SuiviOutils:
    """Le flux Strands d'un agent → les événements `outil` (début, arguments complets, issue, durée d'exécution).
    `parent` : le jumeau dont le sous-agent fait la mission (ses outils s'affichent sous sa consultation) ;
    `ignorer` : des outils internes (sortie structurée) qu'on ne montre pas."""

    def __init__(self, emit, parent=None, ignorer=()):
        self.emit, self.parent, self.ignorer, self.debuts = emit, parent, set(ignorer), {}

    async def suivre(self, e):
        """Rend True si l'événement concernait un outil (annoncé, exécuté ou fini)."""
        if (outil := e.get("current_tool_use")) and (oid := outil.get("toolUseId")):
            if oid not in self.debuts and outil.get("name") not in self.ignorer:
                self.debuts[oid] = time.monotonic()  # Strands répète l'appel pendant que ses arguments arrivent
                await self.emit({"type": "outil", "id": oid, "nom": outil.get("name"),
                                 "libelle": LIBELLES_OUTILS.get(outil.get("name")), "etat": "en_cours",
                                 **({"parent": self.parent} if self.parent else {})})
            return True
        if not isinstance(m := e.get("message"), dict):
            return False
        for bloc in m.get("content") or []:
            if (u := bloc.get("toolUse")) and u.get("toolUseId") in self.debuts:
                self.debuts[u["toolUseId"]] = time.monotonic()  # arguments complets : l'outil s'exécute maintenant
                await self.emit({"type": "outil", "id": u["toolUseId"], "arguments": u.get("input")})
            elif (r := bloc.get("toolResult")) and (oid := r.get("toolUseId")) in self.debuts:
                await self.emit({"type": "outil", "id": oid, "etat": "erreur" if r.get("status") == "error" else "fait",
                                 "duree": round(time.monotonic() - self.debuts[oid], 2), "extrait": _extrait(r)})
        return True


class Activite:
    """L'activité d'un tour, telle qu'elle a eu lieu : étapes et outils dans l'ordre, au format que l'interface
    affiche (`{label, outil?}`, comme journalActivite). Gardée avec la réponse, et avec un tour arrêté."""

    def __init__(self):
        self.ops = []

    def suivre(self, e):
        if e.get("type") == "etape":
            self.ops = [*self.ops, {"label": e.get("libelle") or ""}]
        elif e.get("type") == "outil":
            champs = {k: v for k, v in e.items() if k != "type"}
            i = next((k for k, o in enumerate(self.ops) if (o.get("outil") or {}).get("id") == e.get("id")), None)
            if i is None:
                self.ops = [*self.ops, {"label": e.get("libelle") or e.get("nom") or "", "outil": champs}]
            else:
                self.ops = [*self.ops[:i], {**self.ops[i], "outil": {**self.ops[i]["outil"], **champs}}, *self.ops[i + 1:]]
        elif e.get("type") == "mission":  # la fin de la mission d'un jumeau : sur sa (dernière) consultation
            i = next((k for k in range(len(self.ops) - 1, -1, -1) if (o := self.ops[k].get("outil") or {}).get("nom")
                      == "consulter_jumeau" and (o.get("arguments") or {}).get("jumeau") == e.get("jumeau")), None)
            if i is not None:
                bilan = {k: e.get(k) for k in ("etat", "confiance", "preuves", "constat")}
                self.ops = [*self.ops[:i], {**self.ops[i], "outil": {**self.ops[i]["outil"], "mission": bilan}},
                            *self.ops[i + 1:]]
