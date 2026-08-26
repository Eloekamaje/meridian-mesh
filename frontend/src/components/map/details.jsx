import { Link } from "react-router-dom";
import { couleurDomaine, ETATS_RELATION } from "@/lib/domaines";

export function RelationDetail({ rel, jumeauPar, onConfirmer }) {
  const etat = ETATS_RELATION[rel.etat] || ETATS_RELATION.confirmee;
  const s = jumeauPar(rel.source);
  const c = jumeauPar(rel.cible);
  return (
    <div data-testid="map-relation-detail">
      <span
        className="rounded border px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider"
        style={{ color: etat.couleur, borderColor: `${etat.couleur}55`, backgroundColor: `${etat.couleur}12` }}
      >
        {etat.label}
      </span>
      <h3 className="mt-2 font-display text-base font-bold text-white">
        {s?.nom || rel.source} → {c?.nom || rel.cible}
      </h3>
      {rel.confiance && <div className="mt-1 font-code text-[11px] text-white/60">confiance {rel.confiance} %</div>}

      <dl className="mt-3 space-y-1.5 text-xs">
        <div className="flex justify-between gap-2"><dt className="text-white/40">Découverte</dt><dd className="text-right text-white/80">{rel.decouverte_quand || "—"}</dd></div>
        <div className="flex justify-between gap-2"><dt className="text-white/40">Source</dt><dd className="text-right text-white/80">{rel.source_decouverte || "—"}</dd></div>
      </dl>

      {(rel.confirmee_par || []).length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-white/35">Confirmée par</div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {rel.confirmee_par.map((p, i) => (
              <span key={i} className="rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[10px] text-white/70">{p}</span>
            ))}
          </div>
        </div>
      )}

      {(rel.claims || []).length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-white/35">Claims associés</div>
          <ul className="mt-1 space-y-1">
            {rel.claims.map((cl, i) => <li key={i} className="text-xs text-white/60">→ {cl}</li>)}
          </ul>
        </div>
      )}

      {(rel.observations_contraires || []).length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#F87171]/70">Observations contraires</div>
          <ul className="mt-1 space-y-1">
            {rel.observations_contraires.map((o, i) => <li key={i} className="text-xs text-white/60">≠ {o}</li>)}
          </ul>
        </div>
      )}

      {(rel.evolution || []).length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-white/35">Évolution</div>
          <ul className="mt-1 space-y-1">
            {rel.evolution.map((ev, i) => (
              <li key={i} className="font-code text-[10px] text-white/50">{ev.quand} — <span className="text-white/80">{ev.etat}</span></li>
            ))}
          </ul>
        </div>
      )}

      {rel.etat !== "confirmee" && (
        <button
          onClick={() => onConfirmer(rel)}
          data-testid="confirmer-relation-btn"
          className="mt-4 w-full rounded-md bg-[#FBBF24] px-3 py-2 text-xs font-semibold text-black transition-colors hover:bg-[#E5A910]"
        >
          Confirmer la relation — enrichir la mémoire
        </button>
      )}
    </div>
  );
}

export function DomaineDetail({ label, stats, actions }) {
  if (!stats) return null;
  const m = stats.reg?.maturite;
  return (
    <div data-testid="domaine-detail">
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: couleurDomaine(label) }} />
        <h3 className="font-display text-base font-bold text-white">Domaine {label}</h3>
      </div>
      {m && <div className="mt-1 font-code text-[10px] text-white/45">{m.niveau} · {m.zones_inconnues} zone(s) inconnue(s)</div>}
      {actions && (
        <div className="mt-3 space-y-1.5" data-testid="domaine-actions">
          {actions.dedans ? (
            <button onClick={actions.onQuitter} data-testid="dom-quitter-btn" className="w-full rounded-md border border-white/15 px-3 py-2 text-xs text-white/70 transition-colors hover:text-white">
              Quitter le domaine
            </button>
          ) : (
            <button onClick={actions.onExplorer} data-testid="dom-explorer-btn" className="w-full rounded-md bg-[#22D3EE] px-3 py-2 text-xs font-semibold text-black transition-colors hover:bg-[#17B8D4]">
              Explorer ce domaine
            </button>
          )}
          <div className="flex flex-wrap gap-1.5">
            <button onClick={actions.onComparer} data-testid="dom-comparer-btn" className="flex-1 rounded-md border border-white/15 px-2 py-1.5 text-[11px] text-white/70 transition-colors hover:text-white">
              Comparer…
            </button>
            <button onClick={actions.onEnregistrer} data-testid="dom-enregistrer-btn" className="flex-1 rounded-md border border-white/15 px-2 py-1.5 text-[11px] text-white/70 transition-colors hover:border-[#10B981]/50 hover:text-[#10B981]">
              Enregistrer comme espace
            </button>
          </div>
          <button
            onClick={actions.onPerimetre}
            data-testid="dom-perimetre-btn"
            className={`w-full rounded-md border px-3 py-2 text-xs font-semibold transition-colors ${actions.perimetre ? "border-[#22D3EE]/60 bg-[#22D3EE]/10 text-[#22D3EE]" : "border-white/15 text-white/70 hover:border-[#22D3EE]/50 hover:text-white"}`}
          >
            {actions.perimetre ? "Retirer le périmètre de travail" : "Utiliser comme périmètre de travail"}
          </button>
        </div>
      )}
      <dl className="mt-3 space-y-2 text-xs">
        <div className="flex justify-between"><dt className="text-white/40">Jumeaux</dt><dd className="font-code text-white/85">{stats.twins.length}</dd></div>
        <div className="flex justify-between"><dt className="text-white/40">Couverture moyenne</dt><dd className="font-code text-white/85">{stats.couv} %</dd></div>
        <div className="flex justify-between"><dt className="text-white/40">Situations liées</dt><dd className="font-code text-white/85">{stats.sits.length}</dd></div>
      </dl>
      {stats.equipes.length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-white/35">Équipes responsables</div>
          <ul className="mt-1 space-y-1">
            {stats.equipes.map((e, i) => <li key={i} className="text-xs text-white/60">→ {e}</li>)}
          </ul>
        </div>
      )}
      <div className="mt-3">
        <div className="font-code text-[9px] uppercase tracking-[0.2em] text-white/35">Capacités métier</div>
        <ul className="mt-1 space-y-1">
          {stats.twins.map((j) => <li key={j.id} className="text-xs text-white/60">→ {j.nom} — {(j.mission || "").slice(0, 60)}</li>)}
        </ul>
      </div>
      {Object.keys(stats.ext).length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-white/35">Dépendances vers l'extérieur</div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {Object.entries(stats.ext).map(([dom, n]) => (
              <span key={dom} className="rounded-full border px-2 py-0.5 font-code text-[10px]" style={{ color: couleurDomaine(dom), borderColor: `${couleurDomaine(dom)}44`, backgroundColor: `${couleurDomaine(dom)}0D` }}>
                Vers {dom} · {n}
              </span>
            ))}
          </div>
        </div>
      )}
      {stats.sits.length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-white/35">Découvertes & investigations</div>
          <ul className="mt-1 space-y-1.5">
            {stats.sits.slice(0, 4).map((s) => <li key={s.id} className="text-xs leading-snug text-white/55">→ {s.titre}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}

export function ComparaisonDomaines({ a, b, statsDomaine }) {
  const sa = statsDomaine(a);
  const sb = statsDomaine(b);
  if (!sa || !sb) return null;
  const lignes = [
    ["Jumeaux", sa.twins.length, sb.twins.length],
    ["Couverture moyenne", `${sa.couv} %`, `${sb.couv} %`],
    ["Dépendances externes", Object.values(sa.ext).reduce((x, y) => x + y, 0), Object.values(sb.ext).reduce((x, y) => x + y, 0)],
    ["Situations liées", sa.sits.length, sb.sits.length],
    ["Zones inconnues", sa.reg?.maturite?.zones_inconnues ?? "—", sb.reg?.maturite?.zones_inconnues ?? "—"],
  ];
  return (
    <div data-testid="comparaison-domaines">
      <div className="font-code text-[9px] uppercase tracking-[0.2em] text-white/35">Comparaison de domaines</div>
      <div className="mt-2 grid grid-cols-3 gap-2 font-code text-[11px]">
        <div />
        <div className="font-semibold" style={{ color: couleurDomaine(a) }}>{a}</div>
        <div className="font-semibold" style={{ color: couleurDomaine(b) }}>{b}</div>
        {lignes.map(([label, va, vb]) => (
          <div key={label} className="contents">
            <div className="py-1 text-white/40">{label}</div>
            <div className="py-1 text-white/85">{va}</div>
            <div className="py-1 text-white/85">{vb}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function TwinDetail({ selected }) {
  return (
    <div data-testid="map-twin-detail">
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: couleurDomaine(selected.domaine) }} />
        <h3 className="font-display text-base font-bold text-white">{selected.nom}</h3>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-white/60">{selected.mission}</p>
      <dl className="mt-4 space-y-2 text-xs">
        <div className="flex justify-between"><dt className="text-white/40">Propriétaire</dt><dd className="text-white/80">{selected.proprietaire || "—"}</dd></div>
        <div className="flex justify-between"><dt className="text-white/40">Statut</dt><dd className="font-code text-white/80">{selected.statut}</dd></div>
        <div className="flex justify-between"><dt className="text-white/40">Autonomie</dt><dd className="font-code text-white/80">{selected.autonomie || "—"}</dd></div>
        <div className="flex justify-between"><dt className="text-white/40">Fraîcheur</dt><dd className="font-code text-white/80">{selected.fraicheur}</dd></div>
      </dl>
      <div className="mt-3">
        <div className="flex justify-between text-xs"><span className="text-white/40">Couverture</span><span className="font-code text-white/85">{selected.couverture} %</span></div>
        <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-white/[0.07]">
          <div className="h-full rounded-full" style={{ width: `${selected.couverture}%`, backgroundColor: couleurDomaine(selected.domaine) }} />
        </div>
      </div>
      {selected.sources && (
        <div className="mt-4">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-white/35">Sources</div>
          <div className="mt-1.5 flex gap-1.5">
            {Object.entries(selected.sources).map(([k, v]) => (
              <span key={k} title={k} className={`h-2 w-2 rounded-full ${v ? "bg-[#10B981]" : "bg-white/15"}`} />
            ))}
          </div>
        </div>
      )}
      <Link to="/jumeaux" className="mt-4 inline-block text-xs text-[#3B82F6] hover:underline" data-testid="map-goto-registry">
        Administrer dans Jumeaux →
      </Link>
    </div>
  );
}
