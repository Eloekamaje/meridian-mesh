import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, HourglassMedium, MagnifyingGlass, DotsThree, Sparkle } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { usePerimetre } from "@/lib/perimetre";
import { useContexte } from "@/lib/contexte";
import { couleurDomaine } from "@/lib/domaines";
import { STATUTS, STRATE_LABELS, FRAICHEUR_ETATS, AUTONOMIE, STATUTS_SOURCES, ACTION_LIGNE, qualifConnaissance, resumeStrates, estEnAttention } from "@/lib/jumeaux";
import ComposerFlore from "@/components/ComposerFlore";

const VUES_ENREGISTREES = [
  ["tous", "Tous les jumeaux"],
  ["paiement", "Jumeaux de Paiement"],
  ["admettre", "À admettre"],
  ["connaissance", "Connaissance insuffisante"],
  ["sources-erreur", "Sources en erreur"],
  ["obsoletes", "Jumeaux obsolètes"],
];

export default function Jumeaux() {
  const [jumeaux, setJumeaux] = useState([]);
  const [brouillons, setBrouillons] = useState([]);
  const { version } = usePerimetre();
  const { selection, ajouterJumeau, retirerJumeau } = useContexte();
  const navigate = useNavigate();
  const [recherche, setRecherche] = useState("");
  const [filtreStatut, setFiltreStatut] = useState("tous");
  const [filtreDomaine, setFiltreDomaine] = useState("");
  const [filtreProprio, setFiltreProprio] = useState("");
  const [filtreAutonomie, setFiltreAutonomie] = useState("");
  const [vue, setVue] = useState("tous");
  const [menuOuvert, setMenuOuvert] = useState(null);
  const [suggestionMasquee, setSuggestionMasquee] = useState(false);

  // Suggestion locale de Flore : un jumeau dont la connaissance vieillit
  const suggestionFlore = useMemo(() => {
    if (suggestionMasquee) return null;
    const j = (jumeaux || []).find((x) => x.fraicheur_etat === "ancienne" && x.statut === "actif") || (jumeaux || []).find((x) => x.statut === "observation");
    if (!j) return null;
    return {
      jumeau: j.id,
      texte: `${j.nom} manque de connaissances fraîches — ${j.fraicheur_etat === "ancienne" ? "ses preuves vieillissent" : "sa phase d'observation est en cours"}${(j.sources_detail || []).some((s) => s.statut !== "prete") ? " et une source est en retard" : ""}.`,
      question: `Pourquoi le jumeau ${j.nom} manque-t-il de connaissances fraîches, et que faire ?`,
    };
  }, [jumeaux, suggestionMasquee]);

  const charger = () => api.get("/jumeaux").then((r) => setJumeaux(r.data)).catch(() => {});
  useEffect(() => {
    charger();
    api.get("/commandes").then((r) => setBrouillons(r.data)).catch(() => {});
  }, [version]);

  const commander = async () => {
    try {
      const { data } = await api.post("/commandes", {});
      navigate(`/commande/${data.id}`);
    } catch {
      toast.error("Création de la commande impossible");
    }
  };

  const appliquerVue = (v) => {
    setVue(v);
    setFiltreStatut("tous");
    setFiltreDomaine("");
    setFiltreProprio("");
    setFiltreAutonomie("");
    if (v === "paiement") setFiltreDomaine("Paiement");
    if (v === "admettre") setFiltreStatut("observation");
  };

  const domaines = useMemo(() => [...new Set(jumeaux.map((j) => j.domaine))].sort(), [jumeaux]);
  const proprios = useMemo(() => [...new Set(jumeaux.map((j) => j.proprietaire).filter(Boolean))].sort(), [jumeaux]);

  const filtres = useMemo(() => {
    const q = recherche.trim().toLowerCase();
    return jumeaux.filter((j) => {
      if (filtreStatut === "attention" ? !estEnAttention(j) : filtreStatut !== "tous" && j.statut !== filtreStatut) return false;
      if (filtreDomaine && j.domaine !== filtreDomaine) return false;
      if (filtreProprio && j.proprietaire !== filtreProprio) return false;
      if (filtreAutonomie && j.autonomie !== filtreAutonomie) return false;
      if (vue === "connaissance" && (j.couverture ?? 100) >= 60) return false;
      if (vue === "sources-erreur" && !(j.sources_detail || []).some((s) => s.statut !== "prete")) return false;
      if (vue === "obsoletes" && !["retard", "obsolete"].includes(j.fraicheur_etat)) return false;
      if (q && ![j.nom, j.mission, j.proprietaire, j.domaine].join(" ").toLowerCase().includes(q)) return false;
      return true;
    });
  }, [jumeaux, recherche, filtreStatut, filtreDomaine, filtreProprio, filtreAutonomie, vue]);

  // Liste plate : le domaine devient une colonne (le filtre domaine existe déjà)
  const lignes = useMemo(
    () => [...filtres].sort((a, b) => Number(estEnAttention(b)) - Number(estEnAttention(a)) || (a.couverture ?? 0) - (b.couverture ?? 0)),
    [filtres]
  );

  const compteurs = useMemo(() => ({
    actifs: jumeaux.filter((j) => j.statut === "actif").length,
    construction: jumeaux.filter((j) => j.statut === "en construction").length,
    observation: jumeaux.filter((j) => j.statut === "observation").length,
    attention: jumeaux.filter(estEnAttention).length,
  }), [jumeaux]);

  const CHIPS = [["tous", "Tous"], ["actif", "Actifs"], ["en construction", "Construction"], ["observation", "Observation"], ["attention", "Attention"]];

  return (
    <div className="h-full overflow-y-auto px-4 py-5 pb-44 sm:px-8 sm:py-8 lg:px-12" data-testid="jumeaux-page">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-code text-[10px] uppercase tracking-[0.3em] text-[#60A5FA]">Parc de jumeaux</p>
          <h1 className="mt-1 font-display text-2xl font-black tracking-tight text-[#F2F6F8] sm:text-3xl">Registre des jumeaux</h1>
          <p className="mt-1 max-w-xl text-sm text-[#94A3B8]">
            Consultez les jumeaux de votre périmètre, leur niveau de connaissance, leurs sources et leur état d'admission.
          </p>
          <p className="mt-2 font-code text-[10px] text-[#7C93A8]" data-testid="registre-compteurs">
            {compteurs.actifs} actifs · {compteurs.construction} en construction · {compteurs.observation} en observation · <span className={compteurs.attention ? "text-[#F2B84B]" : ""}>{compteurs.attention} à traiter</span>
          </p>
        </div>
        <button onClick={commander} data-testid="commander-jumeau-btn" className="flex items-center gap-2 rounded-md bg-[#60A5FA] px-4 py-2.5 text-sm font-semibold text-[#071019] transition-colors hover:bg-[#93C5FD]">
          <Plus size={16} weight="bold" /> Commander un jumeau
        </button>
      </header>

      {brouillons.length > 0 && (
        <div className="rise mt-5 flex flex-wrap gap-2" data-testid="commandes-en-cours">
          {brouillons.map((c) => (
            <button key={c.id} onClick={() => navigate(`/commande/${c.id}`)} data-testid={`reprendre-${c.id}`} className="flex items-center gap-2 rounded-lg border border-[#F2B84B]/25 bg-[#F2B84B]/[0.04] px-3 py-2 text-left transition-colors hover:border-[#F2B84B]/50">
              <HourglassMedium size={14} className="text-[#F2B84B]" />
              <div>
                <div className="text-xs font-semibold text-[#F2F6F8]">Commande en cours — {c.jumeau?.nom || "sans nom"}</div>
                <div className="font-code text-[9px] text-[#7C93A8]">étape {c.etape}/4 · {c.sources?.length || 0} source(s) · reprendre →</div>
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Outils de gestion à grande échelle */}
      <div className="mt-5 flex flex-wrap items-center gap-2" data-testid="registre-outils">
        <div className="relative w-full sm:w-auto">
          <MagnifyingGlass size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#7C93A8]" />
          <input value={recherche} onChange={(e) => setRecherche(e.target.value)} placeholder="Rechercher un jumeau…" data-testid="registre-recherche" className="w-full sm:w-56 rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] py-1.5 pl-8 pr-3 text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/50 focus:outline-none" />
        </div>
        <div className="flex max-w-full overflow-x-auto rounded-md border border-[rgba(148,163,184,0.16)]">
          {CHIPS.map(([v, l]) => (
            <button key={v} onClick={() => setFiltreStatut(v)} data-testid={`chip-${v}`} className={`px-2.5 py-1.5 text-[11px] transition-colors ${filtreStatut === v ? "bg-[#60A5FA]/15 text-[#60A5FA]" : "text-[#94A3B8] hover:text-[#F2F6F8]"}`}>
              {l}
            </button>
          ))}
        </div>
        <select value={filtreDomaine} onChange={(e) => setFiltreDomaine(e.target.value)} data-testid="filtre-domaine" className="min-w-[8rem] flex-1 rounded-md sm:flex-none border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2 py-1.5 text-xs text-[#D8E2EA] focus:outline-none">
          <option value="">Domaine ▾</option>
          {domaines.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
        <select value={filtreProprio} onChange={(e) => setFiltreProprio(e.target.value)} data-testid="filtre-proprietaire" className="min-w-[8rem] flex-1 rounded-md sm:flex-none border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2 py-1.5 text-xs text-[#D8E2EA] focus:outline-none">
          <option value="">Propriétaire ▾</option>
          {proprios.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <select value={filtreAutonomie} onChange={(e) => setFiltreAutonomie(e.target.value)} data-testid="filtre-autonomie" className="min-w-[8rem] flex-1 rounded-md sm:flex-none border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2 py-1.5 text-xs text-[#D8E2EA] focus:outline-none">
          <option value="">Autonomie ▾</option>
          {Object.entries(AUTONOMIE).map(([v, [l]]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <select value={vue} onChange={(e) => appliquerVue(e.target.value)} data-testid="registre-vues" className="min-w-[8rem] flex-1 rounded-md sm:flex-none border border-[#60A5FA]/30 bg-[#60A5FA]/[0.06] px-2 py-1.5 text-xs text-[#60A5FA] focus:outline-none">
          {VUES_ENREGISTREES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>

      {/* Registre — liste plate, domaine en colonne */}
      <div className="mt-4 overflow-hidden rounded-xl border border-[rgba(148,163,184,0.16)]" data-testid="registre-table">
        {lignes.map((j) => {
          const st = STATUTS[j.statut] || [j.statut, "#7C93A8"];
          const fr = FRAICHEUR_ETATS[j.fraicheur_etat] || FRAICHEUR_ETATS.partiel;
          const aut = AUTONOMIE[j.autonomie] || AUTONOMIE.aucune;
          const det = j.sources_detail || [];
          const nbOk = det.filter((s) => s.statut === "prete").length;
          const ko = det.filter((s) => s.statut !== "prete");
          const attention = estEnAttention(j);
          const coche = selection.includes(j.id);
          return (
            <div
              key={j.id}
              onClick={() => navigate(`/jumeaux/${j.id}/revue`)}
              data-testid={`jumeau-row-${j.id}`}
              className={`glow-hover rise flex cursor-pointer items-center gap-2 border-b border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-4 py-3 transition-colors last:border-b-0 hover:bg-[rgba(148,163,184,0.07)] ${attention ? "border-l-2 border-l-[#F2B84B]/60" : "border-l-2 border-l-transparent"}`}
            >
              <input
                type="checkbox"
                checked={coche}
                onClick={(e) => e.stopPropagation()}
                onChange={() => (coche ? retirerJumeau(j.id) : ajouterJumeau(j.id))}
                data-testid={`registre-check-${j.id}`}
                title="Ajouter au contexte de Flore"
                className="h-3.5 w-3.5 shrink-0 accent-[#60A5FA]"
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate text-[13px] font-medium text-[#F2F6F8]">{j.nom}</span>
                  {attention && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[#F2B84B]" title="Nécessite une attention" />}
                </div>
                <div className="truncate font-code text-[9px] text-[#7C93A8]">{j.proprietaire || "—"}</div>
                <div className="truncate font-code text-[9px] text-[#94A3B8] lg:hidden">{j.domaine} · {j.couverture} % · {nbOk}/{det.length} prêtes</div>
              </div>
              {/* Domaine en colonne */}
              <span
                className="hidden w-28 shrink-0 truncate rounded border px-1.5 py-0.5 text-center font-code text-[9px] sm:block"
                style={{ color: couleurDomaine(j.domaine), borderColor: `${couleurDomaine(j.domaine)}44`, backgroundColor: `${couleurDomaine(j.domaine)}0D` }}
                data-testid={`domaine-${j.id}`}
              >
                {j.domaine}
              </span>
                  <span className="hidden w-24 shrink-0 rounded border px-1.5 py-0.5 text-center font-code text-[9px] md:block" style={{ color: st[1], borderColor: `${st[1]}44`, backgroundColor: `${st[1]}12` }} data-testid={`statut-${j.id}`}>
                    {st[0]}
                  </span>
                  {/* Connaissance : score + qualification + strates au survol */}
                  <div className="group relative hidden w-40 shrink-0 lg:block" data-testid={`connaissance-${j.id}`}>
                    <div className="font-code text-[11px] text-[#F2F6F8]">{j.couverture} % · {qualifConnaissance(j.couverture)}</div>
                    <div className="truncate font-code text-[9px] text-[#7C93A8]">{resumeStrates(j)}</div>
                    <div className="pointer-events-none absolute -top-2 left-0 z-50 w-52 -translate-y-full rounded-lg border border-[rgba(148,163,184,0.16)] bg-[#0F1D28]/95 p-3 opacity-0 backdrop-blur-xl transition-opacity duration-150 group-hover:opacity-100" data-testid={`connaissance-tip-${j.id}`}>
                      <div className="font-code text-[9px] uppercase tracking-[0.15em] text-[#7C93A8]">Strates de connaissance</div>
                      {Object.entries(STRATE_LABELS).map(([k, l]) => (
                        <div key={k} className="mt-1 flex items-center justify-between font-code text-[10px]">
                          <span className="text-[#94A3B8]">{l}</span>
                          <span className="text-[#F2F6F8]">{j.strates?.[k] ?? "—"} %</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  {/* Fraîcheur qualifiée */}
                  <div className="hidden w-44 shrink-0 xl:block" data-testid={`fraicheur-${j.id}`}>
                    <div className="font-code text-[11px]" style={{ color: fr[1] }}>{fr[0]}</div>
                    <div className="truncate font-code text-[9px] text-[#7C93A8]" title={`Dernière connaissance : ${j.fraicheur}`}>Dernière connaissance : {j.fraicheur}</div>
                  </div>
                  {/* Autonomie contextualisée */}
                  <div className="hidden w-36 shrink-0 xl:block" title={`${aut[0]} — ${aut[1]}`} data-testid={`autonomie-${j.id}`}>
                    <div className="font-code text-[11px]" style={{ color: aut[2] }}>{aut[0]}</div>
                    <div className="truncate font-code text-[9px] text-[#7C93A8]">{aut[1]}</div>
                  </div>
                  {/* Sources : N/M prêtes + détail au survol */}
                  <div className="group relative hidden w-24 shrink-0 lg:block" data-testid={`sources-${j.id}`}>
                    <div className={`font-code text-[11px] ${ko.length ? "text-[#F87171]" : "text-[#34D399]"}`}>{nbOk}/{det.length} prêtes</div>
                    {ko.length > 0 && <div className="truncate font-code text-[9px] text-[#F87171]/80">{ko.length} {ko[0] && STATUTS_SOURCES[ko[0].statut]?.[0]}</div>}
                    <div className="pointer-events-none absolute -top-2 right-0 z-50 w-52 -translate-y-full rounded-lg border border-[rgba(148,163,184,0.16)] bg-[#0F1D28]/95 p-3 opacity-0 backdrop-blur-xl transition-opacity duration-150 group-hover:opacity-100" data-testid={`sources-tip-${j.id}`}>
                      {det.map((s) => {
                        const ss = STATUTS_SOURCES[s.statut] || [s.statut, "#7C93A8"];
                        return (
                          <div key={s.cle} className="mt-1 flex items-center justify-between font-code text-[10px]">
                            <span className="text-[#94A3B8]">{s.nom}</span>
                            <span style={{ color: ss[1] }}>{ss[0]}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                  {/* Action contextuelle + menu secondaire */}
                  <div className="flex shrink-0 items-center justify-end gap-1.5 md:w-48">
                    <button
                      onClick={(e) => { e.stopPropagation(); navigate(`/jumeaux/${j.id}/revue`); }}
                      data-testid={j.statut === "observation" ? `revoir-admission-${j.id}` : `examiner-${j.id}`}
                      className={`hidden rounded px-2.5 py-1 text-[11px] transition-colors sm:block ${j.statut === "observation" ? "bg-[#F2B84B] font-semibold text-[#071019] hover:bg-[#F8CF7A]" : "border border-[rgba(148,163,184,0.16)] text-[#94A3B8] hover:border-[#41576D] hover:text-[#F2F6F8]"}`}
                    >
                      {ACTION_LIGNE[j.statut] || "Ouvrir"}
                    </button>
                    <div className="relative">
                      <button onClick={(e) => { e.stopPropagation(); setMenuOuvert(menuOuvert === j.id ? null : j.id); }} data-testid={`menu-${j.id}`} className="rounded p-1 text-[#7C93A8] transition-colors hover:text-[#F2F6F8]">
                        <DotsThree size={16} weight="bold" />
                      </button>
                      {menuOuvert === j.id && (
                        <>
                          <div className="fixed inset-0 z-40" onClick={(e) => { e.stopPropagation(); setMenuOuvert(null); }} />
                          <div className="absolute right-0 top-7 z-50 w-48 rounded-lg border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-1 shadow-xl" data-testid={`menu-panel-${j.id}`}>
                            <button onClick={(e) => { e.stopPropagation(); setMenuOuvert(null); navigate(`/atlas?focus=${j.id}`); }} className="w-full rounded px-2.5 py-1.5 text-left text-[11px] text-[#94A3B8] hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]" data-testid={`menu-atlas-${j.id}`}>
                              Centrer dans l'Atlas
                            </button>
                            <button onClick={(e) => { e.stopPropagation(); setMenuOuvert(null); window.dispatchEvent(new CustomEvent("meridian:flore-ask", { detail: `Parle-moi du jumeau ${j.nom}` })); }} className="w-full rounded px-2.5 py-1.5 text-left text-[11px] text-[#94A3B8] hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]" data-testid={`menu-flore-${j.id}`}>
                              Demander à Flore
                            </button>
                            <button onClick={async (e) => { e.stopPropagation(); setMenuOuvert(null); try { await navigator.clipboard.writeText(j.id); toast.success("Identifiant copié"); } catch { toast.error("Copie impossible — identifiant : " + j.id); } }} className="w-full rounded px-2.5 py-1.5 text-left text-[11px] text-[#94A3B8] hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]" data-testid={`menu-copier-${j.id}`}>
                              Copier l'identifiant
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
            </div>
          );
        })}
        {filtres.length === 0 && (
          <div className="px-4 py-10 text-center text-sm text-[#7C93A8]" data-testid="registre-vide">Aucun jumeau ne correspond — élargissez la recherche ou les filtres.</div>
        )}
      </div>

      {/* Suggestion de Flore — locale, discrète, ignorable */}
      {suggestionFlore && (
        <div className="mt-4 flex items-center justify-between gap-3 rounded-xl border border-[#60A5FA]/20 bg-[rgba(96,165,250,0.12)] px-4 py-3" data-testid="registre-suggestion-flore">
          <p className="text-xs leading-snug text-[#D8E2EA]">
            <Sparkle size={12} weight="fill" className="mr-1.5 inline text-[#60A5FA]" />
            <span className="font-semibold text-[#BFDBFE]">Suggestion de Flore — </span>
            {suggestionFlore.texte}
          </p>
          <div className="flex shrink-0 gap-1.5">
            <button onClick={() => window.dispatchEvent(new CustomEvent("meridian:flore-ask", { detail: suggestionFlore.question }))} data-testid="suggestion-comprendre-btn" className="rounded-md bg-[#60A5FA] px-2.5 py-1.5 text-[11px] font-semibold text-[#071019] transition-colors hover:bg-[#93C5FD]">
              Comprendre
            </button>
            <button onClick={() => navigate(`/jumeaux/${suggestionFlore.jumeau}/revue`)} data-testid="suggestion-examiner-btn" className="rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2.5 py-1.5 text-[11px] text-[#94A3B8] transition-colors hover:text-[#F2F6F8]">
              Examiner
            </button>
            <button onClick={() => setSuggestionMasquee(true)} data-testid="suggestion-ignorer-btn" title="Masquer la suggestion" className="rounded-md px-2 py-1.5 text-[11px] text-[#7C93A8] transition-colors hover:text-[#F2F6F8]">
              ×
            </button>
          </div>
        </div>
      )}
        {/* Composer compact — contextualisé au registre */}
        <div className="mt-4" data-testid="jumeaux-composer-zone">
          <ComposerFlore compact placeholder="Interrogez le registre…" testidPrefix="jumeaux-composer" />
        </div>

    </div>
  );
}
