// Logique sans écran de la conversation unique (MERIDIAN_Conversation_Contrat_v1) : le panneau Flore et le fil d'un
// Travail parlent au même serveur, sous le même préfixe /cases/{cid}, avec les mêmes actions.

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
      e.trace = m._activite || null;
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
