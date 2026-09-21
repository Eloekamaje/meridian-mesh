import { FloppyDisk } from "@phosphor-icons/react";
import { BoutonRetour } from "@/components/EntetePage";
import { ETAPES_COMMANDE } from "@/lib/sources";

export default function EnteteCommande({ commande, sauvegarde, onQuitter, onEtape, peutContinuer = true }) {
  const j = commande.jumeau;
  return (
    <div className="border-b border-[rgba(148,163,184,0.16)] px-4 py-3 sm:px-8 sm:py-3.5" data-testid="commande-entete">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="flex min-w-0 flex-1 items-center gap-3 sm:gap-4">
          <BoutonRetour label="Quitter" onClick={onQuitter} testid="commande-quitter-btn" />
          <div className="min-w-0">
            <h1 className="font-display text-base font-bold leading-snug tracking-tight text-[#F2F6F8] sm:text-xl" data-testid="commande-titre">Commande du jumeau {j.nom || "…"}</h1>
            <p className="font-code text-[11px] text-[#7C93A8]">
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
        <div className="hidden items-center gap-2 font-code text-[11px] text-[#7C93A8] sm:flex">
          <FloppyDisk size={12} className="text-[#34D399]" /> autosauvegarde active
        </div>
      </div>
      {/* Petit écran : une ligne « Étape 2/4 » plutôt que quatre libellés qui se replient sur 3 lignes */}
      <div className="mt-2 flex items-center gap-2 font-code text-[11px] sm:hidden" data-testid="commande-etape-mobile">
        <span className="rounded bg-[#60A5FA]/10 px-1.5 py-0.5 font-semibold text-[#60A5FA]">Étape {commande.etape}/{ETAPES_COMMANDE.length}</span>
        <span className="truncate text-[#94A3B8]">{ETAPES_COMMANDE[commande.etape - 1]}</span>
        <span className="ml-auto h-1 w-16 overflow-hidden rounded bg-[rgba(148,163,184,0.16)]"><span className="block h-full bg-[#60A5FA]" style={{ width: `${(commande.etape / ETAPES_COMMANDE.length) * 100}%` }} /></span>
      </div>
      {/* Stepper compact façon fil d'Ariane — libère la hauteur pour la file */}
      <nav className="mt-2.5 hidden items-center gap-1 font-code text-[11px] sm:flex" data-testid="commande-stepper">
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
                className={`rounded px-1.5 py-0.5 transition-colors ${n === commande.etape ? "bg-[#60A5FA]/10 font-semibold text-[#60A5FA]" : accessible ? "text-[#7C93A8] hover:text-[#F2F6F8]" : "cursor-default text-[#7C93A8]"}`}
              >
                {n}. {label}
              </button>
            </span>
          );
        })}
        <span className="ml-3 hidden h-px flex-1 bg-[rgba(148,163,184,0.10)] sm:block">
          <span className="block h-px bg-[#60A5FA] transition-[width] duration-500" style={{ width: `${(commande.etape / ETAPES_COMMANDE.length) * 100}%` }} />
        </span>
      </nav>
    </div>
  );
}
