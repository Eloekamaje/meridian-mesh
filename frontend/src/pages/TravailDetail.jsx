import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { DotsThree, SealCheck } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { usePerimetre } from "@/lib/perimetre";
import { TYPES_CASE } from "./Travaux";
import { numeroCase, SENSIBILITES, rel } from "@/components/case/utils";
import OngletTravail from "@/components/case/OngletTravail";
import DecisionPassation from "@/components/case/DecisionPassation";
import PartagerTravail from "@/components/case/PartagerTravail";
import { BoutonRetour } from "@/components/EntetePage";
import { useEcran } from "@/lib/ecran";

// « Nouveau travail » est cette même page : un travail qui n'est pas encore né (pas d'identifiant), avec un fil vide et la même
// saisie. Au premier envoi le travail naît et la conversation continue au même endroit — un seul chat pour tous les travaux.
function nouveauBrouillon() {
  return { id: null, brouillon: true, titre: "Nouveau travail", type: "demande", jumeaux: [], conversation: [] };
}

export default function TravailDetail() {
  const { cid } = useParams();
  const brouillon = cid === "nouveau";
  const location = useLocation();
  const navigate = useNavigate();
  const { version } = usePerimetre();
  const ecran = useEcran();
  const [cas, setCas] = useState(() => (brouillon ? nouveauBrouillon() : null));
  const [erreur, setErreur] = useState(null);
  const [menu, setMenu] = useState(false);
  // Fermé par défaut : il flotte par-dessus la conversation et recouvrirait le début des phrases de Flore ; l'icône de l'en-tête l'ouvre
  const [voletSourcesOuvert, setVoletSourcesOuvert] = useState(false);
  const [canvasOuvert, setCanvasOuvert] = useState(false);

  // Un travail en veille montre d'abord sa note de passation et ses actions : la fenêtre « Sources & Jumeaux » ne les recouvre pas
  const [passationOuverte, setPassationOuverte] = useState(false);
  const enVeille = !!cas?.veille;
  const peutDeposer = cas?.peut_deposer === true; // responsable ou participant : seul à pouvoir écrire
  const actionsMenu = peutDeposer && (cas?.a_revoir || cas?.peut_partager || (!enVeille && cas?.statut !== "clos"));
  useEffect(() => { if (enVeille) setVoletSourcesOuvert(false); }, [enVeille]);

  const participantsMessages = (cas?.conversation || []).reduce(
    (n, m) => n + (m.role === "flore" && Array.isArray(m.jumeaux_participants) ? m.jumeaux_participants.length : 0), 0);
  const nbSources = (cas?.jumeaux_participants || []).length + (cas?.pieces || []).length
    + participantsMessages + (cas?.livrables || []).length;
  const voletAutoOuvert = useRef(false);
  const casNe = !brouillon && !!cas?.id; // le travail existe : en-tête complet, volet
  useEffect(() => {
    // Jamais sur mobile : le volet y prend toute la largeur (inset-x-3) et recouvrirait entièrement
    // le message qui vient d'arriver — sur ce format, l'utilisateur l'ouvre lui-même s'il le souhaite.
    // Une seule ouverture automatique : si l'utilisateur referme le volet, il ne se rouvre pas à chaque réponse.
    if (!voletAutoOuvert.current && nbSources > 0 && !canvasOuvert && ecran !== "mobile") {
      voletAutoOuvert.current = true;
      setVoletSourcesOuvert(true);
    }
  }, [nbSources]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setErreur(null);
    voletAutoOuvert.current = false; // un autre travail peut avoir ses propres sources à révéler
    if (brouillon) return; // rien à charger : le travail n'est pas encore né
    // Quand le travail naît de la conversation, la page reste la même (state.continuite) : on ne la
    // vide pas, et on ne la recharge pas non plus — l'état local, que `envoyer()` vient de mettre à
    // jour avec la réponse de Flore encore en train de s'écrire, est déjà exact ; la recharger
    // écraserait cette réponse par sa version figée et couperait net son déroulé.
    const continuite = location.state?.continuite;
    if (!continuite) setCas(null);
    if (!continuite) {
      api.get(`/cases/${cid}`).then((r) => setCas(r.data)).catch((e) => setErreur(e.response?.data?.detail || "Travail introuvable"));
    }
  }, [cid, version]); // eslint-disable-line react-hooks/exhaustive-deps

  const maj = async (champs) => {
    try {
      const { data } = await api.patch(`/cases/${cid}`, champs);
      setCas((c) => ({ ...c, ...data }));
    } catch {
      toast.error("Mise à jour impossible");
    }
  };

  if (erreur) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4" data-testid="travail-erreur">
        <p className="text-sm text-[#F87171]">{erreur}</p>
        <button onClick={() => navigate("/travaux")} className="rounded-md border border-[rgba(148,163,184,0.16)] px-3 py-1.5 text-xs text-[#94A3B8] hover:text-[#F2F6F8]" data-testid="travail-erreur-retour">← Retour aux travaux</button>
      </div>
    );
  }
  if (!cas) return <div className="p-8 font-code text-[11px] text-[#7C93A8]" data-testid="travail-chargement">Chargement du travail…</div>;

  const t = TYPES_CASE[cas.type] || [cas.type, "#7C93A8"];
  const sens = SENSIBILITES[cas.sensibilite] || [cas.sensibilite || "interne", "#60A5FA"];
  const derniereEvolution = (cas.historique || []).slice(-1)[0];

  // L'entête, le bandeau « à revoir » et le voile de préparation vivent dans la même colonne que
  // le chat (passés en prop) : quand le Canvas s'ouvre, cette colonne rétrécit et eux avec elle,
  // pendant que le Canvas prend toute la hauteur à partir d'où l'entête était (Style ChatGPT Canvas).
  const entete = (
    <>
      <div className="shrink-0 border-b border-white/[0.08] bg-[#071019] px-6 py-2.5" data-testid="travail-entete">
        <div className="flex items-center justify-between gap-4">
          {/* Titre */}
          <div className="flex min-w-0 items-center gap-3">
            {/* On arrive d'une actualité : le retour vers elle est mis en évidence (le travail reste un travail comme les autres) */}
            {location.state?.retour
              ? <BoutonRetour accent label={location.state.retour.label} onClick={() => navigate(location.state.retour.to)} testid="travail-retour-origine" />
              : <BoutonRetour label="Travaux" onClick={() => navigate("/travaux")} testid="travail-retour-travaux" />}
            <h1 className="truncate font-display text-sm font-semibold tracking-tight text-[#F2F6F8]" data-testid="travail-titre">
              {cas.titre}
            </h1>

            {cas.a_revoir && (
              <span className="rounded border border-[#F87171]/40 bg-[#F87171]/[0.06] px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider text-[#F87171]" data-testid="travail-arevoir-entete">
                À revoir
              </span>
            )}
          </div>

          {/* Boutons d'action à droite : Partager, Menu ..., et Toggle Deux Traits (=) */}
          {casNe && <div className="flex shrink-0 items-center gap-2">
            <PartagerTravail cas={cas} onChange={setCas} />

            {actionsMenu && (
              <div className="relative">
                <button
                  onClick={() => setMenu(!menu)}
                  data-testid="travail-menu-btn"
                  className="flex h-7 w-7 items-center justify-center rounded-lg border border-white/[0.08] bg-white/[0.03] text-[#7C93A8] transition-colors hover:border-white/20 hover:text-white"
                >
                  <DotsThree size={16} weight="bold" />
                </button>
                {menu && (
                  <div className="glass absolute right-0 top-8 z-50 w-56 rounded-xl border border-white/10 bg-[#0C1724] p-1.5 shadow-2xl backdrop-blur-xl" data-testid="travail-menu">
                    {cas.a_revoir && peutDeposer && (
                      <button onClick={() => { setMenu(false); maj({ a_revoir: false }); }} data-testid="travail-marquer-revu-btn" className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-left text-[11px] text-[#F87171] hover:bg-white/[0.06]">
                        <SealCheck size={12} /> Marquer comme revu
                      </button>
                    )}
                    {!enVeille && cas.statut !== "clos" && peutDeposer && (
                      <button onClick={() => { setMenu(false); setPassationOuverte(true); }} data-testid="travail-consigner-decision-btn" className="w-full rounded px-2.5 py-1.5 text-left text-[11px] text-[#94A3B8] hover:bg-white/[0.06] hover:text-white">
                        Consigner une décision
                      </button>
                    )}
                    {cas.peut_partager && peutDeposer && (
                      <button
                        onClick={() => { setMenu(false); maj({ statut: cas.statut === "clos" ? "en_cours" : "clos" }); }}
                        data-testid="travail-clore-btn"
                        className="w-full rounded px-2.5 py-1.5 text-left text-[11px] text-[#94A3B8] hover:bg-white/[0.06] hover:text-white"
                      >
                        {cas.statut === "clos" ? "Rouvrir le travail" : "Clore le travail"}
                      </button>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Icône à deux traits horizontaux pour afficher/masquer le volet Résultats & Sources */}
            {(
              <button
                onClick={() => setVoletSourcesOuvert(!voletSourcesOuvert)}
                data-testid="btn-toggle-volet-sources"
                title={voletSourcesOuvert ? "Masquer Résultats & Sources" : "Afficher Résultats & Sources"}
                className={`flex h-7 w-7 items-center justify-center rounded-lg border transition-all ${
                  voletSourcesOuvert
                    ? "border-blue-400/60 bg-blue-500/20 text-blue-200"
                    : "border-white/[0.08] bg-white/[0.03] text-[#7C93A8] hover:border-white/20 hover:text-white"
                }`}
              >
                <svg width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                  <line x1="3" y1="6.5" x2="17" y2="6.5" />
                  <line x1="3" y1="13.5" x2="17" y2="13.5" />
                </svg>
              </button>
            )}
          </div>}
        </div>
      </div>

      {cas.a_revoir && (
        <div className="shrink-0 px-8 pt-4">
          <div className="mx-auto max-w-2xl">
          <div className="flex items-center justify-between gap-3 rounded-xl border border-[#F87171]/30 bg-[#F87171]/[0.04] px-4 py-3" data-testid="travail-arevoir-banner">
            <p className="text-xs text-[#F87171]">
              <span className="font-semibold uppercase tracking-wider">À revoir</span> — une connaissance du Mesh liée à ce travail a changé ; les conclusions peuvent être remises en cause.
            </p>
            {peutDeposer && (
              <button onClick={() => maj({ a_revoir: false })} data-testid="travail-marquer-revu-banner-btn" className="shrink-0 rounded-md border border-[#F87171]/40 px-2.5 py-1.5 text-[11px] font-semibold text-[#F87171] transition-colors hover:bg-[#F87171]/10">
                Marquer comme revu
              </button>
            )}
          </div>
        </div>
        </div>
      )}
    </>
  );

  return (
    <div className="flex h-full" data-testid="travail-detail">
      <OngletTravail
        cas={cas}
        setCas={setCas}
        voletSourcesOuvert={voletSourcesOuvert && casNe}
        setVoletSourcesOuvert={setVoletSourcesOuvert}
        canvasOuvert={canvasOuvert}
        setCanvasOuvert={setCanvasOuvert}
        onConsignerDecision={casNe && peutDeposer ? () => setPassationOuverte(true) : undefined}
        entete={entete}
      />
      {passationOuverte && <DecisionPassation cas={cas} onFermer={() => setPassationOuverte(false)} onEnregistree={(data) => { setCas(data); setPassationOuverte(false); }} />}
    </div>
  );
}
