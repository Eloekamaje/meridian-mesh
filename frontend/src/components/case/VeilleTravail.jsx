import { useState } from "react";
import { CaretDown, Eye, Warning, CheckCircle, Question, CalendarCheck, TrendUp } from "@phosphor-icons/react";

// Un fait observé par un jumeau, confronté par Méridian à la note de passation de la décision.
// Distinct d'une réponse de Flore : Méridian constate et sourcé, Flore interprète quand on l'interroge.
const TYPES = {
  ecart: { icone: Warning, couleur: "#F87171", label: "Écart avec l'attendu" },
  effet_secondaire: { icone: Warning, couleur: "#F87171", label: "Risque matérialisé" },
  revue_due: { icone: CalendarCheck, couleur: "#F2B84B", label: "Revue de la décision" },
  conforme: { icone: CheckCircle, couleur: "#34D399", label: "Objectif atteint" },
  inconnue_levee: { icone: Question, couleur: "#60A5FA", label: "Inconnue levée" },
  progression: { icone: TrendUp, couleur: "#94A3B8", label: "Progression" },
  preuve_pour: { icone: TrendUp, couleur: "#34D399", label: "Indice en faveur" },
  preuve_contre: { icone: Warning, couleur: "#F2B84B", label: "Indice contraire" },
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
      {m.observe && (m.type === "preuve_pour" || m.type === "preuve_contre") && (
        <div className="mt-2 sm:max-w-[12rem]">
          <div className="rounded-lg px-2.5 py-1.5" style={{ backgroundColor: `${t.couleur}14` }}><div className="font-code text-[10px] uppercase tracking-wider text-[#7C93A8]">Confiance</div><div className="text-[13px] font-semibold" style={{ color: t.couleur }}>{m.observe}</div></div>
        </div>
      )}
      {(m.attendu || m.observe) && m.type !== "inconnue_levee" && m.type !== "revue_due" && m.type !== "preuve_pour" && m.type !== "preuve_contre" && (
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

// État de la veille et note de passation de la décision, en tête du fil. La QUESTION de revue, elle, est un message de Flore
// dans le fil (réponses rapides sous son message) — pas un bouton de ce bandeau.
export function BandeauVeille({ cas }) {
  const [ouvert, setOuvert] = useState(false);
  const v = cas.veille;
  if (!v) return null;
  if (v.mode === "maturation") return <BandeauVerification veille={v} />;
  const p = v.passation || {};
  const revueDue = p.revue_le && new Date(p.revue_le) <= new Date() && v.statut === "en_veille";
  const decision = (cas.decisions || []).slice(-1)[0];

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
          {p.reference && <div data-testid="passation-reference"><div className="mb-1 font-semibold text-[#E6EEF5]">Chantier lié</div><span className="font-code text-[#93C5FD]">{p.reference.systeme} {p.reference.ref}</span>{p.reference.titre ? ` — ${p.reference.titre}` : ""}</div>}
          {(p.hypotheses || []).length > 0 && <div><div className="mb-1 font-semibold text-[#E6EEF5]">Hypothèses de la décision</div><ul className="list-disc space-y-0.5 pl-4">{p.hypotheses.map((h) => <li key={h}>{h}</li>)}</ul></div>}
          {(p.attendus || []).length > 0 && <div><div className="mb-1 font-semibold text-[#E6EEF5]">Résultats attendus</div><ul className="space-y-0.5">{p.attendus.map((a) => <li key={a.id}>{a.indicateur} : de <b>{a.depart}</b> à <b>{a.cible}</b> {a.unite}</li>)}</ul></div>}
          {(p.risques || []).length > 0 && <div><div className="mb-1 font-semibold text-[#E6EEF5]">Risques à surveiller</div><ul className="space-y-0.5">{p.risques.map((r) => <li key={r.id}>{r.texte} (seuil {r.seuil} {r.unite})</li>)}</ul></div>}
          {(p.inconnues || []).length > 0 && <div><div className="mb-1 font-semibold text-[#E6EEF5]">Inconnues à lever</div><ul className="space-y-0.5">{p.inconnues.map((i) => <li key={i.id}>{i.texte}</li>)}</ul></div>}
        </div>
      )}
    </section>
  );
}

// Veille AVANT la décision : Flore vérifie un phénomène possible. Le bandeau dit où en est sa confiance et ce qui la fera revenir.
function BandeauVerification({ veille }) {
  const [ouvert, setOuvert] = useState(false);
  const m = veille.maturation || {};
  const confiance = veille.confiance ?? m.confiance_depart;
  const en = veille.statut === "en_veille";
  return (
    <section className="mx-auto mb-2 max-w-3xl rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28]" data-testid="bandeau-veille">
      <button type="button" onClick={() => setOuvert((o) => !o)} aria-expanded={ouvert} data-testid="veille-bascule" className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 text-left">
        <CaretDown size={12} className={`shrink-0 text-[#7C93A8] transition-transform ${ouvert ? "" : "-rotate-90"}`} />
        <span className="rounded-full bg-[#60A5FA]/15 px-2 py-0.5 font-code text-[11px] uppercase tracking-wider text-[#BFDBFE]" data-testid="veille-statut">{en ? "En vérification" : "Vérification terminée"}</span>
        <span className="min-w-0 truncate text-xs text-[#94A3B8]">{m.sujet}</span>
        {en && <span className="ml-auto font-code text-[11px] text-[#7C93A8]" data-testid="veille-confiance">Confiance {Math.round(confiance)} % · confirmer à {Math.round(m.seuil)} %</span>}
      </button>
      {ouvert && (
        <div className="space-y-2 border-t border-[rgba(148,163,184,0.10)] px-4 py-3 text-xs text-[#CBD5E1]" data-testid="note-verification">
          <div className="relative h-2 rounded-full bg-white/[0.06]" aria-hidden="true">
            <div className="absolute inset-y-0 left-0 rounded-full bg-[#60A5FA]" style={{ width: `${Math.max(2, Math.min(100, confiance))}%` }} />
            <div className="absolute -top-1 h-4 w-px bg-[#F87171]" style={{ left: `${m.plancher}%` }} title={`Écarter sous ${Math.round(m.plancher)} %`} />
            <div className="absolute -top-1 h-4 w-px bg-[#34D399]" style={{ left: `${m.seuil}%` }} title={`Confirmer à ${Math.round(m.seuil)} %`} />
          </div>
          <p>Départ {Math.round(m.confiance_depart)} % · je vous propose de confirmer à {Math.round(m.seuil)} %, d'écarter sous {Math.round(m.plancher)} %. Entre les deux, les indices s'ajoutent au fil sans vous déranger.</p>
        </div>
      )}
    </section>
  );
}

// À l'ouverture d'un travail en veille, Flore accueille la personne avant les faits : ce qui s'est passé depuis sa dernière visite,
// et le point qui demande son attention. Calculé pour cette personne (sa dernière visite), rien n'est stocké.
const pl = (n, un, plusieurs) => `${n} ${n === 1 ? un : plusieurs}`;
export function RepriseVeille({ messages, depuis }) {
  const faits = messages.filter((m) => m.role === "evenement");
  if (!faits.length) return null;
  const n = (t) => faits.filter((f) => f.type === t).length;
  if (n("preuve_pour") + n("preuve_contre") > 0) {
    // avant la décision : Flore vérifie un phénomène, les faits sont des indices
    const question = messages.some((m) => m.reponses && !m.reponse);
    return (
      <div className="space-y-2 text-[15px] leading-relaxed text-[#DCE6EE]" data-testid="reprise-veille">
        <p>
          Bon retour. Depuis votre dernière visite{depuis ? ` (${date(depuis)})` : ""}, {pl(n("preuve_pour") + n("preuve_contre"), "indice", "indices")} sur ce que je vérifie :
          {" "}{n("preuve_pour")} en faveur, {n("preuve_contre")} contraire{n("preuve_contre") > 1 ? "s" : ""}.
          {question ? " Un point demande votre décision." : " Rien ne demande votre décision pour l'instant."} Voici le détail.
        </p>
      </div>
    );
  }
  const morceaux = [
    n("conforme") && pl(n("conforme"), "objectif atteint", "objectifs atteints"),
    n("ecart") && pl(n("ecart"), "écart avec l'attendu", "écarts avec l'attendu"),
    n("effet_secondaire") && pl(n("effet_secondaire"), "risque surveillé matérialisé", "risques surveillés matérialisés"),
    n("inconnue_levee") && pl(n("inconnue_levee"), "inconnue levée", "inconnues levées"),
    (n("progression") + n("risque_maitrise")) && pl(n("progression") + n("risque_maitrise"), "mesure intermédiaire", "mesures intermédiaires"),
  ].filter(Boolean);
  const critique = faits.find((f) => f.niveau === 1);
  const revue = messages.some((m) => m.type === "revue_due");
  const quand = depuis ? ` (${date(depuis)})` : "";
  return (
    <div className="space-y-2 text-[15px] leading-relaxed text-[#DCE6EE]" data-testid="reprise-veille">
      <p>
        Bon retour. Depuis votre dernière visite{quand}, {pl(faits.length, "fait nouveau", "faits nouveaux")} sur cette décision : {morceaux.join(", ")}.
        {critique ? ` Ce qui demande votre attention : ${critique.indicateur}.` : ""}
        {revue ? " La date de revue est atteinte." : ""} Voici le détail.
      </p>
    </div>
  );
}

// « Ce que je dis repose sur N preuves » : dépliable, sous le message de Flore.
export function PreuvesMessage({ preuves }) {
  const [ouvert, setOuvert] = useState(false);
  return (
    <div data-testid="preuves-message">
      <button type="button" onClick={() => setOuvert((o) => !o)} aria-expanded={ouvert} className="flex items-center gap-1.5 font-code text-[11px] text-[#60A5FA] hover:underline">
        <Eye size={12} /> Ce que je dis repose sur {preuves.length} preuve{preuves.length > 1 ? "s" : ""} · {ouvert ? "masquer" : "afficher"}
      </button>
      {ouvert && (
        <ul className="mt-1.5 space-y-1 border-l-2 border-[#60A5FA]/25 pl-2.5">
          {preuves.map((p, k) => (
            <li key={k} className="text-[12px] leading-snug text-[#94A3B8]"><span className="font-semibold text-[#BFDBFE]">{p.source}</span> — {p.detail}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
