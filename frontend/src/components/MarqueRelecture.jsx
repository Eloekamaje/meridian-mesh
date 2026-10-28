// La réponse a été relue avant d'être affichée en entier : « relu », ou « corrigé à la relecture ».
export default function MarqueRelecture({ data }) {
  if (!data?.relu) return null;
  return data.corrige ? (
    <span className="mt-2 inline-block rounded-full border border-[#60A5FA]/40 px-2 py-0.5 font-code text-[10px] text-[#93C5FD]" data-testid="flore-corrige">corrigé à la relecture</span>
  ) : (
    <span className="mt-2 inline-block rounded-full border border-[#34D399]/40 px-2 py-0.5 font-code text-[10px] text-[#34D399]" data-testid="flore-relu">relu</span>
  );
}

