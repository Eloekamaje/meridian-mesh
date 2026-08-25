import { Handle, Position } from "@xyflow/react";
import { LockSimple } from "@phosphor-icons/react";
import { couleurDomaine, couleurConfiance, ETATS_RELATION } from "@/lib/domaines";

export default function TwinNode({ data, selected }) {
  const j = data.jumeau;

  if (j.porte) {
    const ap = data.apercuPorte;
    return (
      <div className="group relative" data-testid={`porte-${j.domaine}`}>
        {/* Aperçu avant navigation (savoir où l'on va) */}
        {ap && (
          <div
            className="pointer-events-none absolute -top-3 left-1/2 z-50 w-[230px] -translate-x-1/2 -translate-y-full rounded-lg border border-white/10 bg-black/85 p-3 opacity-0 backdrop-blur-xl transition-opacity duration-200 group-hover:opacity-100"
            data-testid={`porte-apercu-${j.domaine}`}
          >
            <div className="font-display text-xs font-bold" style={{ color: couleurDomaine(j.domaine) }}>{ap.domaine}</div>
            <div className="mt-1.5 space-y-0.5 font-code text-[10px] text-white/55">
              <div>{ap.jumeaux} jumeaux accessibles</div>
              <div>{ap.relations} relation(s) avec {ap.domaineFocus}</div>
              {ap.decouvertes > 0 && <div>{ap.decouvertes} découverte(s) récente(s)</div>}
            </div>
            <div className="mt-2 font-code text-[9px] text-[#22D3EE]">
              {ap.restreint ? "Accès limité — résumé seulement" : "Cliquer pour explorer →"}
            </div>
          </div>
        )}
        <div
          className={`w-[200px] rounded-lg border border-dashed bg-[#0E0E0E]/90 px-3 py-2.5 transition-opacity duration-500 ${data.dim ? "opacity-15" : "opacity-100"}`}
          style={{ borderColor: `${couleurDomaine(j.domaine)}88` }}
        >
          <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-transparent" />
          <div className="flex items-center gap-1.5 font-code text-[10px] font-medium" style={{ color: couleurDomaine(j.domaine) }}>
            {ap?.restreint && <LockSimple size={11} className="shrink-0 text-white/40" />}
            ⇢ {j.nom}
          </div>
          <div className="mt-1 font-code text-[9px] uppercase tracking-[0.18em] text-white/30">
            {ap?.restreint ? "domaine restreint" : "porte externe — cliquer pour explorer"}
          </div>
          <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-transparent" />
        </div>
      </div>
    );
  }

  if (data.voisinRel) {
    const rel = data.voisinRel;
    const etat = ETATS_RELATION[rel.etat] || ETATS_RELATION.confirmee;
    return (
      <div className="group relative" data-testid={`voisin-${j.id}`}>
        {/* Aperçu de la relation au survol */}
        <div
          className="pointer-events-none absolute -top-3 left-1/2 z-50 w-[230px] -translate-x-1/2 -translate-y-full rounded-lg border border-white/10 bg-black/85 p-3 opacity-0 backdrop-blur-xl transition-opacity duration-200 group-hover:opacity-100"
          data-testid={`voisin-hover-${j.id}`}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="font-display text-xs font-bold text-white">{j.nom}</span>
            <span className="shrink-0 font-code text-[9px]" style={{ color: etat.couleur }}>{etat.label}</span>
          </div>
          <div className="mt-1.5 space-y-0.5 font-code text-[10px] text-white/55">
            <div>Relation : {rel.source} → {rel.cible}</div>
            {rel.label && <div>Échangé : {rel.label}</div>}
            {rel.confiance != null && <div>Confiance : <span style={{ color: couleurConfiance(rel.confiance) }}>{rel.confiance} %</span></div>}
            {rel.claims?.length > 0 && <div>{rel.claims.length} claim(s) documentée(s)</div>}
          </div>
          <div className="mt-2 font-code text-[9px] text-[#22D3EE]">Cliquer pour transférer le focus →</div>
        </div>
        <div className="w-[180px] rounded-lg border border-dashed bg-[#0E0E0E]/90 px-3 py-2.5" style={{ borderColor: `${couleurDomaine(j.domaine)}77` }}>
          <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-transparent" />
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: couleurDomaine(j.domaine) }} />
            <span className="truncate font-display text-[12px] font-bold text-white">{j.nom}</span>
          </div>
          <div className="mt-1 font-code text-[9px]" style={{ color: etat.couleur }}>{etat.label}</div>
          <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-transparent" />
        </div>
      </div>
    );
  }

  if (j.anonyme) {
    return (
      <div
        className={`w-[180px] rounded-lg border border-dashed border-white/20 bg-white/[0.02] px-3 py-2.5 transition-opacity duration-500 ${data.dim ? "opacity-20" : "opacity-80"}`}
        data-testid={`twin-node-${j.id}`}
      >
        <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-transparent" />
        <div className="flex items-center gap-2">
          <LockSimple size={13} className="shrink-0 text-white/35" />
          <span className="truncate font-code text-[10px] text-white/45">{j.nom}</span>
        </div>
        <div className="mt-1 font-code text-[9px] uppercase tracking-[0.18em] text-white/25">périmètre restreint</div>
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
        className="pointer-events-none absolute -top-3 left-1/2 z-50 w-[240px] -translate-x-1/2 -translate-y-full rounded-lg border border-white/10 bg-black/85 p-3 opacity-0 shadow-none backdrop-blur-xl transition-opacity duration-200 group-hover:opacity-100"
        data-testid={`twin-hover-${j.id}`}
      >
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: couleur }} />
          <span className="font-display text-xs font-bold text-white">{j.nom}</span>
          <span className="ml-auto font-code text-[9px] uppercase tracking-wider text-white/40">{j.statut}</span>
        </div>
        <p className="mt-1.5 line-clamp-2 text-[11px] leading-snug text-white/60">{j.mission}</p>
        <div className="mt-2 flex items-center justify-between font-code text-[9px] text-white/40">
          <span>Couverture <span className="text-white/80">{j.couverture} %</span></span>
          <span>{j.fraicheur}</span>
        </div>
        <div className="mt-1 h-0.5 overflow-hidden rounded-full bg-white/10">
          <div className="h-full rounded-full" style={{ width: `${j.couverture}%`, backgroundColor: couleur }} />
        </div>
        <div className="mt-2 font-code text-[9px] text-white/30">Cliquer pour le détail complet →</div>
      </div>

      {data.halo && (
        <span className="halo-anim pointer-events-none absolute -inset-3 rounded-xl" style={{ border: `1.5px solid ${couleur}` }} />
      )}
      {data.focusCentral && (
        <span className="pointer-events-none absolute -inset-2 rounded-xl border-2" style={{ borderColor: couleur }} data-testid="twin-focus-ring" />
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
