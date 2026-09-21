// Passerelles entre les messages du moteur de démonstration et les deux vues réelles de
// l'application qui les affichent : la page Nouveau travail (échanges) et la page Travail (fil).
// Un seul fil canonique (state.messages du moteur) — ces fonctions n'en font que des projections.

const preuvesDe = (m, fixtures) =>
  (m.evidenceIds || [])
    .map((pid) => {
      const p = fixtures.preuves[pid];
      return p ? { id: pid, preuveId: pid, source: p.title, detail: p.supports } : null;
    })
    .filter(Boolean);

// Message du fil d'un Travail (format `cas.conversation` lu par OngletTravail)
export function versMessageCase(m, fixtures) {
  return {
    role: m.speaker === "persona" ? "utilisateur" : "flore",
    texte: m.text,
    quand: m.quand,
    anime: !!m.anime, // publié en direct : la réponse se déroule progressivement
    ...(m.speaker === "flore" ? { comportement: "expliquer", ...(m.contenu || {}), preuves: preuvesDe(m, fixtures), trace: m.trace || null } : {}),
  };
}

// Échanges de la page Nouveau travail : une question du persona suivie de la réponse de Flore
export function versEchanges(messages, fixtures) {
  const out = [];
  messages.forEach((m) => {
    if (m.speaker === "persona") {
      out.push({ id: m.id, question: m.text, data: null });
      return;
    }
    const data = {
      reponse: m.text,
      comportement: "expliquer",
      contributions: [],
      indicateurs: null,
      ...(m.contenu || {}),
      preuves: preuvesDe(m, fixtures).map((p) => ({ preuveId: p.preuveId, source: p.source, detail: p.detail })),
    };
    const dernier = out[out.length - 1];
    if (dernier && !dernier.data) out[out.length - 1] = { ...dernier, data };
    else out.push({ id: m.id, question: null, data });
  });
  return out;
}
