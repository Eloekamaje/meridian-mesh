import { useState } from "react";
import { CaretDown, Eye, Warning, CheckCircle, Question, CalendarCheck, TrendUp } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";

// Un fait observé par un jumeau, confronté par Méridian à la note de passation de la décision.
// Distinct d'une réponse de Flore : Méridian constate et sourcé, Flore interprète quand on l'interroge.
const TYPES = {
  ecart: { icone: Warning, couleur: "#F87171", label: "Écart avec l'attendu" },
  effet_secondaire: { icone: Warning, couleur: "#F87171", label: "Risque matérialisé" },
  revue_due: { icone: CalendarCheck, couleur: "#F2B84B", label: "Revue de la décision" },
  conforme: { icone: CheckCircle, couleur: "#34D399", label: "Objectif atteint" },
  inconnue_levee: { icone: Question, couleur: "#60A5FA", label: "Inconnue levée" },
  progression: { icone: TrendUp, couleur: "#94A3B8", label: "Progression" },
  risque_maitrise: { icone: CheckCircle, couleur: "#94A3B8", label: "Risque maîtrisé" },
};

// Une date de revue est un jour, pas un instant : on l'affiche en UTC pour ne pas la décaler d'un jour selon le fuseau
const date = (iso, utc = false) => new Date(iso).toLocaleDateString("fr-FR", { day: "numeric", month: "long", ...(utc ? { timeZone: "UTC" } : {}) });
const NIVEAUX = { 1: "Décision remise en question", 2: "Fait nouveau", 3: "Information" };

export function EvenementVeille({ m, index, nouveau }) {
  const t = TYPES[m.type] || TYPES.progression;
  const Icone = t.icone;
  return (
    <div
      className={`rounded-xl border bg-[#0B1522] p-3.5 ${nouveau ? "shadow-[0_0_0_1px_rgba(96,165,250,0.25)]" : ""}`}
      style={{ borderColor: `${t.couleur}40`, borderLeft: `3px solid ${t.couleur}` }}
      data-testid={`evenement-veille-${index}`}
      data-type={m.type}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 font-code text-[11px]">
        <Icone size={13} weight="fill" style={{ color: t.couleur }} />
        <span className="uppercase tracking-[0.14em]" style={{ color: t.couleur }}>{t.label}</span>
        <span className="text-[#7C93A8]">· {date(m.quand, m.type === "revue_due")}</span>
        {m.niveau === 1 && <span className="rounded bg-[#F87171]/10 px-1.5 py-0.5 text-[#F87171]">{NIVEAUX[1]}</span>}
        {nouveau && <span className="ml-auto rounded bg-[#60A5FA]/15 px-1.5 py-0.5 text-[#BFDBFE]">Nouveau</span>}
      </div>
      <p className="mt-1.5 text-sm leading-relaxed text-[#E6EEF5]">{m.texte}</p>
      {(m.attendu || m.observe) && m.type !== "inconnue_levee" && m.type !== "revue_due" && (
        <div className="mt-2 grid grid-cols-2 gap-2 sm:max-w-sm">
          <div className="rounded-lg bg-white/[0.04] px-2.5 py-1.5"><div className="font-code text-[10px] uppercase tracking-wider text-[#7C93A8]">Attendu</div><div className="text-[13px] font-semibold text-[#DCE6EE]">{m.attendu}</div></div>
          <div className="rounded-lg px-2.5 py-1.5" style={{ backgroundColor: `${t.couleur}14` }}><div className="font-code text-[10px] uppercase tracking-wider text-[#7C93A8]">Observé</div><div className="text-[13px] font-semibold" style={{ color: t.couleur }}>{m.observe}</div></div>
        </div>
      )}
      {(m.jumeau || m.source) && m.type !== "revue_due" && (
        <div className="mt-2 flex items-center gap-1.5 font-code text-[11px] text-[#7C93A8]"><Eye size={11} /> {m.jumeau ? `Observé par le jumeau ${m.jumeau}` : "Méridian"}{m.source ? ` · ${m.source}` : ""}</div>
      )}
    </div>
  );
}

// Note de passation de la décision + réponse humaine à la revue. Affichée en tête du fil tant que le travail est en veille.
export function BandeauVeille({ cas, setCas }) {
  const [ouvert, setOuvert] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  const v = cas.veille;
  if (!v) return null;
  const p = v.passation || {};
  const revueDue = p.revue_le && new Date(p.revue_le) <= new Date() && v.statut === "en_veille";
  const decision = (cas.decisions || []).slice(-1)[0];

  const agir = async (action) => {
    setEnvoi(true);
    try {
      const { data } = await api.post(`/cases/${cas.id}/veille/decision`, { action });
      setCas(data);
      toast.success(action === "rouvrir" ? "Décision rouverte" : action === "maintenir" ? "Décision maintenue — prochaine revue dans 30 jours" : "Veille terminée");
    } catch {
      toast.error("Action impossible");
    } finally {
      setEnvoi(false);
    }
  };

  const statut = v.statut === "en_veille" ? "En veille" : v.statut === "rouverte" ? "Décision rouverte" : "Veille terminée";
  return (
    <section className="mx-auto mb-2 max-w-3xl rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28]" data-testid="bandeau-veille">
      <button type="button" onClick={() => setOuvert((o) => !o)} aria-expanded={ouvert} data-testid="veille-bascule" className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 text-left">
        <CaretDown size={12} className={`shrink-0 text-[#7C93A8] transition-transform ${ouvert ? "" : "-rotate-90"}`} />
        <span className="rounded-full bg-[#60A5FA]/15 px-2 py-0.5 font-code text-[11px] uppercase tracking-wider text-[#BFDBFE]" data-testid="veille-statut">{statut}</span>
        <span className="text-xs text-[#94A3B8]">Décision suivie{decision ? ` : ${decision.texte}` : ""}</span>
        {p.revue_le && <span className={`ml-auto font-code text-[11px] ${revueDue ? "text-[#F2B84B]" : "text-[#7C93A8]"}`}>Revue {revueDue ? "due depuis le" : "le"} {date(p.revue_le, true)}</span>}
      </button>
      {ouvert && (
        <div className="space-y-3 border-t border-[rgba(148,163,184,0.10)] px-4 py-3 text-xs text-[#CBD5E1]" data-testid="note-passation">
          <div className="font-code text-[11px] uppercase tracking-[0.18em] text-[#7C93A8]">Note de passation</div>
          {(p.hypotheses || []).length > 0 && <div><div className="mb-1 font-semibold text-[#E6EEF5]">Hypothèses de la décision</div><ul className="list-disc space-y-0.5 pl-4">{p.hypotheses.map((h) => <li key={h}>{h}</li>)}</ul></div>}
          {(p.attendus || []).length > 0 && <div><div className="mb-1 font-semibold text-[#E6EEF5]">Résultats attendus</div><ul className="space-y-0.5">{p.attendus.map((a) => <li key={a.id}>{a.indicateur} : de <b>{a.depart}</b> à <b>{a.cible}</b> {a.unite}</li>)}</ul></div>}
          {(p.risques || []).length > 0 && <div><div className="mb-1 font-semibold text-[#E6EEF5]">Risques à surveiller</div><ul className="space-y-0.5">{p.risques.map((r) => <li key={r.id}>{r.texte} (seuil {r.seuil} {r.unite})</li>)}</ul></div>}
          {(p.inconnues || []).length > 0 && <div><div className="mb-1 font-semibold text-[#E6EEF5]">Inconnues à lever</div><ul className="space-y-0.5">{p.inconnues.map((i) => <li key={i.id}>{i.texte}</li>)}</ul></div>}
        </div>
      )}
      {revueDue && (
        <div className="flex flex-wrap items-center gap-2 border-t border-[rgba(148,163,184,0.10)] px-4 py-2.5" data-testid="veille-revue-actions">
          <span className="mr-auto text-xs text-[#F2B84B]">La revue est due : que faites-vous de cette décision ?</span>
          <button disabled={envoi} onClick={() => agir("rouvrir")} data-testid="veille-rouvrir" className="rounded-md bg-[#60A5FA] px-3 py-1.5 text-xs font-semibold text-[#071019] transition-colors hover:bg-[#93C5FD] disabled:opacity-50">Rouvrir la décision</button>
          <button disabled={envoi} onClick={() => agir("maintenir")} data-testid="veille-maintenir" className="rounded-md border border-[rgba(148,163,184,0.16)] px-3 py-1.5 text-xs text-[#D8E2EA] transition-colors hover:text-white disabled:opacity-50">Maintenir</button>
          <button disabled={envoi} onClick={() => agir("clore")} data-testid="veille-clore" className="rounded-md border border-[rgba(148,163,184,0.16)] px-3 py-1.5 text-xs text-[#94A3B8] transition-colors hover:text-white disabled:opacity-50">Clore</button>
        </div>
      )}
    </section>
  );
}
