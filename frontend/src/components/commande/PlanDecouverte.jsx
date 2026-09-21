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
      <h2 className="font-display text-lg font-bold text-[#F2F6F8]">Plan de découverte</h2>
      <p className="mt-1 text-sm text-[#94A3B8]">
        Chaque source contribue à un objectif de connaissance. Le jumeau apprendra de toutes les sources prêtes ; les autres pourront être rattrapées ensuite.
      </p>
      <div className="mt-6 space-y-4">
        {Object.entries(objectifs).map(([objectif, lignes]) => (
          <div key={objectif} className="rise rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-4" data-testid={`objectif-${objectif}`}>
            <div className="font-code text-[10px] uppercase tracking-[0.2em] text-[#60A5FA]">{objectif}</div>
            <ul className="mt-2.5 space-y-2">
              {lignes.map(({ source, contribution }) => {
                const st = STATUTS_SOURCE[source.statut] || STATUTS_SOURCE.ajoutee;
                return (
                  <li key={source.id} className="flex items-center justify-between gap-3 rounded-md border border-[rgba(148,163,184,0.16)] px-3 py-2">
                    <div>
                      <div className="text-xs font-semibold text-[#F2F6F8]">{source.nom}</div>
                      <div className="font-code text-[9px] text-[#7C93A8]">{contribution}</div>
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
          <p className="rounded-xl border border-dashed border-[rgba(148,163,184,0.16)] py-10 text-center text-sm text-[#7C93A8]" data-testid="plan-vide">
            Aucune source — le plan de découverte se construira à partir de l'atelier des sources.
          </p>
        )}
      </div>
    </div>
  );
}
