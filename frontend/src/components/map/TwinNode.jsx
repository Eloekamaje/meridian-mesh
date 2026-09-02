import { Handle, Position } from "@xyflow/react";
import { LockSimple } from "@phosphor-icons/react";
import { couleurDomaine, couleurConfiance, ETATS_RELATION } from "@/lib/domaines";

// Symbole du jumeau : deux cercles concentriques — l'application et son reflet numérique
function PointJumeau({ couleur, actif, selected, degrade, dashed }) {
  return (
    <span className="relative flex h-4 w-4 shrink-0 items-center justify-center">
      {actif && (
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-40" style={{ backgroundColor: couleur }} />
      )}
      <span
        className={`relative inline-flex h-4 w-4 items-center justify-center rounded-full border-2 bg-white ${dashed ? "border-dashed" : ""}`}
        style={{
          borderColor: couleur,
          boxShadow: selected || degrade ? `0 0 14px ${couleur}55` : "0 1px 3px rgba(17,17,16,0.15)",
        }}
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
      <div className="group relative" data-testid={`porte-${j.domaine}`}>
        {ap && (
          <div
            className="pointer-events-none absolute -top-3 left-1/2 z-50 w-[230px] -translate-x-1/2 -translate-y-full rounded-lg border border-[#E5E5E3] bg-white p-3 opacity-0 backdrop-blur-xl transition-opacity duration-200 group-hover:opacity-100"
            data-testid={`porte-apercu-${j.domaine}`}
          >
            <div className="font-display text-xs font-bold" style={{ color: c }}>{ap.domaine}</div>
            <div className="mt-1.5 space-y-0.5 font-code text-[10px] text-[#52524F]">
              <div>{ap.jumeaux} jumeaux accessibles</div>
              <div>{ap.relations} relation(s) avec {ap.domaineFocus}</div>
              {ap.decouvertes > 0 && <div>{ap.decouvertes} découverte(s) récente(s)</div>}
            </div>
            <div className="mt-2 font-code text-[9px] text-[#0E7490]">
              {ap.restreint ? "Accès limité — résumé seulement" : "Cliquer pour explorer →"}
            </div>
          </div>
        )}
        <div className={`flex items-center gap-2 transition-opacity duration-500 ${data.dim ? "opacity-15" : "opacity-100"}`}>
          <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-transparent" />
          <PointJumeau couleur={c} dashed />
          <div>
            <div className="flex items-center gap-1.5 text-[12px] font-semibold" style={{ color: c }}>
              {ap?.restreint && <LockSimple size={11} className="shrink-0 text-[#71716D]" />}
              ⇢ {j.nom}
            </div>
            <div className="font-code text-[8px] uppercase tracking-[0.18em] text-[#71716D]">
              {ap?.restreint ? "domaine restreint" : "porte externe"}
            </div>
          </div>
          <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-transparent" />
        </div>
      </div>
    );
  }

  if (data.voisinRel) {
    const rel = data.voisinRel;
    const etat = ETATS_RELATION[rel.etat] || ETATS_RELATION.confirmee;
    const c = couleurDomaine(j.domaine);
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
        <div className="flex items-center gap-2">
          <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-transparent" />
          <PointJumeau couleur={c} />
          <div>
            <div className="text-[12px] font-semibold text-[#111110]">{j.nom}</div>
            <div className="font-code text-[8px] uppercase tracking-[0.15em]" style={{ color: etat.couleur }}>{etat.label}</div>
          </div>
          <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-transparent" />
        </div>
      </div>
    );
  }

  if (j.anonyme) {
    return (
      <div
        className={`flex items-center gap-2 transition-opacity duration-500 ${data.dim ? "opacity-20" : "opacity-75"}`}
        data-testid={`twin-node-${j.id}`}
      >
        <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-transparent" />
        <PointJumeau couleur="#A3A39E" dashed />
        <div>
          <div className="flex items-center gap-1.5 font-code text-[10px] text-[#71716D]">
            <LockSimple size={11} className="shrink-0" /> {j.nom}
          </div>
          <div className="font-code text-[8px] uppercase tracking-[0.18em] text-[#71716D]">périmètre restreint</div>
        </div>
        <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-transparent" />
      </div>
    );
  }

  const couleur = couleurDomaine(j.domaine);
  const degrade = j.sante === "dégradé";
  const actif = j.statut === "actif";

  return (
    <div
      className={`group relative transition-opacity duration-500 ${data.dim ? "opacity-20" : "opacity-100"}`}
      data-testid={`twin-node-${j.id}`}
    >
      {/* Aperçu au survol */}
      <div
        className="pointer-events-none absolute -top-3 left-1/2 z-50 w-[240px] -translate-x-1/2 -translate-y-full rounded-lg border border-[#E5E5E3] bg-white p-3 opacity-0 shadow-none backdrop-blur-xl transition-opacity duration-200 group-hover:opacity-100"
        data-testid={`twin-hover-${j.id}`}
      >
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: couleur }} />
          <span className="font-display text-xs font-bold text-[#111110]">{j.nom}</span>
          <span className="ml-auto font-code text-[9px] uppercase tracking-wider text-[#71716D]">{j.statut}</span>
        </div>
        <p className="mt-1.5 line-clamp-2 text-[11px] leading-snug text-[#52524F]">{j.mission}</p>
        <div className="mt-2 flex items-center justify-between font-code text-[9px] text-[#71716D]">
          <span>Couverture <span className="text-[#3F3F3C]">{j.couverture} %</span></span>
          <span>{j.fraicheur}</span>
        </div>
        <div className="mt-1 h-0.5 overflow-hidden rounded-full bg-[#E5E5E3]">
          <div className="h-full rounded-full" style={{ width: `${j.couverture}%`, backgroundColor: couleur }} />
        </div>
        <div className="mt-2 font-code text-[9px] text-[#71716D]">Cliquer pour le détail complet →</div>
      </div>

      {data.halo && (
        <span className="halo-anim pointer-events-none absolute -inset-2 rounded-full" style={{ border: `1.5px solid ${couleur}` }} />
      )}
      {data.focusCentral && (
        <span className="pointer-events-none absolute -inset-1.5 rounded-full border-2" style={{ borderColor: couleur }} data-testid="twin-focus-ring" />
      )}

      <div className="flex items-center gap-2">
        <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-transparent" />
        <PointJumeau couleur={couleur} actif={actif} selected={selected} degrade={degrade} />
        <div>
          <div className="flex items-center gap-1.5">
            <span className="whitespace-nowrap text-[13px] font-semibold leading-tight text-[#111110]">{j.nom}</span>
            {data.evenements > 0 && (
              <span className="shrink-0 rounded-full bg-[#E5E5E3] px-1.5 py-0.5 font-code text-[9px] text-[#3F3F3C]">
                +{data.evenements}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            <span className="font-code text-[8px] uppercase tracking-[0.18em] text-[#71716D]">{j.domaine}</span>
            {data.etape != null && <span className="font-code text-[9px] text-[#52524F]">étape {data.etape}</span>}
            {j.statut !== "actif" && <span className="font-code text-[9px] text-[#B45309]">{j.statut}</span>}
          </div>
        </div>
        <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-transparent" />
      </div>
    </div>
  );
}
