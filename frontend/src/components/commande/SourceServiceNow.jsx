import SourceConnexion from "@/components/commande/SourceConnexion";

const SERVICENOW = {
  systeme: "servicenow", nom: "ServiceNow", hote: { exemple: "banque.service-now.com" },
  compte: { label: "Utilisateur du compte de service (lecture seule)", type: "text", secret: "Mot de passe", invite: "Collez le mot de passe" },
  perimetre: { cle: "ci", titre: "Élément de configuration", pluriel: "éléments de configuration", lecture: "lecture des incidents, problèmes et changements", label: "CI applicatif", placeholder: "Choisir un CI" },
};

export default function SourceServiceNow(props) {
  return <SourceConnexion cfg={SERVICENOW} {...props} />;
}
