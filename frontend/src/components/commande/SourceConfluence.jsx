import SourceConnexion from "@/components/commande/SourceConnexion";

const CONFLUENCE = {
  systeme: "confluence", nom: "Confluence", hote: { exemple: "banque.atlassian.net" },
  perimetre: { cle: "espace", titre: "Espace", pluriel: "espaces", lecture: "lecture des espaces", label: "Espace Confluence", placeholder: "Choisir un espace" },
};

export default function SourceConfluence(props) {
  return <SourceConnexion cfg={CONFLUENCE} {...props} />;
}
