import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Question } from "@phosphor-icons/react";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import { couleurDomaine, couleurConfiance } from "@/lib/domaines";

export default function Investigations() {
  const [situations, setSituations] = useState([]);
  const { jumeauPar } = useMesh();

  useEffect(() => {
    api.get("/situations").then((r) => {
      setSituations(r.data.filter((s) => (s.hypotheses || []).length > 0 || s.statut === "en investigation" || s.statut === "décidée"));
    }).catch(() => {});
  }, []);

  return (
    <div className="h-full overflow-y-auto px-8 py-8 pb-40" data-testid="investigations-page">
      <header className="rise">
        <div className="font-code text-[10px] uppercase tracking-[0.3em] text-[#3B82F6]">Comprendre</div>
        <h1 className="mt-1 font-display text-4xl font-black text-white">Investigations</h1>
        <p className="mt-2 text-base text-white/50">Le cœur opérationnel : question, chronologie, hypothèses, conclusion.</p>
      </header>

      <div className="mt-8 grid grid-cols-1 gap-4 lg:grid-cols-2">
        {situations.map((sit, idx) => {
          const confianceMax = Math.max(0, ...(sit.hypotheses || []).map((h) => h.confiance));
          return (
            <Link
              key={sit.id}
              to={`/investigations/${sit.id}`}
              data-testid={`investigation-card-${sit.id}`}
              className="rise group rounded-xl border border-white/[0.08] bg-white/[0.02] p-6 transition-colors duration-200 hover:border-[#3B82F6]/40 hover:bg-white/[0.04]"
              style={{ animationDelay: `${idx * 70}ms` }}
            >
              <div className="flex items-center justify-between">
                <span className="rounded border border-white/10 bg-white/[0.04] px-1.5 py-0.5 font-code text-[10px] uppercase tracking-wider text-white/50">
                  {sit.statut}
                </span>
                <ArrowRight size={16} className="text-white/30 transition-transform duration-200 group-hover:translate-x-1 group-hover:text-[#3B82F6]" />
              </div>
              <div className="mt-4 flex items-start gap-2.5">
                <Question size={18} className="mt-0.5 shrink-0 text-[#3B82F6]" />
                <h2 className="font-display text-lg font-bold leading-snug text-white">
                  {sit.question || sit.titre}
                </h2>
              </div>
              <p className="mt-2 line-clamp-2 text-sm text-white/50">{sit.resume}</p>
              <div className="mt-4 flex flex-wrap items-center gap-1.5">
                {(sit.jumeaux || []).map((jid) => {
                  const j = jumeauPar(jid);
                  const c = couleurDomaine(j?.domaine);
                  return (
                    <span key={jid} className="rounded-full border px-2 py-0.5 font-code text-[10px]" style={{ color: c, borderColor: `${c}33`, backgroundColor: `${c}0D` }}>
                      {j?.nom || jid}
                    </span>
                  );
                })}
              </div>
              <div className="mt-4 flex items-center gap-4 font-code text-[10px] text-white/40">
                <span>{(sit.hypotheses || []).length} hypothèse{(sit.hypotheses || []).length > 1 ? "s" : ""}</span>
                {confianceMax > 0 && (
                  <span style={{ color: couleurConfiance(confianceMax) }}>confiance max {confianceMax} %</span>
                )}
              </div>
            </Link>
          );
        })}
      </div>
      {situations.length === 0 && (
        <p className="py-16 text-sm text-white/40">Aucune investigation en cours. Créez-en une depuis le Radar.</p>
      )}
    </div>
  );
}
