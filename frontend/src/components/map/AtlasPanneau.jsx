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
    <div className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 transition-colors hover:bg-[rgba(148,163,184,0.10)]">
      <button onClick={() => onChoisir(j.id)} data-testid={`liste-jumeau-${j.id}`} className="flex min-w-0 flex-1 items-center gap-2 text-left">
        <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: couleurDomaine(j.domaine) }} />
        <span className="min-w-0">
          <span className="block truncate text-xs font-semibold text-[#F2F6F8]">{j.nom}</span>
          <span className="block font-code text-[9px] text-[#7C93A8]">{idNumerique(j.id)} · {j.domaine}</span>
        </span>
      </button>
      {onBasculerFavori && (
        <button
          onClick={() => onBasculerFavori(j.id)}
          title={favori ? "Retirer des favoris" : "Ajouter aux favoris"}
          data-testid={`liste-favori-${j.id}`}
          className={`shrink-0 transition-colors ${favori ? "text-[#F2B84B]" : "text-[#41576D] hover:text-[#F2B84B]"}`}
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
    <button onClick={() => onChoisir(s.id)} data-testid={`liste-situation-${s.id}`} className="w-full rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-[rgba(148,163,184,0.10)]">
      <span className="block truncate text-xs font-semibold text-[#F2F6F8]">{s.titre}</span>
      <span className="block font-code text-[9px]" style={{ color: v?.couleur || "#7C93A8" }}>
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
      : <p className="px-2 text-xs text-[#7C93A8]">Aucun favori — étoilez un jumeau depuis son détail.</p>;
  } else if (vueListe === "recents") {
    const recs = recents().map(parId).filter(Boolean);
    contenuListe = recs.length
      ? recs.map((j) => <LigneJumeau key={j.id} j={j} favori={favorisIds.includes(j.id)} onBasculerFavori={onBasculerFavori} onChoisir={onChoisirJumeau} />)
      : <p className="px-2 text-xs text-[#7C93A8]">Aucun jumeau consulté pour le moment.</p>;
  } else if (vueListe === "investigations") {
    const inv = actives.filter((s) => s.verbe === "a_comprendre");
    contenuListe = inv.length
      ? inv.map((s) => <LigneSituation key={s.id} s={s} onChoisir={onChoisirSituation} />)
      : <p className="px-2 text-xs text-[#7C93A8]">Aucune investigation en cours.</p>;
  } else if (vueListe === "situations") {
    contenuListe = actives.length
      ? actives.map((s) => <LigneSituation key={s.id} s={s} onChoisir={onChoisirSituation} />)
      : <p className="px-2 text-xs text-[#7C93A8]">Aucune situation active.</p>;
  }

  return (
    <div className="space-y-1" data-testid={`panneau-liste-${vueListe}`}>
      <h4 className="px-2 font-code text-[9px] uppercase tracking-[0.2em] text-[#7C93A8]">{TITRES_LISTES[vueListe]}</h4>
      {contenuListe}
    </div>
  );
}

export default function AtlasPanneau({
  onglet, setOnglet,
  comparaison, selectedRelation, selected, domaineSel,
  statsDomaine, actionsDomaine, confirmerRelation,
  eventsVisibles, jumeauPar,
  presentation = "colonne", // "colonne" (desktop, panneau latéral dans le layout) | "feuillet" (tablette/mobile, bottom sheet)
  masquee = false, // Flore ouverte : Flore occupe la colonne droite — les deux panneaux se remplacent, jamais côte à côte
  sansJumeau = false, // desktop : le détail jumeau vit dans sa colonne gauche (PanneauJumeau), ce panneau garde domaines/relations/listes
  onActionSituation,
  mesh, situations, vueListe, setVueListe,
  favorisIds = [], onBasculerFavori, onChoisirJumeau, onChoisirSituation, onRelancerRecherche,
  onFermer, statsTwin, onInterroger,
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

  // Sur desktop (sansJumeau), le détail jumeau vit dans sa colonne gauche — ce panneau garde le reste.
  const selectionActive = sansJumeau ? null : selected;

  // Toute nouvelle sélection ou liste rouvre le panneau (sans jamais déplacer la carte).
  // Sur desktop (sansJumeau), le détail jumeau vit dans sa colonne gauche — il n'ouvre pas ce panneau.
  useEffect(() => {
    if (comparaison || selectedRelation || selectionActive || domaineSel || vueListe) { setOuvert(true); setReplie(false); }
  }, [comparaison, selectedRelation, selectionActive, domaineSel, vueListe]);

  const titre = selectionActive?.nom || domaineSel || (selectedRelation ? "Relation" : comparaison ? "Comparaison" : vueListe ? TITRES_LISTES[vueListe] : "Atlas");

  const entete = (
    <div className="flex border-b border-[rgba(148,163,184,0.16)]">
      {[["detail", "Détail"], ["chrono", "Chronologie"]].map(([id, label]) => (
        <button
          key={id}
          onClick={() => { setVueListe?.(null); setOnglet(id); }}
          data-testid={`map-tab-${id}`}
          className={`flex-1 px-3 py-2.5 font-code text-[10px] uppercase tracking-[0.2em] transition-colors ${
            !vueListe && onglet === id ? "bg-[rgba(148,163,184,0.10)] text-[#F2F6F8]" : "text-[#7C93A8] hover:text-[#D8E2EA]"
          }`}
        >
          {label}
        </button>
      ))}
      <button
        onClick={() => { setOuvert(false); onFermer?.(); }}
        data-testid="panneau-fermer-btn" title="Replier le panneau" className="px-2.5 text-[#7C93A8] transition-colors hover:text-[#F2F6F8]"
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
        ) : selectionActive ? (
          <TwinDetail selected={selectionActive} favori={favorisIds.includes(selectionActive.id)} onBasculerFavori={onBasculerFavori} statsTwin={statsTwin} onInterroger={onInterroger} />
        ) : domaineSel ? (
          <DomaineDetail label={domaineSel} stats={statsDomaine(domaineSel)} actions={actionsDomaine} onActionSituation={onActionSituation} />
        ) : (
          <p className="text-xs text-[#7C93A8]">
            Sélectionnez un jumeau, une relation ou un domaine. Double-clic : explorer (déplacement animé, zoom inchangé) ; la carte est continue — les domaines voisins se découvrent en la faisant glisser.
          </p>
        )
      ) : (
        <ul className="space-y-3" data-testid="map-chrono-list">
          {eventsVisibles.map((e) => {
            const j = jumeauPar(e.jumeau);
            const c = NATURES_EVENEMENT[e.nature] || "#7C93A8";
            const dyn = COUCHES.find(([id]) => id === (e.dynamique || "operationnelle"));
            return (
              <li key={e.uid} className="ticker-item flex items-start gap-2">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: c }} />
                <div>
                  <div className="flex items-center gap-1.5">
                    <span className="font-code text-[10px]" style={{ color: couleurDomaine(j?.domaine) }}>{j?.nom || e.jumeau}</span>
                    {dyn && <span className="font-code text-[8px] uppercase tracking-wider text-[#7C93A8]">{dyn[1]}</span>}
                  </div>
                  <p className="text-xs leading-snug text-[#94A3B8]">{e.texte}</p>
                </div>
              </li>
            );
          })}
          {eventsVisibles.length === 0 && <li className="text-xs text-[#7C93A8]">Aucun événement sur les dynamiques visibles.</li>}
        </ul>
      )}
    </div>
  );

  // Le panneau ne s'ouvre QUE sur sélection ou liste personnelle (règle PO : jamais d'état vide qui obstrue la carte)
  const peutOuvrir = !!(comparaison || selectedRelation || selectionActive || domaineSel || vueListe);

  // Masqué pendant que Flore occupe la colonne droite (l'état interne est conservé :
  // à la fermeture de Flore, le panneau revient tel quel avec la même sélection)
  if (masquee) return null;

  if (!ouvert) {
    if (!peutOuvrir) return null;
    return feuillet ? (
      <button
        onClick={() => { setOnglet("detail"); setOuvert(true); }}
        data-testid="panneau-ouvrir-btn"
        title="Ouvrir le panneau Détail / Chronologie"
        className="glass absolute bottom-20 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1.5 rounded-full px-4 py-2.5 font-code text-[10px] uppercase tracking-[0.15em] text-[#94A3B8] transition-colors hover:text-[#F2F6F8]"
      >
        <SidebarSimple size={14} /> Détail
      </button>
    ) : (
      // Rail de réouverture : colonne fixe de 40 px à droite — rien ne flotte sur la carte
      <div className="flex w-10 shrink-0 flex-col items-center border-l border-[rgba(148,163,184,0.16)] bg-[#0F1D28]/70 py-3 backdrop-blur-xl" data-testid="panneau-rail">
        <button
          onClick={() => { setOnglet("detail"); setOuvert(true); }}
          data-testid="panneau-ouvrir-btn"
          title="Ouvrir le panneau Détail / Chronologie"
          className="flex h-8 w-8 items-center justify-center rounded-md text-[#7C93A8] transition-colors hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]"
        >
          <SidebarSimple size={14} />
        </button>
      </div>
    );
  }

  // Bottom sheet : superposée à la carte (jamais de redimensionnement), 3 états
  // (fermée → réduite avec titre → complète), fermeture par la poignée ou le fond.
  if (feuillet) {
    return (
      <aside
        className="glass absolute inset-x-0 bottom-0 z-20 flex max-h-[60vh] flex-col overflow-hidden rounded-t-2xl border-t border-[rgba(148,163,184,0.16)] shadow-2xl"
        data-testid="map-side-panel"
        data-state={replie ? "reduit" : "complet"}
      >
        <button
          onClick={() => setReplie((r) => !r)}
          data-testid="feuillet-poignee"
          title={replie ? "Déplier le détail" : "Replier (état réduit)"}
          className="flex h-11 w-full shrink-0 flex-col items-center justify-center gap-0.5"
        >
          <span className="h-1 w-10 rounded-full bg-[#5B7089]" />
          <span className="font-code text-[9px] uppercase tracking-[0.15em] text-[#7C93A8]" data-testid="feuillet-titre">{titre}</span>
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

  // Colonne latérale (façon Google Maps) : le panneau prend sa place dans le layout —
  // la carte se redimensionne, la mini-carte et les contrôles restent ancrés à leurs coins.
  return (
    <aside className="flex h-full w-80 shrink-0 flex-col overflow-hidden border-l border-[rgba(148,163,184,0.16)] bg-[#0F1D28]/85 backdrop-blur-xl xl:w-[336px]" data-testid="map-side-panel">
      {entete}
      {contenu}
    </aside>
  );
}
