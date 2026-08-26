import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Sparkle, PaperPlaneTilt, Eye, ArrowSquareOut } from "@phosphor-icons/react";
import api from "@/lib/api";
import FloreActivite, { delaiMin } from "@/components/FloreActivite";
import { usePerimetre } from "@/lib/perimetre";
import { useMesh } from "@/lib/mesh";
import { couleurDomaine } from "@/lib/domaines";
import { GENRES } from "./Actualites";

// Comprendre une actualité = une conversation dédiée avec Flore, ouverte sur son rapport de la situation
export default function Comprendre() {
  const { hid } = useParams();
  const { version } = usePerimetre();
  const { mesh } = useMesh();
  const [data, setData] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [fil, setFil] = useState([]);
  const [q, setQ] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [preuvesOuvertes, setPreuvesOuvertes] = useState(false);
  const finFilRef = useRef(null);

  useEffect(() => {
    setData(null);
    setErreur(null);
    setFil([]);
    delaiMin(api.get(`/actualites/histoire/${hid}`), 2900)
      .then((r) => {
        setData(r.data);
        setFil([{ role: "flore", texte: r.data.rapport.texte, preuves: r.data.rapport.preuves || [], propositions: r.data.rapport.propositions || [], rapport: true }]);
      })
      .catch((e) => setErreur(e.response?.data?.detail || "Actualité introuvable"));
  }, [hid, version]);

  useEffect(() => {
    finFilRef.current?.scrollIntoView({ block: "end" });
  }, [fil.length, envoi]);

  const envoyer = async (e) => {
    e?.preventDefault();
    const question = q.trim();
    if (!question || envoi) return;
    setEnvoi(true);
    setQ("");
    setFil((f) => [...f, { role: "utilisateur", texte: question }]);
    try {
      const { data: rep } = await delaiMin(api.post("/aurora/demander", {
        contexte: "actualites",
        question,
        selection: data?.histoire?.jumeaux || [],
      }));
      setFil((f) => [...f, { role: "flore", texte: rep.reponse || rep.texte, contributions: rep.contributions || [] }]);
    } catch {
      setFil((f) => [...f, { role: "flore", texte: "Flore est indisponible pour le moment." }]);
    } finally {
      setEnvoi(false);
    }
  };

  if (erreur) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4" data-testid="comprendre-erreur">
        <p className="text-sm text-[#B91C1C]">{erreur}</p>
        <Link to="/actualites" data-testid="comprendre-erreur-retour" className="rounded-md border border-[#E5E5E3] px-3 py-1.5 text-xs text-[#52524F] hover:text-[#111110]">← Retour aux actualités</Link>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="flex h-full items-center justify-center" data-testid="comprendre-chargement">
        <FloreActivite genre="rapport" testid="comprendre-chargement-activite" />
      </div>
    );
  }

  const h = data.histoire;
  const g = GENRES[h.genre] || [h.genre, "#71716D"];

  return (
    <div className="flex h-full flex-col" data-testid="comprendre-page">
      {/* En-tête : retour + identité de l'actualité */}
      <div className="shrink-0 border-b border-[#E5E5E3] bg-white px-8 py-3" data-testid="comprendre-entete">
        <div className="flex items-center gap-4">
          <Link to="/actualites" data-testid="comprendre-retour-btn" className="flex shrink-0 items-center gap-1.5 rounded-md border border-[#E5E5E3] px-2.5 py-1.5 text-xs text-[#52524F] transition-colors hover:text-[#111110]">
            <ArrowLeft size={13} /> Actualités
          </Link>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="rounded border px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider" style={{ color: g[1], borderColor: `${g[1]}44`, backgroundColor: `${g[1]}0D` }} data-testid="comprendre-genre">{g[0]}</span>
              {h.quand && <span className="font-code text-[9px] text-[#71716D]">{new Date(h.quand).toLocaleString("fr-FR", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" })}</span>}
              {h.confiance && <span className="font-code text-[9px] text-[#71716D]">· Confiance : {h.confiance}</span>}
              {h.incertain && <span className="rounded border border-dashed px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider" style={{ color: g[1], borderColor: g[1] }}>non confirmée</span>}
            </div>
            <h1 className="mt-0.5 truncate font-display text-lg font-bold tracking-tight text-[#111110]" data-testid="comprendre-titre">{h.titre}</h1>
            <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
              {(h.jumeaux || []).slice(0, 6).map((jid) => {
                const j = mesh?.jumeaux.find((x) => x.id === jid);
                const c = couleurDomaine(j?.domaine);
                return (
                  <span key={jid} className="rounded-full border px-1.5 py-0.5 font-code text-[9px]" style={{ color: c, borderColor: `${c}44`, backgroundColor: `${c}0D` }}>
                    {j?.nom || jid}
                  </span>
                );
              })}
              {h.liens?.travail && (
                <Link to={h.liens.travail} data-testid="comprendre-lien-travail" className="flex items-center gap-1 font-code text-[10px] text-[#3730A3] hover:underline">
                  <ArrowSquareOut size={11} /> Ouvrir le travail
                </Link>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Fil de conversation — le rapport de Flore ouvre le fil */}
      <div className="flex-1 overflow-y-auto px-6">
        <div className="mx-auto max-w-2xl space-y-5 py-5">
          <div className="space-y-5" data-testid="comprendre-conversation">
            {fil.map((m, i) =>
              m.role === "utilisateur" ? (
                <p key={i} className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-[#EEECFA] px-4 py-2.5 text-sm text-[#1d1d1b]" data-testid={`comprendre-msg-${i}`}>
                  {m.texte}
                </p>
              ) : (
                <div key={i} className="rise" data-testid={`comprendre-msg-${i}`}>
                  <div className="flex items-center gap-1.5 font-code text-[9px] uppercase tracking-[0.2em] text-[#312E81]">
                    <Sparkle size={10} weight="fill" /> Flore{m.rapport ? " — rapport sur la situation" : ""}
                  </div>
                  <p className="mt-1 whitespace-pre-line text-sm leading-relaxed text-[#1d1d1b]">{m.texte}</p>
                  {(m.preuves || []).length > 0 && (
                    <div className="mt-2">
                      <button onClick={() => setPreuvesOuvertes((p) => !p)} data-testid="comprendre-preuves-toggle" className="flex items-center gap-1 font-code text-[10px] text-[#3730A3] hover:underline">
                        <Eye size={11} /> Ce rapport repose sur {m.preuves.length} preuve{m.preuves.length > 1 ? "s" : ""} · {preuvesOuvertes ? "masquer" : "afficher"}
                      </button>
                      {preuvesOuvertes && (
                        <ul className="mt-1.5 space-y-1 border-l-2 border-[#3730A3]/25 pl-2.5" data-testid="comprendre-preuves">
                          {m.preuves.map((p, k) => (
                            <li key={k} className="font-code text-[10px] leading-snug text-[#52524F]">
                              <span className="font-semibold text-[#312E81]">{p.source}</span> — {p.detail}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                  {(m.propositions || []).length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {m.propositions.map((p, k) =>
                        p.lien ? (
                          <Link key={k} to={p.lien} data-testid={`comprendre-prop-${i}-${k}`}
                            className="rounded-full border border-[#3730A3]/40 bg-[#3730A3]/[0.06] px-3 py-1.5 text-[11px] font-semibold text-[#3730A3] transition-colors hover:bg-[#3730A3]/15">
                            {p.label}
                          </Link>
                        ) : (
                          <button key={k} onClick={() => setQ(p.question || p.label)} data-testid={`comprendre-prop-${i}-${k}`}
                            className="rounded-full border border-[#E5E5E3] bg-white px-3 py-1.5 text-[11px] text-[#52524F] transition-colors hover:border-[#3730A3]/40 hover:text-[#3730A3]">
                            {p.label}
                          </button>
                        )
                      )}
                    </div>
                  )}
                </div>
              )
            )}
            {envoi && <FloreActivite genre={h.genre} testid="comprendre-attente" />}
            <div ref={finFilRef} />
          </div>
        </div>
      </div>

      {/* Composer ancré — la conversation continue */}
      <div className="shrink-0 border-t border-[#E5E5E3] bg-[#F7F7F6] px-6 py-3" data-testid="comprendre-composer-zone">
        <form onSubmit={envoyer} className="mx-auto max-w-2xl">
          <div className="flex items-end gap-2 rounded-2xl border border-[#E5E5E3] bg-white px-3 py-2 shadow-sm transition-colors focus-within:border-[#3730A3]/50">
            <textarea
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); envoyer(); } }}
              placeholder="Interrogez Flore sur cette situation…"
              rows={1}
              data-testid="comprendre-msg-input"
              className="max-h-32 flex-1 resize-none bg-transparent px-1 py-1.5 text-sm text-[#111110] placeholder:text-[#71716D] focus:outline-none"
            />
            <button type="submit" disabled={envoi || !q.trim()} data-testid="comprendre-msg-send-btn" title="Envoyer"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#3730A3] text-white transition-colors hover:bg-[#4338CA] disabled:opacity-30">
              <PaperPlaneTilt size={14} weight="fill" />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
