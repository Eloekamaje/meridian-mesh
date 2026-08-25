import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { SealCheck, ArrowRight, GitBranch, CirclesThree } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import ChangeLab from "./ChangeLab";
import { NATURES, ETATS_RELATION, PRIORITES } from "@/lib/domaines";

export default function Decisions() {
  const [data, setData] = useState(null);
  const { jumeauPar, recharger } = useMesh();

  const charger = () => api.get("/decisions").then((r) => setData(r.data)).catch(() => {});
  useEffect(() => { charger(); }, []);

  const confirmer = async (r) => {
    try {
      await api.post(`/relations/${r.id}/confirmer`);
      toast.success("Relation confirmée — mémoire du Mesh enrichie");
      charger();
      recharger();
    } catch {
      toast.error("Confirmation impossible");
    }
  };

  return (
    <div className="h-full overflow-y-auto px-8 py-8 pb-44" data-testid="decisions-page">
      <header className="rise">
        <div className="font-code text-[10px] uppercase tracking-[0.3em] text-[#FBBF24]">Décider</div>
        <h1 className="mt-1 font-display text-4xl font-black text-white">Décisions</h1>
        <p className="mt-2 text-base text-white/50">Chaque décision enrichit la mémoire du Mesh — et le cycle recommence.</p>
      </header>

      {!data ? (
        <p className="py-16 text-sm text-white/40">Chargement de la file de décisions…</p>
      ) : (
        <div className="mt-8 space-y-10">
          <section className="rise" data-testid="decisions-relations">
            <h2 className="flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.25em] text-white/45">
              <GitBranch size={14} className="text-[#A78BFA]" /> Relations à confirmer
            </h2>
            <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
              {data.relations.map((r) => {
                const etat = ETATS_RELATION[r.etat] || ETATS_RELATION.confirmee;
                const s = jumeauPar(r.source);
                const c = jumeauPar(r.cible);
                return (
                  <div key={r.id} className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4" data-testid={`decision-relation-${r.id}`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="rounded border px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider" style={{ color: etat.couleur, borderColor: `${etat.couleur}55`, backgroundColor: `${etat.couleur}12` }}>
                        {etat.label}
                      </span>
                      {r.confiance && <span className="font-code text-[10px] text-white/45">confiance {r.confiance} %</span>}
                    </div>
                    <div className="mt-2.5 font-display text-sm font-bold text-white">
                      {s?.nom || r.source} → {c?.nom || r.cible}
                    </div>
                    <p className="mt-1 text-xs text-white/50">{(r.claims || [])[0] || "Relation candidate en attente de confirmation."}</p>
                    <div className="mt-3 flex items-center gap-2">
                      <button
                        onClick={() => confirmer(r)}
                        data-testid={`confirmer-${r.id}`}
                        className="flex items-center gap-1.5 rounded-md bg-[#FBBF24] px-3 py-1.5 text-xs font-semibold text-black transition-colors hover:bg-[#E5A910]"
                      >
                        <SealCheck size={14} weight="fill" /> Confirmer
                      </button>
                      <Link to="/atlas" className="flex items-center gap-1 text-xs text-white/45 transition-colors hover:text-white" data-testid={`voir-atlas-${r.id}`}>
                        Voir dans l'Atlas <ArrowRight size={12} />
                      </Link>
                    </div>
                  </div>
                );
              })}
              {data.relations.length === 0 && <p className="text-xs text-white/30">Aucune relation en attente de confirmation.</p>}
            </div>
          </section>

          <section className="rise" style={{ animationDelay: "80ms" }} data-testid="decisions-situations">
            <h2 className="font-code text-[10px] uppercase tracking-[0.25em] text-white/45">Conclusions & recommandations à valider</h2>
            <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
              {data.situations.map((sit) => {
                const n = NATURES[sit.nature] || { label: sit.nature, couleur: "#9CA3AF" };
                const p = PRIORITES[sit.priorite] || PRIORITES.basse;
                return (
                  <Link
                    key={sit.id}
                    to={`/investigations/${sit.id}`}
                    data-testid={`decision-situation-${sit.id}`}
                    className="group rounded-xl border border-white/[0.08] bg-white/[0.02] p-4 transition-colors hover:border-[#FBBF24]/40"
                  >
                    <div className="flex items-center gap-2">
                      <span className="rounded border px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider" style={{ color: n.couleur, borderColor: `${n.couleur}44`, backgroundColor: `${n.couleur}10` }}>{n.label}</span>
                      <span className="font-code text-[9px] uppercase tracking-wider" style={{ color: p.couleur }}>{p.label}</span>
                      <ArrowRight size={13} className="ml-auto text-white/25 transition-transform group-hover:translate-x-1 group-hover:text-[#FBBF24]" />
                    </div>
                    <div className="mt-2.5 text-sm font-semibold leading-snug text-white/90">{sit.titre}</div>
                    <p className="mt-1 line-clamp-2 text-xs text-white/45">{sit.synthese || sit.resume}</p>
                  </Link>
                );
              })}
              {data.situations.length === 0 && <p className="text-xs text-white/30">Aucune conclusion en attente.</p>}
            </div>
          </section>

          <section className="rise" style={{ animationDelay: "140ms" }} data-testid="decisions-admissions">
            <h2 className="flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.25em] text-white/45">
              <CirclesThree size={14} className="text-[#22D3EE]" /> Admissions de jumeaux
            </h2>
            <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
              {data.admissions.map((j) => (
                <div key={j.id} className="flex items-center justify-between gap-3 rounded-xl border border-white/[0.08] bg-white/[0.02] p-4" data-testid={`decision-jumeau-${j.id}`}>
                  <div>
                    <div className="text-sm font-semibold text-white">{j.nom}</div>
                    <div className="mt-0.5 font-code text-[10px] text-white/40">{j.statut} · couverture {j.couverture} %</div>
                  </div>
                  <Link to="/jumeaux" className="rounded-md border border-white/15 px-3 py-1.5 text-xs text-white/70 transition-colors hover:border-white/40 hover:text-white" data-testid={`admission-lien-${j.id}`}>
                    Examiner
                  </Link>
                </div>
              ))}
              {data.admissions.length === 0 && <p className="text-xs text-white/30">Tous les jumeaux connus sont admis.</p>}
            </div>
          </section>

          <section className="rise border-t border-white/[0.07] pt-8" style={{ animationDelay: "200ms" }}>
            <ChangeLab integre />
          </section>
        </div>
      )}
    </div>
  );
}
