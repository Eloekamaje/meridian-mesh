import axios from "axios";

// Sans REACT_APP_BACKEND_URL, la baseURL valait littéralement « undefined/api » et les
// appels partaient vers /undefined/api/... : on se rabat sur la même origine.
const api = axios.create({
  baseURL: `${process.env.REACT_APP_BACKEND_URL || ""}/api`,
});

api.interceptors.request.use((config) => {
  config.headers["X-Persona"] = localStorage.getItem("meridian.persona") || "architecte";
  const cible = localStorage.getItem("meridian.perimetre") || "mesh-global";
  config.headers["X-Espace"] = cible.startsWith("vue:")
    ? localStorage.getItem("meridian.perimetre.espace") || "mesh-global"
    : cible;
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

export default api;
