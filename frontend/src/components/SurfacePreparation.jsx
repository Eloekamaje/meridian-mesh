import { CircleNotch } from "@phosphor-icons/react";

// État local d'une surface pendant qu'elle prépare le résultat annoncé par Flore.
// Le statut de Flore décrit son activité ; celui-ci décrit le résultat en préparation.
// La vue précédente reste visible dessous (voile léger) jusqu'à ce que la nouvelle soit prête.
// Hors démonstration, ce composant n'est jamais monté.
export default function SurfacePreparation({ preparation, vierge = false, testid = "surface-preparation" }) {
  if (!preparation) return null;
  return (
    <div
      className={`pointer-events-none absolute inset-0 z-30 flex items-center justify-center transition-opacity duration-300 ${
        vierge ? "bg-[#071019]" : "bg-[#071019]/55 backdrop-blur-[2px]"
      }`}
      data-testid={testid}
      role="status"
      aria-live="polite"
    >
      <div className="max-w-[440px] rounded-xl border border-[#60A5FA]/25 bg-[#0F1D28]/95 px-5 py-4 text-center shadow-2xl">
        <div className="flex items-center justify-center gap-2">
          <CircleNotch size={14} className="animate-spin text-[#60A5FA]" />
          <span className="font-code text-[10px] uppercase tracking-[0.25em] text-[#60A5FA]">Préparation</span>
        </div>
        <p className="mt-2 text-sm font-semibold text-[#F2F6F8]" data-testid={`${testid}-titre`}>
          {preparation.titre}
        </p>
        {preparation.detail && (
          <p className="mt-1 text-[11px] leading-snug text-[#7C93A8]" data-testid={`${testid}-detail`}>
            {preparation.detail}
          </p>
        )}
      </div>
    </div>
  );
}
