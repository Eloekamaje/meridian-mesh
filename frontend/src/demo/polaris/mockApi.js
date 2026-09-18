// Adaptateur local Polaris (§4.1) : tant que le kiosque est monté, l'instance axios
// partagée est servie par les fixtures du scénario — l'application réelle (Atlas,
// Flore, Travail) fonctionne à l'identique, sans aucun appel réseau.
import { couleurDomaine } from "@/lib/domaines";

let sceneActive = null;
export const definirSceneActive = (id) => {
  sceneActive = id;
};

const ETAT_REL = { observe: "observee", a_etudier: "supposee" };
const slug = (s) =>
  s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "-");

function versJumeau(base, fixtures) {
  return {
    environnement: "production",
    statut: "actif",
    autonomie: "supervisé",
    couverture: 72,
    fraicheur: "à l'instant",
    sante: "nominal",
    proprietaire: "Démonstration Polaris",
    sources: { code: true, documentation: true },
    ...base,
    position: fixtures.positions?.[base.id] || { x: 0, y: 0 },
  };
}

// Mesh au format du backend réel, filtré par la scène courante (nœuds masqués et
// liens non listés absents — la « révélation » est une vraie mise à jour du Mesh).
function construireMesh(fixtures) {
  const sceneId = sceneActive || fixtures.sceneInitiale || null;
  const scene = sceneId ? fixtures.scenes?.[sceneId] : null;
  const marques = scene ? new Map(scene.noeuds.map((n) => [n.id, n])) : null;
  const liens = scene ? new Set(scene.liens.map((l) => l.id)) : null;

  const tous = [
    ...(fixtures.entites || []).map((e) =>
      versJumeau({ id: e.id, nom: e.label, domaine: e.domaine || "Opérations", mission: e.detail || "" }, fixtures)
    ),
    ...(fixtures.applications || []).map((a) =>
      versJumeau({ id: a.id, nom: a.nom, domaine: a.domaine, mission: a.description || "" }, fixtures)
    ),
  ];
  const jumeaux = tous.filter((j) => !marques?.get(j.id)?.masque);
  const relations = (fixtures.relations || [])
    .filter((r) => !liens || liens.has(r.id))
    .map((r) => ({
      id: r.id,
      source: r.sourceId,
      cible: r.targetId,
      type: r.knowledgeStatus === "observe" ? "structurante" : "decouverte",
      active: true,
      etat: ETAT_REL[r.knowledgeStatus] || "observee",
      label: r.label,
      decouverte_quand: "aujourd'hui",
      source_decouverte: "Relevé de démonstration Polaris",
      confirmee_par: [],
      claims: [],
      observations_contraires: [],
      evolution: [],
    }));

  const parDom = {};
  jumeaux.forEach((j) => {
    (parDom[j.domaine] = parDom[j.domaine] || []).push(j);
  });
  const regions = Object.entries(parDom).map(([dom, js]) => {
    const xs = js.map((j) => j.position.x);
    const ys = js.map((j) => j.position.y);
    return {
      id: `reg-${slug(dom)}`,
      label: dom,
      x: Math.min(...xs) - 80,
      y: Math.min(...ys) - 100,
      w: Math.max(...xs) - Math.min(...xs) + 220,
      h: Math.max(...ys) - Math.min(...ys) + 280,
      couleur: couleurDomaine(dom),
      maturite: { niveau: "partiellement découvert", jumeaux: js.length, relations_emergentes: 0, zones_inconnues: 0 },
    };
  });

  return {
    jumeaux,
    relations,
    regions,
    perimetre: { espace: "Mesh global", global: true, politique: "masquage", nb_autorises: jumeaux.length, nb_restreints: 0 },
  };
}

// Le travail du scénario au format « case » réel : la page Travail authentique
// (onglets Conversation / Aperçu) le consomme sans adaptation.
function construireCase(fixtures, scenario, resultId) {
  const t = fixtures.resultats[resultId];
  const quand = new Date().toISOString();
  const conversation = [];
  (scenario.steps || []).forEach((s) =>
    (s.beats || []).forEach((b) => {
      if (b.type === "message") conversation.push({ role: b.speaker === "persona" ? "utilisateur" : "flore", texte: b.text, quand });
    })
  );
  return {
    id: t.id,
    num: 101,
    titre: t.titre,
    type: "demande",
    statut: "en_cours",
    sensibilite: "interne",
    objectif: t.objectif || "",
    resume: t.synthese || "",
    participants: [scenario.profileId],
    jumeaux: [...(fixtures.entites || []), ...(fixtures.applications || [])].map((x) => x.id).slice(0, 6),
    conversation,
    historique: [{ quand, texte: "Travail préparé par Flore — démonstration Polaris" }],
    questions: (t.aValider || []).map((texte) => ({ texte, resolue: false })),
    hypotheses: (t.hypotheses || []).map((texte) => ({ texte })),
    options: [],
    decisions: [],
    livrables: [],
    situations: [],
    prochaine_etape: (t.prochainesActions || [])[0] || null,
    a_revoir: false,
    cree_le: quand,
    maj_le: quand,
    derniere_visite: quand,
  };
}

function creerAdaptateur({ fixtures, scenario }) {
  const cas = Object.fromEntries(Object.keys(fixtures.resultats || {}).map((rid) => [rid, construireCase(fixtures, scenario, rid)]));
  const personas = [{ id: scenario.profileId, nom: scenario.roleLabel, role: scenario.title }];

  return (config) => {
    const url = (config.url || "").split("?")[0];
    const m = (config.method || "get").toLowerCase();
    const seg = url.split("/").filter(Boolean);
    const corps = () => {
      try {
        return JSON.parse(config.data || "{}");
      } catch {
        return {};
      }
    };
    const ok = (data, status = 200) =>
      new Promise((res) => setTimeout(() => res({ data, status, statusText: "OK", headers: {}, config }), 110));
    const nf = () =>
      Promise.reject({ response: { status: 404, data: { detail: `Route non simulée en démonstration : ${m.toUpperCase()} ${url}` } } });

    if (m === "get" && url === "/personas") return ok(personas);
    if (m === "get" && url === "/espaces") return ok([{ id: "mesh-global", label: "Mesh global", global: true }]);
    if (m === "get" && url === "/vues") return ok([]);
    if (m === "get" && url === "/perimetre")
      return ok({ espace: { id: "mesh-global", label: "Mesh global", global: true }, nb_autorises: 0, nb_restreints: 0 });
    if (m === "get" && url === "/mesh") return ok(construireMesh(fixtures));
    if (m === "get" && url === "/situations") return ok([]);
    if (m === "get" && url === "/activite") return ok([]);
    if (m === "get" && url === "/notifications") return ok([]);
    if (m === "get" && url === "/initiatives/compteurs") return ok({ a_traiter: 0 });
    if (m === "get" && url === "/aurora/suggestions") return ok([]);
    if (m === "get" && url === "/demo/actes") return ok([]);
    if (m === "get" && url === "/cases")
      return ok(Object.values(cas).map((c) => ({ ...c, conversation: undefined, historique: undefined, nb_messages: c.conversation.length })));
    if (m === "get" && seg[0] === "cases" && seg.length === 2) return cas[seg[1]] ? ok(cas[seg[1]]) : nf();
    if (m === "patch" && seg[0] === "cases" && seg.length === 2) {
      if (!cas[seg[1]]) return nf();
      Object.assign(cas[seg[1]], corps());
      return ok(cas[seg[1]]);
    }
    if (m === "post" && url === "/cases") return ok({ id: Object.keys(cas)[0] || "demo-polaris-work-g" }, 201);
    if (m === "post" && seg[0] === "cases" && seg.length === 3) {
      if (seg[2] === "resume") return ok({ resume: cas[seg[1]]?.resume || "" });
      return ok({ ok: true, ...corps() }, 201);
    }
    if (m === "post" && url === "/aurora/demander")
      return ok({
        reponse: "Cette démonstration suit un parcours guidé — Flore mène la séquence.",
        contributions: [],
        preuves: [],
        indicateurs: null,
        comportement: "expliquer",
      });
    if (m === "post" && url === "/journal") return ok({ ok: true });
    if (m === "post" && url === "/vues") return ok({ ok: true }, 201);
    if (m === "post" && url === "/delegations") return ok({ ok: true, tache: "Surveillance (démonstration)" }, 201);
    if (m === "post" && seg[0] === "notifications") return ok({ ok: true });
    if (m === "post" && seg[0] === "situations" && seg[2] === "action") return ok({ ok: true });
    if (m === "post" && seg[0] === "relations" && seg[2] === "confirmer") return ok({ ok: true });
    if (m === "patch" && seg[0] === "jumeaux" && seg.length === 2) return ok({ ok: true });
    console.warn(`[Polaris] route non simulée : ${m.toUpperCase()} ${url}`);
    return nf();
  };
}

// Installation avec compteur de références : robuste au double montage StrictMode.
let installe = null;

export function installerMockPolaris(api, ctx) {
  if (installe) {
    installe.refcount += 1;
    return desinstaller;
  }
  const original = api.defaults.adapter;
  const adapter = creerAdaptateur(ctx);
  api.defaults.adapter = adapter;
  installe = { adapter, original, refcount: 1 };
  return desinstaller;

  function desinstaller() {
    if (!installe) return;
    installe.refcount -= 1;
    if (installe.refcount > 0) return;
    if (api.defaults.adapter === installe.adapter) api.defaults.adapter = installe.original;
    installe = null;
    definirSceneActive(null);
  }
}
