import axios from "axios";

// Sans REACT_APP_BACKEND_URL, la baseURL valait littéralement « undefined/api » et les
// appels partaient vers /undefined/api/... : on se rabat sur la même origine.
const api = axios.create({
  baseURL: `${process.env.REACT_APP_BACKEND_URL || ""}/api`,
  withCredentials: true,
});

// Le périmètre de lecture, partagé par axios et par les réponses au fil de l'eau (fetch).
export function entetesPerimetre() {
  const cible = localStorage.getItem("meridian.perimetre") || "mesh-global";
  const entetes = {
    "X-Espace": cible.startsWith("vue:") ? localStorage.getItem("meridian.perimetre.espace") || "mesh-global" : cible,
  };
  const tenant = (localStorage.getItem("meridian.tenant") || "").trim();
  if (tenant) entetes["X-Tenant"] = tenant;
  return entetes;
}

api.interceptors.request.use((config) => {
  Object.assign(config.headers, entetesPerimetre());
  return config;
});

// Un appel /api qui revient en text/html n'a pas atteint le backend : c'est la page de
// repli d'un serveur statique ou d'un proxy. Le laisser passer pour un succès ferait
// entrer du HTML dans l'état des pages (« espaces.some is not a function »). On le
// rejette comme une panne réseau — ce que chaque appelant sait déjà traiter.
api.interceptors.response.use((reponse) => {
  const type = reponse.headers?.["content-type"] || "";
  if (typeof reponse.data === "string" && type.includes("text/html")) {
    return Promise.reject(
      Object.assign(new Error("Réponse non-JSON : le backend est injoignable"), { reponseNonJson: true, config: reponse.config })
    );
  }
  return reponse;
});

function identifiantRequis(identifiant, nom = "identifiant") {
  const valeur = String(identifiant || "").trim();
  if (!valeur) throw new Error(`${nom} obligatoire`);
  return encodeURIComponent(valeur);
}

function posterTransition(chemin, corps, options) {
  const config = { timeout: 20000 };
  if (options?.idempotencyKey) {
    config.headers = { "Idempotency-Key": options.idempotencyKey };
  }
  return api.post(chemin, corps, config);
}

// Transitions de la boucle canonique. Chaque méthode renvoie la promesse axios ;
// le backend répond `{ objet, chaine }` et l'UI décide de la suite (sélection, rafraîchissement).
export const boucleApi = {
  async ouvrirInvestigation(situationId, corps, options) {
    return posterTransition(
      `/boucle/situations/${identifiantRequis(situationId, "identifiant de situation")}/investigations`,
      corps,
      options,
    );
  },
  async proposerDecision(investigationId, corps, options) {
    return posterTransition(
      `/boucle/investigations/${identifiantRequis(investigationId, "identifiant d'investigation")}/decisions`,
      corps,
      options,
    );
  },
  async trancherDecision(decisionId, corps, options) {
    return posterTransition(
      `/boucle/decisions/${identifiantRequis(decisionId, "identifiant de décision")}/trancher`,
      corps,
      options,
    );
  },
  async lancerInitiative(decisionId, corps, options) {
    return posterTransition(
      `/boucle/decisions/${identifiantRequis(decisionId, "identifiant de décision")}/initiatives`,
      corps,
      options,
    );
  },
  async mesurerOutcome(initiativeId, corps, options) {
    return posterTransition(
      `/boucle/initiatives/${identifiantRequis(initiativeId, "identifiant d'initiative")}/outcomes`,
      corps,
      options,
    );
  },
  async capitaliserLearningDepuisOutcome(outcomeId, corps, options) {
    return posterTransition(
      `/boucle/outcomes/${identifiantRequis(outcomeId, "identifiant d'outcome")}/learnings`,
      corps,
      options,
    );
  },
  async capitaliserLearningDepuisInvestigation(investigationId, corps, options) {
    return posterTransition(
      `/boucle/investigations/${identifiantRequis(investigationId, "identifiant d'investigation")}/learnings`,
      corps,
      options,
    );
  },
};

export default api;
