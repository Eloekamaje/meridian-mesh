import { useRef, useState } from "react";
import { X, FileText, Copy, ArrowsOut, ArrowsIn, Check, DownloadSimple, FloppyDisk } from "@phosphor-icons/react";
import { toast } from "sonner";
import MarkdownFlore from "@/components/MarkdownFlore";
import ArtefactPlanification from "@/components/ArtefactPlanification";
import api from "@/lib/api";

// Repli visuel uniquement : un Travail réel ouvre ses livrables (case.livrables) depuis le volet Résultats.
const CONTENU_REPLI = `# Aucun document ouvert

Choisissez un livrable dans « Résultats » pour l'afficher ici.`;

function Tableau({ artefact }) {
  const colonnes = artefact.colonnes || Object.keys((artefact.lignes || [])[0] || {});
  const lignes = artefact.lignes || [];
  return (
    <div className="overflow-x-auto rounded-lg border border-white/[0.08]">
      <table className="w-full border-collapse text-left text-xs text-[#DCE6EE]">
        <thead className="bg-white/[0.04] font-code text-[10px] uppercase tracking-wider text-[#7C93A8]">
          <tr>{colonnes.map((c) => <th key={c} className="px-3 py-2">{c}</th>)}</tr>
        </thead>
        <tbody>
          {lignes.map((ligne, i) => (
            <tr key={i} className="border-t border-white/[0.06]">
              {colonnes.map((c) => <td key={c} className="px-3 py-2">{Array.isArray(ligne) ? ligne[colonnes.indexOf(c)] : ligne[c]}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ContenuArtefact({ artefact }) {
  if (!artefact) return <MarkdownFlore texte={CONTENU_REPLI} />;
  if (artefact.type === "svg") {
    const data = `data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(artefact.svg || "")))}`;
    return <img src={data} alt={artefact.titre || "Diagramme"} className="max-h-[70vh] w-full object-contain" />;
  }
  if (String(artefact.type || "").startsWith("planification.")) return <ArtefactPlanification artefact={artefact} />;
  if (artefact.type === "mermaid") return <MarkdownFlore texte={"```mermaid\n" + (artefact.code || artefact.contenu || "") + "\n```"} />;
  if (artefact.type === "markdown" || artefact.type === "document") return <MarkdownFlore texte={artefact.contenu || artefact.texte || ""} />;
  if (artefact.type === "table") return <Tableau artefact={artefact} />;
  if (artefact.type === "json") return <pre className="overflow-auto rounded-lg bg-[#071019] p-3 font-code text-[11px] text-[#94A3B8]">{JSON.stringify(artefact.donnees ?? artefact, null, 2)}</pre>;
  return <pre className="overflow-auto rounded-lg bg-[#071019] p-3 font-code text-[11px] text-[#94A3B8]">{JSON.stringify(artefact, null, 2)}</pre>;
}

export default function CanvasDocument({
  titre = "document.md",
  contenu = CONTENU_REPLI,
  artefact = null,
  onFermer,
}) {
  const [pleinEcran, setPleinEcran] = useState(false);
  const [copie, setCopie] = useState(false);
  const contenuRef = useRef(null);

  const exporterSvg = () => {
    if (artefact?.type === "svg") {
      const url = URL.createObjectURL(new Blob([artefact.svg || ""], { type: "image/svg+xml;charset=utf-8" }));
      const lien = document.createElement("a");
      lien.href = url;
      lien.download = /\.[a-z0-9]+$/i.test(titre) ? titre.replace(/\.[a-z0-9]+$/i, ".svg") : `${titre}.svg`;
      lien.click();
      URL.revokeObjectURL(url);
      return;
    }
    const svg = contenuRef.current?.querySelector("svg");
    if (!svg) {
      toast.error("Aucun SVG exportable dans cet artefact");
      return;
    }
    const clone = svg.cloneNode(true);
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)],
      { type: "image/svg+xml;charset=utf-8" }));
    const lien = document.createElement("a");
    lien.href = url;
    lien.download = /\.[a-z0-9]+$/i.test(titre) ? titre.replace(/\.[a-z0-9]+$/i, ".svg") : `${titre}.svg`;
    lien.click();
    URL.revokeObjectURL(url);
  };

  const enregistrerArtefact = async () => {
    if (!artefact) return;
    try {
      await api.post("/planification/artefacts", artefact);
      toast.success("Artefact enregistré");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Enregistrement impossible");
    }
  };

  const copierDocument = () => {
    navigator.clipboard?.writeText(texteCanvas);
    setCopie(true);
    toast.success("Document copié dans le presse-papier");
    setTimeout(() => setCopie(false), 2000);
  };

  const texteCanvas = artefact ? JSON.stringify(artefact, null, 2) : contenu;
  const nomCanvas = () => {
    if (artefact) return /\.[a-z0-9]+$/i.test(titre) ? titre : `${titre}.json`;
    return /\.[a-z0-9]+$/i.test(titre) ? titre : `${titre}.md`;
  };
  const telechargerDocument = () => {
    const nom = nomCanvas();
    const url = URL.createObjectURL(new Blob([texteCanvas], { type: artefact ? "application/json;charset=utf-8" : "text/markdown;charset=utf-8" }));
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
            {artefact ? "Artefact" : "Document généré"}
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

          {artefact && (
            <button
              onClick={enregistrerArtefact}
              className="flex h-7 items-center gap-1.5 rounded-lg border border-white/[0.12] bg-[#07111B] px-2.5 font-code text-[11px] text-[#94A3B8] transition-colors hover:border-white/30 hover:text-white"
              title="Enregistrer l'artefact"
              data-testid="btn-enregistrer-artefact"
            >
              <FloppyDisk size={13} />
              <span>Enregistrer</span>
            </button>
          )}
          <button
            onClick={exporterSvg}
            className="flex h-7 items-center gap-1.5 rounded-lg border border-white/[0.12] bg-[#07111B] px-2.5 font-code text-[11px] text-[#94A3B8] transition-colors hover:border-white/30 hover:text-white"
            title="Exporter le SVG"
            data-testid="btn-exporter-svg"
          >
            <DownloadSimple size={13} />
            <span>SVG</span>
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

      {/* Contenu Markdown — rendu générique, propre à CE document (MarkdownFlore) */}
      <div ref={contenuRef} className="relative flex-1 overflow-y-auto px-8 py-7">
        <div className="mx-auto max-w-2xl">
          <div className="mb-5 flex items-center gap-2 border-b border-white/[0.1] pb-4">
            <FileText size={16} className="text-[#60A5FA]" />
            <span className="font-code text-[10px] uppercase tracking-wider text-[#7C93A8]">{artefact ? "Artefact généré par Flore" : "Document généré par Flore"}</span>
          </div>
          <ContenuArtefact artefact={artefact} />
        </div>
      </div>
    </div>
  );
}
