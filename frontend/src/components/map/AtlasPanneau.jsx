import { Star } from "@phosphor-icons/react";
import { idNumerique } from "@/lib/atlasGraph";
import { couleurDomaine, NATURES_EVENEMENT, VERBES } from "@/lib/domaines";
import { recents } from "@/lib/memoire";
import { RelationDetail, DomaineDetail, ComparaisonDomaines, Section } from "./details";
import PanneauLateral from "./PanneauLateral";

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

// Le détail d'un DOMAINE, d'une relation, d'une comparaison ou d'une liste : le même panneau que celui d'un jumeau (PanneauLateral),
// avec ses propres informations. L'ancien panneau à onglets « Détail / Chronologie » n'existe plus : la chronologie d'un domaine
// est une rubrique de son détail.
export default function AtlasPanneau({
  comparaison, selectedRelation, domaineSel,
  statsDomaine, actionsDomaine, confirmerRelation,
  eventsVisibles = [], jumeauPar,
  presentation = "colonne", // "colonne" | "superposee" | "feuillet"
  masquee = false, // Flore occupe la colonne droite : les deux se remplacent, jamais côte à côte
  onActionSituation,
  mesh, situations, vueListe,
  favorisIds = [], onBasculerFavori, onChoisirJumeau, onChoisirSituation,
  onFermer,
}) {
  const ouvert = !!(comparaison || selectedRelation || domaineSel || vueListe);
  if (masquee || !ouvert) return null;

  const kicker = vueListe ? TITRES_LISTES[vueListe] : selectedRelation ? "Relation" : comparaison ? "Comparaison" : `Domaine`;
  const couleur = domaineSel && !selectedRelation && !comparaison && !vueListe ? couleurDomaine(domaineSel) : null;

  // Chronologie du domaine : les événements des jumeaux de ce domaine
  const idsDomaine = new Set((mesh?.jumeaux || []).filter((j) => j.domaine === domaineSel).map((j) => j.id));
  const evenements = eventsVisibles.filter((e) => idsDomaine.has(e.jumeau));

  return (
    <PanneauLateral kicker={kicker} couleur={couleur} onFermer={onFermer} presentation={presentation} testid="panneau-domaine">
      {vueListe ? (
        <ListePersonnelle vueListe={vueListe} mesh={mesh} situations={situations} favorisIds={favorisIds} onBasculerFavori={onBasculerFavori} onChoisirJumeau={onChoisirJumeau} onChoisirSituation={onChoisirSituation} />
      ) : comparaison ? (
        <ComparaisonDomaines a={comparaison.a} b={comparaison.b} statsDomaine={statsDomaine} />
      ) : selectedRelation ? (
        <RelationDetail rel={selectedRelation} jumeauPar={jumeauPar} onConfirmer={confirmerRelation} />
      ) : (
        <div className="space-y-4">
          <DomaineDetail label={domaineSel} stats={statsDomaine(domaineSel)} actions={actionsDomaine} onActionSituation={onActionSituation} />
          <Section titre="Chronologie" cle="chronologie" compte={evenements.length}>
            <ul className="space-y-3" data-testid="domaine-chronologie">
              {evenements.map((e) => {
                const j = jumeauPar(e.jumeau);
                const c = NATURES_EVENEMENT[e.nature] || "#7C93A8";
                return (
                  <li key={e.uid} className="flex items-start gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: c }} />
                    <div>
                      <span className="font-code text-[10px]" style={{ color: couleurDomaine(j?.domaine) }}>{j?.nom || e.jumeau}</span>
                      <p className="text-xs leading-snug text-[#94A3B8]">{e.texte}</p>
                    </div>
                  </li>
                );
              })}
              {evenements.length === 0 && <li className="text-xs text-[#7C93A8]">Aucun événement récent dans ce domaine.</li>}
            </ul>
          </Section>
        </div>
      )}
    </PanneauLateral>
  );
}
