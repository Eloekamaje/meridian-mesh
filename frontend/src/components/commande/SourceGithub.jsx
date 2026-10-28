import { useEffect, useState } from "react";
import { CaretUpDown, GitBranch, Plus, X } from "@phosphor-icons/react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import api from "@/lib/api";

// Source GitHub de la commande : une connexion de l'espace d'abord, puis des couples dépôt/branche choisis par
// autocomplétion parmi ce que cette connexion peut lire, une ligne à la fois.
export const BORDURE = "border-[rgba(148,163,184,0.16)]";
export const ETIQUETTE = "font-code text-[10px] uppercase tracking-[0.15em] text-[#7C93A8]";
export const CHAMP = `rounded-md border ${BORDURE} bg-[#0F1D28] px-3 py-2 text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/60 focus:outline-none`;
const DELAI_RECHERCHE = 250;

// Charge les propositions de `chemin` (avec ?q=) pendant la saisie ; ignore les réponses dépassées.
function usePropositions(chemin, recherche, actif) {
  const [etat, setEtat] = useState({ items: [], chargement: false, erreur: null });
  useEffect(() => {
    if (!actif || !chemin) return undefined;
    let vivant = true;
    setEtat((e) => ({ ...e, chargement: true, erreur: null }));
    const t = setTimeout(() => {
      api.get(chemin, { params: { q: recherche } })
        .then(({ data }) => vivant && setEtat({ items: data, chargement: false, erreur: null }))
        .catch((e) => vivant && setEtat({ items: [], chargement: false, erreur: e.response?.data?.detail || "GitHub indisponible" }));
    }, DELAI_RECHERCHE);
    return () => { vivant = false; clearTimeout(t); };
  }, [chemin, recherche, actif]);
  return etat;
}

// Champ à autocomplétion (motif combobox : clavier et lecteurs d'écran gérés par cmdk et Radix).
export function Choix({ valeur, placeholder, chemin, rendu, valeurDe, onChoisir, desactive, label, testid }) {
  const [ouvert, setOuvert] = useState(false);
  const [recherche, setRecherche] = useState("");
  const { items, chargement, erreur } = usePropositions(chemin, recherche, ouvert);
  return (
    <Popover open={ouvert} onOpenChange={setOuvert}>
      <PopoverTrigger asChild>
        <button type="button" role="combobox" aria-expanded={ouvert} aria-label={label} disabled={desactive} data-testid={testid}
          className={`${CHAMP} flex w-full items-center justify-between gap-2 text-left disabled:opacity-40`}>
          <span className={`truncate ${valeur ? "" : "text-[#7C93A8]"}`}>{valeur || placeholder}</span>
          <CaretUpDown size={12} aria-hidden className="shrink-0 text-[#7C93A8]" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className={`w-[--radix-popover-trigger-width] min-w-[260px] border ${BORDURE} bg-[#0F1D28] p-0 text-[#F2F6F8]`}>
        <Command shouldFilter={false} className="bg-transparent text-[#F2F6F8]">
          <CommandInput value={recherche} onValueChange={setRecherche} placeholder="Rechercher…" className="text-xs" />
          <CommandList>
            <CommandEmpty className="px-3 py-4 text-xs text-[#94A3B8]">
              {chargement ? "Recherche…" : erreur || "Aucun résultat"}
            </CommandEmpty>
            {items.map((item) => (
              <CommandItem key={valeurDe(item)} value={valeurDe(item)} onSelect={() => { onChoisir(item); setOuvert(false); setRecherche(""); }}
                className="cursor-pointer text-xs data-[selected=true]:bg-[rgba(96,165,250,0.15)] data-[selected=true]:text-[#F2F6F8]">
                {rendu(item)}
              </CommandItem>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

// Connexions GitHub de l'espace : déclarées une fois (jeton vérifié, déposé dans Vault), choisies ensuite.
function Connexion({ choisie, onChoisir }) {
  const [connexions, setConnexions] = useState(null);
  const [ajout, setAjout] = useState(false);
  const [saisie, setSaisie] = useState("");
  const [etat, setEtat] = useState({ encours: false, erreur: null });

  useEffect(() => {
    let vivant = true;
    api.get("/connexions/github")
      .then(({ data }) => { if (vivant) { setConnexions(data); setAjout(data.length === 0); } })
      .catch(() => vivant && setConnexions([]));
    return () => { vivant = false; };
  }, []);

  const declarer = async () => {
    setEtat({ encours: true, erreur: null });
    try {
      const { data } = await api.post("/connexions/github", { jeton: saisie });
      setConnexions((liste) => [...(liste || []).filter((c) => c.id !== data.id), data]);
      setSaisie("");
      setAjout(false);
      setEtat({ encours: false, erreur: null });
      onChoisir(data.id);
    } catch (e) {
      setEtat({ encours: false, erreur: e.response?.data?.detail || "Vérification impossible" });
    }
  };

  if (!connexions) return <p className="text-[11px] text-[#7C93A8]">Chargement des connexions…</p>;
  return (
    <fieldset>
      <legend className={ETIQUETTE}>1 · Compte GitHub</legend>
      {connexions.length > 0 && (
        <div role="radiogroup" aria-label="Connexion GitHub" className="mt-2 space-y-1.5">
          {connexions.map((c) => (
            <label key={c.id} className={`flex cursor-pointer items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs ${c.id === choisie ? "border-[#60A5FA]/60 bg-[rgba(96,165,250,0.08)]" : BORDURE}`}>
              <input type="radio" name="connexion-github" checked={c.id === choisie} onChange={() => onChoisir(c.id)} className="accent-[#60A5FA]" data-testid={`insp-github-connexion-${c.id}`} />
              {c.avatar && <img src={c.avatar} alt="" className="h-5 w-5 rounded-full" />}
              <span className="text-[#F2F6F8]">{c.nom}</span>
              <span className="font-code text-[10px] text-[#7C93A8]">@{c.login}</span>
            </label>
          ))}
        </div>
      )}
      {ajout ? (
        <div className="mt-2">
          <label htmlFor="github-jeton" className="text-[11px] text-[#94A3B8]">Jeton d'accès GitHub (lecture des dépôts)</label>
          <div className="mt-1 flex gap-2">
            <input id="github-jeton" type="password" autoComplete="off" value={saisie} onChange={(e) => setSaisie(e.target.value)}
              placeholder="Collez le jeton" data-testid="insp-github-jeton" className={`${CHAMP} flex-1`} />
            <button type="button" onClick={declarer} disabled={!saisie.trim() || etat.encours} data-testid="insp-github-verifier"
              className="rounded-md bg-[#60A5FA] px-3 text-xs font-semibold text-[#071019] hover:bg-[#93C5FD] disabled:opacity-40">
              {etat.encours ? "Vérification…" : "Vérifier"}
            </button>
          </div>
          <p className="mt-1 text-[10px] text-[#7C93A8]">Le jeton est vérifié auprès de GitHub puis conservé dans Vault ; il ne revient jamais à l'écran.</p>
        </div>
      ) : (
        <button type="button" onClick={() => setAjout(true)} data-testid="insp-github-nouvelle-connexion"
          className="mt-2 flex items-center gap-1.5 text-xs text-[#60A5FA] hover:underline">
          <Plus size={12} aria-hidden /> Nouvelle connexion
        </button>
      )}
      <div aria-live="polite" className="mt-1 min-h-[16px] text-[11px] text-[#F87171]">{etat.erreur}</div>
    </fieldset>
  );
}

export default function SourceGithub({ source, onChange }) {
  const config = source.config || {};
  const lignes = config.selection?.length ? config.selection : [{ depot: "", branche: "" }];
  const base = `/connexions/github/${config.connexion}`;
  const pret = Boolean(config.connexion);
  const majLignes = (nouvelles) => onChange(source.id, { config: { ...config, selection: nouvelles } });
  const majLigne = (i, patch) => majLignes(lignes.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  const dejaChoisis = new Set(lignes.map((l) => l.depot).filter(Boolean));

  return (
    <div className="space-y-4">
      <Connexion choisie={config.connexion} onChoisir={(id) => onChange(source.id, { config: { ...config, connexion: id, selection: id === config.connexion ? config.selection : [] } })} />

      <fieldset disabled={!pret}>
        <legend className={ETIQUETTE}>2 · Dépôts et branches</legend>
        {!pret && <p className="mt-1 text-[11px] text-[#7C93A8]">Choisissez d'abord une connexion : les dépôts proposés sont ceux qu'elle peut lire.</p>}
        <ul className="mt-2 space-y-2" data-testid="insp-github-lignes">
          {lignes.map((l, i) => (
            <li key={i} className="flex items-center gap-2">
              <div className="min-w-0 flex-[3]">
                <Choix label={`Dépôt ${i + 1}`} testid={`insp-github-depot-${i}`} valeur={l.depot} placeholder="Choisir un dépôt" desactive={!pret}
                  chemin={`${base}/depots`} valeurDe={(d) => d.nom}
                  rendu={(d) => (
                    <span className="flex w-full min-w-0 flex-col">
                      <span className="flex items-center gap-2">
                        <span className={`truncate ${dejaChoisis.has(d.nom) ? "text-[#7C93A8]" : ""}`}>{d.nom}</span>
                        <span className="ml-auto shrink-0 font-code text-[9px] text-[#7C93A8]">{[d.langage, d.prive ? "privé" : "public"].filter(Boolean).join(" · ")}</span>
                      </span>
                      {d.description && <span className="truncate text-[10px] text-[#7C93A8]">{d.description}</span>}
                    </span>
                  )}
                  onChoisir={(d) => majLigne(i, { depot: d.nom, branche: d.defaut })} />
              </div>
              <div className="min-w-0 flex-[2]">
                <Choix label={`Branche du dépôt ${i + 1}`} testid={`insp-github-branche-${i}`} valeur={l.branche && `⎇ ${l.branche}`} placeholder="Branche" desactive={!pret || !l.depot}
                  chemin={l.depot ? `${base}/branches?depot=${encodeURIComponent(l.depot)}` : null} valeurDe={(b) => b}
                  rendu={(b) => <span className="flex items-center gap-1.5"><GitBranch size={11} aria-hidden />{b}</span>}
                  onChoisir={(b) => majLigne(i, { branche: b })} />
              </div>
              <button type="button" aria-label={`Retirer le dépôt ${i + 1}`} onClick={() => majLignes(lignes.filter((_, j) => j !== i))}
                disabled={lignes.length === 1 && !l.depot} className="rounded p-1 text-[#7C93A8] hover:text-[#F2F6F8] disabled:opacity-30">
                <X size={13} />
              </button>
            </li>
          ))}
        </ul>
        <button type="button" onClick={() => majLignes([...lignes, { depot: "", branche: "" }])} disabled={!pret || !lignes.at(-1)?.depot}
          data-testid="insp-github-ajouter" className="mt-2 flex items-center gap-1.5 text-xs text-[#60A5FA] hover:underline disabled:opacity-40 disabled:no-underline">
          <Plus size={12} aria-hidden /> Ajouter un dépôt
        </button>
      </fieldset>
    </div>
  );
}
