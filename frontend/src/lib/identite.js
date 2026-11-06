import { usePerimetre } from "@/lib/perimetre";

// Qui est connecté : la personne (son nom) et le profil qu'elle tient (rôle, périmètre). Une seule source pour la barre latérale et les salutations.
export function useIdentite() {
  const { authMode, utilisateur, poste } = usePerimetre();
  const profil = { nom: "Majella Elobo", role: "Directeur SI" };
  if (authMode !== "demo" && utilisateur) {
    return {
      nom: utilisateur,
      sous: poste || "Utilisateur",
      initiales: utilisateur.slice(0, 2).toUpperCase(),
      profil: { ...profil, role: poste || "Utilisateur" },
    };
  }
  return { nom: "Majella Elobo", sous: `${profil.role || "Directeur SI"} · Mesh 38`, initiales: "ME", profil };
}
