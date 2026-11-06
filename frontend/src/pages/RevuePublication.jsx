import { useEffect, useState } from "react";
import { ArrowsClockwise, Check, ShieldCheck, X } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { usePerimetre } from "@/lib/perimetre";

const BORDURE = "border-[rgba(148,163,184,0.16)]";
const FOCUS = "focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#60A5FA]";

const SCOPES = {
  TENANT: "Tenant",
  TEAM: "Équipe",
  TWIN: "Jumeau",
  PORTFOLIO: "Portefeuille",
  EXTERNAL: "Externe",
};

const CONFIDENTIALITES = {
  PUBLIC: ["Public", "#34D399"],
  INTERNAL: ["Interne", "#60A5FA"],
  CONFIDENTIAL: ["Confidentiel", "#F2B84B"],
  SECRET: ["Secret", "#F87171"],
};

const cheminFile = (jid) => `/v2/jumeaux/${encodeURIComponent(jid)}/carte/a-reviser`;

function detailErreur(e, defaut) {
  const detail = e.response?.data?.detail;
  return typeof detail === "string" && detail ? detail : defaut;
}

export default function RevuePublication() {
  const { acteur, version } = usePerimetre();
  const [jumeaux, setJumeaux] = useState(null);
  const [erreurJumeaux, setErreurJumeaux] = useState(null);
  const [relectureJumeaux, setRelectureJumeaux] = useState(0);
  const [jid, setJid] = useState("");
  const [file, setFile] = useState(null);
  const [chargementFile, setChargementFile] = useState(false);
  const [erreurFile, setErreurFile] = useState(null);
  const [relecture, setRelecture] = useState(0);
  const [raisons, setRaisons] = useState({});
  const [envoi, setEnvoi] = useState(null);
  const [retour, setRetour] = useState(null);

  const chargementJumeaux = jumeaux === null && !erreurJumeaux;
  const jumeauChoisi = (jumeaux || []).find((j) => j.id === jid) || null;

  useEffect(() => {
    let actif = true;
    setErreurJumeaux(null);
    api.get("/v2/jumeaux")
      .then(({ data }) => {
        if (!actif) return;
        setJumeaux(Array.isArray(data) ? data : []);
      })
      .catch((e) => {
        if (!actif) return;
        setJumeaux([]);
        setErreurJumeaux(detailErreur(e, "Liste des jumeaux indisponible."));
      });
    return () => { actif = false; };
  }, [version, relectureJumeaux]);

  useEffect(() => {
    if (!jid) {
      setFile(null);
      setErreurFile(null);
      setChargementFile(false);
      return undefined;
    }
    let actif = true;
    setChargementFile(true);
    setErreurFile(null);
    api.get(cheminFile(jid))
      .then(({ data }) => {
        if (actif) setFile(Array.isArray(data) ? data : []);
      })
      .catch((e) => {
        if (!actif) return;
        setFile(null);
        setErreurFile(detailErreur(e, "File de revue indisponible."));
      })
      .finally(() => {
        if (actif) setChargementFile(false);
      });
    return () => { actif = false; };
  }, [jid, relecture, version]);

  const choisirJumeau = (id) => {
    setJid(id);
    setFile(null);
    setErreurFile(null);
    setRetour(null);
    setRaisons({});
    setRelecture((n) => n + 1);
  };

  const decider = async (partage, decision) => {
    if (envoi) return;
    setEnvoi({ id: partage.id, decision });
    setRetour(null);
    const raison = (raisons[partage.id] || "").trim();
    try {
      await api.post(`/v2/jumeaux/${encodeURIComponent(jid)}/carte/revue`, {
        share_id: partage.id,
        decision,
        reason: raison || null,
      });
      const message = decision === "APPROVED"
        ? `Partage #${partage.id} approuvé — « ${partage.objet} » devient lisible dans le périmètre ${SCOPES[partage.scope_type] || partage.scope_type}.`
        : `Partage #${partage.id} rejeté — « ${partage.objet} » reste privé.`;
      setRetour({ ton: "succes", texte: message });
      toast.success(decision === "APPROVED" ? "Publication approuvée" : "Publication rejetée");
      setRaisons((avant) => {
        const suite = { ...avant };
        delete suite[partage.id];
        return suite;
      });
      setRelecture((n) => n + 1);
    } catch (e) {
      const texte = detailErreur(e, "Décision impossible.");
      setRetour({ ton: "erreur", texte });
      toast.error(texte);
    } finally {
      setEnvoi(null);
    }
  };

  return (
    <div className="h-full overflow-y-auto px-4 py-5 pb-44 sm:px-8 sm:py-8 lg:px-12" data-testid="revue-publication-page">
      <header className="rise">
        <p className="font-code text-[10px] uppercase tracking-[0.3em] text-[#60A5FA]">Publication · interne au tenant</p>
        <h1 className="mt-1 font-display text-2xl font-black tracking-tight text-[#F2F6F8] sm:text-3xl">Revue de publication</h1>
        <p className="mt-2 max-w-2xl text-sm text-[#94A3B8]">
          Approuvez ou rejetez les partages de la carte de catalogue qui attendent une revue.
          Un partage approuvé devient lisible dans son périmètre ; un partage rejeté est révoqué et le Claim reste privé.
        </p>
      </header>

      <section className={`rise mt-6 max-w-2xl rounded-xl border ${BORDURE} bg-[#0F1D28] p-4`} style={{ animationDelay: "60ms" }} data-testid="revue-publication-selection">
        <label htmlFor="revue-publication-jumeau" className="block font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">
          Jumeau
        </label>
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <select
            id="revue-publication-jumeau"
            value={jid}
            onChange={(e) => choisirJumeau(e.target.value)}
            disabled={chargementJumeaux}
            data-testid="revue-publication-jumeau"
            className={`h-9 min-w-0 flex-1 rounded-md border ${BORDURE} bg-[#071019] px-2.5 text-xs text-[#F2F6F8] disabled:opacity-60 ${FOCUS}`}
          >
            <option value="">{chargementJumeaux ? "Chargement des jumeaux…" : "Choisir un jumeau…"}</option>
            {(jumeaux || []).map((j) => (
              <option key={j.id} value={j.id}>
                {j.nom}{typeof j.claims === "number" ? ` · ${j.claims} claims` : ""}{j.equipe ? ` · ${j.equipe}` : ""}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => setRelecture((n) => n + 1)}
            disabled={!jid || chargementFile}
            data-testid="revue-publication-rafraichir"
            className={`flex h-9 shrink-0 items-center gap-1.5 rounded-md border ${BORDURE} px-3 text-xs text-[#94A3B8] transition-colors hover:text-[#F2F6F8] disabled:opacity-50 ${FOCUS}`}
          >
            <ArrowsClockwise size={13} className={chargementFile ? "animate-spin" : ""} /> Recharger
          </button>
        </div>

        {erreurJumeaux && (
          <div role="alert" className="mt-3 rounded-lg border border-[#F87171]/30 bg-[#F87171]/[0.06] px-3 py-2" data-testid="revue-publication-erreur-jumeaux">
            <p className="text-xs text-[#F87171]">{erreurJumeaux}</p>
            <button type="button" onClick={() => setRelectureJumeaux((n) => n + 1)} className={`mt-2 rounded-md border ${BORDURE} px-2.5 py-1 text-[11px] text-[#94A3B8] hover:text-[#F2F6F8] ${FOCUS}`} data-testid="revue-publication-reessayer-jumeaux">
              Réessayer
            </button>
          </div>
        )}

        {!chargementJumeaux && !erreurJumeaux && jumeaux?.length === 0 && (
          <p className="mt-3 text-xs text-[#7C93A8]" data-testid="revue-publication-aucun-jumeau">
            Aucun jumeau n'est visible dans votre périmètre.
          </p>
        )}
      </section>

      {!jid && (
        <div className={`mt-6 rounded-xl border border-dashed ${BORDURE} px-5 py-8 text-sm text-[#7C93A8]`} data-testid="revue-publication-attente">
          Choisissez un jumeau pour ouvrir sa file de publication.
        </div>
      )}

      {jid && (
        <section className="mt-6" aria-labelledby="revue-publication-file-titre" data-testid="revue-publication-file">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div>
              <h2 id="revue-publication-file-titre" className="flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.25em] text-[#7C93A8]">
                <ShieldCheck size={14} className="text-[#F2B84B]" /> File de revue
              </h2>
              <p className="mt-1 text-xs text-[#94A3B8]" aria-live="polite">
                {erreurFile ? "File indisponible" : file ? `${file.length} partage${file.length > 1 ? "s" : ""} en attente` : "Lecture de la file…"}
                {jumeauChoisi && <span className="text-[#7C93A8]"> · {jumeauChoisi.nom}</span>}
                {chargementFile && file && <span className="text-[#7C93A8]"> · actualisation…</span>}
              </p>
            </div>
            <span className="rounded border border-[#F2B84B]/40 bg-[#F2B84B]/[0.06] px-2 py-1 font-code text-[9px] uppercase tracking-wider text-[#F2B84B]">
              Claims CONFIDENTIAL
            </span>
          </div>

          {retour && (
            <div
              role={retour.ton === "erreur" ? "alert" : "status"}
              data-testid="revue-publication-retour"
              className={`mt-3 rounded-lg border px-4 py-3 text-xs ${
                retour.ton === "erreur"
                  ? "border-[#F87171]/30 bg-[#F87171]/[0.06] text-[#F87171]"
                  : "border-[#34D399]/30 bg-[#34D399]/[0.06] text-[#34D399]"
              }`}
            >
              {retour.texte}
            </div>
          )}

          {erreurFile && (
            <div role="alert" className="mt-3 rounded-xl border border-[#F87171]/25 bg-[#F87171]/[0.05] px-5 py-4" data-testid="revue-publication-erreur-file">
              <p className="text-sm text-[#F87171]">{erreurFile}</p>
              <button type="button" onClick={() => setRelecture((n) => n + 1)} className={`mt-3 rounded-md border ${BORDURE} px-3 py-1.5 text-xs text-[#94A3B8] transition-colors hover:text-[#F2F6F8] ${FOCUS}`} data-testid="revue-publication-reessayer-file">
                Réessayer
              </button>
            </div>
          )}

          {chargementFile && !file && (
            <p className="mt-4 font-code text-[11px] text-[#7C93A8]" data-testid="revue-publication-chargement">Chargement de la file de revue…</p>
          )}

          {file && !chargementFile && file.length === 0 && (
            <div className={`mt-4 rounded-xl border ${BORDURE} bg-[#0F1D28] px-5 py-8 text-center`} data-testid="revue-publication-vide">
              <p className="text-sm text-[#D8E2EA]">Aucun partage en attente de revue pour ce jumeau.</p>
              <p className="mt-1 text-xs text-[#7C93A8]">Les partages déjà revus, révoqués ou non confidentiels ne figurent pas dans cette file.</p>
            </div>
          )}

          {file && file.length > 0 && (
            <ul className="mt-3 space-y-3" aria-label="Partages en attente de revue" data-testid="revue-publication-liste">
              {file.map((p) => {
                const [libelleConfidentialite, couleurConfidentialite] = CONFIDENTIALITES[p.confidentialite] || [p.confidentialite, "#7C93A8"];
                const enCours = envoi?.id === p.id;
                const parSoiMeme = Boolean(acteur) && p.granted_by === acteur;
                return (
                  <li key={p.id} className={`rise rounded-xl border ${BORDURE} bg-[#0F1D28] p-4`} data-testid={`partage-${p.id}`}>
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-code text-[10px] text-[#7C93A8]">Partage #{p.id} · Claim #{p.claim_id}</span>
                          <span
                            className="rounded border px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider"
                            style={{ color: couleurConfidentialite, borderColor: `${couleurConfidentialite}44`, backgroundColor: `${couleurConfidentialite}12` }}
                            data-testid={`confidentialite-${p.id}`}
                          >
                            {libelleConfidentialite}
                          </span>
                        </div>
                        <p className="mt-1.5 text-sm font-semibold leading-snug text-[#F2F6F8]">{p.objet}</p>
                        <p className="mt-1 break-all font-code text-[10px] text-[#7C93A8]" data-testid={`meta-${p.id}`}>
                          {SCOPES[p.scope_type] || p.scope_type} · {p.scope_id} · demandé par {p.granted_by || "—"}
                        </p>
                      </div>
                    </div>

                    <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-end">
                      <div className="min-w-0 flex-1">
                        <label htmlFor={`raison-${p.id}`} className="mb-1 block text-[10px] uppercase tracking-wider text-[#94A3B8]">
                          Raison (facultatif)
                        </label>
                        <input
                          id={`raison-${p.id}`}
                          value={raisons[p.id] || ""}
                          onChange={(e) => setRaisons((avant) => ({ ...avant, [p.id]: e.target.value }))}
                          maxLength={2000}
                          placeholder="Motif de la décision, utile surtout pour un rejet"
                          data-testid={`raison-${p.id}`}
                          className={`h-9 w-full rounded-md border ${BORDURE} bg-[#071019] px-3 text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] ${FOCUS}`}
                        />
                      </div>
                      <div className="flex shrink-0 gap-2">
                        <button
                          type="button"
                          disabled={Boolean(envoi) || parSoiMeme}
                          onClick={() => decider(p, "APPROVED")}
                          data-testid={`approuver-${p.id}`}
                          className={`flex h-9 items-center gap-1.5 rounded-md bg-[#60A5FA] px-3 text-xs font-semibold text-[#071019] transition-colors hover:bg-[#93C5FD] disabled:opacity-50 ${FOCUS}`}
                        >
                          <Check size={13} weight="bold" /> {enCours && envoi.decision === "APPROVED" ? "Approbation…" : "Approuver"}
                        </button>
                        <button
                          type="button"
                          disabled={Boolean(envoi) || parSoiMeme}
                          onClick={() => decider(p, "REJECTED")}
                          data-testid={`rejeter-${p.id}`}
                          className={`flex h-9 items-center gap-1.5 rounded-md border border-[#F87171]/40 px-3 text-xs text-[#F87171] transition-colors hover:bg-[#F87171]/10 disabled:opacity-50 ${FOCUS}`}
                        >
                          <X size={13} weight="bold" /> {enCours && envoi.decision === "REJECTED" ? "Rejet…" : "Rejeter"}
                        </button>
                      </div>
                    </div>

                    {parSoiMeme && (
                      <p className="mt-2 font-code text-[10px] text-[#F2B84B]" role="note" data-testid={`quatre-yeux-${p.id}`}>
                        Revue à quatre yeux : vous avez demandé ce partage. Un autre reviewer doit décider.
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
