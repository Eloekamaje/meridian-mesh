import SourceConnexion from "@/components/commande/SourceConnexion";

const JIRA = {
  systeme: "jira", nom: "Jira", hote: { exemple: "banque.atlassian.net" },
  perimetre: { cle: "projet", titre: "Projet", pluriel: "projets", lecture: "lecture des projets", label: "Projet Jira", placeholder: "Choisir un projet" },
};

export default function SourceJira(props) {
  return <SourceConnexion cfg={JIRA} {...props} />;
}
