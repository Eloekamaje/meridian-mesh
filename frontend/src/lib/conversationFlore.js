// Logique sans écran de la conversation unique (MERIDIAN_Conversation_Contrat_v1) : le panneau Flore et le fil d'un
// Travail parlent au même serveur, sous le même préfixe /cases/{cid}, avec les mêmes actions.

import { activiteDuTour } from "./fluxFlore";

// L'activité d'une réponse : celle vue en direct, sinon celle que le serveur a enregistrée (après rechargement).
export const activiteDuMessage = (m) => m?._activite || activiteDuTour(m?.activite || [], `enregistree-${m?.quand || ""}`);

export const prefixeTravail = (cid) => `/cases/${encodeURIComponent(cid)}`;
export const urlMessage = (prefixe, n, action) => `${prefixe}/messages/${n}/${action}`;

// ‹ k/N › : null s'il n'y a qu'une seule version (ou branche) ; sinon la position et les voisins.
export function navigation(elements, actif) {
  const total = Array.isArray(elements) ? elements.length : 0;
  if (total < 2) return null;
  const i = Math.min(Math.max(actif ?? 0, 0), total - 1);
  return { k: i + 1, total, precedent: i > 0 ? i - 1 : null, suivant: i < total - 1 ? i + 1 : null };
}
export const navVersions = (m) => navigation(m?.versions, m?.version);
export const navBranches = (m) => navigation(m?.branches, m?.branche);

export const remplacerMessage = (messages, n, nouveau) => messages.map((m, k) => (k === n ? nouveau : m));

// Le serveur n'a peut-être pas encore la route : on le dit, sans faire semblant.
export function erreurAction(err, libelle) {
  const statut = err?.response?.status ?? Number(/\((\d{3})\)/.exec(err?.message || "")?.[1]);
  if ([404, 405, 501].includes(statut)) return `${libelle} : le serveur ne propose pas encore cette action.`;
  return `${libelle} impossible.`;
}

// Regroupe les messages en échanges (question + réponse) pour l'affichage du panneau. `nq` / `nr` sont les index
// serveur des deux messages (les marqueurs locaux n'en ont pas et ne comptent pas).
export function regrouper(messages) {
  const echanges = [];
  let n = -1;
  let courant = null;
  for (const m of messages || []) {
    if (m.marqueur) { courant = null; echanges.push(m); continue; }
    n += 1;
    if (m.role === "utilisateur") {
      courant = { question: m.texte, qMsg: m, nq: n };
      echanges.push(courant);
    } else {
      const e = courant && !courant.data ? courant : { question: null };
      e.data = { ...m, reponse: m.texte };
      e.fMsg = m;
      e.nr = n;
      e.trace = activiteDuMessage(m);
      if (e !== courant) echanges.push(e);
      courant = null;
    }
  }
  return echanges;
}

// Réponse arrêtée avant que le serveur ne l'ait enregistrée : ce qui était écrit, marqué interrompu.
export const reponseInterrompue = (texte, quand = new Date().toISOString()) =>
  ({ role: "flore", texte, interrompu: true, quand, preuves: [], contributions: [] });

// Recherche des travaux : le serveur cherche aussi dans le texte des messages (GET /cases?q=). Un ancien serveur
// ignore `q` et rend tout : dans ce cas (liste complète) on retombe sur le titre, côté client.
export function resultatsRecherche(q, tous, reponse) {
  const mot = (q || "").trim().toLowerCase();
  if (!mot) return tous;
  if (Array.isArray(reponse) && reponse.length < tous.length) return reponse;
  return tous.filter((c) => (c.titre || "").toLowerCase().includes(mot) || (c.objectif || "").toLowerCase().includes(mot));
}

// Le Travail créé par le panneau naît « conversation » (privé à l'auteur) ; « Conserver » le passe à « actif ».
export const STATUT_CONVERSATION = "conversation";
export const STATUT_CONSERVE = "actif";
export const estConversation = (c) => c?.statut === STATUT_CONVERSATION;
// Paramètre de liste : le serveur ne rend les conversations de l'auteur que si on les demande (nom à aligner à l'intégration)
export const PARAM_CONVERSATIONS = { inclure_conversations: 1 };

// Flore a-t-elle produit un plan, une option, une décision ou un livrable ? (c'est alors, et alors seulement, qu'on
// propose de conserver — jamais après N échanges, jamais sans clic.)
const rempli = (v) => (Array.isArray(v) ? v.length > 0 : !!v);
export function floreAProduit(travail, messages) {
  const champs = ["plan", "options", "livrables", "decisions"];
  if (travail && champs.some((k) => rempli(travail[k]))) return true;
  return (messages || []).some((m) => m.role === "flore"
    && (rempli(m.decisions) || rempli(m.options) || rempli(m.plan) || rempli(m.livrables) || !!m.documentCanvas || !!m.propose_passation));
}

// Modifier la question n (index serveur) : elle prend le nouveau texte et la suite disparaît tout de suite, comme le
// fera le serveur (la suite est rangée dans une branche) ; les marqueurs locaux d'avant restent.
export function tronquerApres(messages, n, texte) {
  const garde = [];
  let k = -1;
  for (const m of messages || []) {
    if (!m.marqueur) k += 1;
    if (k > n || (m.marqueur && k === n)) break;
    garde.push(k === n ? { ...m, texte } : m);
  }
  return garde;
}

// Les marqueurs « Contexte actualisé » ne vivent que dans le navigateur : relire la conversation du serveur les
// remet après le même nombre de messages qu'avant (en bas si la conversation est devenue plus courte).
export function garderReperes(avant, conv) {
  const reperes = [];
  let k = 0;
  for (const m of avant || []) {
    if (m.marqueur) reperes.push({ apres: k, m });
    else k += 1;
  }
  if (!reperes.length) return conv;
  const res = [];
  conv.forEach((m, i) => {
    reperes.filter((r) => r.apres === i).forEach((r) => res.push(r.m));
    res.push(m);
  });
  reperes.filter((r) => r.apres >= conv.length).forEach((r) => res.push(r.m));
  return res;
}

// Un tour arrêté, expliqué : ce que Flore avait fait, ce qui était en cours, ce qui avait été écrit. Rien n'est
// présenté comme vérifié (la réponse n'a pas été relue).
export function explicationArret(m) {
  const outils = (m?.activite || []).map((o) => o.outil).filter(Boolean);
  const faits = outils.filter((o) => o.etat !== "en_cours").map((o) => o.nom);
  const enCours = outils.filter((o) => o.etat === "en_cours").map((o) => o.nom);
  const n = (m?.texte || "").length;
  const parties = ["Arrêté par vous"];
  if (faits.length) parties.push(`${faits.length} outil${faits.length > 1 ? "s" : ""} fait${faits.length > 1 ? "s" : ""} (${[...new Set(faits)].join(", ")})`);
  if (enCours.length) parties.push(`${enCours.length} en cours (${[...new Set(enCours)].join(", ")})`);
  parties.push(n ? `${n} caractère${n > 1 ? "s" : ""} écrit${n > 1 ? "s" : ""}` : "rien d'écrit");
  parties.push("non relu");
  return parties.join(" · ");
}

// La connexion n'a pas pu être renouée, mais le tour continue côté serveur : relire le Travail jusqu'à ce que la
// question et sa réponse y soient (`nAvant` : nombre de messages avant l'envoi). Rend le Travail, ou null.
export async function attendreReponse(charger, nAvant, { pas = 3000, essais = 40 } = {}) {
  for (let i = 0; i < essais; i += 1) {
    await new Promise((ok) => setTimeout(ok, pas));
    const travail = await charger().catch(() => null);
    if ((travail?.conversation || []).length >= nAvant + 2) return travail;
  }
  return null;
}
