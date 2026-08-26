import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkle, Compass, Newspaper, ArrowRight, Eye, FolderOpen } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { usePerimetre } from "@/lib/perimetre";
import { useContexte } from "@/lib/contexte";
import ComposerFlore from "@/components/ComposerFlore";
import FloreActivite, { delaiMin } from "@/components/FloreActivite";

const SUGGESTIONS = {
  architecte: [
    "Comprendre les nouvelles dépendances",
    "Comparer l'architecture déclarée au comportement observé",
    "Reprendre la modernisation Oracle",
  ],
  default: [
    "Voir ce que mon jumeau a découvert",
    "Examiner les connaissances à confirmer",
    "Corriger une source en erreur",
  ],
};

function BulleFlore({ data, index, onSuite }) {
  const [preuves, setPreuves] = useState(false);
  return (
    <div className="rise" data-testid={`accueil-reponse-${index}`}>
      <div className="flex items-center gap-1.5 font-code text-[9px] uppercase tracking-[0.2em] text-[#312E81]">
        <Sparkle size={11} weight="fill" /> Flore
      </div>
      <p className="mt-1.5 whitespace-pre-line text-sm leading-relaxed text-[#1d1d1b]">{data.reponse || data.texte}</p>

      {(data.contributions || []).length > 0 && (
        <div className="mt-2.5 space-y-1.5">
          {data.contributions.map((c, k) => (
            <div key={k} className="flex gap-2 rounded-lg bg-[#F7F7F6] px-3 py-2 text-xs" data-testid={`accueil-contribution-${index}-${k}`}>
              <span className="shrink-0 font-code text-[10px] font-semibold text-[#3730A3]">{c.jumeau}</span>
              <span className="text-[#52524F]">{c.texte}</span>
            </div>
          ))}
        </div>
      )}

      {(data.preuves || []).length > 0 && (
        <div className="mt-2.5">
          <button onClick={() => setPreuves((p) => !p)} data-testid={`accueil-preuves-${index}`} className="flex items-center gap-1 font-code text-[10px] text-[#3730A3] hover:underline">
            <Eye size={11} /> Cette conclusion repose sur {data.preuves.length} preuve{data.preuves.length > 1 ? "s" : ""} · {preuves ? "masquer" : "afficher"}
          </button>
          {preuves && (
            <ul className="mt-1.5 space-y-1 border-l-2 border-[#3730A3]/25 pl-2.5">
              {data.preuves.map((p, k) => (
                <li key={k} className="font-code text-[10px] leading-snug text-[#52524F]">
                  <span className="font-semibold text-[#312E81]">{p.source}</span> — {p.detail}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {data.perimetre_investigation && (
        <p className="mt-2.5 font-code text-[9px] uppercase tracking-wider text-[#71716D]" data-testid={`accueil-perimetre-${index}`}>
          Périmètre d'investigation : {data.perimetre_investigation.confidentialite} · expire {data.perimetre_investigation.expire}
        </p>
      )}

      {(data.propositions || []).length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {data.propositions.map((p, k) => (
            <button key={k} onClick={() => onSuite(p.question || p.label)} data-testid={`accueil-prop-${index}-${k}`}
              className="rounded-full border border-[#E5E5E3] bg-white px-3 py-1.5 text-[11px] text-[#52524F] transition-colors hover:border-[#3730A3]/40 hover:text-[#3730A3]">
              {p.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Accueil({ mode = "accueil" }) {
  const navigate = useNavigate();
  const { persona, personas, version, info } = usePerimetre();
  const { selection } = useContexte();
  const [recents, setRecents] = useState([]);
  const [echanges, setEchanges] = useState([]);
  const [envoi, setEnvoi] = useState(false);
  const [propMasquee, setPropMasquee] = useState(false);
  const [conservation, setConservation] = useState(false);
  const creation = mode === "creation";
  const role = personas.find((p) => p.id === persona)?.role || "";
  const suggestions = /architect|urbanisation/i.test(role) ? SUGGESTIONS.architecte : SUGGESTIONS.default;
  const nom = personas.find((p) => p.id === persona)?.nom || "";

  useEffect(() => {
    api.get("/cases").then((r) => setRecents(r.data.filter((c) => c.statut !== "clos").slice(0, 2))).catch(() => {});
  }, [version]);

  // Pas de formulaire : la première question fait naître le travail, la conversation continue dedans
  const faireNaitreLeTravail = async (question, reponseData) => {
    try {
      const now = new Date().toISOString();
      const { data } = await api.post("/cases", {
        titre: question.length > 90 ? `${question.slice(0, 87)}…` : question,
        type: "demande",
        objectif: question,
        jumeaux: selection,
        espace: info?.espace?.id,
      });
      await api.patch(`/cases/${data.id}`, {
        conversation: [
          { role: "utilisateur", texte: question, quand: now },
          { role: "flore", comportement: reponseData.comportement, texte: reponseData.reponse, quand: now },
        ],
      });
      toast.success("Travail né de la conversation");
      navigate(`/travaux/${data.id}`, { replace: true });
    } catch {
      toast.error("Création du travail impossible — la conversation reste ici");
    }
  };

  const demander = async (q) => {
    if (envoi || !q.trim()) return;
    setEnvoi(true);
    setEchanges((e) => [...e, { role: "moi", texte: q }]);
    try {
      const { data } = await delaiMin(api.post("/aurora/demander", { contexte: creation ? "case" : "accueil", question: q, selection }));
      setEchanges((e) => [...e, { role: "flore", data }]);
      if (creation) await faireNaitreLeTravail(q, data);
    } catch {
      setEchanges((e) => [...e, { role: "flore", data: { reponse: "Flore est indisponible pour le moment — réessayez." } }]);
    } finally {
      setEnvoi(false);
    }
  };

  const conserverCommeTravail = async () => {
    if (conservation) return;
    setConservation(true);
    try {
      const premiere = echanges.find((e) => e.role === "moi")?.texte || "Exploration";
      const { data } = await api.post("/cases", {
        titre: premiere.length > 90 ? `${premiere.slice(0, 87)}…` : premiere,
        type: "decouverte",
        objectif: premiere,
        jumeaux: selection,
        espace: info?.espace?.id,
      });
      const now = new Date().toISOString();
      await api.patch(`/cases/${data.id}`, {
        conversation: echanges.flatMap((e) =>
          e.role === "moi"
            ? [{ role: "utilisateur", texte: e.texte, quand: now }]
            : [{ role: "flore", comportement: e.data.comportement, texte: e.data.reponse, quand: now }]
        ),
      });
      toast.success("Travail conservé — la conversation devient mémoire");
      navigate(`/travaux/${data.id}`);
    } catch {
      toast.error("Conservation impossible");
      setConservation(false);
    }
  };

  const enConversation = echanges.length > 0;

  return (
    <div className="flex h-full flex-col overflow-hidden" data-testid="accueil-page">
      {/* Zone de contenu : accueil ou fil de conversation — le chat VIT ici, pas en latéral */}
      <div className="flex-1 overflow-y-auto px-6">
        {creation && !enConversation && (
          <div className="mx-auto w-full max-w-2xl pt-4">
            <button onClick={() => navigate("/travaux")} data-testid="creation-retour-travaux" className="flex items-center gap-1.5 rounded-md border border-[#E5E5E3] bg-white px-2.5 py-1.5 text-xs text-[#52524F] transition-colors hover:text-[#111110]">
              ← Travaux
            </button>
          </div>
        )}
        <div className="mx-auto w-full max-w-2xl pb-8">
          {!enConversation ? (
            <div className="flex min-h-[70vh] flex-col items-center justify-center py-10">
              <h1 className="rise text-center font-display text-3xl font-black tracking-tight text-[#111110] sm:text-4xl" data-testid="accueil-titre">
                {creation ? "Que voulez-vous comprendre\nou accomplir ?" : <>Que voulez-vous comprendre<br />dans votre SI ?</>}
              </h1>
              <p className="rise mt-3 text-center text-sm text-[#52524F]" style={{ animationDelay: "60ms" }}>
                {creation
                  ? "Décrivez-le simplement — le travail naît de votre première question, la conversation devient sa mémoire."
                  : `Flore mobilise les jumeaux et compose la représentation utile${nom ? ` — bonjour ${nom}` : ""}.`}
              </p>
              {!creation && (
                <>
                  <div className="rise mt-5 flex flex-wrap justify-center gap-2" style={{ animationDelay: "120ms" }} data-testid="accueil-suggestions">
                    {suggestions.map((s) => (
                      <button key={s} onClick={() => demander(s)} data-testid={`accueil-suggestion-${s.slice(0, 18)}`}
                        className="rounded-full border border-[#E5E5E3] bg-white px-3.5 py-1.5 text-xs text-[#52524F] transition-colors hover:border-[#3730A3]/40 hover:text-[#3730A3]">
                        {s}
                      </button>
                    ))}
                  </div>
                  <div className="rise mt-10 grid w-full gap-2 sm:grid-cols-3" style={{ animationDelay: "180ms" }}>
                    <button onClick={() => navigate("/actualites")} data-testid="accueil-actus" className="rounded-xl border border-[#E5E5E3] bg-white p-4 text-left transition-colors hover:border-[#3730A3]/40">
                      <Newspaper size={16} className="text-[#3730A3]" />
                      <div className="mt-2 text-xs font-semibold text-[#111110]">Changements d'aujourd'hui</div>
                      <div className="mt-0.5 font-code text-[9px] text-[#71716D]">Le briefing du Mesh</div>
                    </button>
                    {recents[0] && (
                      <button onClick={() => navigate(`/travaux/${recents[0].id}`)} data-testid="accueil-reprendre" className="rounded-xl border border-[#E5E5E3] bg-white p-4 text-left transition-colors hover:border-[#3730A3]/40">
                        <Sparkle size={16} className="text-[#B45309]" />
                        <div className="mt-2 truncate text-xs font-semibold text-[#111110]">Reprendre « {recents[0].titre} »</div>
                        <div className="mt-0.5 font-code text-[9px] text-[#71716D]">Continuité du travail</div>
                      </button>
                    )}
                    <button onClick={() => navigate("/atlas")} data-testid="accueil-explorer" className="rounded-xl border border-[#E5E5E3] bg-white p-4 text-left transition-colors hover:border-[#3730A3]/40">
                      <Compass size={16} className="text-[#0E7490]" />
                      <div className="mt-2 text-xs font-semibold text-[#111110]">Explorer mon espace</div>
                      <div className="mt-0.5 font-code text-[9px] text-[#71716D]">L'Atlas du Mesh</div>
                    </button>
                  </div>
                </>
              )}
            </div>
          ) : (
            <div className="space-y-6 py-8" data-testid="accueil-fil">
              {echanges.map((e, i) =>
                e.role === "moi" ? (
                  <p key={i} className="rise ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-[#EEECFA] px-4 py-2.5 text-sm text-[#1d1d1b]" data-testid={`accueil-msg-${i}`}>
                    {e.texte}
                  </p>
                ) : (
                  <BulleFlore key={i} data={e.data} index={i} onSuite={demander} />
                )
              )}
              {envoi && <FloreActivite testid="accueil-attente" />}

              {/* Une conversation qui s'approfondit peut devenir un Travail */}
              {echanges.length >= 2 && !propMasquee && !envoi && !creation && (
                <div className="rounded-xl border border-[#B45309]/30 bg-[#FFFBEB] px-4 py-3" data-testid="accueil-conservation">
                  <p className="text-xs leading-snug text-[#3F3F3C]">
                    Cette exploration {selection.length > 0 ? `implique ${selection.length} jumeau${selection.length > 1 ? "x" : ""} et ` : ""}pourrait mériter une mémoire persistante.
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <button onClick={conserverCommeTravail} disabled={conservation} data-testid="conserver-travail-btn" className="flex items-center gap-1.5 rounded-md bg-[#B45309] px-2.5 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-[#92400E] disabled:opacity-50">
                      <FolderOpen size={12} /> {conservation ? "Conservation…" : "Conserver comme travail"}
                    </button>
                    <button onClick={() => setPropMasquee(true)} data-testid="continuer-sans-conserver-btn" className="rounded-md border border-[#E5E5E3] bg-white px-2.5 py-1.5 text-[11px] text-[#52524F] transition-colors hover:text-[#111110]">
                      Continuer sans conserver
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Composer — place réservée, toujours au même endroit */}
      <div className="shrink-0 border-t border-[#E5E5E3] bg-[#F7F7F6] px-6 py-3" data-testid="accueil-composer-zone">
        <div className="mx-auto w-full max-w-2xl">
          <ComposerFlore testidPrefix="accueil-composer" onEnvoyer={demander} />
          {!enConversation && (
            <p className="mt-2 text-center font-code text-[10px] text-[#71716D]" data-testid="accueil-pied">
              Une question simple peut rester temporaire — une conversation durable devient un Travail. <ArrowRight size={9} className="inline" />
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
