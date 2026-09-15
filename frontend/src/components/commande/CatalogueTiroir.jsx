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
    <div className="flex h-full min-h-0 flex-col rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28]" data-testid="catalogue-tiroir">
      <div className="flex items-center gap-2 border-b border-[rgba(148,163,184,0.16)] px-4 py-3">
        {choisi ? (
          <button onClick={() => setChoisi(null)} className="flex items-center gap-1.5 text-xs text-[#94A3B8] transition-colors hover:text-[#F2F6F8]" data-testid="catalogue-retour">
            <ArrowLeft size={13} /> Catalogue
          </button>
        ) : (
          <>
            <MagnifyingGlass size={15} className="shrink-0 text-[#7C93A8]" />
            <input
              autoFocus
              value={recherche}
              onChange={(e) => setRecherche(e.target.value)}
              placeholder="Oracle, observabilité, incidents…"
              data-testid="catalogue-recherche"
              className="h-8 flex-1 bg-transparent text-sm text-[#F2F6F8] placeholder:text-[#7C93A8] focus:outline-none"
            />
            <kbd className="rounded border border-[rgba(148,163,184,0.16)] px-1.5 py-0.5 font-code text-[9px] text-[#7C93A8]">↑↓ · ⏎ · esc</kbd>
          </>
        )}
        <button onClick={onFermer} data-testid="catalogue-fermer" title="Fermer le catalogue" className="shrink-0 text-[#7C93A8] transition-colors hover:text-[#F2F6F8]"><X size={16} /></button>
      </div>

      {!choisi ? (
        <>
          <div className="flex flex-wrap gap-1.5 border-b border-[rgba(148,163,184,0.16)] px-4 py-2.5" data-testid="catalogue-categories">
            <button onClick={() => setCategorie("")} className={`rounded-full border px-2.5 py-1 text-[10px] transition-colors ${!categorie ? "border-[#25D0C8]/60 text-[#25D0C8]" : "border-[rgba(148,163,184,0.16)] text-[#94A3B8] hover:text-[#F2F6F8]"}`}>Toutes</button>
            {categories.map((c) => (
              <button key={c} onClick={() => setCategorie(categorie === c ? "" : c)} data-testid={`catalogue-cat-${c}`} className={`rounded-full border px-2.5 py-1 text-[10px] transition-colors ${categorie === c ? "border-[#25D0C8]/60 text-[#25D0C8]" : "border-[rgba(148,163,184,0.16)] text-[#94A3B8] hover:text-[#F2F6F8]"}`}>
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
                  className={`w-full rounded-lg p-3 text-left transition-colors ${i === actif ? "bg-[#25D0C8]/[0.08]" : "hover:bg-[rgba(148,163,184,0.07)]"}`}
                >
                  <div className="flex items-center gap-2.5">
                    <Database size={15} className="shrink-0 text-[#25D0C8]" />
                    <span className="font-display text-sm font-bold text-[#F2F6F8]">{c.nom}</span>
                    <span className="ml-auto font-code text-[9px] text-[#7C93A8]">{c.categorie}</span>
                  </div>
                  <p className="mt-1 text-[11px] text-[#94A3B8]">{c.capacites}</p>
                  <p className="mt-0.5 font-code text-[9px] text-[#7C93A8]">{n > 0 ? `${n} instance${n > 1 ? "s" : ""} déjà configurée${n > 1 ? "s" : ""}` : "aucune instance pour l'instant"}</p>
                </button>
              );
            })}
            {resultats.length === 0 && <p className="py-8 text-center text-xs text-[#7C93A8]">Aucun connecteur ne correspond.</p>}
          </div>
        </>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto p-4" data-testid="catalogue-modes">
          <h4 className="font-display text-sm font-bold text-[#F2F6F8]">{choisi.nom}</h4>
          <p className="mt-1 text-[11px] text-[#7C93A8]">{choisi.capacites}</p>
          <p className="mt-4 font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">Comment voulez-vous ajouter cette source ?</p>
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
                  className="w-full rounded-lg border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-3.5 py-3 text-left transition-colors hover:border-[#25D0C8]/40"
                >
                  <div className="text-xs font-semibold text-[#F2F6F8]">{titre}</div>
                  <div className="mt-0.5 text-[10px] text-[#7C93A8]">{desc}</div>
                </button>
                {mode === "profil" && (
                  <div className="mt-1.5 flex gap-1.5">
                    <select value={profil} onChange={(e) => setProfil(e.target.value)} data-testid="mode-profil-select" className="flex-1 rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2 py-1.5 text-[11px] text-[#D8E2EA] focus:outline-none">
                      <option value="">Choisir un profil…</option>
                      {catalogue.profils.filter((p) => p.applicable.includes(choisi.id)).map((p) => <option key={p.id} value={p.id}>{p.nom}</option>)}
                    </select>
                    <button disabled={!profil} onClick={() => onAjoute(choisi, "profil", { profilId: profil })} data-testid="mode-profil-ok" className="rounded-md bg-[#9B87F5] px-2.5 py-1.5 text-[11px] font-semibold text-[#071019] disabled:opacity-30">Appliquer</button>
                  </div>
                )}
                {mode === "dupliquer" && (
                  <div className="mt-1.5 flex gap-1.5">
                    <select value={dupliquerDe} onChange={(e) => setDupliquerDe(e.target.value)} data-testid="mode-dupliquer-select" className="flex-1 rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2 py-1.5 text-[11px] text-[#D8E2EA] focus:outline-none">
                      <option value="">Instance à dupliquer…</option>
                      {instancesDe(choisi.id).map((s) => <option key={s.id} value={s.id}>{s.nom}</option>)}
                    </select>
                    <button disabled={!dupliquerDe} onClick={() => onAjoute(choisi, "dupliquer", { sourceId: dupliquerDe })} data-testid="mode-dupliquer-ok" className="rounded-md bg-[#9B87F5] px-2.5 py-1.5 text-[11px] font-semibold text-[#071019] disabled:opacity-30">Dupliquer</button>
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
