import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { ArrowLeft, CheckCircle, XCircle, Flask, Lightning, SealCheck, Prohibit } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import TrustBadges from "@/components/TrustBadges";
import { couleurDomaine, couleurConfiance, NATURES_EVENEMENT, NATURES, VERBES } from "@/lib/domaines";

export default function InvestigationDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { jumeauPar } = useMesh();
  const [sit, setSit] = useState(null);
  const [erreur, setErreur] = useState(false);

  useEffect(() => {
    api.get(`/situations/${id}`).then((r) => setSit(r.data)).catch(() => setErreur(true));
  }, [id]);

  if (erreur) {
    return (
      <div className="flex h-full flex-col items-start justify-center gap-4 px-8">
        <p className="text-white/60">Situation introuvable.</p>
        <Link to="/investigations" className="text-sm text-[#3B82F6] hover:underline">← Retour aux investigations</Link>
      </div>
    );
  }
  if (!sit) return <div className="p-8 text-sm text-white/40">Chargement de la situation…</div>;

  const decider = async (decision) => {
    try {
      await api.post(`/situations/${sit.id}/decision`, { decision });
      setSit({ ...sit, statut: "décidée", decision });
      toast.success("Décision enregistrée — Méridian apprend de ce choix");
    } catch {
      toast.error("Impossible d'enregistrer la décision");
    }
  };

  const agirDecision = async (d) => {
    const x = d.toLowerCase();
    try {
      if (x.includes("confirmer la relation") && sit.relation_id) {
        await api.post(`/relations/${sit.relation_id}/confirmer`);
        toast.success("Relation confirmée — mémoire du Mesh enrichie");
        return;
      }
      if (x.includes("coïncidence")) {
        await api.post(`/situations/${sit.id}/action`, { action: "coincidence" });
        setSit({ ...sit, statut: "classée" });
        toast.success("Classée comme coïncidence");
        return;
      }
      if (x.includes("investigation")) {
        await api.post(`/situations/${sit.id}/action`, { action: "investiguer" });
        setSit({ ...sit, statut: "en investigation" });
        toast.success("Investigation ouverte");
        return;
      }
      if (x.includes("surveiller")) {
        await api.post(`/situations/${sit.id}/action`, { action: "surveiller" });
        setSit({ ...sit, statut: "surveillée" });
        toast.success("Placée sous surveillance");
        return;
      }
      if (x.includes("observations")) {
        await api.post(`/situations/${sit.id}/action`, { action: "observer" });
        toast.success("Observations supplémentaires demandées aux jumeaux");
        return;
      }
      if (x.includes("admettre")) { navigate("/jumeaux"); return; }
      if (x.includes("change") || x.includes("scénario") || x.includes("dossier")) { navigate("/decisions"); return; }
      decider(d);
    } catch {
      toast.error("Action impossible");
    }
  };

  const nature = NATURES[sit.nature] || null;
  const verbe = VERBES[sit.verbe] || null;

  return (
    <div className="h-full overflow-y-auto px-8 py-8 pb-44" data-testid="investigation-detail">
      <button onClick={() => navigate("/investigations")} className="flex items-center gap-1.5 text-xs text-white/45 transition-colors hover:text-white" data-testid="back-to-investigations">
        <ArrowLeft size={14} /> Investigations
      </button>

      {/* Zone 1 — La question */}
      <section className="rise mt-5" data-testid="zone-question">
        <div className="font-code text-[10px] uppercase tracking-[0.3em] text-[#A78BFA]">La question</div>
        {(nature || verbe) && (
          <div className="mt-2 flex items-center gap-2">
            {nature && (
              <span
                className="rounded border px-1.5 py-0.5 font-code text-[10px] uppercase tracking-wider"
                style={{ color: nature.couleur, borderColor: `${nature.couleur}44`, backgroundColor: `${nature.couleur}10` }}
                data-testid="nature-badge"
              >
                Investigation · {nature.label}
              </span>
            )}
            {verbe && (
              <span className="font-code text-[10px] uppercase tracking-wider" style={{ color: verbe.couleur }}>
                {verbe.label}
              </span>
            )}
          </div>
        )}
        <h1 className="mt-2 max-w-3xl font-display text-4xl font-black leading-tight text-white">
          {sit.question || sit.titre}
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-white/55">{sit.resume}</p>
        <div className="mt-4 flex flex-wrap items-center gap-1.5">
          {(sit.jumeaux || []).map((jid) => {
            const j = jumeauPar(jid);
            const c = couleurDomaine(j?.domaine);
            return (
              <span key={jid} className="rounded-full border px-2.5 py-1 font-code text-[11px]" style={{ color: c, borderColor: `${c}44`, backgroundColor: `${c}12` }} data-testid={`perimetre-${jid}`}>
                {j?.nom || jid}
              </span>
            );
          })}
          {sit.aurora_recommandation && (
            <span className="ml-2 flex items-center gap-1.5 text-xs italic text-white/40">
              <Lightning size={13} className="text-[#3B82F6]" /> {sit.aurora_recommandation}
            </span>
          )}
        </div>
      </section>

      {/* Fiche découverte : Découvrir → Comprendre → Décider */}
      {(sit.decouverte_quoi || (sit.decouverte_pourquoi || []).length > 0) && (
        <section className="rise mt-8 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4" data-testid="fiche-decouverte" style={{ animationDelay: "60ms" }}>
          <div className="rounded-xl border border-[#22D3EE]/20 bg-[#22D3EE]/[0.04] p-4">
            <div className="font-code text-[10px] uppercase tracking-[0.2em] text-[#22D3EE]">Ce qui a été découvert</div>
            <p className="mt-2 text-sm leading-relaxed text-white/75" data-testid="fiche-quoi">{sit.decouverte_quoi}</p>
          </div>
          <div className="rounded-xl border border-[#A78BFA]/20 bg-[#A78BFA]/[0.04] p-4">
            <div className="font-code text-[10px] uppercase tracking-[0.2em] text-[#A78BFA]">Pourquoi Méridian le pense</div>
            <ul className="mt-2 space-y-1.5" data-testid="fiche-pourquoi">
              {(sit.decouverte_pourquoi || []).map((p, i) => (
                <li key={i} className="text-xs leading-snug text-white/65">→ {p}</li>
              ))}
            </ul>
          </div>
          <div className="rounded-xl border border-[#A78BFA]/20 bg-[#A78BFA]/[0.04] p-4">
            <div className="font-code text-[10px] uppercase tracking-[0.2em] text-[#A78BFA]">Ce qui reste à comprendre</div>
            <ul className="mt-2 space-y-1.5" data-testid="fiche-reste">
              {(sit.reste_a_comprendre || []).map((p, i) => (
                <li key={i} className="text-xs leading-snug italic text-white/55">? {p}</li>
              ))}
            </ul>
          </div>
          <div className="rounded-xl border border-[#FBBF24]/20 bg-[#FBBF24]/[0.04] p-4">
            <div className="font-code text-[10px] uppercase tracking-[0.2em] text-[#FBBF24]">Décision attendue</div>
            <div className="mt-2 flex flex-col gap-1.5" data-testid="fiche-decisions">
              {(sit.decisions_attendues || []).map((d, i) => (
                <button
                  key={i}
                  onClick={() => agirDecision(d)}
                  data-testid={`fiche-decision-${i}`}
                  className="rounded-md border border-white/10 bg-white/[0.04] px-2.5 py-1.5 text-left text-xs text-white/75 transition-colors duration-200 hover:border-[#FBBF24]/50 hover:text-white"
                >
                  {d}
                </button>
              ))}
            </div>
          </div>
        </section>
      )}

      <div className="mt-10 grid grid-cols-12 gap-8">
        {/* Zone 2 — La chronologie */}
        <section className="rise col-span-12 lg:col-span-4" data-testid="zone-chronologie" style={{ animationDelay: "80ms" }}>
          <h2 className="font-code text-[10px] uppercase tracking-[0.3em] text-white/45">Chronologie</h2>
          <ol className="mt-5 space-y-0">
            {(sit.chronologie || []).map((e, i) => {
              const j = jumeauPar(e.jumeau);
              const c = NATURES_EVENEMENT[e.nature] || "#6B7280";
              const derniere = i === sit.chronologie.length - 1;
              return (
                <li key={i} className="relative flex gap-3 pb-6" data-testid={`chrono-event-${i}`}>
                  {!derniere && <span className="absolute left-[5px] top-4 h-full w-px bg-white/10" />}
                  <span className="relative mt-1 h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: c, boxShadow: `0 0 10px ${c}66` }} />
                  <div>
                    <div className="flex items-baseline gap-2">
                      <span className="font-code text-[11px] font-medium text-white/85">{e.heure}</span>
                      {j && <span className="font-code text-[10px]" style={{ color: couleurDomaine(j.domaine) }}>{j.nom}</span>}
                    </div>
                    <p className="mt-0.5 text-sm leading-snug text-white/60">{e.texte}</p>
                  </div>
                </li>
              );
            })}
            {(sit.chronologie || []).length === 0 && (
              <li className="text-sm text-white/35">Chronologie en cours de constitution par les jumeaux.</li>
            )}
          </ol>
        </section>

        {/* Zone 3 — Les hypothèses */}
        <section className="rise col-span-12 lg:col-span-8" data-testid="zone-hypotheses" style={{ animationDelay: "140ms" }}>
          <h2 className="font-code text-[10px] uppercase tracking-[0.3em] text-white/45">Hypothèses</h2>
          <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-2">
            {(sit.hypotheses || []).map((h) => (
              <div key={h.id} className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-5" data-testid={`hypothesis-${h.id}`}>
                <div className="flex items-start justify-between gap-3">
                  <h3 className="text-sm font-semibold leading-snug text-white">{h.texte}</h3>
                  <span className="shrink-0 font-code text-sm font-medium" style={{ color: couleurConfiance(h.confiance) }}>
                    {h.confiance} %
                  </span>
                </div>
                <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-white/[0.07]">
                  <div className="h-full rounded-full transition-[width] duration-700" style={{ width: `${h.confiance}%`, backgroundColor: couleurConfiance(h.confiance) }} />
                </div>
                <div className="mt-4 space-y-1.5">
                  {h.pour.map((p, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs text-white/60">
                      <CheckCircle size={14} weight="fill" className="mt-0.5 shrink-0 text-[#10B981]" /> {p}
                    </div>
                  ))}
                  {h.contre.map((c, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs text-white/60">
                      <XCircle size={14} weight="fill" className="mt-0.5 shrink-0 text-[#EF4444]" /> {c}
                    </div>
                  ))}
                </div>
                <div className="mt-4 border-t border-white/[0.06] pt-3">
                  <span className="font-code text-[10px] uppercase tracking-wider text-white/35">Vérifications restantes</span>
                  {h.verifications.map((v, i) => (
                    <p key={i} className="mt-1 text-xs italic text-white/45">→ {v}</p>
                  ))}
                </div>
              </div>
            ))}
            {(sit.hypotheses || []).length === 0 && (
              <p className="text-sm text-white/35">Aurora n'a pas encore formulé d'hypothèse pour cette situation.</p>
            )}
          </div>
        </section>
      </div>

      {/* Zone 4 — La conclusion */}
      <section className="rise mt-10 rounded-xl border border-white/[0.1] bg-[#0D0D0D] p-6" data-testid="zone-conclusion" style={{ animationDelay: "200ms" }}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.3em] text-white/45">
            <Lightning size={14} className="text-[#3B82F6]" /> Conclusion — synthèse Aurora
          </h2>
          <TrustBadges indicateurs={sit.indicateurs} />
        </div>

        <p className="mt-4 max-w-3xl text-sm leading-relaxed text-white/80" data-testid="conclusion-synthese">{sit.synthese}</p>

        {(sit.contributions || []).length > 0 && (
          <div className="mt-5">
            <div className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Contributions</div>
            <ul className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
              {sit.contributions.map((c, i) => (
                <li key={i} className="flex items-baseline gap-2 text-sm">
                  <span className="shrink-0 rounded border px-1.5 py-0.5 font-code text-[10px]" style={{ color: couleurDomaine(c.domaine), borderColor: `${couleurDomaine(c.domaine)}44`, backgroundColor: `${couleurDomaine(c.domaine)}12` }}>
                    {c.jumeau}
                  </span>
                  <span className="text-white/60">{c.texte}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {(sit.preuves || []).length > 0 && (
          <div className="mt-5" data-testid="conclusion-preuves">
            <div className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Preuves</div>
            <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
              {sit.preuves.map((p, i) => (
                <div key={i} className="rounded-md border border-white/[0.07] bg-white/[0.02] px-3 py-2 text-xs text-white/60" data-testid={`preuve-${i}`}>
                  <span className="font-code text-[11px] text-white/90">{p.source}</span> — {p.detail}
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="mt-6 border-t border-white/[0.08] pt-5">
          {sit.decision ? (
            <div className="flex items-center gap-2 text-sm text-[#10B981]" data-testid="decision-prise">
              <SealCheck size={18} weight="fill" /> Décision humaine : {sit.decision}
            </div>
          ) : (
            <>
              <div className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">La décision vous appartient</div>
              <div className="mt-3 flex flex-wrap gap-2">
                {(sit.actions_proposees || []).map((a, i) => (
                  <button
                    key={i}
                    onClick={() => decider(a)}
                    data-testid={`decision-action-${i}`}
                    className="rounded-md bg-[#3B82F6] px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-[#2F6FDB]"
                  >
                    {a}
                  </button>
                ))}
                <button
                  onClick={() => navigate("/change-lab")}
                  data-testid="decision-changelab-btn"
                  className="flex items-center gap-1.5 rounded-md border border-white/15 px-3 py-2 text-xs text-white/70 transition-colors hover:border-[#3B82F6]/50 hover:text-white"
                >
                  <Flask size={14} /> Ouvrir dans Change Lab
                </button>
                <button
                  onClick={() => decider("Synthèse rejetée")}
                  data-testid="decision-rejeter-btn"
                  className="flex items-center gap-1.5 rounded-md border border-white/15 px-3 py-2 text-xs text-white/50 transition-colors hover:border-[#EF4444]/50 hover:text-[#EF4444]"
                >
                  <Prohibit size={14} /> Rejeter la synthèse
                </button>
              </div>
            </>
          )}
        </div>
      </section>
    </div>
  );
}
