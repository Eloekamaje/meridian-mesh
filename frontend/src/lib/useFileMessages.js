import { useCallback, useEffect, useRef, useState } from "react";

// Écrire pendant que Flore répond (P3, à la manière d'OpenBot — composer/queue.ts) : le message est mis en file ;
// à la fin du tour, quelle qu'elle soit (réponse, arrêt, erreur), tout ce qui attend part en UNE question.
// « Réorienter maintenant » = Arrêter : la file part aussitôt le tour arrêté.

export const mettreEnFile = (file, texte) => ((texte || "").trim() ? [...file, texte.trim()] : file);
export const retirerDeFile = (file, i) => file.filter((_, k) => k !== i);
export const regrouperFile = (file) => file.join("\n\n");

export default function useFileMessages(occupe, envoyer) {
  const [file, setFile] = useState([]);
  const envoyerRef = useRef(envoyer);
  envoyerRef.current = envoyer;
  useEffect(() => {
    if (occupe || !file.length) return;
    const texte = regrouperFile(file);
    setFile([]);
    envoyerRef.current(texte);
  }, [occupe, file]);
  const ajouter = useCallback((texte) => setFile((f) => mettreEnFile(f, texte)), []);
  const retirer = useCallback((i) => setFile((f) => retirerDeFile(f, i)), []);
  // Modifier : le message quitte la file et revient dans la zone de saisie (rend son texte)
  const reprendre = useCallback((i) => {
    const texte = file[i];
    setFile((f) => retirerDeFile(f, i));
    return texte;
  }, [file]);
  return { file, ajouter, retirer, reprendre };
}
