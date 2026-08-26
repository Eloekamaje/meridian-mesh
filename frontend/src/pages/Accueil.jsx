import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkle, Compass, Newspaper, ArrowRight } from "@phosphor-icons/react";
import api from "@/lib/api";
import { usePerimetre } from "@/lib/perimetre";
import ComposerFlore from "@/components/ComposerFlore";

const SUGGESTIONS = {
  architecte: [
    "Comprendre les nouvelles dépendances",
    "Comparer l'architecture déclarée au comportement observé",
    "Reprendre la modernisation Oracle",
  ],
  default: [
    "Voir ce que mon jumeau a découvert",
    "Examiner les connaissances à confirmer",
    "Corriger une source en erreur",
  ],
};

export default function Accueil() {
  const navigate = useNavigate();
  const { persona, personas, version } = usePerimetre();
  const [recents, setRecents] = useState([]);
  const role = personas.find((p) => p.id === persona)?.role || "";
  const suggestions = /architect|urbanisation/i.test(role) ? SUGGESTIONS.architecte : SUGGESTIONS.default;
  const nom = personas.find((p) => p.id === persona)?.nom || "";

  useEffect(() => {
    api.get("/cases").then((r) => setRecents(r.data.filter((c) => c.statut !== "clos").slice(0, 2))).catch(() => {});
  }, [version]);

  const demander = (q) => window.dispatchEvent(new CustomEvent("meridian:flore-ask", { detail: q }));

  return (
    <div className="flex h-full flex-col items-center justify-center overflow-y-auto px-6 py-10" data-testid="accueil-page">
      <div className="w-full max-w-2xl">
        <h1 className="rise text-center font-display text-3xl font-black tracking-tight text-[#111110] sm:text-4xl" data-testid="accueil-titre">
          Que voulez-vous comprendre<br />dans votre SI ?
        </h1>
        <p className="rise mt-3 text-center text-sm text-[#52524F]" style={{ animationDelay: "60ms" }}>
          Flore mobilise les jumeaux et compose la représentation utile{nom ? ` — bonjour ${nom}` : ""}.
        </p>

        <div className="rise mt-8" style={{ animationDelay: "120ms" }}>
          <ComposerFlore testidPrefix="accueil-composer" />
        </div>

        <div className="rise mt-5 flex flex-wrap justify-center gap-2" style={{ animationDelay: "180ms" }} data-testid="accueil-suggestions">
          {suggestions.map((s) => (
            <button key={s} onClick={() => demander(s)} data-testid={`accueil-suggestion-${s.slice(0, 18)}`}
              className="rounded-full border border-[#E5E5E3] bg-white px-3.5 py-1.5 text-xs text-[#52524F] transition-colors hover:border-[#3730A3]/40 hover:text-[#3730A3]">
              {s}
            </button>
          ))}
        </div>

        <div className="rise mt-10 grid gap-2 sm:grid-cols-3" style={{ animationDelay: "240ms" }}>
          <button onClick={() => navigate("/actualites")} data-testid="accueil-actus" className="group rounded-xl border border-[#E5E5E3] bg-white p-4 text-left transition-colors hover:border-[#3730A3]/40">
            <Newspaper size={16} className="text-[#3730A3]" />
            <div className="mt-2 text-xs font-semibold text-[#111110]">Changements d'aujourd'hui</div>
            <div className="mt-0.5 font-code text-[9px] text-[#71716D]">Le briefing du Mesh</div>
          </button>
          {recents[0] && (
            <button onClick={() => navigate(`/travaux/${recents[0].id}`)} data-testid="accueil-reprendre" className="group rounded-xl border border-[#E5E5E3] bg-white p-4 text-left transition-colors hover:border-[#3730A3]/40">
              <Sparkle size={16} className="text-[#B45309]" />
              <div className="mt-2 truncate text-xs font-semibold text-[#111110]">Reprendre « {recents[0].titre} »</div>
              <div className="mt-0.5 font-code text-[9px] text-[#71716D]">Continuité du travail</div>
            </button>
          )}
          <button onClick={() => navigate("/atlas")} data-testid="accueil-explorer" className="group rounded-xl border border-[#E5E5E3] bg-white p-4 text-left transition-colors hover:border-[#3730A3]/40">
            <Compass size={16} className="text-[#0E7490]" />
            <div className="mt-2 text-xs font-semibold text-[#111110]">Explorer mon espace</div>
            <div className="mt-0.5 font-code text-[9px] text-[#71716D]">L'Atlas du Mesh</div>
          </button>
        </div>

        <p className="mt-8 text-center font-code text-[10px] text-[#71716D]" data-testid="accueil-pied">
          Une question simple peut rester temporaire — une conversation durable devient un Travail. <ArrowRight size={9} className="inline" />
        </p>
      </div>
    </div>
  );
}
