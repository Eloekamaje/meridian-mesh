import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { ReactFlow, Background, Controls, ControlButton, MiniMap, SelectionMode, ViewportPortal } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { X, Sparkle, CornersOut, MagnifyingGlass, Globe } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import { usePerimetre } from "@/lib/perimetre";
import { usePilotage } from "@/lib/pilotage";
import SurfacePreparation from "@/components/SurfacePreparation";
import { useContexte } from "@/lib/contexte";
import TwinNode from "@/components/map/TwinNode";
import NoeudGraphe from "@/components/map/NoeudGraphe";
import AreteGraphe from "@/components/map/AreteGraphe";
import AtlasEchelle from "@/components/map/AtlasEchelle";
import { analyserMesh, aretesGraphe, habillerNoeud, tailleDe, STYLE_ETAT } from "@/lib/atlasRendu";
import CielEtoile from "@/components/map/CielEtoile";
import RegionNode from "@/components/map/RegionNode";
import AreteOrthogonale from "@/components/map/AreteOrthogonale";
import AreteCorridor from "@/components/map/AreteCorridor";
import AtlasControle from "@/components/map/AtlasControle";
import AtlasToolbar from "@/components/map/AtlasToolbar";
import AtlasLegende from "@/components/map/AtlasLegende";
import AtlasPanneau from "@/components/map/AtlasPanneau";
import PanneauJumeau from "@/components/map/PanneauJumeau";
import FilAriane from "@/components/map/FilAriane";
import ExpliquerCarte from "@/components/map/ExpliquerCarte";
import useNavigationAtlas, { centreRendu, dansPolygone } from "@/components/map/useNavigationAtlas";
import { CENTRE_ROBOT } from "@/components/map/NoeudGraphe";
import useZoomSemantique from "@/components/map/useZoomSemantique";
import { NIVEAUX_ZOOM, construireGraphe, statsDuDomaine, idNumerique, placerLabels } from "@/lib/atlasGraph";
import { favoris, basculerFavori, noterRecent, noterRecherche } from "@/lib/memoire";
import { useRoutageFinal } from "@/lib/routage";

// Détection du dispositif : le responsive n'agit que sur le chrome, jamais sur le monde
function useMedia(requete) {
  const [m, setM] = useState(() => typeof window !== "undefined" && window.matchMedia(requete).matches);
  useEffect(() => {
    const mm = window.matchMedia(requete);
    const h = () => setM(mm.matches);
    mm.addEventListener("change", h);
    return () => mm.removeEventListener("change", h);
  }, [requete]);
  return m;
}
import { couleurDomaine, ETATS_RELATION, MATURITES } from "@/lib/domaines";
import { parseQuand, finDeJournee, fmtDate } from "@/lib/temps";

const nodeTypes = { twin: TwinNode, region: RegionNode };
const edgeTypes = { ortho: AreteOrthogonale, corridor: AreteCorridor };
// Rendu « graphe » (par défaut) : robots et liens courbes ; ?rendu=classique rétablit membranes/étoiles/corridors
// Au-delà, l'Atlas ne charge plus le graphe : il demande au serveur la vue (grappes, points ou jumeaux) de ce qui est à l'écran
const SEUIL_ECHELLE = 300;
const DELAI_MISE_EN_PAGE = 300; // transition du menu (200 ms) + montage du panneau
const DECALAGE_GRAPHE = CENTRE_ROBOT; // centre du robot dans son nœud
const DECALAGE_CLASSIQUE = { x: 30, y: 40 };
const nodeTypesGraphe = { twin: NoeudGraphe, region: RegionNode };
const edgeTypesGraphe = { ...edgeTypes, graphe: AreteGraphe };

export default function Atlas() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { mesh, jumeauPar, recharger } = useMesh();
  const { version, vueActive, rechargerVues, info } = usePerimetre();
  const [situations, setSituations] = useState([]);
  const focus = searchParams.get("focus");
  const situationParam = searchParams.get("situation");
  const selParam = searchParams.get("sel");
  const domaineParam = searchParams.get("domaine");
  const [selected, setSelected] = useState(null);
  const [selectedRelation, setSelectedRelation] = useState(null);
  const [events, setEvents] = useState([]);
  const [halo, setHalo] = useState(null);
  const [compteurs, setCompteurs] = useState({});
  const [onglet, setOnglet] = useState("chrono");
  const [couches, setCouches] = useState({ operationnelle: true, connaissance: true, mesh: true });
  const [modeTemps, setModeTemps] = useState("direct"); // direct | pause | replay | historique | avantapres
  const [dateRef, setDateRef] = useState(null); // ms — curseur temporel
  const [replaying, setReplaying] = useState(false);
  const [expliquerOuvert, setExpliquerOuvert] = useState(false);
  const direct = modeTemps === "direct";
  const [outil, setOutil] = useState("deplacement");
  const { selection, setSelection, domaineSel, setDomaineSel, focusCarte, commanderCarte, setFocusVisuel, ouvrirFlore, fermerFlore, floreOuverte, setAtlasCtx, atlasEtat, setAtlasEtat, demanderAFlore, preuveSurvolee, setRepliAuto } = useContexte();
  const pilote = usePilotage();
  const graphe = searchParams.get("rendu") !== "classique";
  const echelleSynth = Number(searchParams.get("echelle")) || null; // essai d'échelle : N jumeaux fictifs servis par le backend
  const echelle = !!echelleSynth || (mesh?.perimetre?.nb_autorises || 0) >= SEUIL_ECHELLE;
  const [domainesMasques, setDomainesMasques] = useState(() => new Set()); // légende-filtre : domaines décochés
  const analyse = useMemo(() => (graphe && mesh ? analyserMesh(mesh) : null), [graphe, mesh]);

  // Conservation de l'état de l'Atlas entre les pages : au retour, on restaure exactement
  // viewport, zoom, sélection et couches — jamais de fitView au retour (les liens partagés
  // avec paramètres d'URL priment sur l'état mémorisé)
  const restaurerEtat = !!(atlasEtat?.viewport) && !selParam && !domaineParam && !focus && !situationParam;
  const etatVif = useRef({});
  const etatRestaure = useRef(false);
  const [relFocus, setRelFocus] = useState(false);
  const [posOverrides, setPosOverrides] = useState({});
  const [survolJumeau, setSurvolJumeau] = useState(null);
  const [tooltipPos, setTooltipPos] = useState(null); // position de la mini-infobulle de survol (coords carte)
  const [relSurvolee, setRelSurvolee] = useState(null); // relation survolée (arête)
  const [relTooltipPos, setRelTooltipPos] = useState(null);
  const [couchesRel, setCouchesRel] = useState({ bcm: true, realite: true, ecarts: true });
  const [recherche, setRecherche] = useState("");
  // Couches cartographiques étendues (façon catégories Google Maps) : ne déplacent jamais les jumeaux,
  // elles modifient uniquement la visibilité et l'importance des éléments
  const [couchesCarte, setCouchesCarte] = useState({ situations: false, capacites: false, transformations: false });
  // Navigation personnelle : liste ouverte dans le panneau contextuel (favoris/récents/investigations/situations)
  const [vueListe, setVueListe] = useState(null);
  const [favorisIds, setFavorisIds] = useState(() => favoris());
  const onBasculerFavori = useCallback((id) => setFavorisIds(basculerFavori(id)), []);

  // Moteur Universel de Focus Situationnel (Illumination -> Plongeon cinématique -> Sanctuaire)
  const [theatreSituationnel, setTheatreSituationnel] = useState({
    actif: false,
    phase: "idle", // "idle" | "illumination" | "plongeon" | "sanctuaire" | "sortie"
    cibles: [],
    accents: [],
    titre: null,
  });
  const theatreTimerRef = useRef([]);
  const clearTheatreTimers = () => {
    theatreTimerRef.current.forEach(clearTimeout);
    theatreTimerRef.current = [];
  };

  const carteRef = useRef(null);
  const telemetrieRef = useRef(null); // readout curseur — mis à jour impérativement (pas de re-render)
  const [amorce, setAmorce] = useState(0);
  const [mesures, setMesures] = useState({}); // dimensions mesurées par React Flow, réinjectées dans le graphe
  const [zoomActuel, setZoomActuel] = useState(1);
  const [regionSurvolee, setRegionSurvolee] = useState(null); // membrane survolée {id, label} (proximité frontière)
  const [secteurCurseur, setSecteurCurseur] = useState(null); // territoire SOUS le curseur (intérieur du polygone) — pilote l'illumination des corridors
  const [regionTooltip, setRegionTooltip] = useState(null);
  const [modeEdition, setModeEdition] = useState(false); // déplacement des robots uniquement en mode explicite
  const [provisoire, setProvisoire] = useState(false); // drag en cours : routage maison simple, recalcul final au relâchement
  const { routesFin, pousser } = useRoutageFinal(); // routes finales calculées par libavoid (Web Worker)
  // Responsive : chrome uniquement — la géographie du Mesh ne change jamais avec l'écran
  const estMobile = useMedia("(max-width: 640px)");
  const estTablette = useMedia("(max-width: 1024px)");
  const estTactile = useMedia("(pointer: coarse)");
  const [rechercheMobileOuverte, setRechercheMobileOuverte] = useState(false);
  const [loupeForcee, setLoupeForcee] = useState(false); // recherche re-dépliée à la demande pendant qu'un panneau est ouvert
  const [calquesOuverts, setCalquesOuverts] = useState(false); // Calques déplié → la barre d'outils se range à droite du panneau

  const animCamera = useRef({ fin: 0, cible: null, minuteur: null }); // déplacement de caméra en cours (voir le ResizeObserver)
  const centreMonde = useRef(null); // point monde au centre du viewport (conservation caméra)
  const [fantome, setFantome] = useState(null); // position de départ du robot pendant le drag
  const coquesRef = useRef({}); // rect actuellement affiché de chaque membrane
  const ciblesCoques = useRef({}); // rect cible calculé
  const rafCoques = useRef(null);
  const [tickCoques, setTickCoques] = useState(0);
  const mouvements = useRef([]); // échantillons du viewport pour l'inertie
  const inertie = useRef(false);
  const [perimetreTravail, setPerimetreTravail] = useState(null);
  const [attenteComparaison, setAttenteComparaison] = useState(false);
  const [comparaison, setComparaison] = useState(null);
  const rfRef = useRef(null);
  const dernierClicRegion = useRef({ kind: null, t: 0 });
  const dernierClicPane = useRef(0);
  const restaure = useRef(false);
  const selAvantLasso = useRef([]);
  const centreFocusFait = useRef(null);
  const selectionFocusFaite = useRef(null);

  const urlRef = useRef(null);
  useEffect(() => { urlRef.current = new URLSearchParams(searchParams); }, [searchParams]);
  const majUrl = useCallback((updates) => {
    const p = new URLSearchParams(urlRef.current || undefined);
    Object.entries(updates).forEach(([k, v]) => (v == null ? p.delete(k) : p.set(k, v)));
    urlRef.current = p;
    setSearchParams(p, { replace: true });
  }, [setSearchParams]);

  const domDe = useMemo(() => {
    const m = {};
    (mesh?.jumeaux || []).forEach((j) => { m[j.id] = j.domaine; });
    return m;
  }, [mesh]);

  // Dates de découverte des relations (projection temporelle du Mesh)
  const relTs = useMemo(() => {
    const m = {};
    (mesh?.relations || []).forEach((r) => {
      const d = parseQuand(r.decouverte_quand);
      if (d) m[r.id] = d.getTime();
    });
    return m;
  }, [mesh]);

  const plageMin = useMemo(() => {
    const vals = Object.values(relTs);
    return vals.length ? Math.min(...vals) : Date.now() - 30 * 864e5;
  }, [relTs]);

  // ?date=AAAA-MM-JJ — photographie historique ; ?avant-apres=AAAA-MM-JJ — comparaison
  const dateParam = searchParams.get("date");
  useEffect(() => {
    if (!dateParam) return;
    const d = new Date(`${dateParam.slice(0, 10)}T12:00:00`);
    if (Number.isNaN(d.getTime())) return;
    setModeTemps("historique");
    setDateRef(finDeJournee(d).getTime());
  }, [dateParam]);

  const aaParam = searchParams.get("avant-apres");
  useEffect(() => {
    if (!aaParam) return;
    const d = new Date(`${aaParam.slice(0, 10)}T12:00:00`);
    if (Number.isNaN(d.getTime())) return;
    setModeTemps("avantapres");
    setDateRef(finDeJournee(d).getTime());
  }, [aaParam]);

  // Replay : relecture accélérée de la construction du Mesh (de la 1re relation à maintenant)
  useEffect(() => {
    if (!replaying) return undefined;
    const fin = Date.now();
    const pas = Math.max((fin - plageMin) / 50, 3600e3);
    setDateRef(plageMin);
    const t = setInterval(() => {
      setDateRef((d) => {
        const n = (d ?? plageMin) + pas;
        if (n >= fin) {
          clearInterval(t);
          setReplaying(false);
          return fin;
        }
        return n;
      });
    }, 160);
    return () => clearInterval(t);
  }, [replaying, plageMin]);

  const temps = useMemo(() => {
    if (modeTemps === "direct" || modeTemps === "pause" || !dateRef) return null;
    return { mode: modeTemps === "avantapres" ? "avantapres" : "historique", dateTs: dateRef, relTs };
  }, [modeTemps, dateRef, relTs]);

  const nbNouvelles = useMemo(
    () => (modeTemps === "avantapres" && dateRef ? Object.values(relTs).filter((ts) => ts > dateRef).length : 0),
    [modeTemps, dateRef, relTs]
  );

  // Découvertes et investigations actives par domaine (situations non closes touchant le domaine)
  const statsRegions = useMemo(() => {
    const stats = {};
    situations.forEach((s) => {
      if (["ignorée", "classée", "décidée"].includes(s.statut)) return;
      const doms = new Set((s.jumeaux || []).map((j) => domDe[j]).filter(Boolean));
      doms.forEach((d) => {
        if (!stats[d]) stats[d] = { decouvertes: 0, investigations: 0 };
        if (s.verbe === "a_comprendre") stats[d].investigations += 1;
        else if (s.verbe === "decouvert") stats[d].decouvertes += 1;
      });
    });
    return stats;
  }, [situations, domDe]);

  // Couche « Situations » : jumeaux impliqués dans une situation non close
  const situationsJumeaux = useMemo(() => {
    const s = new Set();
    situations.forEach((sit) => {
      if (["ignorée", "classée", "décidée"].includes(sit.statut)) return;
      (sit.jumeaux || []).forEach((id) => s.add(id));
    });
    return s;
  }, [situations]);

  const { domaineActif, majContexte, explorerDomaine, centrerJumeau, ajusterVue, revenirSelection } = useNavigationAtlas({
    mesh, jumeauPar, posOverrides, selection, majUrl,
    setDomaineSel, setOnglet, setSelected, rfRef,
    decalage: graphe ? DECALAGE_GRAPHE : DECALAGE_CLASSIQUE,
  });

  const { zoomNiveau, onMove } = useZoomSemantique();

  // Restauration du contexte depuis l'URL au chargement (?domaine=X&sel=y) — déplacements animés explicites
  useEffect(() => {
    if (!mesh || restaure.current) return;
    restaure.current = true;
    const d = searchParams.get("domaine");
    const s = searchParams.get("sel");
    if (d && (mesh.regions || []).some((r) => r.label === d)) {
      setDomaineSel(d);
      setOnglet("detail");
      setTimeout(() => explorerDomaine(d), 350);
    }
    if (s) {
      const j = mesh.jumeaux.find((x) => x.id === s && !x.anonyme);
      if (j) { setSelected(j); setOnglet("detail"); }
    }
    const jf = searchParams.get("jumeau");
    if (jf) {
      const j = mesh.jumeaux.find((x) => x.id === jf && !x.anonyme);
      if (j) setTimeout(() => centrerJumeau(j), 400);
    }
  }, [mesh]);

  // Cadrage d'une scène pilotée (démonstration uniquement). Les jumeaux d'un récit sont
  // répartis sur plusieurs lobes : un fitBounds brut tombe sous le seuil « Global » (0,6)
  // où l'Atlas masque les jumeaux individuels — le résultat annoncé resterait invisible.
  // On borne donc le zoom au niveau « constellation », quitte à rogner légèrement.
  const dernierCadrage = useRef(null); // pts du dernier cadrage de scène
  const dernierCadrageIds = useRef(null); // ids des jumeaux du dernier cadrage de scène
  const cadrerScene = useCallback((ptsMesh, options = {}) => {
    if (!ptsMesh || !ptsMesh.length) return;
    // Les positions du Mesh sont théoriques : les jumeaux sont dessinés dans les lobes de leur
    // domaine. On cadre donc sur les positions RÉELLEMENT rendues quand elles existent.
    if (options.ids) dernierCadrageIds.current = options.ids;
    const rf = rfRef.current;
    const rendus = (dernierCadrageIds.current || [])
      .map((id) => rf?.getInternalNode?.(id))
      .filter((n) => n && !n.hidden && n.internals?.positionAbsolute)
      .map((n) => n.internals.positionAbsolute);
    const pts = rendus.length ? rendus : ptsMesh;
    dernierCadrage.current = pts;
    const duration = options.duration ?? 350;
    const xs = pts.map((p) => p.x);
    const ys = pts.map((p) => p.y);
    const MARGE_X = 140;
    // Marge haute généreuse (étiquette et membrane du domaine au-dessus du jumeau) ; le bas est
    // déjà couvert par la hauteur du jumeau — les scènes étalées sur trois domaines sont hautes
    const MARGE_Y_HAUT = 90;
    const x0 = Math.min(...xs) - MARGE_X;
    const y0 = Math.min(...ys) - MARGE_Y_HAUT;
    const b = {
      x: x0,
      y: y0,
      width: Math.max(...xs) + 140 + MARGE_X - x0,
      height: Math.max(...ys) + 100 - y0,
    };
    const r = carteRef.current?.getBoundingClientRect();
    if (!r || !r.width || !r.height) {
      rfRef.current?.fitBounds(b, { duration });
      return;
    }
    // Flore est une colonne en flux : `r` est déjà la largeur du canevas SANS elle.
    // On ne réserve donc que la barre d'outils à gauche et la minimap / le zoom à droite.
    const GAUCHE = 64;
    const DROITE = 80;
    const BAS = 40;
    const largeurUtile = Math.max(320, r.width - GAUCHE - DROITE);
    const utileY = Math.max(240, r.height - BAS);
    const centreX = GAUCHE + largeurUtile / 2;
    const centreY = utileY / 2;
    // Toute la scène doit rester à l'écran ; plancher à 0,7 : sous 0,6 (0,66 avec l'hystérésis du
    // zoom sémantique) l'Atlas repasse en vue « Global » et masque les jumeaux individuels
    const zoom = Math.min(Math.max(Math.min(largeurUtile / b.width, utileY / b.height), 0.7), 1.25);
    rfRef.current?.setViewport(
      { x: centreX - (b.x + b.width / 2) * zoom, y: centreY - (b.y + b.height / 2) * zoom, zoom },
      { duration }
    );
  }, []);

  // Orchestrateur universel de Focus Situationnel
  const activerTheatreSituationnel = useCallback(({ cibles = [], accents = [], titre = null, sansAnimation = false }) => {
    if (!cibles.length || !mesh?.jumeaux) return;
    clearTheatreTimers();

    const idsValides = cibles.filter((id) => mesh.jumeaux.some((j) => j.id === id));
    if (!idsValides.length) return;
    const accentsValides = (accents.length ? accents : idsValides).filter((id) => mesh.jumeaux.some((j) => j.id === id));

    setSelection(accentsValides);
    setRelFocus(true);

    // On cadre sur les éléments ACCENTUÉS (ce que la scène veut montrer) : le contexte atténué
    // autour n'est pas forcé dans le cadre — il rendrait la scène trop haute pour rester lisible
    const idsCadrage = accentsValides.length ? accentsValides : idsValides;
    const pts = idsCadrage
      .filter((id) => !mesh.jumeaux.find((j) => j.id === id)?.cadastre)
      .map((id) => posOverrides[id] || mesh.jumeaux.find((j) => j.id === id)?.position)
      .filter(Boolean);
    if (pts.length) {
      cadrerScene(pts, { duration: sansAnimation ? 0 : 350, ids: idsCadrage });
      // Démonstration : la mise en page des lobes se stabilise après le premier rendu de la
      // scène — un second cadrage, sur les positions alors mesurées, garantit le résultat visible
      if (pilote) setTimeout(() => cadrerScene(pts, { duration: 300 }), 550);
    }

    setTheatreSituationnel({
      actif: true,
      phase: "sanctuaire",
      cibles: idsValides,
      accents: accentsValides,
      titre: titre || "Scène d'analyse",
    });
  }, [mesh, posOverrides, cadrerScene, pilote]);

  const quitterTheatreSituationnel = useCallback(() => {
    clearTheatreTimers();
    setTheatreSituationnel((prev) => ({ ...prev, phase: "sortie" }));
    if (situationParam) {
      majUrl({ situation: null });
    }
    if (focusCarte) {
      commanderCarte(null);
    }
    rfRef.current?.fitView({ duration: 900, padding: 0.15 });
    const t = setTimeout(() => {
      setTheatreSituationnel({ actif: false, phase: "idle", cibles: [], accents: [], titre: null });
      setSelection([]);
      setRelFocus(false);
    }, 900);
    theatreTimerRef.current.push(t);
  }, [situationParam, focusCarte, majUrl, commanderCarte]);

  // Commandes carte envoyées par Flore / Chat / Démonstration Polaris
  useEffect(() => {
    if (!focusCarte) {
      if (theatreSituationnel.actif && !situationParam) {
        quitterTheatreSituationnel();
      }
      return;
    }
    if (focusCarte.type === "scene" && focusCarte.ids?.length) {
      activerTheatreSituationnel({
        cibles: focusCarte.ids,
        accents: focusCarte.accents || focusCarte.ids,
        titre: focusCarte.titre || "Scène d'analyse",
      });
    } else if (focusCarte.type === "dessin" && focusCarte.ids?.length) {
      setSelection(focusCarte.ids);
      setRelFocus(true);
    } else if (focusCarte.type === "relations" && focusCarte.ids?.length) {
      const rels = (mesh?.relations || []).filter((r) => focusCarte.ids.includes(r.id));
      const ids = [...new Set(rels.flatMap((r) => [r.source, r.cible]))].filter((id) => mesh?.jumeaux.some((j) => j.id === id));
      if (ids.length) {
        activerTheatreSituationnel({
          cibles: ids,
          accents: ids,
          titre: "Relations analysées",
        });
      }
    } else if (focusCarte.type === "parcours" && focusCarte.ids?.length) {
      const ids = focusCarte.ids.filter((id) => mesh?.jumeaux.some((j) => j.id === id));
      if (ids.length) {
        activerTheatreSituationnel({
          cibles: ids,
          accents: ids,
          titre: "Parcours analysé",
        });
      }
    } else if (focusCarte.type === "relation" && focusCarte.relationId) {
      const rel = (mesh?.relations || []).find((r) => r.id === focusCarte.relationId);
      if (!rel) return;
      setSelectedRelation(rel);
      setOnglet("detail");
      activerTheatreSituationnel({
        cibles: [rel.source, rel.cible],
        accents: [rel.source, rel.cible],
        titre: `Relation ${rel.source} ↔ ${rel.cible}`,
      });
    } else if (focusCarte.type === "domaine" && focusCarte.domaine) {
      explorerDomaine(focusCarte.domaine);
    }
  }, [focusCarte]);

  // Signal de disponibilité du rendu (démonstration) : la scène demandée est déclarée
  // disponible quand les jumeaux de la commande ACTIVE sont réellement rendus — React
  // Flow a mesuré leurs nœuds. Aucun acquittement par délai fixe, aucun signal périmé :
  // la clé porte l'identifiant de commande et l'étape de révélation.
  const statsDomaine = useCallback(
    (label) => statsDuDomaine(mesh, situations, domDe, label),
    [mesh, situations, domDe]
  );

  const onNodesChange = useCallback((changes) => {
    // Changements de dimensions : les réinjecter dans nos nœuds dérivés — sinon le store
    // interne ne connaît jamais les ports et les arêtes restent invisibles (course au montage)
    const dims = changes.filter((c) => c.type === "dimensions" && c.dimensions);
    if (dims.length) {
      setMesures((m) => {
        let next = m;
        for (const c of dims) {
          const cur = m[c.id];
          if (cur && Math.abs(cur.width - c.dimensions.width) < 1 && Math.abs(cur.height - c.dimensions.height) < 1) continue;
          if (next === m) next = { ...m };
          next[c.id] = { width: c.dimensions.width, height: c.dimensions.height };
        }
        return next;
      });
    }
    setSelection((prev) => {
      let next = prev;
      for (const ch of changes) {
        if (ch.type !== "select" || ch.id.startsWith("reg-")) continue;
        const has = next.includes(ch.id);
        if (ch.selected && !has) next = next === prev ? [...prev, ch.id] : [...next, ch.id];
        if (!ch.selected && has) next = (next === prev ? [...prev] : next).filter((x) => x !== ch.id);
      }
      return next;
    });
    setPosOverrides((prev) => {
      let next = prev;
      for (const ch of changes) {
        if (ch.type === "position" && ch.position) {
          if (next === prev) next = { ...prev };
          next[ch.id] = ch.position;
        }
      }
      return next;
    });
  }, []);

  useEffect(() => {
    api.get("/situations").then((r) => setSituations(r.data)).catch(() => {});
  }, [version]);

  useEffect(() => {
    setEvents([]);
    setCompteurs({});
  }, [version]);

  useEffect(() => {
    let stop = false;
    let timer;
    const tick = async () => {
      try {
        const { data } = await api.get("/activite");
        if (stop) return;
        setEvents((prev) => [...data.map((e, i) => ({ ...e, uid: `${Date.now()}-${i}` })), ...prev].slice(0, 18));
        setHalo(data[Math.floor(Math.random() * data.length)].jumeau);
        setCompteurs((c) => {
          const n = { ...c };
          data.forEach((e) => { n[e.jumeau] = (n[e.jumeau] || 0) + 1; });
          return n;
        });
        clearTimeout(timer);
        timer = setTimeout(() => setHalo(null), 2600);
      } catch {}
    };
    tick();
    if (!direct) return;
    const t = setInterval(tick, 6000);
    return () => { stop = true; clearInterval(t); clearTimeout(timer); };
  }, [version, direct]);

  const situation = situations.find((s) => s.id === situationParam);

  // Mémoire personnelle : consulter le détail d'un jumeau alimente « Récents »
  useEffect(() => { if (selected?.id && !selected.anonyme) noterRecent(selected.id); }, [selected?.id]);

  // Focus situationnel universel déclenché par une situation URL (ex: ?situation=...)
  useEffect(() => {
    if (!mesh || !situation || selectionFocusFaite.current === situation.id) return;
    const ids = (situation.jumeaux || []).filter((id) => mesh.jumeaux.some((j) => j.id === id && !j.anonyme));
    if (ids.length) {
      selectionFocusFaite.current = situation.id;
      activerTheatreSituationnel({
        cibles: ids,
        accents: ids,
        titre: situation.titre || `Situation #${situation.id}`,
      });
    }
  }, [mesh, situation, activerTheatreSituationnel]);

  // Focus simple sur un jumeau unique (?focus=...)
  useEffect(() => {
    if (!mesh || !focus || centreFocusFait.current === focus) return;
    const j = mesh.jumeaux.find((x) => x.id === focus && !x.anonyme);
    if (!j) return;
    centreFocusFait.current = focus;
    centrerJumeau(j);
  }, [mesh, focus, centrerJumeau]);

  const { nodes, edges, snapshot } = useMemo(() => {
    const g = construireGraphe({
      mesh, situation, focus, vueActive, perimetreTravail,
      posOverrides, compteurs, halo, selection,
      // Rendu graphe : les robots sont toujours visibles (jamais d'étoile) et les liens sont directs
      zoomNiveau: graphe ? Math.min(3, Math.max(2, zoomNiveau)) : zoomNiveau,
      relFocus, focusCarte, domDe, statsRegions, temps,
      zoomFort: zoomActuel >= 1.5,
      // Fondu croisé étoile ↔ robot : bande progressive centrée sur le seuil de niveau (1.15)
      fonduJumeau: graphe ? 1 : Math.max(0, Math.min(1, (zoomActuel - 0.95) / 0.4)),
      // Fondu croisé Global ↔ Domaine : corridors/agrégats fondent, arêtes et étoiles se révèlent (z 0.5 → 0.7)
      fonduGD: graphe ? 1 : Math.max(0, Math.min(1, (zoomActuel - 0.5) / 0.2)),
      // Éclatement parent → enfants : le corridor « N flux » se dissout pendant que
      // ses relations membres naissent échelonnées le long de son tracé (z 1.15 → 1.35)
      fonduPE: graphe ? 1 : Math.max(0, Math.min(1, (zoomActuel - 1.15) / 0.2)),
      routesFin, provisoire, tactile: estTactile,
      couchesCarte, situationsJumeaux,
      theatreSituationnel,
      onMajClic: (id) => {
        // Maj+clic : multisélection additive — le jumeau ouvert (selected) est inclus
        setSelection((prev) => {
          const sel = etatVif.current.selected;
          const base = sel && !prev.includes(sel.id) ? [sel.id, ...prev] : prev;
          return base.includes(id) ? base.filter((x) => x !== id) : [...base, id];
        });
      },
    });
    // Conserve les dimensions mesurées par React Flow : le graphe est reconstruit à chaque
    // tick de drag — sans cela les nœuds perdent leur mesure et les arêtes disparaissent.
    // Rendu graphe : pas de territoires — les domaines se lisent par leur couleur et la légende
    if (graphe) g.nodes = g.nodes.filter((n) => n.type !== "region");
    const internes = rfRef.current?.getNodes?.() || [];
    const parId = new Map(internes.map((n) => [n.id, n]));
    const nouvellesCibles = {};
    g.nodes = g.nodes.map((n) => {
      if (n.type === "region") {
        const cible = { x: n.position.x, y: n.position.y, w: n.data.w, h: n.data.h };
        nouvellesCibles[n.id] = cible;
        const cur = coquesRef.current[n.id];
        if (!cur) coquesRef.current[n.id] = { ...cible };
        // Ressort : la membrane affichée poursuit sa cible (matière souple, stabilisation ~300 ms)
        const a = coquesRef.current[n.id];
        n = {
          ...n,
          position: { x: a.x, y: a.y },
          initialWidth: a.w,
          initialHeight: a.h,
          data: {
            ...n.data,
            w: a.w,
            h: a.h,
            wCible: cible.w,
            hCible: cible.h,
            survol: regionSurvolee?.id === n.data.id,
            attenue: !!regionSurvolee && regionSurvolee.id !== n.data.id,
          },
        };
      }
      if (n.type === "twin" && regionSurvolee && n.data.jumeau && !n.data.jumeau.porte && n.data.jumeau.domaine !== regionSurvolee.label) {
        n = { ...n, data: { ...n.data, adouci: true } };
      }
      // Robots source/cible de la relation survolée ou sélectionnée : anneau turquoise
      const relActive = relSurvolee || selectedRelation?.id;
      if (n.type === "twin" && relActive && mesh) {
        const rel = mesh.relations.find((r) => r.id === relActive);
        if (rel && n.data.jumeau && (rel.source === n.data.jumeau.id || rel.cible === n.data.jumeau.id)) {
          n = { ...n, data: { ...n.data, relLiee: true } };
        }
      }
      if (graphe && analyse && n.type === "twin") {
        n = habillerNoeud(n, analyse);
        if (domainesMasques.has(n.data.jumeau?.domaine)) n = { ...n, hidden: true };
      }
      const prev = parId.get(n.id);
      const dim = mesures[n.id];
      const base = prev?.measured ? { ...n, measured: prev.measured, dragging: prev.dragging || undefined } : n;
      return dim ? { ...base, width: dim.width, height: dim.height, measured: { width: dim.width, height: dim.height } } : base;
    });
    ciblesCoques.current = nouvellesCibles;
    return g;
  }, [mesh, focus, situation, halo, compteurs, selection, relFocus, zoomNiveau, vueActive, posOverrides, domaineSel, perimetreTravail, domDe, statsRegions, focusCarte, temps, amorce, mesures, regionSurvolee, tickCoques, relSurvolee, selectedRelation, zoomActuel, routesFin, provisoire, estTactile, couchesCarte, situationsJumeaux, theatreSituationnel, graphe, analyse, domainesMasques]);

  const [renduSignale, setRenduSignale] = useState(null);
  useEffect(() => {
    const cmd = focusCarte;
    if (!pilote?.signalerRenduPret || !cmd || cmd.type !== "scene" || !cmd.commandId) return undefined;
    const cle = `${cmd.commandId}:${cmd.etape ?? 0}`;
    if (renduSignale === cle) return undefined;
    const attendus = (cmd.accents?.length ? cmd.accents : cmd.ids || []).filter((id) => mesh?.jumeaux.some((j) => j.id === id));
    if (!attendus.length) return undefined;
    // Les jumeaux de la commande sont-ils effectivement dans le graphe peint ?
    const peints = new Set(nodes.filter((n) => n.type === "twin" && !n.hidden).map((n) => n.id));
    if (!attendus.every((id) => peints.has(id))) return undefined;
    // …et l'accentuation demandée est-elle appliquée ?
    if (!attendus.every((id) => selection.includes(id))) return undefined;
    const raf = requestAnimationFrame(() => {
      setRenduSignale(cle);
      pilote.signalerRenduPret(cmd.commandId, cmd.etape ?? 0);
    });
    return () => cancelAnimationFrame(raf);
  }, [focusCarte, nodes, selection, mesh, pilote, renduSignale]);

  // Moteur de labels des titres de domaines : sélection > survol > halo > investigations actives ;
  // collision → le titre le moins prioritaire disparaît (jamais de chevauchement de texte)
  const titresVisibles = useMemo(() => {
    const candidats = nodes
      .filter((n) => n.type === "region")
      .map((n) => {
        const d = n.data;
        const candidat =
          zoomNiveau === 1 ||
          regionSurvolee?.id === d.id ||
          domaineSel === d.label ||
          couchesCarte.capacites ||
          (theatreSituationnel?.actif && !d.cadastre);
        if (!candidat) return null;
        const sx = d.w / (d.wCible || d.w);
        const sy = d.h / (d.hCible || d.h);
        return {
          id: d.id,
          x: n.position.x + (d.labelX ?? d.w / 2) * sx,
          y: n.position.y + (d.labelY ?? 30) * sy,
          w: d.label.length * 9 + 26,
          h: d.macro || couchesCarte.capacites ? 48 : 30,
          priorite: (domaineSel === d.label ? 400 : 0) + (regionSurvolee?.id === d.id ? 300 : 0) + (d.halo ? 200 : 0) + 100 + (d.investigations || 0) * 10,
        };
      })
      .filter(Boolean);
    return placerLabels(candidats);
  }, [nodes, zoomNiveau, regionSurvolee, domaineSel, couchesCarte.capacites, theatreSituationnel?.actif]);

  // Instantané contextuel transmis à Flore : surface, sélection, couches actives, niveau de zoom
  useEffect(() => {
    setAtlasCtx({
      domaine: domaineSel,
      jumeau: selected && !selected.anonyme ? `${idNumerique(selected.id)} · ${selected.nom}` : null,
      relation: selectedRelation ? `${idNumerique(selectedRelation.source)} → ${idNumerique(selectedRelation.cible)}` : null,
      couches: [
        couchesRel.bcm && "BCM", couchesRel.realite && "Réalité observée", couchesRel.ecarts && "Écarts",
        couchesCarte.situations && "Situations", couchesCarte.capacites && "Capacités", couchesCarte.transformations && "Transformations",
      ].filter(Boolean),
      zoomLabel: NIVEAUX_ZOOM[zoomNiveau],
    });
    return () => setAtlasCtx(null);
  }, [domaineSel, selected?.id, selectedRelation, couchesRel, couchesCarte, zoomNiveau, setAtlasCtx]);

  // Miroir vivant des états à mémoriser (évite les closures périmées au démontage)
  useEffect(() => {
    etatVif.current = { selected, domaineSel, selectedRelation, couchesRel, couchesCarte };
  });

  // Sauvegarde à la sortie de la page (navigation vers Travaux, Jumeaux, …)
  useEffect(() => () => {
    const vp = rfRef.current?.getViewport?.();
    // Montage StrictMode sans instance : ne JAMAIS écraser l'état mémorisé avec du vide
    if (!vp) return;
    const c = etatVif.current;
    setAtlasEtat({
      viewport: vp || null,
      twinId: c.selected?.id || null,
      domaine: c.domaineSel || null,
      relationId: c.selectedRelation?.id || null,
      couchesRel: c.couchesRel,
      couchesCarte: c.couchesCarte,
    });
  }, [setAtlasEtat]);

  // Restauration au retour : couches + sélection (le viewport est restauré à l'init React Flow)
  useEffect(() => {
    if (!mesh || etatRestaure.current || !restaurerEtat) return;
    etatRestaure.current = true;
    if (atlasEtat.couchesRel) setCouchesRel(atlasEtat.couchesRel);
    if (atlasEtat.couchesCarte) setCouchesCarte(atlasEtat.couchesCarte);
    if (atlasEtat.domaine) setDomaineSel(atlasEtat.domaine);
    if (atlasEtat.twinId) {
      const j = (mesh.jumeaux || []).find((x) => x.id === atlasEtat.twinId);
      if (j) { setSelected(j); setOnglet("detail"); }
    }
    if (atlasEtat.relationId) {
      const r = (mesh.relations || []).find((x) => x.id === atlasEtat.relationId);
      if (r) { setSelectedRelation(r); setOnglet("detail"); }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mesh]);

  // Fil d'Ariane restauré au retour : le contexte passif (domaine sous le centre) est recalculé
  // sur le viewport restauré — sinon il ne réapparaît qu'au prochain mouvement de caméra.
  // majContexte exige 400 ms de stabilité : double appel espacé.
  const contexteRestaure = useRef(false);
  useEffect(() => {
    if (!restaurerEtat || contexteRestaure.current || !nodes.length || !rfRef.current) return;
    const recalculer = () => {
      // Marquage à l'exécution réelle : le cleanup StrictMode annule les timers du premier
      // passage avant tout marquage — le second passage repose alors les timers.
      contexteRestaure.current = true;
      const rect = carteRef.current?.getBoundingClientRect();
      if (!rect || !rfRef.current) return;
      const centre = rfRef.current.screenToFlowPosition({ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 });
      majContexte(centre, nodes.filter((n) => n.type === "region" && n.data.points).map((n) => ({ label: n.data.label, points: n.data.points, ox: n.position.x, oy: n.position.y })));
    };
    const t1 = setTimeout(recalculer, 450);
    const t2 = setTimeout(recalculer, 950);
    return () => { clearTimeout(t1); clearTimeout(t2); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, restaurerEtat]);

  // Panneaux = colonnes de layout (détail à droite, Flore globale) : la carte se redimensionne
  // et le ResizeObserver conserve la caméra — le chrome (mini-carte, zoom, barre) ne bouge jamais.
  const panneauOuvert = !!(comparaison || selectedRelation || selected || domaineSel || vueListe);
  // Recherche rétractée en loupe quand un panneau (détail ou Flore) est ouvert — chrome minimal en mode focus
  const rechercheOuverte = estMobile ? rechercheMobileOuverte : graphe || !panneauOuvert || loupeForcee;
  useEffect(() => { if (!panneauOuvert) setLoupeForcee(false); }, [panneauOuvert]);
  // Le panneau de détail prend la place : la barre latérale se replie en icônes tant qu'il est ouvert
  useEffect(() => {
    setRepliAuto(panneauOuvert);
    return () => setRepliAuto(false);
  }, [panneauOuvert, setRepliAuto]);

  // Remplacement mutuel de la colonne droite : une NOUVELLE sélection de domaine/relation/liste
  // pendant que Flore est ouverte ferme Flore (le dernier panneau demandé gagne).
  // Le détail jumeau vit dans sa colonne GAUCHE — il n'interrompt plus Flore.
  const selCle = selectedRelation?.id || domaineSel || vueListe || (comparaison ? "comparaison" : null);
  useEffect(() => {
    if (floreOuverte && selCle && !pilote) fermerFlore();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selCle]);

  // Paradigme « Google Maps » : l'ouverture/fermeture de Flore redimensionne le canevas —
  // la carte se recadre pour rester entièrement visible avec tous ses composants.
  // En démonstration, si une scène est déjà cadrée, on la RECADRE sur le nouveau canevas
  // au lieu de la remplacer par une vue d'ensemble : le résultat annoncé reste à l'écran.
  useEffect(() => {
    const t = setTimeout(() => {
      if (pilote && dernierCadrage.current?.length) {
        cadrerScene(dernierCadrage.current);
        return;
      }
      rfRef.current?.fitView({ duration: 400, padding: 0.15, maxZoom: 1.35 });
    }, 60);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [floreOuverte]);

  // Routage final : nouveau snapshot géométrique → Web Worker libavoid
  // (jamais pendant le drag, jamais pendant le pan/zoom — la signature géométrique est stable)
  useEffect(() => {
    if (!provisoire && snapshot) pousser(snapshot);
  }, [snapshot, provisoire, pousser]);

  // Couches de relations (BCM déclaré / Réalité découverte / Écarts) + accentuation au survol/épinglage
  const aretesDuGraphe = useMemo(() => (graphe && analyse ? aretesGraphe(mesh, nodes, analyse) : null), [graphe, analyse, mesh, nodes]);
  const edgesVisibles = useMemo(() => {
    let es = (aretesDuGraphe || edges).filter((e) => {
      // Corridors parents : agrégats multi-états, toujours visibles (ils portent tous les flux)
      if (e.type === "corridor") return true;
      const etat = e.data?.etat;
      if (etat === "confirmee" || etat === "obsolete") return couchesRel.bcm;
      if (etat === "observee" || etat === "validation") return couchesRel.realite;
      if (etat === "supposee" || etat === "contestee") return couchesRel.ecarts;
      return true;
    });
    // Corridors (vue Global) : quasi invisibles au repos ; le survol d'un territoire
    // illumine SES liaisons et éteint les autres — lève l'ambiguïté des arcs croisés
    es = es.map((e) => {
      if (e.type !== "corridor") return e;
      const concerne = !!secteurCurseur && e.data?.domains?.includes(secteurCurseur);
      return {
        ...e,
        label: concerne ? e.data?.corridorLabel : undefined,
        data: { ...e.data, miseEnAvant: concerne, estompee: !!secteurCurseur && !concerne },
      };
    });
    // Rendu graphe : le jumeau ouvert (recherche, clic) prime sur le survol ; ses liens restent en avant, les autres s'effacent presque
    const epingle = graphe && selected && !selected.anonyme ? selected.id : null;
    const actif = epingle || survolJumeau;
    if (graphe && domaineSel && !actif) {
      es = es.map((e) => {
        const n = (domDe[e.source] === domaineSel) + (domDe[e.target] === domaineSel);
        return n === 2 ? { ...e, zIndex: 20, style: { ...e.style, strokeWidth: (e.style?.strokeWidth || 1.5) + 1, opacity: 1 } }
          : n === 1 ? { ...e, style: { ...e.style, opacity: 0.4 } }
            : { ...e, data: { ...e.data, estompee: true }, style: { ...e.style, opacity: 0.06 } };
      });
    }
    if (actif) {
      es = es.map((e) =>
        e.source === actif || e.target === actif || e.source === `voisin-${actif}` || e.target === `voisin-${actif}`
          ? { ...e, zIndex: 20, style: { ...e.style, strokeWidth: (e.style?.strokeWidth || 1.5) + 1, opacity: 1 } }
          : { ...e, label: undefined, data: { ...e.data, estompee: true }, style: { ...e.style, opacity: epingle ? 0.06 : 0.12 } }
      );
    }
    // Survol d'une voie agrégée « N flux » : déploiement temporaire des routes membres
    if (relSurvolee?.startsWith("agg-")) {
      return es.map((e) => {
        if (e.id === relSurvolee) return { ...e, hidden: true };
        if (e.data?.groupe === relSurvolee) return { ...e, hidden: false, zIndex: 25, style: { ...e.style, opacity: 1 } };
        return { ...e, label: undefined, data: { ...e.data, estompee: true }, style: { ...e.style, opacity: 0.15 } };
      });
    }
    // Survol/sélection d'une relation : trajet mis en avant, les autres estompées (15–30 % d'opacité)
    const relActive = relSurvolee || selectedRelation?.id;
    if (relActive) {
      es = es.map((e) =>
        e.id === relActive
          ? { ...e, zIndex: 30, data: { ...e.data, survolee: true, estompee: false }, style: { ...e.style, opacity: 1 } }
          : { ...e, data: { ...e.data, estompee: true }, style: { ...e.style, opacity: 0.2 } }
      );
      // la relation active se dessine au-dessus des autres
      es = [...es.filter((e) => e.id !== relActive), ...es.filter((e) => e.id === relActive)];
    }
    // Preuve survolée dans Flore : la relation pulse sur la carte, les autres s'effacent
    if (preuveSurvolee) {
      es = es.map((e) =>
        e.id === preuveSurvolee
          ? { ...e, zIndex: 40, data: { ...e.data, pulse: true, estompee: false, halo: false, survolee: true }, style: { ...e.style, opacity: 1, strokeWidth: (e.style?.strokeWidth || 1.5) + 1 } }
          : { ...e, label: undefined, data: { ...e.data, estompee: true, halo: false }, style: { ...e.style, opacity: 0.18 } }
      );
      es = [...es.filter((e) => e.id !== preuveSurvolee), ...es.filter((e) => e.id === preuveSurvolee)];
    }
    return es;
  }, [edges, aretesDuGraphe, graphe, selected, domaineSel, domDe, couchesRel, survolJumeau, relSurvolee, selectedRelation, preuveSurvolee, secteurCurseur]);

  // Rendu graphe : au survol d'un jumeau (sans sélection), ses voisins restent éclairés, le reste s'estompe
  const nodesRendus = useMemo(() => {
    // Comme le laboratoire : la sélection épinglée (ouverte par recherche ou clic) prime sur le survol
    const focus = selected && !selected.anonyme ? selected.id : survolJumeau;
    // Un domaine ouvert (recherche, légende) éclaire ses robots ; le survol d'un robot reste prioritaire
    if (graphe && domaineSel && !selected && !survolJumeau && !selection.length) {
      return nodes.map((n) => (n.type !== "twin" || n.data?.cadastre || n.data?.jumeau?.domaine === domaineSel ? n : { ...n, data: { ...n.data, dim: true } }));
    }
    if (!graphe || !focus || selection.length || !mesh) return nodes;
    const voisins = new Set([focus]);
    mesh.relations.forEach((r) => { if (r.source === focus) voisins.add(r.cible); if (r.cible === focus) voisins.add(r.source); });
    return nodes.map((n) => {
      if (n.type !== "twin" || n.data?.cadastre) return n;
      if (n.id === focus) return { ...n, selected: n.id === selected?.id, data: { ...n.data, nomVisible: true } };
      return voisins.has(n.id) ? { ...n, data: { ...n.data, nomVisible: true } } : { ...n, data: { ...n.data, dim: true } };
    });
  }, [graphe, nodes, survolJumeau, selected, selection, mesh, domaineSel]);

  // Jumeau survolé ou épinglé → panneau flottant à gauche
  const jumeauSurvole = useMemo(() => {
    const id = survolJumeau;
    return id && mesh ? mesh.jumeaux.find((x) => x.id === id && !x.anonyme) || null : null;
  }, [survolJumeau, mesh]);
  // KPI du jumeau sélectionné (relations observées, écarts) — affichés dans le panneau de détail
  const statsSelection = useMemo(() => {
    if (!selected || !mesh || selected.anonyme) return null;
    const liees = mesh.relations.filter((r) => r.source === selected.id || r.cible === selected.id);
    return {
      flux: liees.filter((r) => r.etat === "observee").length,
      ecarts: liees.filter((r) => r.etat === "supposee" || r.etat === "contestee").length,
    };
  }, [selected, mesh]);

  const resultatsRecherche = useMemo(() => {
    const q = recherche.trim().toLowerCase();
    if (!q || !mesh) return [];
    const js = mesh.jumeaux
      .filter((j) => !j.anonyme && (j.nom.toLowerCase().includes(q) || j.id.toLowerCase().includes(q) || idNumerique(j.id).includes(q)))
      .slice(0, 8)
      .map((j) => ({ type: "jumeau", id: j.id, label: j.nom, sub: `${idNumerique(j.id)} · ${j.domaine}` }));
    const ds = (mesh.regions || [])
      .filter((r) => r.label.toLowerCase().includes(q))
      .slice(0, 3)
      .map((r) => ({ type: "domaine", id: r.label, label: r.label, sub: "domaine" }));
    return [...js, ...ds];
  }, [recherche, mesh]);

  // Voisins directs du jumeau sélectionné (intelligence locale — colonne gauche)
  const voisinsSelection = useMemo(() => {
    if (!selected || !mesh) return [];
    return mesh.relations
      .filter((r) => r.source === selected.id || r.cible === selected.id)
      .map((r) => {
        const autre = r.source === selected.id ? r.cible : r.source;
        const j = mesh.jumeaux.find((x) => x.id === autre);
        if (!j || j.anonyme) return null;
        return { id: j.id, nom: j.nom, nature: r.label || r.type || "lié", direction: r.source === selected.id ? "vers" : "depuis", etat: r.etat };
      })
      .filter(Boolean);
  }, [selected, mesh]);

  // Changements récents : dernières relations découvertes touchant le jumeau
  const relationsRecentes = useMemo(() => {
    if (!selected || !mesh) return [];
    return mesh.relations
      .filter((r) => (r.source === selected.id || r.cible === selected.id) && r.decouverte_quand)
      .slice(0, 3)
      .map((r) => {
        const autre = r.source === selected.id ? r.cible : r.source;
        const nom = mesh.jumeaux.find((x) => x.id === autre)?.nom || autre;
        const sens = r.source === selected.id ? `vers ${nom}` : `depuis ${nom}`;
        return { id: r.id, texte: `Relation ${sens} (${ETATS_RELATION[r.etat]?.label || "confirmée"}) — ${r.decouverte_quand}` };
      });
  }, [selected, mesh]);

  // « Parler au jumeau » : chaque conversation est un travail. On le crée avec le(s) jumeau(x) en contexte, Flore
  // ouvre l'échange, et l'on arrive dans la page du travail. (En démonstration, le réseau est simulé : Flore s'ouvre.)
  const parlerAuJumeau = async (ids) => {
    const js = ids.map((id) => mesh?.jumeaux.find((x) => x.id === id && !x.anonyme)).filter(Boolean);
    if (!js.length) return;
    if (pilote) { setSelection(ids); ouvrirFlore(); return; }
    const seul = js.length === 1 ? js[0] : null;
    const nb = seul ? mesh.relations.filter((r) => r.source === seul.id || r.cible === seul.id).length : 0;
    const accueil = seul
      ? `Vous voulez parler de « ${seul.nom} » (${seul.domaine}). ${seul.mission ? `${seul.mission}. ` : ""}Je le connais avec ${seul.couverture ?? "—"} % de couverture et ${nb} relation${nb > 1 ? "s" : ""}. Que voulez-vous savoir ?`
      : `Vous voulez parler de ${js.length} jumeaux : ${js.map((x) => x.nom).join(", ")}. Relations, points communs, écarts… par où commençons-nous ?`;
    try {
      const now = new Date().toISOString();
      const { data } = await api.post("/cases", {
        titre: seul ? `Échange avec ${seul.nom}` : `Échange sur ${js.length} jumeaux`,
        type: "demande",
        objectif: seul ? `Comprendre ${seul.nom} (${seul.domaine})` : `Comprendre ${js.map((x) => x.nom).join(", ")}`,
        jumeaux: js.map((x) => x.id),
        espace: info?.espace?.id,
      });
      await api.patch(`/cases/${data.id}`, { conversation: [{ role: "flore", comportement: "expliquer", texte: accueil, quand: now }] });
      navigate(`/travaux/${data.id}`);
    } catch {
      toast.error("Impossible d'ouvrir le travail");
    }
  };

  const ouvrirInvestigationJumeau = async () => {
    if (!selected) return;
    try {
      const r = await api.post("/cases", { titre: `Investigation — ${selected.nom}`, type: "investigation", objectif: `Comprendre ${selected.nom} (${selected.domaine})`, jumeaux: [selected.id] });
      toast.success("Investigation créée");
      navigate(`/travaux/${r.data.id}`);
    } catch {
      toast.error("Création impossible");
    }
  };

  const creerGroupeSelection = async () => {
    if (selection.length < 2) return;
    try {
      await api.post("/vues", { nom: `Groupe — ${selection.length} jumeaux`, type: "selection", jumeaux: selection });
      rechargerVues();
      toast.success("Groupe enregistré — retrouvez-le dans le sélecteur de périmètre");
    } catch {
      toast.error("Enregistrement impossible");
    }
  };

  // Actions du cycle de vie d'une situation (Qualifier / Surveiller / Ignorer / Investiguer)
  const actionSituation = async (s, action) => {
    try {
      await api.post(`/situations/${s.id}/action`, { action });
      const { data } = await api.get("/situations");
      setSituations(data);
      toast.success(`Situation ${action === "qualifier" ? "qualifiée" : action === "investiguer" ? "en investigation" : action === "surveiller" ? "sous surveillance" : "ignorée"}`);
    } catch {
      toast.error("Action impossible");
    }
  };

  // Échap ferme la sélection épinglée ; +/−/0 pilotent le zoom (comme Google Maps)
  useEffect(() => {
    const h = (e) => {
      const cible = e.target?.tagName;
      if (cible === "INPUT" || cible === "TEXTAREA") return;
      if (e.key === "Escape") setSurvolJumeau(null);
      if (e.key === "+" || e.key === "=") rfRef.current?.zoomIn({ duration: 220 });
      if (e.key === "-") rfRef.current?.zoomOut({ duration: 220 });
      if (e.key === "0") rfRef.current?.fitView({ duration: 300, padding: 0.15 });
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  // Amorce : force une reconstruction du graphe après le montage pour que React Flow
  // ait mesuré les ports (sinon les arêtes peuvent rester invisibles au premier rendu)
  useEffect(() => {
    if (amorce >= 2) return undefined;
    const t = setTimeout(() => setAmorce((a) => a + 1), amorce === 0 ? 250 : 700);
    return () => clearTimeout(t);
  }, [amorce]);

  const pleinEcran = () => {
    const el = carteRef.current;
    if (!el) return;
    if (document.fullscreenElement) document.exitFullscreen();
    else el.requestFullscreen?.();
  };

  // Ressort des membranes : poursuite exponentielle (~300 ms, sans vibration)
  const poursuite = useCallback(() => {
    let actif = false;
    const alpha = 1 - Math.exp(-(1 / 60) * 9);
    for (const [id, cible] of Object.entries(ciblesCoques.current)) {
      const cur = coquesRef.current[id] || { ...cible };
      const n = {
        x: cur.x + (cible.x - cur.x) * alpha,
        y: cur.y + (cible.y - cur.y) * alpha,
        w: cur.w + (cible.w - cur.w) * alpha,
        h: cur.h + (cible.h - cur.h) * alpha,
      };
      const fini = Math.abs(n.x - cible.x) + Math.abs(n.y - cible.y) + Math.abs(n.w - cible.w) + Math.abs(n.h - cible.h) < 0.6;
      coquesRef.current[id] = fini ? { ...cible } : n;
      if (!fini) actif = true;
    }
    if (actif) {
      setTickCoques((t) => t + 1);
      rafCoques.current = requestAnimationFrame(poursuite);
    } else {
      rafCoques.current = null;
    }
  }, []);

  useEffect(() => {
    if (!rafCoques.current && Object.keys(ciblesCoques.current).length > 0) {
      rafCoques.current = requestAnimationFrame(poursuite);
    }
  }, [nodes, poursuite]);

  // Survol des membranes par proximité de la frontière (les zones d'interaction des arêtes les recouvrent)
  const surSurvolCarte = (e) => {
    if (!rfRef.current || !mesh) return;
    const rect = carteRef.current?.getBoundingClientRect();
    if (!rect) return;
    if (relSurvolee) setRelTooltipPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
    const p = rfRef.current.screenToFlowPosition({ x: e.clientX, y: e.clientY });
    const zoom = rfRef.current.getZoom() || 1;
    let trouve = null;
    for (const n of nodes) {
      if (n.type !== "region" || !n.data.points) continue;
      const ox = n.position.x;
      const oy = n.position.y;
      const pts = n.data.points;
      let min = Infinity;
      for (let i = 0; i < pts.length; i++) {
        const ax = pts[i].x + ox;
        const ay = pts[i].y + oy;
        const bx = pts[(i + 1) % pts.length].x + ox;
        const by = pts[(i + 1) % pts.length].y + oy;
        const dx = bx - ax;
        const dy = by - ay;
        const L2 = dx * dx + dy * dy || 1;
        const t = Math.max(0, Math.min(1, ((p.x - ax) * dx + (p.y - ay) * dy) / L2));
        const d = Math.hypot(p.x - (ax + t * dx), p.y - (ay + t * dy));
        if (d < min) min = d;
      }
      if (min < 18 / zoom) { trouve = n; break; }
    }
    if (trouve) {
      if (regionSurvolee?.id !== trouve.data.id) setRegionSurvolee({ id: trouve.data.id, label: trouve.data.label });
      setRegionTooltip({ x: e.clientX - rect.left, y: e.clientY - rect.top, data: trouve.data });
    } else if (regionSurvolee) {
      setRegionSurvolee(null);
      setRegionTooltip(null);
    }
    // Télémétrie : ne « parle » que lorsqu'un élément est pointé (jumeau ou territoire) —
    // silencieuse sinon (« — », atténuée), pour ne pas bruyer le vide.
    if (telemetrieRef.current) {
      let texte = null;
      if (jumeauSurvole) {
        texte = `JUMEAU ${idNumerique(jumeauSurvole.id)} · ${(jumeauSurvole.domaine || "").toUpperCase()} · Z ${zoom.toFixed(2)}`;
      } else {
        let secteur = null;
        for (const n of nodes) {
          if (n.type !== "region" || !n.data.points) continue;
          if (dansPolygone(p, n.data.points, n.position.x, n.position.y)) { secteur = n.data.label; break; }
        }
        if (secteur !== secteurCurseur) setSecteurCurseur(secteur);
        if (secteur) texte = `${secteur.toUpperCase()} · X ${String(Math.max(0, Math.round(p.x))).padStart(4, "0")} · Y ${String(Math.max(0, Math.round(p.y))).padStart(4, "0")} · Z ${zoom.toFixed(2)}`;
      }
      telemetrieRef.current.textContent = texte || "—";
      telemetrieRef.current.style.opacity = texte ? "1" : "0.35";
    }
  };

  // Conservation de la caméra au redimensionnement / changement d'orientation :
  // même zoom, même point monde au centre — seule la translation est recalculée
  useEffect(() => {
    const el = carteRef.current;
    if (!el) return undefined;
    let derniere = { w: el.clientWidth, h: el.clientHeight };
    const ro = new ResizeObserver(() => {
      const rf = rfRef.current;
      const c = centreMonde.current;
      const { clientWidth: w, clientHeight: h } = el;
      if (w === derniere.w && h === derniere.h) return;
      derniere = { w, h };
      if (!rf || !c) return;
      // Un déplacement de caméra est en cours (recherche, double-clic) : le recadrer ici l'interromptrait.
      // On le laisse finir, puis on le rejoue vers sa cible sur la carte à sa taille définitive.
      const anim = animCamera.current;
      if (Date.now() < anim.fin) {
        clearTimeout(anim.minuteur);
        anim.minuteur = setTimeout(() => rf.setCenter(anim.cible.x, anim.cible.y, { zoom: anim.cible.zoom, duration: 200 }), anim.fin - Date.now() + 30);
        return;
      }
      const vp = rf.getViewport();
      rf.setViewport({ x: w / 2 - c.x * vp.zoom, y: h / 2 - c.y * vp.zoom, zoom: vp.zoom });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Inertie de déplacement : échantillonnage du viewport, décélération progressive au relâchement
  const surMove = (e, vp) => {
    onMove(e, vp);
    setZoomActuel((z) => {
      const arr = Math.round(vp.zoom * 20) / 20;
      return Math.abs(arr - z) >= 0.05 ? arr : z;
    });
    // Contexte passif : domaine sous le centre du viewport (stabilisé 400 ms, caméra jamais déplacée)
    const rect = carteRef.current?.getBoundingClientRect();
    if (rfRef.current && rect) {
      const centre = rfRef.current.screenToFlowPosition({ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 });
      majContexte(centre, nodes.filter((n) => n.type === "region" && n.data.points).map((n) => ({ label: n.data.label, points: n.data.points, ox: n.position.x, oy: n.position.y })));
    }
    if (inertie.current) return;
    const t = Date.now();
    // Zoom en cours : le x/y bouge à cause de l'ancrage au pointeur — ne pas alimenter
    // l'inertie avec ces échantillons, sinon un zoom-out rapide déclenche une translation
    const dernier = mouvements.current[mouvements.current.length - 1];
    if (dernier && Math.abs(dernier.zoom - vp.zoom) > 0.0001) mouvements.current = [];
    // Point monde au centre du viewport (conservation de la caméra au redimensionnement)
    if (rect) centreMonde.current = { x: (rect.width / 2 - vp.x) / vp.zoom, y: (rect.height / 2 - vp.y) / vp.zoom };
    mouvements.current.push({ t, x: vp.x, y: vp.y, zoom: vp.zoom });
    mouvements.current = mouvements.current.filter((m) => t - m.t < 180);
  };

  const surMoveEnd = () => {
    const ms = mouvements.current;
    mouvements.current = [];
    if (!rfRef.current || ms.length < 2) return;
    const a = ms[0];
    const b = ms[ms.length - 1];
    const dt = (b.t - a.t) / 1000;
    if (dt <= 0.02) return;
    let vx = (b.x - a.x) / dt;
    let vy = (b.y - a.y) / dt;
    if (Math.hypot(vx, vy) < 80) return; // trop lent : pas d'inertie
    inertie.current = true;
    let px = b.x;
    let py = b.y;
    let dernier = performance.now();
    const pas = (t) => {
      const d = Math.min((t - dernier) / 1000, 0.05);
      dernier = t;
      const fr = Math.exp(-d * 5.5); // amortissement rapide
      vx *= fr;
      vy *= fr;
      px += vx * d;
      py += vy * d;
      rfRef.current?.setViewport({ x: px, y: py, zoom: rfRef.current.getZoom() });
      if (Math.hypot(vx, vy) > 14) requestAnimationFrame(pas);
      else inertie.current = false;
    };
    requestAnimationFrame(pas);
  };

  // Déplacement d'un robot — uniquement en mode réorganisation
  const debutDrag = (_, node) => {
    if (node.type !== "twin" || !node.data?.jumeau || node.data.jumeau.porte || node.data.voisinRel) return;
    setProvisoire(true);
    const rect = carteRef.current?.getBoundingClientRect();
    if (!rect || !rfRef.current) return;
    const sp = rfRef.current.flowToScreenPosition({ x: node.position.x + 30, y: node.position.y + 40 });
    setFantome({ x: sp.x - rect.left, y: sp.y - rect.top });
  };

  const finDrag = async (_, node) => {
    setFantome(null);
    setProvisoire(false); // déclenche le routage final (Worker) + interpolation des trajets
    if (node.type !== "twin" || !node.data?.jumeau || node.data.jumeau.porte || node.data.voisinRel) return;
    const j = node.data.jumeau;
    const pos = node.position;
    try {
      await api.patch(`/jumeaux/${j.id}`, { position: { x: Math.round(pos.x), y: Math.round(pos.y) } });
    } catch {
      toast.error("Position non enregistrée");
      return;
    }
    // Reclassification jamais automatique : proposition à l'humain
    const centre = { x: pos.x + 30, y: pos.y + 40 };
    const dansPolygone = (pts, ox, oy) => {
      let dedans = false;
      for (let i = 0, k = pts.length - 1; i < pts.length; k = i++) {
        const xi = pts[i].x + ox;
        const yi = pts[i].y + oy;
        const xj = pts[k].x + ox;
        const yj = pts[k].y + oy;
        if (yi > centre.y !== yj > centre.y && centre.x < ((xj - xi) * (centre.y - yi)) / (yj - yi) + xi) dedans = !dedans;
      }
      return dedans;
    };
    let domaineHote = null;
    let minDist = Infinity;
    for (const n of nodes) {
      if (n.type !== "region" || !n.data.points) continue;
      if (dansPolygone(n.data.points, n.position.x, n.position.y)) domaineHote = n.data.label;
      for (const p of n.data.points) {
        minDist = Math.min(minDist, Math.hypot(centre.x - (p.x + n.position.x), centre.y - (p.y + n.position.y)));
      }
    }
    if (domaineHote && domaineHote !== j.domaine) {
      toast(`${j.nom} semble appartenir au domaine ${domaineHote}`, {
        description: "La reclassification n'est jamais automatique — elle vous appartient.",
        duration: 9000,
        action: {
          label: `Reclasser dans ${domaineHote}`,
          onClick: async () => {
            try {
              await api.patch(`/jumeaux/${j.id}`, { domaine: domaineHote });
              toast.success(`${j.nom} reclassé dans ${domaineHote}`);
              recharger();
            } catch {
              toast.error("Reclassification impossible");
            }
          },
        },
      });
    } else if (!domaineHote && minDist > 160) {
      toast.info(`${j.nom} s'éloigne fortement de « ${j.domaine} » — appartenance à qualifier.`, { duration: 7000 });
    }
  };

  // Déplacement de caméra différé : le panneau s'ouvre et le menu se replie, la carte change de largeur. La cible est
  // calculée APRÈS cette mise en page (elle dépend de la taille de la carte) et le recadrage ne doit pas l'interrompre.
  const volerVers = (cible, duration) => {
    setTimeout(() => {
      const t = cible();
      animCamera.current = { ...animCamera.current, fin: Date.now() + duration, cible: t };
      rfRef.current?.setCenter(t.x, t.y, { zoom: t.zoom, duration });
    }, DELAI_MISE_EN_PAGE);
  };

  // Rendu graphe : un domaine se cherche comme un jumeau — la caméra cadre ses robots, les autres s'estompent
  const ouvrirDomaine = (label) => {
    setSelected(null); setSelectedRelation(null); setVueListe(null);
    setDomaineSel(label); setOnglet("detail"); setRecherche("");
    majUrl({ domaine: label, sel: null, jumeau: null });
    const membres = (mesh?.jumeaux || []).filter((j) => j.domaine === label && !j.anonyme && !j.cadastre);
    if (!membres.length) return;
    volerVers(() => {
      const pts = membres.map((j) => centreRendu(rfRef.current, j, posOverrides, DECALAGE_GRAPHE));
      const xs = pts.map((q) => q.x), ys = pts.map((q) => q.y);
      const r = carteRef.current?.getBoundingClientRect();
      const bw = Math.max(...xs) - Math.min(...xs) + 240, bh = Math.max(...ys) - Math.min(...ys) + 240;
      const zoom = r ? Math.min(1.2, Math.max(0.5, Math.min(r.width / bw, r.height / bh))) : 1;
      return { x: (Math.min(...xs) + Math.max(...xs)) / 2, y: (Math.min(...ys) + Math.max(...ys)) / 2, zoom };
    }, 600);
  };

  const centrerSurJumeau = (id) => {
    const j = mesh?.jumeaux.find((x) => x.id === id);
    if (!j) return;
    setHalo(id); // robot brièvement mis en évidence
    setTimeout(() => setHalo((h) => (h === id ? null : h)), 2000);
    // Comme le laboratoire : on vole jusqu'au jumeau tel qu'il est DESSINÉ, à un zoom lisible
    // Le panneau s'ouvre et le menu se replie : la carte change de largeur. On attend que ce soit posé, sinon le
    // recadrage de la carte interrompt l'animation et le jumeau finit hors champ.
    const c = centreRendu(rfRef.current, j, posOverrides, graphe ? DECALAGE_GRAPHE : DECALAGE_CLASSIQUE);
    volerVers(() => ({ x: c.x, y: c.y, zoom: graphe ? 1.2 : 1.4 }), graphe ? 500 : 600);
    majUrl({ sel: j.id, domaine: null });
    // La recherche/liste ouvre directement le détail à droite (survol = simple identification)
    setSelected(j);
    setSelectedRelation(null);
    setDomaineSel(null);
    setVueListe(null);
    setOnglet("detail");
    setRecherche("");
  };

  // Clic sur un jumeau de la vue à l'échelle : même ouverture que sur la scène (panneau, URL)
  const choisirDepuisEchelle = (t) => {
    const j = t.id && mesh?.jumeaux.find((x) => x.id === t.id && !x.anonyme);
    if (!j) { toast.info("Jumeau du jeu d'essai — pas de fiche"); return; }
    setSelected(j); setSelectedRelation(null); setDomaineSel(null); setVueListe(null); setOnglet("detail");
    majUrl({ sel: j.id, domaine: null });
  };

  const eventsVisibles = events.filter((e) => couches[e.dynamique || "operationnelle"]);

  const confirmerRelation = async (r) => {
    try {
      await api.post(`/relations/${r.id}/confirmer`);
      toast.success("Relation confirmée — mémoire du Mesh enrichie");
      setSelectedRelation(null);
      recharger();
    } catch {
      toast.error("Confirmation impossible — permission « Valider » requise");
    }
  };

  const actionsDomaine = domaineSel
    ? {
        onExplorer: () => explorerDomaine(domaineSel), // déplacement animé, zoom constant
        onAjuster: () => explorerDomaine(domaineSel, { ajuster: true }), // fitBounds explicite
        onExplorerVers: (dom) => explorerDomaine(dom),
        onComparer: () => { setAttenteComparaison(true); toast.info("Cliquez un second domaine pour comparer"); },
        onEnregistrer: async () => {
          const stats = statsDomaine(domaineSel);
          if (!stats) return;
          try {
            await api.post("/vues", { nom: `Domaine ${domaineSel}`, type: "selection", jumeaux: stats.twins.map((j) => j.id) });
            rechargerVues();
            toast.success(`Domaine ${domaineSel} enregistré comme espace de travail (vue)`);
          } catch {
            toast.error("Enregistrement impossible");
          }
        },
        perimetre: perimetreTravail === domaineSel,
        onPerimetre: () => setPerimetreTravail(perimetreTravail === domaineSel ? null : domaineSel),
      }
    : null;

  return (
    <div className="flex h-full flex-col">
    {/* Layout façon Google Maps : colonnes de part et d'autre de la carte — le chrome ne bouge jamais.
        Jumeau à gauche (intelligence locale) ; domaine/relation/listes à droite ; Flore remplace la droite. */}
    <div className="relative flex min-h-0 flex-1">
    <div ref={carteRef} onPointerMove={surSurvolCarte} onPointerLeave={() => { setRegionSurvolee(null); setRegionTooltip(null); setSecteurCurseur(null); setRelSurvolee(null); setRelTooltipPos(null); setSurvolJumeau(null); if (telemetrieRef.current) { telemetrieRef.current.textContent = "—"; telemetrieRef.current.style.opacity = "0.35"; } }} className="relative min-w-0 flex-1 overflow-hidden" data-testid="system-map" style={{ background: graphe ? "var(--hub-void)" : "radial-gradient(ellipse at 50% 38%, #0D1B28 0%, #071019 60%, #04090F 100%)" }}>
      {!graphe && <CielEtoile />}
      {/* Rendu graphe : halos bleu (haut droit) et rouge (bas) du hero de hubstechs.com, très discrets */}
      {graphe && <div aria-hidden="true" className="pointer-events-none absolute inset-0" style={{ background: "radial-gradient(ellipse 55% 45% at 90% 4%, rgba(0,51,160,0.26), transparent 70%), radial-gradient(ellipse 45% 35% at 55% 108%, rgba(227,0,15,0.07), transparent 70%)" }} />}
      {/* Démonstration : la surface annonce ce qu'elle prépare. À la première ouverture,
          surface sobre et pleine ; en mise à jour, la vue précédente reste visible dessous. */}
      {pilote?.preparation?.surface === "atlas" && <SurfacePreparation preparation={pilote.preparation} vierge={pilote.premiereScene} testid="atlas-preparation" />}
      <output
        ref={telemetrieRef}
        data-testid="telemetrie"
        aria-hidden="true"
        className="pointer-events-none absolute bottom-3 left-3 z-10 select-none font-code text-[9px] uppercase tracking-[0.18em] text-[#7C93A8]/80 transition-opacity duration-200"
        style={{ opacity: 0.35 }}
      >—</output>
      {echelle ? (
        <AtlasEchelle synthetique={echelleSynth} selectionId={selected?.id || null} onChoisir={choisirDepuisEchelle} />
      ) : (
      <ReactFlow
        key={focus || situationParam || "mesh"}
        colorMode="dark"
        nodes={nodesRendus}
        edges={edgesVisibles}
        nodeTypes={graphe ? nodeTypesGraphe : nodeTypes}
        edgeTypes={graphe ? edgeTypesGraphe : edgeTypes}
        fitView={!restaurerEtat}
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.45}
        maxZoom={2.6}
        // Étendue élargie : au zoom min (0.45) sur écran large, l'ancienne étendue
        // (3900 px monde → 1755 px écran) était plus étroite que le viewport → le pan
        // horizontal se verrouillait complètement. Marge généreuse mais bornée :
        // un pan violent ne peut toujours pas faire disparaître la carte.
        translateExtent={[[-1600, -1100], [3800, 2600]]}
        zoomOnDoubleClick={false}
        onInit={(inst) => {
          rfRef.current = inst;
          if (restaurerEtat && atlasEtat?.viewport) {
            // Retour à l'Atlas : on restaure la fenêtre exacte, sans fitView
            requestAnimationFrame(() => inst.setViewport(atlasEtat.viewport));
          }
          requestAnimationFrame(() => {
            const r = carteRef.current?.getBoundingClientRect();
            const vp = inst.getViewport();
            if (r) centreMonde.current = { x: (r.width / 2 - vp.x) / vp.zoom, y: (r.height / 2 - vp.y) / vp.zoom };
          });
          setTimeout(() => {
            try { inst.updateNodeInternals(inst.getNodes().map((n) => n.id)); } catch { /* mesure ultérieure */ }
          }, 120);
        }}
        onMove={surMove}
        onMoveEnd={surMoveEnd}
        onNodeDragStart={debutDrag}
        onNodeDragStop={finDrag}
        onNodeMouseEnter={(e, node) => {
          if (node.type === "twin" && node.data?.jumeau && !node.data.jumeau.anonyme) {
            setSurvolJumeau(node.data.jumeau.id);
            const rect = carteRef.current?.getBoundingClientRect();
            if (rect) setTooltipPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
          }
        }}
        onNodeMouseLeave={() => setSurvolJumeau(null)}
        onNodesChange={onNodesChange}
        panOnDrag={outil === "deplacement"}
        selectionOnDrag={outil === "lasso"}
        selectionMode={SelectionMode.Partial}
        // La sélection est contrôlée (notre état « selection » est la source de vérité) :
        // pas de multiSelectionKeyCode RF — Maj+clic est géré dans onNodeClick (additif)
        onSelectionStart={() => { selAvantLasso.current = selection; }}
        onSelectionEnd={() => {
          const ids = (rfRef.current?.getNodes() || []).filter((n) => n.selected && n.type === "twin").map((n) => n.id);
          if (ids.length) setSelection([...new Set([...selAvantLasso.current, ...ids])]);
        }}
        onNodeClick={(e, node) => {
          if (outil === "lasso") return;
          if (node.type === "region") {
            const label = node.data.label;
            const dc = dernierClicRegion.current;
            dernierClicRegion.current = { kind: "region", label, t: Date.now() };
            if (dc.kind === "region" && dc.label === label && Date.now() - dc.t < 450) {
              explorerDomaine(label); // double-clic : déplacement animé à zoom constant
              return;
            }
            if (attenteComparaison && domaineSel && label !== domaineSel) {
              setComparaison({ a: domaineSel, b: label });
              setAttenteComparaison(false);
            } else {
              setDomaineSel(label);
            }
            majUrl({ domaine: label, sel: null });
            setSelected(null);
            setSelectedRelation(null);
            setVueListe(null);
            setOnglet("detail");
            return;
          }
          if (node.data?.grappe) {
            // Clic sur une grappe : zoom avant explicite centré — les jumeaux se déploient (niveau 3)
            rfRef.current?.setCenter(node.position.x + 30, node.position.y + 40, { zoom: 1.35, duration: 600 });
            return;
          }
          if (node.type !== "twin") return;
          const dcT = dernierClicRegion.current;
          dernierClicRegion.current = { kind: "twin", id: node.data.jumeau.id, t: Date.now() };
          if (dcT.kind === "twin" && dcT.id === node.data.jumeau.id && Date.now() - dcT.t < 450 && !node.data.jumeau.anonyme) {
            centrerJumeau(node.data.jumeau); // double-clic : déplacement + zoom explicite centré sur le jumeau
            return;
          }
          setSelected(node.data.jumeau);
          setSelectedRelation(null);
          setDomaineSel(null);
          setVueListe(null);
          setOnglet("detail");
          // Moteur d'interaction : un seul point chaud à la fois — le clic remplace le survol
          setSurvolJumeau(null);
          setRelSurvolee(null);
          setRelTooltipPos(null);
          setRegionTooltip(null);
          majUrl({ sel: node.data.jumeau.id, domaine: null });
        }}
        onNodeDoubleClick={(_, node) => {
          if (outil === "lasso") return;
          if (node.type === "region") {
            explorerDomaine(node.data.label);
            return;
          }
          if (node.type === "twin" && node.data?.jumeau && !node.data.jumeau.anonyme) centrerJumeau(node.data.jumeau);
        }}
        onEdgeClick={(_, edge) => {
          const rel = mesh?.relations.find((r) => r.id === edge.id);
          if (!rel) return;
          setSelectedRelation(rel);
          setSelected(null);
          setVueListe(null);
          setSurvolJumeau(null);
          setRelSurvolee(null);
          setRelTooltipPos(null);
          setRegionTooltip(null);
          setOnglet("detail");
        }}
        onEdgeMouseEnter={(e, edge) => {
          setRelSurvolee(edge.id);
          const rect = carteRef.current?.getBoundingClientRect();
          if (rect) setRelTooltipPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
        }}
        onEdgeMouseLeave={() => { setRelSurvolee(null); setRelTooltipPos(null); }}
        onPaneClick={(e) => {
          // Double-clic sur une zone vide : zoom centré sur le pointeur (façon Google Maps)
          const dcP = dernierClicPane.current;
          dernierClicPane.current = Date.now();
          if (Date.now() - dcP < 420 && rfRef.current && carteRef.current) {
            const rect = carteRef.current.getBoundingClientRect();
            const f = rfRef.current.screenToFlowPosition({ x: e.clientX, y: e.clientY });
            const vp = rfRef.current.getViewport();
            const z2 = Math.min(vp.zoom * 1.35, 2.6);
            rfRef.current.setViewport({ x: e.clientX - rect.left - f.x * z2, y: e.clientY - rect.top - f.y * z2, zoom: z2 }, { duration: 240 });
          }
          const dc = dernierClicRegion.current;
          dernierClicRegion.current = { kind: null, t: 0 };
          if (Date.now() - dc.t < 450 && rfRef.current && mesh) {
            const p = rfRef.current.screenToFlowPosition({ x: e.clientX, y: e.clientY });
            if (dc.kind === "twin") {
              const j = mesh.jumeaux.find((x) => x.id === dc.id && !x.anonyme);
              if (j) {
                const pos = posOverrides[j.id] || j.position;
                if (Math.abs(p.x - (pos.x + 30)) < 90 && Math.abs(p.y - (pos.y + 40)) < 85) { centrerJumeau(j); return; }
              }
            }
            if (dc.kind === "region") {
              const reg = (mesh.regions || []).find((r) => r.label === dc.label);
              if (reg && p.x >= reg.x && p.x <= reg.x + reg.w && p.y >= reg.y && p.y <= reg.y + reg.h) {
                explorerDomaine(dc.label);
                return;
              }
            }
          }
          // Tactile : le tap dans une zone vide d'une membrane sélectionne son domaine
          // (remplace le survol, qui n'existe pas au toucher) — le tap sur un robot reste prioritaire
          if (estTactile && rfRef.current) {
            const p = rfRef.current.screenToFlowPosition({ x: e.clientX, y: e.clientY });
            const membrane = nodes.find((n) => n.type === "region" && n.data.points && dansPolygone(p, n.data.points, n.position.x, n.position.y));
            if (membrane) {
              setSelected(null);
              setSelectedRelation(null);
              setDomaineSel(membrane.data.label);
              setOnglet("detail");
              majUrl({ domaine: membrane.data.label, sel: null });
              return;
            }
          }
          setSelected(null); setSelectedRelation(null); setDomaineSel(null); setSelection([]); setRelFocus(false); setComparaison(null); setAttenteComparaison(false); commanderCarte(null); setVueListe(null);
          majUrl({ sel: null, domaine: null, jumeau: null });
        }}
        nodesDraggable={modeEdition}
        nodesConnectable={false}
      >
        {/* Rendu graphe : fond uni + trame de points, comme le laboratoire ; rendu classique : ciel étoilé fixe */}
        {graphe && <Background gap={26} size={1} color="rgba(96,165,250,0.17)" bgColor="transparent" />}
        <Controls showInteractive={false} showFitView={false} position="bottom-right" style={{ marginBottom: estTablette ? 8 : 148, marginRight: 14 }}>
          <ControlButton onClick={pleinEcran} title="Plein écran" data-testid="plein-ecran-btn">
            <CornersOut size={14} />
          </ControlButton>
        </Controls>
        {/* Mini-carte : masquée sur mobile (remplacée par le bouton « Vue d'ensemble ») */}
        {!estMobile && (
          <MiniMap
            position="bottom-right"
            pannable
            zoomable
            style={{ width: 168, height: 112 }}
            nodeColor={(n) => (n.type === "region" ? `${n.data?.couleur || "#7C93A8"}66` : couleurDomaine(n.data?.jumeau?.domaine))}
            maskColor="rgba(4,9,15,0.55)"
            data-testid="minimap"
          />
        )}
        {/* Étiquettes de domaines — révélées au survol de la membrane (niveaux 2-3) ;
            toujours visibles au niveau 1 (vue macro, elles sont le contenu) */}
        <ViewportPortal>
          {nodes.filter((n) => n.type === "region").map((n) => {
            const d = n.data;
            const m = d.maturite;
            const mc = m ? MATURITES[m.niveau] || "#7C93A8" : null;
            const sx = d.w / (d.wCible || d.w);
            const sy = d.h / (d.hCible || d.h);
            const lx = n.position.x + (d.labelX ?? d.w / 2) * sx;
            const ly = n.position.y + (d.labelY ?? 30) * sy;
            const visible =
              (zoomNiveau === 1 ||
                regionSurvolee?.id === d.id ||
                domaineSel === d.label ||
                couchesCarte.capacites ||
                (theatreSituationnel?.actif && !d.cadastre)) &&
              titresVisibles.has(d.id);
            return (
              <div
                key={n.id}
                className="nopan"
                style={{ position: "absolute", left: lx, top: ly, transform: "translate(-50%, -50%)", pointerEvents: visible ? "auto" : "none", cursor: "pointer" }}
                title="Clic : sélectionner le domaine · Double-clic : explorer le domaine"
                data-testid={`region-header-${d.id}`}
                onClick={() => {
                  setSelected(null);
                  setSelectedRelation(null);
                  setDomaineSel(d.label);
                  setOnglet("detail");
                  majUrl({ domaine: d.label, sel: null });
                }}
                onDoubleClick={() => explorerDomaine(d.label)}
              >
                <div className="flex flex-col items-center gap-0.5">
                  <div className="flex items-center justify-center gap-2">
                    {d.halo && (
                      <span className="halo-anim h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: d.couleur }} data-testid={`region-activite-${d.id}`} />
                    )}
                    <span
                      className="whitespace-nowrap rounded bg-[#0F1D28]/60 px-1.5 py-0.5 font-display text-[13px] font-semibold uppercase tracking-[0.2em] backdrop-blur-[2px] transition-opacity duration-200"
                      style={{ color: d.couleur, opacity: visible ? 1 : 0, textShadow: `0 0 14px ${d.couleur}80` }}
                    >
                      {d.label}
                    </span>
                  </div>
                  {mc && !d.macro && (
                    <span
                      className="rounded-full border bg-[#0F1D28]/80 px-1.5 py-0.5 font-code text-[8px] uppercase tracking-wider transition-opacity duration-200"
                      style={{ color: mc, borderColor: `${mc}44`, opacity: visible ? 1 : 0 }}
                    >
                      {m.niveau}
                    </span>
                  )}
                </div>
                {(d.macro || (couchesCarte.capacites && visible)) && m && (d.opaciteMacro ?? 1) > 0.02 && (
                  <div className="mt-1 flex items-center justify-center gap-2 font-code text-[10px] text-[#94A3B8]" style={{ opacity: d.opaciteMacro ?? 1, transition: "opacity 200ms" }} data-testid={`region-macro-${d.id}`}>
                    <span>{m.jumeaux} jumeau{m.jumeaux > 1 ? "x" : ""}</span>
                    <span className="text-[#7C93A8]">·</span>
                    <span>{d.flux ?? 0} flux</span>
                    <span className="text-[#7C93A8]">·</span>
                    <span className={(d.ecarts ?? 0) > 0 ? "text-[#F2B84B]" : ""}>{d.ecarts ?? 0} écart{(d.ecarts ?? 0) > 1 ? "s" : ""}</span>
                  </div>
                )}
              </div>
            );
          })}
        </ViewportPortal>
      </ReactFlow>
      )}

      {/* Marqueurs de flèches partagés par les arêtes orthogonales */}
      <svg width="0" height="0" style={{ position: "absolute" }}>
        <defs>
          <marker id="marqueur-ardoise" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="rgba(148,163,184,0.75)" />
          </marker>
          <marker id="marqueur-teal" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#25D0C8" />
          </marker>
          <marker id="marqueur-orange" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#F2B84B" />
          </marker>
          <marker id="marqueur-violet" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#9B87F5" />
          </marker>
        </defs>
      </svg>

      {/* Recherche — îlot haut-gauche (façon Google Maps). Rétractée en loupe quand un panneau
          (détail ou Flore) est ouvert : un clic sur la loupe la re-déplie à la demande. */}
      <div className="pointer-events-none absolute left-4 top-4 z-20">
        <div className="pointer-events-auto relative">
          {!rechercheOuverte ? (
            <button onClick={() => (estMobile ? setRechercheMobileOuverte(true) : setLoupeForcee(true))} data-testid="btn-recherche" title="Rechercher" className="glass rounded-xl p-2.5 text-[#94A3B8] transition-colors hover:text-[#F2F6F8]">
              <MagnifyingGlass size={14} />
            </button>
          ) : (
            <div className="glass flex items-center gap-2 rounded-xl px-3 py-2">
              <MagnifyingGlass size={13} className="shrink-0 text-[#7C93A8]" />
              <input
                value={recherche}
                onChange={(e) => setRecherche(e.target.value)}
                onKeyDown={(e) => {
                  // Enter : sélectionne le premier résultat et ramène la carte vers lui
                  if (e.key !== "Enter" || resultatsRecherche.length === 0) return;
                  noterRecherche(recherche);
                  const r = resultatsRecherche[0];
                  if (r.type === "jumeau") centrerSurJumeau(r.id);
                  else if (graphe) ouvrirDomaine(r.id);
                  else { setDomaineSel(r.id); setRecherche(""); }
                  if (estMobile) setRechercheMobileOuverte(false);
                  setLoupeForcee(false);
                }}
                placeholder="Rechercher un jumeau, domaine, flux…"
                data-testid="atlas-recherche"
                className={`${estMobile ? "w-[44vw]" : "w-64"} bg-transparent text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] focus:outline-none`}
              />
              {(estMobile || loupeForcee || panneauOuvert) && (
                <button onClick={() => { setRechercheMobileOuverte(false); setLoupeForcee(false); setRecherche(""); }} data-testid="btn-recherche-fermer" title="Refermer la recherche" className="text-[#7C93A8] transition-colors hover:text-[#F2F6F8]"><X size={13} /></button>
              )}
            </div>
          )}
          {rechercheOuverte && resultatsRecherche.length > 0 && (
            <div className="glass absolute left-0 top-11 z-30 w-72 rounded-xl p-1.5" data-testid="atlas-recherche-resultats">
              {resultatsRecherche.map((r) => (
                <button
                  key={`${r.type}-${r.id}`}
                  onClick={() => { noterRecherche(recherche); if (r.type === "jumeau") centrerSurJumeau(r.id); else if (graphe) ouvrirDomaine(r.id); else { setDomaineSel(r.id); setRecherche(""); } }}
                  data-testid={`recherche-${r.type}-${r.id}`}
                  className="w-full rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-[rgba(148,163,184,0.10)]"
                >
                  <div className="text-xs font-semibold text-[#F2F6F8]">{r.label}</div>
                  <div className="font-code text-[9px] text-[#7C93A8]">{r.sub}</div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Pile haute centrée — fil d'Ariane et bannières contextuelles : empilement vertical,
          chaque élément occupe sa propre ligne, jamais de superposition */}
      <div className="pointer-events-none absolute left-1/2 top-3 z-20 flex -translate-x-1/2 flex-col items-center gap-2">
        <FilAriane
          domaineActif={domaineActif}
          selection={selection}
          revenirSelection={revenirSelection}
          ajusterVue={() => {
            if (theatreSituationnel.actif) {
              quitterTheatreSituationnel();
            } else {
              ajusterVue();
            }
          }}
          dansSituation={theatreSituationnel.actif}
          situationTitre={theatreSituationnel.titre}
        />

        {/* Bannière situation (focus profond depuis Aujourd'hui / Investigations) */}
        {situation && (
          <div className="glass pointer-events-auto flex max-w-md items-center gap-3 rounded-xl px-4 py-2.5 shadow-lg shadow-[#9B87F5]/10" data-testid="map-situation-banner">
            <div className="flex-1 min-w-0">
              <div className="font-code text-[9px] uppercase tracking-[0.25em] text-[#9B87F5]">Focus — situation</div>
              <div className="text-xs font-semibold text-[#F2F6F8] truncate">{situation.titre}</div>
              <div className="mt-0.5 font-code text-[9px] text-[#7C93A8]">
                {situation.jumeaux.length} jumeaux · contexte réduit au pertinent
              </div>
            </div>
            <button
              onClick={quitterTheatreSituationnel}
              data-testid="theatre-situation-retour-global"
              className="flex items-center gap-1 rounded-md border border-[#9B87F5]/40 bg-[#9B87F5]/10 px-2 py-1 font-code text-[10px] font-semibold text-[#9B87F5] transition-colors hover:bg-[#9B87F5]/20 hover:text-white"
            >
              <Globe size={12} />
              <span>Vue globale</span>
            </button>
            <button onClick={() => { majUrl({ situation: null }); quitterTheatreSituationnel(); }} data-testid="map-clear-situation" title="Retirer le focus situation" className="shrink-0 text-[#7C93A8] transition-colors hover:text-[#F2F6F8]">
              <X size={13} />
            </button>
          </div>
        )}

        {/* Indicateur de périmètre de travail actif (filtre volontaire, distinct de la sécurité) */}
        {perimetreTravail && (
          <div className="glass pointer-events-auto flex items-center gap-2 rounded-xl px-4 py-2" data-testid="perimetre-travail-chip">
            <span className="h-1.5 w-1.5 rounded-full bg-[#25D0C8]" />
            <span className="font-code text-[10px] text-[#94A3B8]">
              Périmètre de travail : <span style={{ color: couleurDomaine(perimetreTravail) }}>{perimetreTravail}</span> — filtre volontaire, pas sécurité
            </span>
            <button onClick={() => setPerimetreTravail(null)} data-testid="perimetre-travail-clear" className="text-[#7C93A8] transition-colors hover:text-[#F2F6F8]">
              <X size={12} />
            </button>
          </div>
        )}
      </div>

      {/* Infobulle d'identification au survol — une ligne, aucune action, aucun bloc de stats
          (le détail vit dans le panneau de droite au clic ; règle d'unicité : masquée si un panneau est ouvert) */}
      {/* Rendu graphe : fiche d'aperçu du laboratoire — nom, domaine, degré, couverture, fraîcheur, mission — posée à côté du robot */}
      {graphe && !echelle && !estTablette && jumeauSurvole && (() => {
        const rf = rfRef.current;
        const el = carteRef.current;
        if (!rf || !el || !analyse) return null;
        const c = centreRendu(rf, jumeauSurvole, posOverrides, DECALAGE_GRAPHE);
        const boite = el.getBoundingClientRect();
        const p = rf.flowToScreenPosition(c);
        const r = tailleDe(analyse, jumeauSurvole.id) * 0.7 * rf.getZoom();
        const L = 236;
        let left = p.x - boite.left + r + 14;
        if (left + L > boite.width - 8) left = p.x - boite.left - r - 14 - L;
        const top = Math.max(8, Math.min(p.y - boite.top - 44, boite.height - 190));
        const j = jumeauSurvole;
        return (
          <div className="glass hub-coins pointer-events-none absolute z-30 w-[236px] space-y-1.5 rounded-xl p-3" style={{ left, top }} data-testid="infobulle-jumeau">
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: couleurDomaine(j.domaine) }} />
              <span className="font-display min-w-0 flex-1 truncate text-base text-white" data-testid="infobulle-nom">{j.nom}</span>
              <span className="font-code text-[10px] text-[#64748B]">{idNumerique(j.id)}</span>
            </div>
            <div className="font-code text-[10px] uppercase tracking-wider text-[#7C93A8]">
              {j.domaine}
              {analyse.ecarts.has(j.id) && <span className="ml-2 text-[#F59E0B]">⚠ écart</span>}
            </div>
            <div className="grid grid-cols-2 gap-1.5 pt-0.5 text-center">
              {[["Degré", `${analyse.deg.get(j.id) || 0}`], ["Couverture", j.couverture != null ? `${j.couverture} %` : "—"]].map(([k, v]) => (
                <div key={k} className="rounded-lg bg-white/[0.04] px-1 py-1">
                  <div className="font-code text-[11px] font-semibold text-[#F2F6F8]" data-testid={k === "Couverture" ? "infobulle-confiance" : undefined}>{v}</div>
                  <div className="font-code text-[8px] uppercase tracking-wider text-[#64748B]">{k}</div>
                </div>
              ))}
            </div>
            {j.fraicheur && <div className="font-code text-[10px] text-[#7C93A8]">Fraîcheur : <span className="text-[#CBD5E1]">{j.fraicheur}</span></div>}
            {j.mission && <p className="line-clamp-2 text-[11px] leading-snug text-[#94A3B8]">{j.mission}</p>}
            <div className="font-code text-[9px] text-[#526578]">Cliquer pour ouvrir la fiche</div>
          </div>
        );
      })()}

      {/* Rendu graphe : légende-filtre des domaines (plus de territoires — la couleur porte le domaine) et des états de lien */}
      {graphe && !echelle && mesh && (() => {
        const n = new Map();
        mesh.jumeaux.filter((j) => !j.anonyme && !j.cadastre).forEach((j) => n.set(j.domaine, (n.get(j.domaine) || 0) + 1));
        const domaines = [...n.entries()].sort((a, b) => b[1] - a[1]);
        return (
          <div className="glass hub-coins absolute bottom-10 left-3 z-10 w-[200px] rounded-xl p-2.5" data-testid="atlas-legende">
            <div className="mb-1 flex items-center justify-between font-code text-[9px] uppercase tracking-wider text-[#64748B]">
              <span>Domaines</span>
              {domainesMasques.size > 0 && <button onClick={() => setDomainesMasques(new Set())} className="normal-case text-[#25D0C8] hover:underline" data-testid="atlas-legende-tout">tout afficher</button>}
            </div>
            {domaines.map(([d, nb]) => (
              <div key={d} className={`flex items-center gap-1.5 rounded px-1 py-0.5 text-xs hover:bg-white/[0.05] ${domainesMasques.has(d) ? "opacity-40" : ""}`} data-testid={`atlas-legende-${d}`}>
                <input type="checkbox" checked={!domainesMasques.has(d)} onChange={() => setDomainesMasques((m) => { const s = new Set(m); if (s.has(d)) s.delete(d); else s.add(d); return s; })} className="accent-[#9B87F5]" aria-label={`Afficher ${d}`} />
                <button onClick={() => ouvrirDomaine(d)} title={`Ouvrir le domaine ${d}`} className="flex min-w-0 flex-1 items-center gap-1.5 text-left">
                  <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: couleurDomaine(d) }} />
                  <span className="flex-1 truncate text-[#DCE6EE]">{d}</span>
                  <span className="font-code text-[10px] text-[#7C93A8]">{nb}</span>
                </button>
              </div>
            ))}
            <div className="mt-1.5 space-y-0.5 border-t border-white/[0.07] pt-1.5">
              {Object.entries(ETATS_RELATION).map(([k, v]) => (
                <div key={k} className="flex items-center gap-2 text-[10px] text-[#94A3B8]">
                  <span className="inline-block w-5 border-t-2" style={{ borderColor: v.couleur, borderStyle: STYLE_ETAT[k]?.pointille ? "dashed" : "solid" }} />
                  {v.label}
                </div>
              ))}
            </div>
          </div>
        );
      })()}

      {!graphe && !estTablette && jumeauSurvole && zoomNiveau > 1 && !panneauOuvert && tooltipPos && (
        <div
          className="pointer-events-none absolute z-30 flex items-center gap-1.5 rounded-lg border border-[rgba(148,163,184,0.16)] bg-[#0F1D28]/95 px-2.5 py-1.5 shadow-md"
          style={{ left: tooltipPos.x + 14, top: tooltipPos.y + 14 }}
          data-testid="infobulle-jumeau"
        >
          <span className="h-2 w-2 rounded-full" style={{ backgroundColor: couleurDomaine(jumeauSurvole.domaine) }} />
          <span className="font-code text-[10px] font-semibold text-[#7C93A8]">{idNumerique(jumeauSurvole.id)}</span>
          <span className="text-[11px] font-semibold text-[#F2F6F8]" data-testid="infobulle-nom">{jumeauSurvole.nom}</span>
          <span className="font-code text-[9px] text-[#25D0C8]" data-testid="infobulle-confiance">{jumeauSurvole.confiance?.valeur ?? jumeauSurvole.couverture ?? "—"} %</span>
        </div>
      )}

      <AtlasControle
        mesh={mesh} focus={focus}
        modeTemps={modeTemps} setModeTemps={(m) => { setModeTemps(m); if (m === "direct" || m === "pause") { setReplaying(false); setDateRef(null); } }}
        dateRef={dateRef} setDateRef={setDateRef}
        replaying={replaying} onRejouer={() => setReplaying(true)}
        couches={couches} setCouches={setCouches}
        couchesRel={couchesRel} setCouchesRel={setCouchesRel}
        couchesCarte={couchesCarte} setCouchesCarte={setCouchesCarte}
        rechargerVues={rechargerVues}
        deplie={calquesOuverts} setDeplie={setCalquesOuverts} conteneurRef={carteRef}
      />

      {!theatreSituationnel.actif && (
        <AtlasToolbar outil={outil} setOutil={setOutil} rfRef={rfRef} onExpliquer={() => setExpliquerOuvert((o) => !o)} expliquerOuvert={expliquerOuvert} modeEdition={modeEdition} setModeEdition={setModeEdition} vueListe={vueListe} onOuvrirListe={setVueListe} conteneurRef={carteRef} />
      )}

      {/* Pile basse centrée — chip Flore, mode réorganisation, bandeaux temporels, niveau de zoom :
          empilés verticalement, chaque indicateur garde sa propre ligne */}
      <div className="pointer-events-none absolute bottom-4 left-1/2 z-10 flex -translate-x-1/2 flex-col items-center gap-2">
        {/* Barre de multisélection : actions groupées sur les jumeaux choisis (masquée en scène d'analyse pour focus zen) */}
        {selection.length > 1 && !theatreSituationnel.actif && (
          <div className="glass pointer-events-auto flex flex-wrap items-center justify-center gap-1.5 rounded-xl px-3 py-2" data-testid="multi-selection-bar">
            <span className="font-code text-[10px] font-semibold text-[#F2F6F8]" data-testid="multi-selection-compte">{selection.length} jumeaux sélectionnés</span>
            <button onClick={() => parlerAuJumeau(selection)} data-testid="multi-interroger" className="rounded-md border border-[#9B87F5]/40 px-2 py-0.5 font-code text-[10px] font-semibold text-[#9B87F5] transition-colors hover:bg-[#9B87F5]/10">Interroger</button>
            <button onClick={() => { setRelFocus(true); toast.info("Trajets de la sélection mis en avant"); }} data-testid="multi-relations" className="rounded-md border border-[rgba(148,163,184,0.16)] px-2 py-0.5 font-code text-[10px] text-[#94A3B8] transition-colors hover:text-[#F2F6F8]">Relations</button>
            <button onClick={creerGroupeSelection} data-testid="multi-groupe" className="rounded-md border border-[rgba(148,163,184,0.16)] px-2 py-0.5 font-code text-[10px] text-[#94A3B8] transition-colors hover:text-[#F2F6F8]">Créer un groupe</button>
            <button onClick={() => demanderAFlore("Qu'ont en commun ces jumeaux ? Capacités, sources, propriétaires, relations…")} data-testid="multi-commun" className="rounded-md border border-[rgba(148,163,184,0.16)] px-2 py-0.5 font-code text-[10px] text-[#94A3B8] transition-colors hover:text-[#F2F6F8]">Point commun</button>
            <button onClick={() => { setSelection([]); setRelFocus(false); }} data-testid="multi-fermer" title="Effacer la sélection" className="text-[#7C93A8] transition-colors hover:text-[#F2F6F8]"><X size={12} /></button>
          </div>
        )}


        {focusCarte && !theatreSituationnel.actif && (
          <div className="glass pointer-events-auto flex items-center gap-2 rounded-lg px-3 py-1.5" data-testid="focus-flore-chip">
            <Sparkle size={12} className="text-[#9B87F5]" />
            <span className="font-code text-[10px] text-[#94A3B8]">Vue commandée par Flore</span>
            <button onClick={() => commanderCarte(null)} data-testid="focus-flore-clear" className="text-[#7C93A8] transition-colors hover:text-[#F2F6F8]">
              <X size={12} />
            </button>
          </div>
        )}

        {modeEdition && (
          <div className="glass pointer-events-auto flex items-center gap-2 rounded-lg px-3 py-1.5" data-testid="mode-edition-chip">
            <span className="h-1.5 w-1.5 rounded-full bg-[#F2B84B]" />
            <span className="font-code text-[10px] text-[#94A3B8]">
              Mode réorganisation — glissez un robot ; la reclassification est toujours proposée, jamais automatique
            </span>
            <button onClick={() => setModeEdition(false)} data-testid="mode-edition-quitter" className="text-[#7C93A8] transition-colors hover:text-[#F2F6F8]">
              <X size={12} />
            </button>
          </div>
        )}

        {(modeTemps === "historique" || modeTemps === "replay") && dateRef && (
          <div className="glass pointer-events-auto flex items-center gap-3 rounded-xl px-4 py-2" data-testid="bandeau-temps">
            <span className="font-code text-[10px] text-[#94A3B8]">
              {modeTemps === "replay" ? "Relecture du Mesh" : "Photographie du Mesh"} au <strong className="text-[#F2F6F8]">{fmtDate(dateRef)}</strong>
            </span>
            <button onClick={() => { setModeTemps("direct"); setReplaying(false); setDateRef(null); majUrl({ date: null }); }} data-testid="retour-direct-btn" className="rounded-md border border-[#9B87F5]/40 px-2 py-0.5 font-code text-[10px] font-semibold text-[#9B87F5] transition-colors hover:bg-[#9B87F5]/10">
              Revenir au direct
            </button>
          </div>
        )}
        {modeTemps === "avantapres" && dateRef && (
          <div className="glass pointer-events-auto flex items-center gap-3 rounded-xl px-4 py-2" data-testid="bandeau-avant-apres">
            <span className="h-2 w-2 rounded-sm border-2 border-dashed border-[#25D0C8]" />
            <span className="font-code text-[10px] text-[#94A3B8]">
              Avant/Après depuis le <strong className="text-[#F2F6F8]">{fmtDate(dateRef)}</strong> — {nbNouvelles} nouvelle{nbNouvelles > 1 ? "s" : ""} relation{nbNouvelles > 1 ? "s" : ""}
            </span>
            <button onClick={() => { setModeTemps("direct"); setDateRef(null); }} data-testid="retour-direct-btn-aa" className="rounded-md border border-[#9B87F5]/40 px-2 py-0.5 font-code text-[10px] font-semibold text-[#9B87F5] transition-colors hover:bg-[#9B87F5]/10">
              Revenir au direct
            </button>
          </div>
        )}

        {/* Niveau de zoom sémantique — échelle globale, identique partout dans le Mesh */}
        <div className={`glass rounded-lg px-3 py-1.5 font-code text-[10px] text-[#94A3B8] ${echelle ? "hidden" : ""}`} data-testid="zoom-niveau">
          {`Niveau ${zoomNiveau} · ${NIVEAUX_ZOOM[zoomNiveau]}`}
          {zoomNiveau === 1 && " · corridors agrégés"}
          {zoomNiveau === 3 && " · détail des relations"}
          {zoomNiveau === 4 && " · sources et strates arbitrées par priorité"}
        </div>
      </div>

      {/* Position fantôme du robot en cours de déplacement */}
      {fantome && (
        <div
          className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-1/2"
          style={{ left: fantome.x, top: fantome.y }}
          data-testid="robot-fantome"
        >
          <span className="flex h-12 w-12 items-center justify-center rounded-full border-2 border-dashed border-[#7C93A8]/50 bg-[#0F1D28]/50">
            <img src="/assets/robot-jumeau.jpg" alt="" className="h-10 w-10 scale-[1.65] rounded-full object-cover opacity-35" />
          </span>
        </div>
      )}



      {expliquerOuvert && (
        <ExpliquerCarte
          mesh={mesh}
          fermer={() => setExpliquerOuvert(false)}
          domaineActif={domaineActif}
          jumeauPar={jumeauPar}
          selection={selection}
        />
      )}







      {/* Infobulle de relation — survol d'une arête, près du pointeur */}
      {relSurvolee?.startsWith("agg-") && !selectedRelation && relTooltipPos && (() => {
        const agg = edges.find((x) => x.id === relSurvolee);
        if (!agg?.data?.agregat) return null;
        return (
          <div
            className="pointer-events-none absolute z-30 w-56 rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-3 shadow-lg"
            style={{ left: Math.min(relTooltipPos.x + 14, (carteRef.current?.clientWidth || 1200) - 240), top: Math.max(relTooltipPos.y + 14, 8) }}
            data-testid="agregat-tooltip"
          >
            <div className="font-code text-[11px] font-semibold text-[#F2F6F8]">
              {idNumerique(agg.source)} ↔ {idNumerique(agg.target)}
            </div>
            <div className="mt-1.5 font-code text-[10px] text-[#94A3B8]">
              {agg.data.agregat.length} flux partagent ce corridor
            </div>
            <div className="mt-2 font-code text-[9px] text-[#25D0C8]">Routes déployées au survol</div>
          </div>
        );
      })()}
      {relSurvolee && !relSurvolee.startsWith("agg-") && !selectedRelation && relTooltipPos && mesh && (() => {
        const r = mesh.relations.find((x) => x.id === relSurvolee);
        if (!r) return null;
        const e = edgesVisibles.find((x) => x.id === relSurvolee);
        const etat = ETATS_RELATION[r.etat] || { label: r.etat, couleur: "#7C93A8" };
        return (
          <div
            className="pointer-events-none absolute z-30 w-56 rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-3 shadow-lg"
            style={{ left: Math.min(relTooltipPos.x + 14, (carteRef.current?.clientWidth || 1200) - 240), top: Math.max(relTooltipPos.y + 14, 8) }}
            data-testid="relation-tooltip"
          >
            <div className="font-code text-[11px] font-semibold text-[#F2F6F8]">
              {idNumerique(r.source)} → {idNumerique(r.cible)}
            </div>
            <div className="mt-1.5 space-y-0.5 font-code text-[10px] text-[#94A3B8]">
              <div style={{ color: etat.couleur }}>Relation {etat.label.toLowerCase()}</div>
              {e?.data?.label && <div>{e.data.label}</div>}
              {r.confiance != null && <div>Confiance : {r.confiance} %</div>}
              {(r.claims?.length ?? 0) > 0 && <div>{r.claims.length} preuve{r.claims.length > 1 ? "s" : ""}</div>}
            </div>
            <div className="mt-2 font-code text-[9px] text-[#25D0C8]">Clic : qualifier la relation →</div>
          </div>
        );
      })()}

      {/* Infobulle de membrane — proche de la frontière survolée */}
      {regionTooltip && regionSurvolee && (
        <div
          className="pointer-events-none absolute z-30 w-52 rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-3 shadow-lg"
          style={{ left: Math.min(regionTooltip.x + 16, (carteRef.current?.clientWidth || 1200) - 230), top: Math.max(regionTooltip.y + 16, 8) }}
          data-testid={`region-tooltip-${regionSurvolee.id}`}
        >
          <div className="font-display text-xs font-bold" style={{ color: regionTooltip.data.couleur }}>Domaine {regionTooltip.data.label}</div>
          <div className="mt-1.5 space-y-0.5 font-code text-[10px] text-[#94A3B8]">
            <div>{regionTooltip.data.maturite?.jumeaux ?? "—"} jumeaux</div>
            <div>{regionTooltip.data.flux ?? 0} flux observés</div>
            <div>{regionTooltip.data.ecarts ?? 0} écart{(regionTooltip.data.ecarts ?? 0) > 1 ? "s" : ""} structurel{(regionTooltip.data.ecarts ?? 0) > 1 ? "s" : ""}</div>
          </div>
          <div className="mt-2 font-code text-[9px] text-[#25D0C8]">Double-clic : explorer le domaine →</div>
        </div>
      )}



      {/* Mobile : la mini-carte devient un bouton « Vue d'ensemble » (fitView explicite) */}
      {estMobile && (
        <button
          onClick={() => rfRef.current?.fitView({ duration: 600, padding: 0.15 })}
          data-testid="btn-vue-ensemble"
          className="glass absolute bottom-24 right-3 z-10 rounded-full px-3 py-2.5 font-code text-[10px] uppercase tracking-[0.12em] text-[#94A3B8] transition-colors hover:text-[#F2F6F8]"
        >
          Vue d'ensemble
        </button>
      )}

    </div>

      {selected && !estTablette && (
        <PanneauJumeau
          jumeau={selected}
          voisins={voisinsSelection}
          relationsRecentes={relationsRecentes}
          favori={favorisIds.includes(selected.id)}
          onBasculerFavori={onBasculerFavori}
          statsTwin={statsSelection}
          onInterroger={() => parlerAuJumeau([selected.id])}
          onExplorerRelations={() => { setSelection([selected.id]); setRelFocus(true); toast.info("Trajets du jumeau mis en avant"); }}
          onOuvrirInvestigation={ouvrirInvestigationJumeau}
          onChoisirVoisin={centrerSurJumeau}
          onFermer={() => { setSelected(null); majUrl({ sel: null }); }}
        />
      )}
      <AtlasPanneau
        onglet={onglet} setOnglet={setOnglet}
        comparaison={comparaison} selectedRelation={selectedRelation}
        selected={selected} domaineSel={domaineSel}
        statsDomaine={statsDomaine} actionsDomaine={actionsDomaine}
        confirmerRelation={confirmerRelation}
        eventsVisibles={eventsVisibles} jumeauPar={jumeauPar}
        presentation={estTablette ? "feuillet" : "colonne"}
        masquee={floreOuverte}
        sansJumeau={!estTablette}
        onActionSituation={actionSituation}
        mesh={mesh} situations={situations} vueListe={vueListe} setVueListe={setVueListe}
        favorisIds={favorisIds} onBasculerFavori={onBasculerFavori}
        statsTwin={statsSelection}
        onInterroger={() => { if (selected) parlerAuJumeau([selected.id]); }}
        onChoisirJumeau={centrerSurJumeau}
        onChoisirSituation={(id) => majUrl({ situation: id })}
        onRelancerRecherche={(t) => { setRecherche(t); setLoupeForcee(true); if (estMobile) setRechercheMobileOuverte(true); }}
        onFermer={() => { setSelected(null); setSelectedRelation(null); setDomaineSel(null); setComparaison(null); setVueListe(null); majUrl({ sel: null, domaine: null }); }}
      />
    </div>
    </div>
  );
}
