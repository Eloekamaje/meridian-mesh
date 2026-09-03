import { Handle, Position } from "@xyflow/react";
import { LockSimple, Code, Database, Pulse, WarningOctagon, FileText, Lightning } from "@phosphor-icons/react";
import { couleurDomaine, couleurConfiance, ETATS_RELATION } from "@/lib/domaines";
import { idNumerique } from "@/lib/atlasGraph";

const ROBOT = "/assets/robot-jumeau.jpg";

// Niveau 4 — Composants & preuves : sources connectées (icônes) et strates de connaissance (jauges)
const SOURCES_ICONES = {
  code: { Icon: Code, nom: "Code" },
  bdd: { Icon: Database, nom: "Base de données" },
  observabilite: { Icon: Pulse, nom: "Observabilité" },
  incidents: { Icon: WarningOctagon, nom: "Incidents" },
  documentation: { Icon: FileText, nom: "Documentation" },
  evenements: { Icon: Lightning, nom: "Événements" },
};
const STRATES_CLES = [
  ["identite", "I"],
  ["comportement", "C"],
  ["relations", "R"],
  ["trajectoire", "T"],
  ["memoire", "M"],
];

// Avatar robot du jumeau : tête blanche arrondie, écran facial sombre, yeux turquoise, antenne
function AvatarJumeau({ selected, actif, grand, ports, relLiee }) {
  const cls = "!h-2 !w-2 !min-w-0 !border-0 !bg-transparent";
  const taille = grand ? "h-14 w-14" : "h-12 w-12";
  return (
    <span className={`relative flex ${taille} shrink-0 items-center justify-center transition-transform duration-200 group-hover:scale-[1.06]`}>
      <Handle type="target" id="t-l" position={Position.Left} className={cls} style={{ left: -2, top: "46%" }} />
      <Handle type="source" id="s-l" position={Position.Left} className={cls} style={{ left: -2, top: "46%" }} />
      <Handle type="target" id="t-r" position={Position.Right} className={cls} style={{ right: -2, top: "46%" }} />
      <Handle type="source" id="s-r" position={Position.Right} className={cls} style={{ right: -2, top: "46%" }} />
      <Handle type="target" id="t-t" position={Position.Top} className={cls} style={{ top: -2, left: "46%" }} />
      <Handle type="source" id="s-t" position={Position.Top} className={cls} style={{ top: -2, left: "46%" }} />
      {ports && (
        <>
          <span className="absolute -left-1 top-1/2 h-1.5 w-1.5 -translate-y-1/2 rounded-full bg-[#71716D]" data-testid="port-entree" />
          <span className="absolute -right-1 top-1/2 h-1.5 w-1.5 -translate-y-1/2 rounded-full bg-[#0E7490]" data-testid="port-sortie" />
        </>
      )}
      {actif && (
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#0E7490] opacity-25" />
      )}
      <span
        className={`relative flex ${taille} items-center justify-center overflow-hidden rounded-full bg-white transition-shadow duration-200 ${
          selected
            ? "shadow-[0_0_18px_rgba(14,116,144,0.5)] ring-2 ring-[#0E7490]"
            : relLiee
              ? "shadow-[0_0_14px_rgba(14,116,144,0.4)] ring-2 ring-[#0E7490]/70"
              : "shadow-sm ring-1 ring-black/10 group-hover:shadow-[0_0_14px_rgba(14,116,144,0.45)] group-hover:ring-2 group-hover:ring-[#0E7490]/70"
        }`}
      >
        <img src={ROBOT} alt="" draggable={false} className={`${grand ? "h-[3.25rem] w-[3.25rem]" : "h-11 w-11"} scale-[1.65] object-cover`} />
      </span>
    </span>
  );
}

// Pastille discrète (portes externes, périmètres restreints — pas de robot)
function PointJumeau({ couleur, dashed }) {
  const cls = "!h-2 !w-2 !min-w-0 !border-0 !bg-transparent";
  return (
    <span className="relative flex h-4 w-4 shrink-0 items-center justify-center">
      <Handle type="target" id="t-l" position={Position.Left} className={cls} style={{ left: -2, top: 7 }} />
      <Handle type="source" id="s-l" position={Position.Left} className={cls} style={{ left: -2, top: 7 }} />
      <Handle type="target" id="t-r" position={Position.Right} className={cls} style={{ right: -2, top: 7 }} />
      <Handle type="source" id="s-r" position={Position.Right} className={cls} style={{ right: -2, top: 7 }} />
      <Handle type="target" id="t-t" position={Position.Top} className={cls} style={{ top: -2, left: 7 }} />
      <Handle type="source" id="s-t" position={Position.Top} className={cls} style={{ top: -2, left: 7 }} />
      <span
        className={`relative inline-flex h-4 w-4 items-center justify-center rounded-full border-2 bg-white ${dashed ? "border-dashed" : ""}`}
        style={{ borderColor: couleur, boxShadow: "0 1px 3px rgba(17,17,16,0.15)" }}
      >
        <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: couleur }} />
      </span>
    </span>
  );
}

export default function TwinNode({ data, selected }) {
  const j = data.jumeau;
  const couleur = couleurDomaine(j?.domaine || data.grappe?.domaine);
  const niveau3 = (data.niveau || 2) >= 3;

  // Jumeau hors périmètre : pastille pointillée + résumé au survol uniquement
  if (j?.anonyme) {
    return (
      <div className="group relative" data-testid={`twin-node-${j.id}`}>
        <div className="absolute -top-3 left-1/2 z-50 w-56 -translate-x-1/2 -translate-y-full rounded-lg border border-[#E5E5E3] bg-white p-3 opacity-0 backdrop-blur-xl transition-opacity duration-200 group-hover:opacity-100" data-testid={`anonyme-apercu-${j.id}`}>
          <div className="font-display text-xs font-bold" style={{ color: couleur }}>{j.domaine} — hors périmètre</div>
          <div className="mt-1.5 space-y-0.5 font-code text-[10px] text-[#52524F]">
            <div>Domaine voisin non inclus dans votre périmètre.</div>
            <div>Position approximative — la précision n'est pas garantie.</div>
          </div>
          <div className="mt-2 font-code text-[9px] text-[#71716D]">Résumé uniquement</div>
        </div>
        <div className={`flex flex-col items-center gap-1 transition-opacity duration-500 ${data.dim ? "opacity-15" : "opacity-45"}`}>
          <Handle type="target" id="t-b" position={Position.Bottom} className="!h-2 !w-2 !min-w-0 !border-0 !bg-transparent" style={{ bottom: -2, left: "46%" }} />
          <Handle type="source" id="s-b" position={Position.Bottom} className="!h-2 !w-2 !min-w-0 !border-0 !bg-transparent" style={{ bottom: -2, left: "46%" }} />
          <PointJumeau couleur={couleur} dashed />
          <span className="rounded bg-white/70 px-1.5 font-code text-[9px] tracking-wide text-[#52524F]">{idNumerique(j.id)}</span>
          <span className="flex items-center gap-1 rounded-full bg-[#EDECE6] px-1.5 py-px font-code text-[8px] text-[#71716D]">
            <LockSimple size={8} />
            résumé
          </span>
        </div>
      </div>
    );
  }

  // Jumeau = identifiant numérique + robot. Niveau 4 : carte « composants & preuves »
  // arbitrée par le moteur de labels — au-dessus ou en dessous du robot selon l'espace libre.
  const carteDetail = data.detailVisible && j.strates && (
    <div
      className={`w-[150px] rounded-lg border border-[#E5E5E3] bg-white/95 p-2 shadow-sm ${
        data.detailPosition === "haut" ? "absolute bottom-full left-1/2 mb-0.5 -translate-x-1/2" : "-mx-[43px] mt-0.5"
      }`}
      data-testid={`twin-composants-${j.id}`}
    >
      <div className="flex items-center justify-center gap-1.5" data-testid={`twin-sources-${j.id}`}>
        {Object.entries(SOURCES_ICONES).map(([cle, { Icon, nom }]) => {
          const det = j.sources_detail?.find((s) => s.cle === cle);
          const active = !!j.sources?.[cle] || !!det;
          const alerte = !!det && det.statut !== "prete";
          return (
            <Icon
              key={cle}
              size={11}
              weight={active ? "fill" : "regular"}
              title={alerte ? `${nom} — ${det.statut.replaceAll("_", " ")}` : nom}
              className={alerte ? "text-[#B45309]" : active ? "text-[#047857]" : "text-[#D4D4D0]"}
            />
          );
        })}
      </div>
      <div className="mt-1.5 space-y-[3px]" data-testid={`twin-strates-${j.id}`}>
        {STRATES_CLES.map(([cle, initiale]) => (
          <div key={cle} className="flex items-center gap-1" title={`${cle} : ${j.strates[cle]} %`}>
            <span className="w-2.5 shrink-0 font-code text-[7px] uppercase text-[#71716D]">{initiale}</span>
            <div className="h-1 flex-1 overflow-hidden rounded-full bg-[#EDECE6]">
              <div className="h-full rounded-full" style={{ width: `${j.strates[cle]}%`, backgroundColor: couleurConfiance(j.strates[cle]) }} />
            </div>
            <span className="w-5 shrink-0 text-right font-code text-[7px] text-[#52524F]">{j.strates[cle]}</span>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div
      className={`group relative transition-opacity duration-500 ${data.dim ? "opacity-20" : data.adouci ? "opacity-60" : "opacity-100"}`}
      data-testid={`twin-node-${j.id}`}
    >
      {data.halo && (
        <span className="pointer-events-none absolute -inset-2 rounded-2xl" style={{ backgroundColor: `${couleur}10`, border: `1px solid ${couleur}2A` }} />
      )}
      {data.focusCentral && (
        <span className="pointer-events-none absolute -inset-1.5 rounded-2xl border-2" style={{ borderColor: couleur }} data-testid="twin-focus-ring" />
      )}
      <div className="flex w-16 flex-col items-center gap-1">
        <Handle type="target" id="t-b" position={Position.Bottom} className="!h-2 !w-2 !min-w-0 !border-0 !bg-transparent" style={{ bottom: -2, left: "46%" }} />
        <Handle type="source" id="s-b" position={Position.Bottom} className="!h-2 !w-2 !min-w-0 !border-0 !bg-transparent" style={{ bottom: -2, left: "46%" }} />
        <span className="relative inline-flex">
          <AvatarJumeau actif={j.statut === "actif"} selected={selected} grand={niveau3} ports={niveau3} relLiee={data.relLiee} />
          {data.detailPosition === "haut" && carteDetail}
          {data.dansSituation && (
            <span
              className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-[#6D28D9] ring-1 ring-white"
              title="Impliqué dans une situation active"
              data-testid={`twin-situation-${j.id}`}
            />
          )}
          {data.enTransformation && (
            <span
              className="absolute -left-1 -top-1 h-2.5 w-2.5 rounded-full border-2 border-dashed border-[#B45309] bg-white"
              title="En transformation"
              data-testid={`twin-transformation-${j.id}`}
            />
          )}
        </span>
        <span
          className="whitespace-nowrap font-code text-[10px] font-semibold tracking-wide text-[#3F3F3C] transition-colors group-hover:text-[#0E7490]"
          data-testid={`twin-nom-${j.id}`}
        >
          {idNumerique(j.id)}
        </span>
        {data.detailPosition !== "haut" && carteDetail}
      </div>
    </div>
  );
}
