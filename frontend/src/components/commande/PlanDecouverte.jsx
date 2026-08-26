import { STATUTS_SOURCE } from "@/lib/sources";

export default function PlanDecouverte({ sources, catalogue }) {
  const objectifs = {};
  sources.forEach((s) => {
    const c = catalogue.contributions[s.connecteur];
    if (!c) return;
    (objectifs[c.objectif] = objectifs[c.objectif] || []).push({ source: s, contribution: c.contribution });
  });

  return (
    <div className="mx-auto max-w-3xl" data-testid="plan-decouverte">
      <h2 className="font-display text-lg font-bold text-[#111110]">Plan de découverte</h2>
      <p className="mt-1 text-sm text-[#52524F]">
        Chaque source contribue à un objectif de connaissance. Le jumeau apprendra de toutes les sources prêtes ; les autres pourront être rattrapées ensuite.
      </p>
      <div className="mt-6 space-y-4">
        {Object.entries(objectifs).map(([objectif, lignes]) => (
          <div key={objectif} className="rise rounded-xl border border-[#E5E5E3] bg-white p-4" data-testid={`objectif-${objectif}`}>
            <div className="font-code text-[10px] uppercase tracking-[0.2em] text-[#0E7490]">{objectif}</div>
            <ul className="mt-2.5 space-y-2">
              {lignes.map(({ source, contribution }) => {
                const st = STATUTS_SOURCE[source.statut] || STATUTS_SOURCE.ajoutee;
                return (
                  <li key={source.id} className="flex items-center justify-between gap-3 rounded-md border border-[#E5E5E3] px-3 py-2">
                    <div>
                      <div className="text-xs font-semibold text-[#111110]">{source.nom}</div>
                      <div className="font-code text-[9px] text-[#71716D]">{contribution}</div>
                    </div>
                    <span className="shrink-0 rounded border px-1.5 py-0.5 font-code text-[9px]" style={{ color: st.couleur, borderColor: `${st.couleur}44`, backgroundColor: `${st.couleur}12` }}>
                      {st.label}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
        {sources.length === 0 && (
          <p className="rounded-xl border border-dashed border-[#E5E5E3] py-10 text-center text-sm text-[#71716D]" data-testid="plan-vide">
            Aucune source — le plan de découverte se construira à partir de l'atelier des sources.
          </p>
        )}
      </div>
    </div>
  );
}
