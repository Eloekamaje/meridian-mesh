import { entetesPerimetre } from "./api";

// Un tour de Flore en AG-UI (backend jumeau/protocole.py) → les rappels de l'interface. Rend { fin: réponse } au
// RUN_FINISHED ; lève une erreur annoncée au RUN_ERROR. `onOutil(outil)` reçoit l'état complet de l'outil à chaque
// changement : { id, nom, libelle, etat: en_cours|fait|erreur, arguments, extrait, duree }.
export function lecteurAgUi({ onEtape, onTexte, onRelecture, onOutil } = {}) {
  const outils = {};
  const args = {};
  const maj = (id, champs) => { outils[id] = { ...outils[id], ...champs }; onOutil?.(outils[id]); };
  return (e) => {
    switch (e.type) {
      case "STEP_STARTED": onEtape?.(e.stepName); break;
      case "TEXT_MESSAGE_CONTENT": onTexte?.(e.delta); break;
      case "CUSTOM": if (e.name === "relecture") onRelecture?.(); break;
      case "TOOL_CALL_START": {
        const libelle = e.metadata?.libelle || null;
        if (libelle && !onOutil) onEtape?.(libelle); // un appelant qui ne montre que des libellés le voit quand même
        args[e.toolCallId] = "";
        maj(e.toolCallId, { id: e.toolCallId, nom: e.toolCallName, libelle, etat: "en_cours" });
        break;
      }
      case "TOOL_CALL_ARGS": args[e.toolCallId] = (args[e.toolCallId] || "") + e.delta; break;
      case "TOOL_CALL_END": {
        try { maj(e.toolCallId, { arguments: JSON.parse(args[e.toolCallId] || "null") }); } catch { /* arguments illisibles : on ne les montre pas */ }
        break;
      }
      case "TOOL_CALL_RESULT":
        maj(e.toolCallId, { etat: e.metadata?.etat || "fait", extrait: e.content, duree: e.metadata?.duree ?? null });
        break;
      case "RUN_FINISHED": return { fin: e.result };
      case "RUN_ERROR": throw Object.assign(new Error(e.message), { annoncee: true });
      default: break;
    }
    return null;
  };
}

// `signal` (AbortController) : l'interlocuteur arrête la réponse ; la promesse rejette alors une AbortError (estArret).
// Réponse de Flore au fil de l'eau : ses vrais outils, son brouillon (encore en relecture), puis la réponse relue.
// Rend la réponse finale ; rejette en cas d'erreur annoncée ou de flux impossible.
export async function demanderEnFlux(chemin, corps, { onEtape, onTexte, onRelecture, onOutil, signal } = {}) {
  const lire = lecteurAgUi({ onEtape, onTexte, onRelecture, onOutil });
  const reponse = await fetch(`${process.env.REACT_APP_BACKEND_URL || ""}/api${chemin}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...entetesPerimetre() },
    body: JSON.stringify(corps),
    signal,
  });
  if (!reponse.ok || !reponse.body) throw new Error(`flux indisponible (${reponse.status})`);
  const lecteur = reponse.body.getReader();
  const decodeur = new TextDecoder();
  let tampon = "";
  for (;;) {
    const { value, done } = await lecteur.read();
    if (done) break;
    tampon += decodeur.decode(value, { stream: true });
    const blocs = tampon.split("\n\n");
    tampon = blocs.pop();
    for (const bloc of blocs) {
      const ligne = bloc.split("\n").find((l) => l.startsWith("data: "));
      if (!ligne) continue;
      const r = lire(JSON.parse(ligne.slice(6)));
      if (r) return r.fin;
    }
  }
  throw new Error("flux interrompu avant la réponse");
}

// Le brouillon s'affiche sans ses citations (elles iront dans le volet des preuves de la réponse relue).
export function brouillonLisible(texte) {
  return (texte || "").replace(/\s*\(?`[^`]*#L\d+[^`]*`\)?/g, "").replace(/```mermaid[\s\S]*?(```|$)/g, "");
}

// L'interlocuteur a arrêté la réponse (ce n'est pas une panne : pas de repli, pas de message d'erreur).
export const estArret = (err) => err?.name === "AbortError";

// L'activité d'un tour, dans l'ordre : des étapes { label } et des outils { label, outil }. `surChangement(ops)`
// reçoit une nouvelle liste à chaque changement ; un outil mis à jour (arguments, issue) garde sa place.
export function journalActivite(surChangement) {
  const ops = [];
  const publier = () => surChangement?.([...ops]);
  return {
    ops,
    onEtape: (label) => { ops.push({ label }); publier(); },
    onOutil: (outil) => {
      const op = { label: outil.libelle || outil.nom, outil };
      const i = ops.findIndex((o) => o.outil?.id === outil.id);
      if (i < 0) ops.push(op); else ops[i] = op;
      publier();
    },
  };
}

// L'activité d'un tour fini, gardée avec la réponse (null s'il n'y a rien eu).
export const activiteDuTour = (ops, id) => (ops.length ? { id, status: "done", ops: ops.map((o) => ({ ...o, status: "done" })) } : null);
