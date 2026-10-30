import { useEffect, useRef, useState } from "react";
import { FileText, SpinnerGap, X } from "@phosphor-icons/react";
import api from "@/lib/api";

// La section source d'une pièce citée par Flore (`pièce:<id>#<section>`) : le panneau la lit au serveur,
// qui vérifie déjà l'accès au Travail et à la pièce. Il ne modifie rien et ne promet aucune action :
// seulement le nom de la pièce, le titre de la section, son texte et l'état de troncature.
export default function PanneauPiece({ casId, pieceId, sectionId, onFermer }) {
  const [section, setSection] = useState(null); // null : en cours ; { nom, titre, texte, tronque… }
  const [erreur, setErreur] = useState(null);
  const fermer = useRef(null);
  const panneau = useRef(null);
  const declencheur = useRef(null);

  useEffect(() => {
    if (!casId || !pieceId || !sectionId) return undefined;
    let actif = true;
    setSection(null);
    setErreur(null);
    // Segments encodés : un identifiant ne doit jamais changer la forme de l'URL (ni ajouter de chemin).
    api.get(`/cases/${encodeURIComponent(casId)}/pieces/${encodeURIComponent(pieceId)}/sections/${encodeURIComponent(sectionId)}`)
      .then(({ data }) => { if (actif) setSection(data); })
      .catch((e) => { if (actif) setErreur(e.response?.data?.detail || "Section introuvable"); });
    return () => { actif = false; };
  }, [casId, pieceId, sectionId]);

  // Le focus revient au déclencheur à la fermeture — jamais perdu sur <body> après le démontage du panneau.
  useEffect(() => {
    declencheur.current = document.activeElement;
    return () => { declencheur.current?.focus?.(); };
  }, []);
  // Le focus ne revient qu'à l'ouverture d'une nouvelle section, pas à chaque rendu du fil pendant
  // que Flore écrit (le rappel de fermeture, lui, peut changer sans voler le focus).
  useEffect(() => { fermer.current?.focus(); }, [casId, pieceId, sectionId]);
  useEffect(() => {
    const touche = (e) => { if (e.key === "Escape") onFermer?.(); };
    window.addEventListener("keydown", touche);
    return () => window.removeEventListener("keydown", touche);
  }, [onFermer]);

  // Piège de focus simple : Tab/Shift+Tab restent dans le panneau tant qu'il est modal.
  const garderFocus = (e) => {
    if (e.key !== "Tab") return;
    const racine = panneau.current;
    if (!racine) return;
    const focusables = [...racine.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')]
      .filter((el) => !el.disabled && el.tabIndex !== -1);
    if (!focusables.length) { e.preventDefault(); return; }
    const premier = focusables[0];
    const dernier = focusables[focusables.length - 1];
    const dedans = racine.contains(document.activeElement);
    if (e.shiftKey && (!dedans || document.activeElement === premier)) { e.preventDefault(); dernier.focus(); }
    else if (!e.shiftKey && (!dedans || document.activeElement === dernier)) { e.preventDefault(); premier.focus(); }
  };

  if (!casId || !pieceId || !sectionId) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-[#04090F]/60 backdrop-blur-sm" onClick={onFermer}>
      <aside
        ref={panneau}
        role="dialog"
        aria-modal="true"
        aria-labelledby="panneau-piece-titre"
        data-testid="panneau-piece"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={garderFocus}
        className="flex h-full w-full max-w-md flex-col border-l border-white/[0.12] bg-[#0C1724]/95 shadow-2xl backdrop-blur-xl"
      >
        <header className="flex items-start justify-between gap-3 border-b border-white/[0.08] px-5 py-4">
          <div className="flex min-w-0 items-start gap-2.5">
            <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#60A5FA]/15 text-[#93C5FD]">
              <FileText size={15} />
            </span>
            <div className="min-w-0">
              <div className="font-code text-[9px] uppercase tracking-[0.22em] text-[#58A6FF]">Pièce jointe · section</div>
              <h3 id="panneau-piece-titre" className="mt-1 truncate font-display text-sm font-bold text-[#F2F6F8]" data-testid="panneau-piece-nom">
                {section?.nom || pieceId}
              </h3>
              <p className="mt-0.5 truncate font-code text-[11px] text-[#94A3B8]" data-testid="panneau-piece-titre">
                {section?.titre || `Section ${sectionId}`}
              </p>
            </div>
          </div>
          <button
            ref={fermer}
            type="button"
            onClick={onFermer}
            aria-label="Fermer la section"
            data-testid="panneau-piece-fermer"
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-white/[0.12] bg-[#07111B] text-[#94A3B8] transition-colors hover:border-white/30 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#60A5FA]"
          >
            <X size={15} />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {!section && !erreur && (
            <div className="flex items-center gap-2 font-code text-[11px] text-[#7C93A8]" data-testid="panneau-piece-chargement">
              <SpinnerGap size={14} className="animate-spin" />
              Lecture de la section…
            </div>
          )}

          {erreur && (
            <p className="rounded-lg border border-[#F87171]/30 bg-[#F87171]/[0.06] px-3 py-2 text-xs leading-relaxed text-[#FCA5A5]" data-testid="panneau-piece-erreur">
              {erreur}
            </p>
          )}

          {section && (
            <>
              <div className="rounded-lg border-l-2 border-[#60A5FA] bg-[#071019] p-3" data-testid="panneau-piece-texte">
                <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-[#D8E2EA]">
                  {section.texte || "Cette section ne contient pas de texte."}
                </p>
              </div>
              {section.tronque && (
                <p className="mt-2 font-code text-[10px] leading-relaxed text-[#F2B84B]" data-testid="panneau-piece-tronque">
                  Extrait tronqué — la section complète reste dans la pièce.
                </p>
              )}
              <p className="mt-3 break-all font-code text-[10px] text-[#526578]">{section.citation || `pièce:${pieceId}#${sectionId}`}</p>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
