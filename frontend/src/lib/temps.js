// Parse les dates du Mesh : ISO ou libellés relatifs français (« aujourd'hui · 14 h 32 », « il y a 3 jours »…)
export function parseQuand(s, ref = new Date()) {
  if (!s) return null;
  const direct = new Date(s);
  if (!Number.isNaN(direct.getTime())) return direct;
  const base = new Date(ref);
  const hm = s.match(/(\d{1,2})\s*h\s*(\d{2})/);
  const avecHeure = (jours) => {
    const d = new Date(base);
    d.setDate(d.getDate() - jours);
    if (hm) d.setHours(parseInt(hm[1], 10), parseInt(hm[2], 10), 0, 0);
    return d;
  };
  if (s.startsWith("aujourd'hui")) return avecHeure(0);
  if (s.startsWith("hier")) return avecHeure(1);
  const m = s.match(/il y a (\d+)\s*(min|h|jours?|j|sem(?:aines?)?\.?|mois|ans?)/);
  if (!m) return null;
  const n = parseInt(m[1], 10);
  const u = m[2];
  const d = new Date(base);
  if (u === "min") d.setMinutes(d.getMinutes() - n);
  else if (u === "h") d.setHours(d.getHours() - n);
  else if (u.startsWith("sem")) d.setDate(d.getDate() - n * 7);
  else if (u.startsWith("mois")) d.setDate(d.getDate() - n * 30);
  else if (u.startsWith("an")) d.setFullYear(d.getFullYear() - n);
  else d.setDate(d.getDate() - n);
  return d;
}

export const finDeJournee = (d) => {
  const x = new Date(d);
  x.setHours(23, 59, 59, 999);
  return x;
};

export const fmtDate = (d) =>
  new Date(d).toLocaleDateString("fr-FR", { day: "numeric", month: "long" });

export const fmtDateLongue = (d) =>
  new Date(d).toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });

export const fmtDateInput = (d) => {
  const x = new Date(d);
  return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(x.getDate()).padStart(2, "0")}`;
};
