import { MarkerType } from "@xyflow/react";
import { TAILLE_MIN, tailleDe } from "@/lib/atlasRendu";

const RAYON_ROBOT = 0.7;
const LONGUEUR_LABEL = 44;

export const MODES_INTERFACE = {
  declared: { couleur: "#60A5FA", largeur: 2, pointille: false, opacite: 0.72 },
  observed: { couleur: "#34D399", largeur: 1.8, pointille: true, opacite: 0.68 },
  inferred: { couleur: "#F2B84B", largeur: 1.4, pointille: true, opacite: 0.55 },
};

function normaliserMode(mode) {
  const valeur = String(mode || "").toLowerCase();
  return MODES_INTERFACE[valeur] ? valeur : "inferred";
}

function libelleDepuisOperation(operation) {
  if (operation && typeof operation === "object") {
    const methode = operation.method || operation.protocol;
    const chemin = operation.path || operation.name || operation.id;
    if (methode && chemin) return `${String(methode).toUpperCase()} ${chemin}`;
    if (chemin) return String(chemin);
  }
  if (typeof operation === "string" && operation.trim()) return operation.trim();
  return "";
}

function libelleOperation(edge, operationsParId) {
  const direct = libelleDepuisOperation(edge.operation);
  if (direct) return direct;
  const reference = operationsParId.get(String(edge.operation_id || ""));
  const depuisReference = libelleDepuisOperation(reference);
  if (depuisReference) return depuisReference;
  return edge.operation_id != null && edge.operation_id !== "" ? String(edge.operation_id) : "";
}

function cleOperation(edge, libelle) {
  if (edge.operation_id != null && edge.operation_id !== "") return `id:${String(edge.operation_id)}`;
  if (edge.operation && typeof edge.operation === "object") {
    try {
      return `operation:${JSON.stringify(edge.operation)}`;
    } catch {
      return `operation:${libelle}`;
    }
  }
  return `operation:${libelle}`;
}

function tronquer(libelle) {
  return libelle.length > LONGUEUR_LABEL ? `${libelle.slice(0, LONGUEUR_LABEL)}…` : libelle;
}

export function aretesInterfaces(donnees, nodes, analyse) {
  const edges = Array.isArray(donnees?.edges) ? donnees.edges : [];
  const operations = Array.isArray(donnees?.operations) ? donnees.operations : [];
  const operationsParId = new Map(operations.map((operation) => [String(operation.id), operation]));
  const twins = new Map(
    (nodes || [])
      .filter((n) => n.type === "twin" && !n.hidden && !n.data?.cadastre)
      .map((n) => [String(n.id), n])
  );
  const rayon = (n) => {
    const taille = n.data?.taille || (analyse ? tailleDe(analyse, n.id) : TAILLE_MIN);
    return Math.round(taille * RAYON_ROBOT);
  };
  const vues = new Set();
  const aretes = [];

  edges.forEach((edge) => {
    if (!edge) return;
    const source = edge.source != null ? String(edge.source) : "";
    const target = edge.target != null ? String(edge.target) : "";
    const a = twins.get(source);
    const b = twins.get(target);
    if (!a || !b) return;

    const mode = normaliserMode(edge.mode);
    const libelle = libelleOperation(edge, operationsParId);
    const cle = `${source}\u0000${target}\u0000${cleOperation(edge, libelle)}\u0000${mode}`;
    if (vues.has(cle)) return;
    vues.add(cle);

    const style = MODES_INTERFACE[mode];
    const estompee = !!a.data?.dim || !!b.data?.dim;
    const operation = libelle ? tronquer(libelle) : null;

    aretes.push({
      id: `iface-${aretes.length}`,
      source,
      target,
      type: "graphe",
      label: operation || undefined,
      labelStyle: { fill: "#94A3B8", fontSize: 9, fontFamily: "var(--font-mono)" },
      labelBgStyle: { fill: "rgba(15,29,40,0.82)" },
      labelBgPadding: [4, 2],
      data: {
        interface: true,
        mode,
        operation,
        operationId: edge.operation_id ?? null,
        couleur: style.couleur,
        largeur: style.largeur,
        pointille: style.pointille,
        opacite: estompee ? 0.1 : style.opacite,
        estompee,
        r1: rayon(a),
        r2: rayon(b),
        confidence: edge.confidence ?? null,
        assertionSource: edge.assertion_source ?? null,
        evidence: edge.evidence ?? [],
      },
      markerEnd: { type: MarkerType.ArrowClosed, width: 11, height: 11, color: style.couleur },
    });
  });

  return aretes;
}
