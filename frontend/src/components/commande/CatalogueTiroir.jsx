import { useMemo, useState } from "react";
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

  const categories = useMemo(() => [...new Set(catalogue.connecteurs.map((c) => c.categorie))], [catalogue]);

  const resultats = useMemo(() => {
    const q = recherche.trim().toLowerCase();
    return catalogue.connecteurs.filter((c) => {
      if (categorie && c.categorie !== categorie) return false;
      if (q && ![c.nom, c.categorie, c.capacites].join(" ").toLowerCase().includes(q)) return false;
      return true;
    });
  }, [catalogue, recherche, categorie]);

  const instancesDe = (cid) => sources.filter((s) => s.connecteur === cid);

  return (
    <div className="fixed inset-0 z-50" data-testid="catalogue-tiroir">
      <div className="absolute inset-0 bg-black/60" onClick={onFermer} />
      <div className="absolute right-0 top-0 flex h-full w-[440px] flex-col border-l border-white/10 bg-[#0D0D0D] p-5">
        <div className="flex items-center justify-between">
          {choisi ? (
            <button onClick={() => setChoisi(null)} className="flex items-center gap-1.5 text-xs text-white/50 hover:text-white" data-testid="catalogue-retour">
              <ArrowLeft size={13} /> Catalogue
            </button>
          ) : (
            <h3 className="font-display text-base font-bold text-white">Ajouter une source</h3>
          )}
          <button onClick={onFermer} data-testid="catalogue-fermer" className="text-white/40 hover:text-white"><X size={16} /></button>
        </div>

        {!choisi ? (
          <>
            <div className="relative mt-4">
              <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30" />
              <input
                autoFocus
                value={recherche}
                onChange={(e) => setRecherche(e.target.value)}
                placeholder="Oracle, base de données, observabilité, incidents…"
                data-testid="catalogue-recherche"
                className="w-full rounded-md border border-white/10 bg-black/50 py-2.5 pl-9 pr-3 text-sm text-white placeholder:text-white/25 focus:border-[#22D3EE]/60 focus:outline-none"
              />
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5" data-testid="catalogue-categories">
              <button onClick={() => setCategorie("")} className={`rounded-full border px-2.5 py-1 text-[10px] transition-colors ${!categorie ? "border-[#22D3EE]/60 text-[#22D3EE]" : "border-white/10 text-white/50 hover:text-white"}`}>Toutes</button>
              {categories.map((c) => (
                <button key={c} onClick={() => setCategorie(categorie === c ? "" : c)} data-testid={`catalogue-cat-${c}`} className={`rounded-full border px-2.5 py-1 text-[10px] transition-colors ${categorie === c ? "border-[#22D3EE]/60 text-[#22D3EE]" : "border-white/10 text-white/50 hover:text-white"}`}>
                  {c}
                </button>
              ))}
            </div>
            <div className="mt-4 min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
              {resultats.map((c) => {
                const n = instancesDe(c.id).length;
                return (
                  <button key={c.id} onClick={() => setChoisi(c)} data-testid={`connecteur-${c.id}`} className="w-full rounded-lg border border-white/[0.08] bg-white/[0.02] p-3.5 text-left transition-colors hover:border-[#22D3EE]/40">
                    <div className="flex items-center gap-2.5">
                      <Database size={16} className="shrink-0 text-[#22D3EE]" />
                      <span className="font-display text-sm font-bold text-white">{c.nom}</span>
                      <span className="ml-auto font-code text-[9px] text-white/35">{c.categorie}</span>
                    </div>
                    <p className="mt-1.5 text-[11px] text-white/50">{c.capacites}</p>
                    <p className="mt-1 font-code text-[9px] text-white/30">{n > 0 ? `${n} instance${n > 1 ? "s" : ""} déjà configurée${n > 1 ? "s" : ""}` : "aucune instance pour l'instant"}</p>
                  </button>
                );
              })}
              {resultats.length === 0 && <p className="py-8 text-center text-xs text-white/30">Aucun connecteur ne correspond.</p>}
            </div>
          </>
        ) : (
          <div className="mt-4 min-h-0 flex-1 overflow-y-auto" data-testid="catalogue-modes">
            <h4 className="font-display text-sm font-bold text-white">{choisi.nom}</h4>
            <p className="mt-1 text-[11px] text-white/45">{choisi.capacites}</p>
            <p className="mt-4 font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Comment voulez-vous ajouter cette source ?</p>
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
                    className="w-full rounded-lg border border-white/[0.08] bg-white/[0.02] px-3.5 py-3 text-left transition-colors hover:border-[#22D3EE]/40"
                  >
                    <div className="text-xs font-semibold text-white">{titre}</div>
                    <div className="mt-0.5 text-[10px] text-white/45">{desc}</div>
                  </button>
                  {mode === "profil" && (
                    <div className="mt-1.5 flex gap-1.5">
                      <select value={profil} onChange={(e) => setProfil(e.target.value)} data-testid="mode-profil-select" className="flex-1 rounded-md border border-white/10 bg-black/50 px-2 py-1.5 text-[11px] text-white/70 focus:outline-none">
                        <option value="">Choisir un profil…</option>
                        {catalogue.profils.filter((p) => p.applicable.includes(choisi.id)).map((p) => <option key={p.id} value={p.id}>{p.nom}</option>)}
                      </select>
                      <button disabled={!profil} onClick={() => onAjoute(choisi, "profil", { profilId: profil })} data-testid="mode-profil-ok" className="rounded-md bg-[#3B82F6] px-2.5 py-1.5 text-[11px] font-semibold text-white disabled:opacity-30">Appliquer</button>
                    </div>
                  )}
                  {mode === "dupliquer" && (
                    <div className="mt-1.5 flex gap-1.5">
                      <select value={dupliquerDe} onChange={(e) => setDupliquerDe(e.target.value)} data-testid="mode-dupliquer-select" className="flex-1 rounded-md border border-white/10 bg-black/50 px-2 py-1.5 text-[11px] text-white/70 focus:outline-none">
                        <option value="">Instance à dupliquer…</option>
                        {instancesDe(choisi.id).map((s) => <option key={s.id} value={s.id}>{s.nom}</option>)}
                      </select>
                      <button disabled={!dupliquerDe} onClick={() => onAjoute(choisi, "dupliquer", { sourceId: dupliquerDe })} data-testid="mode-dupliquer-ok" className="rounded-md bg-[#3B82F6] px-2.5 py-1.5 text-[11px] font-semibold text-white disabled:opacity-30">Dupliquer</button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
