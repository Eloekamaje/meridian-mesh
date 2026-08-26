import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, Compass, Sparkle, Users, ShareNetwork, DotsThree, SealCheck } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import { usePerimetre } from "@/lib/perimetre";
import { useContexte } from "@/lib/contexte";
import { TYPES_CASE, STATUTS_CASE } from "./Travaux";
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

export default function TravailDetail() {
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
    api.get(`/cases/${cid}`).then((r) => setCas(r.data)).catch((e) => setErreur(e.response?.data?.detail || "Travail introuvable"));
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
      toast.success("Lien du travail copié");
    } catch {
      toast.error("Copie impossible — " + window.location.href);
    }
  };

  if (erreur) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4" data-testid="travail-erreur">
        <p className="text-sm text-[#B91C1C]">{erreur}</p>
        <button onClick={() => navigate("/travaux")} className="rounded-md border border-[#E5E5E3] px-3 py-1.5 text-xs text-[#52524F] hover:text-[#111110]" data-testid="travail-erreur-retour">← Retour aux travaux</button>
      </div>
    );
  }
  if (!cas) return <div className="p-8 font-code text-[11px] text-[#71716D]" data-testid="travail-chargement">Chargement du travail…</div>;

  const t = TYPES_CASE[cas.type] || [cas.type, "#71716D"];
  const sens = SENSIBILITES[cas.sensibilite] || [cas.sensibilite || "interne", "#3730A3"];
  const derniereEvolution = (cas.historique || []).slice(-1)[0];

  return (
    <div className="flex h-full flex-col" data-testid="travail-detail">
      {/* En-tête permanent */}
      <div className="shrink-0 border-b border-[#E5E5E3] bg-white px-8 py-3" data-testid="travail-entete">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-4">
            <button onClick={() => navigate("/travaux")} data-testid="travail-retour-btn" className="flex shrink-0 items-center gap-1.5 rounded-md border border-[#E5E5E3] px-2.5 py-1.5 text-xs text-[#52524F] transition-colors hover:text-[#111110]">
              <ArrowLeft size={13} /> Travaux
            </button>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="rounded border border-[#E5E5E3] bg-[#F7F7F6] px-1.5 py-0.5 font-code text-[10px] text-[#71716D]" data-testid="travail-numero">{numeroCase(cas)}</span>
                <span className="rounded border px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider" style={{ color: t[1], borderColor: `${t[1]}44`, backgroundColor: `${t[1]}0D` }} data-testid="travail-type">{t[0]}</span>
                <span className="rounded border px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider" style={{ color: sens[1], borderColor: `${sens[1]}44`, backgroundColor: `${sens[1]}0D` }} data-testid="travail-sensibilite">{sens[0]}</span>
                {cas.a_revoir && (
                  <span className="rounded border border-[#B91C1C]/40 bg-[#B91C1C]/[0.06] px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider text-[#B91C1C]" data-testid="travail-arevoir-entete">À revoir</span>
                )}
              </div>
              <h1 className="mt-0.5 truncate font-display text-lg font-bold tracking-tight text-[#111110]" data-testid="travail-titre">{cas.titre}</h1>
              <p className="flex items-center gap-1.5 truncate font-code text-[10px] text-[#71716D]">
                <Users size={11} className="shrink-0" /> {(cas.participants || []).map(nomPersona).join(" · ") || "—"}
                {derniereEvolution && <span className="shrink-0 text-[#71716D]">· {derniereEvolution.texte} ({rel(derniereEvolution.quand)})</span>}
              </p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <select value={cas.responsable || ""} onChange={(e) => maj({ responsable: e.target.value })} data-testid="travail-responsable-select" title="Responsable du travail" className="rounded-md border border-[#E5E5E3] bg-white px-2.5 py-1.5 text-xs text-[#111110] focus:outline-none">
              {personas.map((p) => <option key={p.id} value={p.id} label={`Resp. ${p.nom}`} />)}
            </select>
            <select value={cas.statut} onChange={(e) => maj({ statut: e.target.value })} data-testid="travail-statut-select" className="rounded-md border border-[#E5E5E3] bg-white px-2.5 py-1.5 text-xs text-[#111110] focus:outline-none">
              {Object.entries(STATUTS_CASE).map(([k, [l]]) => <option key={k} value={k} label={l} />)}
            </select>
            <button onClick={continuerFlore} data-testid="travail-continuer-flore-btn" className="flex items-center gap-1.5 rounded-md bg-[#3730A3] px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-[#4338CA]">
              <Sparkle size={13} weight="fill" /> Continuer avec Flore
            </button>
            <button onClick={ouvrirAtlas} data-testid="travail-atlas-btn" className="flex items-center gap-1.5 rounded-md border border-[#0E7490]/30 bg-[#0E7490]/[0.06] px-3 py-1.5 text-xs text-[#0E7490] transition-colors hover:bg-[#0E7490]/15">
              <Compass size={13} /> Ouvrir dans Atlas
            </button>
            <button onClick={partager} data-testid="travail-partager-btn" title="Copier le lien du travail" className="flex h-8 w-8 items-center justify-center rounded-md border border-[#E5E5E3] text-[#52524F] transition-colors hover:text-[#111110]">
              <ShareNetwork size={14} />
            </button>
            <div className="relative">
              <button onClick={() => setMenu(!menu)} data-testid="travail-menu-btn" className="flex h-8 w-8 items-center justify-center rounded-md border border-[#E5E5E3] text-[#52524F] transition-colors hover:text-[#111110]">
                <DotsThree size={16} weight="bold" />
              </button>
              {menu && (
                <div className="glass absolute right-0 top-9 z-50 w-56 rounded-xl p-1.5" data-testid="travail-menu">
                  {cas.a_revoir && (
                    <button onClick={() => { setMenu(false); maj({ a_revoir: false }); }} data-testid="travail-marquer-revu-btn" className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-left text-[11px] text-[#B91C1C] hover:bg-[#F0F0EE]">
                      <SealCheck size={12} /> Marquer comme revu
                    </button>
                  )}
                  <button
                    onClick={() => { setMenu(false); maj({ statut: cas.statut === "clos" ? "en_cours" : "clos" }); }}
                    data-testid="travail-clore-btn"
                    className="w-full rounded px-2.5 py-1.5 text-left text-[11px] text-[#52524F] hover:bg-[#F0F0EE] hover:text-[#111110]"
                  >
                    {cas.statut === "clos" ? "Rouvrir le travail" : "Clore le travail"}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Navigation interne — 5 vues */}
        <nav className="mt-3 flex gap-1" data-testid="travail-vues">
          {VUES.map(([id, label]) => (
            <button
              key={id}
              onClick={() => setSearchParams({ vue: id }, { replace: true })}
              data-testid={`travail-vue-${id}`}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                vue === id ? "bg-[#F0F0EE] text-[#111110]" : "text-[#71716D] hover:bg-[#F7F7F6] hover:text-[#111110]"
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
            <div className="mb-4 flex items-center justify-between gap-3 rounded-xl border border-[#B91C1C]/30 bg-[#B91C1C]/[0.04] px-4 py-3" data-testid="travail-arevoir-banner">
              <p className="text-xs text-[#B91C1C]">
                <span className="font-semibold uppercase tracking-wider">À revoir</span> — une connaissance du Mesh liée à ce travail a changé ; les conclusions peuvent être remises en cause.
              </p>
              <button onClick={() => maj({ a_revoir: false })} className="shrink-0 rounded-md border border-[#B91C1C]/40 px-2.5 py-1.5 text-[11px] font-semibold text-[#B91C1C] transition-colors hover:bg-[#B91C1C]/10">
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
