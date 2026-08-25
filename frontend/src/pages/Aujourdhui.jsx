import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { X } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import { usePerimetre } from "@/lib/perimetre";
import { VERBES, NATURES, couleurDomaine } from "@/lib/domaines";

const COLONNES = ["decouvert", "a_comprendre", "a_decider"];

export default function Aujourdhui() {
  const navigate = useNavigate();
  const { jumeauPar } = useMesh();
  const { version, info, vueActive } = usePerimetre();
  const [situations, setSituations] = useState([]);
  const [activite, setActivite] = useState([]);
  const [tickIdx, setTickIdx] = useState(0);

  useEffect(() => {
    api
      .get("/situations")
      .then((r) => setSituations(r.data.filter((s) => !["ignorée", "classée"].includes(s.statut))))
      .catch(() => {});
  }, [version]);

  useEffect(() => {
    setActivite([]);
    let stop = false;
    const tick = async () => {
      try {
        const { data } = await api.get("/activite");
        if (!stop) setActivite(data);
      } catch {}
    };
    tick();
    const t = setInterval(tick, 8000);
    const rot = setInterval(() => setTickIdx((i) => i + 1), 4000);
    return () => { stop = true; clearInterval(t); clearInterval(rot); };
  }, [version]);

  const ignorer = async (e, sit) => {
    e.stopPropagation();
    try {
      await api.post(`/situations/${sit.id}/action`, { action: "ignorer" });
      setSituations((s) => s.filter((x) => x.id !== sit.id));
      toast.success("Élément ignoré");
    } catch {
      toast.error("Action impossible");
    }
  };

  const live = activite.length ? activite[tickIdx % activite.length] : null;
  const liveJ = live ? jumeauPar(live.jumeau) : null;

  return (
    <div className="h-full overflow-y-auto px-8 py-8 pb-40" data-testid="aujourdhui-page">
      <header className="rise">
        <div className="font-code text-[10px] uppercase tracking-[0.3em] text-[#22D3EE]">Observatoire des découvertes</div>
        <h1 className="mt-1 font-display text-4xl font-black text-white">Aujourd'hui</h1>
        <p className="mt-2 text-base text-white/50">
          Ce que Méridian a découvert, compris ou soumis à décision depuis votre dernière visite.
        </p>
        {info && (
          <div className="mt-3 flex flex-wrap items-center gap-2" data-testid="mon-espace-strip">
            <span className="font-code text-[10px] uppercase tracking-[0.2em] text-white/35">
              {info.espace.global ? "Mesh global" : `Mon espace · ${info.espace.label}`}
            </span>
            <span className="rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 font-code text-[10px] text-white/55">
              {info.nb_autorises} jumeaux autorisés
            </span>
            <span className="rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 font-code text-[10px] text-white/55">
              {situations.length} découvertes pertinentes
            </span>
            <span className="rounded-full border border-[#FBBF24]/30 bg-[#FBBF24]/[0.06] px-2 py-0.5 font-code text-[10px] text-[#FBBF24]">
              {situations.filter((s) => s.verbe === "a_decider").length} décisions en attente
            </span>
            {vueActive && (
              <span className="rounded-full border border-[#22D3EE]/30 bg-[#22D3EE]/[0.06] px-2 py-0.5 font-code text-[10px] text-[#22D3EE]">
                Vue « {vueActive.nom} » — filtre personnel, aucun droit supplémentaire
              </span>
            )}
          </div>
        )}
        {live && (
          <div className="mt-4 flex items-center gap-2.5 font-code text-[11px]" data-testid="live-ticker">
            <span className="pulse-soft h-1.5 w-1.5 rounded-full bg-[#10B981]" />
            <span className="uppercase tracking-[0.2em] text-white/35">En direct</span>
            <span key={`${live.jumeau}-${tickIdx}`} className="ticker-item text-white/55">
              <span style={{ color: couleurDomaine(liveJ?.domaine) }}>{liveJ?.nom || live.jumeau}</span>
              {" — "}{live.texte}
            </span>
          </div>
        )}
      </header>

      <div className="mt-8 grid grid-cols-1 gap-6 xl:grid-cols-3" data-testid="observatoire-colonnes">
        {COLONNES.map((col, ci) => {
          const v = VERBES[col];
          let items = situations.filter((s) => s.verbe === col);
          if (vueActive?.type === "selection") {
            items = items.filter((s) => (s.jumeaux || []).some((j) => vueActive.jumeaux.includes(j)));
          }
          return (
            <section
              key={col}
              className="rise rounded-xl border border-white/[0.07] bg-white/[0.015] p-4"
              style={{ animationDelay: `${ci * 90}ms` }}
              data-testid={`colonne-${col}`}
            >
              <div className="flex items-center gap-2 border-b border-white/[0.06] pb-3">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: v.couleur, boxShadow: `0 0 10px ${v.couleur}66` }} />
                <h2 className="font-display text-base font-bold text-white">{v.label}</h2>
                <span className="rounded-full bg-white/[0.07] px-2 py-0.5 font-code text-[10px] text-white/60" data-testid={`count-${col}`}>
                  {items.length}
                </span>
              </div>
              <p className="mt-2 font-code text-[10px] text-white/35">{v.accroche}</p>

              <div className="mt-3 space-y-3">
                {items.map((sit) => {
                  const n = NATURES[sit.nature] || { label: sit.nature || "—", couleur: "#9CA3AF" };
                  return (
                    <article
                      key={sit.id}
                      onClick={() => navigate(`/investigations/${sit.id}`)}
                      data-testid={`decouverte-card-${sit.id}`}
                      className="group cursor-pointer rounded-lg border border-white/[0.07] bg-black/30 p-3.5 transition-colors duration-200 hover:border-white/25 hover:bg-black/50"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span
                          className="rounded border px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider"
                          style={{ color: n.couleur, borderColor: `${n.couleur}44`, backgroundColor: `${n.couleur}10` }}
                        >
                          {n.label}
                        </span>
                        <button
                          onClick={(e) => ignorer(e, sit)}
                          data-testid={`ignorer-${sit.id}`}
                          title="Ignorer"
                          className="text-white/20 opacity-0 transition-opacity duration-200 hover:text-white/70 group-hover:opacity-100"
                        >
                          <X size={13} />
                        </button>
                      </div>
                      <h3 className="mt-2 text-sm font-semibold leading-snug text-white/90">{sit.titre}</h3>
                      <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-white/45">{sit.resume}</p>
                      <div className="mt-2.5 flex items-center justify-between font-code text-[9px] text-white/30">
                        <span>{sit.detectee}</span>
                        {sit.indicateurs && (
                          <span style={{ color: v.couleur }}>confiance {sit.indicateurs.confiance} %</span>
                        )}
                      </div>
                    </article>
                  );
                })}
                {items.length === 0 && (
                  <p className="py-8 text-center text-xs text-white/25">Rien ici pour l'instant — le Mesh continue d'observer.</p>
                )}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
