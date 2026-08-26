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
      <h3 className="mt-2 font-display text-base font-bold text-[#111110]">
        {s?.nom || rel.source} → {c?.nom || rel.cible}
      </h3>
      {rel.confiance && <div className="mt-1 font-code text-[11px] text-[#52524F]">confiance {rel.confiance} %</div>}

      <dl className="mt-3 space-y-1.5 text-xs">
        <div className="flex justify-between gap-2"><dt className="text-[#71716D]">Découverte</dt><dd className="text-right text-[#3F3F3C]">{rel.decouverte_quand || "—"}</dd></div>
        <div className="flex justify-between gap-2"><dt className="text-[#71716D]">Source</dt><dd className="text-right text-[#3F3F3C]">{rel.source_decouverte || "—"}</dd></div>
      </dl>

      {(rel.confirmee_par || []).length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#71716D]">Confirmée par</div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {rel.confirmee_par.map((p, i) => (
              <span key={i} className="rounded-full border border-[#E5E5E3] bg-[#F7F7F6] px-2 py-0.5 text-[10px] text-[#3F3F3C]">{p}</span>
            ))}
          </div>
        </div>
      )}

      {(rel.claims || []).length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#71716D]">Claims associés</div>
          <ul className="mt-1 space-y-1">
            {rel.claims.map((cl, i) => <li key={i} className="text-xs text-[#52524F]">→ {cl}</li>)}
          </ul>
        </div>
      )}

      {(rel.observations_contraires || []).length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#B91C1C]/70">Observations contraires</div>
          <ul className="mt-1 space-y-1">
            {rel.observations_contraires.map((o, i) => <li key={i} className="text-xs text-[#52524F]">≠ {o}</li>)}
          </ul>
        </div>
      )}

      {(rel.evolution || []).length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#71716D]">Évolution</div>
          <ul className="mt-1 space-y-1">
            {rel.evolution.map((ev, i) => (
              <li key={i} className="font-code text-[10px] text-[#52524F]">{ev.quand} — <span className="text-[#3F3F3C]">{ev.etat}</span></li>
            ))}
          </ul>
        </div>
      )}

      {rel.etat !== "confirmee" && (
        <button
          onClick={() => onConfirmer(rel)}
          data-testid="confirmer-relation-btn"
          className="mt-4 w-full rounded-md bg-[#B45309] px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-[#92400E]"
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
        <h3 className="font-display text-base font-bold text-[#111110]">Domaine {label}</h3>
      </div>
      {m && <div className="mt-1 font-code text-[10px] text-[#71716D]">{m.niveau} · {m.zones_inconnues} zone(s) inconnue(s)</div>}
      {actions && (
        <div className="mt-3 space-y-1.5" data-testid="domaine-actions">
          {actions.dedans ? (
            <button onClick={actions.onQuitter} data-testid="dom-quitter-btn" className="w-full rounded-md border border-[#E5E5E3] px-3 py-2 text-xs text-[#3F3F3C] transition-colors hover:text-[#111110]">
              Quitter le domaine
            </button>
          ) : (
            <button onClick={actions.onExplorer} data-testid="dom-explorer-btn" className="w-full rounded-md bg-[#0E7490] px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-[#0891B2]">
              Explorer ce domaine
            </button>
          )}
          <div className="flex flex-wrap gap-1.5">
            <button onClick={actions.onComparer} data-testid="dom-comparer-btn" className="flex-1 rounded-md border border-[#E5E5E3] px-2 py-1.5 text-[11px] text-[#3F3F3C] transition-colors hover:text-[#111110]">
              Comparer…
            </button>
            <button onClick={actions.onEnregistrer} data-testid="dom-enregistrer-btn" className="flex-1 rounded-md border border-[#E5E5E3] px-2 py-1.5 text-[11px] text-[#3F3F3C] transition-colors hover:border-[#047857]/50 hover:text-[#047857]">
              Enregistrer comme espace
            </button>
          </div>
          <button
            onClick={actions.onPerimetre}
            data-testid="dom-perimetre-btn"
            className={`w-full rounded-md border px-3 py-2 text-xs font-semibold transition-colors ${actions.perimetre ? "border-[#0E7490]/60 bg-[#0E7490]/10 text-[#0E7490]" : "border-[#E5E5E3] text-[#3F3F3C] hover:border-[#0E7490]/50 hover:text-[#111110]"}`}
          >
            {actions.perimetre ? "Retirer le périmètre de travail" : "Utiliser comme périmètre de travail"}
          </button>
        </div>
      )}
      <dl className="mt-3 space-y-2 text-xs">
        <div className="flex justify-between"><dt className="text-[#71716D]">Jumeaux</dt><dd className="font-code text-[#111110]">{stats.twins.length}</dd></div>
        <div className="flex justify-between"><dt className="text-[#71716D]">Couverture moyenne</dt><dd className="font-code text-[#111110]">{stats.couv} %</dd></div>
        <div className="flex justify-between"><dt className="text-[#71716D]">Situations liées</dt><dd className="font-code text-[#111110]">{stats.sits.length}</dd></div>
      </dl>
      {stats.equipes.length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#71716D]">Équipes responsables</div>
          <ul className="mt-1 space-y-1">
            {stats.equipes.map((e, i) => <li key={i} className="text-xs text-[#52524F]">→ {e}</li>)}
          </ul>
        </div>
      )}
      <div className="mt-3">
        <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#71716D]">Capacités métier</div>
        <ul className="mt-1 space-y-1">
          {stats.twins.map((j) => <li key={j.id} className="text-xs text-[#52524F]">→ {j.nom} — {(j.mission || "").slice(0, 60)}</li>)}
        </ul>
      </div>
      {Object.keys(stats.ext).length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#71716D]">Dépendances vers l'extérieur</div>
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
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#71716D]">Découvertes & investigations</div>
          <ul className="mt-1 space-y-1.5">
            {stats.sits.slice(0, 4).map((s) => <li key={s.id} className="text-xs leading-snug text-[#52524F]">→ {s.titre}</li>)}
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
      <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#71716D]">Comparaison de domaines</div>
      <div className="mt-2 grid grid-cols-3 gap-2 font-code text-[11px]">
        <div />
        <div className="font-semibold" style={{ color: couleurDomaine(a) }}>{a}</div>
        <div className="font-semibold" style={{ color: couleurDomaine(b) }}>{b}</div>
        {lignes.map(([label, va, vb]) => (
          <div key={label} className="contents">
            <div className="py-1 text-[#71716D]">{label}</div>
            <div className="py-1 text-[#111110]">{va}</div>
            <div className="py-1 text-[#111110]">{vb}</div>
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
        <h3 className="font-display text-base font-bold text-[#111110]">{selected.nom}</h3>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-[#52524F]">{selected.mission}</p>
      <dl className="mt-4 space-y-2 text-xs">
        <div className="flex justify-between"><dt className="text-[#71716D]">Propriétaire</dt><dd className="text-[#3F3F3C]">{selected.proprietaire || "—"}</dd></div>
        <div className="flex justify-between"><dt className="text-[#71716D]">Statut</dt><dd className="font-code text-[#3F3F3C]">{selected.statut}</dd></div>
        <div className="flex justify-between"><dt className="text-[#71716D]">Autonomie</dt><dd className="font-code text-[#3F3F3C]">{selected.autonomie || "—"}</dd></div>
        <div className="flex justify-between"><dt className="text-[#71716D]">Fraîcheur</dt><dd className="font-code text-[#3F3F3C]">{selected.fraicheur}</dd></div>
      </dl>
      <div className="mt-3">
        <div className="flex justify-between text-xs"><span className="text-[#71716D]">Couverture</span><span className="font-code text-[#111110]">{selected.couverture} %</span></div>
        <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-[#E5E5E3]">
          <div className="h-full rounded-full" style={{ width: `${selected.couverture}%`, backgroundColor: couleurDomaine(selected.domaine) }} />
        </div>
      </div>
      {selected.sources && (
        <div className="mt-4">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#71716D]">Sources</div>
          <div className="mt-1.5 flex gap-1.5">
            {Object.entries(selected.sources).map(([k, v]) => (
              <span key={k} title={k} className={`h-2 w-2 rounded-full ${v ? "bg-[#047857]" : "bg-[#E5E5E3]"}`} />
            ))}
          </div>
        </div>
      )}
      <Link to="/jumeaux" className="mt-4 inline-block text-xs text-[#3730A3] hover:underline" data-testid="map-goto-registry">
        Administrer dans Jumeaux →
      </Link>
    </div>
  );
}
