import { badgeRelecture } from "@/lib/marqueRelecture";

// Ce que la relecture a réellement fait, dit sans arrondir : « relu » seulement si le texte envoyé a été relu ;
// une correction n'est jamais relue ; une panne du relecteur s'affiche « non relu » (plan de remédiation L0.1).
export default function MarqueRelecture({ data }) {
  const badge = badgeRelecture(data);
  if (!badge) return null;
  return (
    <span
      className="mt-2 inline-block rounded-full border px-2 py-0.5 font-code text-[10px]"
      style={{ borderColor: `${badge.teinte}66`, color: badge.teinte, backgroundColor: `${badge.teinte}14` }}
      data-testid={badge.testid}
    >
      {badge.texte}
    </span>
  );
}
