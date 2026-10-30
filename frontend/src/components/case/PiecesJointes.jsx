import { useRef, useState } from "react";
import { DownloadSimple, FileText, Paperclip, SpinnerGap, X } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { usePerimetre } from "@/lib/perimetre";

// Même liste que le backend : le refus est d'abord local, pour un retour immédiat, puis serveur (jamais contournable).
export const EXTENSIONS_PIECES = [
  ".txt", ".text", ".md", ".markdown", ".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml", ".xml", ".log",
  ".sql", ".ini", ".conf", ".cfg", ".toml", ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".sh",
  ".bash", ".ps1", ".c", ".h", ".cpp", ".hpp", ".rb", ".php", ".swift", ".kt", ".html", ".htm", ".pdf",
  ".doc", ".docx", ".ppt", ".pptx", ".pps", ".ppsx", ".pot", ".xls", ".xlsx", ".xlsb",
  ".odt", ".ods", ".odp", ".rtf", ".epub",
];
export const MAX_OCTETS_PIECE = 10 * 1024 * 1024;

const ETATS = {
  lu: ["texte lu", "text-emerald-300"],
  tronque: ["texte lu (tronqué)", "text-[#F2B84B]"],
  vide: ["aucun texte", "text-[#7C93A8]"],
  non_lu: ["non lu", "text-[#F2B84B]"],
};

function extension(nom) {
  const trouve = String(nom || "").toLowerCase().match(/\.[a-z0-9]+$/);
  return trouve ? trouve[0] : "";
}

export function tailleLisible(octets) {
  const n = Number(octets) || 0;
  if (n < 1024) return `${n} o`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} Ko`;
  return `${(n / (1024 * 1024)).toFixed(1).replace(".", ",")} Mo`;
}

const MAX_TITRES_SOMMAIRE = 8;
const MAX_TITRES_TABLEAUX = 8;

function nombreSections(piece) {
  const brut = piece?.sections_count ?? (piece?.sections || []).length;
  const n = Number(brut);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
}

function libelleSections(n) {
  return `${n} section${n > 1 ? "s" : ""}`;
}

function sommaireSections(piece) {
  const titres = (piece?.sections || [])
    .map((section) => String(section?.titre || "").trim())
    .filter(Boolean)
    .slice(0, MAX_TITRES_SOMMAIRE);
  return titres.length ? `Sommaire : ${titres.join(" · ")}` : "";
}

function nombreTableaux(piece) {
  const brut = piece?.tables_count ?? (piece?.tables || []).length;
  const n = Number(brut);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
}

function libelleTableaux(n) {
  return `${n} tableau${n > 1 ? "x" : ""}`;
}

function sommaireTableaux(piece) {
  const titres = (piece?.tables || [])
    .map((table) => String(table?.titre || "").trim())
    .filter(Boolean)
    .slice(0, MAX_TITRES_TABLEAUX);
  return titres.length ? `Tableaux : ${titres.join(" · ")}` : "";
}

function resume(piece) {
  const etat = ETATS[piece.etat] || [piece.etat || "—", "text-[#7C93A8]"];
  const morceaux = [piece.type_libelle || "fichier", tailleLisible(piece.taille)];
  if (piece.pages) morceaux.push(`${piece.pages} page${piece.pages > 1 ? "s" : ""}`);
  const sections = nombreSections(piece);
  const tableaux = nombreTableaux(piece);
  const detail = morceaux.join(" · ");
  const morceauxResume = [detail];
  if (sections) morceauxResume.push(libelleSections(sections));
  if (tableaux) morceauxResume.push(libelleTableaux(tableaux));
  return {
    texte: morceauxResume.join(" · "),
    detail,
    sections,
    tableaux,
    etat,
  };
}

function peutRetirer(piece, cas, moi, lectureSeule) {
  if (lectureSeule) return false;
  return moi === piece.joint_par || moi === cas?.responsable;
}

async function telecharger(cas, piece) {
  try {
    const { data } = await api.get(`/cases/${cas.id}/pieces/${piece.id}`, { responseType: "blob" });
    const url = URL.createObjectURL(data);
    const lien = document.createElement("a");
    lien.href = url;
    lien.download = piece.nom;
    document.body.appendChild(lien);
    lien.click();
    lien.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    toast.error(e.response?.data?.detail || "Téléchargement impossible");
  }
}

async function retirer(cas, piece, onChange) {
  if (!window.confirm(`Retirer « ${piece.nom} » de ce travail ?`)) return;
  try {
    await api.delete(`/cases/${cas.id}/pieces/${piece.id}`);
    onChange((cas.pieces || []).filter((p) => p.id !== piece.id));
    toast.success("Pièce jointe retirée");
  } catch (e) {
    toast.error(e.response?.data?.detail || "Retrait impossible");
  }
}

export function BoutonJoindre({ cas, onChange, disabled = false, testid = "piece-joindre" }) {
  const ref = useRef(null);
  const [envoi, setEnvoi] = useState(false);

  const envoyer = async (fichiers) => {
    const choisis = Array.from(fichiers || []);
    if (!choisis.length) return;
    const refus = [];
    const valides = choisis.filter((f) => {
      const ext = extension(f.name);
      if (!EXTENSIONS_PIECES.includes(ext)) {
        refus.push(`${f.name} : format non pris en charge`);
        return false;
      }
      if (f.size > MAX_OCTETS_PIECE) {
        refus.push(`${f.name} : ${tailleLisible(f.size)} (10 Mo au plus)`);
        return false;
      }
      if (!f.size) {
        refus.push(`${f.name} : fichier vide`);
        return false;
      }
      return true;
    });
    refus.forEach((r) => toast.error(r));
    if (!valides.length) return;
    setEnvoi(true);
    const ajoutees = [];
    for (const fichier of valides) {
      const donnees = new FormData();
      donnees.append("fichier", fichier);
      try {
        const { data } = await api.post(`/cases/${cas.id}/pieces`, donnees);
        ajoutees.push(data);
      } catch (e) {
        toast.error(e.response?.data?.detail || `Ajout de ${fichier.name} impossible`);
      }
    }
    setEnvoi(false);
    if (ref.current) ref.current.value = "";
    if (ajoutees.length) {
      onChange([...(cas.pieces || []), ...ajoutees]);
      toast.success(ajoutees.length > 1 ? `${ajoutees.length} pièces jointes ajoutées` : "Pièce jointe ajoutée");
    }
  };

  return (
    <>
      <input
        ref={ref}
        type="file"
        multiple
        accept={EXTENSIONS_PIECES.join(",")}
        onChange={(e) => envoyer(e.target.files)}
        className="hidden"
        data-testid={`${testid}-input`}
        tabIndex={-1}
      />
      <button
        type="button"
        onClick={() => ref.current?.click()}
        disabled={disabled || envoi || !cas?.id}
        title="Joindre un document (PDF, Word, PowerPoint, Excel, OpenDocument, RTF, EPUB, texte…)"
        aria-label="Joindre un document"
        data-testid={testid}
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-white/[0.08] bg-white/[0.03] text-[#94A3B8] transition-colors hover:border-white/20 hover:text-white disabled:cursor-not-allowed disabled:opacity-30"
      >
        {envoi ? <SpinnerGap size={16} className="animate-spin" /> : <Paperclip size={16} />}
      </button>
    </>
  );
}

export function ListePieces({ cas, onChange, compact = false, lectureSeule = false }) {
  const { persona } = usePerimetre();
  const pieces = cas?.pieces || [];
  if (!pieces.length) return null;

  if (compact) {
    return (
      <div className="mb-2 flex flex-wrap gap-1.5" data-testid="pieces-liste">
        {pieces.map((piece) => {
          const { texte, etat } = resume(piece);
          return (
            <span
              key={piece.id}
              className="flex max-w-full items-center gap-1 rounded-full border border-white/[0.10] bg-white/[0.04] px-2 py-0.5 font-code text-[10px] text-[#CBD5E1]"
              data-testid={`piece-chip-${piece.id}`}
              title={`${texte} · ${etat[0]}${piece.note ? ` · ${piece.note}` : ""}`}
            >
              <FileText size={11} className="shrink-0 text-[#60A5FA]" />
              <button
                type="button"
                onClick={() => telecharger(cas, piece)}
                className="truncate hover:text-white"
                title={`Télécharger ${piece.nom}`}
                data-testid={`piece-telecharger-compact-${piece.id}`}
              >
                {piece.nom}
              </button>
              <span className={`shrink-0 ${etat[1]}`}>{etat[0]}</span>
              {peutRetirer(piece, cas, persona, lectureSeule) && (
                <button
                  type="button"
                  onClick={() => retirer(cas, piece, onChange)}
                  className="shrink-0 opacity-60 hover:opacity-100"
                  aria-label={`Retirer ${piece.nom}`}
                  title="Retirer la pièce"
                  data-testid={`piece-retirer-compact-${piece.id}`}
                >
                  <X size={10} />
                </button>
              )}
            </span>
          );
        })}
      </div>
    );
  }

  return (
    <div className="space-y-1.5" data-testid="pieces-liste">
      {pieces.map((piece) => {
        const { detail, etat, sections, tableaux } = resume(piece);
        return (
          <div
            key={piece.id}
            className="flex items-center justify-between gap-2 rounded-lg border border-transparent bg-white/[0.03] px-2.5 py-1.5 text-xs text-[#CBD5E1]"
            data-testid={`piece-ligne-${piece.id}`}
          >
            <div className="flex min-w-0 items-center gap-2">
              <FileText size={13} className="shrink-0 text-[#60A5FA]" />
              <div className="min-w-0">
                <button
                  type="button"
                  onClick={() => telecharger(cas, piece)}
                  className="block max-w-full truncate text-left hover:text-white"
                  title={`Télécharger ${piece.nom}`}
                  data-testid={`piece-telecharger-${piece.id}`}
                >
                  {piece.nom}
                </button>
                <div className="font-code text-[10px] text-[#7C93A8]">
                  {detail} · <span className={etat[1]}>{etat[0]}</span>
                  {sections > 0 && (
                    <span
                      className="text-[#7C93A8]"
                      data-testid={`piece-sections-${piece.id}`}
                      title={sommaireSections(piece) || undefined}
                    >
                      {" "}· {libelleSections(sections)}
                    </span>
                  )}
                  {tableaux > 0 && (
                    <span
                      className="text-[#7C93A8]"
                      data-testid={`piece-tables-${piece.id}`}
                      title={sommaireTableaux(piece) || undefined}
                    >
                      {" "}· {libelleTableaux(tableaux)}
                    </span>
                  )}
                  {piece.etat === "vide" && (
                    <span className="text-[#7C93A8]" data-testid={`piece-non-utilisee-${piece.id}`}>
                      {" "}· non utilisée par Flore
                    </span>
                  )}
                </div>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <button
                type="button"
                onClick={() => telecharger(cas, piece)}
                className="flex h-6 w-6 items-center justify-center rounded text-[#7C93A8] hover:text-white"
                aria-label={`Télécharger ${piece.nom}`}
                title="Télécharger"
                data-testid={`piece-telecharger-bouton-${piece.id}`}
              >
                <DownloadSimple size={13} />
              </button>
              {peutRetirer(piece, cas, persona, lectureSeule) && (
                <button
                  type="button"
                  onClick={() => retirer(cas, piece, onChange)}
                  className="flex h-6 w-6 items-center justify-center rounded text-[#7C93A8] hover:text-[#F87171]"
                  aria-label={`Retirer ${piece.nom}`}
                  title="Retirer"
                  data-testid={`piece-retirer-bouton-${piece.id}`}
                >
                  <X size={13} />
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
