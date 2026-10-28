// Découpe une réponse de Flore en texte et en schémas Mermaid (```mermaid … ```), pour que chaque fil de
// conversation dessine les schémas à leur place. Un bloc non refermé (réponse en train de s'écrire) est « en cours ».
export function decouperMermaid(texte) {
  const segments = [];
  const motif = /```mermaid[ \t]*\n([\s\S]*?)(```|$)/g;
  let fin = 0;
  let m;
  while ((m = motif.exec(texte || "")) !== null) {
    if (m.index > fin) segments.push({ type: "texte", texte: texte.slice(fin, m.index) });
    segments.push({ type: "mermaid", code: m[1].trim(), complet: m[2] === "```" });
    fin = motif.lastIndex;
    if (!m[0]) break;
  }
  if (fin < (texte || "").length) segments.push({ type: "texte", texte: texte.slice(fin) });
  return segments.length ? segments : [{ type: "texte", texte: texte || "" }];
}
