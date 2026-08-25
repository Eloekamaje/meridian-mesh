import { useEffect, useState } from "react";
import { Plus, SealCheck, Eye, ArrowLeft, ArrowRight } from "@phosphor-icons/react";
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

const ETAPES = ["Déclarer", "Connecter", "Observer", "Examiner", "Admettre"];

const OBSERVATIONS = [
  "Analyse du dépôt de code…",
  "Lecture du schéma de base de données…",
  "Ingestion des traces d'observabilité…",
  "Corrélation avec les incidents historiques…",
  "Inférence des capacités métier…",
  "Détection des relations supposées…",
];

const STATUTS = {
  "actif": { label: "actif", couleur: "#10B981" },
  "observation": { label: "observation", couleur: "#F59E0B" },
  "en construction": { label: "en construction", couleur: "#3B82F6" },
};

export default function Jumeaux() {
  const [jumeaux, setJumeaux] = useState([]);
  const { recharger } = useMesh();
  const { version } = usePerimetre();
  const [dialogue, setDialogue] = useState(false);
  const [examen, setExamen] = useState(null);

  const charger = () => api.get("/jumeaux").then((r) => setJumeaux(r.data)).catch(() => {});
  useEffect(() => { charger(); }, [version]);

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
          onClick={() => setDialogue(true)}
          data-testid="commander-jumeau-btn"
          className="flex items-center gap-2 rounded-md bg-[#3B82F6] px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#2F6FDB]"
        >
          <Plus size={16} weight="bold" /> Commander un jumeau
        </button>
      </header>

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

      <CommandeDialog ouvert={dialogue} onFermer={() => setDialogue(false)} onCree={() => { charger(); recharger(); }} />

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

function CommandeDialog({ ouvert, onFermer, onCree }) {
  const [etape, setEtape] = useState(1);
  const [form, setForm] = useState({ nom: "", proprietaire: "", mission: "", environnement: "production" });
  const [sources, setSources] = useState({ code: true, bdd: false, observabilite: true, incidents: false, documentation: false });
  const [progression, setProgression] = useState(0);
  const [lignes, setLignes] = useState([]);
  const [autonomie, setAutonomie] = useState("supervisé");
  const [envoi, setEnvoi] = useState(false);

  useEffect(() => {
    if (etape !== 3) return;
    setProgression(0);
    setLignes([]);
    let i = 0;
    const t = setInterval(() => {
      if (i < OBSERVATIONS.length) {
        setLignes((l) => [...l, OBSERVATIONS[i]]);
        i += 1;
        setProgression(Math.min(100, Math.round((i / OBSERVATIONS.length) * 100)));
      } else {
        clearInterval(t);
      }
    }, 650);
    return () => clearInterval(t);
  }, [etape]);

  const reinitialiser = () => {
    setEtape(1);
    setForm({ nom: "", proprietaire: "", mission: "", environnement: "production" });
    setSources({ code: true, bdd: false, observabilite: true, incidents: false, documentation: false });
    setProgression(0);
    setLignes([]);
    setAutonomie("supervisé");
  };

  const confirmer = async () => {
    setEnvoi(true);
    try {
      const { data: jumeau } = await api.post("/jumeaux", { ...form, sources });
      await api.post(`/jumeaux/${jumeau.id}/admettre`);
      toast.success(`${form.nom} admis dans le Mesh — mémoire enrichie`);
      onCree();
      onFermer();
      reinitialiser();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Admission impossible");
    } finally {
      setEnvoi(false);
    }
  };

  const manquantes = SOURCES.filter(([k]) => !sources[k]).map(([, l]) => l);
  const peutContinuer = etape === 1
    ? form.nom.trim() && form.proprietaire.trim() && form.mission.trim()
    : etape === 3 ? progression >= 100 : true;

  return (
    <Dialog open={ouvert} onOpenChange={(o) => { if (!o) { onFermer(); reinitialiser(); } }}>
      <DialogContent className="border-white/10 bg-[#0D0D0D] text-white sm:max-w-xl" data-testid="commande-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-lg font-bold">Commander un jumeau</DialogTitle>
        </DialogHeader>

        <div className="flex items-center gap-1" data-testid="commande-stepper">
          {ETAPES.map((label, i) => (
            <div key={label} className="flex flex-1 flex-col gap-1">
              <div className={`h-0.5 rounded-full transition-colors duration-300 ${i + 1 <= etape ? "bg-[#22D3EE]" : "bg-white/10"}`} />
              <span className={`font-code text-[9px] uppercase tracking-wider ${i + 1 === etape ? "text-white" : "text-white/35"}`}>{label}</span>
            </div>
          ))}
        </div>

        <div className="min-h-[260px]">
          {etape === 1 && (
            <div className="space-y-3" data-testid="etape-declarer">
              <Champ label="Nom de l'application" value={form.nom} onChange={(v) => setForm({ ...form, nom: v })} testid="champ-nom" placeholder="Ex. Remboursements" />
              <Champ label="Propriétaire" value={form.proprietaire} onChange={(v) => setForm({ ...form, proprietaire: v })} testid="champ-proprietaire" placeholder="Ex. Équipe Care — J. Morel" />
              <Champ label="Mission métier" value={form.mission} onChange={(v) => setForm({ ...form, mission: v })} testid="champ-mission" placeholder="Ex. Traite les demandes de remboursement" />
              <div>
                <label className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Environnement</label>
                <select
                  value={form.environnement}
                  onChange={(e) => setForm({ ...form, environnement: e.target.value })}
                  data-testid="champ-environnement"
                  className="mt-1.5 w-full rounded-md border border-white/10 bg-black/50 px-3 py-2 text-sm text-white focus:outline-none"
                >
                  <option value="production">production</option>
                  <option value="préproduction">préproduction</option>
                  <option value="recette">recette</option>
                </select>
              </div>
            </div>
          )}

          {etape === 2 && (
            <div data-testid="etape-connecter">
              <p className="text-sm text-white/55">Connectez les sources disponibles. Le jumeau apprendra de chacune d'elles.</p>
              <div className="mt-4 space-y-2.5">
                {SOURCES.map(([k, label]) => (
                  <label key={k} className="flex cursor-pointer items-center gap-3 rounded-md border border-white/[0.08] bg-white/[0.02] px-3 py-2.5 transition-colors hover:border-white/20">
                    <input
                      type="checkbox"
                      checked={!!sources[k]}
                      onChange={(e) => setSources({ ...sources, [k]: e.target.checked })}
                      data-testid={`source-${k}`}
                      className="h-4 w-4 accent-[#22D3EE]"
                    />
                    <span className="text-sm text-white/80">{label}</span>
                  </label>
                ))}
              </div>
            </div>
          )}

          {etape === 3 && (
            <div data-testid="etape-observer">
              <p className="text-sm text-white/55">Le jumeau apprend sans rejoindre le Mesh.</p>
              <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-white/[0.07]">
                <div className="h-full rounded-full bg-[#22D3EE] transition-[width] duration-500" style={{ width: `${progression}%` }} data-testid="observation-progress" />
              </div>
              <ul className="mt-4 space-y-2">
                {lignes.map((l, i) => (
                  <li key={i} className="ticker-item font-code text-xs text-white/60">→ {l}</li>
                ))}
              </ul>
            </div>
          )}

          {etape === 4 && (
            <div className="space-y-4" data-testid="etape-examiner">
              <Section titre="Identité découverte" items={[`${form.nom} — ${form.mission}`, `Propriétaire : ${form.proprietaire} · ${form.environnement}`]} />
              <Section titre="Capacités" items={["Répondre sur son périmètre", "Signaler ses dérives", "Expliquer ses relations connues"]} />
              <Section titre="Contradictions" items={["Aucune contradiction majeure détectée"]} />
              <Section titre="Connaissances manquantes" items={manquantes.length ? manquantes : ["Aucune source critique manquante"]} />
            </div>
          )}

          {etape === 5 && (
            <div className="space-y-4" data-testid="etape-admettre">
              <p className="text-sm text-white/55">
                Un humain valide l'entrée de <span className="font-semibold text-white">{form.nom}</span> dans le Mesh et définit son niveau d'autonomie.
              </p>
              <div>
                <label className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Niveau d'autonomie</label>
                <select
                  value={autonomie}
                  onChange={(e) => setAutonomie(e.target.value)}
                  data-testid="champ-autonomie"
                  className="mt-1.5 w-full rounded-md border border-white/10 bg-black/50 px-3 py-2 text-sm text-white focus:outline-none"
                >
                  <option value="supervisé">supervisé — propose, l'humain décide</option>
                  <option value="restreint">restreint — observe et signale</option>
                </select>
              </div>
              <div className="rounded-md border border-[#22D3EE]/30 bg-[#22D3EE]/[0.06] p-3 text-xs leading-relaxed text-white/65">
                Une fois admis, le jumeau devient une nouvelle source de compréhension pour Aurora et rejoint l'Atlas.
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-white/[0.08] pt-4">
          <button
            onClick={() => setEtape((e) => Math.max(1, e - 1))}
            disabled={etape === 1}
            data-testid="etape-precedente-btn"
            className="flex items-center gap-1.5 text-xs text-white/50 transition-colors hover:text-white disabled:opacity-30"
          >
            <ArrowLeft size={14} /> Précédent
          </button>
          {etape < 5 ? (
            <button
              onClick={() => setEtape((e) => e + 1)}
              disabled={!peutContinuer}
              data-testid="etape-suivante-btn"
              className="flex items-center gap-1.5 rounded-md bg-[#3B82F6] px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-[#2F6FDB] disabled:opacity-30"
            >
              Continuer <ArrowRight size={14} />
            </button>
          ) : (
            <button
              onClick={confirmer}
              disabled={envoi}
              data-testid="confirmer-admission-btn"
              className="flex items-center gap-1.5 rounded-md bg-[#FBBF24] px-4 py-2 text-xs font-semibold text-black transition-colors hover:bg-[#E5A910] disabled:opacity-40"
            >
              <SealCheck size={14} /> Admettre dans le Mesh
            </button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Champ({ label, value, onChange, placeholder, testid }) {
  return (
    <div>
      <label className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">{label}</label>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        data-testid={testid}
        className="mt-1.5 w-full rounded-md border border-white/10 bg-black/50 px-3 py-2 text-sm text-white placeholder:text-white/25 focus:border-[#22D3EE]/60 focus:outline-none"
      />
    </div>
  );
}
