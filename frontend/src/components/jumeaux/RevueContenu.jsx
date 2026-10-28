import { STRATE_LABELS, STATUTS_SOURCES, AUTONOMIE } from "@/lib/jumeaux";

export function Section({ titre, items }) {
  return (
    <div>
      <div className="font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">{titre}</div>
      <ul className="mt-1.5 space-y-1">
        {items.map((it, i) => (
          <li key={i} className="text-xs text-[#94A3B8]">→ {it}</li>
        ))}
      </ul>
    </div>
  );
}

// Jumeau né du code : l'application présentée à tout employé, par niveaux (méthode comprendre-application),
// puis, pour aller plus loin, les sept questions et leurs connaissances prouvées.
const MARQUE = { ACCEPTED: ["✓ validé", "#34D399"], CONTESTED: ["contesté", "#F2B84B"] };
const ETIQUETTE = "font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]";

function Liste({ items, vide = "Rien d'établi pour l'instant" }) {
  return (
    <ul className="mt-1.5 space-y-1">
      {items.length === 0 && <li className="text-xs text-[#7C93A8]">{vide}</li>}
      {items.map((it, j) => {
        const texte = typeof it === "string" ? it : it.texte;
        const marque = MARQUE[it?.statut];
        return (
          <li key={j} className="text-[13px] text-[#CBD5E1]">
            → {texte}
            {marque && <span className="ml-1.5 font-code text-[9px]" style={{ color: marque[1] }}>{marque[0]}</span>}
          </li>
        );
      })}
    </ul>
  );
}

function Presentation({ examen }) {
  const p = examen.presentation;
  return (
    <div className="space-y-6" data-testid="revue-presentation">
      <section aria-label="En 30 secondes">
        <div className={ETIQUETTE}>En 30 secondes</div>
        {(p.phrases.length ? p.phrases : [examen.identite?.mission || "Présentation en préparation par le gardien du jumeau."])
          .map((t, i) => <p key={i} className={i === 0 ? "mt-1.5 text-base font-semibold text-[#F2F6F8]" : "mt-1 text-sm text-[#CBD5E1]"}>{t}</p>)}
        <p className="mt-2 font-code text-[11px] text-[#94A3B8]">
          Statut : {p.reperes.statut} · Responsable : {p.reperes.responsable} · Criticité : {p.reperes.criticite}
        </p>
      </section>
      {p.journee && (
        <section aria-label="Une journée avec elle">
          <div className={ETIQUETTE}>Une journée avec elle</div>
          <p className="mt-1.5 text-sm leading-relaxed text-[#CBD5E1]">{p.journee}</p>
        </section>
      )}
      <div className="grid gap-5 md:grid-cols-2">
        {p.blocs.map((b) => (
          <section key={b.cle} aria-label={b.titre} data-testid={`presentation-${b.cle}`}>
            <div className={ETIQUETTE}>{b.titre}</div>
            <Liste items={b.items} />
          </section>
        ))}
      </div>
      <section aria-label="D'où je le sais, et ce que j'ignore">
        <div className={ETIQUETTE}>D'où je le sais, et ce que j'ignore</div>
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {p.sources.map((s) => (
            <li key={s.nom} className={`rounded-full border px-2 py-0.5 text-[11px] ${s.ok ? "border-[#34D399]/50 text-[#34D399]" : "border-[rgba(148,163,184,0.3)] text-[#7C93A8]"}`}>
              {s.nom} : {s.etat}
            </li>
          ))}
        </ul>
        {p.maturite && (
          <p className="mt-2 font-code text-[11px] text-[#94A3B8]" data-testid="revue-maturite">
            Croisées par deux systèmes : {p.maturite.croisees} · Croisées et validées : {p.maturite.validees}
          </p>
        )}
        <Liste items={p.ignore} vide="Rien de signalé" />
      </section>
    </div>
  );
}

function Comprendre({ blocs }) {
  return (
    <div className="mt-3 grid gap-5 md:grid-cols-2" data-testid="revue-comprendre">
      {blocs.map((b, i) => (
        <div key={b.cle} data-testid={`comprendre-${b.cle}`}>
          <div className={ETIQUETTE}>{i + 1} · {b.titre}</div>
          <Liste items={b.items} />
        </div>
      ))}
    </div>
  );
}

const PLUS_LOIN = "group rounded-lg border border-[rgba(148,163,184,0.16)] px-4 py-3";
const RESUME_PLUS_LOIN = "cursor-pointer text-xs font-semibold text-[#60A5FA] hover:underline";

export function PlusLoin({ titre, children, testid }) {
  return (
    <details className={PLUS_LOIN} data-testid={testid}>
      <summary className={RESUME_PLUS_LOIN}>{titre}</summary>
      {children}
    </details>
  );
}

export default function RevueContenu({ examen, jumeau }) {
  if (examen.presentation) {
    const total = examen.comprendre.reduce((n, b) => n + b.items.length, 0);
    return (
      <div className="space-y-4">
        <Presentation examen={examen} />
        <PlusLoin titre={`Pour aller plus loin : ce que le jumeau a établi (${total} connaissances)`} testid="plus-loin-comprendre">
          <Comprendre blocs={examen.comprendre} />
        </PlusLoin>
      </div>
    );
  }
  return (
    <div className="space-y-4 text-sm" data-testid="revue-contenu">
      <p className="text-[#94A3B8]">{examen.identite?.mission}</p>

      {jumeau?.strates && (
        <div>
          <div className="font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">Couverture de connaissance</div>
          <div className="mt-2 grid grid-cols-2 gap-1.5 sm:grid-cols-5" data-testid="revue-strates">
            {Object.entries(STRATE_LABELS).map(([k, l]) => (
              <div key={k} className="rounded-lg border border-[rgba(148,163,184,0.16)] px-2 py-2 text-center">
                <div className={`font-display text-sm font-bold ${(jumeau.strates[k] ?? 0) >= 80 ? "text-[#34D399]" : (jumeau.strates[k] ?? 0) >= 60 ? "text-[#F2B84B]" : "text-[#F87171]"}`}>{jumeau.strates[k] ?? "—"} %</div>
                <div className="mt-0.5 font-code text-[8px] uppercase text-[#7C93A8]">{l}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {(jumeau?.sources_detail || []).length > 0 && (
        <div>
          <div className="font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">Sources</div>
          <div className="mt-1.5 space-y-1" data-testid="revue-sources">
            {jumeau.sources_detail.map((s) => {
              const ss = STATUTS_SOURCES[s.statut] || [s.statut, "#7C93A8"];
              return (
                <div key={s.cle} className="flex items-center justify-between rounded border border-[rgba(148,163,184,0.16)] px-2.5 py-1.5 text-xs">
                  <span className="text-[#D8E2EA]">{s.nom}</span>
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
        <div className="font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">Relations proposées · handshake A2A</div>
        <div className="mt-1.5 flex flex-wrap gap-1.5" data-testid="revue-relations">
          {!(examen.relations_supposees || []).length && <span className="text-xs text-[#7C93A8]">Aucune relation observée pour l'instant</span>}
          {(examen.relations_supposees || []).map((r, i) => (
            <span key={i} className="rounded-full border border-[#60A5FA]/40 bg-[#60A5FA]/10 px-2 py-0.5 font-code text-[10px] text-[#60A5FA]">
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
        <div className="rounded-lg border border-[rgba(148,163,184,0.16)] px-3 py-2"><span className="font-code text-[9px] uppercase text-[#7C93A8]">Propriétaire</span><div className="mt-0.5 text-[#D8E2EA]">{jumeau?.proprietaire || "—"}</div></div>
        <div className="rounded-lg border border-[rgba(148,163,184,0.16)] px-3 py-2"><span className="font-code text-[9px] uppercase text-[#7C93A8]">Autonomie demandée</span><div className="mt-0.5 text-[#D8E2EA]">{AUTONOMIE[jumeau?.autonomie]?.[0] || "—"} — {AUTONOMIE[jumeau?.autonomie]?.[1]}</div></div>
      </div>
    </div>
  );
}
