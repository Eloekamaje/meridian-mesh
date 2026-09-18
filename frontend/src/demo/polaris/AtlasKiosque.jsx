// Projection Atlas du kiosque Polaris : scènes d'objets métier (initiatives, capacités,
// étapes de parcours) posées sur les jumeaux concernés — même identité visuelle que
// l'Atlas, comportements spontanés du produit absents. Acquittement après cadrage.
import { useEffect, useMemo, useRef } from "react";
import { ReactFlow, Background, Handle, Position } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { couleurDomaine } from "@/lib/domaines";

const PANNEAU = "border-[rgba(148,163,184,0.16)] bg-[#0F1D28]";

function NoeudBase({ data, children, largeur, testid }) {
  const c = couleurDomaine(data.domaine);
  const op = data.attenue ? 0.28 : 1;
  return (
    <div
      data-testid={testid}
      className={`rounded-xl border ${PANNEAU} transition-opacity duration-500 ${data.accent ? "shadow-[0_0_24px_rgba(37,208,200,0.15)]" : ""}`}
      style={{ width: largeur, opacity: op, borderColor: data.accent ? "rgba(37,208,200,0.45)" : undefined }}
    >
      <Handle type="target" position={Position.Left} className="!invisible" />
      <Handle type="source" position={Position.Right} className="!invisible" />
      <Handle type="target" position={Position.Top} className="!invisible" />
      <Handle type="source" position={Position.Bottom} className="!invisible" />
      <div className="h-0.5 w-full rounded-t-xl" style={{ background: c }} />
      {children}
    </div>
  );
}

export function NoeudInitiative({ data }) {
  return (
    <NoeudBase data={data} largeur={230} testid={`kiosque-noeud-${data.id}`}>
      <div className="p-3">
        <div className="font-code text-[8px] uppercase tracking-[0.3em] text-[#F2B84B]">Initiative</div>
        <div className="mt-1 font-display text-sm font-semibold leading-tight text-[#F2F6F8]">{data.label}</div>
        <div className="mt-1 text-[11px] leading-snug text-[#7C93A8]">{data.detail}</div>
      </div>
    </NoeudBase>
  );
}

export function NoeudCapacite({ data }) {
  return (
    <NoeudBase data={data} largeur={230} testid={`kiosque-noeud-${data.id}`}>
      <div className="p-3">
        <div className="font-code text-[8px] uppercase tracking-[0.3em] text-[#25D0C8]">Capacité</div>
        <div className="mt-1 font-display text-sm font-semibold leading-tight text-[#F2F6F8]">{data.label}</div>
        <div className="mt-1 text-[11px] leading-snug text-[#7C93A8]">{data.detail}</div>
      </div>
    </NoeudBase>
  );
}

export function NoeudEtape({ data }) {
  return (
    <NoeudBase data={data} largeur={190} testid={`kiosque-noeud-${data.id}`}>
      <div className="p-2.5">
        <div className="font-code text-[8px] uppercase tracking-[0.3em] text-[#7C93A8]">Étape du parcours</div>
        <div className="mt-0.5 font-display text-[13px] font-semibold text-[#F2F6F8]">{data.label}</div>
      </div>
    </NoeudBase>
  );
}

export function NoeudAppli({ data }) {
  return (
    <NoeudBase data={data} largeur={180} testid={`kiosque-noeud-${data.id}`}>
      <div className="flex items-center gap-2 p-2.5">
        <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: couleurDomaine(data.domaine), boxShadow: `0 0 8px ${couleurDomaine(data.domaine)}` }} />
        <div>
          <div className="font-display text-[13px] font-semibold leading-tight text-[#F2F6F8]">{data.label}</div>
          <div className="font-code text-[9px] text-[#7C93A8]">{data.domaine}</div>
        </div>
      </div>
    </NoeudBase>
  );
}

const TYPES = { initiative: NoeudInitiative, capacite: NoeudCapacite, etape: NoeudEtape, appli: NoeudAppli };

const STYLE_LIEN = {
  observee: { stroke: "#25D0C8", strokeWidth: 2 },
  a_etudier: { stroke: "#F2B84B", strokeWidth: 2, strokeDasharray: "8 6" },
  proposition: { stroke: "#9B87F5", strokeWidth: 2, strokeDasharray: "8 6" },
};

export default function AtlasKiosque({ sceneId, version, fixtures, commandeAttente, onScenePrete, onInteraction }) {
  const scene = fixtures.scenes[sceneId];
  const acquitte = useRef(null);

  const { nodes, edges } = useMemo(() => {
    if (!scene) return { nodes: [], edges: [] };
    const entites = Object.fromEntries([...fixtures.entites, ...fixtures.applications].map((e) => [e.id, e]));
    const nodes = scene.noeuds
      .filter((n) => !n.masque)
      .map((n) => {
        const e = entites[n.id];
        return {
          id: n.id,
          type: n.type,
          position: n.position,
          draggable: false,
          data: { id: n.id, label: e?.label || e?.nom, detail: e?.detail, domaine: e?.domaine, accent: n.accent, attenue: n.attenue },
        };
      });
    const edges = scene.liens.map((l) => {
      const rel = fixtures.relations.find((r) => r.id === l.id);
      const st = STYLE_LIEN[l.statut] || STYLE_LIEN.observee;
      return {
        id: l.id,
        source: rel.sourceId,
        target: rel.targetId,
        label: l.statut === "a_etudier" ? "à étudier" : rel.label,
        labelStyle: { fill: "#7C93A8", fontSize: 10, fontFamily: "JetBrains Mono" },
        labelBgStyle: { fill: "#0F1D28", fillOpacity: 0.9 },
        style: { ...st, opacity: l.attenue ? 0.25 : 1 },
        type: "smoothstep",
      };
    });
    return { nodes, edges };
  }, [scene, fixtures]);

  // Acquittement après cadrage réel (§7.3) — jamais déclenché par un timer de durée
  useEffect(() => {
    if (!scene || !commandeAttente) return undefined;
    if (acquitte.current === commandeAttente) return undefined;
    const t = setTimeout(() => {
      acquitte.current = commandeAttente;
      onScenePrete(commandeAttente);
    }, RYTHME_CADRAGE);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sceneId, version, commandeAttente, nodes.length]);

  if (!scene) return null;

  return (
    <div className="relative h-full w-full" data-testid="atlas-kiosque">
      <ReactFlow
        key={`${scene.id}-${version}`}
        nodes={nodes}
        edges={edges}
        nodeTypes={TYPES}
        fitView
        fitViewOptions={{ padding: 0.15, duration: 500 }}
        minZoom={0.4}
        maxZoom={1.6}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        onMoveStart={(evenement) => {
          // fitView programmatique passe evenement=null : seule une vraie interaction
          // utilisateur (souris/tactile) suspend la lecture (§6.3)
          if (evenement) onInteraction?.();
        }}
        proOptions={{ hideAttribution: true }}
        colorMode="dark"
      >
        <Background color="rgba(148,163,184,0.06)" gap={32} />
      </ReactFlow>
      <div className="absolute left-4 top-4 rounded-lg border border-[rgba(148,163,184,0.16)] bg-[#0F1D28]/90 px-3 py-2">
        <div className="font-code text-[9px] uppercase tracking-[0.25em] text-[#7C93A8]">{scene.titre}</div>
        <div className="font-display text-sm font-semibold text-[#F2F6F8]" data-testid="kiosque-scene-titre">{scene.question}</div>
      </div>
      <div className="absolute bottom-4 left-4 flex gap-3 rounded-lg border border-[rgba(148,163,184,0.16)] bg-[#0F1D28]/90 px-3 py-2 font-code text-[9px] text-[#7C93A8]" data-testid="kiosque-legende">
        <span className="flex items-center gap-1.5"><span className="inline-block h-0.5 w-6 bg-[#25D0C8]" /> existante</span>
        <span className="flex items-center gap-1.5"><span className="inline-block h-0.5 w-6 border-t-2 border-dashed border-[#F2B84B]" /> à étudier</span>
        <span className="flex items-center gap-1.5"><span className="inline-block h-0.5 w-6 border-t-2 border-dashed border-[#9B87F5]" /> proposition</span>
      </div>
    </div>
  );
}

const RYTHME_CADRAGE = 550;
