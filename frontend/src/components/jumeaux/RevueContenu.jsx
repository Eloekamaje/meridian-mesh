import { STRATE_LABELS, STATUTS_SOURCES, AUTONOMIE } from "@/lib/jumeaux";

export function Section({ titre, items }) {
  return (
    <div>
      <div className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">{titre}</div>
      <ul className="mt-1.5 space-y-1">
        {items.map((it, i) => (
          <li key={i} className="text-xs text-white/60">→ {it}</li>
        ))}
      </ul>
    </div>
  );
}

export default function RevueContenu({ examen, jumeau }) {
  return (
    <div className="space-y-4 text-sm" data-testid="revue-contenu">
      <p className="text-white/60">{examen.identite?.mission}</p>

      {jumeau?.strates && (
        <div>
          <div className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Couverture de connaissance</div>
          <div className="mt-2 grid grid-cols-2 gap-1.5 sm:grid-cols-5" data-testid="revue-strates">
            {Object.entries(STRATE_LABELS).map(([k, l]) => (
              <div key={k} className="rounded-lg border border-white/[0.08] px-2 py-2 text-center">
                <div className={`font-display text-sm font-bold ${(jumeau.strates[k] ?? 0) >= 80 ? "text-[#10B981]" : (jumeau.strates[k] ?? 0) >= 60 ? "text-[#FBBF24]" : "text-[#F87171]"}`}>{jumeau.strates[k] ?? "—"} %</div>
                <div className="mt-0.5 font-code text-[8px] uppercase text-white/40">{l}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {(jumeau?.sources_detail || []).length > 0 && (
        <div>
          <div className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Sources</div>
          <div className="mt-1.5 space-y-1" data-testid="revue-sources">
            {jumeau.sources_detail.map((s) => {
              const ss = STATUTS_SOURCES[s.statut] || [s.statut, "#9CA3AF"];
              return (
                <div key={s.cle} className="flex items-center justify-between rounded border border-white/[0.06] px-2.5 py-1.5 text-xs">
                  <span className="text-white/70">{s.nom}</span>
                  <span className="font-code text-[9px]" style={{ color: ss[1] }}>{ss[0]}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Section titre="Capacités découvertes" items={examen.capacites || []} />
        <Section titre="Comportements observés" items={examen.comportements || []} />
      </div>

      <div>
        <div className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Relations proposées · handshake A2A</div>
        <div className="mt-1.5 flex flex-wrap gap-1.5" data-testid="revue-relations">
          {(examen.relations_supposees || []).map((r, i) => (
            <span key={i} className="rounded-full border border-[#A78BFA]/40 bg-[#A78BFA]/10 px-2 py-0.5 font-code text-[10px] text-[#A78BFA]">
              {r.jumeau} · {r.confiance} %
            </span>
          ))}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Section titre="Contradictions" items={examen.contradictions?.length ? examen.contradictions : ["Aucune contradiction détectée"]} />
        <Section titre="Connaissances manquantes" items={examen.connaissances_manquantes || []} />
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-lg border border-white/[0.08] px-3 py-2"><span className="font-code text-[9px] uppercase text-white/35">Propriétaire</span><div className="mt-0.5 text-white/80">{jumeau?.proprietaire || "—"}</div></div>
        <div className="rounded-lg border border-white/[0.08] px-3 py-2"><span className="font-code text-[9px] uppercase text-white/35">Autonomie demandée</span><div className="mt-0.5 text-white/80">{AUTONOMIE[jumeau?.autonomie]?.[0] || "—"} — {AUTONOMIE[jumeau?.autonomie]?.[1]}</div></div>
      </div>
    </div>
  );
}
