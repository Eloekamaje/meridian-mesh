import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { CaretDown, CheckCircle, CircleNotch, WarningCircle } from "@phosphor-icons/react";

// Ligne d'activité de Flore — la même partout dans Méridian (vrai backend, démonstration, panneau
// Flore, page Travail, page Nouveau travail).
//
// Une SEULE ligne discrète sous le dernier message :
//   • en cours : petit indicateur animé + libellé court qui se remplace sur place + chevron ;
//   • terminée : « Analyse terminée · Voir l'activité », repliée par défaut.
// Le chevron déplie l'historique (opérations faites, opération en cours, sources consultées) ;
// le refermer n'interrompt jamais le traitement — l'état de l'activité vit chez l'appelant.
//
// activite = { id, status: "running" | "done", ops: [{ label, status: "running" | "done", sources?: string[], outil? }] }
// Un `outil` (P2, appel réel reçu en AG-UI : { nom, etat, arguments, extrait, duree }) est une ligne à part : nom,
// argument principal, durée ; un clic montre arguments et début du résultat (affichés comme données, jamais
// interprétés). Tant que Flore travaille et qu'il y a des outils, la liste est dépliée ; elle se replie à la fin.

const secondes = (d) => (d == null ? "" : `${String(d).replace(".", ",")} s`);
const premierArgument = (args) => {
  const v = args && typeof args === "object" ? Object.values(args).find((x) => typeof x === "string" || typeof x === "number") : null;
  return v == null ? "" : String(v).slice(0, 60);
};

function LigneOutil({ op, testid }) {
  const [detail, setDetail] = useState(false);
  const { outil } = op;
  const enCours = op.status === "running";
  const Icone = outil.etat === "erreur" ? WarningCircle : enCours ? CircleNotch : CheckCircle;
  return (
    <div data-testid={testid}>
      <button type="button" onClick={() => setDetail((d) => !d)} aria-expanded={detail}
        title={op.label} aria-label={`${op.label} — ${outil.nom}${detail ? "" : ", voir le détail"}`}
        className="flex w-full items-start gap-2 rounded text-left hover:text-[#CBD5E1] focus-visible:outline focus-visible:outline-1 focus-visible:outline-[#60A5FA]/60">
        <Icone size={12} aria-hidden="true" className={`mt-0.5 shrink-0 ${enCours ? "animate-spin text-[#60A5FA] motion-reduce:animate-none"
          : outil.etat === "erreur" ? "text-[#F87171]" : "text-[#60A5FA]/70"}`} />
        <span className="min-w-0 flex-1 truncate">
          <span className={enCours ? "text-[#D8E2EA]" : "text-[#7C93A8]"}>{op.label}</span>{" "}
          <span className="font-code text-[11px] text-[#93C5FD]/80">{outil.nom}</span>{" "}
          <span className="font-code text-[11px] text-[#64748B]">{premierArgument(outil.arguments)}</span>
        </span>
        <span className="shrink-0 font-code text-[10px] text-[#64748B]">{enCours ? "en cours…" : secondes(outil.duree)}</span>
      </button>
      {detail && (
        <div className="ml-5 mt-1 space-y-1 border-l border-[#60A5FA]/25 pl-2 font-code text-[11px] text-[#94A3B8]" data-testid={`${testid}-detail`}>
          {outil.arguments != null && <pre className="whitespace-pre-wrap break-words">{JSON.stringify(outil.arguments, null, 1)}</pre>}
          {outil.extrait ? <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words text-[#7C93A8]">{outil.extrait}</pre>
            : !enCours && <span>Aucun résultat lisible.</span>}
        </div>
      )}
    </div>
  );
}
export default function LigneActiviteFlore({ activite, testid = "flore-activite" }) {
  const [choix, setOuvert] = useState(null); // null : suit l'activité (dépliée en cours s'il y a des outils)
  const reduit = useReducedMotion();
  if (!activite) return null;

  const enCours = activite.status !== "done";
  const ops = activite.ops || [];
  const ouvert = choix ?? (enCours && ops.some((o) => o.outil));
  const courante = [...ops].reverse().find((o) => o.status === "running") || ops[ops.length - 1];
  const libelle = courante?.label || "Flore réfléchit…";
  const sources = [...new Set(ops.flatMap((o) => o.sources || []))];
  // Une activité terminée sans aucune étape ne s'annonce pas « Analyse terminée » : elle dit ce qu'elle est.
  const vide = !enCours && ops.length === 0;
  if (vide) {
    return (
      <div className="py-1" data-testid={testid} data-etat="vide">
        <span className="inline-flex min-h-[28px] items-center gap-2 text-xs text-[#7C93A8]" data-testid={`${testid}-libelle`}>
          <CheckCircle size={13} className="shrink-0 text-[#7C93A8]/40" aria-hidden="true" />
          Aucune étape enregistrée
        </span>
      </div>
    );
  }

  return (
    <div className="py-1" data-testid={testid} data-etat={enCours ? "encours" : "termine"}>
      {/* Hauteur fixe : un nouveau libellé ne déplace jamais le fil */}
      <button
        type="button"
        onClick={() => setOuvert(!ouvert)}
        aria-expanded={ouvert}
        data-testid={`${testid}-ligne`}
        className="inline-flex min-h-[28px] max-w-full items-center gap-2 rounded-md text-left text-xs text-[#7C93A8] transition-colors hover:text-[#CBD5E1] focus-visible:outline focus-visible:outline-1 focus-visible:outline-[#60A5FA]/60"
      >
        {enCours ? (
          <CircleNotch size={13} className="shrink-0 animate-spin text-[#60A5FA] motion-reduce:animate-none" aria-hidden="true" />
        ) : (
          <CheckCircle size={13} className="shrink-0 text-[#7C93A8]/70" aria-hidden="true" />
        )}
        {/* Annoncé aux lecteurs d'écran à chaque nouveau libellé */}
        <span className="min-w-0 truncate" role="status" aria-live="polite" data-testid={`${testid}-libelle`}>
          {enCours ? (
            <AnimatePresence mode="wait" initial={false}>
              <motion.span
                key={libelle}
                className="inline-block max-w-full truncate align-bottom"
                initial={reduit ? false : { opacity: 0, y: 3 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reduit ? undefined : { opacity: 0 }}
                transition={{ duration: 0.16 }}
              >
                {libelle}
              </motion.span>
            </AnimatePresence>
          ) : (
            <>
              Analyse terminée <span className="text-[#7C93A8]/60">· Voir l'activité</span>
            </>
          )}
        </span>
        <CaretDown size={12} className={`shrink-0 transition-transform duration-200 ${ouvert ? "rotate-180" : ""}`} aria-hidden="true" />
      </button>

      {ouvert && (
        <div className="mt-1.5 space-y-1.5 border-l border-white/[0.08] pl-3 text-xs" data-testid={`${testid}-detail`}>
          {ops.map((o, i) => (o.outil ? <LigneOutil key={o.outil.id} op={o} testid={`${testid}-outil-${i}`} /> : (
            <div key={`${i}-${o.label}`} className="flex items-start gap-2">
              {o.status === "running" ? (
                <CircleNotch size={12} className="mt-0.5 shrink-0 animate-spin text-[#60A5FA] motion-reduce:animate-none" aria-hidden="true" />
              ) : (
                <CheckCircle size={12} className="mt-0.5 shrink-0 text-[#60A5FA]/70" aria-hidden="true" />
              )}
              <span className={o.status === "running" ? "text-[#D8E2EA]" : "text-[#7C93A8]"}>{o.label}</span>
            </div>
          )))}
          {sources.length > 0 && (
            <div className="pt-1" data-testid={`${testid}-sources`}>
              <div className="mb-1 font-code text-[9px] uppercase tracking-[0.18em] text-[#64748B]">Sources consultées</div>
              <div className="flex flex-wrap gap-1.5">
                {sources.map((s) => (
                  <span key={s} className="rounded-full border border-white/[0.08] bg-white/[0.03] px-2 py-0.5 text-[11px] text-[#94A3B8]">
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
