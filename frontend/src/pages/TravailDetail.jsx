import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, Users, ShareNetwork, DotsThree, SealCheck } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { usePerimetre } from "@/lib/perimetre";
import { TYPES_CASE } from "./Travaux";
import { numeroCase, SENSIBILITES, rel } from "@/components/case/utils";
import OngletApercu from "@/components/case/OngletApercu";
import OngletTravail from "@/components/case/OngletTravail";
import SurfacePreparation from "@/components/SurfacePreparation";
import { usePilotage } from "@/lib/pilotage";

// Deux onglets seulement : Conversation (le fil) et Aperçu (le rapport structuré)
const VUES = [
  ["travail", "Conversation"],
  ["apercu", "Aperçu"],
];

export default function TravailDetail() {
  const { cid } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const vueParam = searchParams.get("vue");
  const vue = vueParam === "apercu" ? "apercu" : "travail";
  const navigate = useNavigate();
  const { version } = usePerimetre();
  const pilote = usePilotage();
  // Démonstration : le travail est déjà né quand la page s'ouvre — aucun écran de chargement
  const [cas, setCas] = useState(() => (pilote?.lireTravail ? pilote.lireTravail(cid) : null));
  const [situations, setSituations] = useState([]);
  const [personas, setPersonas] = useState([]);
  const [erreur, setErreur] = useState(null);
  const [menu, setMenu] = useState(false);
  // Démonstration : le volet « Sources & Jumeaux » s'ouvre quand Flore a consulté des jumeaux (pas avant : il serait vide)
  const [voletSourcesOuvert, setVoletSourcesOuvert] = useState(!pilote);
  const [canvasOuvert, setCanvasOuvert] = useState(false);

  // Démonstration : le travail évolue avec le scénario (titre, résumé, rubriques de l'Aperçu).
  // Rechargement silencieux : la page et le fil ne se remontent pas.
  useEffect(() => {
    if (!pilote) return;
    api.get(`/cases/${cid}`).then((r) => setCas(r.data)).catch(() => {});
  }, [pilote?.versionTravaux]); // eslint-disable-line react-hooks/exhaustive-deps

  // Démonstration : le canvas s'ouvre quand Flore publie son document (et se ferme si on rejoue)
  useEffect(() => {
    if (!pilote) return;
    setCanvasOuvert(!!pilote.canvasOuvert);
    if (pilote.canvasOuvert) setVoletSourcesOuvert(false); // le document est dans le canvas : le volet ne le recouvre pas
  }, [pilote?.canvasOuvert]); // eslint-disable-line react-hooks/exhaustive-deps

  const nbSources = (cas?.jumeaux_participants || []).length;
  useEffect(() => {
    if (pilote && nbSources > 0 && !pilote.canvasOuvert) setVoletSourcesOuvert(true);
  }, [nbSources]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!pilote) setCas(null);
    setErreur(null);
    api.get(`/cases/${cid}`).then((r) => setCas(r.data)).catch((e) => setErreur(e.response?.data?.detail || "Travail introuvable"));
    api.get("/situations").then((r) => setSituations(r.data)).catch(() => {});
    api.get("/personas").then((r) => setPersonas(r.data)).catch(() => {});
  }, [cid, version]); // eslint-disable-line react-hooks/exhaustive-deps

  const maj = async (champs) => {
    try {
      const { data } = await api.patch(`/cases/${cid}`, champs);
      setCas((c) => ({ ...c, ...data }));
    } catch {
      toast.error("Mise à jour impossible");
    }
  };

  const nomPersona = (id) => {
    const p = personas.find((x) => x.id === id);
    return p ? `${p.nom} — ${p.role}` : id;
  };

  const partager = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      toast.success("Lien du travail copié");
    } catch {
      toast.error("Copie impossible — " + window.location.href);
    }
  };

  if (erreur) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4" data-testid="travail-erreur">
        <p className="text-sm text-[#F87171]">{erreur}</p>
        <button onClick={() => navigate("/travaux")} className="rounded-md border border-[rgba(148,163,184,0.16)] px-3 py-1.5 text-xs text-[#94A3B8] hover:text-[#F2F6F8]" data-testid="travail-erreur-retour">← Retour aux travaux</button>
      </div>
    );
  }
  if (!cas) return <div className="p-8 font-code text-[11px] text-[#7C93A8]" data-testid="travail-chargement">Chargement du travail…</div>;

  // Démonstration : un seul fil de conversation, partagé avec Flore. Il ne contient que
  // les messages déjà prononcés — aucun message futur du scénario n'est préchargé ici.
  const casVu = pilote?.conversation ? { ...cas, conversation: pilote.conversation } : cas;

  const t = TYPES_CASE[cas.type] || [cas.type, "#7C93A8"];
  const sens = SENSIBILITES[cas.sensibilite] || [cas.sensibilite || "interne", "#9B87F5"];
  const derniereEvolution = (cas.historique || []).slice(-1)[0];

  return (
    <div className="flex h-full flex-col" data-testid="travail-detail">
      {/* En-tête supérieur épuré (Style ChatGPT Work) */}
      <div className="shrink-0 border-b border-white/[0.08] bg-[#071019] px-6 py-2.5" data-testid="travail-entete">
        <div className="flex items-center justify-between gap-4">
          {/* Titre & sélecteur de vue discret */}
          <div className="flex min-w-0 items-center gap-3">
            <h1 className="truncate font-display text-sm font-semibold tracking-tight text-[#F2F6F8]" data-testid="travail-titre">
              {cas.titre} <span className="font-normal text-[#64748B]">· Travail</span>
            </h1>

            {/* Sélecteur discret Conversation / Aperçu */}
            <nav className="flex items-center rounded-lg border border-white/[0.06] bg-white/[0.02] p-0.5" data-testid="travail-vues">
              {VUES.map(([id, label]) => (
                <button
                  key={id}
                  onClick={() => setSearchParams({ vue: id }, { replace: true })}
                  data-testid={`travail-vue-${id}`}
                  className={`rounded-md px-2 py-0.5 text-[11px] font-medium transition-colors ${
                    vue === id ? "bg-white/[0.1] text-white font-semibold" : "text-[#7C93A8] hover:text-white"
                  }`}
                >
                  {label}
                </button>
              ))}
            </nav>

            {cas.a_revoir && (
              <span className="rounded border border-[#F87171]/40 bg-[#F87171]/[0.06] px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider text-[#F87171]" data-testid="travail-arevoir-entete">
                À revoir
              </span>
            )}
          </div>

          {/* Boutons d'action à droite : Partager, Menu ..., et Toggle Deux Traits (=) */}
          <div className="flex shrink-0 items-center gap-2">
            <button 
              onClick={partager} 
              data-testid="travail-partager-btn" 
              title="Partager le travail" 
              className="flex items-center gap-1.5 rounded-lg border border-white/[0.08] bg-white/[0.03] px-2.5 py-1 text-xs text-[#CBD5E1] transition-colors hover:border-white/20 hover:text-white"
            >
              <ShareNetwork size={14} />
              <span className="hidden sm:inline">Partager</span>
            </button>

            <div className="relative">
              <button 
                onClick={() => setMenu(!menu)} 
                data-testid="travail-menu-btn" 
                className="flex h-7 w-7 items-center justify-center rounded-lg border border-white/[0.08] bg-white/[0.03] text-[#7C93A8] transition-colors hover:border-white/20 hover:text-white"
              >
                <DotsThree size={16} weight="bold" />
              </button>
              {menu && (
                <div className="glass absolute right-0 top-8 z-50 w-56 rounded-xl border border-white/10 bg-[#0C1724] p-1.5 shadow-2xl backdrop-blur-xl" data-testid="travail-menu">
                  {cas.a_revoir && (
                    <button onClick={() => { setMenu(false); maj({ a_revoir: false }); }} data-testid="travail-marquer-revu-btn" className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-left text-[11px] text-[#F87171] hover:bg-white/[0.06]">
                      <SealCheck size={12} /> Marquer comme revu
                    </button>
                  )}
                  <button
                    onClick={() => { setMenu(false); maj({ statut: cas.statut === "clos" ? "en_cours" : "clos" }); }}
                    data-testid="travail-clore-btn"
                    className="w-full rounded px-2.5 py-1.5 text-left text-[11px] text-[#94A3B8] hover:bg-white/[0.06] hover:text-white"
                  >
                    {cas.statut === "clos" ? "Rouvrir le travail" : "Clore le travail"}
                  </button>
                </div>
              )}
            </div>

            {/* Icône à deux traits horizontaux pour afficher/masquer le volet Résultats & Sources */}
            {vue === "travail" && (
              <button
                onClick={() => setVoletSourcesOuvert(!voletSourcesOuvert)}
                data-testid="btn-toggle-volet-sources"
                title={voletSourcesOuvert ? "Masquer Résultats & Sources" : "Afficher Résultats & Sources"}
                className={`flex h-7 w-7 items-center justify-center rounded-lg border transition-all ${
                  voletSourcesOuvert
                    ? "border-sky-400/60 bg-sky-500/20 text-sky-200"
                    : "border-white/[0.08] bg-white/[0.03] text-[#7C93A8] hover:border-white/20 hover:text-white"
                }`}
              >
                <svg width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                  <line x1="3" y1="6.5" x2="17" y2="6.5" />
                  <line x1="3" y1="13.5" x2="17" y2="13.5" />
                </svg>
              </button>
            )}
          </div>
        </div>
      </div>

      {cas.a_revoir && (
        <div className="shrink-0 px-8 pt-4">
          <div className="mx-auto max-w-2xl">
          <div className="flex items-center justify-between gap-3 rounded-xl border border-[#F87171]/30 bg-[#F87171]/[0.04] px-4 py-3" data-testid="travail-arevoir-banner">
            <p className="text-xs text-[#F87171]">
              <span className="font-semibold uppercase tracking-wider">À revoir</span> — une connaissance du Mesh liée à ce travail a changé ; les conclusions peuvent être remises en cause.
            </p>
            <button onClick={() => maj({ a_revoir: false })} className="shrink-0 rounded-md border border-[#F87171]/40 px-2.5 py-1.5 text-[11px] font-semibold text-[#F87171] transition-colors hover:bg-[#F87171]/10">
              Marquer comme revu
            </button>
          </div>
        </div>
        </div>
      )}

      {/* Contenu de la vue — la Conversation occupe toute la hauteur, composer ancré */}
      <div className={`relative ${vue === "travail" ? "flex min-h-0 flex-1 flex-col overflow-hidden" : "flex-1 overflow-y-auto px-8 py-5"}`}>
        {/* Démonstration : la surface annonce la synthèse qu'elle prépare */}
        {pilote?.preparation?.surface === "travail" && <SurfacePreparation preparation={pilote.preparation} testid="travail-preparation" />}
        {vue === "travail" ? (
          <OngletTravail 
            cas={casVu} 
            setCas={setCas} 
            voletSourcesOuvert={voletSourcesOuvert}
            setVoletSourcesOuvert={setVoletSourcesOuvert}
            canvasOuvert={canvasOuvert}
            setCanvasOuvert={setCanvasOuvert}
          />
        ) : (
        <div className="mx-auto max-w-6xl">
          {vue === "apercu" && <OngletApercu cas={casVu} maj={maj} setCas={setCas} situations={situations} />}
        </div>
        )}
      </div>
    </div>
  );
}
