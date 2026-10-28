import SourceConnexion from "@/components/commande/SourceConnexion";

const DATADOG = {
  systeme: "datadog", nom: "Datadog", hote: { exemple: "api.datadoghq.eu" },
  perimetre: { cle: "service", titre: "Service", pluriel: "services", lecture: "lecture des services", label: "Service Datadog", placeholder: "Choisir un service" },
  compte: { label: "Clé d'API", type: "password", secret: "Clé d'application", invite: "Collez la clé d'application" },
};

export default function SourceDatadog(props) {
  return <SourceConnexion cfg={DATADOG} {...props} />;
}
