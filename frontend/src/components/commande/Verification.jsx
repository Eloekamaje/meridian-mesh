import { Rocket, WarningCircle } from "@phosphor-icons/react";
import { estErreurSource } from "@/lib/sources";

export default function Verification({ commande, catalogue, onLancer, lancement }) {
  const sources = commande.sources;
  const pretes = sources.filter((s) => s.statut === "prete");
  const erreurs = sources.filter((s) => estErreurSource(s.statut));
  const restantes = sources.length - pretes.length - erreurs.length;
  const couverture = Math.min(20 + pretes.length * 9, 88);
  const nomConnecteur = (id) => catalogue.connecteurs.find((c) => c.id === id)?.nom || id;

  return (
    <div className="mx-auto max-w-3xl" data-testid="verification">
      <h2 className="font-display text-lg font-bold text-[#111110]">Vérifier et lancer</h2>
      <p className="mt-1 text-sm text-[#52524F]">Dernière revue avant que le jumeau ne commence à apprendre.</p>

      <div className="mt-6 grid grid-cols-3 gap-2 text-center" data-testid="verif-compteurs">
        {[
          [pretes.length, "sources prêtes", "#047857", "verif-pretes"],
          [restantes, "conservées à corriger", "#B45309", "verif-reportees"],
          [erreurs.length, "en erreur", "#B91C1C", "verif-erreurs"],
        ].map(([n, l, c, t]) => (
          <div key={l} className="rounded-xl border border-[#E5E5E3] px-3 py-4" data-testid={t}>
            <div className="font-display text-2xl font-bold" style={{ color: c }}>{n}</div>
            <div className="mt-1 font-code text-[10px] text-[#71716D]">{l}</div>
          </div>
        ))}
      </div>

      {erreurs.length > 0 && (
        <div className="mt-4 space-y-2" data-testid="verif-liste-erreurs">
          {erreurs.map((s) => (
            <div key={s.id} className="flex items-start gap-2 rounded-lg border border-[#B91C1C]/25 bg-[#B91C1C]/[0.04] px-3 py-2.5">
              <WarningCircle size={14} className="mt-0.5 shrink-0 text-[#B91C1C]" />
              <div>
                <div className="text-xs font-semibold text-[#111110]">{s.nom}</div>
                <div className="text-[10px] text-[#52524F]">{s.erreur?.detail || "Erreur non détaillée"} {s.erreur?.action && <span className="text-[#B45309]">→ {s.erreur.action}</span>}</div>
              </div>
            </div>
          ))}
          <p className="text-[11px] text-[#71716D]">Ces sources ne bloquent pas le lancement : elles seront conservées dans la commande pour correction ultérieure.</p>
        </div>
      )}

      <div className="mt-5 rounded-xl border border-[#E5E5E3] bg-white p-5" data-testid="verif-manifeste">
        <div className="font-code text-[10px] uppercase tracking-[0.2em] text-[#71716D]">Manifeste généré</div>
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
          <div><dt className="font-code text-[9px] uppercase text-[#71716D]">Jumeau</dt><dd className="text-[#111110]">{commande.jumeau.nom} — {commande.jumeau.domaine}</dd></div>
          <div><dt className="font-code text-[9px] uppercase text-[#71716D]">Propriétaire</dt><dd className="text-[#111110]">{commande.jumeau.proprietaire || "—"}</dd></div>
          <div><dt className="font-code text-[9px] uppercase text-[#71716D]">Couverture attendue</dt><dd className="text-[#111110]" data-testid="verif-couverture">{couverture} %</dd></div>
          <div><dt className="font-code text-[9px] uppercase text-[#71716D]">Gouvernance</dt><dd className="text-[#111110]">lecture seule · secrets via coffre · journal d'audit</dd></div>
        </dl>
        <div className="mt-3 border-t border-[#E5E5E3] pt-3">
          <div className="font-code text-[9px] uppercase text-[#71716D]">Sources au lancement</div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {pretes.map((s) => (
              <span key={s.id} className="rounded-full border border-[#047857]/30 bg-[#047857]/[0.06] px-2 py-0.5 font-code text-[9px] text-[#047857]">{nomConnecteur(s.connecteur)} · {s.environnement}</span>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-6 flex items-center justify-between">
        <p className="max-w-sm text-[11px] leading-relaxed text-[#71716D]">
          {pretes.length > 0
            ? `Lancer avec ${pretes.length} source${pretes.length > 1 ? "s" : ""} et conserver ${sources.length - pretes.length} source${sources.length - pretes.length > 1 ? "s" : ""} à corriger.`
            : "Au moins une source prête est requise pour lancer."}
        </p>
        <button onClick={onLancer} disabled={pretes.length === 0 || lancement} data-testid="lancer-btn" className="flex items-center gap-1.5 rounded-md bg-[#047857] px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#065F46] disabled:opacity-30">
          <Rocket size={15} /> {lancement ? "Lancement…" : "Lancer la découverte"}
        </button>
      </div>
    </div>
  );
}
