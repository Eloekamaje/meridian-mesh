import { Children, isValidElement, useContext, useState } from "react";
import ReactMarkdown from "react-markdown";
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

function texteDe(noeud) {
  return Children.toArray(noeud).map((n) => (typeof n === "string" ? n : isValidElement(n) ? texteDe(n.props.children) : "")).join("");
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
  a: ({ href, children }) => (numeroPastille(href) != null ? <Pastille n={numeroPastille(href)} /> : <a href={href} target="_blank" rel="noopener noreferrer" className="text-[#60A5FA] underline underline-offset-2 hover:text-[#93C5FD] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#60A5FA]">{children}</a>),
  strong: (p) => <strong className="font-semibold text-white" {...clean(p)} />,
  table: ({ children }) => <div className="overflow-x-auto rounded-xl border border-white/[0.08] bg-[#0A131C]"><table className="w-full text-left text-xs">{children}</table></div>,
  thead: ({ children }) => <thead className="border-b border-white/[0.08] font-code text-[10px] uppercase tracking-wider text-[#7C93A8]">{children}</thead>,
  th: ({ children }) => <th className="px-3 py-2.5">{children}</th>,
  td: ({ children }) => <td className="border-t border-white/[0.05] px-3 py-2 text-[#CBD5E1]">{children}</td>,
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
export default function MarkdownFlore({ texte, enLigne = false, className = "" }) {
  const composants = enLigne ? { ...COMPOSANTS, p: ({ children }) => <>{children}</> } : COMPOSANTS;
  const propre = couperPastille(texte); // au fil de l'eau : jamais une pastille à moitié écrite
  const segments = enLigne ? [{ type: "texte", texte: propre }] : decouperMermaid(propre);
  const Conteneur = enLigne ? "span" : "div";
  return (
    <Conteneur className={`space-y-3 text-[14.5px] leading-relaxed text-[#D8E2EA] ${className}`} data-testid="markdown-flore">
      {segments.map((s, i) => (s.type === "mermaid"
        ? <SchemaMermaid key={i} code={s.code} complet={s.complet} />
        : <ReactMarkdown key={i} remarkPlugins={REMARK} rehypePlugins={REHYPE} components={composants}>{s.texte || ""}</ReactMarkdown>))}
    </Conteneur>
  );
}
