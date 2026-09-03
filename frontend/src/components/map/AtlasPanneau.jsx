import { useEffect, useState } from "react";
import { X, SidebarSimple, Star } from "@phosphor-icons/react";
import { COUCHES, idNumerique } from "@/lib/atlasGraph";
import { couleurDomaine, NATURES_EVENEMENT, VERBES } from "@/lib/domaines";
import { recents } from "@/lib/memoire";
import { RelationDetail, DomaineDetail, ComparaisonDomaines, TwinDetail } from "./details";

const STATUTS_CLOS = ["ignorée", "classée", "décidée"];
const TITRES_LISTES = {
  favoris: "Favoris",
  recents: "Consultés récemment",
  investigations: "Investigations en cours",
  situations: "Situations actives",
};

// Ligne jumeau cliquable (favoris, récents)
function LigneJumeau({ j, favori, onBasculerFavori, onChoisir }) {
  return (
    <div className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 transition-colors hover:bg-[#F0F0EE]">
      <button onClick={() => onChoisir(j.id)} data-testid={`liste-jumeau-${j.id}`} className="flex min-w-0 flex-1 items-center gap-2 text-left">
        <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: couleurDomaine(j.domaine) }} />
        <span className="min-w-0">
          <span className="block truncate text-xs font-semibold text-[#111110]">{j.nom}</span>
          <span className="block font-code text-[9px] text-[#71716D]">{idNumerique(j.id)} · {j.domaine}</span>
        </span>
      </button>
      {onBasculerFavori && (
        <button
          onClick={() => onBasculerFavori(j.id)}
          title={favori ? "Retirer des favoris" : "Ajouter aux favoris"}
          data-testid={`liste-favori-${j.id}`}
          className={`shrink-0 transition-colors ${favori ? "text-[#B45309]" : "text-[#D4D4D0] hover:text-[#B45309]"}`}
        >
          <Star size={13} weight={favori ? "fill" : "regular"} />
        </button>
      )}
    </div>
  );
}

function LigneSituation({ s, onChoisir }) {
  const v = VERBES[s.verbe];
  return (
    <button onClick={() => onChoisir(s.id)} data-testid={`liste-situation-${s.id}`} className="w-full rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-[#F0F0EE]">
      <span className="block truncate text-xs font-semibold text-[#111110]">{s.titre}</span>
      <span className="block font-code text-[9px]" style={{ color: v?.couleur || "#71716D" }}>
        {v?.label || s.verbe} · {(s.jumeaux || []).length} jumeau{(s.jumeaux || []).length > 1 ? "x" : ""}
      </span>
    </button>
  );
}

// Vue liste plein panneau (barre verticale personnelle)
function ListePersonnelle({ vueListe, mesh, situations, favorisIds, onBasculerFavori, onChoisirJumeau, onChoisirSituation }) {
  const js = mesh?.jumeaux || [];
  const parId = (id) => js.find((j) => j.id === id);
  const actives = (situations || []).filter((s) => !STATUTS_CLOS.includes(s.statut));

  let contenuListe = null;
  if (vueListe === "favoris") {
    const favs = favorisIds.map(parId).filter(Boolean);
    contenuListe = favs.length
      ? favs.map((j) => <LigneJumeau key={j.id} j={j} favori onBasculerFavori={onBasculerFavori} onChoisir={onChoisirJumeau} />)
      : <p className="px-2 text-xs text-[#71716D]">Aucun favori — étoilez un jumeau depuis son détail.</p>;
  } else if (vueListe === "recents") {
    const recs = recents().map(parId).filter(Boolean);
    contenuListe = recs.length
      ? recs.map((j) => <LigneJumeau key={j.id} j={j} favori={favorisIds.includes(j.id)} onBasculerFavori={onBasculerFavori} onChoisir={onChoisirJumeau} />)
      : <p className="px-2 text-xs text-[#71716D]">Aucun jumeau consulté pour le moment.</p>;
  } else if (vueListe === "investigations") {
    const inv = actives.filter((s) => s.verbe === "a_comprendre");
    contenuListe = inv.length
      ? inv.map((s) => <LigneSituation key={s.id} s={s} onChoisir={onChoisirSituation} />)
      : <p className="px-2 text-xs text-[#71716D]">Aucune investigation en cours.</p>;
  } else if (vueListe === "situations") {
    contenuListe = actives.length
      ? actives.map((s) => <LigneSituation key={s.id} s={s} onChoisir={onChoisirSituation} />)
      : <p className="px-2 text-xs text-[#71716D]">Aucune situation active.</p>;
  }

  return (
    <div className="space-y-1" data-testid={`panneau-liste-${vueListe}`}>
      <h4 className="px-2 font-code text-[9px] uppercase tracking-[0.2em] text-[#71716D]">{TITRES_LISTES[vueListe]}</h4>
      {contenuListe}
    </div>
  );
}

export default function AtlasPanneau({
  onglet, setOnglet,
  comparaison, selectedRelation, selected, domaineSel,
  statsDomaine, actionsDomaine, confirmerRelation,
  eventsVisibles, jumeauPar,
  presentation = "flottant", // "flottant" (desktop, panneau latéral) | "feuillet" (tablette/mobile, bottom sheet)
  mesh, situations, vueListe, setVueListe,
  favorisIds = [], onBasculerFavori, onChoisirJumeau, onChoisirSituation, onRelancerRecherche,
  onFermer,
}) {
  const feuillet = presentation === "feuillet";
  // Refermé par défaut sur les petits écrans pour laisser la carte respirer
  const [ouvert, setOuvert] = useState(false);
  const [replie, setReplie] = useState(false); // état réduit de la bottom sheet (poignée + titre)

  // Repli automatique quand la fenêtre devient petite (redimensionnement)
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1500px)");
    const maj = (e) => { if (!e.matches) setOuvert(false); };
    mq.addEventListener("change", maj);
    return () => mq.removeEventListener("change", maj);
  }, []);

  // Toute nouvelle sélection ou liste rouvre le panneau (sans jamais déplacer la carte)
  useEffect(() => {
    if (comparaison || selectedRelation || selected || domaineSel || vueListe) { setOuvert(true); setReplie(false); }
  }, [comparaison, selectedRelation, selected, domaineSel, vueListe]);

  const titre = selected?.nom || domaineSel || (selectedRelation ? "Relation" : comparaison ? "Comparaison" : vueListe ? TITRES_LISTES[vueListe] : "Atlas");

  const entete = (
    <div className="flex border-b border-[#E5E5E3]">
      {[["detail", "Détail"], ["chrono", "Chronologie"]].map(([id, label]) => (
        <button
          key={id}
          onClick={() => { setVueListe?.(null); setOnglet(id); }}
          data-testid={`map-tab-${id}`}
          className={`flex-1 px-3 py-2.5 font-code text-[10px] uppercase tracking-[0.2em] transition-colors ${
            !vueListe && onglet === id ? "bg-[#F0F0EE] text-[#111110]" : "text-[#71716D] hover:text-[#3F3F3C]"
          }`}
        >
          {label}
        </button>
      ))}
      <button
        onClick={() => { setOuvert(false); onFermer?.(); }}
        data-testid="panneau-fermer-btn" title="Replier le panneau" className="px-2.5 text-[#71716D] transition-colors hover:text-[#111110]"
      >
        <X size={13} />
      </button>
    </div>
  );

  const contenu = (
    <div className="flex-1 overflow-y-auto p-4">
      {vueListe ? (
        <ListePersonnelle
          vueListe={vueListe} mesh={mesh} situations={situations}
          favorisIds={favorisIds} onBasculerFavori={onBasculerFavori}
          onChoisirJumeau={onChoisirJumeau} onChoisirSituation={onChoisirSituation}
        />
      ) : onglet === "detail" ? (
        comparaison ? (
          <ComparaisonDomaines a={comparaison.a} b={comparaison.b} statsDomaine={statsDomaine} />
        ) : selectedRelation ? (
          <RelationDetail rel={selectedRelation} jumeauPar={jumeauPar} onConfirmer={confirmerRelation} />
        ) : selected ? (
          <TwinDetail selected={selected} favori={favorisIds.includes(selected.id)} onBasculerFavori={onBasculerFavori} />
        ) : domaineSel ? (
          <DomaineDetail label={domaineSel} stats={statsDomaine(domaineSel)} actions={actionsDomaine} />
        ) : (
          <p className="text-xs text-[#71716D]">
            Sélectionnez un jumeau, une relation ou un domaine. Double-clic : explorer (déplacement animé, zoom inchangé) ; la carte est continue — les domaines voisins se découvrent en la faisant glisser.
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
  );

  // Le panneau ne s'ouvre QUE sur sélection ou liste personnelle (règle PO : jamais d'état vide qui obstrue la carte)
  const peutOuvrir = !!(comparaison || selectedRelation || selected || domaineSel || vueListe);

  if (!ouvert) {
    if (!peutOuvrir) return null;
    return feuillet ? (
      <button
        onClick={() => { setOnglet("detail"); setOuvert(true); }}
        data-testid="panneau-ouvrir-btn"
        title="Ouvrir le panneau Détail / Chronologie"
        className="glass absolute bottom-20 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1.5 rounded-full px-4 py-2.5 font-code text-[10px] uppercase tracking-[0.15em] text-[#52524F] transition-colors hover:text-[#111110]"
      >
        <SidebarSimple size={14} /> Détail
      </button>
    ) : (
      <button
        onClick={() => { setOnglet("detail"); setOuvert(true); }}
        data-testid="panneau-ouvrir-btn"
        title="Ouvrir le panneau Détail / Chronologie"
        className="glass absolute right-4 top-16 z-10 flex items-center gap-1.5 rounded-xl px-3 py-2 font-code text-[10px] uppercase tracking-[0.15em] text-[#52524F] transition-colors hover:text-[#111110]"
      >
        <SidebarSimple size={14} /> Détail
      </button>
    );
  }

  // Bottom sheet : superposée à la carte (jamais de redimensionnement), 3 états
  // (fermée → réduite avec titre → complète), fermeture par la poignée ou le fond.
  if (feuillet) {
    return (
      <aside
        className="glass absolute inset-x-0 bottom-0 z-20 flex max-h-[60vh] flex-col overflow-hidden rounded-t-2xl border-t border-[#E5E5E3] shadow-2xl"
        data-testid="map-side-panel"
        data-state={replie ? "reduit" : "complet"}
      >
        <button
          onClick={() => setReplie((r) => !r)}
          data-testid="feuillet-poignee"
          title={replie ? "Déplier le détail" : "Replier (état réduit)"}
          className="flex h-11 w-full shrink-0 flex-col items-center justify-center gap-0.5"
        >
          <span className="h-1 w-10 rounded-full bg-[#D8D8D4]" />
          <span className="font-code text-[9px] uppercase tracking-[0.15em] text-[#71716D]" data-testid="feuillet-titre">{titre}</span>
        </button>
        {!replie && (
          <>
            {entete}
            {contenu}
          </>
        )}
      </aside>
    );
  }

  return (
    <aside className="glass absolute right-4 top-16 z-10 flex max-h-[calc(100%-9rem)] w-72 flex-col overflow-hidden rounded-xl xl:w-80" data-testid="map-side-panel">
      {entete}
      {contenu}
    </aside>
  );
}
