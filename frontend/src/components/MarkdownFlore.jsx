import { Children, isValidElement, useContext, useState } from "react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeHighlight from "rehype-highlight";
import { toast } from "sonner";
import { Copy } from "@phosphor-icons/react";
import "katex/dist/katex.min.css";
import "highlight.js/styles/github-dark.css";
import SchemaMermaid from "./SchemaMermaid";
import { decouperMermaid } from "@/lib/segmentsMermaid";
import { PreuvesContexte, couperPastille, numeroPastille, typeSource } from "@/lib/preuvesFlore";

// Le seul rendu Markdown de Flore (panneau, Travail, Canvas, brouillon). react-markdown n'injecte jamais de HTML brut
// (pas de rehype-raw) et neutralise les URL `javascript:`. Les `$` seuls ne sont pas des formules (« 5 $ et 6 $ »).
const REMARK = [remarkGfm, [remarkMath, { singleDollarTextMath: false }]];
const REHYPE = [rehypeKatex, [rehypeHighlight, { detect: false, ignoreMissing: true }]];

// Une citation de pièce (`pièce:<id>#<section>`, souvent entre accents graves) devient un lien interne :
// react-markdown la rend comme n'importe quel lien, et le composant `a` ci-dessous l'intercepte pour
// ouvrir la section sans jamais naviguer vers une URL inventée. Les blocs de code sont laissés intacts.
const SCHEMA_PIECE = "meridian-piece:";
const RE_CITATION_PIECE = /(`?)\bpi[eè]ce:([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)#([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)\1/gi;
const RE_BLOC_CODE = /(```[\s\S]*?```|~~~[\s\S]*?~~~)/g;
// Identifiants acceptés par l'API des pièces : jamais de chemin, de requête ni de caractère de contrôle.
const RE_ID_PIECE = /^[A-Za-z0-9_-]+$/;
// Une image distante n'est jamais chargée automatiquement : une réponse ne fait aucune requête vers un
// domaine externe. Seules les images `data:` embarquées (raster, base64) restent affichées ; tout le
// reste devient un texte — un lien explicite pour http(s), à ouvrir d'un geste volontaire.
const RE_IMAGE_DATA = /^data:image\/(?:png|jpe?g|gif|webp|avif);base64,[A-Za-z0-9+/=\s]+$/i;
const RE_IMAGE_DISTANTE = /^(?:https?:)?\/\//i;
// react-markdown n'accepte par défaut que http(s), mailto… et les URL relatives : notre schéma interne
// doit donc être explicitement autorisé, comme les images embarquées ; toutes les autres URL gardent
// la validation par défaut.
const transformerUrl = (url) => {
  const valeur = String(url || "");
  return valeur.startsWith(SCHEMA_PIECE) || RE_IMAGE_DATA.test(valeur) ? valeur : defaultUrlTransform(valeur);
};

export function lierCitations(texte) {
  return String(texte || "")
    .split(RE_BLOC_CODE)
    .map((bloc, i) => (i % 2 === 1 ? bloc : bloc.replace(RE_CITATION_PIECE, (_m, _g, pieceId, sectionId, decalage, chaine) => {
      // Une citation de tableau (`pièce:<id>#table:<id>`) reste du texte : elle ne désigne pas une section.
      const tableau = /^table$/i.test(sectionId) && chaine[decalage + _m.length] === ":";
      return tableau
        ? _m
        : `[§](${SCHEMA_PIECE}${encodeURIComponent(pieceId)}#${encodeURIComponent(sectionId)})`;
    })))
    .join("");
}

const decoder = (valeur) => { try { return decodeURIComponent(valeur); } catch { return valeur; } };

export function ciblePiece(href) {
  const valeur = String(href || "");
  if (!valeur.startsWith(SCHEMA_PIECE)) return null;
  const reste = valeur.slice(SCHEMA_PIECE.length);
  const diese = reste.indexOf("#");
  if (diese <= 0 || diese === reste.length - 1) return null;
  const pieceId = decoder(reste.slice(0, diese));
  const sectionId = decoder(reste.slice(diese + 1));
  if (!RE_ID_PIECE.test(pieceId) || !RE_ID_PIECE.test(sectionId)) return null;
  return { pieceId, sectionId };
}

export function LienPiece({ href, children, onOuvrirPiece }) {
  const cible = ciblePiece(href);
  if (!cible) return null;
  const texte = children || "§";
  // Sans geste d'ouverture, une citation n'est pas un lien : on affiche son texte, sans <a> ni focus.
  if (!onOuvrirPiece) {
    return (
      <span
        title={`Section ${cible.sectionId} de la pièce ${cible.pieceId}`}
        data-testid="lien-piece-inactif"
        data-piece-id={cible.pieceId}
        data-section-id={cible.sectionId}
        className="mx-0.5 inline-flex items-center rounded-[5px] bg-[#60A5FA]/10 px-1 font-code text-[11px] text-[#93C5FD]"
      >
        {texte}
      </span>
    );
  }
  const ouvrir = (e) => {
    e.preventDefault();
    onOuvrirPiece(cible);
  };
  return (
    <a
      href={href}
      onClick={ouvrir}
      title={`Ouvrir la section ${cible.sectionId} de la pièce ${cible.pieceId}`}
      aria-label={`Ouvrir la section ${cible.sectionId} de la pièce ${cible.pieceId}`}
      data-testid="lien-piece"
      data-piece-id={cible.pieceId}
      data-section-id={cible.sectionId}
      className="mx-0.5 inline-flex items-center rounded-[5px] bg-[#60A5FA]/10 px-1 font-code text-[11px] text-[#93C5FD] underline underline-offset-2 transition-colors hover:bg-[#60A5FA]/20 hover:text-[#BFDBFE] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#60A5FA]"
    >
      {texte}
    </a>
  );
}

function LienMarkdown({ href, children, onOuvrirPiece }) {
  const n = numeroPastille(href);
  if (n != null) return <Pastille n={n} />;
  if (String(href || "").startsWith(SCHEMA_PIECE)) return <LienPiece href={href} onOuvrirPiece={onOuvrirPiece}>{children}</LienPiece>;
  const externe = /^(?:https?:)?\/\//i.test(href || "");
  return <a href={href} {...(externe ? { target: "_blank", rel: "noopener noreferrer" } : {})} className="text-[#60A5FA] underline underline-offset-2 hover:text-[#93C5FD] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#60A5FA]">{children}</a>;
}

function texteDe(noeud) {
  return Children.toArray(noeud).map((n) => (typeof n === "string" ? n : isValidElement(n) ? texteDe(n.props.children) : "")).join("");
}

export function ImageFlore({ src, alt, title }) {
  const valeur = String(src || "").trim();
  const texte = String(alt || "").trim() || "Image";
  if (RE_IMAGE_DATA.test(valeur)) {
    return (
      <img
        src={valeur}
        alt={alt || ""}
        title={title || undefined}
        loading="lazy"
        data-testid="image-inline"
        className="max-w-full rounded-lg border border-white/[0.08]"
      />
    );
  }
  if (RE_IMAGE_DISTANTE.test(valeur)) {
    return (
      <span className="text-[#94A3B8]" data-testid="image-distante">
        <a
          href={valeur}
          target="_blank"
          rel="noopener noreferrer"
          title="Image distante non chargée automatiquement"
          className="text-[#60A5FA] underline underline-offset-2 hover:text-[#93C5FD] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#60A5FA]"
        >
          {`Image : ${texte}`}
        </a>
      </span>
    );
  }
  return <span className="text-[#94A3B8]" data-testid="image-bloquee">{`Image : ${texte}`}</span>;
}

function BlocCode({ children }) {
  const [copie, setCopie] = useState(false);
  const copier = () => {
    navigator.clipboard?.writeText(texteDe(children).replace(/\n$/, ""));
    setCopie(true);
    toast.success("Code copié");
    setTimeout(() => setCopie(false), 1500);
  };
  return (
    <div className="relative my-2 rounded-lg border border-white/[0.08] bg-[#07111B]">
      <button type="button" onClick={copier} aria-label="Copier le code" title="Copier le code"
        className="absolute right-2 top-2 flex items-center gap-1 rounded-md border border-white/[0.1] bg-[#0B1220] px-1.5 py-0.5 font-code text-[10px] text-[#94A3B8] transition-colors hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#60A5FA]">
        <Copy size={11} /> {copie ? "Copié" : "Copier"}
      </button>
      <pre className="overflow-x-auto p-3 pr-20 font-code text-xs leading-relaxed">{children}</pre>
    </div>
  );
}

const COMPOSANTS = {
  h1: (p) => <h1 className="pt-2 font-display text-xl font-bold text-white" {...clean(p)} />,
  h2: (p) => <h2 className="pt-2 font-display text-lg font-bold text-white" {...clean(p)} />,
  h3: (p) => <h3 className="pt-1 font-display text-base font-bold text-white" {...clean(p)} />,
  h4: (p) => <h4 className="pt-1 font-display text-sm font-bold text-white" {...clean(p)} />,
  p: (p) => <p {...clean(p)} />,
  ul: (p) => <ul className="list-disc space-y-1 pl-5 marker:text-[#60A5FA]" {...clean(p)} />,
  ol: (p) => <ol className="list-decimal space-y-1 pl-5 marker:font-code marker:text-[#60A5FA]" {...clean(p)} />,
  blockquote: (p) => <blockquote className="rounded-r-md border-l-2 border-[#60A5FA]/60 bg-blue-500/[0.04] py-1 pl-3 italic text-blue-200/90" {...clean(p)} />,
  hr: () => <hr className="border-white/[0.08]" />,
  li: Puce,
  strong: (p) => <strong className="font-semibold text-white" {...clean(p)} />,
  table: ({ children }) => <div className="overflow-x-auto rounded-xl border border-white/[0.08] bg-[#0A131C]"><table className="w-full text-left text-xs">{children}</table></div>,
  thead: ({ children }) => <thead className="border-b border-white/[0.08] font-code text-[10px] uppercase tracking-wider text-[#7C93A8]">{children}</thead>,
  th: ({ children }) => <th className="px-3 py-2.5">{children}</th>,
  td: ({ children }) => <td className="border-t border-white/[0.05] px-3 py-2 text-[#CBD5E1]">{children}</td>,
  img: (p) => <ImageFlore {...p} />,
  pre: ({ children }) => <BlocCode>{children}</BlocCode>,
  code: ({ className, children }) => (className
    ? <code className={`${className} !bg-transparent`}>{children}</code>
    : <code className="rounded bg-blue-500/10 px-1 py-0.5 font-code text-xs text-blue-300">{children}</code>),
};
// react-markdown passe `node` : on ne le répercute pas sur le DOM.
function clean({ node, ...reste }) { return reste; }

// Une pastille de preuve (Design System §131, « evidence chips ») : survol = la source, clic = la carte de preuve.
function Pastille({ n }) {
  const ctx = useContext(PreuvesContexte);
  const preuve = ctx?.preuves?.[n - 1];
  if (!preuve) return null; // pas de preuve à ce rang : rien d'affiché (jamais un numéro qui ne mène nulle part)
  return (
    <button type="button" onClick={() => ctx.ouvrir?.(n)} title={`${typeSource(preuve.detail)} · ${preuve.source}`}
      aria-label={`Preuve ${n} : ${preuve.source}`} data-testid={`pastille-${n}`}
      className="mx-0.5 inline-flex min-w-[18px] -translate-y-px items-center justify-center rounded-[5px] bg-[#60A5FA]/15 px-1 align-baseline font-code text-[10px] leading-[16px] text-[#93C5FD] transition-colors hover:bg-[#60A5FA]/30 focus-visible:outline focus-visible:outline-1 focus-visible:outline-[#60A5FA]">
      {n}
    </button>
  );
}

// Note d'impact : un effet (« bloquant », « dégradé », « sans effet », « inconnu ») sans pastille le dit.
const RE_CLASSE_EFFET = /^\s*(bloquant|dégradé|degrade|sans effet(?: visible)?|inconnu)(?=[\s:—-])/i;
const texteHast = (n) => (n?.type === "text" ? n.value : (n?.children || []).map(texteHast).join(""));
const aUnePastille = (n) => (n?.type === "element" && n.tagName === "a" && numeroPastille(n.properties?.href) != null)
  || (n?.children || []).some(aUnePastille);
function Puce({ node, children }) {
  const sansPreuve = RE_CLASSE_EFFET.test(texteHast(node)) && !aUnePastille(node);
  return (
    <li>
      {children}
      {sansPreuve && <span className="ml-1.5 rounded-[5px] bg-[#F2B84B]/15 px-1.5 font-code text-[10px] text-[#F2B84B]" data-testid="sans-preuve">sans preuve</span>}
    </li>
  );
}

// `enLigne` : une cellule ou une puce (pas de paragraphe autour). `className` s'ajoute au conteneur.
export default function MarkdownFlore({ texte, enLigne = false, className = "", onOuvrirPiece }) {
  const composants = {
    ...COMPOSANTS,
    a: (p) => <LienMarkdown {...p} onOuvrirPiece={onOuvrirPiece} />,
    ...(enLigne ? { p: ({ children }) => <>{children}</> } : {}),
  };
  const propre = lierCitations(couperPastille(texte)); // au fil de l'eau : jamais une pastille à moitié écrite
  const segments = enLigne ? [{ type: "texte", texte: propre }] : decouperMermaid(propre);
  const Conteneur = enLigne ? "span" : "div";
  return (
    <Conteneur className={`space-y-3 text-[14.5px] leading-relaxed text-[#D8E2EA] ${className}`} data-testid="markdown-flore">
      {segments.map((s, i) => (s.type === "mermaid"
        ? <SchemaMermaid key={i} code={s.code} complet={s.complet} />
        : <ReactMarkdown key={i} remarkPlugins={REMARK} rehypePlugins={REHYPE} urlTransform={transformerUrl} components={composants}>{s.texte || ""}</ReactMarkdown>))}
    </Conteneur>
  );
}
