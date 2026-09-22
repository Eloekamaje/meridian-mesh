import { memo } from "react";
import { Handle, Position } from "@xyflow/react";
import { couleurDomaine } from "@/lib/domaines";
import { idNumerique } from "@/lib/atlasGraph";
import RobotJumeauSvg, { STYLES_ROBOT } from "./RobotJumeauSvg";
import TwinNode from "./TwinNode";

// Jumeau de l'Atlas : le robot du film, teinté par le domaine, avec son identifiant dessous.
// Même contrat `data` que TwinNode (halo, dim, situation, transformation…) — seul le rendu change.
// Le nœud garde l'empreinte 64 × 80 de TwinNode : le centre du robot est en (32, 34), là où s'accrochent les liens.
export const CENTRE_ROBOT = { x: 32, y: 34 };
const HANDLE = { position: "absolute", left: CENTRE_ROBOT.x, top: CENTRE_ROBOT.y, transform: "translate(-50%,-50%)", width: 1, height: 1, minWidth: 0, minHeight: 0, border: 0, background: "transparent", opacity: 0, pointerEvents: "none" };

function NoeudGraphe(props) {
  const { data, selected } = props;
  const j = data.jumeau;
  // Cadastre d'arrière-plan et jumeaux hors périmètre : représentation d'origine (silhouette / pastille pointillée)
  if (data.cadastre || j?.cadastre || j?.anonyme) return <TwinNode {...props} />;

  const couleur = couleurDomaine(j.domaine);
  const hauteur = Math.round((data.taille || 30) * 1.9);
  const actif = !!selected || !!data.relLiee;
  const opacite = data.fonduPlongeon ? 0.1 : data.dim ? 0.2 : data.adouci ? 0.6 : 1;
  return (
    <div
      className="group relative transition-opacity duration-300"
      style={{ width: 64, height: 80, opacity: opacite, ...(data.entree < 1 ? { opacity: data.entree } : {}), ...(data.style || {}) }}
      data-testid={`twin-node-${j.id}`}
      onClick={(e) => {
        if (e.shiftKey || e.metaKey || e.ctrlKey) { e.stopPropagation(); data.onMajClic?.(j.id); }
      }}
    >
      <style>{STYLES_ROBOT}</style>
      {(data.halo || data.focusCentral) && (
        <span className="pointer-events-none absolute rounded-full border-2" data-testid={data.halo ? "twin-halo-sober" : "twin-focus-ring"}
          style={{ left: CENTRE_ROBOT.x - hauteur * 0.5, top: CENTRE_ROBOT.y - hauteur * 0.5, width: hauteur, height: hauteur, borderColor: couleur, backgroundColor: `${couleur}14` }} />
      )}
      <div
        className="absolute transition-[filter] duration-200"
        style={{
          left: CENTRE_ROBOT.x, top: CENTRE_ROBOT.y, transform: "translate(-50%,-50%)",
          filter: actif ? `drop-shadow(0 0 8px ${couleur}) drop-shadow(0 0 16px ${couleur}88)` : undefined,
        }}
      >
        <RobotJumeauSvg hauteur={hauteur} couleur={couleur} ecart={!!data.ecart} content={actif} delai={(idNumerique(j.id) % 7) * 0.9} leger={!!data.leger} />
      </div>
      {data.dansSituation && (
        <span className="absolute h-2.5 w-2.5 rounded-full bg-[#60A5FA] ring-2 ring-[#070B12]" style={{ left: 46, top: 6 }} title="Impliqué dans une situation active" data-testid={`twin-situation-${j.id}`} />
      )}
      {data.enProjet && (
        <span className={`absolute flex h-4 min-w-4 items-center justify-center rounded px-1 font-code text-[9px] font-bold text-[#071019] ring-2 ring-[#070B12] ${data.enProjet.bloques > 0 ? "bg-[#F87171]" : "bg-[#93C5FD]"}`} style={{ left: 45, top: 42 }}
          title={`${data.enProjet.n} chantier${data.enProjet.n > 1 ? "s" : ""} Jira${data.enProjet.bloques > 0 ? `, ${data.enProjet.bloques} bloqué${data.enProjet.bloques > 1 ? "s" : ""}` : ""}`} data-testid={`twin-projets-${j.id}`}>
          {data.enProjet.n}
        </span>
      )}
      {data.enTransformation && (
        <span className="absolute h-2.5 w-2.5 rounded-full border-2 border-dashed border-[#F59E0B] bg-[#070B12]" style={{ left: 6, top: 6 }} title="En transformation" data-testid={`twin-transformation-${j.id}`} />
      )}
      <span
        className="pointer-events-none absolute left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-[#071019]/75 px-1.5 font-code text-[10px] font-semibold text-[#D8E2EA] group-hover:text-[#60A5FA]"
        style={{ top: CENTRE_ROBOT.y + hauteur / 2 - 3 }}
        data-testid={`twin-nom-${j.id}`}
      >
        {data.nomVisible ? j.nom : idNumerique(j.id)}
      </span>
      <Handle type="target" position={Position.Top} style={HANDLE} isConnectable={false} />
      <Handle type="source" position={Position.Top} style={HANDLE} isConnectable={false} />
    </div>
  );
}

export default memo(NoeudGraphe);
