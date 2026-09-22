import { usePerimetre } from "@/lib/perimetre";
import { usePilotage } from "@/lib/pilotage";

// Qui est connecté : la personne (son nom) et le profil qu'elle tient (rôle, périmètre). Une seule source pour la barre latérale et les salutations.
// Démonstration : l'identité est celle du rôle joué, pas celle de la personne connectée.
export function useIdentite() {
  const { personas, persona } = usePerimetre();
  const pilote = usePilotage();
  const profil = personas.find((p) => p.id === persona) || { nom: "Majella Elobo", role: "Directeur SI" };
  return pilote
    ? { nom: profil.nom, sous: profil.role, initiales: (profil.nom || "?").slice(0, 2).toUpperCase(), profil }
    : { nom: "Majella Elobo", sous: `${profil.role || "Directeur SI"} · Mesh 38`, initiales: "ME", profil };
}
