import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, SquaresFour, Microphone, PaperPlaneTilt, X, Compass, ArrowsLeftRight, Eye, Scales, FileText, ChartLineUp } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import { useContexte } from "@/lib/contexte";
import { couleurDomaine } from "@/lib/domaines";

const CAPACITES = [
  { id: "explorer", label: "Explorer le Mesh", icon: Compass },
  { id: "comparer", label: "Comparer deux états", icon: ArrowsLeftRight },
  { id: "changement", label: "Analyser un changement", icon: ChartLineUp },
  { id: "surveiller", label: "Surveiller un phénomène", icon: Eye },
  { id: "decision", label: "Préparer une décision", icon: Scales },
  { id: "synthese", label: "Créer une synthèse", icon: FileText },
];

// Composer unique de Flore — jamais flottant, une place réservée dans le layout
export default function ComposerFlore({ placeholder = "Demandez à Flore…", compact = false, onEnvoyer, testidPrefix = "composer" }) {
  const navigate = useNavigate();
  const { mesh } = useMesh();
  const { selection, retirerJumeau, ouvrirFlore } = useContexte();
  const [texte, setTexte] = useState("");
  const [menuContexte, setMenuContexte] = useState(false);
  const [menuCapacites, setMenuCapacites] = useState(false);
  const [chips, setChips] = useState([]); // contexte attaché hors sélection Atlas
  const refMenus = useRef(null);

  useEffect(() => {
    const fermer = (e) => {
      if (refMenus.current && !refMenus.current.contains(e.target)) { setMenuContexte(false); setMenuCapacites(false); }
    };
    document.addEventListener("mousedown", fermer);
    return () => document.removeEventListener("mousedown", fermer);
  }, []);

  const envoyer = () => {
    const q = texte.trim();
    if (!q) return;
    const contexte = chips.length ? ` [Contexte : ${chips.map((c) => c.label).join(", ")}]` : "";
    setTexte("");
    setChips([]);
    if (onEnvoyer) onEnvoyer(q + contexte);
    else {
      window.dispatchEvent(new CustomEvent("meridian:flore-ask", { detail: q + contexte }));
      ouvrirFlore();
    }
  };

  const capacite = async (id) => {
    setMenuCapacites(false);
    if (id === "explorer") return navigate("/atlas");
    if (id === "comparer") {
      const d = new Date();
      d.setDate(d.getDate() - 7);
      return navigate(`/atlas?avant-apres=${d.toISOString().slice(0, 10)}`);
    }
    if (id === "surveiller") {
      if (!selection.length) return toast.info("Sélectionnez d'abord des jumeaux dans l'Atlas.");
      try {
        const { data } = await api.post("/delegations", { type: "surveillance", jumeaux: selection, duree_h: 24 });
        toast.success(`Surveillance confiée au Mesh — « ${data.tache} », visible dans Actualités → Suivis`);
      } catch (e) {
        toast.error(e.response?.data?.detail || "Délégation impossible");
      }
      return;
    }
    const questions = {
      changement: "Analyse le changement récent dans mon périmètre : causes probables, impacts, preuves.",
      decision: "Prépare une décision : options, impacts estimés et recommandation pour mon contexte actuel.",
      synthese: "Crée une synthèse de la situation actuelle de mon périmètre.",
    };
    window.dispatchEvent(new CustomEvent("meridian:flore-ask", { detail: questions[id] }));
    ouvrirFlore();
  };

  const ajouterChip = (label) => {
    if (!chips.some((c) => c.label === label)) setChips([...chips, { label }]);
    setMenuContexte(false);
  };

  return (
    <div className={compact ? "" : "w-full"} data-testid={testidPrefix}>
      {/* Chips de contexte */}
      {(selection.length > 0 || chips.length > 0) && (
        <div className="mb-2 flex flex-wrap gap-1.5" data-testid={`${testidPrefix}-chips`}>
          {selection.map((id) => {
            const j = mesh?.jumeaux.find((x) => x.id === id);
            const c = couleurDomaine(j?.domaine);
            return (
              <span key={id} className="flex items-center gap-1 rounded-full border px-2 py-0.5 font-code text-[10px]" style={{ color: c, borderColor: `${c}44`, backgroundColor: `${c}0D` }}>
                {j?.nom || id}
                <button onClick={() => retirerJumeau(id)} className="opacity-60 hover:opacity-100" aria-label={`Retirer ${j?.nom || id}`}><X size={10} /></button>
              </span>
            );
          })}
          {chips.map((c) => (
            <span key={c.label} className="flex items-center gap-1 rounded-full border border-[#E5E5E3] bg-[#F7F7F6] px-2 py-0.5 font-code text-[10px] text-[#52524F]">
              {c.label}
              <button onClick={() => setChips(chips.filter((x) => x.label !== c.label))} className="opacity-60 hover:opacity-100" aria-label={`Retirer ${c.label}`}><X size={10} /></button>
            </span>
          ))}
        </div>
      )}

      <div className="rounded-2xl border border-[#E5E5E3] bg-white shadow-sm transition-colors focus-within:border-[#3730A3]/50" ref={refMenus}>
        <textarea
          value={texte}
          onChange={(e) => setTexte(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); envoyer(); } }}
          placeholder={placeholder}
          rows={compact ? 1 : 2}
          data-testid={`${testidPrefix}-input`}
          className="w-full resize-none rounded-t-2xl bg-transparent px-4 pt-3 text-sm text-[#111110] placeholder:text-[#71716D] focus:outline-none"
        />
        <div className="relative flex items-center gap-1.5 px-3 pb-2.5">
          {/* + Contexte */}
          <div className="relative">
            <button onClick={() => { setMenuContexte((m) => !m); setMenuCapacites(false); }} data-testid={`${testidPrefix}-contexte-btn`} className="flex items-center gap-1 rounded-full border border-[#E5E5E3] px-2.5 py-1 text-[11px] text-[#52524F] transition-colors hover:border-[#D4D4D0] hover:text-[#111110]">
              <Plus size={12} /> Contexte
            </button>
            {menuContexte && (
              <div className="glass absolute bottom-9 left-0 z-40 w-60 rounded-xl p-1.5" data-testid={`${testidPrefix}-contexte-menu`}>
                {[
                  [`Sélection Atlas (${selection.length} jumeau${selection.length > 1 ? "x" : ""})`, selection.length > 0, () => setMenuContexte(false)],
                  ["Période : aujourd'hui", true, () => ajouterChip("Aujourd'hui")],
                  ["Période : 30 derniers jours", true, () => ajouterChip("30 derniers jours")],
                  ["Actualité du Brief", true, () => ajouterChip("Actualité du Brief")],
                ].filter(([, ok]) => ok).map(([label, , fn]) => (
                  <button key={label} onClick={fn} data-testid={`${testidPrefix}-ctx-${label.slice(0, 16)}`} className="w-full rounded px-2.5 py-1.5 text-left text-[11px] text-[#52524F] hover:bg-[#F0F0EE] hover:text-[#111110]">
                    {label}
                  </button>
                ))}
              </div>
            )}
          </div>
          {/* Capacités */}
          <div className="relative">
            <button onClick={() => { setMenuCapacites((m) => !m); setMenuContexte(false); }} data-testid={`${testidPrefix}-capacites-btn`} className="flex items-center gap-1 rounded-full border border-[#E5E5E3] px-2.5 py-1 text-[11px] text-[#52524F] transition-colors hover:border-[#D4D4D0] hover:text-[#111110]">
              <SquaresFour size={12} /> Capacités
            </button>
            {menuCapacites && (
              <div className="glass absolute bottom-9 left-0 z-40 w-60 rounded-xl p-1.5" data-testid={`${testidPrefix}-capacites-menu`}>
                {CAPACITES.map(({ id, label, icon: Icon }) => (
                  <button key={id} onClick={() => capacite(id)} data-testid={`${testidPrefix}-cap-${id}`} className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-left text-[11px] text-[#52524F] hover:bg-[#F0F0EE] hover:text-[#111110]">
                    <Icon size={13} className="text-[#3730A3]" /> {label}
                  </button>
                ))}
              </div>
            )}
          </div>
          <button onClick={() => toast.info("La dictée vocale arrive prochainement.")} data-testid={`${testidPrefix}-micro`} title="Dicter (bientôt)" className="flex h-7 w-7 items-center justify-center rounded-full border border-[#E5E5E3] text-[#71716D] transition-colors hover:text-[#111110]">
            <Microphone size={13} />
          </button>
          <button onClick={envoyer} disabled={!texte.trim()} data-testid={`${testidPrefix}-envoyer`} title="Envoyer" className="ml-auto flex h-8 w-8 items-center justify-center rounded-full bg-[#3730A3] text-white transition-colors hover:bg-[#4338CA] disabled:opacity-30">
            <PaperPlaneTilt size={14} weight="fill" />
          </button>
        </div>
      </div>
    </div>
  );
}
