import { Lightning, WarningCircle, X } from "@phosphor-icons/react";
import { STATUTS_SOURCE, ENVIRONNEMENTS } from "@/lib/sources";

export default function InspecteurSource({ source, connecteur, onChange, onTester, onFermer }) {
  if (!source) {
    return (
      <div className="flex h-full items-center justify-center rounded-xl border border-dashed border-[rgba(148,163,184,0.16)] text-center" data-testid="inspecteur-vide">
        <p className="max-w-[220px] text-xs leading-relaxed text-[#7C93A8]">
          Sélectionnez une source dans la file pour afficher sa configuration ici.
        </p>
      </div>
    );
  }
  const st = STATUTS_SOURCE[source.statut] || STATUTS_SOURCE.ajoutee;
  const champ = (c) => (
    <div key={c.cle}>
      <label className="font-code text-[10px] uppercase tracking-[0.15em] text-[#7C93A8]">
        {c.label}{c.requis && <span className="text-[#F87171]"> *</span>}
      </label>
      {c.type === "select" ? (
        <select value={source.config?.[c.cle] ?? c.defaut ?? ""} onChange={(e) => onChange(source.id, { config: { ...source.config, [c.cle]: e.target.value } })} data-testid={`insp-${c.cle}`} className="mt-1 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-3 py-2 text-xs text-[#F2F6F8] focus:border-[#25D0C8]/60 focus:outline-none">
          {c.options.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      ) : (
        <input
          type={c.type === "nombre" ? "number" : "text"}
          value={source.config?.[c.cle] ?? ""}
          onChange={(e) => onChange(source.id, { config: { ...source.config, [c.cle]: c.type === "nombre" ? Number(e.target.value) : e.target.value } })}
          placeholder={c.type === "liste" ? "valeur1, valeur2…" : c.type === "secret" ? "coffre/…" : ""}
          data-testid={`insp-${c.cle}`}
          className="mt-1 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-3 py-2 text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#25D0C8]/60 focus:outline-none"
        />
      )}
    </div>
  );

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-5" data-testid="inspecteur">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-display text-base font-bold text-[#F2F6F8]" data-testid="inspecteur-nom">{source.nom}</h3>
          <p className="mt-0.5 font-code text-[10px] text-[#7C93A8]">{connecteur?.nom} · {connecteur?.categorie}</p>
        </div>
        <button onClick={onFermer} data-testid="inspecteur-fermer" className="text-[#7C93A8] transition-colors hover:text-[#F2F6F8]"><X size={15} /></button>
      </div>

      <div className="mt-3 flex items-center gap-2">
        <span className="rounded border px-1.5 py-0.5 font-code text-[9px]" style={{ color: st.couleur, borderColor: `${st.couleur}44`, backgroundColor: `${st.couleur}12` }} data-testid="inspecteur-statut">
          {st.label}
        </span>
        {source.dernier_test && <span className="font-code text-[9px] text-[#7C93A8]">dernier test {source.dernier_test.date} — {source.dernier_test.resultat === "ok" ? "réussi" : "échoué"}</span>}
      </div>

      {source.erreur && (
        <div className="mt-3 rounded-lg border border-[#F87171]/30 bg-[#F87171]/[0.05] p-3" data-testid="inspecteur-erreur">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-[#F87171]"><WarningCircle size={13} /> {source.erreur.titre}</div>
          <p className="mt-1 text-[11px] leading-relaxed text-[#94A3B8]">{source.erreur.detail}</p>
          <button
            onClick={() => {
              const manquant = (connecteur?.champs || []).find((c) => c.requis && !source.config?.[c.cle]);
              document.querySelector(`[data-testid="insp-${manquant ? manquant.cle : "perimetre"}"]`)?.focus();
            }}
            data-testid="inspecteur-action-btn"
            className="mt-2 rounded-md bg-[#F2B84B]/90 px-2.5 py-1 text-[10px] font-semibold text-[#071019] transition-colors hover:bg-[#F2B84B]"
          >
            {source.erreur.action} →
          </button>
        </div>
      )}

      <div className="mt-4 grid grid-cols-2 gap-3">
        <div>
          <label className="font-code text-[10px] uppercase tracking-[0.15em] text-[#7C93A8]">Nom de l'instance</label>
          <input value={source.nom} onChange={(e) => onChange(source.id, { nom: e.target.value })} data-testid="insp-nom" className="mt-1 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-3 py-2 text-xs text-[#F2F6F8] focus:border-[#25D0C8]/60 focus:outline-none" />
        </div>
        <div>
          <label className="font-code text-[10px] uppercase tracking-[0.15em] text-[#7C93A8]">Environnement</label>
          <select value={source.environnement} onChange={(e) => onChange(source.id, { environnement: e.target.value })} data-testid="insp-environnement" className="mt-1 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-3 py-2 text-xs text-[#F2F6F8] focus:outline-none">
            {ENVIRONNEMENTS.map((e) => <option key={e} value={e}>{e}</option>)}
          </select>
        </div>
        <div>
          <label className="font-code text-[10px] uppercase tracking-[0.15em] text-[#7C93A8]">Périmètre</label>
          <input value={source.perimetre} onChange={(e) => onChange(source.id, { perimetre: e.target.value })} placeholder="schémas, projets, index…" data-testid="insp-perimetre" className="mt-1 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-3 py-2 text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#25D0C8]/60 focus:outline-none" />
        </div>
        <div>
          <label className="font-code text-[10px] uppercase tracking-[0.15em] text-[#7C93A8]">Propriétaire</label>
          <input value={source.proprietaire} onChange={(e) => onChange(source.id, { proprietaire: e.target.value })} placeholder="Équipe responsable" data-testid="insp-proprietaire" className="mt-1 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-3 py-2 text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#25D0C8]/60 focus:outline-none" />
        </div>
      </div>

      <div className="mt-4 border-t border-[rgba(148,163,184,0.16)] pt-4">
        <div className="mb-3 font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">Connexion {connecteur?.nom}</div>
        <div className="space-y-3">{(connecteur?.champs || []).map(champ)}</div>
      </div>

      <div className="mt-5 flex items-center gap-2 border-t border-[rgba(148,163,184,0.16)] pt-4">
        <button onClick={() => onTester([source.id])} disabled={source.statut === "test_en_cours"} data-testid="insp-tester-btn" className="flex items-center gap-1.5 rounded-md bg-[#9B87F5] px-3 py-2 text-xs font-semibold text-[#071019] transition-colors hover:bg-[#B4A5F7] disabled:opacity-40">
          <Lightning size={13} /> {source.statut === "test_en_cours" ? "Test en cours…" : "Tester la connexion"}
        </button>
        <span className="font-code text-[9px] text-[#7C93A8]">enregistrement automatique</span>
      </div>
    </div>
  );
}
