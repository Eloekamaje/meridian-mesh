import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Question } from "@phosphor-icons/react";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import { usePerimetre } from "@/lib/perimetre";
import { couleurDomaine, couleurConfiance, NATURES, VERBES } from "@/lib/domaines";

const FILTRES = ["tous", "relation", "comportement", "connaissance", "contradiction", "incident", "changement"];

export default function Investigations() {
  const [situations, setSituations] = useState([]);
  const [filtre, setFiltre] = useState("tous");
  const { jumeauPar } = useMesh();
  const { version } = usePerimetre();

  useEffect(() => {
    api.get("/situations").then((r) => {
      setSituations(r.data.filter((s) => !["ignorée", "classée"].includes(s.statut)));
    }).catch(() => {});
  }, [version]);

  const visibles = situations.filter((s) => filtre === "tous" || s.nature === filtre);

  return (
    <div className="h-full overflow-y-auto px-8 py-8 pb-40" data-testid="investigations-page">
      <header className="rise">
        <div className="font-code text-[10px] uppercase tracking-[0.3em] text-[#6D28D9]">Comprendre</div>
        <h1 className="mt-1 font-display text-4xl font-black text-[#111110]">Investigations</h1>
        <p className="mt-2 text-base text-[#52524F]">
          Relations, comportements, connaissances, contradictions — pas seulement des incidents.
        </p>
      </header>

      <div className="rise mt-6 flex flex-wrap gap-1.5" style={{ animationDelay: "60ms" }} data-testid="nature-filters">
        {FILTRES.map((f) => {
          const actif = filtre === f;
          const c = f === "tous" ? "#6D28D9" : NATURES[f]?.couleur || "#71716D";
          return (
            <button
              key={f}
              onClick={() => setFiltre(f)}
              data-testid={`filtre-${f}`}
              className={`rounded-full border px-3 py-1.5 font-code text-[11px] transition-colors duration-200 ${
                actif ? "font-semibold" : "text-[#52524F] hover:text-[#111110]"
              }`}
              style={actif
                ? { color: c, borderColor: `${c}66`, backgroundColor: `${c}14` }
                : { borderColor: "rgba(17,17,16,0.1)" }}
            >
              {f === "tous" ? "Toutes" : NATURES[f]?.label}
            </button>
          );
        })}
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        {visibles.map((sit, idx) => {
          const n = NATURES[sit.nature] || { label: sit.nature || "—", couleur: "#71716D" };
          const v = VERBES[sit.verbe];
          const confianceMax = Math.max(0, ...(sit.hypotheses || []).map((h) => h.confiance));
          return (
            <Link
              key={sit.id}
              to={`/investigations/${sit.id}`}
              data-testid={`investigation-card-${sit.id}`}
              className="rise group rounded-xl border border-[#E5E5E3] bg-white p-6 transition-colors duration-200 hover:border-[#6D28D9]/40 hover:bg-[#F0F0EE]"
              style={{ animationDelay: `${idx * 60}ms` }}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span
                    className="rounded border px-1.5 py-0.5 font-code text-[10px] uppercase tracking-wider"
                    style={{ color: n.couleur, borderColor: `${n.couleur}44`, backgroundColor: `${n.couleur}10` }}
                    data-testid={`nature-${sit.id}`}
                  >
                    {n.label}
                  </span>
                  {v && (
                    <span className="font-code text-[9px] uppercase tracking-wider" style={{ color: v.couleur }}>
                      {v.label}
                    </span>
                  )}
                </div>
                <ArrowRight size={16} className="text-[#71716D] transition-transform duration-200 group-hover:translate-x-1 group-hover:text-[#6D28D9]" />
              </div>
              <div className="mt-4 flex items-start gap-2.5">
                <Question size={18} className="mt-0.5 shrink-0 text-[#6D28D9]" />
                <h2 className="font-display text-lg font-bold leading-snug text-[#111110]">
                  {sit.question || sit.titre}
                </h2>
              </div>
              <p className="mt-2 line-clamp-2 text-sm text-[#52524F]">{sit.resume}</p>
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
              <div className="mt-4 flex items-center gap-4 font-code text-[10px] text-[#71716D]">
                <span>{(sit.hypotheses || []).length} hypothèse{(sit.hypotheses || []).length > 1 ? "s" : ""}</span>
                {confianceMax > 0 && (
                  <span style={{ color: couleurConfiance(confianceMax) }}>confiance max {confianceMax} %</span>
                )}
                <span className="ml-auto">{sit.statut}</span>
              </div>
            </Link>
          );
        })}
      </div>
      {visibles.length === 0 && (
        <p className="py-16 text-sm text-[#71716D]">Aucune investigation de ce type. Les découvertes de l'Observatoire alimentent cette page.</p>
      )}
    </div>
  );
}
