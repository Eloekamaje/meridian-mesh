// Coût et temps d'une réponse de Flore : une estimation lisible, jamais une facture.
const SYMBOLES = { USD: "$", CAD: "$ CA", EUR: "€", GBP: "£" };

export function formatDuree(secondes) {
  const valeur = Number(secondes);
  if (secondes == null || Number.isNaN(valeur)) return "";
  return `${valeur.toFixed(1).replace(".", ",")} s`;
}

export function formatJetons(nombre) {
  const valeur = Number(nombre);
  if (!Number.isFinite(valeur) || valeur <= 0) return "";
  return `${valeur.toLocaleString("fr-FR")} jetons`;
}

export function formatCout(cout) {
  if (!cout || cout.montant == null || Number.isNaN(Number(cout.montant))) return "";
  const montant = Number(cout.montant);
  const texte = montant < 0.01 ? montant.toFixed(4) : montant.toFixed(2);
  const symbole = SYMBOLES[String(cout.devise || "USD").toUpperCase()] || cout.devise || "USD";
  return `~${texte.replace(".", ",")} ${symbole}`;
}

export function coutTemps(message) {
  const durees = message?.durees || {};
  const usage = message?.usage || {};
  const morceaux = [];
  if (durees.total != null) morceaux.push(formatDuree(durees.total));
  if (durees.premier_texte != null) morceaux.push(`premier mot ${formatDuree(durees.premier_texte)}`);
  const jetons = formatJetons(usage.total);
  if (jetons) morceaux.push(jetons);
  const cout = formatCout(usage.cout);
  if (cout) morceaux.push(cout);
  if (!morceaux.length) return null;
  const phases = ["contexte", "agent", "outils", "modele", "relecture", "controles"]
    .filter((cle) => durees[cle] != null)
    .map((cle) => `${cle} ${formatDuree(durees[cle])}`);
  return { texte: morceaux.join(" · "), titre: phases.length ? `Durées : ${phases.join(", ")}` : "" };
}
