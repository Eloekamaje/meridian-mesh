import { entetesPerimetre } from "./api";

// `signal` (AbortController) : l'interlocuteur arrête la réponse ; la promesse rejette alors une AbortError (estArret).
// Réponse de Flore au fil de l'eau (backend jumeau/flux.py) : ses vraies étapes, son brouillon (encore en relecture),
// puis la réponse relue. Rend la réponse finale ; rejette en cas d'erreur annoncée ou de flux impossible.
export async function demanderEnFlux(chemin, corps, { onEtape, onTexte, onRelecture, signal } = {}) {
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
      const e = JSON.parse(ligne.slice(6));
      if (e.type === "etape") onEtape?.(e.libelle);
      else if (e.type === "texte") onTexte?.(e.delta);
      else if (e.type === "relecture") onRelecture?.();
      else if (e.type === "final") return e.reponse;
      else if (e.type === "erreur") throw Object.assign(new Error(e.message), { annoncee: true });
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
