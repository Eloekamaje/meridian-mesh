export const numeroCase = (c) => `CASE-${String(c.num ?? 0).padStart(3, "0")}`;

export const SENSIBILITES = {
  publique: ["Publique", "#047857"],
  interne: ["Interne", "#3730A3"],
  restreinte: ["Restreinte", "#B91C1C"],
};

export const rel = (iso) => {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 3600) return `il y a ${Math.max(1, Math.round(s / 60))} min`;
  if (s < 86400) return `il y a ${Math.round(s / 3600)} h`;
  return `il y a ${Math.round(s / 86400)} j`;
};

export const catHistorique = (texte) => {
  if (texte.startsWith("Décision")) return "decisions";
  if (texte.startsWith("Investigation ouverte") || texte.startsWith("Hypothèse") || texte.startsWith("Résumé")) return "decouvertes";
  return "mesh";
};

export const FILTRES_ACTIVITE = [
  ["tout", "Tout"],
  ["discussions", "Discussions"],
  ["flore", "Flore"],
  ["decouvertes", "Découvertes"],
  ["decisions", "Décisions"],
  ["mesh", "Changements du Mesh"],
];
