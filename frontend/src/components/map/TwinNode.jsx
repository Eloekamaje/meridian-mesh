import { Handle, Position } from "@xyflow/react";
import { LockSimple } from "@phosphor-icons/react";
import { couleurDomaine, couleurConfiance, ETATS_RELATION } from "@/lib/domaines";
import { idNumerique } from "@/lib/atlasGraph";

const ROBOT = "/assets/robot-jumeau.jpg";

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
      <Handle type="target" id="t-b" position={Position.Bottom} className={cls} style={{ bottom: -2, left: "46%" }} />
      <Handle type="source" id="s-b" position={Position.Bottom} className={cls} style={{ bottom: -2, left: "46%" }} />
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
      <Handle type="target" id="t-b" position={Position.Bottom} className={cls} style={{ bottom: -2, left: 7 }} />
      <Handle type="source" id="s-b" position={Position.Bottom} className={cls} style={{ bottom: -2, left: 7 }} />
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

  if (j.porte) {
    const ap = data.apercuPorte;
    const c = couleurDomaine(j.domaine);
    return (
      <div className="group relative" data-testid={j.id}>
        {ap && (
          <div
            className="pointer-events-none absolute -top-3 left-1/2 z-50 w-[230px] -translate-x-1/2 -translate-y-full rounded-lg border border-[#E5E5E3] bg-white p-3 opacity-0 backdrop-blur-xl transition-opacity duration-200 group-hover:opacity-100"
            data-testid={`apercu-${j.id}`}
          >
            <div className="font-display text-xs font-bold" style={{ color: c }}>{ap.domaine}</div>
            <div className="mt-1.5 space-y-0.5 font-code text-[10px] text-[#52524F]">
              <div>{ap.jumeaux} jumeaux accessibles</div>
              <div>{ap.relations} relation(s) avec {ap.domaineFocus}</div>
              {ap.decouvertes > 0 && <div>{ap.decouvertes} découverte(s) récente(s)</div>}
            </div>
            <div className="mt-2 font-code text-[9px] text-[#0E7490]">
              {ap.restreint ? "Accès limité — résumé seulement" : "Clic : chemin · Double-clic : explorer →"}
            </div>
          </div>
        )}
        <div className={`flex flex-col items-center gap-0.5 transition-opacity duration-500 ${data.dim ? "opacity-15" : "opacity-100"}`}>
          <PointJumeau couleur={c} dashed />
          {/* Porte externe : connecteur compact en périphérie — nom du domaine cible + compteur */}
          <div className="flex items-center gap-1.5 whitespace-nowrap rounded-full border border-[#E5E5E3] bg-white/85 px-2 py-0.5">
            {ap?.restreint && <LockSimple size={10} className="shrink-0 text-[#71716D]" />}
            <span className="font-code text-[10px] font-semibold uppercase tracking-[0.12em]" style={{ color: c }}>{ap?.domaine || j.nom}</span>
            <span className="font-code text-[9px] text-[#71716D]">· {ap?.relations ?? 0}</span>
          </div>
        </div>
      </div>
    );
  }

  if (data.voisinRel) {
    const rel = data.voisinRel;
    const etat = ETATS_RELATION[rel.etat] || ETATS_RELATION.confirmee;
    return (
      <div className="group relative" data-testid={`voisin-${j.id}`}>
        <div
          className="pointer-events-none absolute -top-3 left-1/2 z-50 w-[230px] -translate-x-1/2 -translate-y-full rounded-lg border border-[#E5E5E3] bg-white p-3 opacity-0 backdrop-blur-xl transition-opacity duration-200 group-hover:opacity-100"
          data-testid={`voisin-hover-${j.id}`}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="font-display text-xs font-bold text-[#111110]">{j.nom}</span>
            <span className="shrink-0 font-code text-[9px]" style={{ color: etat.couleur }}>{etat.label}</span>
          </div>
          <div className="mt-1.5 space-y-0.5 font-code text-[10px] text-[#52524F]">
            <div>Relation : {rel.source} → {rel.cible}</div>
            {rel.label && <div>Échangé : {rel.label}</div>}
            {rel.confiance != null && <div>Confiance : <span style={{ color: couleurConfiance(rel.confiance) }}>{rel.confiance} %</span></div>}
            {rel.claims?.length > 0 && <div>{rel.claims.length} claim(s) documentée(s)</div>}
          </div>
          <div className="mt-2 font-code text-[9px] text-[#0E7490]">Cliquer pour transférer le focus →</div>
        </div>
        <div className="flex flex-col items-center gap-0.5">
          <span className="font-code text-[10px] font-semibold text-[#3F3F3C]">{idNumerique(j.id)}</span>
          <AvatarJumeau actif={j.statut === "actif"} />
          <div className="whitespace-nowrap font-code text-[8px] uppercase tracking-[0.15em]" style={{ color: etat.couleur }}>{etat.label}</div>
        </div>
      </div>
    );
  }

  if (j.anonyme) {
    return (
      <div
        className={`flex flex-col items-center gap-0.5 transition-opacity duration-500 ${data.dim ? "opacity-20" : "opacity-75"}`}
        data-testid={`twin-node-${j.id}`}
      >
        <PointJumeau couleur="#A3A39E" dashed />
        <div className="text-center">
          <div className="flex items-center justify-center gap-1.5 whitespace-nowrap font-code text-[10px] text-[#71716D]">
            <LockSimple size={11} className="shrink-0" /> {j.nom}
          </div>
          <div className="font-code text-[8px] uppercase tracking-[0.18em] text-[#71716D]">périmètre restreint</div>
        </div>
      </div>
    );
  }

  const couleur = couleurDomaine(j.domaine);
  const niveau3 = (data.niveau || 2) >= 3;

  // Jumeau = identifiant numérique + robot (le nom complet apparaît au niveau 3 — applications & flux)
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
      <div className="flex flex-col items-center gap-0.5">
        <span className="flex items-center gap-1 font-code text-[10px] font-semibold tracking-wide text-[#3F3F3C] transition-colors group-hover:text-[#0E7490]">
          {idNumerique(j.id)}
          {data.evenements > 0 && (
            <span
              title={`${data.evenements} événement${data.evenements > 1 ? "s" : ""} récent${data.evenements > 1 ? "s" : ""} observé${data.evenements > 1 ? "s" : ""} par le Mesh`}
              className="rounded-full bg-[#E5E5E3] px-1 py-px font-code text-[8px] text-[#3F3F3C]"
            >
              +{data.evenements}
            </span>
          )}
        </span>
        <AvatarJumeau actif={j.statut === "actif"} selected={selected} grand={niveau3} ports={niveau3} relLiee={data.relLiee} />
        {niveau3 && (
          <span className="whitespace-nowrap text-[11px] font-semibold text-[#111110]" data-testid={`twin-nom-${j.id}`}>{j.nom}</span>
        )}
      </div>
    </div>
  );
}
