import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, SealCheck, Eye, HourglassMedium } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import { usePerimetre } from "@/lib/perimetre";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { couleurDomaine } from "@/lib/domaines";

const SOURCES = [
  ["code", "Code"],
  ["bdd", "Base de données"],
  ["observabilite", "Observabilité"],
  ["incidents", "Incidents & changements"],
  ["documentation", "Documentation"],
];

const STATUTS = {
  "actif": { label: "actif", couleur: "#10B981" },
  "observation": { label: "observation", couleur: "#F59E0B" },
  "en construction": { label: "en construction", couleur: "#3B82F6" },
};

export default function Jumeaux() {
  const [jumeaux, setJumeaux] = useState([]);
  const [brouillons, setBrouillons] = useState([]);
  const { recharger } = useMesh();
  const { version } = usePerimetre();
  const navigate = useNavigate();
  const [examen, setExamen] = useState(null);

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

  const admettre = async (j) => {
    try {
      await api.post(`/jumeaux/${j.id}/admettre`);
      toast.success(`${j.nom} admis dans le Mesh — mémoire enrichie`);
      charger();
      recharger();
    } catch {
      toast.error("Admission impossible");
    }
  };

  const examiner = async (j) => {
    try {
      const { data } = await api.post(`/jumeaux/${j.id}/examiner`);
      setExamen(data);
    } catch {
      toast.error("Examen impossible");
    }
  };

  return (
    <div className="h-full overflow-y-auto px-8 py-8 pb-44" data-testid="jumeaux-page">
      <header className="rise flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="font-code text-[10px] uppercase tracking-[0.3em] text-[#22D3EE]">Découvrir · Décider</div>
          <h1 className="mt-1 font-display text-4xl font-black text-white">Jumeaux</h1>
          <p className="mt-2 text-base text-white/50">Le réseau de jumeaux applicatifs : admission, autonomie, couverture de connaissance.</p>
        </div>
        <button
          onClick={commander}
          data-testid="commander-jumeau-btn"
          className="flex items-center gap-2 rounded-md bg-[#3B82F6] px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#2F6FDB]"
        >
          <Plus size={16} weight="bold" /> Commander un jumeau
        </button>
      </header>

      {brouillons.length > 0 && (
        <div className="rise mt-6 flex flex-wrap gap-2" data-testid="commandes-en-cours">
          {brouillons.map((c) => (
            <button
              key={c.id}
              onClick={() => navigate(`/commande/${c.id}`)}
              data-testid={`reprendre-${c.id}`}
              className="flex items-center gap-2 rounded-lg border border-[#FBBF24]/25 bg-[#FBBF24]/[0.04] px-3 py-2 text-left transition-colors hover:border-[#FBBF24]/50"
            >
              <HourglassMedium size={14} className="text-[#FBBF24]" />
              <div>
                <div className="text-xs font-semibold text-white">Commande en cours — {c.jumeau?.nom || "sans nom"}</div>
                <div className="font-code text-[9px] text-white/40">étape {c.etape}/4 · {c.sources?.length || 0} source(s) · reprendre →</div>
              </div>
            </button>
          ))}
        </div>
      )}

      <div className="rise mt-8 overflow-hidden rounded-xl border border-white/[0.08]" style={{ animationDelay: "80ms" }} data-testid="jumeaux-table">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/[0.08] bg-white/[0.03] font-code text-[10px] uppercase tracking-wider text-white/40">
              <th className="px-4 py-3 text-left font-medium">Jumeau</th>
              <th className="px-4 py-3 text-left font-medium">Statut</th>
              <th className="px-4 py-3 text-left font-medium">Propriétaire</th>
              <th className="px-4 py-3 text-left font-medium">Couverture</th>
              <th className="px-4 py-3 text-left font-medium">Fraîcheur</th>
              <th className="px-4 py-3 text-left font-medium">Autonomie</th>
              <th className="px-4 py-3 text-left font-medium">Sources</th>
              <th className="px-4 py-3 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {jumeaux.map((j) => {
              const st = STATUTS[j.statut] || { label: j.statut, couleur: "#9CA3AF" };
              const c = couleurDomaine(j.domaine);
              return (
                <tr key={j.id} className="border-b border-white/[0.05] transition-colors hover:bg-white/[0.02]" data-testid={`jumeau-row-${j.id}`}>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: c }} />
                      <div>
                        <div className="font-semibold text-white">{j.nom}</div>
                        <div className="font-code text-[10px] uppercase tracking-wider text-white/35">{j.domaine}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className="rounded border px-1.5 py-0.5 font-code text-[10px]" style={{ color: st.couleur, borderColor: `${st.couleur}44`, backgroundColor: `${st.couleur}12` }}>
                      {st.label}
                    </span>
                  </td>
                  <td className="max-w-[180px] truncate px-4 py-3 text-xs text-white/55">{j.proprietaire}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="h-1 w-16 overflow-hidden rounded-full bg-white/[0.07]">
                        <div className="h-full rounded-full" style={{ width: `${j.couverture}%`, backgroundColor: j.couverture >= 70 ? "#10B981" : j.couverture >= 50 ? "#F59E0B" : "#EF4444" }} />
                      </div>
                      <span className="font-code text-[11px] text-white/70">{j.couverture} %</span>
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 font-code text-[11px] text-white/50">{j.fraicheur}</td>
                  <td className="px-4 py-3 font-code text-[11px] text-white/50">{j.autonomie}</td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1">
                      {SOURCES.map(([k, label]) => (
                        <span key={k} title={label} className={`h-2 w-2 rounded-full ${j.sources?.[k] ? "bg-[#10B981]" : "bg-white/15"}`} />
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1.5">
                      <button onClick={() => examiner(j)} data-testid={`examiner-${j.id}`} className="flex items-center gap-1 rounded border border-white/15 px-2 py-1 text-[11px] text-white/60 transition-colors hover:border-white/40 hover:text-white">
                        <Eye size={12} /> Examiner
                      </button>
                      {j.statut !== "actif" && j.niveau === "complet" && (
                        <button onClick={() => admettre(j)} data-testid={`admettre-${j.id}`} className="flex items-center gap-1 rounded bg-[#FBBF24] px-2 py-1 text-[11px] font-semibold text-black transition-colors hover:bg-[#E5A910]">
                          <SealCheck size={12} /> Admettre
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <Dialog open={!!examen} onOpenChange={() => setExamen(null)}>
        <DialogContent className="border-white/10 bg-[#0D0D0D] text-white sm:max-w-lg" data-testid="examen-dialog">
          <DialogHeader>
            <DialogTitle className="font-display text-lg font-bold">Examen — {examen?.identite?.nom}</DialogTitle>
          </DialogHeader>
          {examen && (
            <div className="space-y-4 text-sm">
              <p className="text-white/60">{examen.identite.mission}</p>
              <Section titre="Capacités découvertes" items={examen.capacites} />
              <Section titre="Comportements observés" items={examen.comportements} />
              <div>
                <div className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Relations supposées</div>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {examen.relations_supposees.map((r, i) => (
                    <span key={i} className="rounded-full border border-[#A78BFA]/40 bg-[#A78BFA]/10 px-2 py-0.5 font-code text-[10px] text-[#A78BFA]">
                      {r.jumeau} · {r.confiance} %
                    </span>
                  ))}
                </div>
              </div>
              <Section titre="Contradictions" items={examen.contradictions.length ? examen.contradictions : ["Aucune contradiction détectée"]} />
              <Section titre="Connaissances manquantes" items={examen.connaissances_manquantes} />
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Section({ titre, items }) {
  return (
    <div>
      <div className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">{titre}</div>
      <ul className="mt-1.5 space-y-1">
        {items.map((it, i) => <li key={i} className="text-xs text-white/60">→ {it}</li>)}
      </ul>
    </div>
  );
}
