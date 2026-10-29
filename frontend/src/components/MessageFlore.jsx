import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ArrowsClockwise, CaretLeft, CaretRight, Copy, PencilSimple, ThumbsDown, ThumbsUp } from "@phosphor-icons/react";
import api from "@/lib/api";
import useFluxAction from "@/lib/useFluxAction";
import { erreurAction, explicationArret, navBranches, navVersions, urlMessage } from "@/lib/conversationFlore";
import MarkdownFlore from "./MarkdownFlore";
import PropositionsFlore from "./PropositionsFlore";
import MarqueRelecture from "./MarqueRelecture";
import MarqueOrigine from "./MarqueOrigine";
import BrouillonFlore from "./BrouillonFlore";
import LigneActiviteFlore from "./LigneActiviteFlore";
import { PreuvesMessage } from "./case/VeilleTravail";

// Les deux composants de la conversation unique : la même question, la même réponse de Flore — rendu, marques, preuves,
// actions — dans le panneau et dans le fil d'un Travail. `prefixe` = /cases/{cid} ; sans lui (démonstration, travail
// pas encore né, réponse non enregistrée) seul « Copier » est proposé : aucune action ne promet ce qu'elle ne fait pas.

const BTN = "flex h-7 min-w-7 items-center justify-center gap-1 rounded-lg px-1.5 text-[#64748B] transition-colors hover:bg-white/[0.06] hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#60A5FA] disabled:opacity-40";

function copier(texte, confirmation) {
  navigator.clipboard?.writeText(texte);
  toast.success(confirmation);
}

function ChoixVersion({ nav, libelle, onChoisir, bloque, testid }) {
  if (!nav) return null;
  return (
    <span className="flex items-center font-code text-[11px] text-[#7C93A8]" data-testid={testid}>
      <button type="button" className={BTN} disabled={bloque || nav.precedent == null} onClick={() => onChoisir(nav.precedent)} aria-label={`${libelle} précédente`}><CaretLeft size={12} /></button>
      <span aria-live="polite" aria-label={`${libelle} ${nav.k} sur ${nav.total}`}>{nav.k}/{nav.total}</span>
      <button type="button" className={BTN} disabled={bloque || nav.suivant == null} onClick={() => onChoisir(nav.suivant)} aria-label={`${libelle} suivante`}><CaretRight size={12} /></button>
    </span>
  );
}

export function MessageFlore({
  message, index, prefixe, onMessage, onMessages, onRelire, bloque = false,
  corps, activite, preuves, testid, children,
}) {
  const [pourquoi, setPourquoi] = useState(false);
  const [motif, setMotif] = useState("");
  const { flux, lancer, arreter } = useFluxAction();
  const agit = !!prefixe && index != null;
  const occupe = bloque || !!flux;

  const retour = async (valeur, motifLibre) => {
    try {
      const { data } = await api.post(urlMessage(prefixe, index, "retour"), motifLibre ? { valeur, motif: motifLibre } : { valeur });
      onMessage?.(index, { ...message, retour: data });
      setPourquoi(false);
      setMotif("");
      toast.success(valeur === "utile" ? "Retour enregistré : réponse utile" : "Retour enregistré : réponse fausse ou inutile");
    } catch (err) {
      toast.error(erreurAction(err, "Retour"));
    }
  };

  const regenerer = async () => {
    try {
      const rep = await lancer(urlMessage(prefixe, index, "regenerer/flux"), {}, () => onRelire?.());
      if (rep) onMessage?.(index, { ...rep, anime: false });
    } catch (err) {
      toast.error(erreurAction(err, "Régénération"));
    }
  };

  // Approbation en ligne : la revue humaine d'une connaissance proposée, exécutée une seule fois par le serveur
  const decider = async (claim, decision) => {
    try {
      const { data } = await api.post(urlMessage(prefixe, index, "approbation"), { claim, decision });
      onMessage?.(index, data);
      toast.success(decision === "ACCEPTED" ? "Connaissance validée" : "Connaissance contestée");
    } catch (err) {
      toast.error(err?.response?.data?.detail || erreurAction(err, "Décision"));
      if (err?.response?.status === 409) onRelire?.(); // tranchée ailleurs : on montre l'état réel
    }
  };

  const choisirVersion = async (i) => {
    try {
      const { data } = await api.post(urlMessage(prefixe, index, "version"), { index: i });
      onMessage?.(index, data);
    } catch (err) {
      toast.error(erreurAction(err, "Changement de version"));
    }
  };

  const nav = navVersions(message);
  return (
    <div className="space-y-2" data-testid={testid}>
      {activite && <LigneActiviteFlore activite={activite} testid={testid ? `${testid}-activite` : undefined} />}
      {corps ?? <MarkdownFlore texte={message.texte} />}
      {message.interrompu && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-[#F2B84B]/40 bg-[#F2B84B]/[0.06] px-2.5 py-1.5 text-xs text-[#F2B84B]" data-testid="flore-interrompu">
          <span>{explicationArret(message)}</span>
          {agit && !flux && (
            <button type="button" onClick={regenerer} disabled={occupe} data-testid={`reprendre-${index}`}
              className="rounded border border-[#F2B84B]/50 px-2 py-0.5 text-[11px] hover:bg-[#F2B84B]/10 disabled:opacity-50 focus-visible:outline focus-visible:outline-1 focus-visible:outline-[#F2B84B]">
              Reprendre la réponse
            </button>
          )}
        </div>
      )}
      <div>
        <MarqueOrigine data={message} />
        <MarqueRelecture data={message} />
      </div>
      {preuves ?? (message.preuves?.length > 0 && <PreuvesMessage preuves={message.preuves} />)}
      <PropositionsFlore propositions={message.a_approuver} index={index} actif={agit} bloque={occupe} onDecider={decider} />
      {children}
      {flux && <BrouillonFlore flux={flux} onArreter={arreter} testid="flore-regeneration" />}
      {!flux && (
        <div className="flex flex-wrap items-center gap-1 pt-1 text-xs" role="group" aria-label="Actions sur la réponse">
          <button type="button" className={BTN} onClick={() => copier(message.texte || "", "Réponse copiée")} aria-label="Copier la réponse" title="Copier la réponse"><Copy size={13} /></button>
          {agit && (
            <>
              <button type="button" className={BTN} onClick={() => retour("utile")} aria-label="Réponse utile" aria-pressed={message.retour?.valeur === "utile"} title="Réponse utile" data-testid={`retour-utile-${index}`}><ThumbsUp size={13} weight={message.retour?.valeur === "utile" ? "fill" : "regular"} /></button>
              <button type="button" className={BTN} onClick={() => setPourquoi((o) => !o)} aria-label="Réponse fausse ou inutile" aria-pressed={message.retour?.valeur === "faux"} aria-expanded={pourquoi} title="Réponse fausse ou inutile" data-testid={`retour-faux-${index}`}><ThumbsDown size={13} weight={message.retour?.valeur === "faux" ? "fill" : "regular"} /></button>
              <button type="button" className={BTN} onClick={regenerer} disabled={occupe} aria-label="Régénérer la réponse" title="Régénérer" data-testid={`regenerer-${index}`}><ArrowsClockwise size={13} /></button>
              <ChoixVersion nav={nav} libelle="Version" onChoisir={choisirVersion} bloque={occupe} testid={`versions-${index}`} />
            </>
          )}
        </div>
      )}
      {agit && pourquoi && !flux && (
        <form
          className="flex items-center gap-2"
          onSubmit={(e) => { e.preventDefault(); retour("faux", motif.trim()); }}
          onKeyDown={(e) => { if (e.key === "Escape") setPourquoi(false); }}
        >
          <input
            autoFocus value={motif} onChange={(e) => setMotif(e.target.value)} maxLength={500}
            aria-label="Pourquoi cette réponse est fausse ou inutile (facultatif)" placeholder="Pourquoi ? (facultatif)"
            className="h-8 flex-1 rounded-md border border-white/[0.12] bg-[#0B1220] px-2 text-xs text-[#D8E2EA] placeholder:text-[#526578] focus:border-[#60A5FA]/60 focus:outline-none"
          />
          <button type="submit" className="rounded-md bg-[#60A5FA] px-2.5 py-1 text-xs font-semibold text-[#071019] focus-visible:outline focus-visible:outline-2 focus-visible:outline-white">Envoyer</button>
        </form>
      )}
    </div>
  );
}

// `variante` : "panneau" (bulle bleue) ou "travail" (bulle sombre). `etiquette` : rôle affiché en démonstration.
// `extraActions` : boutons propres à l'écran (ex. copier le lien vers le message).
export function QuestionFlore({
  message, index, prefixe, onMessages, onRelire, onTronquer, bloque = false, variante = "travail", etiquette, extraActions, testid,
}) {
  const [edition, setEdition] = useState(false);
  const [brouillon, setBrouillon] = useState("");
  const champ = useRef(null);
  const { flux, lancer, arreter } = useFluxAction();
  const agit = !!prefixe && index != null;
  const occupe = bloque || !!flux;
  useEffect(() => { if (edition) champ.current?.focus(); }, [edition]);

  const ouvrir = () => { setBrouillon(message.texte || ""); setEdition(true); };
  const envoyer = async (e) => {
    e?.preventDefault();
    const texte = brouillon.trim();
    if (!texte || texte === message.texte) { setEdition(false); return; }
    setEdition(false);
    onTronquer?.(index, texte); // comme le serveur : la suite part dans une branche, la nouvelle réponse s'écrit à sa place
    try {
      const rep = await lancer(urlMessage(prefixe, index, "modifier/flux"), { texte }, () => onRelire?.());
      if (rep?.messages) onMessages?.(rep.messages);
    } catch (err) {
      toast.error(erreurAction(err, "Modification"));
      onRelire?.(); // rien n'a changé côté serveur : on remet la conversation telle qu'elle est
    }
  };
  const choisirBranche = async (i) => {
    try {
      const { data } = await api.post(urlMessage(prefixe, index, "branche"), { index: i });
      onMessages?.(data.messages);
    } catch (err) {
      toast.error(erreurAction(err, "Changement de branche"));
    }
  };

  const bulle = variante === "panneau"
    ? "ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm border border-[#60A5FA]/30 bg-[#60A5FA]/10 px-4 py-2.5 text-sm shadow-sm"
    : "max-w-[85%] rounded-2xl rounded-tr-xs bg-[#162534] px-5 py-3.5 text-[14.5px] shadow-sm";
  return (
    <div className="flex flex-col items-end gap-1.5" data-testid={testid}>
      {!flux && (
        <div className="flex items-center gap-1 pr-1 text-xs text-[#64748B]" role="group" aria-label="Actions sur la question">
          <button type="button" className={BTN} onClick={() => copier(message.texte || "", "Message copié")} aria-label="Copier le message" title="Copier le message"><Copy size={12} /></button>
          {extraActions}
          {agit && <button type="button" className={BTN} onClick={ouvrir} disabled={occupe || edition} aria-label="Modifier ma question" title="Modifier ma question" data-testid={`modifier-${index}`}><PencilSimple size={12} /></button>}
          {agit && <ChoixVersion nav={navBranches(message)} libelle="Branche" onChoisir={choisirBranche} bloque={occupe} testid={`branches-${index}`} />}
        </div>
      )}
      {edition ? (
        <form onSubmit={envoyer} className="w-full max-w-[85%] space-y-1.5" onKeyDown={(e) => { if (e.key === "Escape") setEdition(false); }}>
          <textarea
            ref={champ} value={brouillon} onChange={(e) => setBrouillon(e.target.value)} rows={3}
            aria-label="Modifier ma question"
            className="w-full resize-y rounded-xl border border-[#60A5FA]/50 bg-[#0B1220] p-2.5 text-sm text-[#F2F6F8] focus:outline-none"
          />
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setEdition(false)} className="rounded-md px-2.5 py-1 text-xs text-[#94A3B8] hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#60A5FA]">Annuler</button>
            <button type="submit" disabled={!brouillon.trim()} className="rounded-md bg-[#60A5FA] px-2.5 py-1 text-xs font-semibold text-[#071019] disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white">Envoyer</button>
          </div>
        </form>
      ) : (
        <div className={`${bulle} text-[#F2F6F8] leading-relaxed`}>
          {etiquette && <div className="mb-0.5 font-code text-[9px] uppercase tracking-wider text-[#BFDBFE]">{etiquette}</div>}
          <p className="whitespace-pre-line">{message.texte}</p>
        </div>
      )}
      {flux && <div className="w-full"><BrouillonFlore flux={flux} onArreter={arreter} testid="flore-modification" /></div>}
    </div>
  );
}
