// Adaptateur local Polaris (§4.1) : tant que le kiosque est monté, l'instance axios
// partagée est servie par les fixtures du scénario — l'application réelle (Atlas,
// Flore, Travail) fonctionne à l'identique, sans aucun appel réseau.
import { MONDE_JUMEAUX, MONDE_RELATIONS, MONDE_REGIONS } from "./data/mondeComplet";
import { versMessageCase } from "./messages";

let sceneActive = null;
export const definirSceneActive = (id) => {
  sceneActive = id;
};

const ETAT_REL = { observe: "observee", a_etudier: "supposee" };

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

// Mesh au format du backend réel : le MONDE PRODUIT COMPLET (instantané, 7 domaines)
// sert de toile de fond — le récit se joue dans le même Atlas que /atlas. Le monde
// connu est entier à l'ouverture ; seule la capacité à découvrir et ses relations
// sont retenues jusqu'au climax — la « révélation » est une vraie mise à jour du Mesh.
// Une scène peut masquer des nœuds du récit pour focaliser, mais ne retire jamais le connu.
function construireMesh(fixtures) {
  const sceneId = sceneActive || fixtures.sceneInitiale || null;
  const scene = sceneId ? fixtures.scenes?.[sceneId] : null;
  const marques = scene ? new Map(scene.noeuds.map((n) => [n.id, n])) : null;
  const revelation = fixtures.revelation || { noeuds: [], liens: [] };
  const revele = scene?.revele === true;

  const recit = [
    ...(fixtures.entites || []).map((e) =>
      versJumeau({ id: e.id, nom: e.label, domaine: e.domaine || "Opérations", mission: e.detail || "" }, fixtures)
    ),
    ...(fixtures.applications || []).map((a) =>
      versJumeau({ id: a.id, nom: a.nom, domaine: a.domaine, mission: a.description || "" }, fixtures)
    ),
  ];
  const jumeaux = [
    ...MONDE_JUMEAUX.map((j) => ({ ...j })),
    ...recit.filter((j) => (revelation.noeuds.includes(j.id) ? revele : !marques?.get(j.id)?.masque)),
  ];
  const relations = [
    ...MONDE_RELATIONS.map((r) => ({ ...r })),
    ...(fixtures.relations || [])
      .filter((r) => (revelation.liens.includes(r.id) ? revele : true))
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
      })),
  ];

  return {
    jumeaux,
    relations,
    regions: MONDE_REGIONS.map((r) => ({ ...r })),
    perimetre: { espace: "Mesh global", global: true, politique: "masquage", nb_autorises: jumeaux.length, nb_restreints: 0 },
  };
}

// Magasin de travaux de la session : VIDE à l'entrée dans la démonstration. Le travail
// naît pendant la conversation, s'enrichit à chaque séquence, puis se fige à la fin.
// Il ne vit qu'en mémoire (jamais de localStorage ni de backend) et disparaît à la sortie.
let cas = {};
const signatures = {};

// Contenu du travail selon sa phase. Il grandit avec la conversation, jamais avant :
//   naissance     — la demande seule
//   diagnostic    — Flore a consulté les jumeaux : questions ouvertes, premier résumé
//   enrichissement — capacité existante constatée : synthèse et hypothèse à valider
//   final         — dossier livré : titre du livrable, options comparées, prochaine étape
// `fige` : parcours terminé, lecture seule.
const RANG_PHASE = { naissance: 0, diagnostic: 1, enrichissement: 2, final: 3 };

function construireCase(fixtures, scenario, resultId, phase, messages, fige, precedent) {
  const t = fixtures.resultats[resultId];
  const quand = new Date().toISOString();
  const rang = RANG_PHASE[phase] ?? 0;
  const conversation = messages.map((m) => versMessageCase(m, fixtures));
  // Seules les APPLICATIONS sont des jumeaux (les initiatives et étapes n'en sont pas),
  // et ils ne sont « mobilisés » qu'une fois consultés par Flore
  const applications = rang >= 1 ? fixtures.applications || [] : [];
  return {
    id: t.id,
    num: 101,
    titre: rang >= 3 ? t.titre : t.titreNaissance || t.titre,
    type: "demande",
    statut: "en_cours",
    demo_phase: fige ? "fige" : "en_construction",
    sensibilite: "interne",
    objectif: rang >= 1 ? t.objectif || "" : t.objectifNaissance || "",
    resume: rang >= 2 ? t.synthese || "" : rang >= 1 ? t.resumeDiagnostic || "" : "",
    participants: [scenario.profileId],
    jumeaux: applications.map((a) => a.id),
    conversation,
    jumeaux_participants: applications.map((a) => ({
      id: a.id,
      app_id: String(a.id).replace("demo-polaris-", ""),
      nom: a.nom,
      domaine: a.domaine || "SI",
      domaineCouleur: "#38BDF8",
      statut: "actif",
      participation: a.description || "Participe à la mission.",
    })),
    historique: [{ quand: precedent?.cree_le || quand, texte: "Travail né de la conversation avec Flore — démonstration Polaris" }],
    questions: rang >= 1 ? (t.aValider || []).map((texte) => ({ texte, resolue: false })) : [],
    hypotheses: rang >= 2 ? (t.hypotheses || []).map((texte, i) => ({ id: `demo-polaris-hyp-${i}`, texte, statut: "a_valider" })) : [],
    options: rang >= 3 ? (t.options || []).map((o) => ({ ...o })) : [],
    decisions: [], // aucune décision : l'arbitrage est soumis au comité
    livrables: [],
    situations: [],
    prochaine_etape: rang >= 3 ? (t.prochainesActions || [])[0] || null : null,
    a_revoir: false,
    cree_le: precedent?.cree_le || quand,
    maj_le: quand,
    // Première visite : ni « session précédente » ni marqueur de nouveauté dans le fil
    derniere_visite: null,
  };
}

// Aligne le magasin sur l'état du moteur (idempotent : même état → aucune écriture).
// Retourne true si le magasin a changé, pour recharger les Récentes.
export function synchroniserTravauxDemo({ fixtures, scenario, resultats, messages, fige }) {
  let change = false;
  Object.keys(cas).forEach((id) => {
    if (!resultats[id]) {
      delete cas[id];
      delete signatures[id];
      change = true;
    }
  });
  Object.entries(resultats).forEach(([id, r]) => {
    const signature = `${r.phase}|${fige}|${messages.length}`;
    if (signatures[id] === signature) return;
    signatures[id] = signature;
    cas[id] = construireCase(fixtures, scenario, id, r.phase, messages, fige, cas[id]);
    change = true;
  });
  return change;
}

// Lecture synchrone : la page Travail s'ouvre sur un travail déjà là, sans écran de chargement
export const lireTravailDemo = (id) => cas[id] || null;

export function reinitialiserTravauxDemo() {
  cas = {};
  Object.keys(signatures).forEach((k) => delete signatures[k]);
}

function creerAdaptateur({ fixtures, scenario }) {
  const personas = [{ id: scenario.profileId, nom: scenario.roleLabel, role: "Directeur · Polaris" }];

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
    // La création passe par le scénario (synchroniserTravauxDemo), jamais par un appel du visiteur
    if (m === "post" && url === "/cases") return nf();
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
  reinitialiserTravauxDemo();
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
    reinitialiserTravauxDemo();
  }
}
