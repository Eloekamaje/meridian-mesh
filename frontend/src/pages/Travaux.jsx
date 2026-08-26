import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, MagnifyingGlass, Rows, Kanban as KanbanIcon, ClockCounterClockwise, X } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import { usePerimetre } from "@/lib/perimetre";
import { couleurDomaine } from "@/lib/domaines";
import { numeroCase } from "@/components/case/utils";

export const TYPES_CASE = {
  demande: ["Demande", "#3730A3"],
  changement: ["Changement", "#B45309"],
  incident: ["Incident", "#B91C1C"],
  decouverte: ["Découverte", "#0E7490"],
  decision: ["Décision", "#6D28D9"],
  conformite: ["Conformité", "#047857"],
  modernisation: ["Modernisation", "#C2410C"],
};

export const STATUTS_CASE = {
  ouvert: ["Ouvert", "#3730A3"],
  en_cours: ["En cours", "#B45309"],
  en_attente: ["En attente", "#64748B"],
  clos: ["Clos", "#047857"],
};

const rel = (iso) => {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 3600) return `il y a ${Math.max(1, Math.round(s / 60))} min`;
  if (s < 86400) return `il y a ${Math.round(s / 3600)} h`;
  return `il y a ${Math.round(s / 86400)} j`;
};

export default function Travaux() {
  const [cases, setCases] = useState([]);
  const [vue, setVue] = useState("liste");
  const [filtreType, setFiltreType] = useState("tous");
  const [filtreStatut, setFiltreStatut] = useState("tous");
  const [recherche, setRecherche] = useState("");
  const [creation, setCreation] = useState(false);
  const [form, setForm] = useState({ titre: "", type: "demande", objectif: "", jumeaux: [] });
  const [envoi, setEnvoi] = useState(false);
  const [mesSeulement, setMesSeulement] = useState(false);
  const [personas, setPersonas] = useState([]);
  const { mesh } = useMesh();
  const { version, persona, info } = usePerimetre();
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/cases").then((r) => setCases(r.data)).catch(() => {});
    api.get("/personas").then((r) => setPersonas(r.data)).catch(() => {});
  }, [version]);

  const filtres = useMemo(() => {
    const q = recherche.trim().toLowerCase();
    return cases.filter(
      (c) =>
        (!mesSeulement || c.responsable === persona) &&
        (filtreType === "tous" || c.type === filtreType) &&
        (filtreStatut === "tous" || c.statut === filtreStatut) &&
        (!q || c.titre.toLowerCase().includes(q) || (c.objectif || "").toLowerCase().includes(q))
    );
  }, [cases, filtreType, filtreStatut, recherche, mesSeulement, persona]);

  const creer = async () => {
    if (!form.titre.trim() || envoi) return;
    setEnvoi(true);
    try {
      const { data } = await api.post("/cases", { ...form, responsable: form.responsable || persona, espace: info?.espace?.id });
      toast.success("Travail conservé");
      navigate(`/travaux/${data.id}`);
    } catch {
      toast.error("Création impossible");
      setEnvoi(false);
    }
  };

  const BadgeArevoir = ({ id }) => (
    <span className="rounded border border-[#B91C1C]/40 bg-[#B91C1C]/[0.06] px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider text-[#B91C1C]" data-testid={`travail-arevoir-${id}`}>À revoir</span>
  );

  const BadgeType = ({ type }) => {
    const t = TYPES_CASE[type] || [type, "#71716D"];
    return <span className="rounded border px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider" style={{ color: t[1], borderColor: `${t[1]}44`, backgroundColor: `${t[1]}0D` }}>{t[0]}</span>;
  };
  const BadgeStatut = ({ statut }) => {
    const s = STATUTS_CASE[statut] || [statut, "#71716D"];
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
      {(ids || []).length > 3 && <span className="font-code text-[9px] text-[#71716D]">+{ids.length - 3}</span>}
    </div>
  );

  return (
    <div className="h-full overflow-y-auto p-8 pb-16" data-testid="travaux-page">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-bold tracking-tight text-[#111110]" data-testid="travaux-titre">Travaux</h1>
          <p className="mt-1 text-sm text-[#52524F]">La mémoire persistante des situations traitées avec Méridian — demandes, changements, incidents, découvertes, décisions.</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <MagnifyingGlass size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#71716D]" />
            <input
              value={recherche}
              onChange={(e) => setRecherche(e.target.value)}
              placeholder="Rechercher un travail…"
              data-testid="recherche-travail"
              className="h-9 w-56 rounded-md border border-[#E5E5E3] bg-white pl-8 pr-3 text-xs text-[#111110] placeholder:text-[#71716D] focus:border-[#3730A3]/60 focus:outline-none"
            />
          </div>
          <div className="flex rounded-md border border-[#E5E5E3]" data-testid="travaux-vues">
            {[["liste", Rows, "Liste"], ["kanban", KanbanIcon, "Kanban"], ["chrono", ClockCounterClockwise, "Chronologie"]].map(([v, Icon, label], i) => (
              <button
                key={v}
                onClick={() => setVue(v)}
                data-testid={`vue-${v}`}
                title={label}
                className={`flex items-center gap-1.5 px-3 py-2 text-xs transition-colors ${i > 0 ? "border-l border-[#E5E5E3]" : ""} ${vue === v ? "bg-[#F0F0EE] text-[#111110]" : "text-[#71716D] hover:text-[#111110]"}`}
              >
                <Icon size={14} /> <span className="hidden lg:inline">{label}</span>
              </button>
            ))}
          </div>
          <button onClick={() => setCreation(!creation)} data-testid="nouveau-travail-btn" className="flex items-center gap-2 rounded-md bg-[#3730A3] px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#4338CA]">
            {creation ? <X size={15} /> : <Plus size={15} weight="bold" />} Nouveau travail
          </button>
        </div>
      </header>

      {/* Création inline */}
      {creation && (
        <div className="rise mt-5 rounded-xl border border-[#3730A3]/25 bg-[#EEECFA] p-5" data-testid="travail-form">
          <div className="grid gap-3 md:grid-cols-2">
            <input
              value={form.titre}
              onChange={(e) => setForm({ ...form, titre: e.target.value })}
              placeholder="Titre du travail — ex. Peut-on proposer le paiement différé aux clients professionnels ?"
              data-testid="travail-titre-input"
              className="rounded-md border border-[#E5E5E3] bg-white px-3 py-2.5 text-sm text-[#111110] placeholder:text-[#71716D] focus:border-[#3730A3]/60 focus:outline-none md:col-span-2"
            />
            <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} data-testid="travail-type-select" className="rounded-md border border-[#E5E5E3] bg-white px-3 py-2.5 text-sm text-[#111110] focus:outline-none">
              {Object.entries(TYPES_CASE).map(([k, [l]]) => <option key={k} value={k} label={l} />)}
            </select>
            <select value={form.responsable || ""} onChange={(e) => setForm({ ...form, responsable: e.target.value || undefined })} data-testid="travail-responsable-select" className="rounded-md border border-[#E5E5E3] bg-white px-3 py-2.5 text-sm text-[#111110] focus:outline-none">
              <option value="" label="Responsable : moi" />
              {personas.map((p) => <option key={p.id} value={p.id} label={`${p.nom} — ${p.role}`} />)}
            </select>
            <input
              value={form.objectif}
              onChange={(e) => setForm({ ...form, objectif: e.target.value })}
              placeholder="Objectif (optionnel)"
              data-testid="travail-objectif-input"
              className="rounded-md border border-[#E5E5E3] bg-white px-3 py-2.5 text-sm text-[#111110] placeholder:text-[#71716D] focus:border-[#3730A3]/60 focus:outline-none"
            />
          </div>
          <div className="mt-3">
            <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#52524F]">Jumeaux à mobiliser</div>
            <div className="mt-1.5 flex flex-wrap gap-1.5" data-testid="travail-jumeaux-select">
              {(mesh?.jumeaux || []).filter((j) => !j.anonyme).map((j) => {
                const actif = form.jumeaux.includes(j.id);
                return (
                  <button
                    key={j.id}
                    onClick={() => setForm({ ...form, jumeaux: actif ? form.jumeaux.filter((x) => x !== j.id) : [...form.jumeaux, j.id] })}
                    data-testid={`travail-jumeau-${j.id}`}
                    className={`rounded-full border px-2.5 py-1 font-code text-[10px] transition-colors ${actif ? "border-[#3730A3]/60 bg-[#3730A3]/15 text-white" : "border-[#E5E5E3] text-[#52524F] hover:text-[#111110]"}`}
                  >
                    {j.nom}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="mt-4 flex justify-end gap-2">
            <button onClick={() => setCreation(false)} className="rounded-md px-3 py-2 text-xs text-[#52524F] transition-colors hover:text-[#111110]">Annuler</button>
            <button onClick={creer} disabled={!form.titre.trim() || envoi} data-testid="travail-creer-submit" className="rounded-md bg-[#3730A3] px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-[#4338CA] disabled:opacity-40">
              {envoi ? "Création…" : "Conserver le travail"}
            </button>
          </div>
        </div>
      )}

      {/* Filtres */}
      <div className="mt-5 flex flex-wrap items-center gap-2">
        <button
          onClick={() => setMesSeulement(!mesSeulement)}
          data-testid="filtre-mes-travaux"
          className={`rounded-full border px-3 py-1.5 text-xs transition-colors ${mesSeulement ? "border-[#3730A3]/60 bg-[#3730A3]/15 text-white" : "border-[#E5E5E3] text-[#52524F] hover:text-[#111110]"}`}
        >
          Mes travaux
        </button>
        <select value={filtreType} onChange={(e) => setFiltreType(e.target.value)} data-testid="filtre-type-travail" className="rounded-md border border-[#E5E5E3] bg-white px-2.5 py-1.5 text-xs text-[#3F3F3C] focus:outline-none">
          <option value="tous" label="Tous les types" />
          {Object.entries(TYPES_CASE).map(([k, [l]]) => <option key={k} value={k} label={l} />)}
        </select>
        <select value={filtreStatut} onChange={(e) => setFiltreStatut(e.target.value)} data-testid="filtre-statut-travail" className="rounded-md border border-[#E5E5E3] bg-white px-2.5 py-1.5 text-xs text-[#3F3F3C] focus:outline-none">
          <option value="tous" label="Tous les statuts" />
          {Object.entries(STATUTS_CASE).map(([k, [l]]) => <option key={k} value={k} label={l} />)}
        </select>
        <span className="font-code text-[10px] text-[#71716D]">{filtres.length} travail{filtres.length > 1 ? "aux" : ""}</span>
      </div>

      {filtres.length === 0 && (
        <p className="mt-10 text-center text-sm text-[#71716D]" data-testid="travaux-vide">Aucun travail dans ce périmètre — conservez-en un depuis une conversation avec Flore.</p>
      )}

      {/* Vue liste — cartes narratives */}
      {vue === "liste" && filtres.length > 0 && (
        <div className="mt-4 space-y-3" data-testid="travaux-liste">
          {filtres.map((c) => {
            const s = STATUTS_CASE[c.statut] || [c.statut, "#71716D"];
            return (
              <div key={c.id} data-testid={`travail-row-${c.id}`} className="rounded-xl border border-[#E5E5E3] bg-white p-4 transition-colors hover:border-[#D4D4D0]">
                <div className="flex items-center gap-2">
                  <span className="rounded border border-[#E5E5E3] bg-[#F7F7F6] px-1.5 py-0.5 font-code text-[10px] text-[#71716D]">{numeroCase(c)}</span>
                  <BadgeType type={c.type} />
                  <span className="flex items-center gap-1.5 text-xs" style={{ color: s[1] }}><span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: s[1] }} />{s[0]}</span>
                  {c.a_revoir && <BadgeArevoir id={c.id} />}
                  <span className="ml-auto font-code text-[9px] text-[#71716D]">Dernière activité : {rel(c.maj_le)}</span>
                </div>
                <div onClick={() => navigate(`/travaux/${c.id}`)} className="mt-1.5 cursor-pointer text-base font-semibold text-[#111110] hover:text-[#3730A3]">{c.titre}</div>
                {c.objectif && <p className="mt-0.5 text-xs leading-snug text-[#52524F]">{c.objectif}</p>}
                {c.resume && (
                  <p className="mt-1.5 border-l-2 border-[#0E7490]/30 pl-2.5 text-xs italic leading-snug text-[#3F3F3C]" data-testid={`travail-resume-extrait-${c.id}`}>
                    <span className="font-code text-[9px] not-italic uppercase tracking-wider text-[#0E7490]">Compréhension actuelle — </span>{c.resume}
                  </p>
                )}
                <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 font-code text-[10px] text-[#52524F]">
                  <span>● {c.jumeaux?.length || 0} jumeau{(c.jumeaux?.length || 0) > 1 ? "x" : ""}</span>
                  <span>◉ {(c.participants || []).length} participant{(c.participants || []).length > 1 ? "s" : ""}</span>
                  <span>? {c.nb_questions_ouvertes} question{c.nb_questions_ouvertes > 1 ? "s" : ""}</span>
                  <span>⚑ {c.nb_options_a_trancher} décision{c.nb_options_a_trancher > 1 ? "s" : ""} attendue{c.nb_options_a_trancher > 1 ? "s" : ""}</span>
                </div>
                <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 border-t border-[#E5E5E3] pt-2.5">
                  <span className="min-w-0 truncate font-code text-[10px] text-[#71716D]">
                    {c.derniere_modif ? <>Modification importante : {c.derniere_modif}</> : "—"}
                  </span>
                  <div className="flex shrink-0 gap-1.5">
                    <button onClick={() => navigate(`/travaux/${c.id}`)} data-testid={`travail-apercu-${c.id}`} className="rounded-md border border-[#E5E5E3] px-3 py-1.5 text-[11px] text-[#52524F] transition-colors hover:border-[#D4D4D0] hover:text-[#111110]">
                      Voir l'aperçu
                    </button>
                    <button onClick={() => navigate(`/travaux/${c.id}?vue=activite`)} data-testid={`travail-continuer-${c.id}`} className="rounded-md bg-[#3730A3] px-3 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-[#4338CA]">
                      Continuer
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Vue kanban */}
      {vue === "kanban" && filtres.length > 0 && (
        <div className="mt-4 grid grid-cols-2 gap-3 xl:grid-cols-4" data-testid="travaux-kanban">
          {Object.entries(STATUTS_CASE).map(([statut, [label, couleur]]) => {
            const colonne = filtres.filter((c) => c.statut === statut);
            return (
              <div key={statut} className="rounded-xl border border-[#E5E5E3] bg-[#F7F7F6] p-3" data-testid={`kanban-col-${statut}`}>
                <div className="flex items-center gap-2 px-1 pb-2">
                  <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: couleur }} />
                  <span className="font-code text-[10px] uppercase tracking-[0.2em] text-[#52524F]">{label}</span>
                  <span className="ml-auto font-code text-[10px] text-[#71716D]">{colonne.length}</span>
                </div>
                <div className="space-y-2">
                  {colonne.map((c) => (
                    <div key={c.id} onClick={() => navigate(`/travaux/${c.id}`)} data-testid={`travail-card-${c.id}`} className="cursor-pointer rounded-lg border border-[#E5E5E3] bg-white p-3 transition-colors hover:border-[#D4D4D0]">
                      <div className="flex items-start justify-between gap-2">
                        <div className="text-xs font-semibold leading-snug text-[#111110]">{c.titre}</div>
                        <div className="flex shrink-0 flex-col items-end gap-1">
                          <BadgeType type={c.type} />
                          {c.a_revoir && <BadgeArevoir id={c.id} />}
                        </div>
                      </div>
                      <div className="mt-2"><ChipsJumeaux ids={c.jumeaux} /></div>
                      <div className="mt-2 flex items-center justify-between font-code text-[9px] text-[#71716D]">
                        <span>{c.nb_decisions} décision{c.nb_decisions > 1 ? "s" : ""} · {c.nb_messages} msg</span>
                        <span>{rel(c.maj_le)}</span>
                      </div>
                      <div className="mt-2 flex gap-1.5 border-t border-[#E5E5E3] pt-2">
                        <button onClick={(e) => { e.stopPropagation(); navigate(`/travaux/${c.id}`); }} data-testid={`travail-apercu-${c.id}`} className="flex-1 rounded border border-[#E5E5E3] px-2 py-1 text-[10px] text-[#52524F] transition-colors hover:text-[#111110]">
                          Aperçu
                        </button>
                        <button onClick={(e) => { e.stopPropagation(); navigate(`/travaux/${c.id}?vue=activite`); }} data-testid={`travail-continuer-${c.id}`} className="flex-1 rounded bg-[#3730A3] px-2 py-1 text-[10px] font-semibold text-white transition-colors hover:bg-[#4338CA]">
                          Continuer
                        </button>
                      </div>
                    </div>
                  ))}
                  {colonne.length === 0 && <p className="px-1 py-3 text-center font-code text-[10px] text-[#71716D]">—</p>}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Vue chronologie */}
      {vue === "chrono" && filtres.length > 0 && (
        <div className="mt-6 max-w-3xl" data-testid="travaux-chrono">
          {filtres.map((c) => {
            const t = TYPES_CASE[c.type] || [c.type, "#71716D"];
            return (
              <div key={c.id} className="relative flex gap-4 pb-6 pl-6" data-testid={`chrono-item-${c.id}`}>
                <span className="absolute left-0 top-1.5 h-2.5 w-2.5 rounded-full border-2 border-[#F7F7F6]" style={{ backgroundColor: t[1] }} />
                <span className="absolute bottom-0 left-[5px] top-4 w-px bg-[#E5E5E3]" />
                <div className="w-24 shrink-0 pt-0.5 font-code text-[10px] text-[#52524F]">{new Date(c.maj_le).toLocaleDateString("fr-FR", { day: "2-digit", month: "short" })}</div>
                <div onClick={() => navigate(`/travaux/${c.id}`)} className="flex-1 cursor-pointer rounded-lg border border-[#E5E5E3] bg-white p-3.5 transition-colors hover:border-[#D4D4D0]">
                  <div className="flex items-center gap-2">
                    <BadgeType type={c.type} />
                    <BadgeStatut statut={c.statut} />
                    {c.a_revoir && <BadgeArevoir id={c.id} />}
                    <span className="ml-auto font-code text-[9px] text-[#71716D]">{rel(c.maj_le)}</span>
                  </div>
                  <div className="mt-1.5 text-sm font-semibold text-[#111110]">{c.titre}</div>
                  {c.objectif && <div className="mt-0.5 text-[11px] text-[#52524F]">{c.objectif}</div>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
