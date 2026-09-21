import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkle, Compass, Newspaper, ArrowRight, Eye, FolderOpen } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { usePerimetre } from "@/lib/perimetre";
import { useContexte } from "@/lib/contexte";
import { usePilotage } from "@/lib/pilotage";
import ComposerFlore from "@/components/ComposerFlore";
import FloreActivite, { delaiMin } from "@/components/FloreActivite";
import LigneActiviteFlore from "@/components/LigneActiviteFlore";
import {
  CREATION_TRAVAIL_ACTIVE,
  FLORE_PRESENTATION,
  FLORE_REPONSE_EN_CONSTRUCTION,
  PROPOSITION_DEMO,
} from "@/lib/messagesFlore";

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

// Gras « **texte** » et code « `texte` » des réponses de Flore — comme dans la page Travail
function TexteRiche({ texte }) {
  return String(texte || "")
    .split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
    .map((part, i) =>
      part.startsWith("**") ? <strong key={i} className="font-semibold text-white">{part.slice(2, -2)}</strong>
      : part.startsWith("`") ? <code key={i} className="rounded bg-white/[0.06] px-1 font-code text-[12px] text-sky-300">{part.slice(1, -1)}</code>
      : part
    );
}

function BulleFlore({ data, index, onSuite }) {
  const navigate = useNavigate();
  const [preuves, setPreuves] = useState(false);
  return (
    <div className="rise" data-testid={`accueil-reponse-${index}`}>
      <div className="flex items-center gap-1.5 font-code text-[9px] uppercase tracking-[0.2em] text-[#BFDBFE]">
        <Sparkle size={11} weight="fill" /> Flore
      </div>
      <p className="mt-1.5 whitespace-pre-line text-sm leading-relaxed text-[#F2F6F8]"><TexteRiche texte={data.reponse || data.texte} /></p>

      {(data.contributions || []).length > 0 && (
        <div className="mt-2.5 space-y-1.5">
          {data.contributions.map((c, k) => (
            <div key={k} className="flex gap-2 rounded-lg bg-[rgba(148,163,184,0.07)] px-3 py-2 text-xs" data-testid={`accueil-contribution-${index}-${k}`}>
              <span className="shrink-0 font-code text-[10px] font-semibold text-[#60A5FA]">{c.jumeau}</span>
              <span className="text-[#94A3B8]">{c.texte}</span>
            </div>
          ))}
        </div>
      )}

      {(data.preuves || []).length > 0 && (
        <div className="mt-2.5">
          <button onClick={() => setPreuves((p) => !p)} data-testid={`accueil-preuves-${index}`} className="flex items-center gap-1 font-code text-[10px] text-[#60A5FA] hover:underline">
            <Eye size={11} /> Cette conclusion repose sur {data.preuves.length} preuve{data.preuves.length > 1 ? "s" : ""} · {preuves ? "masquer" : "afficher"}
          </button>
          {preuves && (
            <ul className="mt-1.5 space-y-1 border-l-2 border-[#60A5FA]/25 pl-2.5">
              {data.preuves.map((p, k) => (
                <li key={k} className="font-code text-[10px] leading-snug text-[#94A3B8]">
                  <span className="font-semibold text-[#BFDBFE]">{p.source}</span> — {p.detail}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {data.perimetre_investigation && (
        <p className="mt-2.5 font-code text-[9px] uppercase tracking-wider text-[#7C93A8]" data-testid={`accueil-perimetre-${index}`}>
          Périmètre d'investigation : {data.perimetre_investigation.confidentialite} · expire {data.perimetre_investigation.expire}
        </p>
      )}

      {(data.propositions || []).length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {data.propositions.map((p, k) => (
            <button key={k} onClick={() => (p.action === "demo" ? navigate("/demo") : onSuite(p.question || p.label))} data-testid={p.action === "demo" ? "creation-decouvrir-demo" : `accueil-prop-${index}-${k}`}
              className="rounded-full border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-3 py-1.5 text-[11px] text-[#94A3B8] transition-colors hover:border-[#60A5FA]/40 hover:text-[#60A5FA]">
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
  const pilote = usePilotage();
  const [recents, setRecents] = useState([]);
  // « Nouveau travail » hors démonstration : la création réelle n'existe pas encore — Flore se
  // présente puis l'annonce, sans appel réseau (textes dans lib/messagesFlore.js)
  const enConstruction = mode === "creation" && !pilote && !CREATION_TRAVAIL_ACTIVE;
  const [echanges, setEchanges] = useState(() =>
    enConstruction ? [{ role: "flore", data: { reponse: FLORE_PRESENTATION, comportement: "expliquer", propositions: [PROPOSITION_DEMO] } }] : []
  );
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
    if (enConstruction) {
      setEchanges((e) => [
        ...e,
        { role: "moi", texte: q },
        { role: "flore", data: { reponse: FLORE_REPONSE_EN_CONSTRUCTION, comportement: "expliquer", propositions: [PROPOSITION_DEMO] } },
      ]);
      return;
    }
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

  // Kiosque Polaris : le fil et l'activité viennent du moteur de lecture
  const fil = pilote
    ? pilote.echanges.flatMap((e) =>
        e.activite
          ? [{ cle: `${e.id}-a`, role: "activite", activite: e.activite }]
          : [
              ...(e.question ? [{ cle: `${e.id}-q`, role: "moi", texte: e.question }] : []),
              ...(e.data ? [{ cle: `${e.id}-r`, role: "flore", data: e.data }] : []),
            ]
      )
    : echanges;
  const enConversation = fil.length > 0;

  return (
    <div className="flex h-full flex-col overflow-hidden" data-testid="accueil-page">
      {/* Zone de contenu : accueil ou fil de conversation — le chat VIT ici, pas en latéral */}
      <div className="flex-1 overflow-y-auto px-6">
        {creation && !enConversation && !pilote && (
          <div className="mx-auto w-full max-w-2xl pt-4">
            <button onClick={() => navigate("/travaux")} data-testid="creation-retour-travaux" className="flex items-center gap-1.5 rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2.5 py-1.5 text-xs text-[#94A3B8] transition-colors hover:text-[#F2F6F8]">
              ← Travaux
            </button>
          </div>
        )}
        <div className="mx-auto w-full max-w-2xl pb-8">
          {!enConversation ? (
            <div className="flex min-h-[70vh] flex-col items-center justify-center py-10">
              <h1 className="rise text-center font-display text-3xl font-black tracking-tight text-[#F2F6F8] sm:text-4xl" data-testid="accueil-titre">
                {creation ? "Que voulez-vous comprendre\nou accomplir ?" : <>Que voulez-vous comprendre<br />dans votre SI ?</>}
              </h1>
              <p className="rise mt-3 text-center text-sm text-[#94A3B8]" style={{ animationDelay: "60ms" }}>
                {creation
                  ? "Décrivez-le simplement — le travail naît de votre première question, la conversation devient sa mémoire."
                  : `Flore mobilise les jumeaux et compose la représentation utile${nom ? ` — bonjour ${nom}` : ""}.`}
              </p>
              {!creation && (
                <>
                  <div className="rise mt-5 flex flex-wrap justify-center gap-2" style={{ animationDelay: "120ms" }} data-testid="accueil-suggestions">
                    {suggestions.map((s) => (
                      <button key={s} onClick={() => demander(s)} data-testid={`accueil-suggestion-${s.slice(0, 18)}`}
                        className="rounded-full border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-3.5 py-1.5 text-xs text-[#94A3B8] transition-colors hover:border-[#60A5FA]/40 hover:text-[#60A5FA]">
                        {s}
                      </button>
                    ))}
                  </div>
                  <div className="rise mt-10 grid w-full gap-2 sm:grid-cols-3" style={{ animationDelay: "180ms" }}>
                    <button onClick={() => navigate("/actualites")} data-testid="accueil-actus" className="rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-4 text-left transition-colors hover:border-[#60A5FA]/40">
                      <Newspaper size={16} className="text-[#60A5FA]" />
                      <div className="mt-2 text-xs font-semibold text-[#F2F6F8]">Changements d'aujourd'hui</div>
                      <div className="mt-0.5 font-code text-[9px] text-[#7C93A8]">Le briefing du Mesh</div>
                    </button>
                    {recents[0] && (
                      <button onClick={() => navigate(`/travaux/${recents[0].id}`)} data-testid="accueil-reprendre" className="rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-4 text-left transition-colors hover:border-[#60A5FA]/40">
                        <Sparkle size={16} className="text-[#F2B84B]" />
                        <div className="mt-2 truncate text-xs font-semibold text-[#F2F6F8]">Reprendre « {recents[0].titre} »</div>
                        <div className="mt-0.5 font-code text-[9px] text-[#7C93A8]">Continuité du travail</div>
                      </button>
                    )}
                    <button onClick={() => navigate("/atlas")} data-testid="accueil-explorer" className="rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-4 text-left transition-colors hover:border-[#60A5FA]/40">
                      <Compass size={16} className="text-[#60A5FA]" />
                      <div className="mt-2 text-xs font-semibold text-[#F2F6F8]">Explorer mon espace</div>
                      <div className="mt-0.5 font-code text-[9px] text-[#7C93A8]">L'Atlas du Mesh</div>
                    </button>
                  </div>
                </>
              )}
            </div>
          ) : (
            <div className="space-y-6 py-8" data-testid="accueil-fil">
              {fil.map((e, i) =>
                e.role === "activite" ? (
                  <LigneActiviteFlore key={e.cle || i} activite={e.activite} testid={`accueil-activite-trace-${i}`} />
                ) : e.role === "moi" ? (
                  <p key={e.cle || i} className="rise ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-[rgba(96,165,250,0.12)] px-4 py-2.5 text-sm text-[#F2F6F8]" data-testid={`accueil-msg-${i}`}>
                    {e.texte}
                  </p>
                ) : (
                  <BulleFlore key={e.cle || i} data={e.data} index={i} onSuite={demander} />
                )
              )}
              {!pilote && envoi && <FloreActivite testid="accueil-attente" />}
              {/* Démonstration : la ligne d'activité de Flore (une par traitement), sous le dernier message */}
              {(pilote?.activites || []).map((a) => (
                <LigneActiviteFlore key={a.id} activite={a} testid={`accueil-activite-${a.id}`} />
              ))}

              {/* Une conversation qui s'approfondit peut devenir un Travail */}
              {!pilote && echanges.length >= 2 && !propMasquee && !envoi && !creation && (
                <div className="rounded-xl border border-[#F2B84B]/30 bg-[rgba(242,184,75,0.10)] px-4 py-3" data-testid="accueil-conservation">
                  <p className="text-xs leading-snug text-[#D8E2EA]">
                    Cette exploration {selection.length > 0 ? `implique ${selection.length} jumeau${selection.length > 1 ? "x" : ""} et ` : ""}pourrait mériter une mémoire persistante.
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <button onClick={conserverCommeTravail} disabled={conservation} data-testid="conserver-travail-btn" className="flex items-center gap-1.5 rounded-md bg-[#F2B84B] px-2.5 py-1.5 text-[11px] font-semibold text-[#071019] transition-colors hover:bg-[#F8CF7A] disabled:opacity-50">
                      <FolderOpen size={12} /> {conservation ? "Conservation…" : "Conserver comme travail"}
                    </button>
                    <button onClick={() => setPropMasquee(true)} data-testid="continuer-sans-conserver-btn" className="rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2.5 py-1.5 text-[11px] text-[#94A3B8] transition-colors hover:text-[#F2F6F8]">
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
      <div className="shrink-0 border-t border-[rgba(148,163,184,0.16)] bg-[rgba(148,163,184,0.07)] px-6 py-3" data-testid="accueil-composer-zone">
        <div className="mx-auto w-full max-w-2xl">
          <ComposerFlore testidPrefix="accueil-composer" onEnvoyer={demander} />
          {!enConversation && (
            <p className="mt-2 text-center font-code text-[10px] text-[#7C93A8]" data-testid="accueil-pied">
              Une question simple peut rester temporaire — une conversation durable devient un Travail. <ArrowRight size={9} className="inline" />
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
