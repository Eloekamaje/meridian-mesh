import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Background, BaseEdge, Handle, MarkerType, Position, ReactFlow, ReactFlowProvider, ViewportPortal, useReactFlow, useStore } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { ArrowCounterClockwise, CaretLeft, Flask, MagnifyingGlass, Sparkle } from "@phosphor-icons/react";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import { couleurDomaine, ETATS_RELATION } from "@/lib/domaines";
import { coqueOrganique, idNumerique } from "@/lib/atlasGraph";
import RobotJumeauSvg, { STYLES_ROBOT } from "@/components/map/RobotJumeauSvg";
import { DOMAINES_ETENDUS, PALETTE_COMMUNAUTES, decrireCommunautes, degres, dispositionForce, genererMesh, louvain } from "@/lib/laboGraphe";

// ============================================================================================
// LABORATOIRE DU GRAPHE — page d'essai, isolée de l'Atlas.
// Reprend des idées de graphify (étiquettes selon l'importance, taille selon le degré, légende-filtre,
// communautés calculées, zones transversales, disposition par forces) sur les VRAIES données du Mesh,
// avec la même pile que l'Atlas (React Flow). Chaque idée s'active séparément pour juger son rendu.
// Rien ici ne modifie l'Atlas ni les données.
// ============================================================================================

const TAILLE_UNIFORME = 34;
const SEUIL_ZOOM_DETAIL = 0.6; // sous ce zoom, l'option « niveau de détail » dessine des disques
const ECHELLES = [["reel", "Réel (38)"], ["100", "100"], ["500", "500"], ["1000", "1 000"]];
const OPTIM_DEFAUT = { virtualisation: false, detail: false };
const couleurGroupeDomaine = (d) => DOMAINES_ETENDUS[d] || couleurDomaine(d);
const HAUTEUR_ROBOT = 1.9; // hauteur du robot = 1,9 × le diamètre du disque de référence
const RAYON_ROBOT = 0.7; // rayon d'accroche des liens = 0,7 × le diamètre
const REGLAGES_ACTUELS = { forme: "robot", disposition: "atlas", couleur: "domaine", taille: "uniforme", etiquettes: "numeros", seuil: 0.35, coques: false, zones: false, ecarts: false };
const REGLAGES_PROPOSES = { forme: "robot", disposition: "atlas", couleur: "domaine", taille: "degre", etiquettes: "noms", seuil: 0.35, coques: false, zones: true, ecarts: true };

// Style des liens selon leur état — mêmes états que l'Atlas
const STYLE_ETAT = {
  confirmee: { largeur: 2, pointille: false, opacite: 0.7 },
  observee: { largeur: 2, pointille: false, opacite: 0.75 },
  supposee: { largeur: 1.3, pointille: true, opacite: 0.55 },
  validation: { largeur: 1.5, pointille: true, opacite: 0.6 },
  contestee: { largeur: 1.6, pointille: true, opacite: 0.7 },
  obsolete: { largeur: 1, pointille: true, opacite: 0.3 },
};
const COULEURS_ZONES = ["#A78BFA", "#F59E0B", "#38BDF8", "#F472B6", "#34D399", "#FB923C"];

const HANDLE_CENTRE = { position: "absolute", left: "50%", top: "50%", transform: "translate(-50%,-50%)", width: 1, height: 1, minWidth: 0, minHeight: 0, border: 0, background: "transparent", opacity: 0, pointerEvents: "none" };

// --- Nœud : disque de la couleur du groupe, étiquette dessous ---------------------------------
const NoeudLabo = memo(function NoeudLabo({ data }) {
  const { taille, couleur, etiquette, ecart, actif, dim, opaciteDim, forme, delai, detail, leger } = data;
  // Niveau de détail : très dézoomé, un robot de 20 px n'est plus lisible — on dessine un disque (bien moins cher)
  const dezoome = useStore((st) => st.transform[2] < SEUIL_ZOOM_DETAIL);
  const robot = forme === "robot" && !(detail && dezoome);
  const hauteur = Math.round(taille * HAUTEUR_ROBOT);
  return (
    <div style={{ width: taille, height: taille }} className="relative cursor-pointer" data-testid={`labo-noeud-${data.id}`}>
      {robot ? (
        <div
          className="absolute left-1/2 top-1/2 transition-[opacity,filter] duration-200"
          style={{
            transform: "translate(-50%,-50%)",
            opacity: dim ? opaciteDim : 1,
            filter: actif ? `drop-shadow(0 0 8px ${couleur}) drop-shadow(0 0 16px ${couleur}88)` : undefined,
          }}
          data-testid={`labo-robot-${data.id}`}
        >
          <RobotJumeauSvg hauteur={hauteur} couleur={couleur} ecart={ecart} content={actif} delai={delai} leger={leger} />
        </div>
      ) : (
        <div
          className="absolute inset-0 rounded-full transition-[box-shadow,opacity] duration-200"
          style={{
            background: couleur,
            border: `2px ${ecart ? "dashed" : "solid"} ${ecart ? "#F59E0B" : "rgba(255,255,255,0.28)"}`,
            opacity: dim ? opaciteDim : 1,
            boxShadow: actif ? `0 0 0 3px ${couleur}66, 0 0 20px ${couleur}99` : ecart ? "0 0 0 3px rgba(245,158,11,0.18)" : "none",
          }}
        />
      )}
      {etiquette && (
        <span
          className="pointer-events-none absolute left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-[#071019]/75 px-1.5 font-code text-[10px] text-[#DCE6EE]"
          style={{ top: robot ? taille / 2 + hauteur / 2 - 2 : taille + 4, opacity: dim ? opaciteDim : 1 }}
        >
          {etiquette}
        </span>
      )}
      <Handle type="target" position={Position.Top} style={HANDLE_CENTRE} isConnectable={false} />
      <Handle type="source" position={Position.Top} style={HANDLE_CENTRE} isConnectable={false} />
    </div>
  );
});

// --- Lien : courbe douce, du bord d'un disque au bord de l'autre, flèche vers la cible ------
function AreteLabo({ id, sourceX, sourceY, targetX, targetY, data, markerEnd }) {
  const dx = targetX - sourceX;
  const dy = targetY - sourceY;
  const L = Math.hypot(dx, dy) || 1;
  const ux = dx / L;
  const uy = dy / L;
  const sx = sourceX + ux * data.r1;
  const sy = sourceY + uy * data.r1;
  const ex = targetX - ux * (data.r2 + 3);
  const ey = targetY - uy * (data.r2 + 3);
  const cx = (sx + ex) / 2 - uy * L * 0.09;
  const cy = (sy + ey) / 2 + ux * L * 0.09;
  return (
    <BaseEdge
      id={id}
      path={`M ${sx} ${sy} Q ${cx} ${cy} ${ex} ${ey}`}
      markerEnd={markerEnd}
      style={{ stroke: data.couleur, strokeWidth: data.largeur, strokeDasharray: data.pointille ? "6 4" : undefined, opacity: data.opacite, transition: "opacity 160ms ease, stroke-width 160ms ease" }}
    />
  );
}

const nodeTypes = { labo: NoeudLabo };
const edgeTypes = { labo: AreteLabo };

// --- Petits éléments d'interface --------------------------------------------------------------
function Segment({ options, valeur, onChange, testid }) {
  return (
    <div className="inline-flex rounded-lg border border-white/10 bg-white/[0.03] p-0.5" role="group">
      {options.map(([v, label]) => (
        <button
          key={v}
          type="button"
          onClick={() => onChange(v)}
          aria-pressed={valeur === v}
          data-testid={`${testid}-${v}`}
          className={`min-h-[30px] rounded-md px-2.5 text-[11px] font-medium transition-colors ${
            valeur === v ? "bg-[#9B87F5]/25 text-white" : "text-[#7C93A8] hover:text-white"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function Bascule({ actif, onChange, label, testid, aide }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={actif}
      onClick={() => onChange(!actif)}
      data-testid={testid}
      title={aide}
      className="flex min-h-[30px] w-full items-center justify-between gap-3 rounded-lg px-1 text-left text-[11px] text-[#CBD5E1] hover:text-white"
    >
      <span>{label}</span>
      <span className={`relative h-4 w-7 shrink-0 rounded-full transition-colors ${actif ? "bg-[#9B87F5]" : "bg-white/15"}`}>
        <span className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all ${actif ? "left-3.5" : "left-0.5"}`} />
      </span>
    </button>
  );
}

const Rubrique = ({ numero, titre, idee, children }) => (
  <div className="space-y-1.5 border-t border-white/[0.07] pt-2.5 first:border-0 first:pt-0">
    <div className="flex items-baseline gap-1.5">
      <span className="font-code text-[9px] text-[#9B87F5]">{numero}</span>
      <span className="text-[11px] font-semibold text-white">{titre}</span>
      {idee && <span className="ml-auto font-code text-[8px] uppercase tracking-wider text-[#64748B]">{idee}</span>}
    </div>
    {children}
  </div>
);

// ============================================================================================
function Labo() {
  const { mesh: meshReel } = useMesh();
  const rf = useReactFlow();
  const [reglages, setReglages] = useState(REGLAGES_ACTUELS);
  const { disposition, couleur, taille, etiquettes, seuil, coques, zones, ecarts } = reglages;
  const regler = (cle) => (valeur) => setReglages((r) => ({ ...r, [cle]: valeur }));
  // Un préréglage repart d'un état net : réglages, groupes masqués et sélection
  const appliquer = (preset) => {
    setReglages(preset);
    setMasques(new Set());
    setSelection(null);
  };
  const [masques, setMasques] = useState(() => new Set());
  const [selection, setSelection] = useState(null);
  const [survol, setSurvol] = useState(null);
  const [areteSurvolee, setAreteSurvolee] = useState(null); // { id, x, y }
  const carteRef = useRef(null);
  const [recherche, setRecherche] = useState("");
  const [situationsApi, setSituationsApi] = useState([]);
  // Échelle : le vrai Mesh, ou un Mesh synthétique de même structure (100, 500, 1 000 jumeaux)
  const [echelle, setEchelle] = useState("reel");
  const [optim, setOptim] = useState(OPTIM_DEFAUT);
  const [mesures, setMesures] = useState({});
  const [fluidite, setFluidite] = useState(null);
  const chronos = useRef({});
  const t0Echelle = useRef(0);
  const chrono = (cle, f) => {
    const a = performance.now();
    const r = f();
    chronos.current[cle] = Math.round(performance.now() - a);
    return r;
  };
  const synth = useMemo(() => (echelle === "reel" ? null : chrono("generation", () => genererMesh(Number(echelle)))), [echelle]); // eslint-disable-line react-hooks/exhaustive-deps
  const mesh = synth ? synth.mesh : meshReel;
  const situations = synth ? synth.situations : situationsApi;
  // Les réglages ne s'affichent pas par défaut : la carte occupe tout l'espace, un bouton les ouvre
  const [panneau, setPanneau] = useState(false);
  // Situations dont la zone est tracée : les 11 ensemble s'entassent — on en choisit quelques-unes
  const [zonesChoisies, setZonesChoisies] = useState(() => new Set());
  const basculerZone = (id) => setZonesChoisies((z) => { const n = new Set(z); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  useEffect(() => {
    api.get("/situations").then((r) => setSituationsApi(Array.isArray(r.data) ? r.data : [])).catch(() => {});
  }, []);
  useEffect(() => {
    setZonesChoisies(new Set(situations.slice(0, 2).map((x) => x.id)));
  }, [situations]);

  // ---- Données ---------------------------------------------------------------------------
  const jumeaux = useMemo(() => mesh?.jumeaux || [], [mesh]);
  const relations = useMemo(() => {
    const ids = new Set(jumeaux.map((j) => j.id));
    return (mesh?.relations || []).filter((r) => ids.has(r.source) && ids.has(r.cible) && r.source !== r.cible);
  }, [mesh, jumeaux]);
  const ids = useMemo(() => jumeaux.map((j) => j.id), [jumeaux]);
  const deg = useMemo(() => degres(ids, relations.map((r) => ({ source: r.source, cible: r.cible }))), [ids, relations]);
  const maxDeg = useMemo(() => Math.max(1, ...deg.values()), [deg]);
  const louv = useMemo(() => chrono("louvain", () => louvain(ids, relations.map((r) => ({ source: r.source, cible: r.cible })))), [ids, relations]); // eslint-disable-line react-hooks/exhaustive-deps
  const { communautes, ecartsSet } = useMemo(() => {
    const d = decrireCommunautes(jumeaux, louv.comm);
    return { communautes: d.communautes, ecartsSet: d.ecarts };
  }, [jumeaux, louv]);

  // ---- Disposition : coordonnées stables de l'Atlas, ou proposition par forces -------------
  const posAtlas = useMemo(() => new Map(jumeaux.map((j) => [j.id, { x: j.position?.x ?? 0, y: j.position?.y ?? 0 }])), [jumeaux]);
  // Calculée seulement à la demande : à 1 000 jumeaux elle coûte de l'ordre de la seconde
  const posForce = useMemo(() => (disposition === "force" && jumeaux.length ? chrono("force", () => dispositionForce(posAtlas, relations.map((r) => ({ source: r.source, cible: r.cible })))) : new Map()), [posAtlas, relations, jumeaux.length, disposition]); // eslint-disable-line react-hooks/exhaustive-deps
  const cible = disposition === "force" ? posForce : posAtlas;

  // Transition animée d'une disposition à l'autre (les liens suivent : tout est recalculé à chaque image)
  const [pos, setPos] = useState(() => new Map());
  const posRef = useRef(pos);
  posRef.current = pos;
  useEffect(() => {
    const de = posRef.current;
    const t0 = performance.now();
    let raf;
    const pas = (t) => {
      const k = Math.min(1, (t - t0) / 700);
      const e = 1 - (1 - k) ** 3;
      setPos(
        new Map(
          [...cible.entries()].map(([id, b]) => {
            const a = de.get(id) || b;
            return [id, { x: a.x + (b.x - a.x) * e, y: a.y + (b.y - a.y) * e }];
          })
        )
      );
      if (k < 1) raf = requestAnimationFrame(pas);
    };
    raf = requestAnimationFrame(pas);
    return () => cancelAnimationFrame(raf);
  }, [cible]);

  useEffect(() => {
    if (!jumeaux.length) return undefined;
    const t = setTimeout(() => rf.fitView({ padding: 0.2, duration: 600 }), 760);
    return () => clearTimeout(t);
  }, [disposition, jumeaux.length]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- Groupes (légende) : domaine déclaré ou communauté calculée --------------------------
  const cleDe = useCallback((j) => (couleur === "domaine" ? j.domaine : `C${louv.comm.get(j.id)}`), [couleur, louv]);
  const legende = useMemo(() => {
    if (couleur === "domaine") {
      const n = new Map();
      jumeaux.forEach((j) => n.set(j.domaine, (n.get(j.domaine) || 0) + 1));
      return [...n.entries()].sort((a, b) => b[1] - a[1]).map(([d, nb]) => ({ cle: d, label: d, n: nb, couleur: couleurGroupeDomaine(d) }));
    }
    return communautes.map((c) => ({
      cle: `C${c.cid}`,
      label: c.nom,
      n: c.membres.length,
      couleur: PALETTE_COMMUNAUTES[c.cid % PALETTE_COMMUNAUTES.length],
      purete: c.part,
    }));
  }, [couleur, jumeaux, communautes]);
  const couleurGroupe = useMemo(() => new Map(legende.map((e) => [e.cle, e.couleur])), [legende]);
  useEffect(() => setMasques(new Set()), [couleur]);

  const basculerGroupe = (cle) => setMasques((m) => { const s = new Set(m); if (s.has(cle)) s.delete(cle); else s.add(cle); return s; });
  const toutBasculer = (afficher) => setMasques(afficher ? new Set() : new Set(legende.map((e) => e.cle)));
  const refTout = useCallback((el) => { if (el) el.indeterminate = masques.size > 0 && masques.size < legende.length; }, [masques, legende.length]);

  // ---- Graphe React Flow -------------------------------------------------------------------
  // Focus contextuel (comme l'Atlas) : les voisins du jumeau sélectionné — à défaut survolé — restent
  // éclairés, le reste s'estompe. La sélection épinglée prime sur le survol.
  const focusId = selection || survol;
  const voisins = useMemo(() => {
    if (!focusId) return null;
    const s = new Set([focusId]);
    relations.forEach((r) => { if (r.source === focusId) s.add(r.cible); if (r.cible === focusId) s.add(r.source); });
    return s;
  }, [focusId, relations]);

  const tailleDe = useCallback((id) => (taille === "degre" ? Math.round(22 + 34 * ((deg.get(id) || 0) / maxDeg)) : TAILLE_UNIFORME), [taille, deg, maxDeg]);
  const rayonDe = useCallback((id) => (reglages.forme === "robot" ? Math.round(tailleDe(id) * RAYON_ROBOT) : tailleDe(id) / 2), [reglages.forme, tailleDe]);
  const cache = useCallback((j) => masques.has(cleDe(j)), [masques, cleDe]);
  const parId = useMemo(() => new Map(jumeaux.map((j) => [j.id, j])), [jumeaux]);

  const nodes = useMemo(
    () =>
      jumeaux.map((j) => {
        const p = pos.get(j.id) || posAtlas.get(j.id) || { x: 0, y: 0 };
        const t = tailleDe(j.id);
        const important = (deg.get(j.id) || 0) >= seuil * maxDeg;
        // Le numéro n'est jamais remplacé par le nom : l'identité complète est dans l'aperçu du survol
        const montrerNom = etiquettes === "noms" && (important || j.id === selection || j.id === survol);
        return {
          id: j.id,
          type: "labo",
          position: { x: p.x - t / 2, y: p.y - t / 2 },
          hidden: cache(j),
          draggable: false,
          selectable: false,
          data: {
            id: j.id,
            taille: t,
            couleur: couleurGroupe.get(cleDe(j)) || "#94A3B8",
            nom: j.nom,
            etiquette: montrerNom ? j.nom : etiquettes === "numeros" ? idNumerique(j.id) : "",
            ecart: ecarts && ecartsSet.has(j.id),
            actif: j.id === selection,
            dim: !!voisins && !voisins.has(j.id),
            opaciteDim: selection ? 0.22 : 0.45,
            forme: reglages.forme,
            detail: optim.detail,
            leger: optim.detail && jumeaux.length > 150,
            delai: (idNumerique(j.id) % 7) * 0.9, // décale clignement et flottement d'un jumeau à l'autre
          },
        };
      }),
    [jumeaux, pos, posAtlas, tailleDe, deg, seuil, maxDeg, etiquettes, selection, survol, cache, couleurGroupe, cleDe, ecarts, ecartsSet, voisins, reglages.forme, optim.detail]
  );

  const edges = useMemo(
    () =>
      relations.map((r) => {
        const st = STYLE_ETAT[r.etat] || STYLE_ETAT.observee;
        const c = ETATS_RELATION[r.etat]?.couleur || "#94A3B8";
        const incident = !!focusId && (r.source === focusId || r.cible === focusId);
        const surLien = areteSurvolee?.id === r.id;
        // Priorité : lien survolé, puis liens du jumeau en focus, sinon état par défaut
        const opacite = areteSurvolee ? (surLien ? 1 : 0.15) : focusId ? (incident ? 1 : selection ? 0.06 : 0.12) : st.opacite;
        const largeur = surLien || incident ? st.largeur + 1 : st.largeur;
        return {
          id: r.id,
          source: r.source,
          target: r.cible,
          type: "labo",
          zIndex: surLien || incident ? 20 : 0,
          hidden: (parId.get(r.source) && cache(parId.get(r.source))) || (parId.get(r.cible) && cache(parId.get(r.cible))),
          data: { couleur: c, largeur, pointille: st.pointille, opacite, r1: rayonDe(r.source), r2: rayonDe(r.cible) },
          markerEnd: { type: MarkerType.ArrowClosed, width: 11, height: 11, color: c },
        };
      }),
    [relations, focusId, selection, areteSurvolee, parId, cache, rayonDe]
  );

  // ---- Coques : regroupement courant et situations transversales ----------------------------
  const coquesGroupes = useMemo(() => {
    if (!coques) return [];
    return legende
      .filter((e) => !masques.has(e.cle))
      .map((e) => {
        const centres = jumeaux.filter((j) => cleDe(j) === e.cle).map((j) => pos.get(j.id)).filter(Boolean);
        const c = centres.length ? coqueOrganique(centres, 44) : null;
        return c && { ...c, cle: e.cle, couleur: e.couleur, titre: e.label };
      })
      .filter(Boolean);
  }, [coques, legende, masques, jumeaux, cleDe, pos]);

  const zonesSituations = useMemo(() => {
    if (!zones) return [];
    return situations
      .map((s, i) => {
        if (!zonesChoisies.has(s.id)) return null;
        const centres = (s.jumeaux || []).filter((id) => parId.get(id) && !cache(parId.get(id))).map((id) => pos.get(id)).filter(Boolean);
        if (centres.length < 2) return null;
        const c = coqueOrganique(centres, 34);
        return c && { ...c, cle: s.id, couleur: COULEURS_ZONES[i % COULEURS_ZONES.length], titre: s.titre };
      })
      .filter(Boolean);
  }, [zones, situations, zonesChoisies, parId, cache, pos]);

  // ---- Recherche et sélection --------------------------------------------------------------
  const resultats = useMemo(() => {
    const q = recherche.trim().toLowerCase();
    if (!q) return [];
    return jumeaux.filter((j) => j.nom.toLowerCase().includes(q) || j.id.toLowerCase().includes(q) || idNumerique(j.id).includes(q)).slice(0, 8);
  }, [recherche, jumeaux]);
  const centrerSur = (id) => {
    setSelection(id);
    const p = pos.get(id);
    if (p) rf.setCenter(p.x, p.y, { zoom: 1.2, duration: 500 });
  };

  const apercu = useMemo(() => {
    const j = survol ? parId.get(survol) : null;
    const el = carteRef.current;
    const p = survol ? pos.get(survol) : null;
    if (!j || !el || !p) return null;
    const boite = el.getBoundingClientRect();
    const c = rf.flowToScreenPosition({ x: p.x, y: p.y });
    const r = rayonDe(j.id) * rf.getZoom();
    const L = 236;
    let left = c.x - boite.left + r + 14;
    if (left + L > boite.width - 8) left = c.x - boite.left - r - 14 - L; // bascule à gauche près du bord
    const top = Math.max(8, Math.min(c.y - boite.top - 44, boite.height - 190));
    return { j, left, top };
  }, [survol, parId, pos, rf, rayonDe]);

  // ---- Échelle : changement de jeu de données, mesures, test de fluidité --------------------
  const changerEchelle = (v) => {
    t0Echelle.current = performance.now();
    setEchelle(v);
    setMasques(new Set());
    setSelection(null);
    setFluidite(null);
  };
  const [dom, setDom] = useState({ noeuds: 0, liens: 0 });
  useEffect(() => {
    const t0 = t0Echelle.current;
    if (!t0) return undefined;
    let r2;
    const r1 = requestAnimationFrame(() => {
      r2 = requestAnimationFrame(() => {
        setMesures({ generation: chronos.current.generation, louvain: chronos.current.louvain, force: chronos.current.force, affichage: Math.round(performance.now() - t0) });
        t0Echelle.current = 0;
      });
    });
    return () => { cancelAnimationFrame(r1); cancelAnimationFrame(r2); };
  }, [jumeaux]);
  useEffect(() => {
    if (disposition === "force") setMesures((m) => ({ ...m, force: chronos.current.force }));
  }, [posForce, disposition]);
  // React Flow n'affiche les liens qu'une fois les nœuds mesurés : on relève à plusieurs reprises
  useEffect(() => {
    const releve = () => setDom({ noeuds: document.querySelectorAll(".react-flow__node").length, liens: document.querySelectorAll(".react-flow__edge").length });
    const ts = [700, 2200, 5000].map((ms) => setTimeout(releve, ms));
    return () => ts.forEach(clearTimeout);
  }, [jumeaux, relations, optim.virtualisation, masques]);
  const mesurerFluidite = useCallback(() => new Promise((resolve) => {
    // Panoramique + zoom continus pendant 2,5 s : on relève le temps de chaque image
    const dt = [];
    const vp0 = rf.getViewport();
    const debut = performance.now();
    let dernier = debut;
    const pas = (t) => {
      dt.push(t - dernier);
      dernier = t;
      const k = (t - debut) / 2500;
      if (k >= 1) {
        rf.setViewport(vp0);
        const tri = [...dt].sort((a, b) => a - b);
        const moyenne = dt.reduce((a, b) => a + b, 0) / dt.length;
        resolve({ ips: Math.round(1000 / moyenne), p95: Math.round(tri[Math.floor(tri.length * 0.95)]), pire: Math.round(tri[tri.length - 1]), images: dt.length });
        return;
      }
      rf.setViewport({ x: vp0.x + Math.sin(k * 12.57) * 220, y: vp0.y + Math.cos(k * 6.28) * 90, zoom: vp0.zoom * (1 + 0.35 * Math.sin(k * 12.57)) });
      requestAnimationFrame(pas);
    };
    requestAnimationFrame(pas);
  }), [rf]);
  useEffect(() => {
    window.__laboMesurerFluidite = async () => { const r = await mesurerFluidite(); setFluidite(r); return r; };
    return () => { delete window.__laboMesurerFluidite; };
  }, [mesurerFluidite]);

  const sel = selection ? parId.get(selection) : null;
  const communauteSel = sel ? communautes.find((c) => c.cid === louv.comm.get(sel.id)) : null;
  const voisinsSel = sel ? relations.filter((r) => r.source === sel.id || r.cible === sel.id).map((r) => ({ r, autre: parId.get(r.source === sel.id ? r.cible : r.source), sortant: r.source === sel.id })) : [];

  if (!mesh) return <div className="p-8 font-code text-[11px] text-[#7C93A8]" data-testid="labo-chargement">Chargement du Mesh…</div>;

  const zoneSvg = (z, opacite) => (
    <g key={z.cle} transform={`translate(${z.x},${z.y})`}>
      <path d={z.path} fill={z.couleur} fillOpacity={opacite} stroke={z.couleur} strokeOpacity={0.55} strokeWidth={1.6} strokeDasharray="7 5" />
      <text x={z.labelX} y={z.labelY} textAnchor="middle" fill={z.couleur} fontSize="11" fontFamily="monospace" opacity="0.95" style={{ paintOrder: "stroke", stroke: "#071019", strokeWidth: 3 }}>
        {String(z.titre).length > 46 ? `${String(z.titre).slice(0, 44)}…` : z.titre}
      </text>
    </g>
  );

  return (
    <div className="flex h-full" data-testid="labo-atlas">
      <style>{STYLES_ROBOT}</style>
      {panneau && (
      <div className="w-[330px] shrink-0 space-y-2.5 overflow-y-auto border-r border-white/[0.08] bg-[#091420] p-3.5" data-testid="labo-reglages">
          <div className="flex items-center gap-2">
            <Flask size={16} className="text-[#9B87F5]" />
            <div className="min-w-0 flex-1 leading-tight">
              <div className="text-xs font-bold text-white">Laboratoire du graphe</div>
              <div className="text-[10px] text-[#7C93A8]">Inspiré de graphify · données réelles du Mesh</div>
            </div>
            <button type="button" onClick={() => setPanneau(false)} title="Replier les réglages" aria-label="Replier les réglages" data-testid="labo-replier" className="flex h-7 w-7 items-center justify-center rounded-md text-[#7C93A8] hover:bg-white/[0.06] hover:text-white">
              <CaretLeft size={14} />
            </button>
          </div>
          <div className="flex gap-1.5">
            <button onClick={() => appliquer(REGLAGES_ACTUELS)} data-testid="labo-preset-actuel" className="flex min-h-[30px] flex-1 items-center justify-center gap-1.5 rounded-lg border border-white/10 text-[11px] text-[#CBD5E1] hover:text-white">
              <ArrowCounterClockwise size={12} /> Atlas actuel
            </button>
            <button onClick={() => appliquer(REGLAGES_PROPOSES)} data-testid="labo-preset-propose" className="flex min-h-[30px] flex-1 items-center justify-center gap-1.5 rounded-lg border border-[#9B87F5]/40 bg-[#9B87F5]/15 text-[11px] font-semibold text-[#C4B5FD] hover:text-white">
              <Sparkle size={12} weight="fill" /> Proposition
            </button>
          </div>

          <Rubrique numero="①" titre="Étiquettes" idee="importance">
            <Segment testid="labo-etiquettes" valeur={etiquettes} onChange={regler("etiquettes")} options={[["numeros", "Numéros (actuel)"], ["noms", "Noms des plus connectés"]]} />
            {etiquettes === "noms" && (
              <label className="flex items-center gap-2 text-[10px] text-[#7C93A8]">
                Seuil : degré ≥ {Math.round(seuil * 100)} % du max
                <input type="range" min="0" max="1" step="0.05" value={seuil} onChange={(e) => regler("seuil")(Number(e.target.value))} data-testid="labo-seuil" className="flex-1 accent-[#9B87F5]" />
              </label>
            )}
          </Rubrique>
          <Rubrique numero="②" titre="Légende-filtre" idee="cases à cocher">
            <p className="text-[10px] leading-snug text-[#7C93A8]">Voir la colonne de droite : cochez / décochez un groupe pour l'afficher ou le masquer.</p>
          </Rubrique>
          <Rubrique numero="③" titre="Couleur" idee="communautés">
            <Segment testid="labo-couleur" valeur={couleur} onChange={regler("couleur")} options={[["domaine", "Domaine déclaré"], ["communaute", "Communauté calculée"]]} />
            <Bascule testid="labo-ecarts" actif={ecarts} onChange={regler("ecarts")} label={`Marquer les écarts déclaré ↔ calculé (${ecartsSet.size})`} aide="Jumeau dont la communauté réelle est dominée par un autre domaine que le sien" />
          </Rubrique>
          <Rubrique numero="④" titre="Zones" idee="hyper-arêtes">
            <Bascule testid="labo-zones-situations" actif={zones} onChange={regler("zones")} label={`Situations transversales (${zonesChoisies.size}/${situations.length})`} aide="Chaque situation regroupe des jumeaux de plusieurs domaines" />
            {zones && (
              <div className="max-h-32 space-y-0.5 overflow-y-auto rounded-lg border border-white/[0.06] p-1.5" data-testid="labo-liste-situations">
                {situations.map((sit, i) => (
                  <label key={sit.id} className="flex cursor-pointer items-start gap-1.5 rounded px-1 py-0.5 text-[10px] leading-snug text-[#94A3B8] hover:bg-white/[0.05]">
                    <input type="checkbox" checked={zonesChoisies.has(sit.id)} onChange={() => basculerZone(sit.id)} className="mt-0.5 accent-[#9B87F5]" />
                    <span className="mt-1 h-2 w-2 shrink-0 rounded-full" style={{ background: COULEURS_ZONES[i % COULEURS_ZONES.length] }} />
                    <span className="flex-1">{sit.titre}</span>
                    <span className="font-code text-[9px] text-[#64748B]">{(sit.jumeaux || []).length}</span>
                  </label>
                ))}
              </div>
            )}
            <Bascule testid="labo-coques" actif={coques} onChange={regler("coques")} label="Coques du regroupement courant" aide="Enveloppe de chaque domaine ou communauté" />
          </Rubrique>
          <Rubrique numero="⑤" titre="Taille" idee="degré">
            <Segment testid="labo-taille" valeur={taille} onChange={regler("taille")} options={[["uniforme", "Uniforme (actuel)"], ["degre", "Selon le degré"]]} />
          </Rubrique>
          <Rubrique numero="⑦" titre="Forme" idee="robot du film">
            <Segment testid="labo-forme" valeur={reglages.forme} onChange={regler("forme")} options={[["robot", "Robot-jumeau"], ["disque", "Disque"]]} />
            <p className="text-[10px] leading-snug text-[#7C93A8]">Le robot vectoriel du film (remotion-meridian), teinté de la couleur du groupe : yeux, cœur, antenne, aura. Le jumeau sélectionné sourit.</p>
          </Rubrique>
          <Rubrique numero="⑥" titre="Disposition" idee="forces">
            <Segment testid="labo-disposition" valeur={disposition} onChange={regler("disposition")} options={[["atlas", "Atlas (stable)"], ["force", "Force (proposée)"]]} />
            <p className="text-[10px] leading-snug text-[#7C93A8]">La disposition par forces rapproche les jumeaux fortement liés. Déterministe, sans chevauchement (≥ 105 px). Elle propose : elle ne remplace pas les coordonnées de l'Atlas.</p>
          </Rubrique>
          <Rubrique numero="⑧" titre="Échelle" idee="100 · 500 · 1 000">
            <Segment testid="labo-echelle" valeur={echelle} onChange={changerEchelle} options={ECHELLES} />
            {echelle !== "reel" && <p className="text-[10px] leading-snug text-[#7C93A8]">Mesh synthétique de même structure (domaines, hubs, liens transverses, états), déterministe.</p>}
            <Bascule testid="labo-optim-virtualisation" actif={optim.virtualisation} onChange={(v) => setOptim((o) => ({ ...o, virtualisation: v }))} label="Ne rendre que les éléments visibles" aide="Virtualisation React Flow : nœuds et liens hors écran ne sont pas dessinés" />
            <Bascule testid="labo-optim-detail" actif={optim.detail} onChange={(v) => setOptim((o) => ({ ...o, detail: v }))} label="Niveau de détail (disques si très dézoomé)" aide={`Sous un zoom de ${SEUIL_ZOOM_DETAIL} les robots deviennent des disques ; au-delà de 150 jumeaux, robots sans filtres ni animations`} />
            <button type="button" onClick={async () => setFluidite(await mesurerFluidite())} data-testid="labo-mesurer" className="flex min-h-[30px] w-full items-center justify-center rounded-lg border border-white/10 text-[11px] text-[#CBD5E1] hover:text-white">
              Mesurer la fluidité (pan + zoom, 2,5 s)
            </button>
            <div className="space-y-0.5 rounded-lg bg-white/[0.03] p-2 font-code text-[10px] leading-relaxed text-[#94A3B8]" data-testid="labo-mesures">
              <div>Génération {mesures.generation ?? "—"} ms · Louvain {mesures.louvain ?? "—"} ms{mesures.force != null ? ` · Force ${mesures.force} ms` : ""}</div>
              <div>Affichage après changement : {mesures.affichage ?? "—"} ms</div>
              <div>Dans le DOM : {dom.noeuds} nœuds · {dom.liens} liens</div>
              <div>Fluidité : {fluidite ? `${fluidite.ips} images/s · p95 ${fluidite.p95} ms · pire ${fluidite.pire} ms` : "—"}</div>
            </div>
          </Rubrique>
          <Link to="/labo/echelle" className="block text-center font-code text-[10px] text-[#C4B5FD] hover:text-white" data-testid="labo-vers-echelle">
            Passage à l'échelle : 1 000 → 1 000 000 de jumeaux →
          </Link>
          <Link to="/atlas" className="block text-center font-code text-[10px] text-[#7C93A8] hover:text-white" data-testid="labo-vers-atlas">
            Ouvrir l'Atlas actuel →
          </Link>
        </div>
      )}
      <div ref={carteRef} className="relative min-w-0 flex-1">
        {!panneau && (
          <button type="button" onClick={() => setPanneau(true)} data-testid="labo-deplier" className="absolute left-3 top-3 z-10 flex min-h-[34px] items-center gap-1.5 rounded-lg border border-white/10 bg-[#0C1724]/92 px-3 text-[11px] text-[#CBD5E1] hover:text-white">
            <Flask size={13} className="text-[#9B87F5]" /> Réglages
          </button>
        )}
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.04}
          maxZoom={2.5}
          onlyRenderVisibleElements={optim.virtualisation}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          proOptions={{ hideAttribution: true }}
          onNodeClick={(_, n) => setSelection((s) => (s === n.id ? null : n.id))}
          onPaneClick={() => setSelection(null)}
          onNodeMouseEnter={(_, n) => { setAreteSurvolee(null); setSurvol(n.id); }}
          onNodeMouseLeave={() => setSurvol(null)}
          onEdgeMouseEnter={(e, ed) => { const b = carteRef.current?.getBoundingClientRect(); if (b) setAreteSurvolee({ id: ed.id, x: e.clientX - b.left, y: e.clientY - b.top }); }}
          onEdgeMouseMove={(e) => { const b = carteRef.current?.getBoundingClientRect(); if (b) setAreteSurvolee((a) => (a ? { ...a, x: e.clientX - b.left, y: e.clientY - b.top } : a)); }}
          onEdgeMouseLeave={() => setAreteSurvolee(null)}
          // Sans gestionnaire de clic, React Flow marque les liens « inactifs » (pointer-events: none) : le survol ne partirait jamais
          onEdgeClick={() => {}}
          className="!bg-[#020617]"
        >
          <Background gap={26} size={1} color="rgba(96,165,250,0.17)" />
          <ViewportPortal>
            <svg style={{ position: "absolute", left: 0, top: 0, overflow: "visible", pointerEvents: "none" }} width="1" height="1" data-testid="labo-zones">
              {coquesGroupes.map((z) => zoneSvg(z, 0.07))}
              {zonesSituations.map((z) => zoneSvg(z, 0.12))}
            </svg>
          </ViewportPortal>
        </ReactFlow>

        {apercu && (
          <div className="pointer-events-none absolute z-20 w-[236px] space-y-1.5 rounded-xl border border-white/10 bg-[#0C1724]/95 p-3 shadow-2xl backdrop-blur-xl" style={{ left: apercu.left, top: apercu.top }} data-testid="labo-apercu">
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: couleurGroupe.get(cleDe(apercu.j)) || couleurGroupeDomaine(apercu.j.domaine) }} />
              <span className="min-w-0 flex-1 truncate text-sm font-semibold text-white">{apercu.j.nom}</span>
              <span className="font-code text-[10px] text-[#64748B]">{idNumerique(apercu.j.id)}</span>
            </div>
            <div className="font-code text-[10px] uppercase tracking-wider text-[#7C93A8]">
              {apercu.j.domaine}
              {ecartsSet.has(apercu.j.id) && <span className="ml-2 text-[#F59E0B]">⚠ écart</span>}
            </div>
            <div className="grid grid-cols-2 gap-1.5 pt-0.5 text-center">
              {[["Degré", `${deg.get(apercu.j.id) || 0}`], ["Couverture", apercu.j.couverture != null ? `${apercu.j.couverture} %` : "—"]].map(([k, v]) => (
                <div key={k} className="rounded-lg bg-white/[0.04] px-1 py-1">
                  <div className="font-code text-[11px] font-semibold text-[#F2F6F8]">{v}</div>
                  <div className="font-code text-[8px] uppercase tracking-wider text-[#64748B]">{k}</div>
                </div>
              ))}
            </div>
            {apercu.j.fraicheur && <div className="font-code text-[10px] text-[#7C93A8]">Fraîcheur : <span className="text-[#CBD5E1]">{apercu.j.fraicheur}</span></div>}
            {apercu.j.mission && <p className="line-clamp-2 text-[11px] leading-snug text-[#94A3B8]">{apercu.j.mission}</p>}
            <div className="font-code text-[9px] text-[#526578]">Cliquer pour épingler la fiche</div>
          </div>
        )}
        {areteSurvolee && (() => {
          const r = relations.find((x) => x.id === areteSurvolee.id);
          if (!r) return null;
          const a = parId.get(r.source);
          const b = parId.get(r.cible);
          const e = ETATS_RELATION[r.etat];
          return (
            <div className="pointer-events-none absolute z-20 max-w-[260px] rounded-lg border border-white/10 bg-[#0C1724]/95 px-2.5 py-1.5 text-[11px] text-[#DCE6EE] shadow-xl" style={{ left: areteSurvolee.x + 14, top: areteSurvolee.y + 14 }} data-testid="labo-tooltip-lien">
              <div className="font-semibold">{a?.nom} → {b?.nom}</div>
              <div className="font-code text-[10px]" style={{ color: e?.couleur }}>{e?.label || r.etat}</div>
            </div>
          );
        })()}

        <div className="pointer-events-none absolute bottom-3 left-4 z-10 rounded-md bg-[#071019]/80 px-2.5 py-1 font-code text-[10px] text-[#7C93A8]" data-testid="labo-stats">
          {jumeaux.length} jumeaux · {relations.length} relations · {communautes.length} communautés (modularité {louv.modularite.toFixed(2)}) · {ecartsSet.size} écarts
        </div>
      </div>

      {/* Colonne de droite : recherche, fiche, légende-filtre */}
      <aside className="flex w-[300px] shrink-0 flex-col border-l border-white/[0.08] bg-[#091420]" data-testid="labo-colonne">
        <div className="relative border-b border-white/[0.08] p-3">
          <div className="flex items-center gap-2 rounded-lg border border-white/10 bg-[#071019] px-2.5">
            <MagnifyingGlass size={13} className="text-[#7C93A8]" />
            <input value={recherche} onChange={(e) => setRecherche(e.target.value)} placeholder="Rechercher un jumeau…" data-testid="labo-recherche" className="min-h-[34px] flex-1 bg-transparent text-xs text-white outline-none placeholder:text-[#526578]" />
          </div>
          {resultats.length > 0 && (
            <div className="mt-1.5 max-h-40 overflow-y-auto" data-testid="labo-resultats">
              {resultats.map((j) => (
                <button key={j.id} onClick={() => { centrerSur(j.id); setRecherche(""); }} className="flex w-full items-center gap-2 rounded px-2 py-1 text-left text-xs text-[#CBD5E1] hover:bg-white/[0.06]" style={{ borderLeft: `3px solid ${couleurGroupeDomaine(j.domaine)}` }}>
                  {j.nom} <span className="ml-auto font-code text-[9px] text-[#64748B]">{idNumerique(j.id)}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="min-h-[150px] border-b border-white/[0.08] p-3.5" data-testid="labo-fiche">
          <h3 className="mb-2 font-code text-[10px] uppercase tracking-wider text-[#64748B]">Jumeau</h3>
          {!sel ? (
            <p className="text-xs italic text-[#526578]">Cliquez un jumeau pour l'inspecter.</p>
          ) : (
            <div className="space-y-1 text-xs text-[#CBD5E1]">
              <div className="text-sm font-semibold text-white">{sel.nom} <span className="font-code text-[10px] text-[#64748B]">{idNumerique(sel.id)}</span></div>
              <div>Domaine déclaré : <b className="text-white">{sel.domaine}</b></div>
              <div>Communauté calculée : <b className="text-white">{communauteSel?.nom}</b> <span className="text-[#64748B]">({Math.round((communauteSel?.part || 0) * 100)} % de ce domaine)</span></div>
              {ecartsSet.has(sel.id) && <div className="font-semibold text-[#F59E0B]" data-testid="labo-fiche-ecart">⚠ Écart : couplé surtout à « {communauteSel?.domaineDominant} »</div>}
              <div>Degré : <b className="text-white">{deg.get(sel.id) || 0}</b> / {maxDeg}</div>
              {voisinsSel.length > 0 && (
                <div className="pt-1">
                  <div className="mb-1 text-[10px] text-[#64748B]">Voisins ({voisinsSel.length})</div>
                  <div className="max-h-32 space-y-0.5 overflow-y-auto">
                    {voisinsSel.map(({ r, autre, sortant }) => autre && (
                      <button key={r.id} onClick={() => centrerSur(autre.id)} className="flex w-full items-center gap-1.5 rounded px-1.5 py-0.5 text-left text-[11px] hover:bg-white/[0.06]" style={{ borderLeft: `3px solid ${couleurGroupeDomaine(autre.domaine)}` }}>
                        <span className="text-[#64748B]">{sortant ? "→" : "←"}</span>
                        <span className="truncate">{autre.nom}</span>
                        <span className="ml-auto text-[9px]" style={{ color: ETATS_RELATION[r.etat]?.couleur }}>{ETATS_RELATION[r.etat]?.label}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-3.5" data-testid="labo-legende">
          <h3 className="mb-2 font-code text-[10px] uppercase tracking-wider text-[#64748B]">{couleur === "domaine" ? "Domaines déclarés" : "Communautés calculées"}</h3>
          <label className="mb-2 flex cursor-pointer items-center gap-2 text-xs text-[#94A3B8]">
            <input ref={refTout} type="checkbox" checked={masques.size === 0} onChange={(e) => toutBasculer(e.target.checked)} data-testid="labo-tout" className="accent-[#9B87F5]" />
            Tout sélectionner
          </label>
          {legende.map((e) => (
            <label key={e.cle} className={`flex cursor-pointer items-center gap-2 rounded px-1 py-1 text-xs hover:bg-white/[0.05] ${masques.has(e.cle) ? "opacity-40" : ""}`} data-testid={`labo-groupe-${e.cle}`}>
              <input type="checkbox" checked={!masques.has(e.cle)} onChange={() => basculerGroupe(e.cle)} className="accent-[#9B87F5]" />
              <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: e.couleur }} />
              <span className="flex-1 truncate text-[#DCE6EE]">{e.label}</span>
              {e.purete != null && <span className="font-code text-[9px] text-[#64748B]" title="Part du domaine dominant">{Math.round(e.purete * 100)} %</span>}
              <span className="font-code text-[10px] text-[#7C93A8]">{e.n}</span>
            </label>
          ))}
          <div className="mt-4 space-y-1 border-t border-white/[0.07] pt-3">
            <h3 className="mb-1 font-code text-[10px] uppercase tracking-wider text-[#64748B]">Liens</h3>
            {Object.entries(ETATS_RELATION).map(([k, v]) => (
              <div key={k} className="flex items-center gap-2 text-[11px] text-[#94A3B8]">
                <span className="inline-block w-5 border-t-2" style={{ borderColor: v.couleur, borderStyle: STYLE_ETAT[k]?.pointille ? "dashed" : "solid" }} />
                {v.label}
              </div>
            ))}
          </div>
        </div>
      </aside>
    </div>
  );
}

export default function LaboAtlas() {
  return (
    <ReactFlowProvider>
      <Labo />
    </ReactFlowProvider>
  );
}
