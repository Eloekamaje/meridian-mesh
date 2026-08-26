import { useEffect, useRef, useState } from "react";
import { Sparkle, PaperPlaneTilt } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { rel } from "./utils";

// Onglet Conversation — on replonge simplement dans le fil, là où la session s'était arrêtée
export default function OngletTravail({ cas, setCas }) {
  const [nouveauMsg, setNouveauMsg] = useState("");
  const [envoiMsg, setEnvoiMsg] = useState(false);
  const finFilRef = useRef(null);
  const coupureRef = useRef(null);
  const monte = useRef(false);

  const messages = cas.conversation || [];
  const coupure = cas.derniere_visite;
  const idxCoupure = coupure ? messages.findIndex((m) => m.quand && m.quand > coupure) : -1;

  useEffect(() => {
    if (monte.current) {
      finFilRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
      return;
    }
    monte.current = true;
    // À l'arrivée : se replacer là où la session s'était arrêtée
    if (idxCoupure > 0) coupureRef.current?.scrollIntoView({ block: "center" });
    else finFilRef.current?.scrollIntoView({ block: "end" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages.length, envoiMsg]);

  const envoyer = async (e) => {
    e?.preventDefault();
    const q = nouveauMsg.trim();
    if (!q || envoiMsg) return;
    setEnvoiMsg(true);
    setNouveauMsg("");
    try {
      const { data } = await api.post(`/cases/${cas.id}/messages`, { texte: q });
      setCas((c) => ({ ...c, conversation: [...(c.conversation || []), data.utilisateur, data.flore] }));
    } catch {
      toast.error("Message impossible");
    } finally {
      setEnvoiMsg(false);
    }
  };

  return (
    <div className="flex h-full flex-col" data-testid="onglet-travail">
      <div className="flex-1 overflow-y-auto px-6">
        <div className="mx-auto max-w-2xl space-y-5 py-5">
          <div className="space-y-5" data-testid="case-conversation">
            {messages.map((m, i) => (
              <div key={i}>
                {i === idxCoupure && idxCoupure > 0 && (
                  <div ref={coupureRef} className="my-2 flex items-center gap-3" data-testid="reprise-coupure">
                    <span className="h-px flex-1 bg-[#3730A3]/25" />
                    <span className="font-code text-[9px] uppercase tracking-[0.2em] text-[#3730A3]">Nouveau depuis votre dernière visite</span>
                    <span className="h-px flex-1 bg-[#3730A3]/25" />
                  </div>
                )}
                {m.role === "utilisateur" ? (
                  <p className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-[#EEECFA] px-4 py-2.5 text-sm text-[#1d1d1b]" data-testid={`case-msg-${i}`}>
                    {m.texte}
                  </p>
                ) : (
                  <div className="rise" data-testid={`case-msg-${i}`}>
                    <div className="flex items-center gap-1.5 font-code text-[9px] uppercase tracking-[0.2em] text-[#312E81]">
                      <Sparkle size={10} weight="fill" /> Flore
                      {m.quand && <span className="text-[#71716D] normal-case tracking-normal">· {rel(m.quand)}</span>}
                    </div>
                    <p className="mt-1 whitespace-pre-line text-sm leading-relaxed text-[#1d1d1b]">{m.texte}</p>
                    {(m.contributions || []).length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {m.contributions.map((c, k) => (
                          <span key={k} className="rounded-full border border-[#E5E5E3] bg-white px-2 py-0.5 font-code text-[9px] text-[#52524F]">
                            {c.jumeau} — {c.texte}
                          </span>
                        ))}
                      </div>
                    )}
                    {(m.propositions || []).length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {m.propositions.map((p, k) => (
                          <button key={k} onClick={() => setNouveauMsg(p.question || p.label)} data-testid={`case-prop-${i}-${k}`}
                            className="rounded-full border border-[#E5E5E3] bg-white px-3 py-1.5 text-[11px] text-[#52524F] transition-colors hover:border-[#3730A3]/40 hover:text-[#3730A3]">
                            {p.label}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
            {messages.length === 0 && (
              <p className="py-6 text-center text-sm text-[#71716D]">La conversation est la mémoire du travail — commencez ci-dessous.</p>
            )}
            {envoiMsg && <p className="font-code text-[10px] text-[#71716D]" data-testid="case-msg-attente">Flore consulte le Mesh…</p>}
            <div ref={finFilRef} />
          </div>
        </div>
      </div>

      {/* Composer ancré — même geste que la création */}
      <div className="shrink-0 border-t border-[#E5E5E3] bg-[#F7F7F6] px-6 py-3" data-testid="case-composer-zone">
        <form onSubmit={envoyer} className="mx-auto max-w-2xl">
          <div className="flex items-end gap-2 rounded-2xl border border-[#E5E5E3] bg-white px-3 py-2 shadow-sm transition-colors focus-within:border-[#3730A3]/50">
            <textarea
              value={nouveauMsg}
              onChange={(e) => setNouveauMsg(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); envoyer(); } }}
              placeholder="Continuez avec Flore — chaque échange enrichit la mémoire du travail…"
              rows={1}
              data-testid="case-msg-input"
              className="max-h-32 flex-1 resize-none bg-transparent px-1 py-1.5 text-sm text-[#111110] placeholder:text-[#71716D] focus:outline-none"
            />
            <button type="submit" disabled={envoiMsg || !nouveauMsg.trim()} data-testid="case-msg-send-btn" title="Envoyer"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#3730A3] text-white transition-colors hover:bg-[#4338CA] disabled:opacity-30">
              <PaperPlaneTilt size={14} weight="fill" />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
