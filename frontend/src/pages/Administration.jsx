import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Database, CheckCircle, Clock, Users, Scroll, ArrowCounterClockwise, Check, Minus, MagnifyingGlass } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { usePerimetre } from "@/lib/perimetre";
import { couleurConfiance } from "@/lib/domaines";

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
  const [recherche, setRecherche] = useState("");
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

  // La recherche filtre les deux listes par jumeau (nom, propriétaire, domaine)
  const visibles = useMemo(() => {
    const q = recherche.trim().toLowerCase();
    return q ? jumeaux.filter((j) => [j.nom, j.proprietaire, j.domaine].some((v) => (v || "").toLowerCase().includes(q))) : jumeaux;
  }, [jumeaux, recherche]);

  const couvertureMoy = jumeaux.length ? Math.round(jumeaux.reduce((a, j) => a + (j.couverture || 0), 0) / jumeaux.length) : 0;
  const parStatut = jumeaux.reduce((acc, j) => ({ ...acc, [j.statut]: (acc[j.statut] || 0) + 1 }), {});
  const proprios = jumeaux.reduce((acc, j) => {
    (acc[j.proprietaire] = acc[j.proprietaire] || []).push(j.nom);
    return acc;
  }, {});

  return (
    <div className="h-full overflow-y-auto px-4 py-5 pb-44 sm:px-8 sm:py-8" data-testid="administration-page">
      <header className="rise">
        <div className="font-code text-[10px] uppercase tracking-[0.3em] text-[#60A5FA]">Administration</div>
        <h1 className="mt-1 font-display text-2xl font-black tracking-tight text-[#F2F6F8] sm:text-3xl">Administration</h1>
        <p className="mt-2 text-base text-[#94A3B8]">Sources, propriétaires, couverture et fraîcheur de la connaissance du Mesh.</p>
        <div className="relative mt-4 max-w-sm">
          <MagnifyingGlass size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#7C93A8]" />
          <input value={recherche} onChange={(e) => setRecherche(e.target.value)} placeholder="Filtrer par jumeau, propriétaire ou domaine…" data-testid="admin-recherche" aria-label="Filtrer les jumeaux"
            className="h-9 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] pl-7 pr-3 text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/60 focus:outline-none" />
        </div>
      </header>

      <div className="mt-8 grid grid-cols-12 gap-6">
        <section className="rise col-span-12 rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-5 lg:col-span-5" style={{ animationDelay: "60ms" }} data-testid="admin-couverture">
          <h2 className="flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.25em] text-[#7C93A8]">
            <CheckCircle size={14} className="text-[#60A5FA]" /> Couverture de connaissance
          </h2>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-display text-4xl font-black text-[#F2F6F8]" data-testid="couverture-moyenne">{couvertureMoy} %</span>
            <span className="font-code text-[10px] text-[#7C93A8]">moyenne du Mesh</span>
          </div>
          <p className="mt-2 font-code text-[11px] text-[#7C93A8]">
            Couleur = niveau de couverture :
            <span className="ml-2 text-[#F87171]">● &lt; 40 %</span> <span className="ml-2 text-[#F2B84B]">● 40–69 %</span> <span className="ml-2 text-[#34D399]">● ≥ 70 %</span>
          </p>
          <ul className="mt-3 space-y-1">
            {[...visibles].sort((a, b) => a.couverture - b.couverture).map((j) => (
              <li key={j.id}>
                <Link to={`/jumeaux/${j.id}/revue`} data-testid={`admin-couv-${j.id}`} title={`Ouvrir la revue de ${j.nom}`} className="flex items-center gap-3 rounded-md px-1 py-1.5 transition-colors hover:bg-white/[0.04]">
                  <span className="w-28 shrink-0 truncate text-xs text-[#94A3B8] sm:w-32">{j.nom}</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[rgba(148,163,184,0.16)]">
                    <div className="h-full rounded-full" style={{ width: `${j.couverture}%`, backgroundColor: couleurConfiance(j.couverture) }} />
                  </div>
                  <span className="w-11 shrink-0 text-right font-code text-[11px] text-[#D8E2EA]">{j.couverture} %</span>
                </Link>
              </li>
            ))}
            {visibles.length === 0 && <li className="py-3 text-center text-xs text-[#7C93A8]">Aucun jumeau ne correspond.</li>}
          </ul>
        </section>

        <section className="rise col-span-12 rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-5 lg:col-span-7" style={{ animationDelay: "120ms" }} data-testid="admin-sources">
          <h2 className="flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.25em] text-[#7C93A8]">
            <Database size={14} className="text-[#60A5FA]" /> Sources connectées
          </h2>
          <p className="mt-2 flex items-center gap-3 font-code text-[11px] text-[#7C93A8]">
            <span className="flex items-center gap-1"><Check size={11} weight="bold" className="text-[#34D399]" /> source connectée</span>
            <span className="flex items-center gap-1"><Minus size={11} /> absente</span>
          </p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[30rem] text-xs">
              <thead>
                <tr className="font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">
                  <th className="pb-2 text-left font-medium">Jumeau</th>
                  {SOURCES.map(([k, label]) => <th key={k} className="pb-2 text-center font-medium">{label}</th>)}
                </tr>
              </thead>
              <tbody>
                {visibles.map((j) => (
                  <tr key={j.id} className="border-t border-[rgba(148,163,184,0.16)]" data-testid={`admin-source-${j.id}`}>
                    <td className="py-2 pr-3 text-[#D8E2EA]"><Link to={`/jumeaux/${j.id}/revue`} className="hover:text-[#60A5FA] hover:underline">{j.nom}</Link></td>
                    {SOURCES.map(([k, label]) => (
                      <td key={k} className="py-2 text-center">
                        {j.sources?.[k]
                          ? <Check size={13} weight="bold" className="inline text-[#34D399]" aria-label={`${label} connectée`} />
                          : <Minus size={13} className="inline text-[#41576D]" aria-label={`${label} absente`} />}
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
            <Users size={14} className="text-[#60A5FA]" /> Propriétaires
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
            {[...visibles].sort((a, b) => (a.statut === "actif" ? 1 : 0) - (b.statut === "actif" ? 1 : 0)).map((j) => (
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
            <Scroll size={14} className="text-[#60A5FA]" /> Journal d'accès et de décisions
          </h2>
          <div className="mt-4 overflow-x-auto rounded-lg border border-[rgba(148,163,184,0.16)]">
            <table className="w-full min-w-[40rem] text-xs">
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
