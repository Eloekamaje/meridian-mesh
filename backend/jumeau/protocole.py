"""Les événements internes de Flore, traduits en AG-UI (ag-ui-protocol 1.0, https://docs.ag-ui.com).

Flore émet un petit vocabulaire interne (`etape`, `texte`, `relecture`, `outil`) ; le fil du flux le traduit ici, et
nulle part ailleurs, en événements standard : un client AG-UI quelconque peut suivre un tour de Flore. Ce qui est
propre à Méridian voyage dans les champs prévus par le protocole : le libellé en mots simples d'un outil dans
`metadata`, la relecture comme événement `CUSTOM`.
"""
import json

from ag_ui import core as ag


class Traducteur:
    """Un tour (`run`) d'un fil (`thread` = le Travail). Garde l'état nécessaire aux paires début/fin."""

    def __init__(self, fil, tour):
        self.fil, self.tour = fil, tour
        self.message = f"{tour}-reponse"
        self.texte_ouvert = False
        self.etape = None
        self.outils_ouverts = set()

    def debut(self):
        return [ag.RunStartedEvent(thread_id=self.fil, run_id=self.tour)]

    def traduire(self, e):
        quoi = e.get("type")
        if quoi == "texte":
            if not e.get("delta"):
                return []  # AG-UI refuse un morceau vide
            ouverture = [] if self.texte_ouvert else [ag.TextMessageStartEvent(message_id=self.message, role="assistant")]
            self.texte_ouvert = True
            return ouverture + [ag.TextMessageContentEvent(message_id=self.message, delta=e["delta"])]
        if quoi == "relecture":
            return self._fermer_texte() + [ag.CustomEvent(name="relecture", value=None)]
        if quoi == "etape":
            sortie = self._fermer_etape()
            self.etape = e.get("libelle") or ""
            return sortie + [ag.StepStartedEvent(step_name=self.etape)]
        if quoi == "outil":
            return self._outil(e)
        return [ag.CustomEvent(name=str(quoi), value=e)]

    def _outil(self, e):
        oid = e["id"]
        if e.get("etat") == "en_cours":
            self.outils_ouverts.add(oid)
            meta = {"libelle": e["libelle"]} if e.get("libelle") else None
            return [ag.ToolCallStartEvent(tool_call_id=oid, tool_call_name=e.get("nom") or "outil", metadata=meta)]
        sortie = []
        if "arguments" in e:
            sortie.append(ag.ToolCallArgsEvent(tool_call_id=oid, delta=json.dumps(e["arguments"], ensure_ascii=False, default=str)))
        if oid in self.outils_ouverts and ("arguments" in e or e.get("etat")):
            self.outils_ouverts.discard(oid)
            sortie.append(ag.ToolCallEndEvent(tool_call_id=oid))
        if e.get("etat") in ("fait", "erreur"):
            sortie.append(ag.ToolCallResultEvent(message_id=f"{oid}-resultat", tool_call_id=oid, role="tool",
                                                 content=e.get("extrait") or "",
                                                 metadata={"etat": e["etat"], "duree": e.get("duree")}))
        return sortie

    def _fermer_texte(self):
        if not self.texte_ouvert:
            return []
        self.texte_ouvert = False
        return [ag.TextMessageEndEvent(message_id=self.message)]

    def _fermer_etape(self):
        if self.etape is None:
            return []
        etape, self.etape = self.etape, None
        return [ag.StepFinishedEvent(step_name=etape)]

    def fin(self, reponse):
        return self._fermer_texte() + self._fermer_etape() + [
            ag.RunFinishedEvent(thread_id=self.fil, run_id=self.tour, result=reponse)]

    def arret(self):
        """Arrêté par l'interlocuteur : le tour finit avec l'issue AG-UI « cancelled »."""
        return self._fermer_texte() + self._fermer_etape() + [
            ag.RunFinishedEvent(thread_id=self.fil, run_id=self.tour, outcome=ag.RunFinishedCancelledOutcome(type="cancelled"))]

    def erreur(self, message):
        return [ag.RunErrorEvent(message=message)]


def encoder(evenement):
    """Une ligne SSE, comme l'encodeur officiel (`data: <json camelCase sans champs vides>`)."""
    return f"data: {evenement.model_dump_json(by_alias=True, exclude_none=True)}\n\n"
