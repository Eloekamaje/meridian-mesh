import { MarkerType } from "@xyflow/react";
import { aretesInterfaces } from "./atlasInterfaces";

const nodes = [
  { id: "app-facturation", type: "twin", data: { taille: 30 } },
  { id: "app-crm", type: "twin", data: { taille: 20 } },
  { id: "app-reporting", type: "twin", data: { taille: 24 } },
  { id: "app-cache", type: "twin", hidden: true, data: { taille: 26 } },
  { id: "region", type: "region", data: {} },
];

const operations = [
  { id: "op-1", method: "GET", path: "/clients" },
  { id: "op-2", method: "POST", path: "/factures" },
  { id: "op-3", method: "GET", path: "/rapports" },
];

function arete(source, target, operationId, mode) {
  return { source, target, operation_id: operationId, mode, confidence: 0.9, assertion_source: "contrat", evidence: ["preuve"] };
}

test("aretesInterfaces construit une arête React Flow pour deux twins visibles", () => {
  const aretes = aretesInterfaces({ operations, edges: [arete("app-facturation", "app-crm", "op-1", "declared")] }, nodes, null);

  expect(aretes).toHaveLength(1);
  const [a] = aretes;
  expect(a.id).toMatch(/^iface-/);
  expect(a.type).toBe("graphe");
  expect(a.source).toBe("app-facturation");
  expect(a.target).toBe("app-crm");
  expect(a.data.interface).toBe(true);
  expect(a.data.mode).toBe("declared");
  expect(a.data.couleur).toBe("#60A5FA");
  expect(a.data.largeur).toBeGreaterThan(0);
  expect(a.data.pointille).toBe(false);
  expect(a.data.opacite).toBeGreaterThan(0);
  expect(a.data.r1).toBe(21);
  expect(a.data.r2).toBe(14);
  expect(a.label).toBe("GET /clients");
  expect(a.data.operation).toBe("GET /clients");
  expect(a.data.confidence).toBe(0.9);
  expect(a.data.assertionSource).toBe("contrat");
  expect(a.data.evidence).toEqual(["preuve"]);
  expect(a.markerEnd.type).toBe(MarkerType.ArrowClosed);
});

test("aretesInterfaces ignore les nœuds absents, masqués ou non twin", () => {
  const edges = [
    arete("inconnue", "app-crm", "op-1", "declared"),
    arete("app-facturation", "inconnue", "op-1", "declared"),
    arete("app-facturation", "app-cache", "op-2", "observed"),
    arete("app-facturation", "region", "op-3", "inferred"),
  ];

  expect(aretesInterfaces({ operations, edges }, nodes, null)).toEqual([]);
});

test("aretesInterfaces applique les couleurs et pointillés des modes puis déduplique", () => {
  const edges = [
    arete("app-facturation", "app-crm", "op-1", "declared"),
    { ...arete("app-facturation", "app-crm", "op-1", "declared"), operation: "GET /clients" },
    arete("app-reporting", "app-crm", "op-3", "observed"),
    arete("app-crm", "app-reporting", "op-2", "inferred"),
  ];

  const aretes = aretesInterfaces({ operations, edges }, nodes, null);

  expect(aretes).toHaveLength(3);
  expect(aretes[0].data.couleur).toBe("#60A5FA");
  expect(aretes[0].data.pointille).toBe(false);

  const observee = aretes.find((a) => a.data.mode === "observed");
  expect(observee.data.couleur).toBe("#34D399");
  expect(observee.data.pointille).toBe(true);
  expect(observee.label).toBe("GET /rapports");

  const inferee = aretes.find((a) => a.data.mode === "inferred");
  expect(inferee.data.couleur).toBe("#F2B84B");
  expect(inferee.data.pointille).toBe(true);
  expect(inferee.label).toBe("POST /factures");
});

test("aretesInterfaces calcule le rayon depuis l'analyse quand le nœud n'a pas de taille", () => {
  const sansTaille = [
    { id: "app-facturation", type: "twin", data: {} },
    { id: "app-crm", type: "twin", data: {} },
  ];
  const analyse = { deg: new Map([["app-facturation", 10], ["app-crm", 0]]), maxDeg: 10 };

  const [a] = aretesInterfaces({ operations, edges: [arete("app-facturation", "app-crm", "op-1", "declared")] }, sansTaille, analyse);

  expect(a.data.r1).toBe(24);
  expect(a.data.r2).toBe(15);
});

test("aretesInterfaces estompe les arêtes dont un nœud est atténué", () => {
  const attenues = nodes.map((n) => (n.id === "app-crm" ? { ...n, data: { ...n.data, dim: true } } : n));

  const [a] = aretesInterfaces({ operations, edges: [arete("app-facturation", "app-crm", "op-1", "declared")] }, attenues, null);

  expect(a.data.estompee).toBe(true);
  expect(a.data.opacite).toBe(0.1);
});
