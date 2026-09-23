// Registre central des parcours de démonstration Polaris : un personnage = un scénario + ses
// fixtures (voir KiosqueProvider.jsx). PROFILS liste tous les personnages, disponibles ou à venir.
import { SCENARIO_VP } from "./vp";
import { SCENARIO_DIRECTEUR } from "./directeur";
import { SCENARIO_ANALYSTE } from "./analyste";
import { SCENARIO_SUPPORTTI } from "./supportti";

export const PROFILS = [
  {
    id: "vp",
    titre: "VP Transformation",
    phrase: "Décider quelles initiatives financer, lesquelles arrêter.",
    disponible: true,
  },
  {
    id: "directeur",
    titre: "Directeur Polaris",
    phrase: "Piloter le décommissionnement du parc applicatif.",
    disponible: true,
  },
  {
    id: "analyste",
    titre: "Analyste d'affaires",
    phrase: "Comprendre une application avant de la remplacer.",
    disponible: true,
  },
  {
    id: "ligne-affaires",
    titre: "Ligne d'affaires",
    phrase: "Réduire le délai d'émission d'une traite en succursale.",
    disponible: false,
  },
  {
    id: "architecte",
    titre: "Architecte",
    phrase: "Décommissionner ou réécrire MD2 : comprendre les impacts.",
    disponible: false,
  },
  {
    id: "support-ti",
    titre: "Analyste support TI",
    phrase: "Anticiper une dégradation avant les premiers impacts utilisateurs.",
    disponible: true,
  },
  {
    id: "developpeur",
    titre: "Développeur",
    phrase: "Comprendre un changement et les usages à préserver.",
    disponible: false,
  },
];

export const SCENARIOS = {
  vp: SCENARIO_VP,
  directeur: SCENARIO_DIRECTEUR,
  analyste: SCENARIO_ANALYSTE,
  "support-ti": SCENARIO_SUPPORTTI,
};
