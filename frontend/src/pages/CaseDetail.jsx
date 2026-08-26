import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, Compass, Sparkle, Users, ShareNetwork, DotsThree, SealCheck } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import { usePerimetre } from "@/lib/perimetre";
import { useContexte } from "@/lib/contexte";
import { TYPES_CASE, STATUTS_CASE } from "./Cases";
import { numeroCase, SENSIBILITES, rel } from "@/components/case/utils";
import OngletApercu from "@/components/case/OngletApercu";
import OngletTravail from "@/components/case/OngletTravail";
import OngletAtlas from "@/components/case/OngletAtlas";
import OngletDecisions from "@/components/case/OngletDecisions";
import OngletActivite from "@/components/case/OngletActivite";

const VUES = [
  ["apercu", "Aperçu"],
  ["travail", "Travail"],
  ["atlas", "Atlas"],
  ["decisions", "Décisions & actions"],
  ["activite", "Activité"],
];

export default function CaseDetail() {
  const { cid } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const vue = searchParams.get("vue") || "apercu";
  const navigate = useNavigate();
  const { mesh } = useMesh();
  const { version } = usePerimetre();
  const { setSelection, ouvrirFlore } = useContexte();
  const [cas, setCas] = useState(null);
  const [situations, setSituations] = useState([]);
  const [personas, setPersonas] = useState([]);
  const [erreur, setErreur] = useState(null);
  const [menu, setMenu] = useState(false);

  useEffect(() => {
    setCas(null);
    setErreur(null);
    api.get(`/cases/${cid}`).then((r) => setCas(r.data)).catch((e) => setErreur(e.response?.data?.detail || "Case introuvable"));
    api.get("/situations").then((r) => setSituations(r.data)).catch(() => {});
    api.get("/personas").then((r) => setPersonas(r.data)).catch(() => {});
  }, [cid, version]);

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

  const continuerFlore = () => {
    setSelection(cas.jumeaux || []);
    ouvrirFlore();
  };

  const ouvrirAtlas = () => {
    setSelection(cas.jumeaux || []);
    navigate("/atlas");
  };

  const partager = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      toast.success("Lien du case copié");
    } catch {
      toast.error("Copie impossible — " + window.location.href);
    }
  };

  if (erreur) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4" data-testid="case-erreur">
        <p className="text-sm text-[#F87171]">{erreur}</p>
        <button onClick={() => navigate("/cases")} className="rounded-md border border-white/10 px-3 py-1.5 text-xs text-white/60 hover:text-white" data-testid="case-erreur-retour">← Retour aux cases</button>
      </div>
    );
  }
  if (!cas) return <div className="p-8 font-code text-[11px] text-white/40" data-testid="case-chargement">Chargement du case…</div>;

  const t = TYPES_CASE[cas.type] || [cas.type, "#9CA3AF"];
  const sens = SENSIBILITES[cas.sensibilite] || [cas.sensibilite || "interne", "#3B82F6"];
  const derniereEvolution = (cas.historique || []).slice(-1)[0];

  return (
    <div className="flex h-full flex-col" data-testid="case-detail">
      {/* En-tête permanent */}
      <div className="shrink-0 border-b border-white/[0.07] px-8 py-3" data-testid="case-entete">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-4">
            <button onClick={() => navigate("/cases")} data-testid="case-retour-btn" className="flex shrink-0 items-center gap-1.5 rounded-md border border-white/10 px-2.5 py-1.5 text-xs text-white/55 transition-colors hover:text-white">
              <ArrowLeft size={13} /> Cases
            </button>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="rounded border border-white/15 bg-white/[0.04] px-1.5 py-0.5 font-code text-[10px] text-white/60" data-testid="case-numero">{numeroCase(cas)}</span>
                <span className="rounded border px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider" style={{ color: t[1], borderColor: `${t[1]}44`, backgroundColor: `${t[1]}12` }} data-testid="case-type">{t[0]}</span>
                <span className="rounded border px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider" style={{ color: sens[1], borderColor: `${sens[1]}44`, backgroundColor: `${sens[1]}12` }} data-testid="case-sensibilite">{sens[0]}</span>
                {cas.a_revoir && (
                  <span className="rounded border border-[#F87171]/40 bg-[#F87171]/[0.08] px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider text-[#F87171]" data-testid="case-arevoir-entete">À revoir</span>
                )}
              </div>
              <h1 className="mt-0.5 truncate font-display text-lg font-bold tracking-tight text-white" data-testid="case-titre">{cas.titre}</h1>
              <p className="flex items-center gap-1.5 truncate font-code text-[10px] text-white/40">
                <Users size={11} className="shrink-0" /> {(cas.participants || []).map(nomPersona).join(" · ") || "—"}
                {derniereEvolution && <span className="shrink-0 text-white/25">· {derniereEvolution.texte} ({rel(derniereEvolution.quand)})</span>}
              </p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <select value={cas.responsable || ""} onChange={(e) => maj({ responsable: e.target.value })} data-testid="case-responsable-select" title="Responsable du case" className="rounded-md border border-white/10 bg-black/50 px-2.5 py-1.5 text-xs text-white focus:outline-none">
              {personas.map((p) => <option key={p.id} value={p.id} label={`Resp. ${p.nom}`} />)}
            </select>
            <select value={cas.statut} onChange={(e) => maj({ statut: e.target.value })} data-testid="case-statut-select" className="rounded-md border border-white/10 bg-black/50 px-2.5 py-1.5 text-xs text-white focus:outline-none">
              {Object.entries(STATUTS_CASE).map(([k, [l]]) => <option key={k} value={k} label={l} />)}
            </select>
            <button onClick={continuerFlore} data-testid="case-continuer-flore-btn" className="flex items-center gap-1.5 rounded-md bg-[#3B82F6] px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-[#2F6FDB]">
              <Sparkle size={13} weight="fill" /> Continuer avec Flore
            </button>
            <button onClick={ouvrirAtlas} data-testid="case-atlas-btn" className="flex items-center gap-1.5 rounded-md border border-[#22D3EE]/30 bg-[#22D3EE]/[0.06] px-3 py-1.5 text-xs text-[#22D3EE] transition-colors hover:bg-[#22D3EE]/15">
              <Compass size={13} /> Ouvrir dans Atlas
            </button>
            <button onClick={partager} data-testid="case-partager-btn" title="Copier le lien du case" className="flex h-8 w-8 items-center justify-center rounded-md border border-white/10 text-white/55 transition-colors hover:text-white">
              <ShareNetwork size={14} />
            </button>
            <div className="relative">
              <button onClick={() => setMenu(!menu)} data-testid="case-menu-btn" className="flex h-8 w-8 items-center justify-center rounded-md border border-white/10 text-white/55 transition-colors hover:text-white">
                <DotsThree size={16} weight="bold" />
              </button>
              {menu && (
                <div className="glass absolute right-0 top-9 z-50 w-56 rounded-xl p-1.5" data-testid="case-menu">
                  {cas.a_revoir && (
                    <button onClick={() => { setMenu(false); maj({ a_revoir: false }); }} data-testid="case-marquer-revu-btn" className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-left text-[11px] text-[#F87171] hover:bg-white/[0.06]">
                      <SealCheck size={12} /> Marquer comme revu
                    </button>
                  )}
                  <button
                    onClick={() => { setMenu(false); maj({ statut: cas.statut === "clos" ? "en_cours" : "clos" }); }}
                    data-testid="case-clore-btn"
                    className="w-full rounded px-2.5 py-1.5 text-left text-[11px] text-white/65 hover:bg-white/[0.06] hover:text-white"
                  >
                    {cas.statut === "clos" ? "Rouvrir le case" : "Clore le case"}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Navigation interne — 5 vues */}
        <nav className="mt-3 flex gap-1" data-testid="case-vues">
          {VUES.map(([id, label]) => (
            <button
              key={id}
              onClick={() => setSearchParams({ vue: id }, { replace: true })}
              data-testid={`case-vue-${id}`}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                vue === id ? "bg-white/[0.08] text-white" : "text-white/45 hover:bg-white/[0.04] hover:text-white"
              }`}
            >
              {label}
            </button>
          ))}
        </nav>
      </div>

      {/* Contenu de la vue */}
      <div className="flex-1 overflow-y-auto px-8 py-5">
        <div className="mx-auto max-w-6xl">
          {cas.a_revoir && vue === "apercu" && (
            <div className="mb-4 flex items-center justify-between gap-3 rounded-xl border border-[#F87171]/30 bg-[#F87171]/[0.05] px-4 py-3" data-testid="case-arevoir-banner">
              <p className="text-xs text-[#F87171]">
                <span className="font-semibold uppercase tracking-wider">À revoir</span> — une connaissance du Mesh liée à ce case a changé ; les conclusions peuvent être remises en cause.
              </p>
              <button onClick={() => maj({ a_revoir: false })} className="shrink-0 rounded-md border border-[#F87171]/40 px-2.5 py-1.5 text-[11px] font-semibold text-[#F87171] transition-colors hover:bg-[#F87171]/10">
                Marquer comme revu
              </button>
            </div>
          )}
          {vue === "apercu" && <OngletApercu cas={cas} maj={maj} setCas={setCas} />}
          {vue === "travail" && <OngletTravail cas={cas} maj={maj} setCas={setCas} situations={situations} />}
          {vue === "atlas" && <OngletAtlas cas={cas} mesh={mesh} />}
          {vue === "decisions" && <OngletDecisions cas={cas} maj={maj} setCas={setCas} />}
          {vue === "activite" && <OngletActivite cas={cas} maj={maj} setCas={setCas} />}
        </div>
      </div>
    </div>
  );
}
