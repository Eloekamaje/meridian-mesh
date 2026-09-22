import { useEffect, useRef, useState } from "react";
import { 
  Sparkle, 
  User, 
  FileText, 
  Globe, 
  Database, 
  Broadcast, 
  CheckCircle, 
  ArrowUp, 
  Plus, 
  CaretDown, 
  CaretRight, 
  Microphone, 
  ArrowDown, 
  Coins, 
  Clock, 
  ShieldCheck,
  Buildings,
  Copy,
  ArrowsClockwise,
  DotsThree
} from "@phosphor-icons/react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import api from "@/lib/api";
import { usePerimetre } from "@/lib/perimetre";
import { useContexte } from "@/lib/contexte";
import { CREATION_TRAVAIL_ACTIVE, FLORE_REPONSE_EN_CONSTRUCTION, PROPOSITION_DEMO } from "@/lib/messagesFlore";
import FloreActivite, { delaiMin, activiteTerminee } from "@/components/FloreActivite";
import LigneActiviteFlore from "@/components/LigneActiviteFlore";
import IndicateurClic from "@/components/IndicateurClic";
import { usePilotage } from "@/lib/pilotage";
import { useEcran } from "@/lib/ecran";
import { rel } from "./utils";
import CanvasDocument from "./CanvasDocument";
import { BandeauVeille, EvenementVeille, RepriseVeille, PreuvesMessage } from "./VeilleTravail";

// Dictionnaire des Jumeaux participants du SI pour CASE-101
export const DICT_JUMEAUX_PARTICIPANTS = {
  "demo-polaris-app-portail": {
    app_id: "app-portail",
    nom: "Portail client",
    domaine: "Client",
    domaineCouleur: "#60A5FA",
    type: "Parcours Web Client",
    statut: "actif",
    participation: "Fournit les données de parcours client et l'estimation de volumétrie pour l'auto-suivi des demandes.",
  },
  "demo-polaris-app-conseiller": {
    app_id: "app-conseiller",
    nom: "Poste conseiller",
    domaine: "Distribution",
    domaineCouleur: "#FB7185",
    type: "Interface succursales",
    statut: "actif",
    participation: "Fournit le diagnostic de charge de traitement des conseillers en succursale.",
  },
  "demo-polaris-app-dossiers": {
    app_id: "app-dossiers",
    nom: "Gestion des dossiers",
    domaine: "Opérations",
    domaineCouleur: "#A3E635",
    type: "Socle métier central",
    statut: "80% existant en production",
    participation: "Détient la machine à états officielle et le cycle de vie complet de chaque dossier.",
  },
  "demo-polaris-app-statuts": {
    app_id: "app-statuts",
    nom: "Diffusion des statuts",
    domaine: "Opérations",
    domaineCouleur: "#A3E635",
    type: "Exposition temps réel",
    statut: "actif en production",
    participation: "Expose les flux d'événements Kafka pour diffuser les changements d'état en direct.",
  },
};

// Pipeline Architectural Horizontal (Fidèle au diagramme horizontal de la capture)
export function PipelineArchitecture() {
  return (
    <div className="my-5 overflow-x-auto py-2" data-testid="pipeline-architecture-convergence">
      <div className="flex items-center gap-2 min-w-max">
        {/* Nœud 1 : Portail client */}
        <div className="rounded-xl border border-blue-400/30 bg-blue-500/10 px-3.5 py-2 text-center shadow-sm">
          <div className="text-[9px] font-code font-semibold uppercase tracking-wider text-blue-300">Canal Client</div>
          <div className="text-xs font-bold text-white mt-0.5">Portail client Web</div>
          <div className="text-[10px] text-blue-200/70 font-code">app-portail</div>
        </div>

        <span className="text-blue-400/70 font-code text-xs px-1">──▶</span>

        {/* Nœud 2 : Diffusion des statuts (Kafka) */}
        <div className="rounded-xl border border-blue-400/40 bg-blue-500/15 px-3.5 py-2 text-center shadow-sm ring-1 ring-blue-400/20">
          <div className="text-[9px] font-code font-semibold uppercase tracking-wider text-blue-300">Hub Événements Temps Réel</div>
          <div className="text-xs font-bold text-white mt-0.5">Diffusion des statuts</div>
          <div className="text-[10px] text-blue-200/70 font-code">app-statuts (Kafka)</div>
        </div>

        <span className="text-emerald-400/70 font-code text-xs px-1">◀──</span>

        {/* Nœud 3 : Socle Existant (80%) */}
        <div className="rounded-xl border border-emerald-400/50 bg-emerald-500/20 px-4 py-2 text-center shadow-md ring-1 ring-emerald-400/30">
          <div className="text-[9px] font-code font-semibold uppercase tracking-wider text-emerald-300">Socle Existant (80%)</div>
          <div className="text-xs font-bold text-emerald-100 mt-0.5">Gestion des dossiers</div>
          <div className="text-[10px] text-emerald-300/80 font-code">app-dossiers (Production)</div>
        </div>

        <span className="text-rose-400/70 font-code text-xs px-1">◀──</span>

        {/* Nœud 4 : Poste conseiller */}
        <div className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-3.5 py-2 text-center shadow-sm">
          <div className="text-[9px] font-code font-semibold uppercase tracking-wider text-rose-300">Canal Succursale</div>
          <div className="text-xs font-bold text-white mt-0.5">Poste conseiller</div>
          <div className="text-[10px] text-rose-200/70 font-code">app-conseiller</div>
        </div>
      </div>
    </div>
  );
}

// Réponses déjà déroulées : un message ne se rejoue jamais (remontage de la page, retour au travail)
const REPONSES_JOUEES = new Set();

// Déroulé progressif de la réponse de Flore (démonstration : message publié en direct). Même cadence
// que le moteur (3 caractères / 18 ms) ; gelé pendant la pause ; cartes et document après le texte.
// `animer` distingue « en train de s'écrire » (curseur visible) d'une réponse déjà ancienne, révélée d'un bloc.
function useDeroule(message, pilote) {
  const total = (message.texte || "").length;
  const cle = message.quand;
  const reduit = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const animer = !!pilote && !!message.anime && !REPONSES_JOUEES.has(cle) && !reduit;
  const [n, setN] = useState(animer ? 0 : total);
  const enPause = !!pilote?.enPause;
  useEffect(() => {
    if (n >= total) {
      REPONSES_JOUEES.add(cle);
      return undefined;
    }
    if (!animer || enPause) return undefined;
    const t = setTimeout(() => setN((x) => Math.min(total, x + 3)), 18);
    return () => clearTimeout(t);
  }, [n, total, animer, enPause, cle]);
  return { visible: (message.texte || "").slice(0, n), fini: n >= total };
}

// Rendu formaté, fluide et aéré du texte (Style ChatGPT / Claude)
export function CorpsMessageFlore({ message, onOuvrirCanvas, canvasActif, children }) {
  const pilote = usePilotage();
  const texte = message.texte || "";
  const { visible, fini } = useDeroule(message, pilote);
  const lignes = visible.split("\n");

  // Détecte si le message présente l'architecture ou la convergence pour intégrer le pipeline
  const montrePipeline = 
    texte.includes("app-dossiers") || 
    texte.includes("Diffusion des statuts") || 
    texte.includes("80 %") ||
    texte.includes("triple redondance") ||
    message.comportement === "arbitrer";

  return (
    <div className="space-y-3.5 text-[15px] leading-relaxed text-[#DCE6EE]">
      {lignes.map((ligne, idx) => {
        const trimmed = ligne.trim();
        if (!trimmed) return <div key={idx} className="h-1.5" />;

        // Sous-titre Markdown ###
        if (trimmed.startsWith("### ")) {
          return (
            <h3 key={idx} className="font-display text-base font-bold text-white pt-2">
              {trimmed.replace("### ", "")}
            </h3>
          );
        }

        // Sous-titre Markdown ##
        if (trimmed.startsWith("## ")) {
          return (
            <h2 key={idx} className="font-display text-lg font-bold text-white pt-3">
              {trimmed.replace("## ", "")}
            </h2>
          );
        }

        // Puce de liste
        if (trimmed.startsWith("* ") || trimmed.startsWith("- ") || trimmed.startsWith("• ") || trimmed.startsWith("— ")) {
          const contenu = trimmed.replace(/^[\*\-•—]\s*/, "");
          return (
            <div key={idx} className="flex items-start gap-2 pl-2 text-sm text-[#CBD5E1]">
              <span className="text-[#60A5FA] mt-1 text-xs">•</span>
              <span dangerouslySetInnerHTML={{ __html: formaterGrasCode(contenu) }} />
            </div>
          );
        }

        // Citation / callout >
        if (trimmed.startsWith("> ")) {
          return (
            <div key={idx} className="border-l-2 border-[#60A5FA]/60 pl-3 py-1 my-2 text-sm italic text-blue-200/90 bg-blue-500/[0.04] rounded-r-md">
              <span dangerouslySetInnerHTML={{ __html: formaterGrasCode(trimmed.replace("> ", "")) }} />
            </div>
          );
        }

        // Paragraphe classique
        return (
          <p key={idx} dangerouslySetInnerHTML={{ __html: formaterGrasCode(ligne) }} />
        );
      })}

      {/* Curseur clignotant : Flore est encore en train d'écrire (sinon, rien ne le distingue d'une lecture) */}
      {!fini && <span className="curseur-teletype -mt-2 inline-block">▍</span>}

      {/* Pipeline architectural horizontal */}
      {fini && montrePipeline && <PipelineArchitecture />}

      {/* KPIs épurés et légers (Style stat strip moderne) */}
      {fini && message.kpis && (
        <div className="my-4 grid grid-cols-1 gap-2.5 sm:grid-cols-3">
          <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/[0.06] p-3">
            <div className="flex items-center justify-between text-emerald-400">
              <span className="font-code text-[10px] uppercase tracking-wider">Gain net</span>
              <Coins size={14} />
            </div>
            <div className="mt-0.5 font-display text-xl font-bold text-emerald-300">
              {message.kpis.gain}
            </div>
            <p className="mt-0.5 font-code text-[11px] text-emerald-200/80">
              {message.kpis.gainSousTitre}
            </p>
          </div>

          <div className="rounded-xl border border-blue-500/20 bg-blue-500/[0.06] p-3">
            <div className="flex items-center justify-between text-blue-400">
              <span className="font-code text-[10px] uppercase tracking-wider">Délai cible</span>
              <Clock size={14} />
            </div>
            <div className="mt-0.5 font-display text-xl font-bold text-blue-300">
              {message.kpis.delai}
            </div>
            <p className="mt-0.5 font-code text-[11px] text-blue-200/80">
              {message.kpis.delaiSousTitre}
            </p>
          </div>

          <div className="rounded-xl border border-[#60A5FA]/20 bg-[#60A5FA]/[0.06] p-3">
            <div className="flex items-center justify-between text-[#BFDBFE]">
              <span className="font-code text-[10px] uppercase tracking-wider">Socle existant</span>
              <Database size={14} />
            </div>
            <div className="mt-0.5 font-display text-xl font-bold text-[#DBEAFE]">
              {message.kpis.socle}
            </div>
            <p className="mt-0.5 font-code text-[11px] text-[#BFDBFE]/80">
              {message.kpis.socleSousTitre}
            </p>
          </div>
        </div>
      )}

      {/* Tableau comparatif épuré */}
      {fini && message.tableauComparatif && (
        <div className="my-4 overflow-x-auto rounded-xl border border-white/[0.08] bg-[#0A131C]">
          <table className="w-full min-w-[28rem] text-left text-xs">
            <thead>
              <tr className="border-b border-white/[0.08] font-code text-[10px] uppercase tracking-wider text-[#7C93A8]">
                <th className="py-2.5 pl-4 pr-2">Critère</th>
                <th className="px-2 py-2.5 text-rose-300">Trajectoire Silos</th>
                <th className="py-2.5 pl-2 pr-4 text-emerald-300">Socle Mutualisé (CASE-101)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.05]">
              {message.tableauComparatif.map((row, rk) => (
                <tr key={rk}>
                  <td className="py-2 pl-4 pr-2 font-medium text-[#CBD5E1]">{row.critere}</td>
                  <td className="px-2 py-2 text-rose-300">{row.silos}</td>
                  <td className="py-2 pl-2 pr-4 font-code font-semibold text-emerald-300">{row.socle}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Bouton léger pour ouvrir le Document dans Canvas si disponible */}
      {fini && (message.documentCanvas || texte.includes("CASE_101_ARBITRAGE_CONVERGENCE.md")) && (
        <div className="pt-2">
          <button
            onClick={onOuvrirCanvas}
            className="inline-flex items-center gap-2 rounded-xl border border-blue-400/30 bg-blue-500/10 px-3.5 py-1.5 font-code text-xs text-blue-200 transition-all hover:bg-blue-500/20 hover:border-blue-400/50"
            data-testid="btn-ouvrir-canvas-inline"
          >
            <FileText size={14} className="text-blue-400" />
            <span>CASE_101_ARBITRAGE_CONVERGENCE.md</span>
            <span className="text-blue-400 font-semibold">{canvasActif ? "(Canvas ouvert ↗)" : "(Ouvrir dans le Canvas ↗)"}</span>
          </button>
        </div>
      )}

      {/* Décisions, suggestions, actions… : n'apparaissent qu'une fois la réponse complète — ni
          pendant son déroulé (`fini`), ni sur une simple annonce (« Je vais… ») suivie d'un
          traitement encore à venir (`termine`, absent hors démo : toujours vrai dans ce cas) */}
      {fini && message.termine !== false && children}
    </div>
  );
}

// Fonction utilitaire pour formater gras et code inline
function formaterGrasCode(txt) {
  if (!txt) return "";
  let res = txt
    .replace(/\*\*(.*?)\*\*/g, "<strong class='font-semibold text-white'>$1</strong>")
    .replace(/`([^`]+)`/g, "<code class='font-code text-xs text-blue-300 bg-blue-500/10 px-1 py-0.5 rounded'>$1</code>");
  return res;
}

export default function OngletTravail({ 
  cas, 
  setCas, 
  voletSourcesOuvert: voletSourcesOuvertProp,
  setVoletSourcesOuvert: setVoletSourcesOuvertProp,
  canvasOuvert: canvasOuvertProp, 
  setCanvasOuvert: setCanvasOuvertProp,
  onBasculerCanvas,
  onOuvrirPreuve,
  onConsignerDecision,
}) {
  const pilote = usePilotage();
  const navigate = useNavigate();
  const ecran = useEcran();
  const { info } = usePerimetre();
  const { selection } = useContexte();
  // Travail pas encore né (« Nouveau travail ») : même conversation, sans identifiant
  const brouillon = cas?.id == null;
  // Le dossier CASE_101 et ses deux preuves sont le contenu du scénario de démonstration : ils n'appartiennent qu'au
  // travail de démonstration (né pendant la démo, ou le travail de démonstration du jeu de données), jamais aux travaux réels
  const contenuScenario = pilote ? !!pilote.documentGenere : cas?.id === "demo-polaris-work-g";
  const [nouveauMsg, setNouveauMsg] = useState("");
  const [envoiMsg, setEnvoiMsg] = useState(false);
  // Rubriques du volet (Résultats, Sources & Jumeaux) : chacune se plie et se déplie
  const [pliees, setPliees] = useState({});
  const basculerRubrique = (cle) => setPliees((p) => ({ ...p, [cle]: !p[cle] }));
  const [jumeauInspecte, setJumeauInspecte] = useState(null);
  const [preuveInspectee, setPreuveInspectee] = useState(null);
  const [estEnBas, setEstEnBas] = useState(true);

  // Gestion synchronisée ou locale des volets
  const [voletSourcesLocal, setVoletSourcesLocal] = useState(!pilote);
  const [canvasLocal, setCanvasLocal] = useState(false);

  const voletSourcesOuvert = voletSourcesOuvertProp !== undefined ? voletSourcesOuvertProp : voletSourcesLocal;
  const setVoletSourcesOuvert = setVoletSourcesOuvertProp || setVoletSourcesLocal;

  const canvasActif = canvasOuvertProp !== undefined ? canvasOuvertProp : canvasLocal;
  const setCanvasActif = setCanvasOuvertProp || setCanvasLocal;
  const toggleCanvas = onBasculerCanvas || (() => setCanvasActif((v) => !v));

  const defilementRef = useRef(null);
  const finFilRef = useRef(null);
  const coupureRef = useRef(null);
  const taRef = useRef(null);
  // Champ de saisie qui grandit avec son contenu (comme ChatGPT/Claude) — sinon les lignes au-delà
  // de la première restent invisibles (la hauteur ne bouge jamais toute seule). Rejoue aussi
  // pendant la frappe simulée de la démo (le texte change sans passer par onChange).
  const texteSaisie = pilote ? pilote.saisie?.texte || "" : nouveauMsg;
  useEffect(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [texteSaisie]);

  const messages = cas.conversation || [];
  const coupure = cas.derniere_visite;
  // Le « nouveau » est ce que les AUTRES ont écrit : vos propres messages ne comptent jamais
  const idxCoupure = coupure ? messages.findIndex((m) => m.quand && m.quand > coupure && m.role !== "utilisateur") : -1;

  // Résolution des jumeaux participants
  const jumeauxParticipants = (cas.jumeaux_participants && cas.jumeaux_participants.length > 0)
    ? cas.jumeaux_participants
    : (cas.jumeaux || []).map((id) => {
        const ref = DICT_JUMEAUX_PARTICIPANTS[id];
        if (ref) return { id, ...ref };
        return {
          id,
          app_id: id.replace("demo-polaris-", ""),
          nom: id.replace("demo-polaris-", "").replace("app-", ""),
          domaine: "SI",
          domaineCouleur: "#60A5FA",
          statut: "actif",
          participation: "Jumeau numérique participant à la mission.",
        };
      });

  // Positionnement du fil : à l'ouverture, sur le repère « nouveau depuis votre dernière visite » (sinon en bas) ; ensuite, en bas à chaque
  // nouveau message. On compare à l'état précédent plutôt que de compter les appels : React (mode développement) exécute chaque effet deux
  // fois, et le second appel ne doit pas passer pour un nouveau message.
  const etatPrecedent = useRef(null);
  useEffect(() => {
    const etat = `${messages.length}|${envoiMsg}|${pilote?.activite?.ops?.length}`;
    if (etatPrecedent.current === null) {
      etatPrecedent.current = etat;
      if (idxCoupure > 0) coupureRef.current?.scrollIntoView({ block: "center" });
      else finFilRef.current?.scrollIntoView({ block: "end" });
      return;
    }
    if (etatPrecedent.current === etat) return;
    etatPrecedent.current = etat;
    finFilRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, envoiMsg, pilote?.activite?.ops?.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const verifierPositionScroll = () => {
    if (!defilementRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = defilementRef.current;
    setEstEnBas(scrollHeight - scrollTop - clientHeight < 80);
  };

  const allerEnBas = () => {
    finFilRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const envoyer = async (e, texteDirect) => {
    e?.preventDefault?.();
    const q = (texteDirect ?? nouveauMsg).trim();
    if (!q || envoiMsg || pilote) return;
    setEnvoiMsg(true);
    setNouveauMsg("");
    const maintenant = new Date().toISOString();
    // Le message de l'utilisateur apparaît tout de suite ; la réponse de Flore le rejoint quand elle arrive
    const avant = cas.conversation || [];
    const monMessage = { role: "utilisateur", texte: q, quand: maintenant };
    setCas((c) => ({ ...c, conversation: [...avant, monMessage] }));
    // « Nouveau travail » hors démonstration : la création réelle n'existe pas encore — Flore l'annonce, aucun appel réseau
    if (brouillon && !CREATION_TRAVAIL_ACTIVE) {
      await delaiMin(Promise.resolve());
      setCas((c) => ({
        ...c,
        conversation: [...avant, monMessage, { role: "flore", comportement: "expliquer", texte: FLORE_REPONSE_EN_CONSTRUCTION, proposition: PROPOSITION_DEMO, quand: maintenant }],
      }));
      setEnvoiMsg(false);
      return;
    }
    try {
      // La première question fait naître le travail ; la conversation continue ensuite dans la même page
      let idTravail = cas.id;
      let travailNe = null;
      if (brouillon) {
        const { data: c } = await api.post("/cases", {
          titre: q.length > 90 ? `${q.slice(0, 87)}…` : q, type: "demande", objectif: q, jumeaux: selection, espace: info?.espace?.id,
        });
        idTravail = c.id;
        travailNe = c;
      }
      const { data } = await delaiMin(api.post(`/cases/${idTravail}/messages`, { texte: q }));
      if (travailNe) {
        setCas({ ...travailNe, conversation: [data.utilisateur, { ...data.flore, _activite: activiteTerminee("travail") }] });
        navigate(`/travaux/${idTravail}`, { replace: true, state: { continuite: true } });
        if (data.flore?.documentCanvas) setCanvasActif(true);
        return;
      }
      setCas((c) => ({
        ...c,
        conversation: [...avant, data.utilisateur, { ...data.flore, _activite: activiteTerminee("travail") }],
      }));
      if (data.flore?.documentCanvas && !canvasActif) {
        setCanvasActif(true);
      }
    } catch {
      setCas((c) => ({ ...c, conversation: avant }));
      setNouveauMsg(q); // le texte n'est pas perdu
      toast.error(brouillon ? "Création du travail impossible" : "Message impossible");
    } finally {
      setEnvoiMsg(false);
    }
  };

  // Une décision attendue par la situation : le choix est appliqué côté serveur (statut de la situation, relation confirmée…) et écrit dans le fil
  const trancher = async (texte) => {
    setEnvoiMsg(true);
    try {
      const { data } = await api.post(`/cases/${cas.id}/decision-attendue`, { texte });
      setCas(data);
      if (data.lien) navigate(data.lien);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Décision impossible");
    } finally {
      setEnvoiMsg(false);
    }
  };

  // Réponse à la question de revue : votre choix devient votre message, Flore répond (tout est dans le fil)
  const repondreRevue = async (action) => {
    setEnvoiMsg(true);
    try {
      const { data } = await api.post(`/cases/${cas.id}/veille/decision`, { action });
      setCas(data);
    } catch {
      toast.error("Action impossible");
    } finally {
      setEnvoiMsg(false);
    }
  };

  return (
    <div className="relative flex h-full w-full overflow-hidden bg-[#071019] text-[#DCE6EE]" data-testid="onglet-travail">
      
      {/* ========================================================================= */}
      {/* ZONE CENTRALE : CONVERSATION FLUIDE, AÉRÉE, SANS CARDS LOURDES            */}
      {/* ========================================================================= */}
      <div className={`relative flex h-full w-full flex-col overflow-hidden transition-all duration-300 ${canvasActif ? "lg:w-auto lg:flex-[55]" : ""}`}>
        
        {/* ========================================================================= */}
        {/* VOLET FLOTTANT : RÉSULTATS & SOURCES JUMEAUX (Style ChatGPT Canvas)        */}
        {/* Toggable à volonté via l'icône à deux traits horizontaux                 */}
        {/* ========================================================================= */}
        {voletSourcesOuvert && (
          <div 
            className="absolute inset-x-3 top-3 z-40 max-h-[75%] overflow-y-auto rounded-2xl border border-white/10 bg-[#0C1724]/95 p-4 sm:inset-x-auto sm:right-6 sm:w-80 shadow-2xl backdrop-blur-xl animate-in fade-in zoom-in-95 duration-200"
            data-testid="volet-flottant-sources-resultats"
          >
            {/* Section RÉSULTATS : en démonstration, le dossier n'apparaît qu'une fois généré par Flore */}
            {contenuScenario && (
              <>
            {/* Section RÉSULTATS — en-tête cliquable : plie / déplie la rubrique */}
            <div className={`flex items-center justify-between text-xs font-semibold text-white ${pliees.resultats ? "" : "mb-2.5"}`}>
              <button
                type="button"
                onClick={() => basculerRubrique("resultats")}
                aria-expanded={!pliees.resultats}
                data-testid="rubrique-resultats-bascule"
                className="flex min-h-[28px] flex-1 items-center gap-1.5 text-left transition-colors hover:text-blue-200"
              >
                <CaretDown size={11} className={`shrink-0 text-[#7C93A8] transition-transform duration-200 ${pliees.resultats ? "-rotate-90" : ""}`} />
                <FileText size={14} className="text-blue-400" />
                <span>Résultats</span>
              </button>
              <button
                onClick={() => setCanvasActif(true)}
                className="text-[#7C93A8] hover:text-white transition-colors"
                title="Ouvrir le document dans le Canvas"
                data-testid="btn-plus-resultats"
              >
                <Plus size={14} />
              </button>
            </div>

            {!pliees.resultats && (
              <>
            {/* Item Document CASE-101 */}
            <div 
              onClick={() => setCanvasActif(!canvasActif)}
              className={`group cursor-pointer rounded-xl border p-2.5 transition-all ${
                canvasActif
                  ? "border-blue-400/60 bg-blue-500/20"
                  : "border-white/[0.08] bg-white/[0.03] hover:border-blue-400/40 hover:bg-white/[0.06]"
              }`}
              data-testid="item-resultat-document"
            >
              <div className="flex items-start gap-2.5">
                <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-blue-500/20 text-blue-300">
                  <FileText size={16} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-code text-xs font-semibold text-blue-200">
                    CASE_101_ARBITRAGE_CONVERGENCE.md
                  </div>
                  <div className="text-[11px] text-[#7C93A8]">
                    Recommandation officielle · 5 sections
                  </div>
                </div>
                <span className="shrink-0 text-[11px] font-code text-blue-400">
                  {canvasActif ? "Ouvert ↗" : "+ Ouvrir"}
                </span>
              </div>
            </div>
              </>
            )}

            {/* Séparateur fin */}
            <div className="my-3.5 border-t border-white/[0.08]" />
              </>
            )}

            {/* Section SOURCES — en-tête cliquable : plie / déplie la rubrique */}
            <div className={`flex items-center justify-between text-xs font-semibold text-white ${pliees.sources ? "" : "mb-2.5"}`}>
              <button
                type="button"
                onClick={() => basculerRubrique("sources")}
                aria-expanded={!pliees.sources}
                data-testid="rubrique-sources-bascule"
                className="flex min-h-[28px] flex-1 items-center gap-1.5 text-left transition-colors hover:text-[#BFDBFE]"
              >
                <CaretDown size={11} className={`shrink-0 text-[#7C93A8] transition-transform duration-200 ${pliees.sources ? "-rotate-90" : ""}`} />
                <Globe size={14} className="text-[#60A5FA]" />
                <span>Sources & Jumeaux</span>
                <span className="rounded-full bg-white/[0.08] px-1.5 py-0.2 font-code text-[10px] text-[#7C93A8]">{jumeauxParticipants.length + (contenuScenario ? 2 : 0)}</span>
              </button>
              <button 
                onClick={() => setVoletSourcesOuvert(false)}
                className="text-[#7C93A8] hover:text-white transition-colors"
                title="Masquer le volet"
              >
                ✕
              </button>
            </div>

            {!pliees.sources && (
              <>
            <div className="space-y-1.5 max-h-64 overflow-y-auto pr-1">
              {/* 4 Jumeaux Participants */}
              {jumeauxParticipants.map((j) => (
                <div 
                  key={j.app_id || j.id}
                  onClick={() => setJumeauInspecte(jumeauInspecte?.app_id === j.app_id ? null : j)}
                  className={`flex items-center justify-between rounded-lg px-2.5 py-1.5 text-xs transition-colors cursor-pointer border ${
                    jumeauInspecte?.app_id === j.app_id
                      ? "border-blue-400 bg-blue-500/20 text-white"
                      : "border-transparent bg-white/[0.03] text-[#CBD5E1] hover:bg-white/[0.07] hover:text-white"
                  }`}
                  data-testid={`source-jumeau-${j.app_id}`}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: j.domaineCouleur || "#60A5FA" }} />
                    <span className="truncate">{j.nom}</span>
                  </div>
                  <span className="font-code text-[10px] text-[#7C93A8] shrink-0">
                    {j.app_id}
                    {j.statut?.includes("80%") && <span className="ml-1 text-emerald-400 font-bold">(80%)</span>}
                  </span>
                </div>
              ))}

              {contenuScenario && (
              <>
              <div 
                onClick={() => setPreuveInspectee(preuveInspectee === "ev-g-initiatives" ? null : "ev-g-initiatives")}
                className={`flex items-center justify-between rounded-lg px-2.5 py-1.5 text-xs transition-colors cursor-pointer border ${
                  preuveInspectee === "ev-g-initiatives"
                    ? "border-emerald-400 bg-emerald-500/20 text-white"
                    : "border-transparent bg-white/[0.03] text-[#CBD5E1] hover:bg-white/[0.07] hover:text-white"
                }`}
                data-testid="source-preuve-initiatives"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <FileText size={13} className="text-[#60A5FA] shrink-0" />
                  <span className="truncate">Fiches initiatives (6,6 M€)</span>
                </div>
                <span className="font-code text-[10px] text-[#7C93A8] shrink-0">ev-g-initiatives</span>
              </div>

              <div 
                onClick={() => setPreuveInspectee(preuveInspectee === "ev-g-couverture" ? null : "ev-g-couverture")}
                className={`flex items-center justify-between rounded-lg px-2.5 py-1.5 text-xs transition-colors cursor-pointer border ${
                  preuveInspectee === "ev-g-couverture"
                    ? "border-emerald-400 bg-emerald-500/20 text-white"
                    : "border-transparent bg-white/[0.03] text-[#CBD5E1] hover:bg-white/[0.07] hover:text-white"
                }`}
                data-testid="source-preuve-couverture"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <FileText size={13} className="text-emerald-400 shrink-0" />
                  <span className="truncate">Matrice audit SI (80%)</span>
                </div>
                <span className="font-code text-[10px] text-[#7C93A8] shrink-0">ev-g-couverture</span>
              </div>
              </>
              )}
            </div>

            {/* Tiroir d'inspection si un élément est cliqué */}
            {jumeauInspecte && (
              <div className="mt-3 rounded-xl border border-blue-400/30 bg-[#07131F] p-2.5 text-xs animate-in fade-in">
                <div className="flex items-center justify-between font-semibold text-white">
                  <span>{jumeauInspecte.nom} <span className="font-code text-[10px] text-blue-300">[{jumeauInspecte.app_id}]</span></span>
                  <button onClick={() => setJumeauInspecte(null)} className="text-[#64748B] hover:text-white">✕</button>
                </div>
                <p className="mt-1 text-[11px] leading-relaxed text-slate-300">
                  {jumeauInspecte.participation}
                </p>
              </div>
            )}

            {preuveInspectee && (
              <div className="mt-3 rounded-xl border border-emerald-400/30 bg-[#06181B] p-2.5 text-xs animate-in fade-in">
                <div className="flex items-center justify-between font-semibold text-emerald-200">
                  <span>{preuveInspectee === "ev-g-initiatives" ? "Demandes 6,6 M€" : "Audit technique SI (80%)"}</span>
                  <button onClick={() => setPreuveInspectee(null)} className="text-[#64748B] hover:text-white">✕</button>
                </div>
                <p className="mt-1 text-[11px] leading-relaxed text-slate-300">
                  {preuveInspectee === "ev-g-initiatives"
                    ? "3 initiatives en silos (2,0 M€ + 2,0 M€ + 2,6 M€) demandant la même information d'état."
                    : "80% de la logique et machine à états déjà dans app-dossiers. Économie nette de 5,1 M€ en mutualisant."}
                </p>
              </div>
            )}
              </>
            )}
          </div>
        )}
        
        {/* Fil de discussion principal */}
        {cas.veille && <div className="shrink-0 px-6 pt-3 sm:px-12"><BandeauVeille cas={cas} /></div>}
        <div 
          ref={defilementRef}
          onScroll={verifierPositionScroll}
          className="flex-1 overflow-y-auto px-6 sm:px-12"
        >
          <div className="mx-auto max-w-3xl space-y-7 py-8" data-testid="case-conversation">
            {messages.map((m, i) => (
              <div key={i} className="space-y-3">
                {/* Reprise de visite */}
                {i === idxCoupure && idxCoupure > 0 && (
                  <div ref={coupureRef} className="my-4 flex items-center gap-3" data-testid="reprise-coupure">
                    <span className="h-px flex-1 bg-[#60A5FA]/25" />
                    <span className="font-code text-[9px] uppercase tracking-[0.2em] text-[#60A5FA]">
                      Nouveau depuis votre dernière visite
                    </span>
                    <span className="h-px flex-1 bg-[#60A5FA]/25" />
                  </div>
                )}
                {/* Travail en veille : Flore accueille avant les faits (ce qui a changé depuis la dernière visite) */}
                {i === idxCoupure && idxCoupure > 0 && cas.veille && <RepriseVeille messages={messages.slice(i)} depuis={coupure} />}

                {/* Message Utilisateur (sobre, simple bulle élégante à droite) */}
                {m.role === "evenement" ? (
                  <EvenementVeille m={m} index={i} nouveau={!!coupure && m.quand > coupure} />
                ) : m.role === "utilisateur" ? (
                  <div className="flex flex-col items-end gap-1.5 animate-in fade-in duration-200" data-testid={`case-msg-${i}`}>
                    {/* Micro-actions discrètes au-dessus de la bulle (Style ChatGPT) */}
                    <div className="flex items-center gap-1.5 text-[#64748B] opacity-60 hover:opacity-100 transition-opacity pr-1 text-xs">
                      <button 
                        onClick={() => { navigator.clipboard?.writeText(m.texte); toast.success("Message copié"); }} 
                        title="Copier le message" 
                        className="flex h-6 w-6 items-center justify-center rounded-md hover:bg-white/[0.06] hover:text-white transition-colors"
                      >
                        <Copy size={12} />
                      </button>
                      <button 
                        onClick={() => toast.success("Lien prêt")} 
                        title="Partager" 
                        className="flex h-6 w-6 items-center justify-center rounded-md hover:bg-white/[0.06] hover:text-white transition-colors"
                      >
                        <ArrowUp size={12} />
                      </button>
                      <button 
                        title="Options" 
                        className="flex h-6 w-6 items-center justify-center rounded-md hover:bg-white/[0.06] hover:text-white transition-colors"
                      >
                        <DotsThree size={13} />
                      </button>
                    </div>

                    <div className="max-w-[85%] rounded-2xl rounded-tr-xs bg-[#162534] px-5 py-3.5 text-[14.5px] text-[#F2F6F8] leading-relaxed shadow-sm">
                      {m.texte}
                    </div>
                  </div>
                ) : (
                  /* Réponse Flore IA : Zéro card lourde, texte au fil de l'eau, lecture pure */
                  <div className="space-y-2 animate-in fade-in duration-200" data-testid={`case-msg-${i}`}>
                    
                    {/* Corps formaté du message de Flore — décisions/suggestions/actions en enfants :
                        n'apparaissent qu'une fois la réponse complète (voir CorpsMessageFlore) */}
                    <CorpsMessageFlore
                      message={m}
                      onOuvrirCanvas={() => setCanvasActif(true)}
                      canvasActif={canvasActif}
                    >

                    {/* Décision attendue (situation) : réponses rapides ; votre choix devient votre message et Flore répond */}
                    {m.decisions?.length > 0 && !m.reponse && (
                      <div data-testid="decisions-attendues">
                        <div className="mb-1.5 font-code text-[11px] uppercase tracking-[0.16em] text-[#F2B84B]">Décision attendue</div>
                        <div className="flex flex-wrap gap-2">
                          {m.decisions.map((d, k) => (
                            <button key={d} disabled={envoiMsg} onClick={() => trancher(d)} data-testid={`decision-attendue-${k}`}
                              className="rounded-full border border-[#F2B84B]/40 bg-[#F2B84B]/[0.06] px-3.5 py-1.5 text-left text-xs text-[#F2F6F8] transition-colors hover:border-[#F2B84B]/70 hover:bg-[#F2B84B]/[0.14] disabled:opacity-50">
                              {d}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                    {m.decisions?.length > 0 && m.reponse && (
                      <div className="font-code text-[11px] text-[#7C93A8]" data-testid="decision-attendue-prise">Décision prise : {m.reponse}</div>
                    )}
                    {/* Flore propose de consigner la décision qu'elle vient d'enregistrer : ce qu'on en attend, ce qu'on surveille, quand on la revoit */}
                    {m.propose_passation && !cas.veille && onConsignerDecision && i === messages.length - 1 && !envoiMsg && (
                      <div className="flex flex-wrap gap-2" data-testid="propose-passation">
                        <button onClick={onConsignerDecision} data-testid="passation-ouvrir" className="rounded-full border border-[#60A5FA]/50 bg-[#60A5FA]/[0.08] px-3.5 py-1.5 text-xs font-medium text-[#BFDBFE] transition-colors hover:bg-[#60A5FA]/[0.18]">
                          Consigner ce que j'en attends
                        </button>
                      </div>
                    )}
                    {/* Sur quoi repose ce que Flore vient de dire (preuves du rapport) */}
                    {m.preuves?.length > 0 && <PreuvesMessage preuves={m.preuves} />}
                    {/* Pistes que Flore propose de creuser : un clic les envoie comme votre question (sur le dernier message seulement) */}
                    {m.suggestions?.length > 0 && i === messages.length - 1 && !envoiMsg && (
                      <div className="flex flex-wrap gap-2" data-testid="suggestions-flore">
                        {m.suggestions.map((s) => (
                          <button key={s.label} onClick={() => envoyer(null, s.question)} data-testid="suggestion-flore" className="rounded-full border border-[rgba(148,163,184,0.2)] px-3.5 py-1.5 text-xs text-[#D8E2EA] transition-colors hover:border-[#60A5FA]/40 hover:text-white">
                            {s.label}
                          </button>
                        ))}
                      </div>
                    )}
                    {/* Réponses rapides à une question de Flore (revue d'une décision) ; une fois répondu, on garde la trace du choix */}
                    {m.reponses && !m.reponse && cas.veille?.statut === "en_veille" && (
                      <div className="flex flex-wrap gap-2" data-testid="reponses-flore">
                        {m.reponses.map((r) => (
                          <button
                            key={r.action}
                            disabled={envoiMsg}
                            onClick={() => repondreRevue(r.action)}
                            data-testid={`veille-${r.action}`}
                            className={`rounded-full border px-3.5 py-1.5 text-xs transition-colors disabled:opacity-50 ${r.action === "rouvrir" || (m.type === "seuil_atteint" && r.action === "confirmer") || (m.type === "affaiblie" && r.action === "ecarter") ? "border-[#60A5FA] bg-[#60A5FA]/10 font-semibold text-[#BFDBFE] hover:bg-[#60A5FA]/20" : "border-[rgba(148,163,184,0.2)] text-[#D8E2EA] hover:border-[#60A5FA]/40 hover:text-white"}`}
                          >
                            {r.label}
                          </button>
                        ))}
                      </div>
                    )}
                    {/* Suite proposée par Flore (ex. « Découvrir la démonstration ») */}
                    {m.proposition && (
                      <button
                        onClick={() => m.proposition.action === "demo" && navigate("/demo")}
                        data-testid="proposition-flore"
                        className="rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-3 py-1.5 text-xs text-[#DCE6EE] transition-colors hover:border-[#60A5FA]/40 hover:text-[#60A5FA]"
                      >
                        {m.proposition.label}
                      </button>
                    )}

                    {/* Rangée de micro-actions sous la réponse de Flore (Style ChatGPT) */}
                    <div className="flex items-center gap-1.5 pt-2 text-[#64748B] text-xs">
                      <button 
                        onClick={() => { navigator.clipboard?.writeText(m.texte); toast.success("Réponse copiée"); }} 
                        title="Copier la réponse" 
                        className="flex h-7 w-7 items-center justify-center rounded-lg hover:bg-white/[0.06] hover:text-white transition-colors"
                      >
                        <Copy size={13} />
                      </button>
                      <button 
                        onClick={() => toast.success("Merci pour votre retour")} 
                        title="Bonne réponse" 
                        className="flex h-7 w-7 items-center justify-center rounded-lg hover:bg-white/[0.06] hover:text-white transition-colors"
                      >
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M7 10v12" />
                          <path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h3" />
                        </svg>
                      </button>
                      <button 
                        onClick={() => toast.info("Feedback pris en compte")} 
                        title="Mauvaise réponse" 
                        className="flex h-7 w-7 items-center justify-center rounded-lg hover:bg-white/[0.06] hover:text-white transition-colors"
                      >
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M17 14V2" />
                          <path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-3" />
                        </svg>
                      </button>
                      <button 
                        onClick={() => {
                          const derniereQuestion = [...messages].reverse().find(x => x.role === "utilisateur");
                          if (derniereQuestion) {
                            setNouveauMsg(derniereQuestion.texte);
                          }
                        }} 
                        title="Régénérer la réponse" 
                        className="flex h-7 w-7 items-center justify-center rounded-lg hover:bg-white/[0.06] hover:text-white transition-colors"
                      >
                        <ArrowsClockwise size={13} />
                      </button>
                      <button 
                        title="Options" 
                        className="flex h-7 w-7 items-center justify-center rounded-lg hover:bg-white/[0.06] hover:text-white transition-colors"
                      >
                        <DotsThree size={13} />
                      </button>
                    </div>
                    </CorpsMessageFlore>
                  </div>
                )}
                {/* Ligne d'activité de Flore : sous le dernier message du traitement, repliée une fois terminée */}
                {(pilote?.activites || [])
                  .filter((a) => a.apres === i + 1)
                  .map((a) => (
                    <LigneActiviteFlore key={a.id} activite={a} testid={`travail-activite-${a.id}`} />
                  ))}
                {m._activite && <LigneActiviteFlore activite={m._activite} testid={`travail-activite-msg-${i}`} />}
              </div>
            ))}

            {messages.length === 0 && brouillon && (
              <div className="flex min-h-[50vh] flex-col items-center justify-center space-y-3 py-10 text-center" data-testid="brouillon-vide">
                <h2 className="font-display text-3xl font-black tracking-tight text-[#F2F6F8]">Que voulez-vous comprendre<br />ou accomplir ?</h2>
                <p className="text-sm text-[#94A3B8]">Décrivez-le simplement — le travail naît de votre première question, la conversation devient sa mémoire.</p>
              </div>
            )}
            {messages.length === 0 && !brouillon && (
              <div className="py-16 text-center text-sm text-[#7C93A8] space-y-2">
                <p className="font-display text-base text-[#CBD5E1]">
                  Espace de travail ouvert pour <strong>{cas.titre}</strong>
                </p>
                <p className="font-code text-xs">
                  Posez votre première question ci-dessous pour initier l'analyse avec Flore et les jumeaux du Mesh.
                </p>
              </div>
            )}

            {envoiMsg && <FloreActivite genre="travail" testid="case-msg-attente" />}
            <div ref={finFilRef} />
          </div>
        </div>

        {/* Bouton pour descendre si l'utilisateur a scrollé vers le haut */}
        {!estEnBas && (
          <div className="flex justify-center -mb-4 z-20">
            <button
              onClick={allerEnBas}
              className="flex h-7 w-7 items-center justify-center rounded-full border border-white/10 bg-[#0C1724]/90 text-slate-300 shadow-lg backdrop-blur-md hover:text-white transition-all"
              title="Descendre au dernier message"
            >
              <ArrowDown size={14} />
            </button>
          </div>
        )}

        {/* ========================================================================= */}
        {/* COMPOSITEUR DE PROMPT FLOTTANT (Style ChatGPT / Claude)                    */}
        {/* ========================================================================= */}
        <div className="shrink-0 p-4 pb-5" data-testid="case-composer-zone">
          {(() => {
            // Démo interactive : une fois la réplique tapée, elle reste EN ATTENTE — c'est le clic
            // du visiteur sur « Envoyer » qui la publie, jamais un timer (à chaque réplique du profil démo).
            const pretAEnvoyer = !!pilote?.saisie && !pilote.saisie.enFrappe;
            const soumettre = (e) => {
              e?.preventDefault?.();
              if (pilote) { if (pretAEnvoyer) pilote.envoyerSaisie(); return; }
              envoyer(e);
            };
            return (
          <form onSubmit={soumettre} className="mx-auto max-w-3xl">
            <div className="flex items-center gap-2 rounded-2xl border border-white/[0.12] bg-[#0A131C]/90 px-3.5 py-2.5 shadow-2xl backdrop-blur-xl transition-colors focus-within:border-blue-400/60">

              {/* Bouton + pour outils / pièces jointes */}
              <button
                type="button"
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-[#7C93A8] hover:bg-white/[0.06] hover:text-white transition-colors"
                title="Ajouter une ressource ou un jumeau"
              >
                <Plus size={16} />
              </button>

              {/* Champ de saisie aéré — grandit avec son contenu (voir l'effet sur taRef) */}
              <textarea
                ref={taRef}
                value={texteSaisie}
                readOnly={!!pilote}
                onChange={(e) => setNouveauMsg(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    soumettre(e);
                  }
                }}
                placeholder={pilote ? "Conversation de démonstration" : ecran === "mobile" ? "Posez une question…" : "Posez une question à Flore et aux jumeaux du SI…"}
                rows={1}
                data-testid="case-msg-input"
                className="max-h-32 flex-1 resize-none overflow-y-auto bg-transparent px-1 py-1 text-sm text-[#F2F6F8] placeholder:text-[#526578] focus:outline-none"
              />

              {/* Bouton micro vocal */}
              <button
                type="button"
                className="hidden sm:flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-[#7C93A8] hover:bg-white/[0.06] hover:text-white transition-colors"
                title="Commande vocale"
              >
                <Microphone size={16} />
              </button>

              {/* Bouton d'envoi vibrant — en démo, l'index humain pointe dessus une fois la réplique prête */}
              <div className="relative shrink-0">
                <button
                  type="submit"
                  disabled={pilote ? !pretAEnvoyer : envoiMsg || !nouveauMsg.trim()}
                  data-testid="case-msg-send-btn"
                  title="Envoyer le message"
                  className={`flex h-8 w-8 items-center justify-center rounded-xl transition-all ${
                    (pilote ? pretAEnvoyer : nouveauMsg.trim() && !envoiMsg)
                      ? `bg-[#60A5FA] text-[#071019] shadow-md shadow-[#60A5FA]/20 hover:scale-105${pretAEnvoyer ? " animate-pulse" : ""}`
                      : "bg-white/[0.05] text-[#475569] opacity-30 cursor-not-allowed"
                  }`}
                >
                  <ArrowUp size={16} weight="bold" />
                </button>
                {pretAEnvoyer && <IndicateurClic texte="Prêt" sousTexte="Cliquez pour envoyer" testid="indicateur-clic-envoyer" />}
              </div>
            </div>
          </form>
            );
          })()}
        </div>
      </div>

      {/* ========================================================================= */}
      {/* VOLET DROIT : CANVAS DU DOCUMENT GÉNÉRÉ (Style ChatGPT Canvas)           */}
      {/* ========================================================================= */}
      {canvasActif && (
        <div className="absolute inset-0 z-30 h-full overflow-hidden bg-[#071019] transition-all duration-300 lg:static lg:flex-[45] lg:border-l lg:border-white/[0.1]">
          <CanvasDocument onFermer={toggleCanvas} />
        </div>
      )}
    </div>
  );
}
