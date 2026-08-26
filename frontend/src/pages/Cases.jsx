import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, MagnifyingGlass, Rows, Kanban as KanbanIcon, ClockCounterClockwise, X } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import { usePerimetre } from "@/lib/perimetre";
import { couleurDomaine } from "@/lib/domaines";

export const TYPES_CASE = {
  demande: ["Demande", "#3B82F6"],
  changement: ["Changement", "#FBBF24"],
  incident: ["Incident", "#F87171"],
  decouverte: ["Découverte", "#22D3EE"],
  decision: ["Décision", "#A78BFA"],
  conformite: ["Conformité", "#10B981"],
  modernisation: ["Modernisation", "#F97316"],
};

export const STATUTS_CASE = {
  ouvert: ["Ouvert", "#3B82F6"],
  en_cours: ["En cours", "#FBBF24"],
  en_attente: ["En attente", "#94A3B8"],
  clos: ["Clos", "#10B981"],
};

const rel = (iso) => {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 3600) return `il y a ${Math.max(1, Math.round(s / 60))} min`;
  if (s < 86400) return `il y a ${Math.round(s / 3600)} h`;
  return `il y a ${Math.round(s / 86400)} j`;
};

export default function Cases() {
  const [cases, setCases] = useState([]);
  const [vue, setVue] = useState("liste");
  const [filtreType, setFiltreType] = useState("tous");
  const [filtreStatut, setFiltreStatut] = useState("tous");
  const [recherche, setRecherche] = useState("");
  const [creation, setCreation] = useState(false);
  const [form, setForm] = useState({ titre: "", type: "demande", objectif: "", jumeaux: [] });
  const [envoi, setEnvoi] = useState(false);
  const { mesh } = useMesh();
  const { version } = usePerimetre();
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/cases").then((r) => setCases(r.data)).catch(() => {});
  }, [version]);

  const filtres = useMemo(() => {
    const q = recherche.trim().toLowerCase();
    return cases.filter(
      (c) =>
        (filtreType === "tous" || c.type === filtreType) &&
        (filtreStatut === "tous" || c.statut === filtreStatut) &&
        (!q || c.titre.toLowerCase().includes(q) || (c.objectif || "").toLowerCase().includes(q))
    );
  }, [cases, filtreType, filtreStatut, recherche]);

  const creer = async () => {
    if (!form.titre.trim() || envoi) return;
    setEnvoi(true);
    try {
      const { data } = await api.post("/cases", form);
      toast.success("Case créé");
      navigate(`/cases/${data.id}`);
    } catch {
      toast.error("Création impossible");
      setEnvoi(false);
    }
  };

  const BadgeType = ({ type }) => {
    const t = TYPES_CASE[type] || [type, "#9CA3AF"];
    return <span className="rounded border px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider" style={{ color: t[1], borderColor: `${t[1]}44`, backgroundColor: `${t[1]}12` }}>{t[0]}</span>;
  };
  const BadgeStatut = ({ statut }) => {
    const s = STATUTS_CASE[statut] || [statut, "#9CA3AF"];
    return <span className="flex items-center gap-1.5 text-xs" style={{ color: s[1] }}><span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: s[1] }} />{s[0]}</span>;
  };
  const ChipsJumeaux = ({ ids }) => (
    <div className="flex flex-wrap gap-1">
      {(ids || []).slice(0, 3).map((id) => {
        const j = mesh?.jumeaux.find((x) => x.id === id);
        if (!j) return null;
        return (
          <span key={id} className="rounded-full border px-1.5 py-0.5 font-code text-[9px]" style={{ color: couleurDomaine(j.domaine), borderColor: `${couleurDomaine(j.domaine)}44`, backgroundColor: `${couleurDomaine(j.domaine)}0D` }}>
            {j.nom}
          </span>
        );
      })}
      {(ids || []).length > 3 && <span className="font-code text-[9px] text-white/35">+{ids.length - 3}</span>}
    </div>
  );

  return (
    <div className="h-full overflow-y-auto p-8 pb-16" data-testid="cases-page">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-bold tracking-tight text-white" data-testid="cases-titre">Cases</h1>
          <p className="mt-1 text-sm text-white/50">Le centre du travail collectif — demandes, changements, incidents, découvertes, décisions.</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <MagnifyingGlass size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-white/30" />
            <input
              value={recherche}
              onChange={(e) => setRecherche(e.target.value)}
              placeholder="Rechercher un case…"
              data-testid="recherche-case"
              className="h-9 w-56 rounded-md border border-white/10 bg-black/40 pl-8 pr-3 text-xs text-white placeholder:text-white/30 focus:border-[#3B82F6]/60 focus:outline-none"
            />
          </div>
          <div className="flex rounded-md border border-white/10" data-testid="cases-vues">
            {[["liste", Rows, "Liste"], ["kanban", KanbanIcon, "Kanban"], ["chrono", ClockCounterClockwise, "Chronologie"]].map(([v, Icon, label], i) => (
              <button
                key={v}
                onClick={() => setVue(v)}
                data-testid={`vue-${v}`}
                title={label}
                className={`flex items-center gap-1.5 px-3 py-2 text-xs transition-colors ${i > 0 ? "border-l border-white/10" : ""} ${vue === v ? "bg-white/[0.08] text-white" : "text-white/45 hover:text-white"}`}
              >
                <Icon size={14} /> <span className="hidden lg:inline">{label}</span>
              </button>
            ))}
          </div>
          <button onClick={() => setCreation(!creation)} data-testid="nouveau-case-btn" className="flex items-center gap-2 rounded-md bg-[#3B82F6] px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#2F6FDB]">
            {creation ? <X size={15} /> : <Plus size={15} weight="bold" />} Nouveau Case
          </button>
        </div>
      </header>

      {/* Création inline */}
      {creation && (
        <div className="rise mt-5 rounded-xl border border-[#3B82F6]/25 bg-[#3B82F6]/[0.03] p-5" data-testid="case-form">
          <div className="grid gap-3 md:grid-cols-2">
            <input
              value={form.titre}
              onChange={(e) => setForm({ ...form, titre: e.target.value })}
              placeholder="Titre du case — ex. Peut-on proposer le paiement différé aux clients professionnels ?"
              data-testid="case-titre-input"
              className="rounded-md border border-white/10 bg-black/50 px-3 py-2.5 text-sm text-white placeholder:text-white/30 focus:border-[#3B82F6]/60 focus:outline-none md:col-span-2"
            />
            <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} data-testid="case-type-select" className="rounded-md border border-white/10 bg-black/50 px-3 py-2.5 text-sm text-white focus:outline-none">
              {Object.entries(TYPES_CASE).map(([k, [l]]) => <option key={k} value={k} label={l} />)}
            </select>
            <input
              value={form.objectif}
              onChange={(e) => setForm({ ...form, objectif: e.target.value })}
              placeholder="Objectif (optionnel)"
              data-testid="case-objectif-input"
              className="rounded-md border border-white/10 bg-black/50 px-3 py-2.5 text-sm text-white placeholder:text-white/30 focus:border-[#3B82F6]/60 focus:outline-none"
            />
          </div>
          <div className="mt-3">
            <div className="font-code text-[9px] uppercase tracking-[0.2em] text-white/40">Jumeaux à mobiliser</div>
            <div className="mt-1.5 flex flex-wrap gap-1.5" data-testid="case-jumeaux-select">
              {(mesh?.jumeaux || []).filter((j) => !j.anonyme).map((j) => {
                const actif = form.jumeaux.includes(j.id);
                return (
                  <button
                    key={j.id}
                    onClick={() => setForm({ ...form, jumeaux: actif ? form.jumeaux.filter((x) => x !== j.id) : [...form.jumeaux, j.id] })}
                    data-testid={`case-jumeau-${j.id}`}
                    className={`rounded-full border px-2.5 py-1 font-code text-[10px] transition-colors ${actif ? "border-[#3B82F6]/60 bg-[#3B82F6]/15 text-white" : "border-white/10 text-white/45 hover:text-white"}`}
                  >
                    {j.nom}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="mt-4 flex justify-end gap-2">
            <button onClick={() => setCreation(false)} className="rounded-md px-3 py-2 text-xs text-white/50 transition-colors hover:text-white">Annuler</button>
            <button onClick={creer} disabled={!form.titre.trim() || envoi} data-testid="case-creer-submit" className="rounded-md bg-[#3B82F6] px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-[#2F6FDB] disabled:opacity-40">
              {envoi ? "Création…" : "Créer le Case"}
            </button>
          </div>
        </div>
      )}

      {/* Filtres */}
      <div className="mt-5 flex flex-wrap items-center gap-2">
        <select value={filtreType} onChange={(e) => setFiltreType(e.target.value)} data-testid="filtre-type-case" className="rounded-md border border-white/10 bg-black/40 px-2.5 py-1.5 text-xs text-white/70 focus:outline-none">
          <option value="tous" label="Tous les types" />
          {Object.entries(TYPES_CASE).map(([k, [l]]) => <option key={k} value={k} label={l} />)}
        </select>
        <select value={filtreStatut} onChange={(e) => setFiltreStatut(e.target.value)} data-testid="filtre-statut-case" className="rounded-md border border-white/10 bg-black/40 px-2.5 py-1.5 text-xs text-white/70 focus:outline-none">
          <option value="tous" label="Tous les statuts" />
          {Object.entries(STATUTS_CASE).map(([k, [l]]) => <option key={k} value={k} label={l} />)}
        </select>
        <span className="font-code text-[10px] text-white/30">{filtres.length} case{filtres.length > 1 ? "s" : ""}</span>
      </div>

      {filtres.length === 0 && (
        <p className="mt-10 text-center text-sm text-white/35" data-testid="cases-vide">Aucun case dans ce périmètre — créez-en un, ou depuis une conversation avec Flore.</p>
      )}

      {/* Vue liste */}
      {vue === "liste" && filtres.length > 0 && (
        <div className="mt-4 overflow-hidden rounded-xl border border-white/[0.06]" data-testid="cases-liste">
          <div className="grid grid-cols-[minmax(0,2.4fr)_110px_110px_minmax(0,1.6fr)_150px_80px] gap-3 border-b border-white/[0.06] px-5 py-2.5 font-code text-[9px] uppercase tracking-[0.2em] text-white/35 max-lg:hidden">
            <span>Case</span><span>Type</span><span>Statut</span><span>Jumeaux mobilisés</span><span>Contenu</span><span className="text-right">Màj</span>
          </div>
          {filtres.map((c) => (
            <div
              key={c.id}
              onClick={() => navigate(`/cases/${c.id}`)}
              data-testid={`case-row-${c.id}`}
              className="grid cursor-pointer grid-cols-[minmax(0,2.4fr)_110px_110px_minmax(0,1.6fr)_150px_80px] items-center gap-3 border-b border-white/[0.04] px-5 py-3.5 transition-colors last:border-0 hover:bg-white/[0.03] max-lg:grid-cols-[minmax(0,1fr)_auto]"
            >
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-white/90">{c.titre}</div>
                {c.objectif && <div className="mt-0.5 truncate text-[11px] text-white/40">{c.objectif}</div>}
              </div>
              <div className="max-lg:hidden"><BadgeType type={c.type} /></div>
              <div className="max-lg:hidden"><BadgeStatut statut={c.statut} /></div>
              <ChipsJumeaux ids={c.jumeaux} />
              <div className="font-code text-[10px] text-white/45 max-lg:hidden">
                {c.nb_options} option{c.nb_options > 1 ? "s" : ""} · {c.nb_decisions} décision{c.nb_decisions > 1 ? "s" : ""} · {c.nb_messages} msg
              </div>
              <div className="text-right font-code text-[10px] text-white/40">{rel(c.maj_le)}</div>
            </div>
          ))}
        </div>
      )}

      {/* Vue kanban */}
      {vue === "kanban" && filtres.length > 0 && (
        <div className="mt-4 grid grid-cols-2 gap-3 xl:grid-cols-4" data-testid="cases-kanban">
          {Object.entries(STATUTS_CASE).map(([statut, [label, couleur]]) => {
            const colonne = filtres.filter((c) => c.statut === statut);
            return (
              <div key={statut} className="rounded-xl border border-white/[0.06] bg-white/[0.015] p-3" data-testid={`kanban-col-${statut}`}>
                <div className="flex items-center gap-2 px-1 pb-2">
                  <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: couleur }} />
                  <span className="font-code text-[10px] uppercase tracking-[0.2em] text-white/50">{label}</span>
                  <span className="ml-auto font-code text-[10px] text-white/30">{colonne.length}</span>
                </div>
                <div className="space-y-2">
                  {colonne.map((c) => (
                    <div key={c.id} onClick={() => navigate(`/cases/${c.id}`)} data-testid={`case-card-${c.id}`} className="cursor-pointer rounded-lg border border-white/[0.07] bg-[#0D0D0D] p-3 transition-colors hover:border-white/20">
                      <div className="flex items-start justify-between gap-2">
                        <div className="text-xs font-semibold leading-snug text-white/90">{c.titre}</div>
                        <BadgeType type={c.type} />
                      </div>
                      <div className="mt-2"><ChipsJumeaux ids={c.jumeaux} /></div>
                      <div className="mt-2 flex items-center justify-between font-code text-[9px] text-white/35">
                        <span>{c.nb_decisions} décision{c.nb_decisions > 1 ? "s" : ""} · {c.nb_messages} msg</span>
                        <span>{rel(c.maj_le)}</span>
                      </div>
                    </div>
                  ))}
                  {colonne.length === 0 && <p className="px-1 py-3 text-center font-code text-[10px] text-white/20">—</p>}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Vue chronologie */}
      {vue === "chrono" && filtres.length > 0 && (
        <div className="mt-6 max-w-3xl" data-testid="cases-chrono">
          {filtres.map((c) => {
            const t = TYPES_CASE[c.type] || [c.type, "#9CA3AF"];
            return (
              <div key={c.id} className="relative flex gap-4 pb-6 pl-6" data-testid={`chrono-item-${c.id}`}>
                <span className="absolute left-0 top-1.5 h-2.5 w-2.5 rounded-full border-2 border-[#050505]" style={{ backgroundColor: t[1] }} />
                <span className="absolute bottom-0 left-[5px] top-4 w-px bg-white/[0.08]" />
                <div className="w-24 shrink-0 pt-0.5 font-code text-[10px] text-white/40">{new Date(c.maj_le).toLocaleDateString("fr-FR", { day: "2-digit", month: "short" })}</div>
                <div onClick={() => navigate(`/cases/${c.id}`)} className="flex-1 cursor-pointer rounded-lg border border-white/[0.07] p-3.5 transition-colors hover:border-white/20 hover:bg-white/[0.02]">
                  <div className="flex items-center gap-2">
                    <BadgeType type={c.type} />
                    <BadgeStatut statut={c.statut} />
                    <span className="ml-auto font-code text-[9px] text-white/30">{rel(c.maj_le)}</span>
                  </div>
                  <div className="mt-1.5 text-sm font-semibold text-white/90">{c.titre}</div>
                  {c.objectif && <div className="mt-0.5 text-[11px] text-white/45">{c.objectif}</div>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
