import { useCallback, useEffect, useState } from "react";
import { SealCheck, Warning, FileCode } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";

// Connaissances d'un jumeau né du code, dans sa fiche (/jumeaux/:jid/revue) : chaque Claim s'ouvre sur sa preuve,
// lue au commit ingéré de son dépôt.
const FAMILLES = {
  REALISE_CAPACITE: "À quoi elle sert",
  SERT_ACTEUR: "Pour qui, dans quels parcours",
  DETIENT: "Les informations qu'elle détient",
  APPLIQUE_REGLE: "Les règles qu'elle applique",
  ECHANGE_AVEC: "Avec qui elle échange",
  EXPOSE: "APIs exposées",
  DEPEND_DE: "Dépendances logicielles",
  LIT_VARIABLE: "Configuration lue",
  EXECUTE_IMAGE: "Images exécutées",
};
const STATUT = {
  PROPOSED: "text-[#94A3B8] border-[rgba(148,163,184,0.3)]",
  ACCEPTED: "text-[#4ADE80] border-[#4ADE80]/40",
  CONTESTED: "text-[#F2B84B] border-[#F2B84B]/40",
};
const BORDURE = "border-[rgba(148,163,184,0.16)]";
const FOCUS = "focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#60A5FA]";

// Charge `chemin` et ignore la réponse si la requête est devenue obsolète (changement rapide de sélection, démontage).
function useDonnees(chemin, version = 0) {
  const [etat, setEtat] = useState({ donnees: null, erreur: null });
  useEffect(() => {
    if (!chemin) return undefined;
    let actif = true;
    setEtat({ donnees: null, erreur: null });
    api.get(chemin)
      .then(({ data }) => actif && setEtat({ donnees: data, erreur: null }))
      .catch((e) => actif && setEtat({ donnees: null, erreur: e.response?.data?.detail || "Service indisponible" }));
    return () => { actif = false; };
  }, [chemin, version]);
  return etat;
}

const Message = ({ children }) => <p className="p-8 text-sm text-[#94A3B8]">{children}</p>;

function Preuve({ preuve, claim, onRevue }) {
  const { donnees: extrait, erreur } = useDonnees(`/v2/preuves/${preuve.id}/extrait`);
  const [motif, setMotif] = useState("");
  const [envoi, setEnvoi] = useState(false);

  const reviser = async (decision) => {
    setEnvoi(true);
    try {
      await api.post(`/v2/claims/${claim.id}/revue`, { decision, motif: motif || null });
      toast.success(decision === "ACCEPTED" ? "Claim validé" : "Claim contesté");
      setMotif("");
      onRevue();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Revue impossible");
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <section className="flex h-full flex-col" aria-label="Preuve du claim" data-testid="panneau-preuve">
      <div className={`border-b ${BORDURE} p-4`}>
        <h2 className="text-sm font-semibold text-[#F2F6F8]">{claim.sujet} · {claim.predicat} · {claim.objet}</h2>
        <div className="mt-1 break-all font-code text-[10px] text-[#7C93A8]">{preuve.locator}</div>
        {extrait && (
          <div role="status" className={`mt-2 flex items-center gap-1 text-xs ${extrait.integre ? "text-[#4ADE80]" : "text-[#F2B84B]"}`}>
            {extrait.integre ? <SealCheck size={14} aria-hidden /> : <Warning size={14} aria-hidden />}
            {extrait.integre ? "Preuve intègre au SHA indexé" : "Le contenu ne correspond plus à la preuve"}
          </div>
        )}
      </div>
      <pre className="flex-1 overflow-auto bg-[#071019] p-3 font-code text-[11px] leading-5" data-testid="extrait">
        {!extrait && !erreur && "Lecture de la preuve…"}
        {erreur && `Preuve illisible : ${erreur}`}
        {extrait?.lignes.map((l) => (
          <div key={l.n} className={l.citee ? "bg-[#60A5FA]/15 text-[#F2F6F8]" : "text-[#7C93A8]"}>
            <span className="mr-3 inline-block w-10 select-none text-right opacity-60">{l.n}</span>{l.texte}
          </div>
        ))}
      </pre>
      <div className={`border-t ${BORDURE} p-4`}>
        <label htmlFor="motif-revue" className="mb-1 block text-[10px] uppercase tracking-wider text-[#94A3B8]">Motif (facultatif)</label>
        <input id="motif-revue" value={motif} onChange={(e) => setMotif(e.target.value)} maxLength={2000}
          className={`mb-2 w-full rounded-md border ${BORDURE} bg-[#0F1D28] px-3 py-2 text-xs text-[#F2F6F8] ${FOCUS}`} />
        <div className="flex gap-2">
          <button type="button" disabled={envoi} onClick={() => reviser("ACCEPTED")} data-testid="valider-claim"
            className={`h-9 rounded-md bg-[#60A5FA] px-3 text-xs font-semibold text-[#071019] transition-colors hover:bg-[#93C5FD] disabled:opacity-50 ${FOCUS}`}>Valider</button>
          <button type="button" disabled={envoi} onClick={() => reviser("CONTESTED")} data-testid="contester-claim"
            className={`h-9 rounded-md border border-[#F2B84B]/50 px-3 text-xs text-[#F2B84B] transition-colors hover:bg-[#F2B84B]/10 disabled:opacity-50 ${FOCUS}`}>Contester</button>
        </div>
        {claim.revues[0] && (
          <p className="mt-2 font-code text-[10px] text-[#7C93A8]">Dernière revue : {claim.revues[0].acteur} · {claim.revues[0].decision}{claim.revues[0].motif ? ` · ${claim.revues[0].motif}` : ""}</p>
        )}
      </div>
    </section>
  );
}

// Ce que le jumeau dit de l'application : fiche vivante rédigée par le gardien à chaque commit.
// Le code lu par le jumeau (dépôts, branche, commit) ; le résumé lui-même est rendu par la revue.
function CodeLu({ jid }) {
  const { donnees: fiche } = useDonnees(`/v2/jumeaux/${encodeURIComponent(jid)}/fiche`);
  if (!fiche?.depots?.length) return null;
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Code lu par le jumeau" data-testid="fiche-depots">
      {fiche.depots.map((d) => (
        <li key={d.nom} className={`rounded border ${BORDURE} px-1.5 py-0.5 font-code text-[10px] text-[#94A3B8]`}>
          {d.nom}{d.branche ? ` · ${d.branche}` : ""} · {d.commit}
        </li>
      ))}
    </ul>
  );
}

function Connaissances({ jid }) {
  const [version, setVersion] = useState(0);
  const { donnees: claims, erreur } = useDonnees(`/v2/jumeaux/${encodeURIComponent(jid)}/claims`, version);
  const [selectionId, setSelectionId] = useState(null);
  const recharger = useCallback(() => setVersion((v) => v + 1), []);
  const [claimsAffiches, setClaimsAffiches] = useState(null);
  // Garde la liste affichée pendant un rechargement après revue (pas de clignotement).
  useEffect(() => { if (claims) setClaimsAffiches(claims); }, [claims]);

  if (erreur) return <Message>Jumeau indisponible : {erreur}</Message>;
  if (!claimsAffiches) return <Message>Chargement…</Message>;

  const selection = claimsAffiches.find((c) => c.id === selectionId);
  const preuve = selection?.preuves.at(-1);
  const familles = [
    ...Object.entries(FAMILLES).map(([p, titre]) => [titre, claimsAffiches.filter((c) => c.predicat === p)]),
    ["Proposées en conversation", claimsAffiches.filter((c) => !FAMILLES[c.predicat])],
  ].filter(([, liste]) => liste.length);

  return (
    <div className="grid gap-6 lg:grid-cols-2" data-testid="fiche-jumeau">
      <div>
        <CodeLu jid={jid} />
        <p className="mt-4 text-xs text-[#94A3B8]">{claimsAffiches.length} connaissances prouvées par le code</p>
        {familles.map(([titre, liste]) => (
          <section key={titre} className="mt-5" aria-label={titre}>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-[#94A3B8]">{titre} ({liste.length})</h2>
            {liste.map((c) => (
              <div key={c.id}>
              <button type="button" onClick={() => setSelectionId(c.id)} aria-pressed={c.id === selectionId}
                disabled={!c.preuves.length} data-testid={`claim-${c.id}`}
                className={`mb-1 flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-[rgba(148,163,184,0.07)] ${FOCUS} ${c.id === selectionId ? "bg-[rgba(96,165,250,0.12)]" : ""}`}>
                <FileCode size={13} aria-hidden className="shrink-0 text-[#7C93A8]" />
                <span className="flex-1 truncate font-code text-[#F2F6F8]">{c.objet}</span>
                <span className={`rounded border px-1.5 font-code text-[9px] ${STATUT[c.statut] || STATUT.PROPOSED}`}>{c.statut} · {c.maturite}</span>
                <span className="w-8 text-right font-code text-[9px] text-[#7C93A8]">{Math.round((c.confiance ?? 0) * 100)}%</span>
              </button>
              {c.ancres?.map((a) => (
                <div key={`${a.chemin}:${a.ligne_debut}`} className="ml-7 break-all font-code text-[10px] text-[#7C93A8]" data-testid={`ancre-${c.id}`}>
                  concerne : {a.chemin}:{a.ligne_debut === a.ligne_fin ? a.ligne_debut : `${a.ligne_debut}-${a.ligne_fin}`}
                </div>
              ))}
              </div>
            ))}
          </section>
        ))}
      </div>
      <div className={`self-start rounded-lg border ${BORDURE} lg:sticky lg:top-0`}>
        {preuve
          ? <Preuve key={selection.id} preuve={preuve} claim={selection} onRevue={recharger} />
          : <Message>Choisissez une connaissance pour ouvrir sa preuve dans le code.</Message>}
      </div>
    </div>
  );
}

export default function ConnaissancesCode({ jid }) {
  // key={jid} : changer de jumeau repart d'un état vierge (pas d'anciens claims ni d'ancienne sélection).
  return <Connaissances key={jid} jid={jid} />;
}
