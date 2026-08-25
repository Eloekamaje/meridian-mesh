import { useEffect, useState } from "react";
import { Flask, FileText, Warning, CheckCircle, SealCheck } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Textarea } from "@/components/ui/textarea";
import { couleurDomaine } from "@/lib/domaines";

const COULEURS_NIVEAU = { "Élevé": "#EF4444", "Élevée": "#EF4444", "Moyen": "#F59E0B", "Moyenne": "#F59E0B", "Faible": "#10B981" };

function RayonImpact({ perimetre }) {
  const cx = 150, cy = 130, r = 88;
  return (
    <svg viewBox="0 0 300 260" className="h-[240px] w-full" data-testid="impact-map">
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(59,130,246,0.25)" strokeDasharray="4 5" />
      <circle cx={cx} cy={cy} r={r * 0.55} fill="none" stroke="rgba(59,130,246,0.15)" strokeDasharray="4 5" />
      {(perimetre || []).slice(1).map((jid, i, arr) => {
        const angle = (i / arr.length) * 2 * Math.PI - Math.PI / 2;
        const x = cx + r * Math.cos(angle);
        const y = cy + r * Math.sin(angle);
        return (
          <g key={jid}>
            <line x1={cx} y1={cy} x2={x} y2={y} stroke="rgba(59,130,246,0.4)" strokeWidth="1.2" />
            <circle cx={x} cy={y} r="17" fill="#0E0E0E" stroke={couleurDomaine(domaineDe(jid))} strokeWidth="1.5" />
            <text x={x} y={y + 32} textAnchor="middle" fill="rgba(255,255,255,0.65)" fontSize="9" fontFamily="IBM Plex Mono">{nomDe(jid)}</text>
          </g>
        );
      })}
      <circle cx={cx} cy={cy} r="24" fill="#0E0E0E" stroke="#3B82F6" strokeWidth="2">
        <animate attributeName="r" values="24;27;24" dur="2.4s" repeatCount="indefinite" />
      </circle>
      <text x={cx} y={cy + 3} textAnchor="middle" fill="#fff" fontSize="9" fontWeight="bold" fontFamily="Chivo">{nomDe((perimetre || [])[0])}</text>
    </svg>
  );
}
const NOMS = { paiements: "Paiements", facturation: "Facturation", comptes: "Comptes", support: "Support", fraude: "Fraude" };
const DOM = { paiements: "Paiement", facturation: "Paiement", comptes: "Client", support: "Support", fraude: "Risque" };
const nomDe = (id) => NOMS[id] || id || "…";
const domaineDe = (id) => DOM[id] || "Non classé";

export default function ChangeLab({ integre = false }) {
  const [description, setDescription] = useState("Remplacer settlementDate par settlementTimestamp dans l'événement PaymentSettled");
  const [resultat, setResultat] = useState(null);
  const [scenarioChoisi, setScenarioChoisi] = useState(null);
  const [chargement, setChargement] = useState(false);
  const [dossier, setDossier] = useState(null);

  useEffect(() => {
    api.get("/change-lab").then((r) => setResultat(r.data)).catch(() => {});
  }, []);

  const simuler = async () => {
    if (!description.trim() || chargement) return;
    setChargement(true);
    setDossier(null);
    try {
      const { data } = await api.post("/change-lab/simuler", { description });
      setResultat(data);
      setScenarioChoisi(data.scenarios?.find((s) => s.recommande)?.nom || null);
      toast.success("Simulation terminée — périmètre et scénarios calculés");
    } catch {
      toast.error("Simulation impossible");
    } finally {
      setChargement(false);
    }
  };

  const creerDossier = async () => {
    if (!scenarioChoisi) {
      toast.error("Choisissez un scénario");
      return;
    }
    try {
      const { data } = await api.post("/change-lab/dossier", { scenario: scenarioChoisi, changement: resultat.changement });
      setDossier(data);
      toast.success(`Dossier de changement ${data.id} créé`);
    } catch {
      toast.error("Création du dossier impossible");
    }
  };

  return (
    <div className={integre ? "" : "h-full overflow-y-auto px-8 py-8 pb-44"} data-testid="changelab-page">
      {!integre && (
        <header className="rise">
          <div className="font-code text-[10px] uppercase tracking-[0.3em] text-[#FBBF24]">Décider</div>
          <h1 className="mt-1 font-display text-4xl font-black text-white">Change Lab</h1>
          <p className="mt-2 text-base text-white/50">Préparer et simuler les changements avant qu'ils ne touchent le SI.</p>
        </header>
      )}
      {integre && (
        <div className="mb-6">
          <div className="font-code text-[10px] uppercase tracking-[0.25em] text-white/40">Simulateur</div>
          <h2 className="mt-1 font-display text-xl font-bold text-white">Change Lab</h2>
        </div>
      )}

      <div className="mt-8 grid grid-cols-12 gap-8">
        <section className="rise col-span-12 lg:col-span-4">
          <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-5">
            <h2 className="flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.25em] text-white/45">
              <Flask size={14} className="text-[#3B82F6]" /> Décrire un changement
            </h2>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={5}
              data-testid="change-description-input"
              className="mt-4 border-white/10 bg-black/40 text-sm text-white placeholder:text-white/30 focus-visible:ring-[#3B82F6]"
              placeholder="Ex. Remplacer settlementDate par settlementTimestamp…"
            />
            <button
              onClick={simuler}
              disabled={chargement}
              data-testid="simuler-btn"
              className="mt-4 w-full rounded-md bg-[#3B82F6] px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#2F6FDB] disabled:opacity-40"
            >
              {chargement ? "Simulation en cours…" : "Simuler le changement"}
            </button>
            {resultat && (
              <div className="mt-6">
                <div className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Rayon d'impact</div>
                <RayonImpact perimetre={resultat.perimetre} />
              </div>
            )}
          </div>
        </section>

        <section className="rise col-span-12 lg:col-span-8" style={{ animationDelay: "80ms" }}>
          {!resultat ? (
            <p className="py-16 text-sm text-white/35">Décrivez un changement pour calculer son périmètre probable.</p>
          ) : (
            <div className="space-y-6">
              <div>
                <div className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Changement analysé</div>
                <p className="mt-1.5 font-display text-lg font-bold text-white" data-testid="changement-titre">{resultat.changement}</p>
              </div>

              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4" data-testid="consommateurs-directs">
                  <h3 className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Consommateurs directs</h3>
                  <ul className="mt-3 space-y-2.5">
                    {(resultat.consommateurs_directs || []).map((c, i) => (
                      <li key={i} className="text-sm">
                        <span className="rounded border px-1.5 py-0.5 font-code text-[10px]" style={{ color: couleurDomaine(c.domaine), borderColor: `${couleurDomaine(c.domaine)}44`, backgroundColor: `${couleurDomaine(c.domaine)}12` }}>
                          {c.jumeau}
                        </span>
                        <p className="mt-1 text-xs text-white/55">{c.detail}</p>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="space-y-4">
                  <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
                    <h3 className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Effets indirects</h3>
                    <ul className="mt-2 space-y-1.5">
                      {(resultat.effets_indirects || []).map((e, i) => (
                        <li key={i} className="text-xs text-white/55">→ {e}</li>
                      ))}
                    </ul>
                  </div>
                  <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
                    <h3 className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Processus & règles</h3>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {(resultat.processus || []).map((p, i) => (
                        <span key={i} className="rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[11px] text-white/65">{p}</span>
                      ))}
                    </div>
                    <ul className="mt-2 space-y-1">
                      {(resultat.regles || []).map((r, i) => (
                        <li key={i} className="font-code text-[11px] text-white/50">{r}</li>
                      ))}
                    </ul>
                  </div>
                </div>

                <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
                  <h3 className="flex items-center gap-1.5 font-code text-[10px] uppercase tracking-[0.2em] text-white/40"><FileText size={13} /> Incidents similaires</h3>
                  {(resultat.incidents_similaires || []).map((inc, i) => (
                    <p key={i} className="mt-2 text-xs text-white/60"><span className="font-code text-[#F59E0B]">{inc.id}</span> — {inc.texte}</p>
                  ))}
                  <h3 className="mt-4 flex items-center gap-1.5 font-code text-[10px] uppercase tracking-[0.2em] text-white/40"><CheckCircle size={13} /> Tests recommandés</h3>
                  <ul className="mt-2 space-y-1.5">
                    {(resultat.tests_recommandes || []).map((t, i) => (
                      <li key={i} className="text-xs text-white/55">→ {t}</li>
                    ))}
                  </ul>
                </div>

                <div className="rounded-xl border border-[#F59E0B]/25 bg-[#F59E0B]/[0.04] p-4">
                  <h3 className="flex items-center gap-1.5 font-code text-[10px] uppercase tracking-[0.2em] text-[#F59E0B]"><Warning size={13} /> Zones non couvertes</h3>
                  <ul className="mt-2 space-y-1.5">
                    {(resultat.zones_non_couvertes || []).map((z, i) => (
                      <li key={i} className="text-xs text-white/60">{z}</li>
                    ))}
                  </ul>
                </div>
              </div>

              <div>
                <h3 className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Scénarios comparés</h3>
                <div className="mt-3 overflow-hidden rounded-xl border border-white/[0.08]" data-testid="scenarios-table">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-white/[0.08] bg-white/[0.03] font-code text-[10px] uppercase tracking-wider text-white/40">
                        <th className="px-4 py-3 text-left font-medium">Scénario</th>
                        <th className="px-4 py-3 text-left font-medium">Risque</th>
                        <th className="px-4 py-3 text-left font-medium">Effort</th>
                        <th className="px-4 py-3 text-left font-medium">Compatibilité</th>
                        <th className="px-4 py-3 text-left font-medium">Note d'Aurora</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(resultat.scenarios || []).map((s, i) => (
                        <tr
                          key={i}
                          onClick={() => setScenarioChoisi(s.nom)}
                          data-testid={`scenario-row-${i}`}
                          className={`cursor-pointer border-b border-white/[0.05] transition-colors ${scenarioChoisi === s.nom ? "bg-[#3B82F6]/[0.08]" : "hover:bg-white/[0.03]"}`}
                        >
                          <td className="px-4 py-3">
                            <span className="font-semibold text-white">{s.nom}</span>
                            {s.recommande && (
                              <span className="ml-2 rounded border border-[#10B981]/40 bg-[#10B981]/10 px-1.5 py-0.5 font-code text-[9px] uppercase text-[#10B981]">recommandé</span>
                            )}
                          </td>
                          {["risque", "effort", "compatibilite"].map((k) => (
                            <td key={k} className="px-4 py-3 font-code text-xs" style={{ color: COULEURS_NIVEAU[s[k]] || "#9CA3AF" }}>{s[k]}</td>
                          ))}
                          <td className="max-w-[280px] px-4 py-3 text-xs text-white/50">{s.note}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="flex items-center gap-4">
                <button
                  onClick={creerDossier}
                  data-testid="creer-dossier-btn"
                  className="rounded-md bg-[#3B82F6] px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#2F6FDB]"
                >
                  Créer le dossier de changement
                </button>
                {dossier && (
                  <span className="flex items-center gap-2 text-sm text-[#10B981]" data-testid="dossier-cree">
                    <SealCheck size={18} weight="fill" /> Dossier {dossier.id} — scénario « {dossier.scenario} »
                  </span>
                )}
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
