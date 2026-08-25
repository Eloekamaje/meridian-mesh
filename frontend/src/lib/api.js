import axios from "axios";

const api = axios.create({
  baseURL: `${process.env.REACT_APP_BACKEND_URL}/api`,
});

api.interceptors.request.use((config) => {
  config.headers["X-Persona"] = localStorage.getItem("meridian.persona") || "architecte";
  const cible = localStorage.getItem("meridian.perimetre") || "mesh-global";
  config.headers["X-Espace"] = cible.startsWith("vue:")
    ? localStorage.getItem("meridian.perimetre.espace") || "mesh-global"
    : cible;
  return config;
});

export default api;
