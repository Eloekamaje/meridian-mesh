// Textes de Flore hors démonstration — modifiables sans toucher aux composants.

// Création d'un travail par une conversation avec Flore (components/case/OngletTravail.jsx, envoi d'un brouillon) :
// la première question crée le travail avec les jumeaux du contexte, puis Flore répond. Un jumeau réel du contexte est
// mobilisé (ses Claims et son code). À false, « Nouveau travail » annonce seulement que la conversation arrive.
export const CREATION_TRAVAIL_ACTIVE = true;

export const FLORE_PRESENTATION =
  "Bonjour, je suis Flore. Je vous aide à comprendre votre environnement : je rapproche ce que Méridian sait de vos applications, de leurs relations et de leurs preuves, puis je vous aide à préparer le travail qui en découle.\n\n" +
  "Cette conversation est encore en construction. Elle arrive bientôt. En attendant, la démonstration vous montre comment elle fonctionnera.";

export const FLORE_REPONSE_EN_CONSTRUCTION =
  "Je ne peux pas encore traiter votre demande : cette conversation est en construction et arrive bientôt. La démonstration vous montre comment elle fonctionnera.";

// Bouton proposé sous chaque message d'annonce
export const PROPOSITION_DEMO = { label: "Découvrir la démonstration", action: "demo" };
