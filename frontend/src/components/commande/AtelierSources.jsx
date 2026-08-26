import { useMemo, useState } from "react";
import { CaretDown, CaretRight, MagnifyingGlass, Plus, UploadSimple, Lightning } from "@phosphor-icons/react";
import { STATUTS_SOURCE, estErreurSource, ENVIRONNEMENTS } from "@/lib/sources";

const REGROUPEMENTS = [
  ["aucun", "Sans regroupement"],
  ["connecteur", "Par connecteur"],
  ["environnement", "Par environnement"],
  ["proprietaire", "Par équipe"],
  ["statut", "Par statut"],
];

export default function AtelierSources({ sources, catalogue, sourceActiveId, onSelect, selLot, setSelLot, onTester, onOuvrirTiroir, onOuvrirImport, onLot }) {
  const [recherche, setRecherche] = useState("");
  const [filtreStatut, setFiltreStatut] = useState(null);
  const [filtreConnecteur, setFiltreConnecteur] = useState("");
  const [filtreEnv, setFiltreEnv] = useState("");
  const [groupement, setGroupement] = useState("connecteur");
  const [pliés, setPliés] = useState({});

  const nomConnecteur = (id) => catalogue.connecteurs.find((c) => c.id === id)?.nom || id;

  const compteurs = useMemo(() => ({
    total: sources.length,
    pretes: sources.filter((s) => s.statut === "prete").length,
    aConfigurer: sources.filter((s) => ["ajoutee", "a_configurer", "prete_a_tester"].includes(s.statut)).length,
    erreurs: sources.filter((s) => estErreurSource(s.statut)).length,
  }), [sources]);

  const filtrees = useMemo(() => {
    const q = recherche.trim().toLowerCase();
    return sources.filter((s) => {
      if (filtreStatut === "prete" && s.statut !== "prete") return false;
      if (filtreStatut === "a_configurer" && !["ajoutee", "a_configurer", "prete_a_tester"].includes(s.statut)) return false;
      if (filtreStatut === "erreur" && !estErreurSource(s.statut)) return false;
      if (filtreConnecteur && s.connecteur !== filtreConnecteur) return false;
      if (filtreEnv && s.environnement !== filtreEnv) return false;
      if (q && ![s.nom, nomConnecteur(s.connecteur), s.proprietaire, s.perimetre].join(" ").toLowerCase().includes(q)) return false;
      return true;
    });
  }, [sources, recherche, filtreStatut, filtreConnecteur, filtreEnv]);

  const groupes = useMemo(() => {
    if (groupement === "aucun") return [["", filtrees]];
    const map = {};
    filtrees.forEach((s) => {
      const cle = groupement === "connecteur" ? nomConnecteur(s.connecteur) : groupement === "statut" ? (STATUTS_SOURCE[s.statut]?.label || s.statut) : s[groupement] || "—";
      (map[cle] = map[cle] || []).push(s);
    });
    return Object.entries(map).sort((a, b) => a[0].localeCompare(b[0]));
  }, [filtrees, groupement]);

  const basculerLot = (id) => setSelLot(selLot.includes(id) ? selLot.filter((x) => x !== id) : [...selLot, id]);

  const INDICS = [
    { cle: null, label: "sources ajoutées", n: compteurs.total, couleur: "#E5E7EB", testid: "indic-total" },
    { cle: "prete", label: "prêtes", n: compteurs.pretes, couleur: "#10B981", testid: "indic-pretes" },
    { cle: "a_configurer", label: "à configurer", n: compteurs.aConfigurer, couleur: "#FBBF24", testid: "indic-a-configurer" },
    { cle: "erreur", label: "en erreur", n: compteurs.erreurs, couleur: "#F87171", testid: "indic-erreurs" },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="atelier-sources">
      {/* Indicateurs de préparation — cliquables, filtrent la file */}
      <div className="flex flex-wrap items-center gap-2" data-testid="indicateurs">
        {INDICS.map((i) => (
          <button
            key={i.label}
            onClick={() => setFiltreStatut(filtreStatut === i.cle ? null : i.cle)}
            data-testid={i.testid}
            className={`flex items-baseline gap-1.5 rounded-lg border px-3 py-1.5 transition-colors ${filtreStatut === i.cle || (i.cle === null && !filtreStatut) ? "border-white/30 bg-white/[0.06]" : "border-white/[0.08] hover:border-white/20"}`}
          >
            <span className="font-display text-lg font-bold" style={{ color: i.couleur }}>{i.n}</span>
            <span className="font-code text-[10px] text-white/50">{i.label}</span>
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2">
          <button onClick={onOuvrirImport} data-testid="import-btn" className="flex items-center gap-1.5 rounded-md border border-white/15 px-2.5 py-1.5 text-[11px] text-white/70 transition-colors hover:text-white">
            <UploadSimple size={13} /> Importer
          </button>
          <button onClick={onOuvrirTiroir} data-testid="ajouter-source-btn" className="flex items-center gap-1.5 rounded-md bg-[#3B82F6] px-3 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-[#2F6FDB]">
            <Plus size={13} /> Ajouter une source
          </button>
        </div>
      </div>

      {/* Barre de recherche et filtres */}
      <div className="mt-3 flex flex-wrap items-center gap-2" data-testid="file-outils">
        <div className="relative">
          <MagnifyingGlass size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-white/30" />
          <input value={recherche} onChange={(e) => setRecherche(e.target.value)} placeholder="Rechercher une instance…" data-testid="file-recherche"
            className="w-56 rounded-md border border-white/10 bg-black/40 py-1.5 pl-8 pr-3 text-xs text-white placeholder:text-white/25 focus:border-[#22D3EE]/50 focus:outline-none" />
        </div>
        <select value={filtreConnecteur} onChange={(e) => setFiltreConnecteur(e.target.value)} data-testid="filtre-connecteur" className="rounded-md border border-white/10 bg-black/40 px-2 py-1.5 text-xs text-white/70 focus:outline-none">
          <option value="">Tous connecteurs</option>
          {[...new Set(sources.map((s) => s.connecteur))].map((c) => <option key={c} value={c}>{nomConnecteur(c)}</option>)}
        </select>
        <select value={filtreEnv} onChange={(e) => setFiltreEnv(e.target.value)} data-testid="filtre-environnement" className="rounded-md border border-white/10 bg-black/40 px-2 py-1.5 text-xs text-white/70 focus:outline-none">
          <option value="">Tous environnements</option>
          {ENVIRONNEMENTS.map((e) => <option key={e} value={e}>{e}</option>)}
        </select>
        <select value={groupement} onChange={(e) => setGroupement(e.target.value)} data-testid="groupement" className="rounded-md border border-white/10 bg-black/40 px-2 py-1.5 text-xs text-white/70 focus:outline-none">
          {REGROUPEMENTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>

      {/* File des sources */}
      <div className="mt-3 min-h-0 flex-1 overflow-y-auto rounded-xl border border-white/[0.07]" data-testid="file-sources">
        {groupes.map(([groupe, lignes]) => (
          <div key={groupe || "toutes"}>
            {groupe && (
              <button onClick={() => setPliés({ ...pliés, [groupe]: !pliés[groupe] })} data-testid={`groupe-${groupe}`} className="sticky top-0 flex w-full items-center gap-2 border-b border-white/[0.07] bg-[#0C0C0C] px-4 py-2 text-left">
                {pliés[groupe] ? <CaretRight size={12} className="text-white/40" /> : <CaretDown size={12} className="text-white/40" />}
                <span className="font-code text-[10px] uppercase tracking-[0.15em] text-white/55">Groupe {groupe} · {lignes.length} instance{lignes.length > 1 ? "s" : ""}</span>
              </button>
            )}
            {!pliés[groupe] && lignes.map((s) => {
              const st = STATUTS_SOURCE[s.statut] || STATUTS_SOURCE.ajoutee;
              const active = sourceActiveId === s.id;
              return (
                <div
                  key={s.id}
                  onClick={() => onSelect(s.id)}
                  data-testid={`source-ligne-${s.id}`}
                  className={`rise flex cursor-pointer items-center gap-3 border-b border-white/[0.04] px-4 py-2.5 transition-colors ${active ? "bg-[#22D3EE]/[0.06]" : "hover:bg-white/[0.02]"}`}
                >
                  <input type="checkbox" checked={selLot.includes(s.id)} onClick={(e) => e.stopPropagation()} onChange={() => basculerLot(s.id)} data-testid={`lot-check-${s.id}`} className="h-3.5 w-3.5 shrink-0 accent-[#22D3EE]" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[13px] font-medium text-white/90">{s.nom}</div>
                    <div className="truncate font-code text-[9px] text-white/35">{nomConnecteur(s.connecteur)} · {s.environnement}{s.perimetre ? ` · ${s.perimetre}` : ""}{s.proprietaire ? ` · ${s.proprietaire}` : ""}</div>
                  </div>
                  {s.statut === "test_en_cours" && (
                    <div className="h-1 w-16 overflow-hidden rounded-full bg-white/10">
                      <div className="h-full w-1/2 animate-pulse rounded-full bg-[#3B82F6]" />
                    </div>
                  )}
                  <span className="shrink-0 rounded border px-1.5 py-0.5 font-code text-[9px]" style={{ color: st.couleur, borderColor: `${st.couleur}44`, backgroundColor: `${st.couleur}12` }} data-testid={`source-statut-${s.id}`}>
                    {st.label}
                  </span>
                  <span className="w-20 shrink-0 text-right font-code text-[9px] text-white/30">
                    {s.dernier_test ? `${s.dernier_test.date}` : "jamais testé"}
                  </span>
                </div>
              );
            })}
          </div>
        ))}
        {filtrees.length === 0 && (
          <div className="px-4 py-10 text-center text-sm text-white/35" data-testid="file-vide">Aucune source ne correspond — ajoutez une source ou élargissez les filtres.</div>
        )}
      </div>

      {/* Barre d'actions en lot */}
      {selLot.length > 0 && (
        <div className="glass rise mt-3 flex flex-wrap items-center gap-2 rounded-xl px-4 py-2.5" data-testid="lot-bar">
          <span className="font-code text-[11px] font-medium text-white" data-testid="lot-count">{selLot.length} source{selLot.length > 1 ? "s" : ""} sélectionnée{selLot.length > 1 ? "s" : ""}</span>
          <select onChange={(e) => e.target.value && onLot("profil", e.target.value)} value="" data-testid="lot-profil" className="rounded-md border border-white/15 bg-black/40 px-2 py-1.5 text-[11px] text-white/70 focus:outline-none">
            <option value="">Appliquer un profil…</option>
            {catalogue.profils.map((p) => <option key={p.id} value={p.id}>{p.nom}</option>)}
          </select>
          <select onChange={(e) => e.target.value && onLot("environnement", e.target.value)} value="" data-testid="lot-environnement" className="rounded-md border border-white/15 bg-black/40 px-2 py-1.5 text-[11px] text-white/70 focus:outline-none">
            <option value="">Définir l'environnement…</option>
            {ENVIRONNEMENTS.map((e) => <option key={e} value={e}>{e}</option>)}
          </select>
          <select onChange={(e) => e.target.value && onLot("frequence", e.target.value)} value="" data-testid="lot-frequence" className="rounded-md border border-white/15 bg-black/40 px-2 py-1.5 text-[11px] text-white/70 focus:outline-none">
            <option value="">Modifier la fréquence…</option>
            {["horaire", "quotidienne", "hebdomadaire"].map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
          <button onClick={() => onTester(selLot)} data-testid="lot-tester-btn" className="flex items-center gap-1.5 rounded-md border border-[#3B82F6]/40 px-2.5 py-1.5 text-[11px] text-[#3B82F6] transition-colors hover:bg-[#3B82F6]/10">
            <Lightning size={12} /> Tester les connexions
          </button>
          <button onClick={() => onLot("supprimer")} data-testid="lot-supprimer-btn" className="rounded-md border border-[#F87171]/40 px-2.5 py-1.5 text-[11px] text-[#F87171] transition-colors hover:bg-[#F87171]/10">
            Supprimer de la commande
          </button>
          <button onClick={() => setSelLot([])} data-testid="lot-annuler-btn" className="text-[11px] text-white/40 hover:text-white">✕</button>
        </div>
      )}
    </div>
  );
}
