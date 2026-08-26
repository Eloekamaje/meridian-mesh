import { Users, ShieldCheck, LockSimple, Sparkle } from "@phosphor-icons/react";
import { usePerimetre } from "@/lib/perimetre";
import { useContexte } from "@/lib/contexte";

const POLITIQUES = {
  masquage: "masquage complet",
  anonymisee: "dépendance anonymisée",
  resume: "résumé autorisé",
};

export default function Topbar() {
  const { personas, persona, espaces, vues, cible, info, changerPersona, changerCible } = usePerimetre();
  const { selection, floreOuverte, basculerFlore } = useContexte();

  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b border-white/[0.08] bg-[#0A0A0A] px-4" data-testid="topbar">
      <span className="font-code text-[9px] uppercase tracking-[0.25em] text-white/35">Périmètre</span>
      <select
        value={cible}
        onChange={(e) => changerCible(e.target.value)}
        data-testid="selecteur-perimetre"
        className="rounded-md border border-white/10 bg-black/60 px-2.5 py-1.5 text-xs font-semibold text-white focus:border-[#22D3EE]/60 focus:outline-none"
      >
        <optgroup label="Espaces">
          {espaces.map((e) => (
            <option key={e.id} value={e.id} label={e.global ? `${e.label} (autorisé)` : e.label} />
          ))}
        </optgroup>
        {vues.length > 0 && (
          <optgroup label="Vues enregistrées">
            {vues.map((v) => (
              <option key={v.id} value={`vue:${v.id}`} label={`Vue — ${v.nom}`} />
            ))}
          </optgroup>
        )}
      </select>

      {info && (
        <span
          className="hidden items-center gap-1.5 rounded border px-2 py-1 font-code text-[9px] uppercase tracking-wider md:inline-flex"
          style={
            info.espace.global
              ? { color: "#34D399", borderColor: "#34D39944", backgroundColor: "#34D3990D" }
              : { color: "#FBBF24", borderColor: "#FBBF2444", backgroundColor: "#FBBF240D" }
          }
          data-testid="perimetre-badge"
        >
          {info.espace.global ? <ShieldCheck size={12} /> : <LockSimple size={12} />}
          {info.espace.global
            ? "Vue complète du périmètre autorisé"
            : `Filtré côté serveur · ${info.nb_autorises} jumeaux · ${POLITIQUES[info.espace.politique_dependances] || ""}`}
        </span>
      )}

      <div className="ml-auto flex items-center gap-2">
        <button
          onClick={basculerFlore}
          data-testid="flore-btn"
          title="Ouvrir Flore (⌘K)"
          className={`flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs font-semibold transition-colors ${
            floreOuverte
              ? "border-[#3B82F6]/60 bg-[#3B82F6]/15 text-white"
              : "border-white/10 text-white/70 hover:border-[#3B82F6]/50 hover:text-white"
          }`}
        >
          <Sparkle size={13} weight="fill" className="text-[#3B82F6]" />
          Flore
          {selection.length > 0 && (
            <span className="rounded-full bg-[#3B82F6]/25 px-1.5 font-code text-[9px] text-white" data-testid="flore-btn-badge">
              {selection.length}
            </span>
          )}
        </button>
        <Users size={14} className="text-white/40" />
        <select
          value={persona}
          onChange={(e) => changerPersona(e.target.value)}
          data-testid="selecteur-persona"
          className="rounded-md border border-white/10 bg-black/60 px-2.5 py-1.5 text-xs text-white/80 focus:outline-none"
        >
          {personas.map((p) => (
            <option key={p.id} value={p.id} label={`${p.nom} — ${p.role}`} />
          ))}
        </select>
      </div>
    </header>
  );
}
