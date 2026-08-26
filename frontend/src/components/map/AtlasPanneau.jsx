import { useEffect, useState } from "react";
import { X, SidebarSimple } from "@phosphor-icons/react";
import { COUCHES } from "@/lib/atlasGraph";
import { couleurDomaine, NATURES_EVENEMENT } from "@/lib/domaines";
import { RelationDetail, DomaineDetail, ComparaisonDomaines, TwinDetail } from "./details";

export default function AtlasPanneau({
  onglet, setOnglet,
  comparaison, selectedRelation, selected, domaineSel,
  statsDomaine, actionsDomaine, confirmerRelation,
  eventsVisibles, jumeauPar,
}) {
  // Refermé par défaut sur les petits écrans pour laisser la carte respirer
  const [ouvert, setOuvert] = useState(() => typeof window !== "undefined" && window.innerWidth >= 1500);

  // Repli automatique quand la fenêtre devient petite (redimensionnement)
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1500px)");
    const maj = (e) => { if (!e.matches) setOuvert(false); };
    mq.addEventListener("change", maj);
    return () => mq.removeEventListener("change", maj);
  }, []);

  // Toute nouvelle sélection rouvre le panneau
  useEffect(() => {
    if (comparaison || selectedRelation || selected || domaineSel) setOuvert(true);
  }, [comparaison, selectedRelation, selected, domaineSel]);

  if (!ouvert) {
    return (
      <button
        onClick={() => setOuvert(true)}
        data-testid="panneau-ouvrir-btn"
        title="Ouvrir le panneau Détail / Chronologie"
        className="glass absolute right-4 top-4 z-10 flex items-center gap-1.5 rounded-xl px-3 py-2 font-code text-[10px] uppercase tracking-[0.15em] text-[#52524F] transition-colors hover:text-[#111110]"
      >
        <SidebarSimple size={14} /> Détail
      </button>
    );
  }

  return (
    <aside className="glass absolute right-4 top-4 z-10 flex max-h-[calc(100%-6rem)] w-72 flex-col overflow-hidden rounded-xl xl:w-80" data-testid="map-side-panel">
      <div className="flex border-b border-[#E5E5E3]">
        {[["detail", "Détail"], ["chrono", "Chronologie"]].map(([id, label]) => (
          <button
            key={id}
            onClick={() => setOnglet(id)}
            data-testid={`map-tab-${id}`}
            className={`flex-1 px-3 py-2.5 font-code text-[10px] uppercase tracking-[0.2em] transition-colors ${
              onglet === id ? "bg-[#F0F0EE] text-[#111110]" : "text-[#71716D] hover:text-[#3F3F3C]"
            }`}
          >
            {label}
          </button>
        ))}
        <button onClick={() => setOuvert(false)} data-testid="panneau-fermer-btn" title="Replier le panneau" className="px-2.5 text-[#71716D] transition-colors hover:text-[#111110]">
          <X size={13} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {onglet === "detail" ? (
          comparaison ? (
            <ComparaisonDomaines a={comparaison.a} b={comparaison.b} statsDomaine={statsDomaine} />
          ) : selectedRelation ? (
            <RelationDetail rel={selectedRelation} jumeauPar={jumeauPar} onConfirmer={confirmerRelation} />
          ) : selected ? (
            <TwinDetail selected={selected} />
          ) : domaineSel ? (
            <DomaineDetail label={domaineSel} stats={statsDomaine(domaineSel)} actions={actionsDomaine} />
          ) : (
            <p className="text-xs text-[#71716D]">
              Sélectionnez un jumeau, une relation ou un domaine. Double-clic sur un domaine pour y entrer ; le zoom révèle progressivement le contenu.
            </p>
          )
        ) : (
          <ul className="space-y-3" data-testid="map-chrono-list">
            {eventsVisibles.map((e) => {
              const j = jumeauPar(e.jumeau);
              const c = NATURES_EVENEMENT[e.nature] || "#71716D";
              const dyn = COUCHES.find(([id]) => id === (e.dynamique || "operationnelle"));
              return (
                <li key={e.uid} className="ticker-item flex items-start gap-2">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: c }} />
                  <div>
                    <div className="flex items-center gap-1.5">
                      <span className="font-code text-[10px]" style={{ color: couleurDomaine(j?.domaine) }}>{j?.nom || e.jumeau}</span>
                      {dyn && <span className="font-code text-[8px] uppercase tracking-wider text-[#71716D]">{dyn[1]}</span>}
                    </div>
                    <p className="text-xs leading-snug text-[#52524F]">{e.texte}</p>
                  </div>
                </li>
              );
            })}
            {eventsVisibles.length === 0 && <li className="text-xs text-[#71716D]">Aucun événement sur les dynamiques visibles.</li>}
          </ul>
        )}
      </div>
    </aside>
  );
}
