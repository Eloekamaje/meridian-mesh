import { useEffect, useState } from "react";
import { Plus } from "@phosphor-icons/react";
import api from "@/lib/api";
import { BORDURE, CHAMP, ETIQUETTE, Choix } from "@/components/commande/SourceGithub";

// Source « connexion + périmètre » de la commande (Confluence, Jira…) : une connexion de l'espace d'abord (e-mail +
// jeton d'API), puis le périmètre choisi par autocomplétion parmi ceux que cette connexion peut lire.
// `cfg` : { systeme, nom, perimetre: { cle, titre, label, placeholder, prefixe } }.
function Connexion({ cfg, choisie, onChoisir }) {
  const { systeme, nom } = cfg;
  const [connexions, setConnexions] = useState(null);
  const [ajout, setAjout] = useState(false);
  const [saisie, setSaisie] = useState({ email: "", jeton: "" });
  const [etat, setEtat] = useState({ encours: false, erreur: null });

  useEffect(() => {
    let vivant = true;
    api.get(`/connexions/${systeme}`)
      .then(({ data }) => { if (vivant) { setConnexions(data); setAjout(data.length === 0); } })
      .catch(() => vivant && setConnexions([]));
    return () => { vivant = false; };
  }, []);

  const declarer = async () => {
    setEtat({ encours: true, erreur: null });
    try {
      const { data } = await api.post(`/connexions/${systeme}`, saisie);
      setConnexions((liste) => [...(liste || []).filter((c) => c.id !== data.id), data]);
      setSaisie({ email: "", jeton: "" });
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
      <legend className={ETIQUETTE}>1 · Compte {nom}</legend>
      {connexions.length > 0 && (
        <div role="radiogroup" aria-label={`Connexion ${nom}`} className="mt-2 space-y-1.5">
          {connexions.map((c) => (
            <label key={c.id} className={`flex cursor-pointer items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs ${c.id === choisie ? "border-[#60A5FA]/60 bg-[rgba(96,165,250,0.08)]" : BORDURE}`}>
              <input type="radio" name={`connexion-${systeme}`} checked={c.id === choisie} onChange={() => onChoisir(c.id)} className="accent-[#60A5FA]" data-testid={`insp-${systeme}-connexion-${c.id}`} />
              <span className="text-[#F2F6F8]">{c.nom}</span>
              <span className="font-code text-[10px] text-[#7C93A8]">{c.login}</span>
            </label>
          ))}
        </div>
      )}
      {ajout ? (
        <div className="mt-2 space-y-1.5">
          <label htmlFor={`${systeme}-email`} className="text-[11px] text-[#94A3B8]">Adresse e-mail du compte Atlassian</label>
          <input id={`${systeme}-email`} type="email" autoComplete="off" value={saisie.email} onChange={(e) => setSaisie({ ...saisie, email: e.target.value })}
            data-testid={`insp-${systeme}-email`} className={`${CHAMP} w-full`} />
          <label htmlFor={`${systeme}-jeton`} className="text-[11px] text-[#94A3B8]">Jeton d'API ({cfg.perimetre.lecture})</label>
          <div className="flex gap-2">
            <input id={`${systeme}-jeton`} type="password" autoComplete="off" value={saisie.jeton} onChange={(e) => setSaisie({ ...saisie, jeton: e.target.value })}
              placeholder="Collez le jeton" data-testid={`insp-${systeme}-jeton`} className={`${CHAMP} flex-1`} />
            <button type="button" onClick={declarer} disabled={!saisie.email.trim() || !saisie.jeton.trim() || etat.encours} data-testid={`insp-${systeme}-verifier`}
              className="rounded-md bg-[#60A5FA] px-3 text-xs font-semibold text-[#071019] hover:bg-[#93C5FD] disabled:opacity-40">
              {etat.encours ? "Vérification…" : "Vérifier"}
            </button>
          </div>
          <p className="text-[10px] text-[#7C93A8]">Les identifiants sont vérifiés auprès de {nom} puis conservés dans Vault ; le jeton ne revient jamais à l'écran.</p>
        </div>
      ) : (
        <button type="button" onClick={() => setAjout(true)} data-testid={`insp-${systeme}-nouvelle-connexion`}
          className="mt-2 flex items-center gap-1.5 text-xs text-[#60A5FA] hover:underline">
          <Plus size={12} aria-hidden /> Nouvelle connexion
        </button>
      )}
      <div aria-live="polite" className="mt-1 min-h-[16px] text-[11px] text-[#F87171]">{etat.erreur}</div>
    </fieldset>
  );
}

export default function SourceConnexion({ cfg, source, onChange }) {
  const config = source.config || {};
  const { systeme, perimetre: p } = cfg;
  const pret = Boolean(config.connexion);
  return (
    <div className="space-y-4">
      <Connexion cfg={cfg} choisie={config.connexion} onChoisir={(id) => onChange(source.id, { config: { ...config, connexion: id, [p.cle]: id === config.connexion ? config[p.cle] : "" } })} />
      <fieldset disabled={!pret}>
        <legend className={ETIQUETTE}>2 · {p.titre}</legend>
        {!pret && <p className="mt-1 text-[11px] text-[#7C93A8]">Choisissez d'abord une connexion : les {p.pluriel} proposés sont ceux qu'elle peut lire.</p>}
        <div className="mt-2">
          <Choix label={p.label} testid={`insp-${systeme}-${p.cle}`} valeur={config[p.cle]} placeholder={p.placeholder} desactive={!pret}
            chemin={`/connexions/${systeme}/${config.connexion}/perimetres`} valeurDe={(e) => e.cle}
            rendu={(e) => <span className="flex w-full items-center gap-2"><span className="truncate">{e.nom}</span><span className="ml-auto shrink-0 font-code text-[9px] text-[#7C93A8]">{e.cle}</span></span>}
            onChoisir={(e) => onChange(source.id, { config: { ...config, [p.cle]: e.cle }, perimetre: `${p.cle} ${e.cle}` })} />
        </div>
      </fieldset>
    </div>
  );
}
