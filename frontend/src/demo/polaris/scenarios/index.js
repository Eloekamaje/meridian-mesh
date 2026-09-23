// Registre central des parcours de démonstration Polaris : un personnage = un scénario + ses
// fixtures (voir KiosqueProvider.jsx). PROFILS liste tous les personnages, disponibles ou à venir.
import { SCENARIO_VP } from "./vp";
import { SCENARIO_DIRECTEUR } from "./directeur";

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
    titre: "Support TI",
    phrase: "Relier les alertes et orienter le diagnostic.",
    disponible: false,
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
};
