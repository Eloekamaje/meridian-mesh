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
          <span className="absolute -left-1 top-1/2 h-1.5 w-1.5 -translate-y-1/2 rounded-full bg-[#7C93A8]" data-testid="port-entree" />
          <span className="absolute -right-1 top-1/2 h-1.5 w-1.5 -translate-y-1/2 rounded-full bg-[#25D0C8]" data-testid="port-sortie" />
        </>
      )}
      {actif && (
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#25D0C8] opacity-25" />
      )}
      <span
        className={`relative flex ${taille} items-center justify-center overflow-hidden rounded-full bg-[#0F1D28] transition-shadow duration-200 ${
          selected
            ? "shadow-[0_0_18px_rgba(14,116,144,0.5)] ring-2 ring-[#25D0C8]"
            : relLiee
              ? "shadow-[0_0_14px_rgba(14,116,144,0.4)] ring-2 ring-[#25D0C8]/70"
              : "shadow-sm ring-1 ring-black/10 group-hover:shadow-[0_0_14px_rgba(14,116,144,0.45)] group-hover:ring-2 group-hover:ring-[#25D0C8]/70"
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
        className={`relative inline-flex h-4 w-4 items-center justify-center rounded-full border-2 bg-[#0F1D28] ${dashed ? "border-dashed" : ""}`}
        style={{ borderColor: couleur, boxShadow: "0 1px 3px rgba(148,163,184,0.18)" }}
      >
        <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: couleur }} />
      </span>
    </span>
  );
}

// Niveau 2 « constellation » : le jumeau est une étoile brillante (halo teinté par le
// domaine, cœur quasi blanc, scintillement si actif). Le robot réapparaît au niveau 3.
// Même empreinte que l'avatar (h-12) : géométrie et routage strictement inchangés.
function EtoileJumeau({ couleur, selected, actif, relLiee, sansPorts = false }) {
  const cls = "!h-2 !w-2 !min-w-0 !border-0 !bg-transparent";
  const lumineux = selected || relLiee;
  return (
    <span className="relative flex h-12 w-12 shrink-0 items-center justify-center">
      {!sansPorts && (
        <>
          <Handle type="target" id="t-l" position={Position.Left} className={cls} style={{ left: -2, top: "46%" }} />
          <Handle type="source" id="s-l" position={Position.Left} className={cls} style={{ left: -2, top: "46%" }} />
          <Handle type="target" id="t-r" position={Position.Right} className={cls} style={{ right: -2, top: "46%" }} />
          <Handle type="source" id="s-r" position={Position.Right} className={cls} style={{ right: -2, top: "46%" }} />
          <Handle type="target" id="t-t" position={Position.Top} className={cls} style={{ top: -2, left: "46%" }} />
          <Handle type="source" id="s-t" position={Position.Top} className={cls} style={{ top: -2, left: "46%" }} />
        </>
      )}
      <span
        className="absolute rounded-full transition-opacity duration-200"
        style={{ width: 38, height: 38, background: `radial-gradient(circle, ${couleur}4D 0%, ${couleur}00 70%)`, opacity: lumineux ? 1 : 0.65 }}
      />
      {actif && <span className="absolute inline-flex h-3.5 w-3.5 animate-ping rounded-full opacity-40" style={{ backgroundColor: couleur }} />}
      <span
        className="relative rounded-full transition-all duration-200 group-hover:scale-125"
        style={{
          width: lumineux ? 10 : 7,
          height: lumineux ? 10 : 7,
          backgroundColor: "#F2F6F8",
          boxShadow: `0 0 6px 2px ${couleur}, 0 0 ${lumineux ? 26 : 16}px ${lumineux ? 9 : 5}px ${couleur}66`,
        }}
      />
    </span>
  );
}


export default function TwinNode({ data, selected }) {
  const j = data.jumeau;
  const couleur = couleurDomaine(j?.domaine || data.grappe?.domaine);
  const niveau3 = (data.niveau || 2) >= 3;
  // Fondu croisé continu : 0 = étoile pure, 1 = robot pur (bande z 0.95 → 1.35, centrée sur le seuil)
  const fondu = data.fondu ?? (niveau3 ? 1 : 0);

  // Jumeau hors périmètre : pastille pointillée + résumé au survol uniquement
  if (j?.anonyme) {
    return (
      <div className="group relative" data-testid={`twin-node-${j.id}`}>
        <div className="absolute -top-3 left-1/2 z-50 w-56 -translate-x-1/2 -translate-y-full rounded-lg border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-3 opacity-0 backdrop-blur-xl transition-opacity duration-200 group-hover:opacity-100" data-testid={`anonyme-apercu-${j.id}`}>
          <div className="font-display text-xs font-bold" style={{ color: couleur }}>{j.domaine} — hors périmètre</div>
          <div className="mt-1.5 space-y-0.5 font-code text-[10px] text-[#94A3B8]">
            <div>Domaine voisin non inclus dans votre périmètre.</div>
            <div>Position approximative — la précision n'est pas garantie.</div>
          </div>
          <div className="mt-2 font-code text-[9px] text-[#7C93A8]">Résumé uniquement</div>
        </div>
        <div className={`flex flex-col items-center gap-1 transition-opacity duration-500 ${data.dim ? "opacity-15" : "opacity-45"}`}>
          <Handle type="target" id="t-b" position={Position.Bottom} className="!h-2 !w-2 !min-w-0 !border-0 !bg-transparent" style={{ bottom: -2, left: "46%" }} />
          <Handle type="source" id="s-b" position={Position.Bottom} className="!h-2 !w-2 !min-w-0 !border-0 !bg-transparent" style={{ bottom: -2, left: "46%" }} />
          <PointJumeau couleur={couleur} dashed />
          <span className="rounded bg-[#0F1D28]/70 px-1.5 font-code text-[9px] tracking-wide text-[#94A3B8]">{idNumerique(j.id)}</span>
          <span className="flex items-center gap-1 rounded-full bg-[rgba(148,163,184,0.14)] px-1.5 py-px font-code text-[8px] text-[#7C93A8]">
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
      className={`w-[150px] rounded-lg border border-[rgba(148,163,184,0.16)] bg-[#0F1D28]/95 p-2 shadow-sm ${
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
              className={alerte ? "text-[#F2B84B]" : active ? "text-[#34D399]" : "text-[#41576D]"}
            />
          );
        })}
      </div>
      <div className="mt-1.5 space-y-[3px]" data-testid={`twin-strates-${j.id}`}>
        {STRATES_CLES.map(([cle, initiale]) => (
          <div key={cle} className="flex items-center gap-1" title={`${cle} : ${j.strates[cle]} %`}>
            <span className="w-2.5 shrink-0 font-code text-[7px] uppercase text-[#7C93A8]">{initiale}</span>
            <div className="h-1 flex-1 overflow-hidden rounded-full bg-[rgba(148,163,184,0.14)]">
              <div className="h-full rounded-full" style={{ width: `${j.strates[cle]}%`, backgroundColor: couleurConfiance(j.strates[cle]) }} />
            </div>
            <span className="w-5 shrink-0 text-right font-code text-[7px] text-[#94A3B8]">{j.strates[cle]}</span>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div
      className={`node-deploiement group relative transition-opacity duration-500 ${data.dim ? "opacity-20" : data.adouci ? "opacity-60" : "opacity-100"}`}
      style={{ animationDelay: `${250 + (idNumerique(j.id) % 8) * 55}ms` }}
      data-testid={`twin-node-${j.id}`}
      onClick={(e) => {
        // Maj+clic : multisélection additive gérée ici — la sélection est contrôlée (notre état
        // est la source de vérité), React Flow ne sélectionne pas les nœuds nativement.
        if (e.shiftKey || e.metaKey || e.ctrlKey) {
          e.stopPropagation();
          data.onMajClic?.(j.id);
        }
      }}
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
          {fondu > 0 && (
            <span className="inline-flex" style={fondu < 1 ? { opacity: fondu, transform: `scale(${0.72 + fondu * 0.28})` } : undefined}>
              <AvatarJumeau actif={j.statut === "actif"} selected={selected} grand ports relLiee={data.relLiee} />
            </span>
          )}
          {fondu < 1 && (
            <span
              className={fondu > 0 ? "absolute inset-0 flex items-center justify-center" : "inline-flex"}
              style={fondu > 0 ? { opacity: 1 - fondu, transform: `scale(${1 + fondu * 0.35})` } : undefined}
            >
              <EtoileJumeau couleur={couleur} selected={selected} actif={j.statut === "actif"} relLiee={data.relLiee} sansPorts={fondu > 0} />
            </span>
          )}
          {data.detailPosition === "haut" && carteDetail}
          {data.dansSituation && (
            <span
              className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-[#9B87F5] ring-1 ring-[#071019]"
              title="Impliqué dans une situation active"
              data-testid={`twin-situation-${j.id}`}
            />
          )}
          {data.enTransformation && (
            <span
              className="absolute -left-1 -top-1 h-2.5 w-2.5 rounded-full border-2 border-dashed border-[#F2B84B] bg-[#0F1D28]"
              title="En transformation"
              data-testid={`twin-transformation-${j.id}`}
            />
          )}
        </span>
        <span
          className={`whitespace-nowrap font-code text-[10px] font-semibold tracking-wide text-[#D8E2EA] transition-all duration-200 group-hover:text-[#25D0C8] ${fondu >= 1 ? "" : fondu > 0 ? "pointer-events-none" : "pointer-events-none opacity-0 group-hover:opacity-100"}`}
          style={fondu > 0 && fondu < 1 ? { opacity: fondu } : undefined}
          data-testid={`twin-nom-${j.id}`}
        >
          {idNumerique(j.id)}
        </span>
        {data.detailPosition !== "haut" && carteDetail}
      </div>
    </div>
  );
}
