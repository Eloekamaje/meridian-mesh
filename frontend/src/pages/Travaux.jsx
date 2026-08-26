import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, MagnifyingGlass, Rows, Kanban as KanbanIcon, ClockCounterClockwise, X, DotsThree, ArrowRight, Compass, CaretDown, Flag } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import { usePerimetre } from "@/lib/perimetre";
import { useContexte } from "@/lib/contexte";
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

// Un travail tient sur une ligne dense : titre, intention, signal, fraîcheur — actions au survol
function CarteTravail({ c, navigate, setSelection, attention }) {
  const [menu, setMenu] = useState(false);
  const s = STATUTS_CASE[c.statut] || [c.statut, "#71716D"];

  return (
    <div
      onClick={() => navigate(`/travaux/${c.id}`)}
      className={`group relative flex cursor-pointer items-center gap-3 rounded-lg border-b border-[#E5E5E3] px-2 py-2.5 transition-colors last:border-b-0 hover:bg-white ${attention ? "border-l-2 border-l-[#B45309]/60" : ""}`}
      data-testid={`travail-row-${c.id}`}
    >
      <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: s[1] }} title={s[0]} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="truncate text-sm font-medium text-[#111110]">{c.titre}</span>
          {c.a_revoir && (
            <span className="shrink-0 rounded border border-[#B91C1C]/40 bg-[#B91C1C]/[0.06] px-1.5 py-px font-code text-[9px] uppercase tracking-wider text-[#B91C1C]" data-testid={`travail-arevoir-${c.id}`}>À revoir</span>
          )}
          {(c.nb_options_a_trancher || 0) > 0 && (
            <span className="flex shrink-0 items-center gap-1 rounded border border-[#6D28D9]/30 bg-[#6D28D9]/[0.06] px-1.5 py-px font-code text-[9px] text-[#6D28D9]">
              <Flag size={9} /> {c.nb_options_a_trancher} décision{c.nb_options_a_trancher > 1 ? "s" : ""}
            </span>
          )}
        </div>
        <div className="flex items-baseline gap-2">
          {(c.nb_nouveautes || 0) > 0 ? (
            <p className="truncate text-[11px] text-[#047857]" data-testid={`travail-nouveau-${c.id}`}>
              <span className="mr-1 inline-block h-1 w-1 rounded-full bg-[#047857]" />
              Nouveau depuis votre dernière visite : {c.nouveaute_texte}
            </p>
          ) : (
            <p className="truncate text-[11px] text-[#71716D]">{c.objectif || c.resume || "La mémoire s'écrit au fil des échanges."}</p>
          )}
        </div>
      </div>
      <span className="shrink-0 font-code text-[9px] text-[#71716D]" title={`${TYPES_CASE[c.type]?.[0] || c.type} · ${s[0]} · ${c.jumeaux?.length || 0} jumeaux`}>{rel(c.maj_le)}</span>
      <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
        <button
          onClick={(e) => { e.stopPropagation(); navigate(`/travaux/${c.id}`); }}
          data-testid={`travail-continuer-${c.id}`}
          className="flex items-center gap-1 rounded-md bg-[#3730A3] px-2.5 py-1 text-[11px] font-semibold text-white transition-colors hover:bg-[#4338CA]"
        >
          Continuer <ArrowRight size={10} />
        </button>
        <button onClick={(e) => { e.stopPropagation(); setMenu((m) => !m); }} data-testid={`travail-menu-${c.id}`} title="Autres actions" className="flex h-6 w-6 items-center justify-center rounded-md border border-[#E5E5E3] bg-white text-[#71716D] transition-colors hover:text-[#111110]">
          <DotsThree size={14} weight="bold" />
        </button>
      </div>
      {menu && (
        <div className="glass absolute right-2 top-9 z-30 w-52 rounded-xl p-1.5" data-testid={`travail-menu-panel-${c.id}`} onClick={(e) => e.stopPropagation()}>
          <button onClick={() => navigate(`/travaux/${c.id}?vue=activite`)} data-testid={`travail-apercu-${c.id}`} className="w-full rounded px-2.5 py-1.5 text-left text-[11px] text-[#52524F] hover:bg-[#F0F0EE] hover:text-[#111110]">
            Reprendre là où vous étiez
          </button>
          <button onClick={() => { setSelection(c.jumeaux || []); navigate("/atlas"); }} data-testid={`travail-atlas-${c.id}`} className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-left text-[11px] text-[#52524F] hover:bg-[#F0F0EE] hover:text-[#111110]">
            <Compass size={12} /> Voir dans l'Atlas
          </button>
          <p className="border-t border-[#F0F0EE] px-2.5 pt-1.5 font-code text-[9px] text-[#71716D]">
            {numeroCase(c)} · {TYPES_CASE[c.type]?.[0] || c.type} · {c.jumeaux?.length || 0} jumeau{(c.jumeaux?.length || 0) > 1 ? "x" : ""}
          </p>
        </div>
      )}
    </div>
  );
}

export default function Travaux() {
  const [cases, setCases] = useState([]);
  const [vue, setVue] = useState("liste");
  const [vuesMenu, setVuesMenu] = useState(false);
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
  const { setSelection } = useContexte();
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/cases").then((r) => setCases(r.data)).catch(() => {});
    api.get("/personas").then((r) => setPersonas(r.data)).catch(() => {});
    if (new URLSearchParams(window.location.search).get("nouveau")) setCreation(true);
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

  // Regroupement par signification : attention / progrès / le reste
  const sections = useMemo(() => {
    const attention = filtres.filter((c) => c.a_revoir || (c.nb_options_a_trancher || 0) > 0);
    const progres = filtres.filter((c) => !attention.includes(c) && (c.nb_nouveautes || 0) > 0);
    const autres = filtres.filter((c) => !attention.includes(c) && !progres.includes(c));
    return [
      ["attention", "Ce qui attend votre attention", attention],
      ["progres", "Ce qui a progressé sans vous", progres],
      ["autres", "Tous les travaux", autres],
    ].filter(([, , l]) => l.length);
  }, [filtres]);

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
    <div className="h-full overflow-y-auto px-6 py-8 pb-20 sm:px-8" data-testid="travaux-page">
      <div className="mx-auto max-w-4xl">
        <header className="rise">
          <div className="font-code text-[10px] uppercase tracking-[0.3em] text-[#3730A3]">Travaux</div>
          <div className="mt-1 flex flex-wrap items-center justify-between gap-3">
            <h1 className="font-display text-xl font-black tracking-tight text-[#111110]" data-testid="travaux-titre">La mémoire de ce que l'entreprise cherche à comprendre</h1>
            <div className="flex items-center gap-2">
              <div className="relative">
                <MagnifyingGlass size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#71716D]" />
                <input value={recherche} onChange={(e) => setRecherche(e.target.value)} placeholder="Rechercher un travail…" data-testid="recherche-travail"
                  className="h-8 w-48 rounded-md border border-[#E5E5E3] bg-white pl-7 pr-3 text-xs text-[#111110] placeholder:text-[#71716D] focus:border-[#3730A3]/60 focus:outline-none" />
              </div>
              <div className="relative">
                <button onClick={() => setVuesMenu((v) => !v)} data-testid="travaux-vues" className="flex h-8 items-center gap-1.5 rounded-md border border-[#E5E5E3] bg-white px-2.5 text-xs text-[#52524F] transition-colors hover:text-[#111110]">
                  {vue === "liste" ? <Rows size={13} /> : vue === "kanban" ? <KanbanIcon size={13} /> : <ClockCounterClockwise size={13} />}
                  <span className="hidden lg:inline">{vue === "liste" ? "Récits" : vue === "kanban" ? "Kanban" : "Chronologie"}</span>
                  <CaretDown size={10} />
                </button>
                {vuesMenu && (
                  <div className="glass absolute right-0 top-9 z-30 w-44 rounded-xl p-1.5" data-testid="vues-menu">
                    {[["liste", Rows, "Récits"], ["kanban", KanbanIcon, "Kanban"], ["chrono", ClockCounterClockwise, "Chronologie"]].map(([v, Icon, label]) => (
                      <button key={v} onClick={() => { setVue(v); setVuesMenu(false); }} data-testid={`vue-${v}`}
                        className={`flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-left text-[11px] ${vue === v ? "bg-[#EEECFA] font-semibold text-[#312E81]" : "text-[#52524F] hover:bg-[#F0F0EE] hover:text-[#111110]"}`}>
                        <Icon size={13} /> {label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <button onClick={() => setMesSeulement(!mesSeulement)} data-testid="filtre-mes-travaux"
                className={`h-8 rounded-full border px-3 text-xs transition-colors ${mesSeulement ? "border-[#3730A3] bg-[#3730A3] text-white" : "border-[#E5E5E3] bg-white text-[#52524F] hover:text-[#111110]"}`}>
                Mes travaux
              </button>
              <select value={filtreType} onChange={(e) => setFiltreType(e.target.value)} data-testid="filtre-type-travail" className="h-8 rounded-md border border-[#E5E5E3] bg-white px-2 text-xs text-[#3F3F3C] focus:outline-none">
                <option value="tous" label="Tous les types" />
                {Object.entries(TYPES_CASE).map(([k, [l]]) => <option key={k} value={k} label={l} />)}
              </select>
              <select value={filtreStatut} onChange={(e) => setFiltreStatut(e.target.value)} data-testid="filtre-statut-travail" className="h-8 rounded-md border border-[#E5E5E3] bg-white px-2 text-xs text-[#3F3F3C] focus:outline-none">
                <option value="tous" label="Tous les statuts" />
                {Object.entries(STATUTS_CASE).map(([k, [l]]) => <option key={k} value={k} label={l} />)}
              </select>
              <button onClick={() => setCreation(!creation)} data-testid="nouveau-travail-btn" title="Nouveau travail" className="flex h-8 w-8 items-center justify-center rounded-md bg-[#3730A3] text-white transition-colors hover:bg-[#4338CA]">
                {creation ? <X size={14} /> : <Plus size={14} weight="bold" />}
              </button>
            </div>
          </div>
          <p className="mt-1 font-code text-[10px] text-[#71716D]">{filtres.length} travail{filtres.length > 1 ? "aux" : ""} · la conversation est le contenu, la liste est l'index</p>
        </header>

        {/* Création inline */}
        {creation && (
          <div className="rise mt-5 rounded-xl border border-[#3730A3]/25 bg-[#EEECFA] p-5" data-testid="travail-form">
            <div className="grid gap-3 md:grid-cols-2">
              <input value={form.titre} onChange={(e) => setForm({ ...form, titre: e.target.value })} placeholder="Titre du travail — ex. Peut-on proposer le paiement différé aux clients professionnels ?" data-testid="travail-titre-input"
                className="rounded-md border border-[#E5E5E3] bg-white px-3 py-2.5 text-sm text-[#111110] placeholder:text-[#71716D] focus:border-[#3730A3]/60 focus:outline-none md:col-span-2" />
              <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} data-testid="travail-type-select" className="rounded-md border border-[#E5E5E3] bg-white px-3 py-2.5 text-sm text-[#111110] focus:outline-none">
                {Object.entries(TYPES_CASE).map(([k, [l]]) => <option key={k} value={k} label={l} />)}
              </select>
              <select value={form.responsable || ""} onChange={(e) => setForm({ ...form, responsable: e.target.value || undefined })} data-testid="travail-responsable-select" className="rounded-md border border-[#E5E5E3] bg-white px-3 py-2.5 text-sm text-[#111110] focus:outline-none">
                <option value="" label="Responsable : moi" />
                {personas.map((p) => <option key={p.id} value={p.id} label={`${p.nom} — ${p.role}`} />)}
              </select>
              <input value={form.objectif} onChange={(e) => setForm({ ...form, objectif: e.target.value })} placeholder="Intention — que cherche-t-on à comprendre ou accomplir ?" data-testid="travail-objectif-input"
                className="rounded-md border border-[#E5E5E3] bg-white px-3 py-2.5 text-sm text-[#111110] placeholder:text-[#71716D] focus:border-[#3730A3]/60 focus:outline-none" />
            </div>
            <div className="mt-3">
              <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#52524F]">Jumeaux à mobiliser</div>
              <div className="mt-1.5 flex flex-wrap gap-1.5" data-testid="travail-jumeaux-select">
                {(mesh?.jumeaux || []).filter((j) => !j.anonyme).map((j) => {
                  const actif = form.jumeaux.includes(j.id);
                  return (
                    <button key={j.id} onClick={() => setForm({ ...form, jumeaux: actif ? form.jumeaux.filter((x) => x !== j.id) : [...form.jumeaux, j.id] })} data-testid={`travail-jumeau-${j.id}`}
                      className={`rounded-full border px-2.5 py-1 font-code text-[10px] transition-colors ${actif ? "border-[#3730A3]/60 bg-[#3730A3]/15 text-white" : "border-[#E5E5E3] text-[#52524F] hover:text-[#111110]"}`}>
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

        {filtres.length === 0 && (
          <p className="mt-12 text-center text-sm text-[#71716D]" data-testid="travaux-vide">Aucun travail dans ce périmètre — conservez-en un depuis une conversation avec Flore.</p>
        )}

        {/* Vue récits — mémoire narrative regroupée par signification */}
        {vue === "liste" && filtres.length > 0 && (
          <div className="mt-4 space-y-6" data-testid="travaux-liste">
            {sections.map(([id, titre, liste]) => (
              <section key={id} data-testid={`travaux-section-${id}`}>
                <h2 className="font-code text-[10px] uppercase tracking-[0.25em] text-[#52524F]">{titre}</h2>
                <div className="mt-1.5">
                  {liste.map((c) => (
                    <CarteTravail key={c.id} c={c} navigate={navigate} setSelection={setSelection} attention={id === "attention"} />
                  ))}
                </div>
              </section>
            ))}
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
                            {c.a_revoir && <span className="rounded border border-[#B91C1C]/40 bg-[#B91C1C]/[0.06] px-1.5 py-0.5 font-code text-[9px] uppercase text-[#B91C1C]">À revoir</span>}
                          </div>
                        </div>
                        <div className="mt-2"><ChipsJumeaux ids={c.jumeaux} /></div>
                        <div className="mt-2 flex items-center justify-between font-code text-[9px] text-[#71716D]">
                          <span>{c.nb_decisions} décision{c.nb_decisions > 1 ? "s" : ""} · {c.nb_messages} msg</span>
                          <span>{rel(c.maj_le)}</span>
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
          <div className="mt-6" data-testid="travaux-chrono">
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
    </div>
  );
}
