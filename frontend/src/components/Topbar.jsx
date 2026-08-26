import { Users, ShieldCheck, LockSimple } from "@phosphor-icons/react";
import { usePerimetre } from "@/lib/perimetre";

const POLITIQUES = {
  masquage: "masquage complet",
  anonymisee: "dépendance anonymisée",
  resume: "résumé autorisé",
};

export default function Topbar() {
  const { personas, persona, espaces, vues, cible, info, changerPersona, changerCible } = usePerimetre();

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
