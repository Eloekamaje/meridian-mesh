import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { CaretRight, Flask, MagnifyingGlass, Sparkle, X } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { usePerimetre } from "@/lib/perimetre";
import { useContexte } from "@/lib/contexte";
import AtlasEchelle from "@/components/map/AtlasEchelle";
import PanneauJumeau from "@/components/map/PanneauJumeau";

// ============================================================================================
// LABORATOIRE — l'ATLAS À L'ÉCHELLE, avec des CENTAINES DE DOMAINES.
//
// Remplace l'ancien « Atlas vivant » (projection isolée, données et rendu qui n'étaient pas ceux du produit).
// Ici, aucun rendu maison : c'est le MÊME composant que l'Atlas réel bascule sur au-delà de 300 jumeaux
// (`AtlasEchelle`, servie par `GET /api/mesh/vue` — voir docs/ATLAS.md §15) et le MÊME comportement — fiche
// d'aperçu au survol, panneau de détail à droite, recherche qui vole jusqu'à sa cible, « Parler au jumeau » qui
// ouvre un travail — sauf que le jeu de données est un essai synthétique : jusqu'à des millions de jumeaux
// répartis sur des centaines de domaines, disposés en amas organique (comme graph.html), pas en grille de
// territoires. Dézoomé au maximum, l'œil ne distingue plus que des galaxies de couleur ; en zoomant, elles se
// résolvent en grappes puis, tout près, en robots individuels — même langage visuel qu'à petite échelle.
// ============================================================================================

const TAILLES = [[1000, "1 000"], [10000, "10 000"], [100000, "100 000"], [1000000, "1 M"], [5000000, "5 M"]];
const DOMAINES_PRESETS = [[8, "8"], [50, "50"], [150, "150"], [400, "400"], [1000, "1 000"]];
const compact = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)} M` : n >= 1e3 ? `${(n / 1e3).toFixed(n >= 1e4 ? 0 : 1)} k` : String(n)).replace(".", ",");

export default function LaboAtlasEtendu() {
  const navigate = useNavigate();
  const { info } = usePerimetre();
  const { setRepliAuto } = useContexte();
  const [n, setN] = useState(100000);
  const [domaines, setDomaines] = useState(150);
  const [graine, setGraine] = useState(1);
  const [rep, setRep] = useState(null); // dernière vue reçue par AtlasEchelle (domaines, couleurs, familles, tailles)
  const [selection, setSelection] = useState(null); // jumeau détaillé, chargé à la demande au clic
  const [chargement, setChargement] = useState(false);
  const [recherche, setRecherche] = useState("");
  const [rechercheOuverte, setRechercheOuverte] = useState(false);
  const [legendeOuverte, setLegendeOuverte] = useState(true);
  const [filtreLegende, setFiltreLegende] = useState("");
  const [toutLaLegende, setToutLaLegende] = useState(false);
  const cleAtlas = `${n}-${domaines}-${graine}`;

  // Le menu se replie tant qu'un panneau est ouvert — même règle que sur l'Atlas réel
  useEffect(() => { setRepliAuto(!!selection); return () => setRepliAuto(false); }, [selection, setRepliAuto]);

  // Statistiques et légende : on relit ce que le composant a reçu du serveur, à un rythme raisonnable
  useEffect(() => {
    const t = setInterval(() => { const r = window.__atlasEchelle?.rep?.(); if (r) setRep(r); }, 300);
    return () => clearInterval(t);
  }, [cleAtlas]);

  // Clic sur un jumeau : on va chercher sa fiche complète (mission, propriétaire, sources…) — le panneau est
  // alors EXACTEMENT celui de l'Atlas réel, pas une version allégée du laboratoire
  const choisir = useCallback(async (cible) => {
    setChargement(true);
    try {
      const { data } = await api.get("/mesh/vue/jumeau", { params: { i: cible.i, synthetique: n, domaines, graine } });
      setSelection(data);
    } catch {
      toast.error("Jumeau introuvable");
    } finally {
      setChargement(false);
    }
  }, [n, domaines, graine]);

  // « Parler au jumeau » — même geste que sur l'Atlas réel : ouvre un travail avec l'accueil de Flore. Sans
  // `jumeaux` (l'identifiant synthétique n'existe dans aucun périmètre réel — l'y mettre bloquerait ensuite
  // tout accès au travail, « hors de votre périmètre ») : le jumeau reste nommé dans le titre et l'objectif.
  const parlerAuJumeau = async (j) => {
    try {
      const now = new Date().toISOString();
      const accueil = `Vous voulez parler de « ${j.nom} » (${j.domaine}). ${j.mission}. Je le connais avec ${j.couverture} % de couverture. Que voulez-vous savoir ?`;
      const { data } = await api.post("/cases", {
        titre: `Échange avec ${j.nom}`, type: "demande", objectif: `Comprendre ${j.nom} (${j.domaine}) — essai du laboratoire`,
        espace: info?.espace?.id,
      });
      await api.patch(`/cases/${data.id}`, { conversation: [{ role: "flore", comportement: "expliquer", texte: accueil, quand: now }] });
      navigate(`/travaux/${data.id}`);
    } catch {
      toast.error("Impossible d'ouvrir le travail");
    }
  };

  // Recherche : un numéro vole jusqu'à ce jumeau, un nom (« Domaine 42 ») jusqu'à ce domaine — mêmes coordonnées
  // que celles que le rendu utilise réellement (voir mesh_vue_routes.localiser)
  const voler = useCallback(async (q) => {
    if (!q) return;
    try {
      const { data: cible } = await api.get("/mesh/vue/localiser", { params: { q, synthetique: n, domaines, graine } });
      if (cible.type === "jumeau") {
        window.__atlasEchelle?.aller(cible.x, cible.y, 1.4);
        choisir(cible);
      } else {
        const zoom = Math.min(6, Math.max(0.03, 260 / Math.max(cible.r, 1)));
        window.__atlasEchelle?.aller(cible.x, cible.y, zoom);
        toast.info(`${cible.nom} · ${compact(cible.n)} jumeaux`);
      }
    } catch {
      toast.error(`Introuvable : ${q}`);
    }
  }, [n, domaines, graine, choisir]);
  const chercher = (e) => { e.preventDefault(); voler(recherche.trim()); setRecherche(""); setRechercheOuverte(false); };

  // Légende : classée par population ; à des centaines de domaines, les 14 plus gros d'abord, le reste sur demande
  // (avec un filtre texte) — plutôt qu'une liste à cases à cocher illisible au-delà d'une vingtaine d'entrées.
  const domainesTries = useMemo(() => {
    if (!rep?.domaines) return [];
    return rep.domaines.map((nom, d) => ({ d, nom, couleur: rep.domaines_couleur?.[d], famille: rep.domaines_famille?.[d], taille: rep.domaines_taille?.[d] || 0 }))
      .sort((a, b) => b.taille - a.taille);
  }, [rep]);
  const domainesFiltres = useMemo(() => {
    const q = filtreLegende.trim().toLowerCase();
    const liste = q ? domainesTries.filter((x) => x.nom.toLowerCase().includes(q)) : domainesTries;
    return toutLaLegende || q ? liste : liste.slice(0, 14);
  }, [domainesTries, filtreLegende, toutLaLegende]);

  const changerTaille = (v) => { setSelection(null); setN(v); };
  const changerDomaines = (v) => { setSelection(null); setDomaines(v); };

  return (
    <div className="relative flex h-full min-h-0 w-full" data-testid="labo-atlas-etendu">
      <div className="relative min-h-0 min-w-0 flex-1">
        <AtlasEchelle key={cleAtlas} synthetique={n} domaines={domaines} selectionId={selection?.id || null} selectionIndex={selection?.i ?? null} onChoisir={choisir} />

        {/* Bandeau du laboratoire — n, domaines, graine, recherche */}
        <div className="glass pointer-events-auto absolute left-3 top-3 z-10 w-[300px] space-y-2.5 rounded-xl p-3" data-testid="labo-atlas-etendu-hud">
          <div className="flex items-center gap-2">
            <span className="rounded-lg border border-[#60A5FA]/25 bg-[#60A5FA]/[0.08] p-1.5 text-[#60A5FA]"><Flask size={14} /></span>
            <div className="min-w-0 leading-tight">
              <div className="truncate text-xs font-bold text-white">Laboratoire · Atlas à l'échelle</div>
              <div className="text-[10px] text-[#7C93A8]">Mêmes comportements, des centaines de domaines</div>
            </div>
          </div>

          <div>
            <div className="mb-1 font-code text-[9px] uppercase tracking-[0.16em] text-[#7C93A8]">Jumeaux</div>
            <div className="flex flex-wrap gap-1">
              {TAILLES.map(([v, l]) => (
                <button key={v} onClick={() => changerTaille(v)} data-testid={`labo-etendu-n-${v}`} aria-pressed={n === v}
                  className={`rounded-md px-2 py-1 text-[11px] font-medium transition-colors ${n === v ? "bg-[#60A5FA] text-[#071019]" : "border border-white/10 text-[#94A3B8] hover:text-white"}`}>{l}</button>
              ))}
            </div>
          </div>

          <div>
            <div className="mb-1 font-code text-[9px] uppercase tracking-[0.16em] text-[#7C93A8]">Domaines</div>
            <div className="flex flex-wrap gap-1">
              {DOMAINES_PRESETS.map(([v, l]) => (
                <button key={v} onClick={() => changerDomaines(v)} data-testid={`labo-etendu-domaines-${v}`} aria-pressed={domaines === v}
                  className={`rounded-md px-2 py-1 text-[11px] font-medium transition-colors ${domaines === v ? "bg-[#60A5FA] text-[#071019]" : "border border-white/10 text-[#94A3B8] hover:text-white"}`}>{l}</button>
              ))}
              <input type="number" min={1} max={2000} value={domaines} onChange={(e) => changerDomaines(Math.max(1, Math.min(2000, Number(e.target.value) || 1)))}
                data-testid="labo-etendu-domaines-saisie" className="h-6 w-16 rounded-md border border-white/10 bg-[#071019] px-1.5 text-[11px] text-white outline-none" />
            </div>
          </div>

          <button onClick={() => setGraine((g) => g + 1)} data-testid="labo-etendu-rejouer" className="w-full rounded-md border border-white/10 py-1 text-[10px] text-[#94A3B8] hover:text-white">
            Rejouer avec une autre disposition (graine {graine})
          </button>

          <form onSubmit={chercher} className="flex items-center gap-2 rounded-lg border border-white/10 bg-[#071019] px-2.5" onFocus={() => setRechercheOuverte(true)}>
            <MagnifyingGlass size={13} className="text-[#7C93A8]" />
            <input value={recherche} onChange={(e) => setRecherche(e.target.value)} placeholder="N° de jumeau, ou « Domaine 42 »"
              data-testid="labo-etendu-recherche" className="min-h-[30px] flex-1 bg-transparent text-xs text-white outline-none placeholder:text-[#526578]" />
            {recherche && <button type="button" onClick={() => setRecherche("")} className="text-[#7C93A8] hover:text-white"><X size={12} /></button>}
          </form>
          {rechercheOuverte && <p className="font-code text-[9px] text-[#526578]">Entrée pour voler jusqu'à la cible.</p>}

          {rep && (
            <div className="space-y-0.5 rounded-lg bg-white/[0.03] p-2 font-code text-[10px] leading-relaxed text-[#94A3B8]" data-testid="labo-etendu-stats">
              <div>{compact(rep.n_total)} jumeaux · {rep.domaines?.length} domaines · {rep.domaines_famille ? new Set(rep.domaines_famille).size : "—"} familles</div>
              <div>{compact(rep.jumeaux?.length || 0)} / {compact(rep.n_total)} jumeaux affichés · {rep.duree_ms} ms serveur</div>
            </div>
          )}
        </div>

        {/* Légende des domaines — groupée par famille (teinte), triée par population, filtrable à des centaines d'entrées */}
        {rep?.domaines?.length > 0 && (
          <div className="glass pointer-events-auto absolute bottom-3 left-3 z-10 w-[240px] rounded-xl p-2.5" data-testid="labo-etendu-legende">
            <button onClick={() => setLegendeOuverte((o) => !o)} aria-expanded={legendeOuverte} className="flex w-full items-center justify-between font-code text-[9px] uppercase tracking-wider text-[#7C93A8] hover:text-white">
              <span className="flex items-center gap-1"><CaretRight size={10} className={`transition-transform ${legendeOuverte ? "rotate-90" : ""}`} /> Domaines ({rep.domaines.length})</span>
            </button>
            {legendeOuverte && (
              <div className="mt-2 space-y-1.5">
                {rep.domaines.length > 14 && (
                  <input value={filtreLegende} onChange={(e) => setFiltreLegende(e.target.value)} placeholder="Filtrer…" data-testid="labo-etendu-legende-filtre"
                    className="h-6 w-full rounded-md border border-white/10 bg-[#071019] px-2 text-[10px] text-white outline-none placeholder:text-[#526578]" />
                )}
                <div className="max-h-[220px] space-y-0.5 overflow-y-auto pr-1">
                  {domainesFiltres.map((x) => (
                    <button key={x.d} onClick={() => voler(x.nom)} data-testid={`labo-etendu-legende-${x.d}`}
                      className="flex w-full items-center gap-1.5 rounded px-1 py-0.5 text-left text-[10px] text-[#94A3B8] hover:bg-white/[0.06] hover:text-white">
                      <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: x.couleur }} />
                      <span className="min-w-0 flex-1 truncate">{x.nom}</span>
                      <span className="shrink-0 font-code text-[9px] text-[#64748B]">{compact(x.taille)}</span>
                    </button>
                  ))}
                </div>
                {!toutLaLegende && !filtreLegende && domainesTries.length > 14 && (
                  <button onClick={() => setToutLaLegende(true)} data-testid="labo-etendu-legende-tout" className="text-[10px] text-[#60A5FA] hover:underline">
                    Voir les {domainesTries.length - 14} autres →
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        <div className="pointer-events-none absolute bottom-3 right-3 z-10 rounded-md bg-[#071019]/80 px-2.5 py-1 font-code text-[10px] text-[#7C93A8]">
          Molette : zoom · glisser : déplacer · clic sur une grappe : plonger
        </div>

        <Link to="/labo/serveur" className="glass pointer-events-auto absolute right-3 top-3 z-10 flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[10px] text-[#94A3B8] hover:text-white" data-testid="labo-etendu-vers-serveur">
          Vue brute (sans comportements) →
        </Link>
      </div>

      {selection && (
        <PanneauJumeau
          jumeau={selection}
          favori={false}
          onBasculerFavori={undefined}
          statsTwin={{ flux: selection.degre, ecarts: selection.ecart ? 1 : 0 }}
          onInterroger={() => parlerAuJumeau(selection)}
          voisins={[]}
          relationsRecentes={[]}
          onChoisirVoisin={undefined}
          onExplorerRelations={undefined}
          onOuvrirInvestigation={undefined}
          onFermer={() => setSelection(null)}
        />
      )}
      {chargement && !selection && (
        <div className="glass pointer-events-none absolute right-3 top-3 z-20 flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-[#94A3B8]">
          <Sparkle size={13} className="text-[#60A5FA]" /> Flore prépare la fiche du jumeau…
        </div>
      )}
    </div>
  );
}
