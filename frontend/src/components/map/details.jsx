import { Link } from "react-router-dom";
import { Star, Sparkle, ArrowSquareOut } from "@phosphor-icons/react";
import { couleurDomaine, ETATS_RELATION } from "@/lib/domaines";
import { idNumerique } from "@/lib/atlasGraph";
import { useContexte } from "@/lib/contexte";

// Teinte du score de compréhension : consolidé → teal, à renforcer → ambre, insuffisant → rouge doux
const couleurComprehension = (c) => (c >= 90 ? "#25D0C8" : c >= 60 ? "#F2B84B" : "#F87171");

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
      <h3 className="mt-2 font-display text-base font-bold text-[#F2F6F8]">
        {s?.nom || rel.source} → {c?.nom || rel.cible}
      </h3>
      {rel.confiance && <div className="mt-1 font-code text-[11px] text-[#94A3B8]">confiance {rel.confiance} %</div>}

      <dl className="mt-3 space-y-1.5 text-xs">
        <div className="flex justify-between gap-2"><dt className="text-[#7C93A8]">Découverte</dt><dd className="text-right text-[#D8E2EA]">{rel.decouverte_quand || "—"}</dd></div>
        <div className="flex justify-between gap-2"><dt className="text-[#7C93A8]">Source</dt><dd className="text-right text-[#D8E2EA]">{rel.source_decouverte || "—"}</dd></div>
      </dl>

      {(rel.confirmee_par || []).length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#7C93A8]">Confirmée par</div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {rel.confirmee_par.map((p, i) => (
              <span key={i} className="rounded-full border border-[rgba(148,163,184,0.16)] bg-[rgba(148,163,184,0.07)] px-2 py-0.5 text-[10px] text-[#D8E2EA]">{p}</span>
            ))}
          </div>
        </div>
      )}

      {(rel.claims || []).length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#7C93A8]">Claims associés</div>
          <ul className="mt-1 space-y-1">
            {rel.claims.map((cl, i) => <li key={i} className="text-xs text-[#94A3B8]">→ {cl}</li>)}
          </ul>
        </div>
      )}

      {(rel.observations_contraires || []).length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#F87171]/70">Observations contraires</div>
          <ul className="mt-1 space-y-1">
            {rel.observations_contraires.map((o, i) => <li key={i} className="text-xs text-[#94A3B8]">≠ {o}</li>)}
          </ul>
        </div>
      )}

      {(rel.evolution || []).length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#7C93A8]">Évolution</div>
          <ul className="mt-1 space-y-1">
            {rel.evolution.map((ev, i) => (
              <li key={i} className="font-code text-[10px] text-[#94A3B8]">{ev.quand} — <span className="text-[#D8E2EA]">{ev.etat}</span></li>
            ))}
          </ul>
        </div>
      )}

      {rel.etat !== "confirmee" && (
        <button
          onClick={() => onConfirmer(rel)}
          data-testid="confirmer-relation-btn"
          className="mt-4 w-full rounded-md bg-[#F2B84B] px-3 py-2 text-xs font-semibold text-[#071019] transition-colors hover:bg-[#F8CF7A]"
        >
          Confirmer la relation — enrichir la mémoire
        </button>
      )}
    </div>
  );
}

export function DomaineDetail({ label, stats, actions, onActionSituation }) {
  if (!stats) return null;
  const m = stats.reg?.maturite;
  return (
    <div data-testid="domaine-detail">
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: couleurDomaine(label) }} />
        <h3 className="font-display text-base font-bold text-[#F2F6F8]">Domaine {label}</h3>
      </div>
      {m && <div className="mt-1 font-code text-[10px] text-[#7C93A8]">{m.niveau} · {m.zones_inconnues} zone(s) inconnue(s)</div>}
      {actions && (
        <div className="mt-3 space-y-1.5" data-testid="domaine-actions">
          <button onClick={actions.onExplorer} data-testid="dom-explorer-btn" title="Déplacement animé à zoom constant" className="w-full rounded-md bg-[#25D0C8] px-3 py-2 text-xs font-semibold text-[#071019] transition-colors hover:bg-[#0891B2]">
            Explorer ce domaine
          </button>
          <button onClick={actions.onAjuster} data-testid="dom-ajuster-btn" title="Cadrer toute la membrane (fitBounds explicite)" className="w-full rounded-md border border-[#25D0C8]/40 px-3 py-2 text-xs font-semibold text-[#25D0C8] transition-colors hover:bg-[#25D0C8]/10">
            Ajuster au domaine
          </button>
          <div className="flex flex-wrap gap-1.5">
            <button onClick={actions.onComparer} data-testid="dom-comparer-btn" className="flex-1 rounded-md border border-[rgba(148,163,184,0.16)] px-2 py-1.5 text-[11px] text-[#D8E2EA] transition-colors hover:text-[#F2F6F8]">
              Comparer…
            </button>
            <button onClick={actions.onEnregistrer} data-testid="dom-enregistrer-btn" className="flex-1 rounded-md border border-[rgba(148,163,184,0.16)] px-2 py-1.5 text-[11px] text-[#D8E2EA] transition-colors hover:border-[#34D399]/50 hover:text-[#34D399]">
              Enregistrer comme espace
            </button>
          </div>
          <button
            onClick={actions.onPerimetre}
            data-testid="dom-perimetre-btn"
            className={`w-full rounded-md border px-3 py-2 text-xs font-semibold transition-colors ${actions.perimetre ? "border-[#25D0C8]/60 bg-[#25D0C8]/10 text-[#25D0C8]" : "border-[rgba(148,163,184,0.16)] text-[#D8E2EA] hover:border-[#25D0C8]/50 hover:text-[#F2F6F8]"}`}
          >
            {actions.perimetre ? "Retirer le périmètre de travail" : "Utiliser comme périmètre de travail"}
          </button>
        </div>
      )}
      <dl className="mt-3 space-y-2 text-xs">
        <div className="flex justify-between"><dt className="text-[#7C93A8]">Jumeaux</dt><dd className="font-code text-[#F2F6F8]">{stats.twins.length}</dd></div>
        <div className="flex justify-between"><dt className="text-[#7C93A8]">Couverture moyenne</dt><dd className="font-code text-[#F2F6F8]">{stats.couv} %</dd></div>
        <div className="flex justify-between"><dt className="text-[#7C93A8]">Situations liées</dt><dd className="font-code text-[#F2F6F8]">{stats.sits.length}</dd></div>
      </dl>
      {stats.equipes.length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#7C93A8]">Équipes responsables</div>
          <ul className="mt-1 space-y-1">
            {stats.equipes.map((e, i) => <li key={i} className="text-xs text-[#94A3B8]">→ {e}</li>)}
          </ul>
        </div>
      )}
      <div className="mt-3">
        <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#7C93A8]">Capacités métier</div>
        <ul className="mt-1 space-y-1">
          {stats.twins.map((j) => <li key={j.id} className="text-xs text-[#94A3B8]">→ {j.nom} — {(j.mission || "").slice(0, 60)}</li>)}
        </ul>
      </div>
      {Object.keys(stats.ext).length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#7C93A8]">Dépendances vers l'extérieur</div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {Object.entries(stats.ext).map(([dom, n]) => (
              <button
                key={dom}
                onClick={() => actions?.onExplorerVers?.(dom)}
                data-testid={`vers-${dom}`}
                title={`Explorer ${dom} (déplacement animé, zoom inchangé)`}
                className="rounded-full border px-2 py-0.5 font-code text-[10px] transition-transform hover:scale-105"
                style={{ color: couleurDomaine(dom), borderColor: `${couleurDomaine(dom)}44`, backgroundColor: `${couleurDomaine(dom)}0D` }}
              >
                Vers {dom} · {n}
              </button>
            ))}
          </div>
        </div>
      )}
      {stats.sits.length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#7C93A8]">Découvertes & investigations</div>
          <ul className="mt-1 space-y-1.5">
            {stats.sits.slice(0, 4).map((s) => <SituationCard key={s.id} s={s} onAction={onActionSituation} />)}
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
      <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#7C93A8]">Comparaison de domaines</div>
      <div className="mt-2 grid grid-cols-3 gap-2 font-code text-[11px]">
        <div />
        <div className="font-semibold" style={{ color: couleurDomaine(a) }}>{a}</div>
        <div className="font-semibold" style={{ color: couleurDomaine(b) }}>{b}</div>
        {lignes.map(([label, va, vb]) => (
          <div key={label} className="contents">
            <div className="py-1 text-[#7C93A8]">{label}</div>
            <div className="py-1 text-[#F2F6F8]">{va}</div>
            <div className="py-1 text-[#F2F6F8]">{vb}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function TwinDetail({ selected, favori, onBasculerFavori, statsTwin, onInterroger, voisins = [], relationsRecentes = [], onChoisirVoisin, onExplorerRelations, onOuvrirInvestigation }) {
  const det = selected.sources_detail || [];
  const pretes = det.filter((s) => s.statut === "prete").length;
  const comprehension = selected.couverture ?? 0;
  const statutComp = comprehension >= 90 ? "Solide" : comprehension >= 60 ? "À renforcer" : "Insuffisante";
  return (
    <div className="space-y-4" data-testid="map-twin-detail">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full" style={{ backgroundColor: couleurDomaine(selected.domaine) }} />
          <div>
            <h3 className="font-display text-base font-bold text-[#F2F6F8]">{selected.nom}</h3>
            <p className="font-code text-[10px] text-[#7C93A8]">{idNumerique(selected.id)} · {selected.domaine}{selected.environnement ? ` · ${selected.environnement}` : ""}</p>
          </div>
        </div>
        {onBasculerFavori && (
          <button
            onClick={() => onBasculerFavori(selected.id)}
            title={favori ? "Retirer des favoris" : "Ajouter des favoris"}
            data-testid="twin-favori-btn"
            className={`shrink-0 transition-colors ${favori ? "text-[#F2B84B]" : "text-[#41576D] hover:text-[#F2B84B]"}`}
          >
            <Star size={15} weight={favori ? "fill" : "regular"} />
          </button>
        )}
      </div>

      <Section titre="Ce qu'il fait">
        <p className="text-xs leading-relaxed text-[#94A3B8]">{selected.mission}</p>
        <dl className="mt-2 space-y-2 text-xs">
          <div className="flex justify-between"><dt className="text-[#7C93A8]">Propriétaire</dt><dd className="text-[#D8E2EA]">{selected.proprietaire || "—"}</dd></div>
          <div className="flex justify-between"><dt className="text-[#7C93A8]">Statut</dt><dd className="font-code text-[#D8E2EA]">{selected.statut}</dd></div>
          <div className="flex justify-between"><dt className="text-[#7C93A8]">Autonomie</dt><dd className="font-code text-[#D8E2EA]">{selected.autonomie || "—"}</dd></div>
          <div className="flex justify-between"><dt className="text-[#7C93A8]">Fraîcheur</dt><dd className="font-code text-[#D8E2EA]">{selected.fraicheur}</dd></div>
        </dl>
      </Section>

      <Section titre="Compréhension" action={<span className="font-code text-xs font-semibold" style={{ color: couleurComprehension(comprehension) }} data-testid="twin-comprehension">{comprehension} % · {statutComp}</span>}>
        <div className="h-1 overflow-hidden rounded-full bg-[rgba(148,163,184,0.16)]">
          <div className="h-full rounded-full transition-[width] duration-500" style={{ width: `${comprehension}%`, backgroundColor: couleurComprehension(comprehension) }} />
        </div>
        <p className="mt-1 text-[11px] leading-snug text-[#7C93A8]">
          {det.length > 0 ? `${pretes}/${det.length} sources prêtes` : "Aucune source détaillée"}{comprehension < 90 ? " — une partie des règles reste à documenter" : " — connaissance consolidée"}.
        </p>
      </Section>

      {selected.capacites?.length > 0 && (
        <Section titre="Capacités métier">
          <div className="flex flex-wrap gap-1.5" data-testid="twin-capacites">
            {selected.capacites.map((c) => (
              <span key={c} className="rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2 py-1 text-[11px] text-[#D8E2EA]">{c}</span>
            ))}
          </div>
        </Section>
      )}

      {det.length > 0 && (
        <Section titre="Sources de connaissance">
          <ul className="space-y-1" data-testid="twin-sources">
            {det.map((s) => (
              <li key={s.nom} className="flex items-center justify-between text-[11px] text-[#94A3B8]">
                <span className="flex items-center gap-1.5">
                  <span className={`h-1.5 w-1.5 rounded-full ${s.statut === "prete" ? "bg-[#25D0C8]" : "bg-[rgba(148,163,184,0.16)]"}`} />
                  {s.nom}
                </span>
                <span className="font-code text-[9px] text-[#7C93A8]">{s.statut === "prete" ? "prête" : s.statut}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {voisins.length > 0 && (
        <Section titre="Voisins">
          <ul className="space-y-0.5" data-testid="twin-voisins">
            {voisins.map((v) => (
              <li key={`${v.id}-${v.direction}`}>
                <button
                  onClick={() => onChoisirVoisin?.(v.id)}
                  data-testid={`voisin-${v.id}`}
                  className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left transition-colors hover:bg-[rgba(148,163,184,0.10)]"
                >
                  <span className="font-code text-[10px] text-[#7C93A8]">{idNumerique(v.id)}</span>
                  <span className="truncate text-xs font-semibold text-[#F2F6F8]">{v.nom}</span>
                  <span className="ml-auto shrink-0 font-code text-[9px] text-[#7C93A8]">{v.direction === "vers" ? "→" : "←"} {v.nature}</span>
                </button>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {relationsRecentes.length > 0 && (
        <Section titre="Changements récents">
          <ul className="space-y-1 text-[11px] leading-snug text-[#94A3B8]" data-testid="twin-changements">
            {relationsRecentes.map((r) => (
              <li key={r.id}>· {r.texte}</li>
            ))}
          </ul>
        </Section>
      )}

      {statsTwin && (
        <div className="grid grid-cols-3 gap-2" data-testid="twin-kpis">
          <div className="rounded-lg border border-[rgba(148,163,184,0.10)] bg-[#0F1D28] px-2 py-2 text-center">
            <div className="font-code text-sm font-bold text-[#25D0C8]" data-testid="twin-kpi-confiance">{selected.confiance?.valeur ?? selected.couverture ?? "—"} %</div>
            <div className="font-code text-[8px] uppercase tracking-wider text-[#7C93A8]">Confiance</div>
          </div>
          <div className="rounded-lg border border-[rgba(148,163,184,0.10)] bg-[#0F1D28] px-2 py-2 text-center">
            <div className="font-code text-sm font-bold text-[#F2F6F8]" data-testid="twin-kpi-flux">{statsTwin.flux}</div>
            <div className="font-code text-[8px] uppercase tracking-wider text-[#7C93A8]">Rel. observées</div>
          </div>
          <div className="rounded-lg border border-[rgba(148,163,184,0.10)] bg-[#0F1D28] px-2 py-2 text-center">
            <div className={`font-code text-sm font-bold ${statsTwin.ecarts > 0 ? "text-[#F2B84B]" : "text-[#F2F6F8]"}`} data-testid="twin-kpi-ecarts">{statsTwin.ecarts}</div>
            <div className="font-code text-[8px] uppercase tracking-wider text-[#7C93A8]">Écarts BCM</div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-1.5">
        {onInterroger && (
          <button
            onClick={onInterroger}
            data-testid="twin-interroger-btn"
            title="Ouvrir Flore avec ce jumeau en contexte"
            className="flex items-center justify-center gap-1.5 rounded-lg bg-[#25D0C8] px-3 py-2 text-xs font-semibold text-[#071019] transition-colors hover:bg-[#1BAE9F]"
          >
            <Sparkle size={13} weight="fill" /> Parler au jumeau
          </button>
        )}
        {onExplorerRelations && (
          <button
            onClick={onExplorerRelations}
            data-testid="twin-relations-btn"
            className="flex items-center justify-center gap-1 rounded-lg border border-[rgba(148,163,184,0.16)] px-3 py-2 text-xs font-semibold text-[#D8E2EA] transition-colors hover:bg-[rgba(148,163,184,0.10)]"
          >
            Explorer les dépendances
          </button>
        )}
        {onOuvrirInvestigation && (
          <button
            onClick={onOuvrirInvestigation}
            data-testid="twin-investigation-btn"
            className="flex items-center justify-center gap-1 rounded-lg border border-[rgba(148,163,184,0.16)] px-3 py-2 text-xs font-semibold text-[#D8E2EA] transition-colors hover:bg-[rgba(148,163,184,0.10)]"
          >
            Ouvrir une investigation
          </button>
        )}
        <Link
          to={`/jumeaux/${selected.id}/revue`}
          data-testid="twin-ouvrir-fiche"
          className="flex items-center justify-center gap-1.5 rounded-lg border border-[#25D0C8]/40 px-3 py-2 text-xs font-semibold text-[#25D0C8] transition-colors hover:bg-[#25D0C8]/10"
        >
          Voir les preuves <ArrowSquareOut size={11} />
        </Link>
      </div>
    </div>
  );
}

// En-tête de section réutilisable
export function Section({ titre, children, action }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <span className="font-code text-[9px] uppercase tracking-[0.2em] text-[#7C93A8]">{titre}</span>
        {action}
      </div>
      {children}
    </div>
  );
}

// Fiche « situation candidate » : cycle Signal → Candidate → Qualification → Investigation.
// Une situation n'est jamais présentée comme un incident confirmé.
const ETAPES_SITUATION = ["Signal", "Candidate", "Qualification", "Investigation"];
const etapeSituation = (s) =>
  s.statut === "en investigation" ? 3 : ["qualifiée", "surveillée", "ignorée", "classée", "décidée"].includes(s.statut) ? 2 : 1;

export function SituationCard({ s, onAction }) {
  const { demanderAFlore } = useContexte();
  const etape = etapeSituation(s);
  return (
    <div className="rounded-lg border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-3" data-testid={`situation-card-${s.id}`}>
      <div className="flex items-start gap-2">
        <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: s.nature === "incident" ? "#F2B84B" : "#9B87F5" }} />
        <div className="min-w-0">
          <div className="text-xs font-semibold text-[#F2F6F8]">{s.titre}</div>
          <div className="mt-0.5 font-code text-[9px] text-[#7C93A8]">
            {s.nature === "incident" ? "Origine : traces applicatives" : "Découverte du Mesh"} · confiance {s.score} % · {s.detectee}
          </div>
        </div>
      </div>
      <div className="mt-2 flex items-center gap-1" data-testid={`situation-cycle-${s.id}`}>
        {ETAPES_SITUATION.map((e, i) => (
          <span key={e} className="flex items-center gap-1">
            <span className={`rounded px-1.5 py-0.5 font-code text-[8px] uppercase tracking-wider ${i <= etape ? "bg-[#25D0C8]/10 font-semibold text-[#25D0C8]" : "text-[#5B7089]"}`}>{e}</span>
            {i < ETAPES_SITUATION.length - 1 && <span className="text-[9px] text-[#41576D]">→</span>}
          </span>
        ))}
      </div>
      {s.resume && <p className="mt-2 line-clamp-2 text-[11px] leading-snug text-[#94A3B8]">{s.resume}</p>}
      <div className="mt-2 flex flex-wrap gap-1.5">
        {etape < 2 && (
          <button onClick={() => onAction?.(s, "qualifier")} data-testid={`situation-qualifier-${s.id}`} className="rounded-md bg-[#9B87F5] px-2 py-1 font-code text-[10px] font-semibold text-[#071019] transition-colors hover:bg-[#B4A5F7]">
            Qualifier
          </button>
        )}
        {etape === 2 && (
          <button onClick={() => onAction?.(s, "investiguer")} data-testid={`situation-investiguer-${s.id}`} className="rounded-md bg-[#9B87F5] px-2 py-1 font-code text-[10px] font-semibold text-[#071019] transition-colors hover:bg-[#B4A5F7]">
            Ouvrir une investigation
          </button>
        )}
        <button onClick={() => demanderAFlore(`Analyse la situation « ${s.titre} » et propose une qualification.`)} data-testid={`situation-flore-${s.id}`} className="rounded-md border border-[#9B87F5]/40 px-2 py-1 font-code text-[10px] font-semibold text-[#9B87F5] transition-colors hover:bg-[#9B87F5]/10">
          Demander à Flore
        </button>
        {etape < 2 && (
          <>
            <button onClick={() => onAction?.(s, "surveiller")} data-testid={`situation-surveiller-${s.id}`} className="rounded-md border border-[rgba(148,163,184,0.16)] px-2 py-1 font-code text-[10px] text-[#94A3B8] transition-colors hover:text-[#F2F6F8]">
              Surveiller
            </button>
            <button onClick={() => onAction?.(s, "ignorer")} data-testid={`situation-ignorer-${s.id}`} className="rounded-md border border-[rgba(148,163,184,0.16)] px-2 py-1 font-code text-[10px] text-[#94A3B8] transition-colors hover:text-[#F2F6F8]">
              Ignorer
            </button>
          </>
        )}
      </div>
    </div>
  );
}

