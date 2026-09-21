import { MarkerType } from "@xyflow/react";
import { ETATS_RELATION } from "@/lib/domaines";
import { decrireCommunautes, degres, louvain } from "@/lib/laboGraphe";

// Rendu « graphe » de l'Atlas : robots dimensionnés par leur degré, liens courbes stylés selon l'état de la relation,
// écarts de communauté (le domaine déclaré n'est pas celui que le couplage réel suggère).
// Ces fonctions ne touchent ni aux positions ni à la sélection : elles habillent ce que construit `construireGraphe`.

export const TAILLE_MIN = 22;
export const TAILLE_MAX = 34; // hauteur du robot = 1,9 × taille : le plus grand tient dans l'empreinte 64 × 80
export const SEUIL_NOM = 0.35; // un jumeau porte son nom quand son degré atteint 35 % du maximum
const RAYON_ROBOT = 0.7; // rayon d'accroche des liens = 0,7 × taille
const SEUIL_LEGER = 150; // au-delà, robots sans filtres ni animations

export const STYLE_ETAT = {
  confirmee: { largeur: 2, pointille: false, opacite: 0.7 },
  observee: { largeur: 2, pointille: false, opacite: 0.75 },
  supposee: { largeur: 1.3, pointille: true, opacite: 0.55 },
  validation: { largeur: 1.5, pointille: true, opacite: 0.6 },
  contestee: { largeur: 1.6, pointille: true, opacite: 0.7 },
  obsolete: { largeur: 1, pointille: true, opacite: 0.3 },
};

export function analyserMesh(mesh) {
  const jumeaux = (mesh?.jumeaux || []).filter((j) => !j.anonyme);
  const ids = jumeaux.map((j) => j.id);
  const rels = (mesh?.relations || []).filter((r) => r.source !== r.cible).map((r) => ({ source: r.source, cible: r.cible }));
  const deg = degres(ids, rels);
  const maxDeg = Math.max(1, ...deg.values());
  const { ecarts } = decrireCommunautes(jumeaux, louvain(ids, rels).comm);
  return { deg, maxDeg, ecarts, leger: jumeaux.length > SEUIL_LEGER };
}

export const tailleDe = (analyse, id) => Math.round(TAILLE_MIN + (TAILLE_MAX - TAILLE_MIN) * ((analyse.deg.get(id) || 0) / analyse.maxDeg));

// Habille un nœud « twin » construit par construireGraphe.
export function habillerNoeud(n, analyse) {
  const j = n.data?.jumeau;
  if (!j || j.anonyme || j.cadastre) return n;
  const important = (analyse.deg.get(j.id) || 0) >= SEUIL_NOM * analyse.maxDeg;
  return { ...n, data: { ...n.data, taille: tailleDe(analyse, j.id), ecart: analyse.ecarts.has(j.id), nomVisible: important, leger: analyse.leger } };
}

export function aretesGraphe(mesh, nodes, analyse) {
  const twins = new Map(nodes.filter((n) => n.type === "twin" && !n.hidden && !n.data?.cadastre).map((n) => [n.id, n]));
  const rayon = (n) => Math.round((n.data.taille || tailleDe(analyse, n.id)) * RAYON_ROBOT);
  return (mesh?.relations || [])
    .filter((r) => r.source !== r.cible && twins.has(r.source) && twins.has(r.cible))
    .map((r) => {
      const a = twins.get(r.source);
      const b = twins.get(r.cible);
      const st = STYLE_ETAT[r.etat] || STYLE_ETAT.observee;
      const couleur = ETATS_RELATION[r.etat]?.couleur || "#94A3B8";
      const estompee = !!a.data.dim || !!b.data.dim;
      return {
        id: r.id,
        source: r.source,
        target: r.cible,
        type: "graphe",
        data: { etat: r.etat, couleur, largeur: st.largeur, pointille: st.pointille, opacite: estompee ? 0.1 : st.opacite, estompee, r1: rayon(a), r2: rayon(b) },
        markerEnd: { type: MarkerType.ArrowClosed, width: 11, height: 11, color: couleur },
      };
    });
}
