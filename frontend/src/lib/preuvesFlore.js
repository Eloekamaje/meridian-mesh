import { createContext } from "react";

// Les preuves d'une réponse de Flore, dans le texte (Design System §60, §67, §69-70, §131) : le serveur
// (jumeau/flore.py · pastiller) remplace chaque citation par une pastille `[n](#preuve-n)`, n étant la place de la
// preuve dans le volet sous le message. Ici : la logique sans écran ; les composants lisent PreuvesContexte.

// { preuves, texte, ouvrir(n) } fourni par MessageFlore : le rendu Markdown le lit où qu'il soit (corps standard,
// texte au fil de l'eau du panneau, corps du Travail).
export const PreuvesContexte = createContext(null);

const RE_PASTILLE = /\s*\[\d+\]\(#preuve-\d+\)/g;

export function numeroPastille(href) {
  const m = /^#preuve-(\d+)$/.exec(href || "");
  return m ? Number(m[1]) : null;
}

// Au fil de l'eau, le texte est coupé n'importe où : une pastille à moitié écrite (« [1](#pre ») ne s'affiche pas.
export const couperPastille = (texte) => (texte || "").replace(/\s*\[\d*(\](\([^)]*)?)?$/, "");

export const sansPastilles = (texte) => (texte || "").replace(RE_PASTILLE, "");

const sansMarques = (t) => sansPastilles(t).replace(/\*\*|__|`/g, "").replace(/^\s*(?:[-*+]|\d+\.)\s+/, "").trim();

// La phrase que supporte la preuve n (« Ce que ça supporte ») : celle qui porte sa pastille.
export function phraseDe(texte, n) {
  const marque = `](#preuve-${n})`;
  const ligne = (texte || "").split("\n").find((l) => l.includes(marque));
  if (!ligne) return null;
  const phrases = ligne.split(/(?<=[.!?])\s+(?=[^\s])/);
  return sansMarques(phrases.find((p) => p.includes(marque)) || ligne);
}

// Une note d'impact (méthode evaluer-impact) : une ligne par effet, commençant par sa classe en gras. Rend
// { prouves, total } — ou null s'il n'y a pas de note.
export const RE_EFFET = /^\s*[-*+]\s+\*\*(bloquant|dégradé|degrade|sans effet(?: visible)?|inconnu)(?=[\s*:—-])[^*]*\*\*/i;
export function bilanEffets(texte) {
  const effets = (texte || "").split("\n").filter((l) => RE_EFFET.test(l));
  if (!effets.length) return null;
  return { prouves: effets.filter((l) => /\]\(#preuve-\d+\)/.test(l)).length, total: effets.length };
}

const TYPES = { git: "Code", confluence: "Confluence", jira: "Jira", servicenow: "ServiceNow", datadog: "Datadog" };
export function typeSource(detail) {
  const schema = /^([a-z]+):\/\//.exec(detail || "")?.[1];
  return TYPES[schema] || (schema ? schema[0].toUpperCase() + schema.slice(1) : "Source");
}
