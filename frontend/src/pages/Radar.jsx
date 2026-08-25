import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Eye, MagnifyingGlass, Prohibit, Binoculars, Lightning } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import { PRIORITES, TYPES_SITUATION, NATURES_EVENEMENT, couleurDomaine } from "@/lib/domaines";

export default function Radar() {
  const navigate = useNavigate();
  const { jumeauPar } = useMesh();
  const [situations, setSituations] = useState([]);
  const [activite, setActivite] = useState([]);

  useEffect(() => {
    api.get("/situations").then((r) => setSituations(r.data.filter((s) => s.statut !== "ignorée"))).catch(() => {});
  }, []);

  useEffect(() => {
    let stop = false;
    const tick = async () => {
      try {
        const { data } = await api.get("/activite");
        if (stop) return;
        setActivite((prev) => [...data.map((e, i) => ({ ...e, uid: `${Date.now()}-${i}` })), ...prev].slice(0, 14));
      } catch {}
    };
    tick();
    const t = setInterval(tick, 6000);
    return () => { stop = true; clearInterval(t); };
  }, []);

  const agir = async (sit, action) => {
    try {
      await api.post(`/situations/${sit.id}/action`, { action });
      if (action === "ignorer") {
        setSituations((s) => s.filter((x) => x.id !== sit.id));
        toast.success("Situation ignorée");
      } else if (action === "surveiller") {
        setSituations((s) => s.map((x) => (x.id === sit.id ? { ...x, statut: "surveillée" } : x)));
        toast.success("Situation placée sous surveillance");
      } else if (action === "investiguer") {
        toast.success("Investigation créée");
        navigate(`/investigations/${sit.id}`);
      } else {
        navigate(`/investigations/${sit.id}`);
      }
    } catch {
      toast.error("Action impossible");
    }
  };

  return (
    <div className="h-full overflow-y-auto px-8 py-8 pb-40" data-testid="radar-page">
      <header className="rise">
        <div className="font-code text-[10px] uppercase tracking-[0.3em] text-[#3B82F6]">Détecter</div>
        <h1 className="mt-1 font-display text-4xl font-black text-white">Radar</h1>
        <p className="mt-2 text-base text-white/50">Qu'est-ce qui change ou mérite votre attention ?</p>
      </header>

      <div className="mt-8 grid grid-cols-12 gap-8">
        <div className="col-span-12 xl:col-span-8">
          <div data-testid="radar-feed">
            {situations.map((sit, idx) => {
              const prio = PRIORITES[sit.priorite] || PRIORITES.basse;
              const type = TYPES_SITUATION[sit.type] || { label: sit.type, couleur: "#9CA3AF" };
              return (
                <article
                  key={sit.id}
                  data-testid={`situation-card-${sit.id}`}
                  className="rise group border-b border-white/[0.06] py-6 transition-colors duration-200 hover:bg-white/[0.015]"
                  style={{ animationDelay: `${idx * 60}ms` }}
                >
                  <div className="flex items-start gap-4">
                    <span className="mt-1 h-full w-0.5 self-stretch rounded-full" style={{ backgroundColor: prio.couleur }} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className="rounded border px-1.5 py-0.5 font-code text-[10px] uppercase tracking-wider"
                          style={{ color: type.couleur, borderColor: `${type.couleur}44`, backgroundColor: `${type.couleur}12` }}
                        >
                          {type.label}
                        </span>
                        <span className="font-code text-[10px] uppercase tracking-wider" style={{ color: prio.couleur }}>
                          {prio.label} · score {sit.score}
                        </span>
                        <span className="font-code text-[10px] text-white/35">{sit.detectee}</span>
                        {sit.statut === "surveillée" && (
                          <span className="rounded border border-[#F59E0B]/40 bg-[#F59E0B]/10 px-1.5 py-0.5 font-code text-[10px] text-[#F59E0B]">
                            surveillée
                          </span>
                        )}
                      </div>
                      <h2 className="mt-2 font-display text-lg font-bold leading-snug text-white">{sit.titre}</h2>
                      <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-white/55">{sit.resume}</p>

                      <div className="mt-3 flex flex-wrap items-center gap-1.5">
                        {(sit.jumeaux || []).map((jid) => {
                          const j = jumeauPar(jid);
                          const c = couleurDomaine(j?.domaine);
                          return (
                            <span
                              key={jid}
                              className="rounded-full border px-2 py-0.5 font-code text-[10px]"
                              style={{ color: c, borderColor: `${c}33`, backgroundColor: `${c}0D` }}
                            >
                              {j?.nom || jid}
                            </span>
                          );
                        })}
                      </div>

                      {sit.aurora_recommandation && (
                        <div className="mt-3 flex items-center gap-2 text-xs text-white/40">
                          <Lightning size={13} className="text-[#3B82F6]" />
                          <span className="italic">{sit.aurora_recommandation}</span>
                        </div>
                      )}

                      <div className="mt-4 flex flex-wrap gap-2 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
                        <button onClick={() => agir(sit, "examiner")} data-testid={`action-examiner-${sit.id}`} className="flex items-center gap-1.5 rounded-md border border-white/15 px-2.5 py-1.5 text-xs text-white/70 transition-colors hover:border-white/40 hover:text-white">
                          <Eye size={14} /> Examiner
                        </button>
                        <button onClick={() => agir(sit, "investiguer")} data-testid={`action-investiguer-${sit.id}`} className="flex items-center gap-1.5 rounded-md bg-[#3B82F6] px-2.5 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-[#2F6FDB]">
                          <MagnifyingGlass size={14} /> Créer une investigation
                        </button>
                        <button onClick={() => agir(sit, "surveiller")} data-testid={`action-surveiller-${sit.id}`} className="flex items-center gap-1.5 rounded-md border border-white/15 px-2.5 py-1.5 text-xs text-white/70 transition-colors hover:border-[#F59E0B]/50 hover:text-[#F59E0B]">
                          <Binoculars size={14} /> Surveiller
                        </button>
                        <button onClick={() => agir(sit, "ignorer")} data-testid={`action-ignorer-${sit.id}`} className="flex items-center gap-1.5 rounded-md border border-white/15 px-2.5 py-1.5 text-xs text-white/50 transition-colors hover:border-white/30 hover:text-white/80">
                          <Prohibit size={14} /> Ignorer
                        </button>
                      </div>
                    </div>
                  </div>
                </article>
              );
            })}
            {situations.length === 0 && (
              <p className="py-16 text-sm text-white/40">Aucune situation active. Le Mesh observe en silence.</p>
            )}
          </div>
        </div>

        <aside className="col-span-12 xl:col-span-4">
          <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-5">
            <div className="flex items-center gap-2">
              <span className="pulse-soft h-1.5 w-1.5 rounded-full bg-[#10B981]" />
              <h3 className="font-code text-[10px] uppercase tracking-[0.25em] text-white/45">Activité du Mesh</h3>
            </div>
            <ul className="mt-4 space-y-3" data-testid="mesh-activity-feed">
              {activite.map((e) => {
                const j = jumeauPar(e.jumeau);
                const c = NATURES_EVENEMENT[e.nature] || "#6B7280";
                return (
                  <li key={e.uid} className="ticker-item flex items-start gap-2.5 text-sm">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: c }} />
                    <div className="min-w-0">
                      <span className="font-code text-[10px]" style={{ color: couleurDomaine(j?.domaine) }}>
                        {j?.nom || e.jumeau}
                      </span>
                      <p className="text-xs leading-snug text-white/55">{e.texte}</p>
                    </div>
                  </li>
                );
              })}
              {activite.length === 0 && <li className="text-xs text-white/30">Écoute du Mesh en cours…</li>}
            </ul>
          </div>
        </aside>
      </div>
    </div>
  );
}
