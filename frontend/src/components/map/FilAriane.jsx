// Fil d'Ariane PASSIF : reflète le domaine sous le centre du viewport (stabilisé 400 ms).
// Il ne déplace jamais la caméra ; les actions sont explicites (ajuster à la vue, sélection).
export default function FilAriane({ domaineActif, selection, revenirSelection, ajusterVue }) {
  if (!domaineActif && selection.length === 0) return null;
  return (
    <div className="glass absolute left-1/2 top-4 z-10 flex -translate-x-1/2 items-center gap-2 rounded-xl px-4 py-2" data-testid="breadcrumb">
      <button
        onClick={ajusterVue}
        className="text-xs text-[#52524F] transition-colors hover:text-[#111110]"
        data-testid="breadcrumb-mesh"
        title="Ajuster à la vue — tout le Mesh"
      >
        Mesh global
      </button>
      {domaineActif && (
        <>
          <span className="text-[#71716D]">›</span>
          <span className="text-xs font-semibold text-[#111110]" data-testid="breadcrumb-domaine">
            Domaine {domaineActif}
          </span>
        </>
      )}
      {selection.length > 0 && (
        <button
          onClick={revenirSelection}
          data-testid="nav-selection"
          className="rounded-md border border-[#E5E5E3] px-2 py-0.5 font-code text-[9px] text-[#52524F] transition-colors hover:border-[#3730A3]/50 hover:text-[#111110]"
        >
          Revenir à ma sélection ({selection.length})
        </button>
      )}
    </div>
  );
}
