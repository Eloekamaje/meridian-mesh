import { ArrowLeft, FloppyDisk } from "@phosphor-icons/react";
import { ETAPES_COMMANDE } from "@/lib/sources";

export default function EnteteCommande({ commande, sauvegarde, onQuitter, onEtape, peutContinuer = true }) {
  const j = commande.jumeau;
  return (
    <div className="border-b border-[rgba(148,163,184,0.16)] px-8 py-3.5" data-testid="commande-entete">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-4">
          <button onClick={onQuitter} data-testid="commande-quitter-btn" className="flex items-center gap-1.5 rounded-md border border-[rgba(148,163,184,0.16)] px-2.5 py-1.5 text-xs text-[#94A3B8] transition-colors hover:text-[#F2F6F8]" title="Quitter et reprendre plus tard">
            <ArrowLeft size={13} /> Quitter
          </button>
          <div>
            <h1 className="font-display text-xl font-bold tracking-tight text-[#F2F6F8]" data-testid="commande-titre">Commande du jumeau {j.nom || "…"}</h1>
            <p className="font-code text-[10px] text-[#7C93A8]">
              {commande.id} · Domaine {j.domaine || "Non classé"} ·{" "}
              {sauvegarde === "encours" ? (
                <span className="text-[#F2B84B]">Enregistrement…</span>
              ) : sauvegarde ? (
                <span className="text-[#34D399]">Brouillon enregistré</span>
              ) : (
                "Brouillon"
              )}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 font-code text-[10px] text-[#7C93A8]">
          <FloppyDisk size={12} className="text-[#34D399]" /> autosauvegarde active
        </div>
      </div>
      {/* Stepper compact façon fil d'Ariane — libère la hauteur pour la file */}
      <nav className="mt-2.5 flex items-center gap-1 font-code text-[10px]" data-testid="commande-stepper">
        {ETAPES_COMMANDE.map((label, i) => {
          const n = i + 1;
          const accessible = n <= commande.etape || (n === commande.etape + 1 && peutContinuer);
          return (
            <span key={label} className="flex items-center gap-1">
              {i > 0 && <span className="text-[#7C93A8]">›</span>}
              <button
                onClick={() => accessible && onEtape(n)}
                disabled={!accessible}
                data-testid={`etape-nav-${n}`}
                className={`rounded px-1.5 py-0.5 transition-colors ${n === commande.etape ? "bg-[#25D0C8]/10 font-semibold text-[#25D0C8]" : accessible ? "text-[#7C93A8] hover:text-[#F2F6F8]" : "cursor-default text-[#7C93A8]"}`}
              >
                {n}. {label}
              </button>
            </span>
          );
        })}
        <span className="ml-3 hidden h-px flex-1 bg-[rgba(148,163,184,0.10)] sm:block">
          <span className="block h-px bg-[#25D0C8] transition-[width] duration-500" style={{ width: `${(commande.etape / ETAPES_COMMANDE.length) * 100}%` }} />
        </span>
      </nav>
    </div>
  );
}
