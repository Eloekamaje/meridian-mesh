import { motion, useReducedMotion } from "framer-motion";
import { HandPointing } from "@phosphor-icons/react";

// Invitation au geste dans la démonstration : une main index qui tapote à droite du bouton visé,
// avec une bulle. À placer dans un conteneur `relative` qui entoure le bouton.
// Purement visuel : ne capte aucun clic (le bouton dessous reste l'élément cliquable).
export default function IndicateurClic({ texte = "Commencez ici", sousTexte = "Cliquez sur « Nouveau travail »", testid = "indicateur-clic" }) {
  const reduit = useReducedMotion();
  return (
    <div className="pointer-events-none absolute left-full top-1/2 z-50 ml-3 flex -translate-y-1/2 items-center gap-2" data-testid={testid} role="note">
      {/* La main index pointe vers la gauche, sur le bouton, et tapote */}
      <motion.span
        aria-hidden="true"
        className="text-[#BFDBFE] drop-shadow-[0_2px_8px_rgba(96,165,250,0.6)]"
        style={{ rotate: -90 }}
        animate={reduit ? undefined : { x: [0, -9, 0] }}
        transition={reduit ? undefined : { duration: 1.1, repeat: Infinity, ease: "easeInOut" }}
      >
        <HandPointing size={34} weight="fill" />
      </motion.span>
      <span className="hidden whitespace-nowrap rounded-lg border sm:block border-[#60A5FA]/40 bg-[#0F1D28] px-2.5 py-1.5 shadow-lg">
        <span className="block font-code text-[9px] uppercase tracking-[0.2em] text-[#60A5FA]">{texte}</span>
        <span className="block text-[11px] leading-snug text-[#D8E2EA]">{sousTexte}</span>
      </span>
    </div>
  );
}
