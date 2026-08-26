import { STRATE_LABELS, STATUTS_SOURCES, AUTONOMIE } from "@/lib/jumeaux";

export function Section({ titre, items }) {
  return (
    <div>
      <div className="font-code text-[10px] uppercase tracking-[0.2em] text-[#71716D]">{titre}</div>
      <ul className="mt-1.5 space-y-1">
        {items.map((it, i) => (
          <li key={i} className="text-xs text-[#52524F]">→ {it}</li>
        ))}
      </ul>
    </div>
  );
}

export default function RevueContenu({ examen, jumeau }) {
  return (
    <div className="space-y-4 text-sm" data-testid="revue-contenu">
      <p className="text-[#52524F]">{examen.identite?.mission}</p>

      {jumeau?.strates && (
        <div>
          <div className="font-code text-[10px] uppercase tracking-[0.2em] text-[#71716D]">Couverture de connaissance</div>
          <div className="mt-2 grid grid-cols-2 gap-1.5 sm:grid-cols-5" data-testid="revue-strates">
            {Object.entries(STRATE_LABELS).map(([k, l]) => (
              <div key={k} className="rounded-lg border border-[#E5E5E3] px-2 py-2 text-center">
                <div className={`font-display text-sm font-bold ${(jumeau.strates[k] ?? 0) >= 80 ? "text-[#047857]" : (jumeau.strates[k] ?? 0) >= 60 ? "text-[#B45309]" : "text-[#B91C1C]"}`}>{jumeau.strates[k] ?? "—"} %</div>
                <div className="mt-0.5 font-code text-[8px] uppercase text-[#71716D]">{l}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {(jumeau?.sources_detail || []).length > 0 && (
        <div>
          <div className="font-code text-[10px] uppercase tracking-[0.2em] text-[#71716D]">Sources</div>
          <div className="mt-1.5 space-y-1" data-testid="revue-sources">
            {jumeau.sources_detail.map((s) => {
              const ss = STATUTS_SOURCES[s.statut] || [s.statut, "#71716D"];
              return (
                <div key={s.cle} className="flex items-center justify-between rounded border border-[#E5E5E3] px-2.5 py-1.5 text-xs">
                  <span className="text-[#3F3F3C]">{s.nom}</span>
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
        <div className="font-code text-[10px] uppercase tracking-[0.2em] text-[#71716D]">Relations proposées · handshake A2A</div>
        <div className="mt-1.5 flex flex-wrap gap-1.5" data-testid="revue-relations">
          {(examen.relations_supposees || []).map((r, i) => (
            <span key={i} className="rounded-full border border-[#6D28D9]/40 bg-[#6D28D9]/10 px-2 py-0.5 font-code text-[10px] text-[#6D28D9]">
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
        <div className="rounded-lg border border-[#E5E5E3] px-3 py-2"><span className="font-code text-[9px] uppercase text-[#71716D]">Propriétaire</span><div className="mt-0.5 text-[#3F3F3C]">{jumeau?.proprietaire || "—"}</div></div>
        <div className="rounded-lg border border-[#E5E5E3] px-3 py-2"><span className="font-code text-[9px] uppercase text-[#71716D]">Autonomie demandée</span><div className="mt-0.5 text-[#3F3F3C]">{AUTONOMIE[jumeau?.autonomie]?.[0] || "—"} — {AUTONOMIE[jumeau?.autonomie]?.[1]}</div></div>
      </div>
    </div>
  );
}
