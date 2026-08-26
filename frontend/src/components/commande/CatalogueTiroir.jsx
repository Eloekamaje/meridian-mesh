import { useEffect, useMemo, useState } from "react";
import { MagnifyingGlass, X, Database, ArrowLeft } from "@phosphor-icons/react";

const MODES_AJOUT = [
  ["nouvelle", "Nouvelle instance", "Configurer une instance à partir de zéro"],
  ["profil", "Depuis un profil existant", "Hériter des règles d'un profil (fréquence, secret, sécurité)"],
  ["dupliquer", "Dupliquer une configuration", "Reprendre la configuration d'une instance existante"],
  ["import", "Importer plusieurs instances", "Manifeste ou fichier structuré"],
  ["cmdb", "Découvrir depuis la CMDB", "Récupérer les instances déclarées"],
];

export default function CatalogueTiroir({ catalogue, sources, onAjoute, onImport, onFermer }) {
  const [recherche, setRecherche] = useState("");
  const [categorie, setCategorie] = useState("");
  const [choisi, setChoisi] = useState(null);
  const [profil, setProfil] = useState("");
  const [dupliquerDe, setDupliquerDe] = useState("");
  const [actif, setActif] = useState(0);

  const categories = useMemo(() => [...new Set(catalogue.connecteurs.map((c) => c.categorie))], [catalogue]);

  const resultats = useMemo(() => {
    const q = recherche.trim().toLowerCase();
    return catalogue.connecteurs.filter((c) => {
      if (categorie && c.categorie !== categorie) return false;
      if (q && ![c.nom, c.categorie, c.capacites].join(" ").toLowerCase().includes(q)) return false;
      return true;
    });
  }, [catalogue, recherche, categorie]);

  useEffect(() => setActif(0), [recherche, categorie]);

  useEffect(() => {
    const handler = (e) => {
      if (e.key === "Escape") onFermer();
      if (choisi) return;
      if (e.key === "ArrowDown") { e.preventDefault(); setActif((a) => Math.min(a + 1, resultats.length - 1)); }
      if (e.key === "ArrowUp") { e.preventDefault(); setActif((a) => Math.max(a - 1, 0)); }
      if (e.key === "Enter" && resultats[actif]) { e.preventDefault(); setChoisi(resultats[actif]); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [choisi, resultats, actif, onFermer]);

  const instancesDe = (cid) => sources.filter((s) => s.connecteur === cid);

  // Le catalogue vit dans le panneau droit de l'atelier — plus de palette modale
  return (
    <div className="flex h-full min-h-0 flex-col rounded-xl border border-[#E5E5E3] bg-white" data-testid="catalogue-tiroir">
      <div className="flex items-center gap-2 border-b border-[#E5E5E3] px-4 py-3">
        {choisi ? (
          <button onClick={() => setChoisi(null)} className="flex items-center gap-1.5 text-xs text-[#52524F] transition-colors hover:text-[#111110]" data-testid="catalogue-retour">
            <ArrowLeft size={13} /> Catalogue
          </button>
        ) : (
          <>
            <MagnifyingGlass size={15} className="shrink-0 text-[#71716D]" />
            <input
              autoFocus
              value={recherche}
              onChange={(e) => setRecherche(e.target.value)}
              placeholder="Oracle, observabilité, incidents…"
              data-testid="catalogue-recherche"
              className="h-8 flex-1 bg-transparent text-sm text-[#111110] placeholder:text-[#71716D] focus:outline-none"
            />
            <kbd className="rounded border border-[#E5E5E3] px-1.5 py-0.5 font-code text-[9px] text-[#71716D]">↑↓ · ⏎ · esc</kbd>
          </>
        )}
        <button onClick={onFermer} data-testid="catalogue-fermer" title="Fermer le catalogue" className="shrink-0 text-[#71716D] transition-colors hover:text-[#111110]"><X size={16} /></button>
      </div>

      {!choisi ? (
        <>
          <div className="flex flex-wrap gap-1.5 border-b border-[#E5E5E3] px-4 py-2.5" data-testid="catalogue-categories">
            <button onClick={() => setCategorie("")} className={`rounded-full border px-2.5 py-1 text-[10px] transition-colors ${!categorie ? "border-[#0E7490]/60 text-[#0E7490]" : "border-[#E5E5E3] text-[#52524F] hover:text-[#111110]"}`}>Toutes</button>
            {categories.map((c) => (
              <button key={c} onClick={() => setCategorie(categorie === c ? "" : c)} data-testid={`catalogue-cat-${c}`} className={`rounded-full border px-2.5 py-1 text-[10px] transition-colors ${categorie === c ? "border-[#0E7490]/60 text-[#0E7490]" : "border-[#E5E5E3] text-[#52524F] hover:text-[#111110]"}`}>
                {c}
              </button>
            ))}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2">
            {resultats.map((c, i) => {
              const n = instancesDe(c.id).length;
              return (
                <button
                  key={c.id}
                  onClick={() => setChoisi(c)}
                  onMouseEnter={() => setActif(i)}
                  data-testid={`connecteur-${c.id}`}
                  className={`w-full rounded-lg p-3 text-left transition-colors ${i === actif ? "bg-[#0E7490]/[0.08]" : "hover:bg-[#F7F7F6]"}`}
                >
                  <div className="flex items-center gap-2.5">
                    <Database size={15} className="shrink-0 text-[#0E7490]" />
                    <span className="font-display text-sm font-bold text-[#111110]">{c.nom}</span>
                    <span className="ml-auto font-code text-[9px] text-[#71716D]">{c.categorie}</span>
                  </div>
                  <p className="mt-1 text-[11px] text-[#52524F]">{c.capacites}</p>
                  <p className="mt-0.5 font-code text-[9px] text-[#71716D]">{n > 0 ? `${n} instance${n > 1 ? "s" : ""} déjà configurée${n > 1 ? "s" : ""}` : "aucune instance pour l'instant"}</p>
                </button>
              );
            })}
            {resultats.length === 0 && <p className="py-8 text-center text-xs text-[#71716D]">Aucun connecteur ne correspond.</p>}
          </div>
        </>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto p-4" data-testid="catalogue-modes">
          <h4 className="font-display text-sm font-bold text-[#111110]">{choisi.nom}</h4>
          <p className="mt-1 text-[11px] text-[#71716D]">{choisi.capacites}</p>
          <p className="mt-4 font-code text-[10px] uppercase tracking-[0.2em] text-[#71716D]">Comment voulez-vous ajouter cette source ?</p>
          <div className="mt-3 space-y-2">
            {MODES_AJOUT.map(([mode, titre, desc]) => (
              <div key={mode}>
                <button
                  onClick={() => {
                    if (mode === "profil" || mode === "dupliquer") return;
                    if (mode === "import") { onImport("fichier"); return; }
                    if (mode === "cmdb") { onImport("cmdb"); return; }
                    onAjoute(choisi, mode, {});
                  }}
                  data-testid={`mode-${mode}`}
                  className="w-full rounded-lg border border-[#E5E5E3] bg-white px-3.5 py-3 text-left transition-colors hover:border-[#0E7490]/40"
                >
                  <div className="text-xs font-semibold text-[#111110]">{titre}</div>
                  <div className="mt-0.5 text-[10px] text-[#71716D]">{desc}</div>
                </button>
                {mode === "profil" && (
                  <div className="mt-1.5 flex gap-1.5">
                    <select value={profil} onChange={(e) => setProfil(e.target.value)} data-testid="mode-profil-select" className="flex-1 rounded-md border border-[#E5E5E3] bg-white px-2 py-1.5 text-[11px] text-[#3F3F3C] focus:outline-none">
                      <option value="">Choisir un profil…</option>
                      {catalogue.profils.filter((p) => p.applicable.includes(choisi.id)).map((p) => <option key={p.id} value={p.id}>{p.nom}</option>)}
                    </select>
                    <button disabled={!profil} onClick={() => onAjoute(choisi, "profil", { profilId: profil })} data-testid="mode-profil-ok" className="rounded-md bg-[#3730A3] px-2.5 py-1.5 text-[11px] font-semibold text-white disabled:opacity-30">Appliquer</button>
                  </div>
                )}
                {mode === "dupliquer" && (
                  <div className="mt-1.5 flex gap-1.5">
                    <select value={dupliquerDe} onChange={(e) => setDupliquerDe(e.target.value)} data-testid="mode-dupliquer-select" className="flex-1 rounded-md border border-[#E5E5E3] bg-white px-2 py-1.5 text-[11px] text-[#3F3F3C] focus:outline-none">
                      <option value="">Instance à dupliquer…</option>
                      {instancesDe(choisi.id).map((s) => <option key={s.id} value={s.id}>{s.nom}</option>)}
                    </select>
                    <button disabled={!dupliquerDe} onClick={() => onAjoute(choisi, "dupliquer", { sourceId: dupliquerDe })} data-testid="mode-dupliquer-ok" className="rounded-md bg-[#3730A3] px-2.5 py-1.5 text-[11px] font-semibold text-white disabled:opacity-30">Dupliquer</button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
