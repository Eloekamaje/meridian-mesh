import { useState } from "react";
import { X, FileText, Copy, ArrowsOut, ArrowsIn, Check, DownloadSimple } from "@phosphor-icons/react";
import { toast } from "sonner";
import { RenduMarkdown } from "@/lib/renduMarkdown";

// Document de repli hors démonstration : aucun document réel n'existe encore tant que la création
// de travail par conversation n'est pas active (voir messagesFlore.js::CREATION_TRAVAIL_ACTIVE).
const CONTENU_REPLI = `# Document de démonstration

Ce document illustre la mise en page du Canvas. Un vrai travail y publiera son propre contenu.`;

export default function CanvasDocument({
  titre = "document.md",
  contenu = CONTENU_REPLI,
  onFermer,
}) {
  const [pleinEcran, setPleinEcran] = useState(false);
  const [copie, setCopie] = useState(false);

  const copierDocument = () => {
    navigator.clipboard?.writeText(contenu);
    setCopie(true);
    toast.success("Document copié dans le presse-papier");
    setTimeout(() => setCopie(false), 2000);
  };

  const telechargerDocument = () => {
    const nom = /\.[a-z0-9]+$/i.test(titre) ? titre : `${titre}.md`;
    const url = URL.createObjectURL(new Blob([contenu], { type: "text/markdown;charset=utf-8" }));
    const lien = document.createElement("a");
    lien.href = url;
    lien.download = nom;
    lien.click();
    URL.revokeObjectURL(url);
    toast.success("Téléchargement lancé");
  };

  return (
    <div
      className={`flex h-full w-full flex-col border-l border-white/[0.1] bg-[#0A1520] shadow-2xl transition-all duration-300 ${
        pleinEcran ? "fixed inset-0 z-50 bg-[#071019]" : ""
      }`}
      data-testid="canvas-document"
    >
      {/* En-tête du volet Canvas — fidèle à l'esthétique ChatGPT Canvas */}
      <div className="flex items-center justify-between border-b border-white/[0.08] bg-[#0D1A27] px-4 py-3">
        <div className="flex min-w-0 items-center gap-2 font-code text-xs">
          <span className="text-[#64748B]">Bibliothèque /</span>
          <span className="truncate font-semibold text-[#F2F6F8]">{titre}</span>
          <span className="ml-1 shrink-0 rounded bg-[#60A5FA]/20 px-1.5 py-0.5 text-[9px] font-semibold text-[#60A5FA]">
            Document généré
          </span>
        </div>

        {/* Outils d'action : Copier, Télécharger, Plein écran, Fermer */}
        <div className="flex shrink-0 items-center gap-1.5">
          <button
            onClick={copierDocument}
            className="flex h-7 items-center gap-1.5 rounded-lg border border-white/[0.12] bg-[#07111B] px-2.5 font-code text-[11px] text-[#94A3B8] transition-colors hover:border-white/30 hover:text-white"
            title="Copier le document"
            data-testid="btn-copier-doc"
          >
            {copie ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
            <span>{copie ? "Copié" : "Copier"}</span>
          </button>

          <button
            onClick={telechargerDocument}
            className="flex h-7 items-center gap-1.5 rounded-lg border border-white/[0.12] bg-[#07111B] px-2.5 font-code text-[11px] text-[#94A3B8] transition-colors hover:border-white/30 hover:text-white"
            title="Télécharger le document"
            data-testid="btn-telecharger-doc"
          >
            <DownloadSimple size={13} />
            <span>Télécharger</span>
          </button>

          <button
            onClick={() => setPleinEcran(!pleinEcran)}
            className="flex h-7 w-7 items-center justify-center rounded-lg border border-white/[0.12] bg-[#07111B] text-[#94A3B8] transition-colors hover:border-white/30 hover:text-white"
            title={pleinEcran ? "Réduire l'affichage" : "Plein écran"}
            data-testid="btn-plein-ecran-canvas"
          >
            {pleinEcran ? <ArrowsIn size={14} /> : <ArrowsOut size={14} />}
          </button>

          {onFermer && (
            <button
              onClick={onFermer}
              className="flex h-7 w-7 items-center justify-center rounded-lg border border-white/[0.12] bg-[#07111B] text-[#94A3B8] transition-colors hover:border-white/30 hover:text-white"
              title="Fermer le Canvas"
              data-testid="btn-fermer-canvas"
            >
              <X size={15} />
            </button>
          )}
        </div>
      </div>

      {/* Contenu Markdown — rendu générique, propre à CE document (voir lib/renduMarkdown.jsx) */}
      <div className="relative flex-1 overflow-y-auto px-8 py-7">
        <div className="mx-auto max-w-2xl">
          <div className="mb-5 flex items-center gap-2 border-b border-white/[0.1] pb-4">
            <FileText size={16} className="text-[#60A5FA]" />
            <span className="font-code text-[10px] uppercase tracking-wider text-[#7C93A8]">Document généré par Flore</span>
          </div>
          <RenduMarkdown texte={contenu} />
        </div>
      </div>
    </div>
  );
}
