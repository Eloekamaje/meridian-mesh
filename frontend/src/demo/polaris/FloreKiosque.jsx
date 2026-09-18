// Fil de conversation du kiosque Polaris : même identité visuelle que Flore,
// alimenté par le scénario (jamais de saisie ni d'appel réseau).
import { useEffect, useRef, useState } from "react";
import { Sparkle, Check, FileText } from "@phosphor-icons/react";

// Télétype avec pause : l'effet de frappe se fige et reprend avec le lecteur (§6.3)
function Teletype({ texte, actif, enPause, testid }) {
  const reduit = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const [n, setN] = useState(() => (actif && !reduit ? 0 : (texte || "").length));
  useEffect(() => {
    if (!actif || reduit) { setN((texte || "").length); return undefined; }
    if (enPause) return undefined; // gel : n conservé
    const t = setInterval(() => {
      setN((v) => {
        if (v >= texte.length) { clearInterval(t); return v; }
        return Math.min(texte.length, v + 3);
      });
    }, 18);
    return () => clearInterval(t);
  }, [texte, actif, reduit, enPause]);
  const fini = n >= (texte || "").length;
  return (
    <p className="text-sm leading-relaxed text-[#D8E2EA]" data-testid={testid}>
      {(texte || "").slice(0, n)}
      {!fini && <span className="curseur-teletype">▍</span>}
    </p>
  );
}

function Activite({ activite }) {
  return (
    <div className="rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-3" data-testid="kiosque-activite" role="status" aria-live="polite">
      <div className="mb-1.5 flex items-center gap-2 font-code text-[9px] uppercase tracking-[0.25em] text-[#7C93A8]">
        <Sparkle size={11} className="text-[#9B87F5]" /> {activite.label}
      </div>
      <div className="space-y-1.5">
        {activite.ops.map((op, i) => (
          op.status !== "pending" && (
            <div key={i} className="flex items-center gap-2 font-code text-[11px]">
              {op.status === "running" ? (
                <Sparkle size={12} weight="fill" className="animate-pulse text-[#9B87F5]" />
              ) : (
                <Check size={12} weight="bold" className="text-[#34D399]" />
              )}
              <span className={op.status === "running" ? "text-[#D8E2EA]" : "text-[#7C93A8]/70"}>Flore {op.label}</span>
            </div>
          )
        ))}
      </div>
    </div>
  );
}

export default function FloreKiosque({ messages, activite, frappeActive, enPause, roleLabel, onPreuve, compact = false }) {
  const finRef = useRef(null);
  useEffect(() => {
    finRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, activite]);

  return (
    <div className="flex h-full flex-col" data-testid="flore-kiosque">
      <div className="flex-1 space-y-4 overflow-y-auto px-1 py-2">
        {messages.map((m, i) => {
          const estFlore = m.speaker === "flore";
          const dernierFlore = estFlore && i === messages.length - 1 && frappeActive;
          return (
            <div key={m.id} data-testid={`kiosque-msg-${i}`} className={estFlore ? "" : "flex justify-end"}>
              <div
                className={
                  estFlore
                    ? "rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-4"
                    : "max-w-[85%] rounded-xl border border-[rgba(37,208,200,0.25)] bg-[rgba(37,208,200,0.06)] p-4"
                }
              >
                <div className="mb-1 flex items-center gap-2 font-code text-[9px] uppercase tracking-[0.25em] text-[#7C93A8]">
                  {estFlore ? <Sparkle size={12} className="text-[#9B87F5]" /> : null}
                  {estFlore ? "Flore" : m.speakerLabel}
                </div>
                {estFlore ? (
                  <Teletype texte={m.text} actif={dernierFlore && m.anime} enPause={enPause} testid={`kiosque-msg-texte-${i}`} />
                ) : (
                  <p className="text-sm leading-relaxed text-[#D8E2EA]" data-testid={`kiosque-msg-texte-${i}`}>{m.text}</p>
                )}
                {m.evidenceIds?.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {m.evidenceIds.map((pid) => (
                      <button
                        key={pid}
                        onClick={() => onPreuve(pid)}
                        data-testid={`kiosque-preuve-${pid}`}
                        className="flex items-center gap-1.5 rounded-md border border-[rgba(148,163,184,0.16)] bg-[#071019] px-2 py-1 font-code text-[10px] text-[#58A6FF] transition-colors hover:border-[#58A6FF]/50"
                      >
                        <FileText size={11} /> Voir la preuve
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}
        {activite && <Activite activite={activite} />}
        <div ref={finRef} />
      </div>
      {!compact && (
        <div className="border-t border-[rgba(148,163,184,0.1)] px-1 pt-3">
          <p className="text-center font-code text-[10px] text-[#7C93A8]" data-testid="kiosque-mention-demo">
            Conversation de démonstration — {roleLabel}
          </p>
        </div>
      )}
    </div>
  );
}
