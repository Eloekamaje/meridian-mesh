// Rendu Markdown partagé, sobre — titres, puces, citations, tableaux, paragraphes, gras/code
// inline. Utilisé pour un document déjà complet (Canvas) : contrairement au déroulé progressif de
// CorpsMessageFlore (qui gère en plus le texte en train de s'écrire), un document de Canvas
// s'affiche d'un bloc dès son ouverture.

export function formaterGrasCode(txt) {
  if (!txt) return "";
  return txt
    .replace(/\*\*(.*?)\*\*/g, "<strong class='font-semibold text-white'>$1</strong>")
    .replace(/`([^`]+)`/g, "<code class='font-code text-xs text-blue-300 bg-blue-500/10 px-1 py-0.5 rounded'>$1</code>");
}

function decouperBlocs(texte) {
  const lignes = (texte || "").split("\n");
  const blocs = [];
  let tableauEnCours = null;
  lignes.forEach((ligne, idx) => {
    const trimmed = ligne.trim();
    if (trimmed.startsWith("|")) {
      const cellules = trimmed.split("|").slice(1, -1).map((c) => c.trim());
      if (cellules.every((c) => /^:?-+:?$/.test(c))) return; // ligne séparatrice |---|---|
      if (!tableauEnCours) { tableauEnCours = { key: `tbl-${idx}`, lignes: [] }; blocs.push(tableauEnCours); }
      tableauEnCours.lignes.push(cellules);
      return;
    }
    tableauEnCours = null;
    if (!trimmed) { blocs.push({ key: idx, type: "espace" }); return; }
    if (trimmed === "---") { blocs.push({ key: idx, type: "regle" }); return; }
    if (trimmed.startsWith("### ")) { blocs.push({ key: idx, type: "h3", texte: trimmed.slice(4) }); return; }
    if (trimmed.startsWith("## ")) { blocs.push({ key: idx, type: "h2", texte: trimmed.slice(3) }); return; }
    if (trimmed.startsWith("# ")) { blocs.push({ key: idx, type: "h1", texte: trimmed.slice(2) }); return; }
    if (trimmed.startsWith("* ") || trimmed.startsWith("- ") || trimmed.startsWith("• ")) {
      blocs.push({ key: idx, type: "puce", texte: trimmed.replace(/^[*\-•]\s*/, "") });
      return;
    }
    if (trimmed.startsWith("> ")) { blocs.push({ key: idx, type: "citation", texte: trimmed.slice(2) }); return; }
    blocs.push({ key: idx, type: "p", texte: trimmed });
  });
  return blocs;
}

export function RenduMarkdown({ texte, className = "" }) {
  const blocs = decouperBlocs(texte);
  return (
    <div className={`space-y-3 text-sm leading-relaxed text-[#CBD5E1] ${className}`}>
      {blocs.map((b) => {
        if (b.lignes) {
          const [entete, ...corps] = b.lignes;
          return (
            <div key={b.key} className="overflow-x-auto rounded-xl border border-white/[0.08] bg-[#07111B]">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-white/[0.08] bg-[#0D1A27] font-code text-[10px] uppercase tracking-wider text-[#64748B]">
                    {entete.map((c, i) => (
                      <th key={i} className="py-2.5 px-3">{c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.05]">
                  {corps.map((ligne, li) => (
                    <tr key={li}>
                      {ligne.map((c, ci) => (
                        <td key={ci} className="py-2 px-3" dangerouslySetInnerHTML={{ __html: formaterGrasCode(c) }} />
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        switch (b.type) {
          case "espace":
            return <div key={b.key} className="h-1" />;
          case "regle":
            return <hr key={b.key} className="border-white/[0.08]" />;
          case "h1":
            return <h1 key={b.key} className="font-display text-2xl font-bold text-[#F2F6F8]">{b.texte}</h1>;
          case "h2":
            return <h2 key={b.key} className="font-display text-lg font-semibold text-[#F2F6F8] pt-2">{b.texte}</h2>;
          case "h3":
            return <h3 key={b.key} className="font-display text-base font-semibold text-[#F2F6F8] pt-1">{b.texte}</h3>;
          case "puce":
            return (
              <div key={b.key} className="flex items-start gap-2 pl-2">
                <span className="mt-1 text-xs text-[#60A5FA]">•</span>
                <span dangerouslySetInnerHTML={{ __html: formaterGrasCode(b.texte) }} />
              </div>
            );
          case "citation":
            return (
              <div
                key={b.key}
                className="border-l-2 border-[#60A5FA]/60 pl-3 py-1 italic text-[#94A3B8]"
                dangerouslySetInnerHTML={{ __html: formaterGrasCode(b.texte) }}
              />
            );
          default:
            return <p key={b.key} dangerouslySetInnerHTML={{ __html: formaterGrasCode(b.texte) }} />;
        }
      })}
    </div>
  );
}
