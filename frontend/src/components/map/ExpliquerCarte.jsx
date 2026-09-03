import { X } from "@phosphor-icons/react";
import { ETATS_RELATION, MATURITES, couleurDomaine } from "@/lib/domaines";

// « Expliquer cette carte » — version textuelle et structurée de l'Atlas (WCAG 2.2 AA)
export default function ExpliquerCarte({ mesh, fermer, domaineActif, jumeauPar, selection }) {
  if (!mesh) return null;
  const jumeaux = mesh.jumeaux || [];
  const visibles = jumeaux.filter((j) => !j.anonyme);
  const restreints = jumeaux.length - visibles.length;
  const parEtat = {};
  (mesh.relations || []).forEach((r) => { parEtat[r.etat] = (parEtat[r.etat] || 0) + 1; });

  return (
    <aside
      role="complementary"
      aria-label="Description textuelle de la carte du Mesh"
      className="glass absolute bottom-4 right-4 top-16 z-20 flex w-[380px] max-w-[92vw] flex-col overflow-hidden rounded-xl"
      data-testid="expliquer-carte-panel"
    >
      <div className="flex items-center justify-between border-b border-[#E5E5E3] px-4 py-3">
        <h2 className="font-display text-sm font-bold text-[#111110]">Expliquer cette carte</h2>
        <button onClick={fermer} data-testid="expliquer-carte-fermer" title="Fermer la description" className="rounded-md p-1 text-[#71716D] transition-colors hover:bg-[#F0F0EE] hover:text-[#111110]">
          <X size={14} />
        </button>
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto p-4 text-xs leading-relaxed text-[#3F3F3C]">
        <p data-testid="expliquer-resume">
          Cette carte représente le Mesh : {(mesh.regions || []).length} domaines, {visibles.length} jumeaux visibles
          {restreints > 0 ? ` (${restreints} restreint${restreints > 1 ? "s" : ""} par votre périmètre)` : ""} et {(mesh.relations || []).length} relations connues.
        </p>

        {domaineActif && (
          <section>
            <h3 className="font-code text-[10px] uppercase tracking-[0.18em] text-[#71716D]">Position actuelle</h3>
            <p className="mt-1" data-testid="expliquer-position">
              Le centre de votre vue se trouve dans le domaine {domaineActif}. La carte est continue : faites-la glisser pour découvrir les domaines voisins à la même échelle.
            </p>
          </section>
        )}

        <section>
          <h3 className="font-code text-[10px] uppercase tracking-[0.18em] text-[#71716D]">Domaines</h3>
          <ul className="mt-1.5 space-y-1.5">
            {(mesh.regions || []).map((r) => {
              const n = visibles.filter((j) => j.domaine === r.label).length;
              const mat = r.maturite?.niveau;
              return (
                <li key={r.id} className="flex items-baseline gap-2" data-testid={`expliquer-domaine-${r.label}`}>
                  <span className="h-1.5 w-1.5 shrink-0 translate-y-[-1px] rounded-full" style={{ backgroundColor: couleurDomaine(r.label) }} />
                  <span>
                    <strong className="text-[#111110]">{r.label}</strong> — {n} jumeau{n > 1 ? "x" : ""} accessible{n > 1 ? "s" : ""}
                    {mat ? `, maturité « ${mat} »` : ""}.
                  </span>
                </li>
              );
            })}
          </ul>
        </section>

        <section>
          <h3 className="font-code text-[10px] uppercase tracking-[0.18em] text-[#71716D]">Relations par état de connaissance</h3>
          <ul className="mt-1.5 space-y-1">
            {Object.entries(ETATS_RELATION).map(([k, v]) =>
              parEtat[k] ? (
                <li key={k} data-testid={`expliquer-etat-${k}`}>
                  <strong className="text-[#111110]">{parEtat[k]}</strong> {v.label.toLowerCase()}{parEtat[k] > 1 && !v.label.endsWith("e") ? "s" : ""}
                </li>
              ) : null
            )}
          </ul>
        </section>

        {selection.length > 0 && (
          <section>
            <h3 className="font-code text-[10px] uppercase tracking-[0.18em] text-[#71716D]">Sélection courante</h3>
            <p className="mt-1" data-testid="expliquer-selection">
              {selection.length} jumeau{selection.length > 1 ? "x" : ""} sélectionné{selection.length > 1 ? "s" : ""} : {selection.map((id) => jumeauPar(id)?.nom || id).join(", ")}.
              Cette sélection constitue le contexte de Flore.
            </p>
          </section>
        )}

        <p className="border-t border-[#F0F0EE] pt-3 font-code text-[10px] text-[#71716D]">
          Navigation : clic = sélection · clic sur une porte = chemin vers le domaine · double-clic = explorer (déplacement animé, zoom inchangé) · molette = zoom explicite · lasso = sélection multiple.
        </p>
      </div>
    </aside>
  );
}
