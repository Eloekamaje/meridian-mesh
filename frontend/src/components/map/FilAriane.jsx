export default function FilAriane({
  domaineInterne, jumeauFocus, jumeauPar, historique, indexHist,
  allerHist, sortirDomaine, sortirJumeau, perimetreTravail, selection, revenirSelection,
}) {
  if (!domaineInterne && !jumeauFocus) return null;
  return (
    <div className="glass absolute left-1/2 top-4 z-10 flex -translate-x-1/2 items-center gap-2 rounded-xl px-4 py-2" data-testid="breadcrumb">
      <button
        onClick={() => allerHist(indexHist - 1)}
        disabled={indexHist <= 0}
        data-testid="nav-precedent"
        title="Précédent"
        className="text-xs text-[#52524F] transition-colors hover:text-[#111110] disabled:opacity-25"
      >
        ←
      </button>
      <button
        onClick={() => allerHist(indexHist + 1)}
        disabled={indexHist >= historique.length - 1}
        data-testid="nav-suivant"
        title="Suivant"
        className="text-xs text-[#52524F] transition-colors hover:text-[#111110] disabled:opacity-25"
      >
        →
      </button>
      <button onClick={sortirDomaine} className="text-xs text-[#52524F] transition-colors hover:text-[#111110]" data-testid="breadcrumb-mesh">
        Mesh global
      </button>
      {domaineInterne && (
        <>
          <span className="text-[#71716D]">›</span>
          {jumeauFocus ? (
            <button onClick={sortirJumeau} className="text-xs text-[#52524F] transition-colors hover:text-[#111110]" data-testid="breadcrumb-domaine">
              Domaine {domaineInterne}
            </button>
          ) : (
            <span className="text-xs font-semibold text-[#111110]" data-testid="breadcrumb-domaine-inactif">Domaine {domaineInterne}</span>
          )}
        </>
      )}
      {jumeauFocus && (
        <>
          <span className="text-[#71716D]">›</span>
          <span className="text-xs font-semibold text-[#111110]" data-testid="breadcrumb-jumeau">{jumeauPar(jumeauFocus)?.nom}</span>
        </>
      )}
      {perimetreTravail === domaineInterne && (
        <span className="rounded-full border border-[#0E7490]/40 bg-[#0E7490]/10 px-2 py-0.5 font-code text-[9px] text-[#0E7490]">
          périmètre de travail (filtre, pas sécurité)
        </span>
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
