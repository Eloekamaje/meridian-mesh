import { badgeOrigine } from "@/lib/origineFlore";

// D'où vient la réponse, quand ce n'est pas d'un raisonnement de Flore (plan de remédiation L0.5).
export default function MarqueOrigine({ data }) {
  const badge = badgeOrigine(data);
  if (!badge) return null;
  return (
    <span
      className="mt-2 ml-2 inline-block rounded-full border px-2 py-0.5 font-code text-[10px]"
      style={{ borderColor: `${badge.teinte}66`, color: badge.teinte, backgroundColor: `${badge.teinte}14` }}
      data-testid={badge.testid}
    >
      {badge.texte}
    </span>
  );
}
