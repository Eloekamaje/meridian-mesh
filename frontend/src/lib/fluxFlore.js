import { entetesPerimetre } from "./api";

// Un tour de Flore en AG-UI (backend jumeau/protocole.py) → les rappels de l'interface. Rend { fin: réponse } au
// RUN_FINISHED ; lève une erreur annoncée au RUN_ERROR. `onOutil(outil)` reçoit l'état complet de l'outil à chaque
// changement : { id, nom, libelle, etat: en_cours|fait|erreur, arguments, extrait, duree }.
export function lecteurAgUi({ onEtape, onTexte, onRelecture, onOutil, onDebut, onMission } = {}) {
  const outils = {};
  const args = {};
  const maj = (id, champs) => { outils[id] = { ...outils[id], ...champs }; onOutil?.(outils[id]); };
  return (e) => {
    switch (e.type) {
      case "RUN_STARTED": onDebut?.(e.runId); break;
      case "STEP_STARTED": onEtape?.(e.stepName); break;
      case "TEXT_MESSAGE_CONTENT": onTexte?.(e.delta); break;
      case "CUSTOM":
        if (e.name === "relecture") onRelecture?.();
        else if (e.name === "mission") onMission?.(e.value); // fin de la mission d'un jumeau (carte d'expert)
        break;
      case "TOOL_CALL_START": {
        const libelle = e.metadata?.libelle || null;
        if (libelle && !onOutil) onEtape?.(libelle); // un appelant qui ne montre que des libellés le voit quand même
        args[e.toolCallId] = "";
        const parent = e.metadata?.parent;
        maj(e.toolCallId, { id: e.toolCallId, nom: e.toolCallName, libelle, etat: "en_cours", debut: Date.now(), ...(parent ? { parent } : {}) });
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
      case "RUN_FINISHED":
        // arrêté (ailleurs, ou avant une reprise) : comme un arrêt ici, l'appelant relit la conversation
        if (e.outcome?.type === "cancelled") throw Object.assign(new Error("tour arrêté"), { name: "AbortError" });
        return { fin: e.result };
      case "RUN_ERROR": throw Object.assign(new Error(e.message), { annoncee: true });
      default: break;
    }
    return null;
  };
}

const API = () => `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const PAUSES_REPRISE = [1000, 2000, 4000]; // ms avant chaque tentative de reprise après une coupure

const attendre = (ms, signal) => new Promise((ok, ko) => {
  const t = setTimeout(ok, ms);
  signal?.addEventListener("abort", () => { clearTimeout(t); ko(Object.assign(new Error("arrêt"), { name: "AbortError" })); });
});

// Les événements d'une réponse SSE, un par ligne `data:`.
async function* evenements(reponse) {
  const lecteur = reponse.body.getReader();
  const decodeur = new TextDecoder();
  let tampon = "";
  for (;;) {
    const { value, done } = await lecteur.read();
    if (done) return;
    tampon += decodeur.decode(value, { stream: true });
    const blocs = tampon.split("\n\n");
    tampon = blocs.pop();
    for (const bloc of blocs) {
      const ligne = bloc.split("\n").find((l) => l.startsWith("data: "));
      if (ligne) yield JSON.parse(ligne.slice(6));
    }
  }
}

// Réponse de Flore au fil de l'eau (AG-UI) : ses vrais outils, son brouillon (encore en relecture), puis la réponse
// relue, qu'elle rend. `signal` : « Arrêter » — le serveur est prié d'arrêter le tour (il enregistre ce qui était
// écrit) AVANT que la promesse ne rejette une AbortError (estArret) : la relecture qui suit voit la réponse partielle.
// Une coupure de réseau n'arrête pas le tour : `onCoupure(true)`, puis reprise depuis le dernier événement lu
// (`/tours/{id}/flux?depuis=n`), `onCoupure(false)` quand le fil est renoué. Rejette sur une erreur annoncée.
export async function demanderEnFlux(chemin, corps, { onEtape, onTexte, onRelecture, onOutil, onMission, onCoupure, signal } = {}) {
  let tour = null;
  let lus = 0;
  const lire = lecteurAgUi({ onEtape, onTexte, onRelecture, onOutil, onMission, onDebut: (id) => { tour = id; } });
  const entetes = { Accept: "text/event-stream", ...entetesPerimetre() };
  let reponse = await fetch(`${API()}${chemin}`, {
    method: "POST", headers: { "Content-Type": "application/json", ...entetes }, body: JSON.stringify(corps), signal,
  });
  if (!reponse.ok || !reponse.body) throw new Error(`flux indisponible (${reponse.status})`);
  for (let essai = 0; ; ) {
    try {
      for await (const e of evenements(reponse)) {
        lus += 1;
        const r = lire(e);
        if (r) return r.fin;
        if (essai && lus) { onCoupure?.(false); essai = 0; } // le fil est renoué
      }
      throw new Error("flux interrompu avant la réponse");
    } catch (err) {
      if (estArret(err) || signal?.aborted) {
        // ponytail: un arrêt avant RUN_STARTED (premières millisecondes) ne peut pas viser le tour ; il se termine
        if (tour && !(err.message === "tour arrêté")) {
          await fetch(`${API()}/tours/${tour}/arreter`, { method: "POST", headers: entetesPerimetre() }).catch(() => {});
        }
        throw err;
      }
      if (err.annoncee || !tour) throw err;
      // le tour continue côté serveur : l'appelant ne doit pas reposer la question (il attend la réponse enregistrée)
      if (essai >= PAUSES_REPRISE.length) throw Object.assign(err, { tourEnCours: true });
      onCoupure?.(true);
      await attendre(PAUSES_REPRISE[essai], signal);
      essai += 1;
      reponse = await fetch(`${API()}/tours/${tour}/flux?depuis=${lus}`, { headers: entetes, signal })
        .catch((e) => (estArret(e) ? Promise.reject(e) : { ok: false, status: 0 }));
      if (reponse.status === 404) throw Object.assign(err, { tourEnCours: true }); // tour oublié : l'appelant relit
      if (!reponse.ok || !reponse.body) reponse = { ok: false, body: { getReader: () => ({ read: () => Promise.reject(err) }) } };
    }
  }
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
    // Fin de la mission d'un jumeau : sur sa (dernière) consultation (Design System §85 : état, confiance, preuves)
    onMission: ({ jumeau, type, ...bilan }) => {
      const i = ops.map((o) => o.outil).findLastIndex((o) => o?.nom === "consulter_jumeau" && o.arguments?.jumeau === jumeau);
      if (i < 0) return;
      ops[i] = { ...ops[i], outil: { ...ops[i].outil, mission: bilan } };
      publier();
    },
  };
}

// Les consultations de jumeaux, chacune avec les outils de sa mission (rangés sous elle par `parent`).
export function grouperConsultations(ops) {
  return (ops || []).filter((o) => o.outil?.nom === "consulter_jumeau").map((c) => ({
    ...c, sous: ops.filter((o) => o.outil?.parent && o.outil.parent === c.outil.arguments?.jumeau),
  }));
}

export function resumeConsultations(ops) {
  const c = grouperConsultations(ops);
  if (!c.length) return null;
  const finies = c.filter((x) => x.outil.mission || x.outil.etat !== "en_cours").length;
  return `${c.length} jumeau${c.length > 1 ? "x" : ""} consulté${c.length > 1 ? "s" : ""} · ${finies} terminé${finies > 1 ? "s" : ""}`;
}

// L'activité d'un tour fini, gardée avec la réponse (null s'il n'y a rien eu).
export const activiteDuTour = (ops, id) => (ops.length ? { id, status: "done", ops: ops.map((o) => ({ ...o, status: "done" })) } : null);
