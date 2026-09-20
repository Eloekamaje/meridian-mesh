import { useEffect, useState } from "react";
import { Sparkle, CheckCircle, CircleNotch, CaretRight, Lightbulb } from "@phosphor-icons/react";

// Ligne de pensée / Trace d'activité épurée de Flore.
// Pendant l'analyse : stepper vivant, sobre et animé, sans effet de grosse carte lourde.
// Une fois terminée : repli automatique en pastille discrète consultable d'un clic.
export default function ActivitePilotee({ activite, testid = "flore-activite-demo", compact = false }) {
  const terminee = activite?.status === "done";
  const [ouvert, setOuvert] = useState(!terminee);

  useEffect(() => {
    if (!terminee) setOuvert(true);
  }, [terminee, activite?.id]);

  if (!activite) return null;
  const ops = activite.ops || [];
  const constats = activite.constats || [];
  const faites = ops.filter((o) => o.status === "done").length;
  const resume = activite.resume || (terminee ? "Analyse achevée" : activite.label);

  return (
    <div
      className={`transition-all duration-300 ${
        terminee
          ? "my-2"
          : "my-3 rounded-xl border border-[#9B87F5]/20 bg-[#9B87F5]/[0.03] p-3.5 shadow-sm backdrop-blur-sm"
      }`}
      data-testid={testid}
      data-etat={terminee ? "termine" : "encours"}
    >
      {terminee ? (
        <div className="flex items-center">
          <button
            onClick={() => setOuvert((o) => !o)}
            data-testid={`${testid}-resume`}
            aria-expanded={ouvert}
            className="group inline-flex items-center gap-2 rounded-full border border-[rgba(148,163,184,0.18)] bg-[#0A1622]/80 px-3 py-1 font-code text-[10px] text-[#7C93A8] transition-all hover:border-[#25D0C8]/40 hover:bg-[#0F1D28] hover:text-[#D8E2EA]"
          >
            <CheckCircle size={12} weight="fill" className="text-[#25D0C8]" />
            <span>
              {resume} · {ops.length} étape{ops.length > 1 ? "s" : ""}
              {constats.length > 0 ? ` · ${constats.length} constat` : ""}
            </span>
            <CaretRight
              size={11}
              weight="bold"
              className={`transition-transform duration-200 text-[#7C93A8] group-hover:text-[#25D0C8] ${
                ouvert ? "rotate-90" : ""
              }`}
            />
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.2em] text-[#9B87F5]">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#9B87F5] opacity-75"></span>
            <span className="relative inline-flex h-2 w-2 rounded-full bg-[#9B87F5]"></span>
          </span>
          <Sparkle size={12} weight="fill" className="text-[#9B87F5]" />
          <span>{activite.label}</span>
          <span className="ml-auto font-mono text-[10px] text-[#7C93A8]">
            {faites}/{ops.length}
          </span>
        </div>
      )}

      {ouvert && (
        <div className={terminee ? "mt-2.5 rounded-lg border border-[rgba(148,163,184,0.12)] bg-[#08121B] p-3" : "mt-3"}>
          <ul className="space-y-2">
            {ops.map((op, oi) => {
              const isDone = op.status === "done";
              const isRunning = op.status === "running";
              return (
                <li
                  key={oi}
                  className={`flex items-start gap-2.5 text-xs transition-colors duration-200 ${
                    isRunning
                      ? "font-medium text-[#F2F6F8]"
                      : isDone
                      ? "text-[#7C93A8]"
                      : "text-[#4B6072]"
                  }`}
                  data-testid={`${testid}-op-${oi}`}
                >
                  <span className="mt-0.5 shrink-0">
                    {isDone ? (
                      <CheckCircle size={13} weight="fill" className="text-[#25D0C8]" />
                    ) : isRunning ? (
                      <CircleNotch size={13} className="animate-spin text-[#9B87F5]" />
                    ) : (
                      <span className="inline-block h-2 w-2 rounded-full border border-[rgba(148,163,184,0.3)] bg-transparent" />
                    )}
                  </span>
                  <span className="leading-snug">{op.label}</span>
                </li>
              );
            })}
          </ul>

          {/* Constats intermédiaires : mis en valeur sobrement sans lourdeur */}
          {constats.length > 0 && (
            <div className="mt-3 space-y-2 border-t border-[rgba(148,163,184,0.14)] pt-2.5" data-testid={`${testid}-constats`}>
              {constats.map((c, ci) => (
                <div
                  key={ci}
                  className="rounded-lg border-l-2 border-[#F2B84B] bg-[#F2B84B]/[0.05] p-2.5"
                  data-testid={`${testid}-constat-${ci}`}
                >
                  <div className="flex items-start gap-2">
                    <Lightbulb size={13} weight="fill" className="mt-0.5 shrink-0 text-[#F2B84B]" />
                    <div className="min-w-0">
                      <p className="text-xs leading-relaxed text-[#F2F6F8]">{c.text}</p>
                      {c.source && (
                        <p className="mt-1 font-code text-[10px] text-[#F2B84B]/80">
                          Source : {c.source}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
