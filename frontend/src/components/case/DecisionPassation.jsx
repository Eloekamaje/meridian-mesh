import { useEffect, useState } from "react";
import { Plus, X, Sparkle } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";

// Enregistrer une décision avec sa NOTE DE PASSATION (Continuous Improvement & Learning Model, « Decision Handoff ») :
// ce sur quoi elle repose, ce qu'on en attend (départ → cible), ce qu'on surveille (seuil), ce qu'on ignore encore, quand on la revoit.
// Flore préremplit ce qu'elle sait ; les chiffres et les seuils restent à la personne. Une fois consignée, la décision met le travail en veille.

const champ = "h-9 w-full rounded-md border border-[rgba(148,163,184,0.2)] bg-[#0F1D28] px-2.5 text-[13px] text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/60 focus:outline-none";
const etiquette = "block font-code text-[11px] uppercase tracking-[0.16em] text-[#94A3B8]";

const nombre = (v) => (v === "" || v == null ? null : Number(String(v).replace(",", ".")));
const valide = (v) => v !== null && Number.isFinite(v);

function Rubrique({ titre, aide, onAjouter, libelleAjout, children }) {
  return (
    <section className="space-y-2">
      <div>
        <h3 className={etiquette}>{titre}</h3>
        {aide && <p className="mt-0.5 text-xs text-[#7C93A8]">{aide}</p>}
      </div>
      {children}
      <button type="button" onClick={onAjouter} className="flex items-center gap-1 text-xs font-medium text-[#60A5FA] hover:text-[#93C5FD]">
        <Plus size={12} /> {libelleAjout}
      </button>
    </section>
  );
}

function Ligne({ onSupprimer, children, testid }) {
  return (
    <div className="flex items-start gap-2" data-testid={testid}>
      <div className="grid flex-1 grid-cols-2 gap-2 sm:grid-cols-[minmax(0,1fr)_5rem_5rem_5rem]">{children}</div>
      <button type="button" onClick={onSupprimer} title="Retirer" className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[#7C93A8] hover:bg-white/[0.06] hover:text-white">
        <X size={13} />
      </button>
    </div>
  );
}

export default function DecisionPassation({ cas, onFermer, onEnregistree }) {
  const { mesh } = useMesh();
  const [charge, setCharge] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  const [decision, setDecision] = useState("");
  const [hypotheses, setHypotheses] = useState([]);
  const [attendus, setAttendus] = useState([]);
  const [risques, setRisques] = useState([]);
  const [inconnues, setInconnues] = useState([]);
  const [revue, setRevue] = useState("");
  const [gain, setGain] = useState("");
  const [reference, setReference] = useState("");

  // Flore prépare un brouillon à partir de ce qu'elle sait du travail
  useEffect(() => {
    let vivant = true;
    api.get(`/cases/${cas.id}/passation/brouillon`).then(({ data }) => {
      if (!vivant) return;
      setDecision(data.decision || "");
      setHypotheses(data.hypotheses || []);
      setGain(data.gain || "");
      setReference(data.reference?.ref || "");
      setAttendus([{ indicateur: "", depart: "", cible: "", unite: "" }]);
      setInconnues((data.inconnues || []).map((i) => i.texte));
      setRevue((data.revue_le || "").slice(0, 10));
    }).catch(() => {}).finally(() => vivant && setCharge(true));
    return () => { vivant = false; };
  }, [cas.id]);

  useEffect(() => {
    const echap = (e) => e.key === "Escape" && onFermer();
    document.addEventListener("keydown", echap);
    return () => document.removeEventListener("keydown", echap);
  }, [onFermer]);

  const maj = (setter, i, cle, v) => setter((l) => l.map((x, k) => (k === i ? { ...x, [cle]: v } : x)));
  const majTexte = (setter, i, v) => setter((l) => l.map((x, k) => (k === i ? v : x)));
  const retirer = (setter, i) => setter((l) => l.filter((_, k) => k !== i));

  // Une ligne d'attendu est complète si elle a un indicateur, un départ et une cible chiffrés ; un risque, un libellé et un seuil.
  const attendusOk = attendus.filter((a) => a.indicateur.trim() && valide(nombre(a.depart)) && valide(nombre(a.cible)));
  const risquesOk = risques.filter((r) => r.texte.trim() && valide(nombre(r.seuil)));
  const inconnuesOk = inconnues.filter((t) => t.trim());
  const vide = (a) => !a.indicateur.trim() && a.depart === "" && a.cible === "";
  const incompletes = attendus.filter((a) => !vide(a)).length - attendusOk.length + risques.length - risquesOk.length;
  const peutEnvoyer = decision.trim() && (attendusOk.length + risquesOk.length + inconnuesOk.length) > 0 && incompletes === 0 && !envoi;

  const enregistrer = async () => {
    setEnvoi(true);
    try {
      await api.post(`/cases/${cas.id}/decisions`, {
        texte: decision.trim(),
        type: "arbitrage",
        passation: {
          hypotheses: hypotheses.filter((h) => h.trim()),
          attendus: attendusOk.map((a) => ({ indicateur: a.indicateur, depart: nombre(a.depart), cible: nombre(a.cible), unite: a.unite })),
          risques: risquesOk.map((r) => ({ texte: r.texte, jumeau: r.jumeau || null, sens: r.sens || "hausse", seuil: nombre(r.seuil), unite: r.unite })),
          inconnues: inconnuesOk.map((texte) => ({ texte })),
          revue_le: revue ? `${revue}T00:00:00+00:00` : null,
          reference: reference.trim() ? { systeme: "Jira", ref: reference.trim() } : null,
        },
      });
      const { data } = await api.get(`/cases/${cas.id}`);
      onEnregistree(data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Impossible d'enregistrer la décision");
      setEnvoi(false);
    }
  };

  const jumeauxDuTravail = (cas.jumeaux || []).map((id) => ({ id, nom: mesh?.jumeaux.find((j) => j.id === id)?.nom || id }));

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50" onMouseDown={(e) => e.target === e.currentTarget && onFermer()} data-testid="decision-passation">
      <aside className="flex h-full w-full max-w-xl flex-col border-l border-[rgba(148,163,184,0.16)] bg-[#0C1724] shadow-2xl" role="dialog" aria-label="Consigner une décision">
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-[rgba(148,163,184,0.12)] px-5 py-4">
          <div>
            <h2 className="font-display text-base font-semibold text-[#F2F6F8]">Consigner la décision</h2>
            <p className="mt-1 flex items-start gap-1.5 text-xs leading-relaxed text-[#94A3B8]">
              <Sparkle size={12} weight="fill" className="mt-0.5 shrink-0 text-[#60A5FA]" />
              J'ai prérempli ce que je sais. Indiquez ce que vous en attendez, je l'observerai avec les jumeaux et je reviendrai vers vous à la revue.
            </p>
          </div>
          <button onClick={onFermer} title="Fermer" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-[#7C93A8] hover:bg-white/[0.06] hover:text-white">
            <X size={15} />
          </button>
        </header>

        <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-5 py-5">
          {!charge && <p className="font-code text-[11px] text-[#7C93A8]">Flore prépare la note…</p>}
          <section className="space-y-1.5">
            <label htmlFor="passation-decision" className={etiquette}>Décision</label>
            <textarea id="passation-decision" value={decision} onChange={(e) => setDecision(e.target.value)} rows={2} data-testid="passation-decision"
              placeholder="Ce qui est décidé, en une phrase"
              className="w-full resize-none rounded-md border border-[rgba(148,163,184,0.2)] bg-[#0F1D28] px-2.5 py-2 text-[13px] text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/60 focus:outline-none" />
          </section>

          <Rubrique titre="Ce sur quoi elle repose" aide="Les hypothèses : si l'une tombe, la décision est à revoir." onAjouter={() => setHypotheses((l) => [...l, ""])} libelleAjout="Ajouter une hypothèse">
            {hypotheses.map((h, i) => (
              <div key={i} className="flex items-center gap-2">
                <input value={h} onChange={(e) => majTexte(setHypotheses, i, e.target.value)} className={champ} aria-label={`Hypothèse ${i + 1}`} />
                <button type="button" onClick={() => retirer(setHypotheses, i)} title="Retirer" className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[#7C93A8] hover:bg-white/[0.06] hover:text-white"><X size={13} /></button>
              </div>
            ))}
          </Rubrique>

          <Rubrique titre="Ce qu'on en attend" aide={`Un indicateur, sa valeur de départ et la cible. Je compare ce que les jumeaux observent à cette cible.${gain ? ` Gain annoncé : ${gain}` : ""}`} onAjouter={() => setAttendus((l) => [...l, { indicateur: "", depart: "", cible: "", unite: "" }])} libelleAjout="Ajouter un résultat attendu">
            {attendus.map((a, i) => (
              <Ligne key={i} onSupprimer={() => retirer(setAttendus, i)} testid={`passation-attendu-${i}`}>
                <input value={a.indicateur} onChange={(e) => maj(setAttendus, i, "indicateur", e.target.value)} placeholder="Indicateur" aria-label="Indicateur" className={`${champ} col-span-2 sm:col-span-1`} data-testid={`passation-attendu-indicateur-${i}`} />
                <input value={a.depart} onChange={(e) => maj(setAttendus, i, "depart", e.target.value)} placeholder="Départ" inputMode="decimal" aria-label="Valeur de départ" className={champ} data-testid={`passation-attendu-depart-${i}`} />
                <input value={a.cible} onChange={(e) => maj(setAttendus, i, "cible", e.target.value)} placeholder="Cible" inputMode="decimal" aria-label="Cible" className={champ} data-testid={`passation-attendu-cible-${i}`} />
                <input value={a.unite} onChange={(e) => maj(setAttendus, i, "unite", e.target.value)} placeholder="Unité" aria-label="Unité" className={champ} />
              </Ligne>
            ))}
          </Rubrique>

          <Rubrique titre="Ce qu'on surveille" aide="Un risque et le seuil au-delà duquel il remet la décision en question." onAjouter={() => setRisques((l) => [...l, { texte: "", jumeau: "", sens: "hausse", seuil: "", unite: "" }])} libelleAjout="Ajouter un risque">
            {risques.map((r, i) => (
              <div key={i} className="space-y-2 rounded-lg border border-[rgba(148,163,184,0.12)] p-2.5" data-testid={`passation-risque-${i}`}>
                <div className="flex items-center gap-2">
                  <input value={r.texte} onChange={(e) => maj(setRisques, i, "texte", e.target.value)} placeholder="Le risque (ce qui pourrait mal tourner)" aria-label="Risque" className={champ} data-testid={`passation-risque-texte-${i}`} />
                  <button type="button" onClick={() => retirer(setRisques, i)} title="Retirer" className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[#7C93A8] hover:bg-white/[0.06] hover:text-white"><X size={13} /></button>
                </div>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <select value={r.jumeau} onChange={(e) => maj(setRisques, i, "jumeau", e.target.value)} aria-label="Jumeau qui l'observe" className={`${champ} col-span-2 sm:col-span-1`}>
                    <option value="">Jumeau…</option>
                    {jumeauxDuTravail.map((j) => <option key={j.id} value={j.id}>{j.nom}</option>)}
                  </select>
                  <select value={r.sens} onChange={(e) => maj(setRisques, i, "sens", e.target.value)} aria-label="Sens" className={champ}>
                    <option value="hausse">au-delà de</option>
                    <option value="baisse">sous</option>
                  </select>
                  <input value={r.seuil} onChange={(e) => maj(setRisques, i, "seuil", e.target.value)} placeholder="Seuil" inputMode="decimal" aria-label="Seuil" className={champ} data-testid={`passation-risque-seuil-${i}`} />
                  <input value={r.unite} onChange={(e) => maj(setRisques, i, "unite", e.target.value)} placeholder="Unité" aria-label="Unité" className={champ} />
                </div>
              </div>
            ))}
          </Rubrique>

          <Rubrique titre="Ce qu'on ignore encore" aide="Des questions ouvertes que les jumeaux pourraient lever." onAjouter={() => setInconnues((l) => [...l, ""])} libelleAjout="Ajouter une inconnue">
            {inconnues.map((t, i) => (
              <div key={i} className="flex items-center gap-2">
                <input value={t} onChange={(e) => majTexte(setInconnues, i, e.target.value)} className={champ} aria-label={`Inconnue ${i + 1}`} />
                <button type="button" onClick={() => retirer(setInconnues, i)} title="Retirer" className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[#7C93A8] hover:bg-white/[0.06] hover:text-white"><X size={13} /></button>
              </div>
            ))}
          </Rubrique>

          <section className="space-y-1.5">
            <label htmlFor="passation-reference" className={etiquette}>Chantier Jira lié (facultatif)</label>
            <input id="passation-reference" value={reference} onChange={(e) => setReference(e.target.value)} placeholder="PAY-140" className={`${champ} max-w-[12rem] font-code`} data-testid="passation-reference-saisie" />
            <p className="text-xs text-[#7C93A8]">Méridian ne suit pas les tickets : il garde la référence pour relier la décision à son action et observer ses effets.</p>
          </section>

          <section className="space-y-1.5">
            <label htmlFor="passation-revue" className={etiquette}>Revue le</label>
            <input id="passation-revue" type="date" value={revue} onChange={(e) => setRevue(e.target.value)} className={`${champ} max-w-[12rem]`} data-testid="passation-revue" />
            <p className="text-xs text-[#7C93A8]">Ce jour-là, je vous demande de maintenir, rouvrir ou clore la décision.</p>
          </section>
        </div>

        <footer className="shrink-0 space-y-2 border-t border-[rgba(148,163,184,0.12)] px-5 py-3.5">
          {incompletes > 0 && <p className="text-xs text-[#F2B84B]">{incompletes} ligne{incompletes > 1 ? "s" : ""} incomplète{incompletes > 1 ? "s" : ""} : un indicateur demande départ et cible chiffrés, un risque son seuil.</p>}
          {incompletes === 0 && decision.trim() && attendusOk.length + risquesOk.length + inconnuesOk.length === 0 && <p className="text-xs text-[#94A3B8]">Ajoutez au moins une chose à observer : sans cela, il n'y a rien à surveiller.</p>}
          <div className="flex items-center justify-end gap-2">
            <button onClick={onFermer} className="rounded-md border border-[rgba(148,163,184,0.2)] px-3.5 py-2 text-xs text-[#D8E2EA] hover:border-white/30">Annuler</button>
            <button onClick={enregistrer} disabled={!peutEnvoyer} data-testid="passation-enregistrer"
              className="rounded-md bg-[#60A5FA] px-4 py-2 text-xs font-semibold text-[#071019] transition-colors hover:bg-[#93C5FD] disabled:cursor-not-allowed disabled:opacity-40">
              {envoi ? "Enregistrement…" : "Consigner et mettre en veille"}
            </button>
          </div>
        </footer>
      </aside>
    </div>
  );
}
