import { Handle, Position } from "@xyflow/react";
import { couleurDomaine } from "@/lib/domaines";

export default function TwinNode({ data, selected }) {
  const j = data.jumeau;
  const couleur = couleurDomaine(j.domaine);
  const degrade = j.sante === "dégradé";
  const actif = j.statut === "actif";

  return (
    <div
      className={`relative transition-opacity duration-500 ${data.dim ? "opacity-20" : "opacity-100"}`}
      data-testid={`twin-node-${j.id}`}
    >
      {data.halo && (
        <span className="halo-anim pointer-events-none absolute -inset-3 rounded-xl" style={{ border: `1.5px solid ${couleur}` }} />
      )}
      <div
        className="w-[180px] rounded-lg border bg-[#0E0E0E]/95 px-3 py-2.5 backdrop-blur-sm transition-colors duration-300"
        style={{
          borderColor: selected ? couleur : `${couleur}55`,
          boxShadow: degrade ? `0 0 26px ${couleur}30` : selected ? `0 0 20px ${couleur}30` : "none",
        }}
      >
        <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-transparent" />
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2 shrink-0">
            {actif && (
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-50" style={{ backgroundColor: couleur }} />
            )}
            <span className="relative inline-flex h-2 w-2 rounded-full" style={{ backgroundColor: couleur }} />
          </span>
          <span className="truncate font-display text-[13px] font-bold text-white">{j.nom}</span>
          {data.evenements > 0 && (
            <span className="ml-auto shrink-0 rounded-full bg-white/10 px-1.5 py-0.5 font-code text-[9px] text-white/70">
              +{data.evenements}
            </span>
          )}
        </div>
        <div className="mt-1 flex items-center justify-between">
          <span className="font-code text-[9px] uppercase tracking-[0.18em] text-white/40">{j.domaine}</span>
          {data.etape != null && (
            <span className="font-code text-[9px] text-white/60">étape {data.etape}</span>
          )}
          {j.statut !== "actif" && (
            <span className="font-code text-[9px] text-[#F59E0B]">{j.statut}</span>
          )}
        </div>
        <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-transparent" />
      </div>
    </div>
  );
}
