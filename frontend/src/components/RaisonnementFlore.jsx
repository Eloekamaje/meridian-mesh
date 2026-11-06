import { CaretDown, ShieldCheck, ShieldWarning } from "@phosphor-icons/react";

const LIBELLES = {
  N0: "direct", N1: "étayé", N2: "cadré", N3: "décisionnel", N4: "critique",
  clarification_requise: "clarification requise", proposition: "proposition",
  partiel: "proposition partielle", refus: "bloqué", reponse: "réponse",
};

function findings(dossier) {
  return (dossier?.critiques || []).flatMap((critique) => critique.findings || []);
}

export default function RaisonnementFlore({ raisonnement, evaluation = null, testid = "flore-raisonnement" }) {
  if (!raisonnement) return null;
  const niveau = raisonnement.niveau || raisonnement.demande?.niveau || "N0";
  const statut = raisonnement.statut || "reponse";
  const liste = findings(raisonnement);
  const majeurs = liste.filter((f) => f.severite === "majeure" || f.severite === "critique");
  const Icone = majeurs.length ? ShieldWarning : ShieldCheck;
  const options = raisonnement.options || [];
  const questions = raisonnement.demande?.questions || [];
  const constats = raisonnement.constats || [];
  const twinIds = raisonnement.contexte?.twin_ids || [];
  const beliefs = raisonnement.beliefs || [];
  const presuppositions = raisonnement.question_frame?.presuppositions || [];
  const sourcePlan = raisonnement.source_plan;
  return (
    <details className="group rounded-lg border border-white/[0.08] bg-white/[0.02] px-3 py-2 text-xs text-[#94A3B8]" data-testid={testid}>
      <summary className="flex cursor-pointer list-none items-center gap-2 focus-visible:outline focus-visible:outline-1 focus-visible:outline-[#60A5FA]/60">
        <Icone size={14} className={majeurs.length ? "text-[#F2B84B]" : "text-[#34D399]"} aria-hidden="true" />
        <span className="font-code text-[10px] uppercase tracking-[0.16em] text-[#7C93A8]">{niveau}</span>
        <span className="text-[#7C93A8]">{LIBELLES[niveau]}</span>
        <span>{LIBELLES[statut] || statut}</span>
        {liste.length > 0 && <span className="text-[#64748B]">· {liste.length} point{liste.length > 1 ? "s" : ""}</span>}
        {evaluation?.score != null && <span className="font-code text-[10px] text-[#64748B]">{Math.round(evaluation.score * 100)}%</span>}
        <CaretDown size={12} className="ml-auto transition-transform group-open:rotate-180" aria-hidden="true" />
      </summary>
      <div className="mt-2 space-y-2 border-t border-white/[0.06] pt-2">
        {questions.length > 0 && (
          <div>
            <div className="mb-1 font-code text-[9px] uppercase tracking-[0.16em] text-[#64748B]">Cadrage</div>
            <ul className="list-disc space-y-0.5 pl-4">
              {questions.map((question) => <li key={question}>{question}</li>)}
            </ul>
          </div>
        )}
        {options.length > 0 && <div className="text-[#7C93A8]">{`${options.length} option${options.length > 1 ? "s" : ""} comparée${options.length > 1 ? "s" : ""}`}</div>}
        {presuppositions.length > 0 && (
          <div>
            <div className="mb-1 font-code text-[9px] uppercase tracking-[0.16em] text-[#64748B]">Présupposés</div>
            <ul className="space-y-0.5">
              {presuppositions.map((p) => (
                <li key={p.id || p.texte} className={p.statut === "CONNU" ? "text-[#34D399]" : p.statut === "CONTREDIT" ? "text-[#F2B84B]" : "text-[#F2B84B]"}>
                  {p.texte} · <span className="font-code text-[10px]">{p.statut}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {beliefs.length > 0 && (
          <div>
            <div className="mb-1 font-code text-[9px] uppercase tracking-[0.16em] text-[#64748B]">Croyances</div>
            <ul className="space-y-0.5 text-[#7C93A8]">
              {beliefs.slice(0, 6).map((b) => (
                <li key={b.id || `${b.sujet}-${b.predicat}-${b.objet}`}>
                  <span className="font-code text-[10px]">{b.statut}</span> · {b.objet}
                </li>
              ))}
            </ul>
          </div>
        )}
        {sourcePlan && (
          <div className="text-[#64748B]">
            <span className="font-code text-[9px] uppercase tracking-[0.16em]">Sources</span>{" "}
            {sourcePlan.twins?.length ? `Twins : ${sourcePlan.twins.join(", ")}` : "aucun Twin"}
            {sourcePlan.sources?.length ? ` · sources : ${sourcePlan.sources.join(", ")}` : ""}
          </div>
        )}
        {(constats.length > 0 || twinIds.length > 0) && (
          <div className="text-[#7C93A8]">
            {constats.length > 0 && <span>{`${constats.length} constat${constats.length > 1 ? "s" : ""}`}</span>}
            {twinIds.length > 0 && <span>{constats.length > 0 ? " · " : ""}{`Twins : ${twinIds.join(", ")}`}</span>}
          </div>
        )}
        {liste.length > 0 && (
          <div>
            <div className="mb-1 font-code text-[9px] uppercase tracking-[0.16em] text-[#64748B]">Revue</div>
            <ul className="space-y-1">
              {liste.map((finding) => (
                <li key={finding.id || finding.constat} className="text-[#94A3B8]">
                  <span className={finding.severite === "majeure" || finding.severite === "critique" ? "text-[#F2B84B]" : "text-[#7C93A8]"}>
                    [{finding.severite}] {finding.constat}
                  </span>
                  {finding.remediation && <span className="block text-[#64748B]">{finding.remediation}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
        {(raisonnement.gates || []).some((g) => g.statut !== "ok") && (
          <div className="text-[#F2B84B]">
            {(raisonnement.gates || []).filter((g) => g.statut !== "ok").map((g) => <div key={g.id}>{g.id} : {g.message || g.statut}</div>)}
          </div>
        )}
      </div>
    </details>
  );
}
