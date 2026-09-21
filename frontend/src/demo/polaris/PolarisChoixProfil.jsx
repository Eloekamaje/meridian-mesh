// Choix du profil de la démonstration Polaris — page de la VRAIE application (route /demo),
// rendue dans la zone de contenu : la sidebar reste là. Choisir un profil ramène sur l'Atlas réel.
import { Sparkle, UserFocus, ChartLineUp, Compass, Lifebuoy, Code } from "@phosphor-icons/react";
import { PROFILS } from "./scenarios/gestionnaire";
import { useKiosque } from "./KiosqueProvider";

const ICONES = {
  gestionnaire: UserFocus,
  "ligne-affaires": ChartLineUp,
  architecte: Compass,
  "support-ti": Lifebuoy,
  developpeur: Code,
};

export default function PolarisChoixProfil() {
  const { demarrer } = useKiosque();
  return (
    <div className="h-full overflow-y-auto px-6 py-12 text-[#D8E2EA]" data-testid="polaris-welcome">
      <div className="mx-auto max-w-[1000px]">
        <div className="mb-2 flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.3em] text-[#60A5FA]">
          <Sparkle size={13} weight="fill" /> Démonstration Polaris
        </div>
        <h1 className="font-display text-4xl font-bold tracking-tight text-[#F2F6F8]" data-testid="polaris-titre">
          Cinq façons de voir Méridian travailler.
        </h1>
        <p className="mt-3 max-w-[640px] text-sm leading-relaxed text-[#7C93A8]">
          Chaque parcours est une conversation guidée avec Flore, l'assistante de Méridian : elle observe, découvre et prépare — puis montre ses preuves.
        </p>

        <div className="mt-10 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {PROFILS.map((p) => {
            const Icone = ICONES[p.id] || UserFocus;
            return (
              <button
                key={p.id}
                disabled={!p.disponible}
                onClick={() => demarrer(p.id)}
                data-testid={`polaris-profil-${p.id}`}
                title={p.disponible ? p.phrase : "Disponible prochainement"}
                className={`group min-h-[44px] rounded-xl border p-5 text-left transition-all ${
                  p.disponible
                    ? "border-[rgba(148,163,184,0.2)] bg-[#0F1D28] hover:-translate-y-0.5 hover:border-[#60A5FA]/50 hover:shadow-[0_8px_32px_rgba(96,165,250,0.08)]"
                    : "cursor-not-allowed border-[rgba(148,163,184,0.08)] bg-[#0F1D28]/40 opacity-50"
                }`}
              >
                <div className="flex items-center justify-between">
                  <Icone size={22} className={p.disponible ? "text-[#60A5FA]" : "text-[#7C93A8]"} />
                  {!p.disponible && (
                    <span className="rounded-full border border-[rgba(148,163,184,0.2)] px-2 py-0.5 font-code text-[9px] uppercase tracking-widest text-[#7C93A8]">
                      Bientôt
                    </span>
                  )}
                </div>
                <div className="mt-3 font-display text-lg font-semibold text-[#F2F6F8]">{p.titre}</div>
                <div className="mt-1 text-[12px] leading-snug text-[#7C93A8]">{p.phrase}</div>
              </button>
            );
          })}
        </div>

        <p className="mt-10 text-center font-code text-[10px] text-[#7C93A8]" data-testid="polaris-mention-fictif">
          Démonstration sur données fictives — aucune connexion à un environnement réel.
        </p>
      </div>
    </div>
  );
}
