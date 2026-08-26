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
      <h2 className="font-display text-lg font-bold text-white">Plan de découverte</h2>
      <p className="mt-1 text-sm text-white/50">
        Chaque source contribue à un objectif de connaissance. Le jumeau apprendra de toutes les sources prêtes ; les autres pourront être rattrapées ensuite.
      </p>
      <div className="mt-6 space-y-4">
        {Object.entries(objectifs).map(([objectif, lignes]) => (
          <div key={objectif} className="rise rounded-xl border border-white/[0.08] bg-white/[0.02] p-4" data-testid={`objectif-${objectif}`}>
            <div className="font-code text-[10px] uppercase tracking-[0.2em] text-[#22D3EE]">{objectif}</div>
            <ul className="mt-2.5 space-y-2">
              {lignes.map(({ source, contribution }) => {
                const st = STATUTS_SOURCE[source.statut] || STATUTS_SOURCE.ajoutee;
                return (
                  <li key={source.id} className="flex items-center justify-between gap-3 rounded-md border border-white/[0.06] px-3 py-2">
                    <div>
                      <div className="text-xs font-semibold text-white">{source.nom}</div>
                      <div className="font-code text-[9px] text-white/40">{contribution}</div>
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
          <p className="rounded-xl border border-dashed border-white/[0.1] py-10 text-center text-sm text-white/35" data-testid="plan-vide">
            Aucune source — le plan de découverte se construira à partir de l'atelier des sources.
          </p>
        )}
      </div>
    </div>
  );
}
