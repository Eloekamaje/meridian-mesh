import { useEffect, useState } from "react";
import { Database, CheckCircle, Clock, Users, Scroll, ArrowCounterClockwise } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { usePerimetre } from "@/lib/perimetre";
import { couleurDomaine } from "@/lib/domaines";

const SOURCES = [
  ["code", "Code"],
  ["bdd", "Base de données"],
  ["observabilite", "Observabilité"],
  ["incidents", "Incidents"],
  ["documentation", "Documentation"],
];

export default function Administration() {
  const [jumeaux, setJumeaux] = useState([]);
  const [journal, setJournal] = useState([]);
  const [confirmReset, setConfirmReset] = useState(false);
  const [resetEnCours, setResetEnCours] = useState(false);
  const { version } = usePerimetre();
  useEffect(() => {
    api.get("/jumeaux").then((r) => setJumeaux(r.data)).catch(() => {});
    api.get("/journal").then((r) => setJournal(r.data)).catch(() => {});
  }, [version]);

  const reinitialiser = async () => {
    if (!confirmReset) {
      setConfirmReset(true);
      setTimeout(() => setConfirmReset(false), 4000);
      return;
    }
    setResetEnCours(true);
    try {
      await api.post("/demo/reinitialiser");
      toast.success("Données de démonstration réinitialisées — rechargement…");
      setTimeout(() => window.location.reload(), 800);
    } catch {
      toast.error("Réinitialisation impossible");
      setResetEnCours(false);
      setConfirmReset(false);
    }
  };

  const couvertureMoy = jumeaux.length ? Math.round(jumeaux.reduce((a, j) => a + (j.couverture || 0), 0) / jumeaux.length) : 0;
  const parStatut = jumeaux.reduce((acc, j) => ({ ...acc, [j.statut]: (acc[j.statut] || 0) + 1 }), {});
  const proprios = jumeaux.reduce((acc, j) => {
    (acc[j.proprietaire] = acc[j.proprietaire] || []).push(j.nom);
    return acc;
  }, {});

  return (
    <div className="h-full overflow-y-auto px-8 py-8 pb-44" data-testid="administration-page">
      <header className="rise">
        <div className="font-code text-[10px] uppercase tracking-[0.3em] text-[#9B87F5]">Administration</div>
        <h1 className="mt-1 font-display text-3xl font-black tracking-tight text-[#F2F6F8]">Administration</h1>
        <p className="mt-2 text-base text-[#94A3B8]">Sources, propriétaires, couverture et fraîcheur de la connaissance du Mesh.</p>
      </header>

      <div className="mt-8 grid grid-cols-12 gap-6">
        <section className="rise col-span-12 rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-5 lg:col-span-5" style={{ animationDelay: "60ms" }} data-testid="admin-couverture">
          <h2 className="flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.25em] text-[#7C93A8]">
            <CheckCircle size={14} className="text-[#25D0C8]" /> Couverture de connaissance
          </h2>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-display text-4xl font-black text-[#F2F6F8]" data-testid="couverture-moyenne">{couvertureMoy} %</span>
            <span className="font-code text-[10px] text-[#7C93A8]">moyenne du Mesh</span>
          </div>
          <ul className="mt-4 space-y-2.5">
            {[...jumeaux].sort((a, b) => a.couverture - b.couverture).map((j) => (
              <li key={j.id} className="flex items-center gap-3">
                <span className="w-28 truncate text-xs text-[#94A3B8]">{j.nom}</span>
                <div className="h-1 flex-1 overflow-hidden rounded-full bg-[rgba(148,163,184,0.16)]">
                  <div className="h-full rounded-full" style={{ width: `${j.couverture}%`, backgroundColor: couleurDomaine(j.domaine) }} />
                </div>
                <span className="w-10 text-right font-code text-[10px] text-[#94A3B8]">{j.couverture} %</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="rise col-span-12 rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-5 lg:col-span-7" style={{ animationDelay: "120ms" }} data-testid="admin-sources">
          <h2 className="flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.25em] text-[#7C93A8]">
            <Database size={14} className="text-[#9B87F5]" /> Sources connectées
          </h2>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">
                  <th className="pb-2 text-left font-medium">Jumeau</th>
                  {SOURCES.map(([k, label]) => <th key={k} className="pb-2 text-center font-medium">{label}</th>)}
                </tr>
              </thead>
              <tbody>
                {jumeaux.map((j) => (
                  <tr key={j.id} className="border-t border-[rgba(148,163,184,0.16)]" data-testid={`admin-source-${j.id}`}>
                    <td className="py-2 pr-3 text-[#D8E2EA]">{j.nom}</td>
                    {SOURCES.map(([k]) => (
                      <td key={k} className="py-2 text-center">
                        <span className={`inline-block h-2 w-2 rounded-full ${j.sources?.[k] ? "bg-[#34D399]" : "bg-[rgba(148,163,184,0.16)]"}`} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="rise col-span-12 rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-5 lg:col-span-6" style={{ animationDelay: "180ms" }} data-testid="admin-proprietaires">
          <h2 className="flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.25em] text-[#7C93A8]">
            <Users size={14} className="text-[#9B87F5]" /> Propriétaires
          </h2>
          <ul className="mt-4 space-y-3">
            {Object.entries(proprios).map(([p, js]) => (
              <li key={p} className="flex items-start justify-between gap-3">
                <span className="text-sm text-[#D8E2EA]">{p}</span>
                <span className="text-right font-code text-[10px] text-[#7C93A8]">{js.join(" · ")}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="rise col-span-12 rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-5 lg:col-span-6" style={{ animationDelay: "240ms" }} data-testid="admin-admissions">
          <h2 className="flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.25em] text-[#7C93A8]">
            <Clock size={14} className="text-[#F2B84B]" /> Admissions & fraîcheur
          </h2>
          <div className="mt-4 flex flex-wrap gap-2">
            {Object.entries(parStatut).map(([s, n]) => (
              <span key={s} className="rounded border border-[rgba(148,163,184,0.16)] bg-[rgba(148,163,184,0.07)] px-2.5 py-1 font-code text-[11px] text-[#D8E2EA]">
                {s} · {n}
              </span>
            ))}
          </div>
          <ul className="mt-4 space-y-2">
            {[...jumeaux].sort((a, b) => (a.statut === "actif" ? 1 : 0) - (b.statut === "actif" ? 1 : 0)).map((j) => (
              <li key={j.id} className="flex items-center justify-between text-xs">
                <span className="text-[#94A3B8]">{j.nom}</span>
                <span className="font-code text-[10px] text-[#7C93A8]">{j.fraicheur}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="rise col-span-12 rounded-xl border border-[#F87171]/20 bg-[#F87171]/[0.03] p-5" style={{ animationDelay: "360ms" }} data-testid="admin-reset">
          <h2 className="flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.25em] text-[#7C93A8]">
            <ArrowCounterClockwise size={14} className="text-[#F87171]" /> Zone de démonstration
          </h2>
          <p className="mt-2 text-xs text-[#7C93A8]">
            Restaure le jeu de données initial : situations ignorées ou décidées, jumeaux admis, vues enregistrées, dossiers de changement et journal sont remis à zéro.
          </p>
          <button
            onClick={reinitialiser}
            disabled={resetEnCours}
            data-testid="reset-demo-btn"
            className={`mt-3 rounded-md border px-3 py-2 text-xs font-semibold transition-colors ${
              confirmReset
                ? "border-[#F87171] bg-[#F87171]/15 text-[#F87171]"
                : "border-[rgba(148,163,184,0.16)] text-[#94A3B8] hover:border-[#F87171]/50 hover:text-[#F87171]"
            } disabled:opacity-50`}
          >
            {resetEnCours ? "Réinitialisation…" : confirmReset ? "Confirmer la réinitialisation ?" : "Réinitialiser la démo"}
          </button>
        </section>

        <section className="rise col-span-12 rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-5" style={{ animationDelay: "300ms" }} data-testid="admin-journal">
          <h2 className="flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.25em] text-[#7C93A8]">
            <Scroll size={14} className="text-[#25D0C8]" /> Journal d'accès et de décisions
          </h2>
          <div className="mt-4 overflow-hidden rounded-lg border border-[rgba(148,163,184,0.16)]">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-[rgba(148,163,184,0.07)] font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">
                  <th className="px-3 py-2 text-left font-medium">Quand</th>
                  <th className="px-3 py-2 text-left font-medium">Identité</th>
                  <th className="px-3 py-2 text-left font-medium">Espace</th>
                  <th className="px-3 py-2 text-left font-medium">Action</th>
                  <th className="px-3 py-2 text-left font-medium">Cible</th>
                  <th className="px-3 py-2 text-left font-medium">Détail</th>
                </tr>
              </thead>
              <tbody>
                {journal.map((e, i) => (
                  <tr key={i} className="border-t border-[rgba(148,163,184,0.16)]" data-testid={`journal-entry-${i}`}>
                    <td className="whitespace-nowrap px-3 py-2 font-code text-[10px] text-[#7C93A8]">
                      {new Date(e.quand).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
                    </td>
                    <td className="px-3 py-2 font-code text-[10px] text-[#D8E2EA]">{e.persona}</td>
                    <td className="px-3 py-2 font-code text-[10px] text-[#7C93A8]">{e.espace || "—"}</td>
                    <td className="px-3 py-2 text-[#D8E2EA]">{e.action}</td>
                    <td className="px-3 py-2 font-code text-[10px] text-[#94A3B8]">{e.cible || "—"}</td>
                    <td className="max-w-[280px] truncate px-3 py-2 text-[#7C93A8]">{e.detail || "—"}</td>
                  </tr>
                ))}
                {journal.length === 0 && (
                  <tr><td colSpan={6} className="px-3 py-6 text-center text-[#7C93A8]">Aucune entrée pour l'instant.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
