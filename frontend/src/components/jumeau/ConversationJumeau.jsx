import { useEffect, useRef, useState } from "react";
import { PaperPlaneRight, ArrowCounterClockwise, Wrench } from "@phosphor-icons/react";
import { toast } from "sonner";
import api, { entetesMeridian } from "@/lib/api";

// Conversation avec le jumeau : fil personnel du membre, réponses en flux, citations git:// cliquables.
const RE_CITATION = /git:\/\/[^\s@`]+@[0-9a-f]+:([^\s#`]+)#L(\d+)-L(\d+)/g;
const LIBELLES_OUTILS = {
  mes_connaissances: "consulte ses connaissances",
  architecture: "regarde son architecture",
  chercher_texte: "cherche dans son code",
  chercher_symbole: "cherche un symbole",
  tracer_appels: "trace des appels",
  lire_code: "lit son code",
  proposer_connaissance: "propose une connaissance à l'équipe",
};
const SUGGESTIONS = ["Qui es-tu ?", "Quelles APIs exposes-tu et qui les protège ?", "Comment gères-tu les droits d'accès ?"];

// Rendu sûr (aucun HTML injecté) : **gras**, `code` et citations, découpés en éléments React.
function Ligne({ texte, onCitation }) {
  const morceaux = [];
  let reste = 0;
  for (const m of texte.matchAll(RE_CITATION)) {
    morceaux.push(texte.slice(reste, m.index));
    morceaux.push({ chemin: m[1], debut: Number(m[2]), fin: Number(m[3]), brut: m[0] });
    reste = m.index + m[0].length;
  }
  morceaux.push(texte.slice(reste));
  return morceaux.map((m, i) => (typeof m === "string"
    ? m.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((t, j) => {
        if (t.startsWith("**") && t.endsWith("**") && t.length > 4) return <strong key={`${i}-${j}`} className="font-semibold text-white">{t.slice(2, -2)}</strong>;
        if (t.startsWith("`") && t.endsWith("`") && t.length > 2) return <code key={`${i}-${j}`} className="rounded bg-[#60A5FA]/10 px-1 font-code text-[11px] text-[#BFDBFE]">{t.slice(1, -1)}</code>;
        return t;
      })
    : (
      <button key={i} type="button" onClick={() => onCitation(m)} title={m.brut}
        className="mx-0.5 rounded border border-[#60A5FA]/40 bg-[#60A5FA]/10 px-1 font-code text-[10px] text-[#93C5FD] hover:bg-[#60A5FA]/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#60A5FA]">
        {m.chemin}:{m.debut}{m.fin !== m.debut ? `-${m.fin}` : ""}
      </button>
    )));
}

function Bulle({ message, onCitation }) {
  const moi = message.role === "user";
  return (
    <div className={`mb-3 flex ${moi ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[92%] rounded-lg px-3 py-2 text-xs leading-relaxed ${moi ? "bg-[#60A5FA]/15 text-[#F2F6F8]" : "border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] text-[#CBD5E1]"}`}>
        {message.outils?.length > 0 && (
          <div className="mb-1.5 flex flex-wrap gap-1">
            {message.outils.map((o, i) => (
              <span key={i} className="flex items-center gap-1 rounded bg-[rgba(148,163,184,0.08)] px-1.5 py-0.5 font-code text-[9px] text-[#7C93A8]">
                <Wrench size={9} aria-hidden />{LIBELLES_OUTILS[o] || o}
              </span>
            ))}
          </div>
        )}
        {message.texte.split("\n").map((l, i) => (
          <div key={i} className="min-h-[1em] whitespace-pre-wrap"><Ligne texte={l} onCitation={onCitation} /></div>
        ))}
        {message.enCours && !message.texte && <span className="text-[#7C93A8]">…</span>}
      </div>
    </div>
  );
}

// Lit un flux SSE « data: {...}\n\n » et appelle `surEvenement` pour chaque événement.
async function lireFlux(reponse, surEvenement) {
  const lecteur = reponse.body.getReader();
  const decodeur = new TextDecoder();
  let tampon = "";
  for (;;) {
    const { value, done } = await lecteur.read();
    if (done) return;
    tampon += decodeur.decode(value, { stream: true });
    const blocs = tampon.split("\n\n");
    tampon = blocs.pop();
    blocs.filter((b) => b.startsWith("data: ")).forEach((b) => surEvenement(JSON.parse(b.slice(6))));
  }
}

export default function ConversationJumeau({ jid, onCitation, onReponse }) {
  const [messages, setMessages] = useState([]);
  const [saisie, setSaisie] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const fin = useRef(null);
  const annulation = useRef(null);

  useEffect(() => {
    let actif = true;
    api.get(`/v2/jumeaux/${encodeURIComponent(jid)}/conversation`)
      .then(({ data }) => actif && setMessages(data))
      .catch(() => actif && setMessages([]));
    return () => { actif = false; annulation.current?.abort(); };
  }, [jid]);
  useEffect(() => { fin.current?.scrollIntoView({ block: "end" }); }, [messages]);

  // Ne touche que la réponse en cours : après un changement de fil (annulation), le dernier message n'est plus le nôtre.
  const majDernier = (f) => setMessages((ms) => {
    const dernier = ms[ms.length - 1];
    return dernier?.role === "assistant" && dernier.enCours ? [...ms.slice(0, -1), f(dernier)] : ms;
  });

  const envoyer = async (texte) => {
    if (!texte.trim() || envoi) return;
    setEnvoi(true);
    setSaisie("");
    setMessages((ms) => [...ms, { role: "user", texte }, { role: "assistant", texte: "", outils: [], enCours: true }]);
    annulation.current = new AbortController();
    try {
      const reponse = await fetch(`${process.env.REACT_APP_BACKEND_URL || ""}/api/v2/jumeaux/${encodeURIComponent(jid)}/conversation`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...entetesMeridian() },
        body: JSON.stringify({ texte }),
        signal: annulation.current.signal,
      });
      if (!reponse.ok) {
        const detail = (await reponse.json().catch(() => ({}))).detail;
        throw new Error(detail || "Le jumeau est indisponible");
      }
      await lireFlux(reponse, (ev) => {
        if (ev.type === "texte") majDernier((m) => ({ ...m, texte: m.texte + ev.texte }));
        else if (ev.type === "outil") majDernier((m) => ({ ...m, outils: [...m.outils, ev.nom] }));
        else if (ev.type === "erreur") throw new Error(ev.message);
      });
      onReponse?.();
    } catch (e) {
      if (e.name !== "AbortError") {
        toast.error(e.message);
        majDernier((m) => ({ ...m, texte: m.texte || `⚠ ${e.message}`, enCours: false }));
      }
    } finally {
      if (!annulation.current?.signal.aborted) {
        majDernier((m) => ({ ...m, enCours: false }));
        setEnvoi(false);
      }
    }
  };

  const nouveauFil = async () => {
    try {
      await api.delete(`/v2/jumeaux/${encodeURIComponent(jid)}/conversation`);
      setMessages([]);
    } catch {
      toast.error("Impossible d'effacer le fil");
    }
  };

  return (
    <section className="flex h-full flex-col" aria-label="Conversation avec le jumeau" data-testid="conversation-jumeau">
      <div className="flex-1 overflow-y-auto p-4" aria-live="polite">
        {!messages.length && (
          <div className="text-xs text-[#94A3B8]">
            <p className="mb-3">Votre fil personnel avec ce jumeau. Il répond à partir de son code, preuves à l'appui.</p>
            {SUGGESTIONS.map((s) => (
              <button key={s} type="button" onClick={() => envoyer(s)} className="mb-1.5 block rounded-md border border-[rgba(148,163,184,0.16)] px-3 py-1.5 text-left hover:bg-[rgba(148,163,184,0.07)]">{s}</button>
            ))}
          </div>
        )}
        {messages.map((m, i) => <Bulle key={i} message={m} onCitation={onCitation} />)}
        <div ref={fin} />
      </div>
      <form className="flex gap-2 border-t border-[rgba(148,163,184,0.16)] p-3" onSubmit={(e) => { e.preventDefault(); envoyer(saisie); }}>
        <button type="button" onClick={nouveauFil} disabled={envoi} title="Nouveau fil" aria-label="Nouveau fil"
          className="h-9 rounded-md border border-[rgba(148,163,184,0.16)] px-2 text-[#94A3B8] hover:text-[#F2F6F8] disabled:opacity-50">
          <ArrowCounterClockwise size={14} aria-hidden />
        </button>
        <label htmlFor="saisie-jumeau" className="sr-only">Message au jumeau</label>
        <input id="saisie-jumeau" value={saisie} onChange={(e) => setSaisie(e.target.value)} maxLength={4000} disabled={envoi}
          placeholder="Interrogez le jumeau…" className="h-9 flex-1 rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-3 text-xs text-[#F2F6F8] disabled:opacity-60" />
        <button type="submit" disabled={envoi || !saisie.trim()} aria-label="Envoyer"
          className="h-9 rounded-md bg-[#60A5FA] px-3 text-[#071019] hover:bg-[#93C5FD] disabled:opacity-50">
          <PaperPlaneRight size={14} weight="fill" aria-hidden />
        </button>
      </form>
    </section>
  );
}
