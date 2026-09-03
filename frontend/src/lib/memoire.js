// Mémoire locale de l'Atlas : favoris, jumeaux consultés, recherches récentes.
// Stockage navigateur (localStorage) — personnel à l'utilisateur, jamais envoyé au serveur.
const CLE_FAVORIS = "meridian:favoris";
const CLE_RECENTS = "meridian:recents";
const CLE_RECHERCHES = "meridian:recherches";
const MAX = 8;

function lire(cle) {
  try {
    return JSON.parse(localStorage.getItem(cle)) || [];
  } catch {
    return [];
  }
}

function ecrire(cle, valeurs) {
  try {
    localStorage.setItem(cle, JSON.stringify(valeurs.slice(0, MAX)));
  } catch { /* quota plein : silencieux */ }
}

export const favoris = () => lire(CLE_FAVORIS);
export const estFavori = (id) => favoris().includes(id);

export function basculerFavori(id) {
  const f = favoris();
  const next = f.includes(id) ? f.filter((x) => x !== id) : [id, ...f];
  ecrire(CLE_FAVORIS, next);
  return next;
}

export const recents = () => lire(CLE_RECENTS);
export function noterRecent(id) {
  ecrire(CLE_RECENTS, [id, ...recents().filter((x) => x !== id)]);
}

export const recherches = () => lire(CLE_RECHERCHES);
export function noterRecherche(terme) {
  const t = (terme || "").trim();
  if (!t) return;
  ecrire(CLE_RECHERCHES, [t, ...recherches().filter((x) => x !== t)]);
}
