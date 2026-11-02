import { CalendarBlank, CurrencyEur, Warning, Users, GitBranch } from "@phosphor-icons/react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const euros = (valeur, devise = "EUR") =>
  new Intl.NumberFormat("fr-FR", { style: "currency", currency: devise, maximumFractionDigits: 0 }).format(valeur || 0);

export function artefactDepuisOutil(outil) {
  if (!outil?.nom?.startsWith("planification_") || !outil.extrait) return null;
  try {
    const valeur = JSON.parse(outil.extrait);
    return valeur && typeof valeur === "object" && valeur.type?.startsWith("planification.")
      ? valeur : null;
  } catch {
    return null;
  }
}

function Barre({ valeur, maximum, couleur = "#60A5FA" }) {
  const largeur = maximum > 0 ? Math.min(100, Math.max(0, (valeur / maximum) * 100)) : 0;
  return (
    <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.08]">
      <div className="h-full rounded-full" style={{ width: `${largeur}%`, backgroundColor: couleur }} />
    </div>
  );
}

function Capacite({ data }) {
  const equipes = data.equipes || [];
  return (
    <div data-testid="artefact-capacite">
      <div className="mb-3 flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">
        <Users size={14} className="text-[#60A5FA]" /> Capacité & charge
      </div>
      {equipes.length === 0 && <p className="text-xs text-[#7C93A8]">Aucune équipe observée.</p>}
      <div className="space-y-3">
        {equipes.map((equipe) => (
          <div key={equipe.equipe_id} className="rounded-lg border border-white/[0.08] bg-white/[0.02] p-3">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm font-semibold text-[#F2F6F8]">{equipe.nom}</span>
              <span className="font-code text-[10px] text-[#7C93A8]">{equipe.elements_actifs} actif(s)</span>
            </div>
            <div className="mt-2 space-y-2">
              {(equipe.charges || []).map((charge) => {
                const max = Math.max(charge.capacite || 0, charge.connue || 0, 1);
                return (
                  <div key={charge.unite} className="grid grid-cols-[4.5rem_1fr_4rem] items-center gap-2">
                    <span className="font-code text-[9px] uppercase text-[#7C93A8]">{charge.unite}</span>
                    <div className="space-y-1">
                      <Barre valeur={charge.connue} maximum={max} />
                      <div className="flex justify-between font-code text-[9px] text-[#64748B]">
                        <span>charge {charge.connue}</span>
                        <span>capacité {charge.capacite ?? "?"}</span>
                      </div>
                    </div>
                    <span className={`text-right font-code text-[10px] ${charge.marge != null && charge.marge < 0 ? "text-[#F87171]" : "text-[#34D399]"}`}>
                      {charge.marge != null ? `marge ${charge.marge}` : "—"}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Prevision({ data }) {
  const p = data.prevision || data;
  const ok = p.ok !== false && p.p50;
  return (
    <div data-testid="artefact-prevision">
      <div className="mb-3 flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">
        <CalendarBlank size={14} className="text-[#60A5FA]" /> Prévision
      </div>
      {!ok ? <p className="text-xs text-[#F2B84B]">{p.raison || "Prévision indisponible : historique insuffisant."}</p> : (
        <>
          <div className="grid grid-cols-3 gap-2">
            {[["P50", p.p50], ["P85", p.p85], ["P95", p.p95]].map(([label, valeur]) => (
              <div key={label} className="rounded-md border border-white/[0.08] bg-white/[0.03] px-2 py-2 text-center">
                <div className="font-code text-[9px] text-[#7C93A8]">{label}</div>
                <div className="mt-1 text-xs font-semibold text-[#F2F6F8]">{valeur}</div>
              </div>
            ))}
          </div>
          <div className="mt-2 font-code text-[10px] text-[#64748B]">
            {p.methode} · confiance {Math.round((p.confiance || 0) * 100)} %
          </div>
          {(p.hypotheses || []).length > 0 && (
            <ul className="mt-2 list-disc space-y-0.5 pl-4 text-[11px] text-[#94A3B8]">
              {p.hypotheses.slice(0, 3).map((h) => <li key={h}>{h}</li>)}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

function Budget({ data }) {
  return (
    <div data-testid="artefact-budget">
      <div className="mb-3 flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">
        <CurrencyEur size={14} className="text-[#34D399]" /> Budget & valeur
      </div>
      <div className="space-y-2">
        {(data.budgets || []).slice(0, 5).map((b) => {
          const max = Math.max(b.enveloppe || 0, b.forecast || 0, 1);
          return (
            <div key={b.id} className="rounded-md border border-white/[0.08] bg-white/[0.03] p-2.5">
              <div className="flex justify-between gap-2 text-xs">
                <span className="text-[#DCE6EE]">{b.libelle}</span>
                <span className="font-code text-[#94A3B8]">{euros(b.enveloppe, b.devise)}</span>
              </div>
              <div className="mt-2"><Barre valeur={b.forecast} maximum={max} couleur={(b.variance || 0) < 0 ? "#F87171" : "#34D399"} /></div>
              <div className="mt-1 flex justify-between font-code text-[9px] text-[#64748B]">
                <span>forecast {euros(b.forecast, b.devise)}</span>
                <span className={(b.variance || 0) < 0 ? "text-[#F87171]" : "text-[#34D399]"}>variance {euros(b.variance, b.devise)}</span>
              </div>
            </div>
          );
        })}
        {(data.budgets || []).length === 0 && <p className="text-xs text-[#7C93A8]">Aucun budget observé.</p>}
      </div>
    </div>
  );
}

function Alertes({ data }) {
  return (
    <div data-testid="artefact-alertes">
      <div className="mb-3 flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">
        <Warning size={14} className="text-[#F2B84B]" /> Alertes
      </div>
      <ul className="space-y-1.5">
        {(data.alertes || []).slice(0, 6).map((a, i) => (
          <li key={`${a.type}-${i}`} className="rounded-md border border-white/[0.08] bg-white/[0.03] px-2.5 py-2 text-[11px] text-[#94A3B8]">
            <span className="font-code text-[9px] uppercase text-[#F2B84B]">{a.type}</span>
            <div>{a.message}</div>
          </li>
        ))}
        {(data.alertes || []).length === 0 && <li className="text-xs text-[#7C93A8]">Aucune alerte.</li>}
      </ul>
    </div>
  );
}

function Serie({ data }) {
  const lignes = data.donnees || data.series || [];
  return (
    <div data-testid="artefact-serie">
      <div className="mb-3 flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">
        <CalendarBlank size={14} className="text-[#60A5FA]" /> Série temporelle
      </div>
      {lignes.length === 0 ? <p className="text-xs text-[#7C93A8]">Aucune série observée.</p> : (
        <div className="h-48 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={lignes}>
              <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
              <XAxis dataKey="periode" tick={{ fill: "#7C93A8", fontSize: 10 }} />
              <YAxis tick={{ fill: "#7C93A8", fontSize: 10 }} width={32} />
              <Tooltip contentStyle={{ background: "#0F1D28", border: "1px solid rgba(255,255,255,0.12)", fontSize: 11 }} />
              <Bar dataKey="valeur" name="Réalisé" fill="#60A5FA" radius={[3, 3, 0, 0]} />
              {lignes.some((l) => l.capacite != null) && <Bar dataKey="capacite" name="Capacité" fill="#34D399" radius={[3, 3, 0, 0]} />}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

function Gantt({ data }) {
  const lignes = data.lignes || data.rows || [];
  const dates = lignes.flatMap((l) => [new Date(l.debut), new Date(l.fin)]).filter((d) => !Number.isNaN(d.getTime()));
  const min = dates.length ? Math.min(...dates.map((d) => d.getTime())) : Date.now();
  const max = dates.length ? Math.max(...dates.map((d) => d.getTime())) : min + 1;
  const span = Math.max(1, max - min);
  return (
    <div data-testid="artefact-gantt">
      <div className="mb-3 flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">
        <CalendarBlank size={14} className="text-[#60A5FA]" /> Planning
      </div>
      {lignes.length === 0 ? <p className="text-xs text-[#7C93A8]">Aucune ligne planifiée.</p> : (
        <div className="space-y-2" role="list" aria-label="Planning">
          {lignes.map((l, i) => {
            const debut = new Date(l.debut).getTime();
            const fin = new Date(l.fin).getTime();
            const left = Number.isNaN(debut) ? 0 : ((debut - min) / span) * 100;
            const largeur = Number.isNaN(debut) || Number.isNaN(fin) ? 0 : Math.max(1, ((fin - debut) / span) * 100);
            return (
              <div key={l.id || i} role="listitem" className="grid grid-cols-[7rem_1fr] items-center gap-3">
                <span className="truncate text-[11px] text-[#DCE6EE]">{l.label || l.titre || l.nom}</span>
                <div className="relative h-4 rounded bg-white/[0.04]">
                  <div className="absolute inset-y-0 rounded bg-[#60A5FA]/70" style={{ left: `${left}%`, width: `${largeur}%` }} title={`${l.debut} → ${l.fin}`} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Dependances({ data }) {
  const noeuds = data.noeuds || [];
  const aretes = data.aretes || [];
  const parId = Object.fromEntries(noeuds.map((n) => [n.id, n]));
  const positions = {};
  noeuds.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / Math.max(1, noeuds.length) - Math.PI / 2;
    positions[n.id] = { x: 320 + Math.cos(angle) * 180, y: 180 + Math.sin(angle) * 120 };
  });
  return (
    <div data-testid="artefact-dependances">
      <div className="mb-3 flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">
        <GitBranch size={14} className="text-[#60A5FA]" /> Dépendances
      </div>
      {noeuds.length === 0 ? <p className="text-xs text-[#7C93A8]">Aucun élément à relier.</p> : (
        <svg viewBox="0 0 640 360" role="img" aria-label={data.titre || "Graphe de dépendances"} className="h-auto w-full">
          <title>{data.titre || "Graphe de dépendances"}</title>
          <desc>{`${noeuds.length} éléments, ${aretes.length} dépendances.`}</desc>
          {aretes.map((a, i) => {
            const s = positions[a.source];
            const c = positions[a.cible];
            return s && c ? <line key={i} x1={s.x} y1={s.y} x2={c.x} y2={c.y} stroke="#7C93A8" strokeWidth="1" opacity="0.65" /> : null;
          })}
          {noeuds.map((n) => {
            const p = positions[n.id];
            return (
              <g key={n.id}>
                <circle cx={p.x} cy={p.y} r="5" fill="#60A5FA" />
                <text x={p.x + 9} y={p.y + 3} fill="#DCE6EE" fontSize="10">{String(n.label || parId[n.id]?.label || n.id).slice(0, 26)}</text>
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
}

export default function ArtefactPlanification({ artefact }) {
  if (!artefact) return null;
  const contenu = artefact.type === "planification.capacite" ? <Capacite data={artefact} />
    : artefact.type === "planification.prevision" ? <Prevision data={artefact} />
    : artefact.type === "planification.budget" ? <Budget data={artefact} />
    : artefact.type === "planification.alertes" ? <Alertes data={artefact} />
    : artefact.type === "planification.dependances" ? <Dependances data={artefact} />
    : artefact.type === "planification.gantt" ? <Gantt data={artefact} />
    : artefact.type === "planification.serie" ? <Serie data={artefact} />
    : <pre className="max-h-48 overflow-auto whitespace-pre-wrap text-[11px] text-[#94A3B8]">{JSON.stringify(artefact, null, 2)}</pre>;
  return (
    <div className="rounded-xl border border-[#60A5FA]/20 bg-[#0B1721] p-3" data-testid="artefact-planification">
      {contenu}
    </div>
  );
}
