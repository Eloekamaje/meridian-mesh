// Surface Travail du kiosque : résultat structuré (base commune) + onglets
// Conversation / Aperçu. Données du fixture de session uniquement.
import { useState } from "react";
import { CheckCircle, FileText, Warning, ClipboardText } from "@phosphor-icons/react";
import FloreKiosque from "./FloreKiosque";

function Section({ titre, children, testid }) {
  return (
    <div className="rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-4" data-testid={testid}>
      <div className="mb-2 font-code text-[9px] uppercase tracking-[0.25em] text-[#7C93A8]">{titre}</div>
      {children}
    </div>
  );
}

export default function TravailKiosque({ travail, messages, preuves, onPreuve }) {
  const [onglet, setOnglet] = useState("apercu");
  return (
    <div className="flex h-full flex-col" data-testid="travail-kiosque">
      <div className="mb-3 flex items-center gap-2">
        <button
          onClick={() => setOnglet("apercu")}
          data-testid="kiosque-onglet-apercu"
          className={`rounded-lg px-3 py-1.5 font-code text-[11px] transition-colors ${onglet === "apercu" ? "bg-[rgba(37,208,200,0.12)] text-[#25D0C8]" : "text-[#7C93A8] hover:text-[#D8E2EA]"}`}
        >
          Aperçu
        </button>
        <button
          onClick={() => setOnglet("conversation")}
          data-testid="kiosque-onglet-conversation"
          className={`rounded-lg px-3 py-1.5 font-code text-[11px] transition-colors ${onglet === "conversation" ? "bg-[rgba(37,208,200,0.12)] text-[#25D0C8]" : "text-[#7C93A8] hover:text-[#D8E2EA]"}`}
        >
          Conversation
        </button>
      </div>
      {onglet === "conversation" ? (
        <FloreKiosque messages={messages} activite={null} frappeActive={false} roleLabel={travail.role} onPreuve={onPreuve} compact />
      ) : (
        <div className="flex-1 space-y-3 overflow-y-auto pr-1">
          <div>
            <h2 className="font-display text-xl font-bold text-[#F2F6F8]" data-testid="kiosque-travail-titre">{travail.titre}</h2>
            <p className="mt-1 text-sm text-[#7C93A8]">{travail.objectif}</p>
          </div>
          <Section titre="Synthèse" testid="kiosque-travail-synthese">
            <p className="text-sm leading-relaxed text-[#D8E2EA]">{travail.synthese}</p>
          </Section>
          <Section titre="Commun aux trois initiatives" testid="kiosque-travail-commun">
            <ul className="space-y-1.5">
              {travail.commun.map((c, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-[#D8E2EA]">
                  <CheckCircle size={14} className="mt-0.5 shrink-0 text-[#34D399]" /> {c}
                </li>
              ))}
            </ul>
          </Section>
          <Section titre="Spécifique à chacune" testid="kiosque-travail-specifique">
            <ul className="space-y-2">
              {Object.entries(travail.specifique).map(([k, v]) => (
                <li key={k} className="text-sm">
                  <span className="font-semibold text-[#F2F6F8]">{k}</span>
                  <span className="text-[#7C93A8]"> — {v}</span>
                </li>
              ))}
            </ul>
          </Section>
          <Section titre="À valider avant estimation" testid="kiosque-travail-avalider">
            <ul className="space-y-1.5">
              {travail.aValider.map((c, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-[#D8E2EA]">
                  <Warning size={14} className="mt-0.5 shrink-0 text-[#F2B84B]" /> {c}
                </li>
              ))}
            </ul>
          </Section>
          <Section titre="Prochaines actions" testid="kiosque-travail-actions">
            <ul className="space-y-1.5">
              {travail.prochainesActions.map((c, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-[#D8E2EA]">
                  <ClipboardText size={14} className="mt-0.5 shrink-0 text-[#25D0C8]" /> {c}
                </li>
              ))}
            </ul>
          </Section>
          <Section titre="Preuves" testid="kiosque-travail-preuves">
            <div className="flex flex-wrap gap-2">
              {travail.preuves.map((pid) => (
                <button
                  key={pid}
                  onClick={() => onPreuve(pid)}
                  data-testid={`kiosque-travail-preuve-${pid}`}
                  className="flex items-center gap-1.5 rounded-md border border-[rgba(148,163,184,0.16)] bg-[#071019] px-2.5 py-1.5 font-code text-[10px] text-[#58A6FF] transition-colors hover:border-[#58A6FF]/50"
                >
                  <FileText size={11} /> {preuves[pid]?.title || pid}
                </button>
              ))}
            </div>
            {travail.hypotheses.map((h, i) => (
              <p key={i} className="mt-2 text-[11px] italic text-[#7C93A8]">{h}</p>
            ))}
          </Section>
        </div>
      )}
    </div>
  );
}
