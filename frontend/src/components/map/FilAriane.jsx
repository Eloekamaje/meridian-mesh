// Fil d'Ariane PASSIF : reflète le domaine sous le centre du viewport (stabilisé 400 ms).
// Il ne déplace jamais la caméra ; les actions sont explicites (ajuster à la vue, sélection).
export default function FilAriane({
  domaineActif,
  selection,
  revenirSelection,
  ajusterVue,
  dansSituation,
  situationTitre,
}) {
  if (!domaineActif && selection.length === 0 && !dansSituation) return null;
  return (
    <div className="glass pointer-events-auto flex items-center gap-2 rounded-xl px-4 py-2" data-testid="breadcrumb">
      <button
        onClick={ajusterVue}
        className="text-xs text-[#94A3B8] transition-colors hover:text-[#F2F6F8]"
        data-testid="breadcrumb-mesh"
        title="Ajuster à la vue — tout le Mesh"
      >
        Mesh global
      </button>
      {domaineActif && !dansSituation && (
        <>
          <span className="text-[#7C93A8]">›</span>
          <span className="text-xs font-semibold text-[#F2F6F8]" data-testid="breadcrumb-domaine">
            Domaine {domaineActif}
          </span>
        </>
      )}
      {dansSituation && (
        <>
          <span className="text-[#7C93A8]">›</span>
          <span className="text-xs font-semibold text-[#60A5FA]" data-testid="breadcrumb-situation">
            {situationTitre || "Analyse de situation"}
          </span>
        </>
      )}
      {selection.length > 0 && !dansSituation && (
        <button
          onClick={revenirSelection}
          data-testid="nav-selection"
          className="rounded-md border border-[rgba(148,163,184,0.16)] px-2 py-0.5 font-code text-[9px] text-[#94A3B8] transition-colors hover:border-[#60A5FA]/50 hover:text-[#F2F6F8]"
        >
          Revenir à ma sélection ({selection.length})
        </button>
      )}
    </div>
  );
}
