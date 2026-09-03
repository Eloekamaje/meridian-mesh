import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ReactFlow, Background, BackgroundVariant, Controls, ControlButton, MiniMap, SelectionMode, ViewportPortal } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { X, Sparkle, CornersOut, MagnifyingGlass } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import { usePerimetre } from "@/lib/perimetre";
import { useContexte } from "@/lib/contexte";
import TwinNode from "@/components/map/TwinNode";
import RegionNode from "@/components/map/RegionNode";
import AreteOrthogonale from "@/components/map/AreteOrthogonale";
import AtlasControle from "@/components/map/AtlasControle";
import AtlasToolbar from "@/components/map/AtlasToolbar";
import AtlasLegende from "@/components/map/AtlasLegende";
import AtlasPanneau from "@/components/map/AtlasPanneau";
import FilAriane from "@/components/map/FilAriane";
import ExpliquerCarte from "@/components/map/ExpliquerCarte";
import useNavigationAtlas, { dansPolygone } from "@/components/map/useNavigationAtlas";
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
const edgeTypes = { ortho: AreteOrthogonale };

export default function Atlas() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { mesh, jumeauPar, recharger } = useMesh();
  const { version, vueActive, rechargerVues } = usePerimetre();
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
  const { selection, setSelection, domaineSel, setDomaineSel, focusCarte, commanderCarte, setFocusVisuel, ouvrirFlore, fermerFlore, floreOuverte, setAtlasCtx, atlasEtat, setAtlasEtat } = useContexte();

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
  const carteRef = useRef(null);
  const [amorce, setAmorce] = useState(0);
  const [mesures, setMesures] = useState({}); // dimensions mesurées par React Flow, réinjectées dans le graphe
  const [zoomActuel, setZoomActuel] = useState(1);
  const [regionSurvolee, setRegionSurvolee] = useState(null); // membrane survolée {id, label} (proximité frontière)
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

  // Commandes carte envoyées par Aurora (éclairer des relations, isoler un parcours, aller à un domaine)
  useEffect(() => {
    if (!focusCarte) return;
    if (focusCarte.type === "parcours" && focusCarte.ids?.length) {
      setSelection(focusCarte.ids.filter((id) => mesh?.jumeaux.some((j) => j.id === id)));
      setRelFocus(true);
    } else if (focusCarte.type === "domaine" && focusCarte.domaine) {
      explorerDomaine(focusCarte.domaine);
    }
  }, [focusCarte]);

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

  // Focus profond : la caméra cadre les jumeaux concernés (situation ou jumeau filtré)
  useEffect(() => {
    const cle = situation?.id || focus || null;
    if (!mesh || !cle || centreFocusFait.current === cle) return;
    const cibles = situation
      ? (situation.jumeaux || []).map((id) => mesh.jumeaux.find((j) => j.id === id)).filter(Boolean)
      : [mesh.jumeaux.find((j) => j.id === focus)].filter(Boolean);
    if (!cibles.length) return;
    centreFocusFait.current = cle;
    const t = setTimeout(() => {
      const pts = cibles.map((j) => posOverrides[j.id] || j.position);
      const xs = pts.map((p) => p.x);
      const ys = pts.map((p) => p.y);
      rfRef.current?.fitBounds(
        { x: Math.min(...xs) - 230, y: Math.min(...ys) - 190, width: Math.max(...xs) - Math.min(...xs) + 460, height: Math.max(...ys) - Math.min(...ys) + 380 },
        { duration: 800 }
      );
    }, 350);
    return () => clearTimeout(t);
  }, [mesh, situation, focus]);

  // Le contexte Aurora suit toujours le focus profond : les jumeaux concernés deviennent la sélection
  useEffect(() => {
    if (!mesh || !situation || selectionFocusFaite.current === situation.id) return;
    const ids = (situation.jumeaux || []).filter((id) => mesh.jumeaux.some((j) => j.id === id && !j.anonyme));
    if (ids.length) {
      selectionFocusFaite.current = situation.id;
      setSelection(ids);
    }
  }, [mesh, situation]);

  const { nodes, edges, snapshot } = useMemo(() => {
    const g = construireGraphe({
      mesh, situation, focus, vueActive, perimetreTravail,
      posOverrides, compteurs, halo, selection,
      zoomNiveau, relFocus, focusCarte, domDe, statsRegions, temps,
      zoomFort: zoomActuel >= 1.5,
      routesFin, provisoire, tactile: estTactile,
      couchesCarte, situationsJumeaux,
    });
    // Conserve les dimensions mesurées par React Flow : le graphe est reconstruit à chaque
    // tick de drag — sans cela les nœuds perdent leur mesure et les arêtes disparaissent.
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
      const prev = parId.get(n.id);
      const dim = mesures[n.id];
      const base = prev?.measured ? { ...n, measured: prev.measured, dragging: prev.dragging || undefined } : n;
      return dim ? { ...base, width: dim.width, height: dim.height, measured: { width: dim.width, height: dim.height } } : base;
    });
    ciblesCoques.current = nouvellesCibles;
    return g;
  }, [mesh, focus, situation, halo, compteurs, selection, relFocus, zoomNiveau, vueActive, posOverrides, domaineSel, perimetreTravail, domDe, statsRegions, focusCarte, temps, amorce, mesures, regionSurvolee, tickCoques, relSurvolee, selectedRelation, zoomActuel, routesFin, provisoire, estTactile, couchesCarte, situationsJumeaux]);

  // Moteur de labels des titres de domaines : sélection > survol > halo > investigations actives ;
  // collision → le titre le moins prioritaire disparaît (jamais de chevauchement de texte)
  const titresVisibles = useMemo(() => {
    const candidats = nodes
      .filter((n) => n.type === "region")
      .map((n) => {
        const d = n.data;
        const candidat = zoomNiveau === 1 || regionSurvolee?.id === d.id || domaineSel === d.label || couchesCarte.capacites;
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
  }, [nodes, zoomNiveau, regionSurvolee, domaineSel, couchesCarte.capacites]);

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
  const rechercheOuverte = estMobile ? rechercheMobileOuverte : !(panneauOuvert || floreOuverte) || loupeForcee;
  useEffect(() => { if (!panneauOuvert && !floreOuverte) setLoupeForcee(false); }, [panneauOuvert, floreOuverte]);

  // Remplacement mutuel de la colonne droite : une NOUVELLE sélection pendant que Flore est
  // ouverte ferme Flore — le détail reprend la place (le dernier panneau demandé gagne).
  // « Interroger » ne change pas la sélection → ne ferme jamais Flore.
  const selCle = selected?.id || selectedRelation?.id || domaineSel || vueListe || null;
  useEffect(() => {
    if (floreOuverte && selCle) fermerFlore();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selCle]);

  // Routage final : nouveau snapshot géométrique → Web Worker libavoid
  // (jamais pendant le drag, jamais pendant le pan/zoom — la signature géométrique est stable)
  useEffect(() => {
    if (!provisoire && snapshot) pousser(snapshot);
  }, [snapshot, provisoire, pousser]);

  // Couches de relations (BCM déclaré / Réalité découverte / Écarts) + accentuation au survol/épinglage
  const edgesVisibles = useMemo(() => {
    let es = edges.filter((e) => {
      const etat = e.data?.etat;
      if (etat === "confirmee" || etat === "obsolete") return couchesRel.bcm;
      if (etat === "observee" || etat === "validation") return couchesRel.realite;
      if (etat === "supposee" || etat === "contestee") return couchesRel.ecarts;
      return true;
    });
    const actif = survolJumeau;
    if (actif) {
      es = es.map((e) =>
        e.source === actif || e.target === actif || e.source === `voisin-${actif}` || e.target === `voisin-${actif}`
          ? { ...e, zIndex: 20, style: { ...e.style, strokeWidth: (e.style?.strokeWidth || 1.5) + 1, opacity: 1 } }
          : { ...e, label: undefined, data: { ...e.data, estompee: true }, style: { ...e.style, opacity: 0.12 } }
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
    return es;
  }, [edges, couchesRel, survolJumeau, relSurvolee, selectedRelation]);

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
      .filter((j) => !j.anonyme && (j.nom.toLowerCase().includes(q) || idNumerique(j.id).includes(q)))
      .slice(0, 5)
      .map((j) => ({ type: "jumeau", id: j.id, label: j.nom, sub: `${idNumerique(j.id)} · ${j.domaine}` }));
    const ds = (mesh.regions || [])
      .filter((r) => r.label.toLowerCase().includes(q))
      .slice(0, 3)
      .map((r) => ({ type: "domaine", id: r.label, label: r.label, sub: "domaine" }));
    return [...js, ...ds];
  }, [recherche, mesh]);

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

  const centrerSurJumeau = (id) => {
    const j = mesh?.jumeaux.find((x) => x.id === id);
    if (!j) return;
    const pos = posOverrides[id] || j.position;
    setHalo(id); // membrane + robot brièvement mis en évidence
    setTimeout(() => setHalo((h) => (h === id ? null : h)), 2000);
    rfRef.current?.setCenter(pos.x + 30, pos.y + 40, { zoom: 1.4, duration: 600 });
    // La recherche/liste ouvre directement le détail à droite (survol = simple identification)
    setSelected(j);
    setSelectedRelation(null);
    setDomaineSel(null);
    setVueListe(null);
    setOnglet("detail");
    setRecherche("");
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
    {/* Layout façon Google Maps : la carte et le panneau détail sont des colonnes — le chrome ne bouge jamais */}
    <div className="relative flex min-h-0 flex-1">
    <div ref={carteRef} onPointerMove={surSurvolCarte} onPointerLeave={() => { setRegionSurvolee(null); setRegionTooltip(null); }} className="relative min-w-0 flex-1 overflow-hidden" data-testid="system-map" style={{ background: "radial-gradient(ellipse at 50% 38%, #FDFDFB 0%, #F5F4F0 65%, #EDECE6 100%)" }}>
      <ReactFlow
        key={focus || situationParam || "mesh"}
        nodes={nodes}
        edges={edgesVisibles}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView={!restaurerEtat}
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.3}
        maxZoom={2.6}
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
        multiSelectionKeyCode={["Meta", "Control", "Shift"]}
        onSelectionStart={() => { selAvantLasso.current = selection; }}
        onSelectionEnd={() => {
          const ids = (rfRef.current?.getNodes() || []).filter((n) => n.selected && n.type === "twin").map((n) => n.id);
          if (ids.length) setSelection([...new Set([...selAvantLasso.current, ...ids])]);
        }}
        onNodeClick={(_, node) => {
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
        colorMode="light"
      >
        <Background variant={BackgroundVariant.Dots} gap={26} size={1.3} color="rgba(17,17,16,0.13)" />
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
            nodeColor={(n) => (n.type === "region" ? `${n.data?.couleur || "#71716D"}66` : couleurDomaine(n.data?.jumeau?.domaine))}
            maskColor="rgba(247,247,246,0.6)"
            data-testid="minimap"
          />
        )}
        {/* Étiquettes de domaines — révélées au survol de la membrane (niveaux 2-3) ;
            toujours visibles au niveau 1 (vue macro, elles sont le contenu) */}
        <ViewportPortal>
          {nodes.filter((n) => n.type === "region").map((n) => {
            const d = n.data;
            const m = d.maturite;
            const mc = m ? MATURITES[m.niveau] || "#71716D" : null;
            const sx = d.w / (d.wCible || d.w);
            const sy = d.h / (d.hCible || d.h);
            const lx = n.position.x + (d.labelX ?? d.w / 2) * sx;
            const ly = n.position.y + (d.labelY ?? 30) * sy;
            const visible = (zoomNiveau === 1 || regionSurvolee?.id === d.id || domaineSel === d.label || couchesCarte.capacites) && titresVisibles.has(d.id);
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
                      className="whitespace-nowrap rounded bg-white/60 px-1.5 py-0.5 font-code text-[11px] font-semibold uppercase tracking-[0.25em] backdrop-blur-[2px] transition-opacity duration-200"
                      style={{ color: d.couleur, opacity: visible ? 1 : 0 }}
                    >
                      {d.label}
                    </span>
                  </div>
                  {mc && !d.macro && (
                    <span
                      className="rounded-full border bg-white/80 px-1.5 py-0.5 font-code text-[8px] uppercase tracking-wider transition-opacity duration-200"
                      style={{ color: mc, borderColor: `${mc}44`, opacity: visible ? 1 : 0 }}
                    >
                      {m.niveau}
                    </span>
                  )}
                </div>
                {(d.macro || (couchesCarte.capacites && visible)) && m && (
                  <div className="mt-1 flex items-center justify-center gap-2 font-code text-[10px] text-[#52524F]" data-testid={`region-macro-${d.id}`}>
                    <span>{m.jumeaux} jumeau{m.jumeaux > 1 ? "x" : ""}</span>
                    <span className="text-[#71716D]">·</span>
                    <span>{d.flux ?? 0} flux</span>
                    <span className="text-[#71716D]">·</span>
                    <span className={(d.ecarts ?? 0) > 0 ? "text-[#D97706]" : ""}>{d.ecarts ?? 0} écart{(d.ecarts ?? 0) > 1 ? "s" : ""}</span>
                  </div>
                )}
              </div>
            );
          })}
        </ViewportPortal>
      </ReactFlow>

      {/* Marqueurs de flèches partagés par les arêtes orthogonales */}
      <svg width="0" height="0" style={{ position: "absolute" }}>
        <defs>
          <marker id="marqueur-ardoise" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="rgba(17,17,16,0.5)" />
          </marker>
          <marker id="marqueur-teal" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#0E7490" />
          </marker>
          <marker id="marqueur-orange" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#D97706" />
          </marker>
          <marker id="marqueur-violet" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#6D28D9" />
          </marker>
        </defs>
      </svg>

      {/* Recherche — îlot haut-gauche (façon Google Maps). Rétractée en loupe quand un panneau
          (détail ou Flore) est ouvert : un clic sur la loupe la re-déplie à la demande. */}
      <div className="pointer-events-none absolute left-4 top-4 z-20">
        <div className="pointer-events-auto relative">
          {!rechercheOuverte ? (
            <button onClick={() => (estMobile ? setRechercheMobileOuverte(true) : setLoupeForcee(true))} data-testid="btn-recherche" title="Rechercher" className="glass rounded-xl p-2.5 text-[#52524F] transition-colors hover:text-[#111110]">
              <MagnifyingGlass size={14} />
            </button>
          ) : (
            <div className="glass flex items-center gap-2 rounded-xl px-3 py-2">
              <MagnifyingGlass size={13} className="shrink-0 text-[#71716D]" />
              <input
                value={recherche}
                onChange={(e) => setRecherche(e.target.value)}
                onKeyDown={(e) => {
                  // Enter : sélectionne le premier résultat et ramène la carte vers lui
                  if (e.key !== "Enter" || resultatsRecherche.length === 0) return;
                  noterRecherche(recherche);
                  const r = resultatsRecherche[0];
                  if (r.type === "jumeau") centrerSurJumeau(r.id);
                  else { setDomaineSel(r.id); setRecherche(""); }
                  if (estMobile) setRechercheMobileOuverte(false);
                  setLoupeForcee(false);
                }}
                placeholder="Rechercher un jumeau, domaine, flux…"
                data-testid="atlas-recherche"
                className={`${estMobile ? "w-[44vw]" : "w-64"} bg-transparent text-xs text-[#111110] placeholder:text-[#71716D] focus:outline-none`}
              />
              {(estMobile || loupeForcee || panneauOuvert || floreOuverte) && (
                <button onClick={() => { setRechercheMobileOuverte(false); setLoupeForcee(false); setRecherche(""); }} data-testid="btn-recherche-fermer" title="Refermer la recherche" className="text-[#71716D] transition-colors hover:text-[#111110]"><X size={13} /></button>
              )}
            </div>
          )}
          {rechercheOuverte && resultatsRecherche.length > 0 && (
            <div className="glass absolute left-0 top-11 z-30 w-72 rounded-xl p-1.5" data-testid="atlas-recherche-resultats">
              {resultatsRecherche.map((r) => (
                <button
                  key={`${r.type}-${r.id}`}
                  onClick={() => { noterRecherche(recherche); if (r.type === "jumeau") centrerSurJumeau(r.id); else { setDomaineSel(r.id); setRecherche(""); } }}
                  data-testid={`recherche-${r.type}-${r.id}`}
                  className="w-full rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-[#F0F0EE]"
                >
                  <div className="text-xs font-semibold text-[#111110]">{r.label}</div>
                  <div className="font-code text-[9px] text-[#71716D]">{r.sub}</div>
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
          domaineActif={domaineActif} selection={selection}
          revenirSelection={revenirSelection} ajusterVue={ajusterVue}
        />

        {/* Bannière situation (focus profond depuis Aujourd'hui / Investigations) */}
        {situation && (
          <div className="glass pointer-events-auto flex max-w-md items-center gap-3 rounded-xl px-4 py-2.5" data-testid="map-situation-banner">
            <div>
              <div className="font-code text-[9px] uppercase tracking-[0.25em] text-[#6D28D9]">Focus — situation</div>
              <div className="text-xs font-semibold text-[#111110]">{situation.titre}</div>
              <div className="mt-0.5 font-code text-[9px] text-[#71716D]">
                {situation.jumeaux.length} jumeaux · contexte réduit au pertinent
              </div>
            </div>
            <button onClick={() => majUrl({ situation: null })} data-testid="map-clear-situation" title="Retirer le focus situation" className="shrink-0 text-[#71716D] transition-colors hover:text-[#111110]">
              <X size={13} />
            </button>
          </div>
        )}

        {/* Indicateur de périmètre de travail actif (filtre volontaire, distinct de la sécurité) */}
        {perimetreTravail && (
          <div className="glass pointer-events-auto flex items-center gap-2 rounded-xl px-4 py-2" data-testid="perimetre-travail-chip">
            <span className="h-1.5 w-1.5 rounded-full bg-[#0E7490]" />
            <span className="font-code text-[10px] text-[#52524F]">
              Périmètre de travail : <span style={{ color: couleurDomaine(perimetreTravail) }}>{perimetreTravail}</span> — filtre volontaire, pas sécurité
            </span>
            <button onClick={() => setPerimetreTravail(null)} data-testid="perimetre-travail-clear" className="text-[#71716D] transition-colors hover:text-[#111110]">
              <X size={12} />
            </button>
          </div>
        )}
      </div>

      {/* Infobulle d'identification au survol — une ligne, aucune action, aucun bloc de stats
          (le détail vit dans le panneau de droite au clic ; règle d'unicité : masquée si un panneau est ouvert) */}
      {!estTablette && jumeauSurvole && zoomNiveau > 1 && !panneauOuvert && tooltipPos && (
        <div
          className="pointer-events-none absolute z-30 flex items-center gap-1.5 rounded-lg border border-[#E5E5E3] bg-white/95 px-2.5 py-1.5 shadow-md"
          style={{ left: tooltipPos.x + 14, top: tooltipPos.y + 14 }}
          data-testid="infobulle-jumeau"
        >
          <span className="h-2 w-2 rounded-full" style={{ backgroundColor: couleurDomaine(jumeauSurvole.domaine) }} />
          <span className="font-code text-[10px] font-semibold text-[#71716D]">{idNumerique(jumeauSurvole.id)}</span>
          <span className="text-[11px] font-semibold text-[#111110]" data-testid="infobulle-nom">{jumeauSurvole.nom}</span>
          <span className="font-code text-[9px] text-[#0E7490]" data-testid="infobulle-confiance">{jumeauSurvole.confiance?.valeur ?? jumeauSurvole.couverture ?? "—"} %</span>
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

      <AtlasToolbar outil={outil} setOutil={setOutil} rfRef={rfRef} onExpliquer={() => setExpliquerOuvert((o) => !o)} expliquerOuvert={expliquerOuvert} modeEdition={modeEdition} setModeEdition={setModeEdition} vueListe={vueListe} onOuvrirListe={setVueListe} conteneurRef={carteRef} />

      {/* Pile basse centrée — chip Flore, mode réorganisation, bandeaux temporels, niveau de zoom :
          empilés verticalement, chaque indicateur garde sa propre ligne */}
      <div className="pointer-events-none absolute bottom-4 left-1/2 z-10 flex -translate-x-1/2 flex-col items-center gap-2">
        {focusCarte && (
          <div className="glass pointer-events-auto flex items-center gap-2 rounded-lg px-3 py-1.5" data-testid="focus-flore-chip">
            <Sparkle size={12} className="text-[#3730A3]" />
            <span className="font-code text-[10px] text-[#52524F]">Vue commandée par Flore</span>
            <button onClick={() => commanderCarte(null)} data-testid="focus-flore-clear" className="text-[#71716D] transition-colors hover:text-[#111110]">
              <X size={12} />
            </button>
          </div>
        )}

        {modeEdition && (
          <div className="glass pointer-events-auto flex items-center gap-2 rounded-lg px-3 py-1.5" data-testid="mode-edition-chip">
            <span className="h-1.5 w-1.5 rounded-full bg-[#B45309]" />
            <span className="font-code text-[10px] text-[#52524F]">
              Mode réorganisation — glissez un robot ; la reclassification est toujours proposée, jamais automatique
            </span>
            <button onClick={() => setModeEdition(false)} data-testid="mode-edition-quitter" className="text-[#71716D] transition-colors hover:text-[#111110]">
              <X size={12} />
            </button>
          </div>
        )}

        {(modeTemps === "historique" || modeTemps === "replay") && dateRef && (
          <div className="glass pointer-events-auto flex items-center gap-3 rounded-xl px-4 py-2" data-testid="bandeau-temps">
            <span className="font-code text-[10px] text-[#52524F]">
              {modeTemps === "replay" ? "Relecture du Mesh" : "Photographie du Mesh"} au <strong className="text-[#111110]">{fmtDate(dateRef)}</strong>
            </span>
            <button onClick={() => { setModeTemps("direct"); setReplaying(false); setDateRef(null); majUrl({ date: null }); }} data-testid="retour-direct-btn" className="rounded-md border border-[#3730A3]/40 px-2 py-0.5 font-code text-[10px] font-semibold text-[#3730A3] transition-colors hover:bg-[#3730A3]/10">
              Revenir au direct
            </button>
          </div>
        )}
        {modeTemps === "avantapres" && dateRef && (
          <div className="glass pointer-events-auto flex items-center gap-3 rounded-xl px-4 py-2" data-testid="bandeau-avant-apres">
            <span className="h-2 w-2 rounded-sm border-2 border-dashed border-[#0E7490]" />
            <span className="font-code text-[10px] text-[#52524F]">
              Avant/Après depuis le <strong className="text-[#111110]">{fmtDate(dateRef)}</strong> — {nbNouvelles} nouvelle{nbNouvelles > 1 ? "s" : ""} relation{nbNouvelles > 1 ? "s" : ""}
            </span>
            <button onClick={() => { setModeTemps("direct"); setDateRef(null); }} data-testid="retour-direct-btn-aa" className="rounded-md border border-[#3730A3]/40 px-2 py-0.5 font-code text-[10px] font-semibold text-[#3730A3] transition-colors hover:bg-[#3730A3]/10">
              Revenir au direct
            </button>
          </div>
        )}

        {/* Niveau de zoom sémantique — échelle globale, identique partout dans le Mesh */}
        <div className="glass rounded-lg px-3 py-1.5 font-code text-[10px] text-[#52524F]" data-testid="zoom-niveau">
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
          <span className="flex h-12 w-12 items-center justify-center rounded-full border-2 border-dashed border-[#71716D]/50 bg-white/50">
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
            className="pointer-events-none absolute z-30 w-56 rounded-xl border border-[#E5E5E3] bg-white p-3 shadow-lg"
            style={{ left: Math.min(relTooltipPos.x + 14, (carteRef.current?.clientWidth || 1200) - 240), top: Math.max(relTooltipPos.y + 14, 8) }}
            data-testid="agregat-tooltip"
          >
            <div className="font-code text-[11px] font-semibold text-[#111110]">
              {idNumerique(agg.source)} ↔ {idNumerique(agg.target)}
            </div>
            <div className="mt-1.5 font-code text-[10px] text-[#52524F]">
              {agg.data.agregat.length} flux partagent ce corridor
            </div>
            <div className="mt-2 font-code text-[9px] text-[#0E7490]">Routes déployées au survol</div>
          </div>
        );
      })()}
      {relSurvolee && !relSurvolee.startsWith("agg-") && !selectedRelation && relTooltipPos && mesh && (() => {
        const r = mesh.relations.find((x) => x.id === relSurvolee);
        if (!r) return null;
        const e = edgesVisibles.find((x) => x.id === relSurvolee);
        const etat = ETATS_RELATION[r.etat] || { label: r.etat, couleur: "#71716D" };
        return (
          <div
            className="pointer-events-none absolute z-30 w-56 rounded-xl border border-[#E5E5E3] bg-white p-3 shadow-lg"
            style={{ left: Math.min(relTooltipPos.x + 14, (carteRef.current?.clientWidth || 1200) - 240), top: Math.max(relTooltipPos.y + 14, 8) }}
            data-testid="relation-tooltip"
          >
            <div className="font-code text-[11px] font-semibold text-[#111110]">
              {idNumerique(r.source)} → {idNumerique(r.cible)}
            </div>
            <div className="mt-1.5 space-y-0.5 font-code text-[10px] text-[#52524F]">
              <div style={{ color: etat.couleur }}>Relation {etat.label.toLowerCase()}</div>
              {e?.data?.label && <div>{e.data.label}</div>}
              {r.confiance != null && <div>Confiance : {r.confiance} %</div>}
              {(r.claims?.length ?? 0) > 0 && <div>{r.claims.length} preuve{r.claims.length > 1 ? "s" : ""}</div>}
            </div>
            <div className="mt-2 font-code text-[9px] text-[#0E7490]">Clic : qualifier la relation →</div>
          </div>
        );
      })()}

      {/* Infobulle de membrane — proche de la frontière survolée */}
      {regionTooltip && regionSurvolee && (
        <div
          className="pointer-events-none absolute z-30 w-52 rounded-xl border border-[#E5E5E3] bg-white p-3 shadow-lg"
          style={{ left: Math.min(regionTooltip.x + 16, (carteRef.current?.clientWidth || 1200) - 230), top: Math.max(regionTooltip.y + 16, 8) }}
          data-testid={`region-tooltip-${regionSurvolee.id}`}
        >
          <div className="font-display text-xs font-bold" style={{ color: regionTooltip.data.couleur }}>Domaine {regionTooltip.data.label}</div>
          <div className="mt-1.5 space-y-0.5 font-code text-[10px] text-[#52524F]">
            <div>{regionTooltip.data.maturite?.jumeaux ?? "—"} jumeaux</div>
            <div>{regionTooltip.data.flux ?? 0} flux observés</div>
            <div>{regionTooltip.data.ecarts ?? 0} écart{(regionTooltip.data.ecarts ?? 0) > 1 ? "s" : ""} structurel{(regionTooltip.data.ecarts ?? 0) > 1 ? "s" : ""}</div>
          </div>
          <div className="mt-2 font-code text-[9px] text-[#0E7490]">Double-clic : explorer le domaine →</div>
        </div>
      )}



      {/* Mobile : la mini-carte devient un bouton « Vue d'ensemble » (fitView explicite) */}
      {estMobile && (
        <button
          onClick={() => rfRef.current?.fitView({ duration: 600, padding: 0.15 })}
          data-testid="btn-vue-ensemble"
          className="glass absolute bottom-24 right-3 z-10 rounded-full px-3 py-2.5 font-code text-[10px] uppercase tracking-[0.12em] text-[#52524F] transition-colors hover:text-[#111110]"
        >
          Vue d'ensemble
        </button>
      )}

    </div>

      <AtlasPanneau
        onglet={onglet} setOnglet={setOnglet}
        comparaison={comparaison} selectedRelation={selectedRelation}
        selected={selected} domaineSel={domaineSel}
        statsDomaine={statsDomaine} actionsDomaine={actionsDomaine}
        confirmerRelation={confirmerRelation}
        eventsVisibles={eventsVisibles} jumeauPar={jumeauPar}
        presentation={estTablette ? "feuillet" : "colonne"}
        masquee={floreOuverte}
        mesh={mesh} situations={situations} vueListe={vueListe} setVueListe={setVueListe}
        favorisIds={favorisIds} onBasculerFavori={onBasculerFavori}
        statsTwin={statsSelection}
        onInterroger={() => { if (selected) { setSelection([selected.id]); ouvrirFlore(); } }}
        onChoisirJumeau={centrerSurJumeau}
        onChoisirSituation={(id) => majUrl({ situation: id })}
        onRelancerRecherche={(t) => { setRecherche(t); setLoupeForcee(true); if (estMobile) setRechercheMobileOuverte(true); }}
        onFermer={() => { setSelected(null); setSelectedRelation(null); setDomaineSel(null); setComparaison(null); setVueListe(null); majUrl({ sel: null, domaine: null }); }}
      />
    </div>
    </div>
  );
}
