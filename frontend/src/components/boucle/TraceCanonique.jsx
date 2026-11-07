import { ArrowRight } from "@phosphor-icons/react";

const texte = (valeur) => (valeur == null ? "" : String(valeur));

function typeEtape(etape) {
  if (!etape || typeof etape !== "object") return "";
  return texte(etape.type || etape.donnees?.type).trim().toUpperCase();
}

function titreEtape(etape) {
  if (etape == null) return "Étape sans titre";
  if (typeof etape === "string") return etape;
  return texte(etape.titre)
    || texte(etape.id)
    || texte(etape.objet_id)
    || "Étape sans titre";
}

export default function TraceCanonique({ trace, className = "" }) {
  if (!trace || (!trace.id && (!Array.isArray(trace.chaine) || trace.chaine.length === 0))) {
    return null;
  }

  const chaine = Array.isArray(trace.chaine) ? trace.chaine : [];

  return (
    <section
      className={`shrink-0 border-b border-white/[0.06] bg-[#08131E] px-6 py-2 ${className}`}
      aria-label="Trace canonique de la boucle"
      data-testid="travail-boucle-trace"
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="font-code text-[9px] uppercase tracking-[0.2em] text-[#7C93A8]">
          Boucle canonique
        </span>
        {trace.id && (
          <span className="flex min-w-0 items-center gap-1.5">
            <span className="font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">ID</span>
            <code
              className="truncate font-code text-[10px] text-[#BFDBFE]"
              title={trace.id}
              data-testid="travail-boucle-id"
            >
              {trace.id}
            </code>
          </span>
        )}
        {trace.statut && (
          <span
            className="rounded border border-[#60A5FA]/35 bg-[#60A5FA]/[0.08] px-1.5 py-px font-code text-[9px] uppercase tracking-wider text-[#93C5FD]"
            data-testid="travail-boucle-statut"
          >
            {trace.statut}
          </span>
        )}
      </div>

      {chaine.length > 0 ? (
        <ol className="mt-1.5 flex flex-wrap items-center gap-1" data-testid="travail-boucle-chaine">
          {chaine.map((etape, index) => (
            <li
              key={`${titreEtape(etape)}-${index}`}
              className="flex min-w-0 items-center gap-1"
              data-testid="travail-boucle-etape"
            >
              {typeEtape(etape) && (
                <span className="font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">
                  {typeEtape(etape)}
                </span>
              )}
              <span className="max-w-[16rem] truncate text-[10px] text-[#CBD5E1]" title={titreEtape(etape)}>
                {titreEtape(etape)}
              </span>
              {index < chaine.length - 1 && (
                <ArrowRight size={9} aria-hidden="true" className="shrink-0 text-[#7C93A8]" />
              )}
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-1 font-code text-[10px] text-[#7C93A8]" data-testid="travail-boucle-chaine-vide">
          Chaîne canonique non disponible.
        </p>
      )}
    </section>
  );
}
