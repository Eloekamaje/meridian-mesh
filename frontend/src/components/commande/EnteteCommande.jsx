import { ArrowLeft, FloppyDisk } from "@phosphor-icons/react";
import { ETAPES_COMMANDE } from "@/lib/sources";

export default function EnteteCommande({ commande, sauvegarde, onQuitter, onEtape, peutContinuer = true }) {
  const j = commande.jumeau;
  return (
    <div className="border-b border-white/[0.07] px-8 py-4" data-testid="commande-entete">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-4">
          <button onClick={onQuitter} data-testid="commande-quitter-btn" className="flex items-center gap-1.5 rounded-md border border-white/10 px-2.5 py-1.5 text-xs text-white/55 transition-colors hover:text-white" title="Quitter et reprendre plus tard">
            <ArrowLeft size={13} /> Quitter
          </button>
          <div>
            <h1 className="font-display text-xl font-bold text-white" data-testid="commande-titre">Commande du jumeau {j.nom || "…"}</h1>
            <p className="font-code text-[10px] text-white/40">
              {commande.id} · Domaine {j.domaine || "Non classé"} ·{" "}
              {sauvegarde === "encours" ? (
                <span className="text-[#FBBF24]">Enregistrement…</span>
              ) : sauvegarde ? (
                <span className="text-[#10B981]">Brouillon enregistré</span>
              ) : (
                "Brouillon"
              )}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 font-code text-[10px] text-white/40">
          <FloppyDisk size={12} className="text-[#10B981]" /> autosauvegarde active
        </div>
      </div>
      <div className="mt-4 flex items-center gap-1" data-testid="commande-stepper">
        {ETAPES_COMMANDE.map((label, i) => {
          const n = i + 1;
          const accessible = n <= commande.etape || (n === commande.etape + 1 && peutContinuer);
          return (
            <button key={label} onClick={() => accessible && onEtape(n)} disabled={!accessible} data-testid={`etape-nav-${n}`} className="flex flex-1 flex-col gap-1 text-left disabled:cursor-default">
              <div className={`h-0.5 rounded-full transition-colors duration-300 ${n <= commande.etape ? "bg-[#22D3EE]" : "bg-white/10"}`} />
              <span className={`font-code text-[9px] uppercase tracking-wider ${n === commande.etape ? "text-white" : accessible ? "text-white/50 hover:text-white/80" : "text-white/30"}`}>
                {n}. {label}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
