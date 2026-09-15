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

  const t = TYPES_CASE[cas.type] || [cas.type, "#7C93A8"];
  const sens = SENSIBILITES[cas.sensibilite] || [cas.sensibilite || "interne", "#9B87F5"];
  const derniereEvolution = (cas.historique || []).slice(-1)[0];

  return (
    <div className="flex h-full flex-col" data-testid="travail-detail">
      {/* En-tête permanent */}
      <div className="shrink-0 border-b border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-8 py-3" data-testid="travail-entete">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-4">
            <button onClick={() => navigate("/travaux")} data-testid="travail-retour-btn" className="flex shrink-0 items-center gap-1.5 rounded-md border border-[rgba(148,163,184,0.16)] px-2.5 py-1.5 text-xs text-[#94A3B8] transition-colors hover:text-[#F2F6F8]">
              <ArrowLeft size={13} /> Travaux
            </button>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="rounded border border-[rgba(148,163,184,0.16)] bg-[rgba(148,163,184,0.07)] px-1.5 py-0.5 font-code text-[10px] text-[#7C93A8]" data-testid="travail-numero">{numeroCase(cas)}</span>
                <span className="rounded border px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider" style={{ color: t[1], borderColor: `${t[1]}44`, backgroundColor: `${t[1]}0D` }} data-testid="travail-type">{t[0]}</span>
                <span className="rounded border px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider" style={{ color: sens[1], borderColor: `${sens[1]}44`, backgroundColor: `${sens[1]}0D` }} data-testid="travail-sensibilite">{sens[0]}</span>
                {cas.a_revoir && (
                  <span className="rounded border border-[#F87171]/40 bg-[#F87171]/[0.06] px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider text-[#F87171]" data-testid="travail-arevoir-entete">À revoir</span>
                )}
              </div>
              <h1 className="mt-0.5 truncate font-display text-lg font-bold tracking-tight text-[#F2F6F8]" data-testid="travail-titre">{cas.titre}</h1>
              <p className="flex items-center gap-1.5 truncate font-code text-[10px] text-[#7C93A8]">
                <Users size={11} className="shrink-0" /> {(cas.participants || []).map(nomPersona).join(" · ") || "—"}
                {derniereEvolution && <span className="shrink-0 text-[#7C93A8]">· {derniereEvolution.texte} ({rel(derniereEvolution.quand)})</span>}
              </p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button onClick={partager} data-testid="travail-partager-btn" title="Copier le lien du travail" className="flex h-8 w-8 items-center justify-center rounded-md border border-[rgba(148,163,184,0.16)] text-[#94A3B8] transition-colors hover:text-[#F2F6F8]">
              <ShareNetwork size={14} />
            </button>
            <div className="relative">
              <button onClick={() => setMenu(!menu)} data-testid="travail-menu-btn" className="flex h-8 w-8 items-center justify-center rounded-md border border-[rgba(148,163,184,0.16)] text-[#94A3B8] transition-colors hover:text-[#F2F6F8]">
                <DotsThree size={16} weight="bold" />
              </button>
              {menu && (
                <div className="glass absolute right-0 top-9 z-50 w-56 rounded-xl p-1.5" data-testid="travail-menu">
                  {cas.a_revoir && (
                    <button onClick={() => { setMenu(false); maj({ a_revoir: false }); }} data-testid="travail-marquer-revu-btn" className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-left text-[11px] text-[#F87171] hover:bg-[rgba(148,163,184,0.10)]">
                      <SealCheck size={12} /> Marquer comme revu
                    </button>
                  )}
                  <button
                    onClick={() => { setMenu(false); maj({ statut: cas.statut === "clos" ? "en_cours" : "clos" }); }}
                    data-testid="travail-clore-btn"
                    className="w-full rounded px-2.5 py-1.5 text-left text-[11px] text-[#94A3B8] hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]"
                  >
                    {cas.statut === "clos" ? "Rouvrir le travail" : "Clore le travail"}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Navigation interne — 2 vues */}
        <nav className="mt-3 flex gap-1" data-testid="travail-vues">
          {VUES.map(([id, label]) => (
            <button
              key={id}
              onClick={() => setSearchParams({ vue: id }, { replace: true })}
              data-testid={`travail-vue-${id}`}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                vue === id ? "bg-[rgba(148,163,184,0.10)] text-[#F2F6F8]" : "text-[#7C93A8] hover:bg-[rgba(148,163,184,0.07)] hover:text-[#F2F6F8]"
              }`}
            >
              {label}
            </button>
          ))}
        </nav>
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
      <div className={vue === "travail" ? "flex min-h-0 flex-1 flex-col overflow-hidden" : "flex-1 overflow-y-auto px-8 py-5"}>
        {vue === "travail" ? (
          <OngletTravail cas={cas} setCas={setCas} />
        ) : (
        <div className="mx-auto max-w-6xl">
          {vue === "apercu" && <OngletApercu cas={cas} maj={maj} setCas={setCas} situations={situations} />}
        </div>
        )}
      </div>
    </div>
  );
}
