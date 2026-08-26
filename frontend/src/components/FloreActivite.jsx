import { useEffect, useState } from "react";
import { Sparkle, Check } from "@phosphor-icons/react";

// Indicateur d'activité de Flore — les étapes se déroulent comme un raisonnement visible
const ETAPES = {
  defaut: ["S'informe dans le Mesh…", "Croise les sources concernées…", "Comprend la situation…"],
  rapport: ["Se saisit de la situation…", "Rassemble les preuves et les jumeaux concernés…", "Rédige son rapport…"],
  incident: ["Analyse la dérive en cours…", "Croise traces, incidents passés et règles récentes…", "Évalue la propagation…"],
  relation: ["Examine les signaux entre les jumeaux…", "Vérifie les preuves concordantes…", "Mesure la confiance…"],
  phenomene: ["Examine les signaux entre les jumeaux…", "Vérifie les preuves concordantes…", "Mesure la confiance…"],
  changement: ["Rejoue le scénario de changement…", "Mesure la propagation sur les dépendants…", "Évalue les options…"],
  travail: ["Relit la mémoire du travail…", "Repère où vous vous étiez arrêté…", "Rassemble le contexte…"],
};
const FINALE = "A tout ce qu'il faut.";

// Laisse aux étapes le temps de se dérouler même si la réponse arrive vite
export function delaiMin(promesse, ms = 2400) {
  return Promise.all([promesse, new Promise((r) => setTimeout(r, ms))]).then(([res]) => res);
}

export default function FloreActivite({ genre = "defaut", testid = "flore-activite" }) {
  const etapes = [...(ETAPES[genre] || ETAPES.defaut), FINALE];
  const [courant, setCourant] = useState(0);

  useEffect(() => {
    if (courant >= etapes.length - 1) return undefined;
    const t = setTimeout(() => setCourant((c) => c + 1), courant === etapes.length - 2 ? 900 : 750);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courant]);

  return (
    <div className="space-y-1.5 py-1" data-testid={testid} role="status" aria-live="polite">
      {etapes.slice(0, courant + 1).map((e, i) => {
        const active = i === courant;
        const finale = i === etapes.length - 1;
        return (
          <div key={i} className="rise flex items-center gap-2 font-code text-[11px]" style={{ animationDuration: "180ms" }}>
            {active && !finale ? (
              <Sparkle size={12} weight="fill" className="animate-pulse text-[#3730A3]" />
            ) : (
              <Check size={12} weight="bold" className={finale ? "text-[#047857]" : "text-[#71716D]/60"} />
            )}
            <span className={active ? (finale ? "font-semibold text-[#047857]" : "text-[#3F3F3C]") : "text-[#71716D]/70"}>
              Flore {e}
            </span>
            {active && !finale && (
              <span className="flex gap-0.5">
                {[0, 1, 2].map((d) => (
                  <span key={d} className="h-1 w-1 animate-bounce rounded-full bg-[#3730A3]/50" style={{ animationDelay: `${d * 150}ms` }} />
                ))}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
