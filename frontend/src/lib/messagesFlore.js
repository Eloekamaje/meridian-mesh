// Textes de Flore hors démonstration — modifiables sans toucher aux composants.

// La création d'un travail par une conversation avec Flore n'est pas encore développée dans
// le produit. Tant que ce drapeau est faux, « Nouveau travail » ouvre une conversation qui
// l'annonce (aucun appel réseau, aucun travail créé). Le code de création réel reste en place
// dans pages/Accueil.jsx : il redevient actif en passant ce drapeau à true.
export const CREATION_TRAVAIL_ACTIVE = false;

export const FLORE_PRESENTATION =
  "Bonjour, je suis Flore. Je vous aide à comprendre votre environnement : je rapproche ce que Méridian sait de vos applications, de leurs relations et de leurs preuves, puis je vous aide à préparer le travail qui en découle.\n\n" +
  "Cette conversation est encore en construction. Elle arrive bientôt. En attendant, la démonstration vous montre comment elle fonctionnera.";

export const FLORE_REPONSE_EN_CONSTRUCTION =
  "Je ne peux pas encore traiter votre demande : cette conversation est en construction et arrive bientôt. La démonstration vous montre comment elle fonctionnera.";

// Bouton proposé sous chaque message d'annonce
export const PROPOSITION_DEMO = { label: "Découvrir la démonstration", action: "demo" };
