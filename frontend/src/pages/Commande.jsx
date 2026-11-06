import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowRight } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import { useContexte } from "@/lib/contexte";
import {
  AIDES_TYPE_TWIN,
  APPLICATION_ID,
  applicationIdDe,
  candidatDe,
  IDENTIFIANT_TYPE_TWIN,
  LIBELLES_IDENTIFIANT_TWIN,
  LIBELLES_TYPE_TWIN,
  TYPES_TWIN,
  genererTwinId,
  identifiantsDe,
  normaliserJumeau,
  nouvelleInstance,
  statutCalcule,
  typeTwin,
  validerIdentite,
} from "@/lib/sources";
import EnteteCommande from "@/components/commande/EnteteCommande";
import AtelierSources from "@/components/commande/AtelierSources";
import InspecteurSource from "@/components/commande/InspecteurSource";
import CatalogueTiroir from "@/components/commande/CatalogueTiroir";
import ImportIdentite from "@/components/commande/ImportIdentite";
import PlanDecouverte from "@/components/commande/PlanDecouverte";
import Verification from "@/components/commande/Verification";

const CHAMPS_IDENTITE = [
  "type", "twin_id", "application_id", "resource_id", "supplier_id", "team_id",
  "nom", "proprietaire", "perimetre", "identifiants", "candidat",
];

const commandeVide = () => ({
  id: null,
  etat: "local",
  etape: 1,
  jumeau: normaliserJumeau({}),
  sources: [],
});

const identiteCommencee = (etat) => {
  const j = etat?.jumeau || {};
  return Boolean(
    `${j.nom || ""}`.trim()
    || `${j.proprietaire || ""}`.trim()
    || `${j.perimetre || ""}`.trim()
    || applicationIdDe(j)
    || `${j.team_id || ""}`.trim()
    || `${j.resource_id || ""}`.trim()
    || `${j.supplier_id || ""}`.trim()
    || Object.keys(identifiantsDe(j)).length
    || (etat?.sources || []).length
  );
};

function ChampIdentifiants({ valeur, onChange }) {
  const [texte, setTexte] = useState(() => JSON.stringify(valeur || {}, null, 2));
  const [erreur, setErreur] = useState("");
  const externe = useRef(valeur);

  useEffect(() => {
    if (valeur !== externe.current) {
      externe.current = valeur;
      setTexte(JSON.stringify(valeur || {}, null, 2));
      setErreur("");
    }
  }, [valeur]);

  const changer = (evenement) => {
    const brut = evenement.target.value;
    setTexte(brut);
    if (!brut.trim()) {
      setErreur("");
      externe.current = {};
      onChange({});
      return;
    }
    try {
      const parse = JSON.parse(brut);
      if (!parse || typeof parse !== "object" || Array.isArray(parse)) {
        throw new Error("objet attendu");
      }
      setErreur("");
      externe.current = parse;
      onChange(parse);
    } catch {
      setErreur("JSON invalide — un objet d'identifiants externes est attendu.");
    }
  };

  return (
    <div>
      <label className="font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">Identifiants externes</label>
      <textarea
        value={texte}
        onChange={changer}
        rows={4}
        placeholder={'{"ci_servicenow": "CI-123", "contrat": "CTR-42"}'}
        data-testid="identite-identifiants"
        className={`mt-1.5 w-full rounded-md border bg-[#0F1D28] px-3 py-2 font-code text-[11px] text-[#D8E2EA] placeholder:text-[#7C93A8] focus:outline-none ${erreur ? "border-[#F87171]/60 focus:border-[#F87171]" : "border-[rgba(148,163,184,0.16)] focus:border-[#60A5FA]/60"}`}
      />
      <p className={`mt-1 text-[10px] ${erreur ? "text-[#F87171]" : "text-[#7C93A8]"}`} data-testid="identite-identifiants-aide">
        {erreur || "Objet JSON : CI ServiceNow, contrat, asset ID, URL, code fournisseur…"}
      </p>
    </div>
  );
}

export default function Commande() {
  const { cid: cidParam } = useParams();
  const navigate = useNavigate();
  const { recharger } = useMesh();
  const { setLot } = useContexte();
  const [commande, setCommande] = useState(null);
  const [catalogue, setCatalogue] = useState(null);
  const [sauvegarde, setSauvegarde] = useState(null);
  const [sourceActiveId, setSourceActiveId] = useState(null);
  const [selLot, setSelLot] = useState([]);
  const [tiroirOuvert, setTiroirOuvert] = useState(false);
  const [modeIdentite, setModeIdentite] = useState("formulaire");
  const [lancement, setLancement] = useState(false);
  const cidRef = useRef(cidParam);
  const premiereCharge = useRef(true);
  const commandeRef = useRef(null);
  const sale = useRef(false);
  const twinIdManuel = useRef(false);

  useEffect(() => {
    premiereCharge.current = true;
    if (cidParam === "nouvelle") {
      cidRef.current = null;
      api.get("/connecteurs")
        .then(({ data }) => {
          setCatalogue(data);
          setCommande(commandeVide());
        })
        .catch(() => { toast.error("Chargement du catalogue impossible"); navigate("/jumeaux"); });
      return;
    }
    cidRef.current = cidParam;
    Promise.all([api.get(`/commandes/${cidParam}`), api.get("/connecteurs")])
      .then(([c, x]) => setTimeout(() => {
        setCommande({ ...c.data, jumeau: normaliserJumeau(c.data.jumeau || {}) });
        setCatalogue(x.data);
      }, 0))
      .catch(() => { toast.error("Commande introuvable"); navigate("/jumeaux"); });
  }, [cidParam, navigate]);

  useEffect(() => {
    if (commande) commandeRef.current = commande;
  }, [commande]);

  const sauvegarder = async (etat = commandeRef.current) => {
    if (!etat) return null;
    if (!cidRef.current && !identiteCommencee(etat)) return null;
    setSauvegarde("encours");
    try {
      let id = cidRef.current || etat.id;
      if (!id) {
        const { data } = await api.post("/commandes", {});
        id = data.id;
        cidRef.current = id;
        window.history.replaceState(null, "", `/commande/${id}`);
        setCommande((c) => (c ? { ...c, id } : c));
      }
      await api.patch(`/commandes/${id}`, { jumeau: etat.jumeau, etape: etat.etape, sources: etat.sources });
      if (commandeRef.current === etat) sale.current = false;
      setSauvegarde(new Date().toISOString());
      return id;
    } catch (e) {
      setSauvegarde(null);
      throw e;
    }
  };

  // Autosauvegarde (debounce) : la dernière frappe n'est jamais perdue à la sortie.
  useEffect(() => {
    if (!commande) return;
    if (premiereCharge.current) { premiereCharge.current = false; return; }
    sale.current = true;
    setSauvegarde("encours");
    const t = setTimeout(() => {
      sauvegarder(commande).catch(() => toast.error("Sauvegarde impossible"));
    }, 900);
    return () => clearTimeout(t);
  }, [commande]);

  useEffect(() => () => {
    const id = cidRef.current;
    if (sale.current && commandeRef.current && id) {
      api.patch(`/commandes/${id}`, {
        jumeau: commandeRef.current.jumeau,
        etape: commandeRef.current.etape,
        sources: commandeRef.current.sources,
      }).catch(() => {});
    }
  }, []);

  const maj = (patch) => setCommande((c) => ({ ...c, ...patch }));
  const majJumeau = (patch) => maj({ jumeau: { ...commande.jumeau, ...patch } });

  const changerType = (type) => {
    const jumeau = commande.jumeau;
    const patch = { type, candidat: type === "APPLICATION" ? candidatDe(jumeau) : false };
    if (type !== "APPLICATION") patch.application_id = "";
    const twin = (jumeau.twin_id || "").trim();
    const automatique = /^(app|team|res|sup|eco)-[a-z0-9]+$/i.test(twin);
    if (!twin || (automatique && !twinIdManuel.current)) patch.twin_id = genererTwinId(type);
    majJumeau(patch);
  };
  // Une correction de configuration repasse la source par « à configurer / prête à tester ».
  const avecStatut = (source, patch = {}) => {
    const fusion = { ...source, ...patch };
    const conn = catalogue.connecteurs.find((c) => c.id === fusion.connecteur);
    fusion.statut = statutCalcule({ ...fusion, statut: "a_configurer" }, conn);
    fusion.erreur = null;
    return fusion;
  };
  const majSource = (sid, patch) => {
    maj({
      sources: commande.sources.map((s) => {
        if (s.id !== sid) return s;
        return patch.config || patch.perimetre !== undefined || patch.environnement !== undefined
          ? avecStatut(s, patch)
          : { ...s, ...patch };
      }),
    });
  };

  const ajouterSources = (instances) => {
    maj({ sources: [...commande.sources, ...instances] });
    const derniere = instances[instances.length - 1];
    if (derniere) setSourceActiveId(derniere.id);
  };

  const ajouterDepuisCatalogue = (connecteur, mode, opts) => {
    if (connecteur?.branche === false) {
      toast.error("Ce connecteur n'est pas encore branché : il ne peut pas alimenter la découverte.");
      return;
    }
    const n = commande.sources.filter((s) => s.connecteur === connecteur.id).length + 1;
    let inst = nouvelleInstance(connecteur, n);
    if (mode === "dupliquer" && opts.sourceId) {
      const origine = commande.sources.find((s) => s.id === opts.sourceId);
      if (origine) inst = { ...origine, id: inst.id, nom: `${origine.nom} (copie)`, statut: "a_configurer", erreur: null, dernier_test: null, config: { ...origine.config } };
    }
    if (mode === "profil" && opts.profilId) {
      const p = catalogue.profils.find((x) => x.id === opts.profilId);
      if (p) inst = avecStatut(inst, { environnement: p.regles.environnement || inst.environnement, config: { ...inst.config, ...p.regles.config } });
    }
    if (mode === "dupliquer") inst = avecStatut(inst);
    inst.proprietaire = inst.proprietaire || commande.jumeau.proprietaire || "";
    ajouterSources([inst]);
    setTiroirOuvert(false);
    toast.success(`${inst.nom} ajoutée à la file`);
  };

  const importer = (apercu) => {
    const instances = apercu?.nouvelles || [];
    if (apercu?.identite) {
      const actuel = commande.jumeau;
      const importee = apercu.identite;
      const patch = {};
      CHAMPS_IDENTITE.forEach((cle) => {
        if (importee[cle] !== undefined && importee[cle] !== null) patch[cle] = importee[cle];
      });
      const type = TYPES_TWIN.includes(patch.type) ? patch.type : typeTwin(actuel);
      if (!patch.twin_id && type !== typeTwin(actuel)) patch.twin_id = genererTwinId(type);
      majJumeau(normaliserJumeau({ ...actuel, ...patch, type }));
    }
    const avecIds = instances.map((s, i) => avecStatut(
      { statut: "a_configurer", erreur: null, dernier_test: null, ...s, id: `src-imp-${Date.now().toString(36)}-${i}` },
    ));
    if (avecIds.length) ajouterSources(avecIds);
    setModeIdentite("formulaire");
    setTiroirOuvert(false);
    toast.success(`${avecIds.length} instance(s) importée(s) dans la file${apercu?.identite ? " avec l'identité" : ""}`);
  };

  const quitter = async () => {
    if (!cidRef.current && !identiteCommencee(commande)) {
      navigate("/jumeaux");
      return;
    }
    try {
      await sauvegarder(commande);
      toast.success("Brouillon enregistré — reprenez quand vous voulez");
      navigate("/jumeaux");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Sauvegarde impossible — réessayez avant de quitter");
    }
  };

  // L'import CMDB/manifeste a besoin d'un identifiant de commande : on n'ouvre un brouillon
  // qu'à ce moment-là, pas au simple clic sur « Commander ».
  useEffect(() => {
    if (modeIdentite === "formulaire" || cidRef.current || !commande) return;
    api.post("/commandes", {})
      .then(({ data }) => {
        cidRef.current = data.id;
        window.history.replaceState(null, "", `/commande/${data.id}`);
        setCommande((c) => (c ? { ...c, id: data.id } : c));
      })
      .catch(() => toast.error("Création de la commande impossible"));
  }, [modeIdentite, commande]);

  const tester = async (ids) => {
    try {
      await sauvegarder(commande);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Sauvegarde impossible avant le test");
      return;
    }
    maj({ sources: commande.sources.map((s) => (ids.includes(s.id) ? { ...s, statut: "test_en_cours" } : s)) });
    try {
      const id = cidRef.current;
      if (!id) return;
      const { data } = await api.post(`/commandes/${id}/tester`, { ids });
      setCommande((c) => ({ ...c, sources: c.sources.map((s) => (data.resultats[s.id] ? { ...s, ...data.resultats[s.id] } : s)) }));
      const echecs = Object.values(data.resultats).filter((r) => r.statut !== "prete").length;
      if (echecs) toast.error(`${echecs} source(s) en échec — voir le détail dans l'inspecteur`);
      else toast.success("Toutes les connexions testées sont prêtes");
    } catch {
      maj({ sources: commande.sources.map((s) => (ids.includes(s.id) ? { ...s, statut: "a_configurer" } : s)) });
      toast.error("Test impossible");
    }
  };

  const actionLot = (type, valeur) => {
    if (type === "tester") {
      tester(selLot);
      return;
    }
    if (type === "supprimer") {
      maj({ sources: commande.sources.filter((s) => !selLot.includes(s.id)) });
      if (selLot.includes(sourceActiveId)) setSourceActiveId(null);
      toast.success(`${selLot.length} source(s) retirée(s) de la commande`);
      setSelLot([]);
      return;
    }
    if (type === "profil") {
      const p = catalogue.profils.find((x) => x.id === valeur);
      if (!p) return;
      maj({
        sources: commande.sources.map((s) =>
          selLot.includes(s.id) && p.applicable.includes(s.connecteur)
            ? avecStatut(s, { environnement: p.regles.environnement || s.environnement, config: { ...s.config, ...p.regles.config } })
            : s
        ),
      });
      toast.success(`Profil « ${p.nom} » appliqué aux instances compatibles`);
      return;
    }
    if (type === "environnement") maj({ sources: commande.sources.map((s) => (selLot.includes(s.id) ? avecStatut(s, { environnement: valeur }) : s)) });
    if (type === "frequence") maj({ sources: commande.sources.map((s) => (selLot.includes(s.id) ? avecStatut(s, { config: { ...s.config, frequence: valeur } }) : s)) });
  };

  const lancer = async () => {
    setLancement(true);
    try {
      await sauvegarder(commande);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Sauvegarde impossible avant le lancement");
      setLancement(false);
      return;
    }
    try {
      const id = cidRef.current;
      if (!id) return;
      const { data } = await api.post(`/commandes/${id}/lancer`);
      sale.current = false;
      toast.success(data.deja
        ? "Commande déjà lancée — le jumeau est déjà au registre."
        : data.naissance === "en_cours"
          ? "Naissance du jumeau en cours : lecture du code, connaissances prouvées, fiche vivante. Il apparaîtra au registre, en observation."
          : `Découverte lancée — ${data.sources_lancees} source(s), ${data.sources_reportees} reportée(s)`);
      recharger();
      navigate("/jumeaux");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Lancement impossible");
      setLancement(false);
    }
  };

  // La sélection en lot morphe la barre Aurora en barre d'actions (store partagé)
  useEffect(() => {
    if (commande && catalogue && selLot.length > 0) {
      setLot({ ids: selLot, profils: catalogue.profils, onAction: actionLot, onAnnuler: () => setSelLot([]) });
    } else {
      setLot(null);
    }
    return () => setLot(null);
  }, [selLot, commande, catalogue]);

  if (!commande || !catalogue) {
    return <div className="flex h-full items-center justify-center font-code text-xs text-[#7C93A8]" data-testid="commande-chargement">Chargement de la commande…</div>;
  }

  const etape = commande.etape;
  const sourceActive = commande.sources.find((s) => s.id === sourceActiveId) || null;
  const connecteurActif = sourceActive ? catalogue.connecteurs.find((c) => c.id === sourceActive.connecteur) : null;
  const type = typeTwin(commande.jumeau);
  const appId = applicationIdDe(commande.jumeau);
  const appIdValide = APPLICATION_ID.test(appId);
  const validationIdentite = validerIdentite(commande.jumeau);
  const peutContinuer = etape === 1
    ? validationIdentite.valide
    : etape === 2 ? commande.sources.length > 0 : true;

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="commande-page">
      <EnteteCommande commande={commande} sauvegarde={sauvegarde} peutContinuer={!!peutContinuer} onQuitter={quitter} onEtape={(n) => maj({ etape: n })} />

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 pb-36 sm:px-8 sm:py-6">
        {etape === 1 && (
          <div className="mx-auto max-w-xl space-y-4" data-testid="etape-identite">
            <h2 className="font-display text-lg font-bold text-[#F2F6F8]">Identité du jumeau</h2>
            <div className="inline-flex rounded-lg border border-[rgba(148,163,184,0.16)] p-1" data-testid="identite-modes">
              {[
                ["formulaire", "Formulaire"],
                ["cmdb", "CMDB"],
                ["manifeste", "Manifeste"],
              ].map(([cle, label]) => (
                <button key={cle} type="button" onClick={() => setModeIdentite(cle)} data-testid={`identite-mode-${cle}`} className={`rounded-md px-3 py-1.5 text-[11px] font-semibold transition-colors ${modeIdentite === cle ? "bg-[#60A5FA] text-[#071019]" : "text-[#94A3B8] hover:text-[#F2F6F8]"}`}>
                  {label}
                </button>
              ))}
            </div>

            {modeIdentite === "formulaire" ? (
              <>
                <div>
                  <label htmlFor="type-twin" className="font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">Type de Twin</label>
                  <select
                    id="type-twin"
                    value={type}
                    onChange={(e) => changerType(e.target.value)}
                    data-testid="identite-type"
                    className="mt-1.5 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-3 py-2.5 text-sm text-[#F2F6F8] focus:border-[#60A5FA]/60 focus:outline-none"
                  >
                    {TYPES_TWIN.map((t) => (
                      <option key={t} value={t} label={`${t} — ${LIBELLES_TYPE_TWIN[t]}`} />
                    ))}
                  </select>
                  <p className="mt-1 text-[10px] text-[#7C93A8]" data-testid="identite-type-aide">{AIDES_TYPE_TWIN[type]}</p>
                </div>

                {type === "APPLICATION" && (
                  <div>
                    <label className="font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">App ID</label>
                    <input
                      value={applicationIdDe(commande.jumeau)}
                      onChange={(e) => majJumeau({ application_id: e.target.value })}
                      placeholder="Ex. remboursements"
                      maxLength={128}
                      aria-invalid={appId.length > 0 && !appIdValide}
                      data-testid="identite-application_id"
                      className={`mt-1.5 w-full rounded-md border bg-[#0F1D28] px-3 py-2.5 text-sm text-[#F2F6F8] placeholder:text-[#7C93A8] focus:outline-none ${appId.length > 0 && !appIdValide ? "border-[#F87171]/60 focus:border-[#F87171]" : "border-[rgba(148,163,184,0.16)] focus:border-[#60A5FA]/60"}`}
                    />
                    <p className={`mt-1 text-[10px] ${appId.length > 0 && !appIdValide ? "text-[#F87171]" : "text-[#7C93A8]"}`} data-testid="identite-application_id-aide">
                      {appId.length > 0 && !appIdValide
                        ? "Identifiant invalide — minuscules, chiffres, point, tiret ou underscore."
                        : candidatDe(commande.jumeau)
                          ? "Mode candidat : l'App ID reste facultatif."
                          : "Identifiant stable et unique, en minuscules."}
                    </p>
                    <label className="mt-2 flex items-center gap-2 text-[11px] text-[#94A3B8]">
                      <input
                        type="checkbox"
                        checked={candidatDe(commande.jumeau)}
                        onChange={(e) => majJumeau({ candidat: e.target.checked })}
                        data-testid="identite-candidat"
                        className="h-3.5 w-3.5 accent-[#60A5FA]"
                      />
                      Application candidate — autoriser l'absence d'App ID
                    </label>
                  </div>
                )}

                {type !== "APPLICATION" && IDENTIFIANT_TYPE_TWIN[type] && (
                  <div>
                    <label className="font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">{LIBELLES_IDENTIFIANT_TWIN[IDENTIFIANT_TYPE_TWIN[type]]}</label>
                    <input
                      value={commande.jumeau[IDENTIFIANT_TYPE_TWIN[type]] || ""}
                      onChange={(e) => majJumeau({ [IDENTIFIANT_TYPE_TWIN[type]]: e.target.value })}
                      placeholder={type === "TEAM" ? "Ex. equipe-paiements" : type === "RESOURCE" ? "Ex. CI-123 / asset fournisseur" : "Ex. FOURN-42"}
                      maxLength={128}
                      data-testid={`identite-${IDENTIFIANT_TYPE_TWIN[type]}`}
                      className="mt-1.5 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-3 py-2.5 text-sm text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/60 focus:outline-none"
                    />
                    <p className="mt-1 text-[10px] text-[#7C93A8]">
                      {type === "TEAM" ? "Identifiant d'organisation (facultatif si le twin_id suffit)." : "Identifiant métier externe (facultatif si le twin_id suffit)."}
                    </p>
                  </div>
                )}

                {[
                  ["nom", "Nom", "Ex. Remboursements"],
                  ["proprietaire", "Propriétaire", "Ex. Équipe Paiements — L. Marchand"],
                  ["perimetre", type === "TEAM" || type === "ECOSYSTEM" ? "Périmètre (requis)" : "Périmètre", "Ex. Équipe Paiements / ressources tierces"],
                ].map(([cle, label, ph]) => (
                  <div key={cle}>
                    <label className="font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">{label}</label>
                    <input
                      value={commande.jumeau[cle] || ""}
                      onChange={(e) => majJumeau({ [cle]: e.target.value })}
                      placeholder={ph}
                      maxLength={200}
                      data-testid={`identite-${cle}`}
                      className="mt-1.5 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-3 py-2.5 text-sm text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/60 focus:outline-none"
                    />
                  </div>
                ))}

                <details className="rounded-md border border-[rgba(148,163,184,0.12)] px-3 py-2" data-testid="identite-avance">
                  <summary className="cursor-pointer font-code text-[10px] uppercase tracking-[0.18em] text-[#7C93A8]">Avancé — identité interne</summary>
                  <div className="mt-3 space-y-3">
                    <div>
                      <label className="font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">Twin ID (généré automatiquement)</label>
                      <input
                        value={commande.jumeau.twin_id || ""}
                        onChange={(e) => { twinIdManuel.current = true; majJumeau({ twin_id: e.target.value }); }}
                        placeholder="Généré si vide"
                        maxLength={128}
                        data-testid="identite-twin_id"
                        className="mt-1.5 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-3 py-2.5 font-code text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/60 focus:outline-none"
                      />
                      <p className="mt-1 text-[10px] text-[#7C93A8]">Généré et stable. À modifier seulement si un identifiant interne existe déjà.</p>
                    </div>
                    <ChampIdentifiants valeur={identifiantsDe(commande.jumeau)} onChange={(valeur) => majJumeau({ identifiants: valeur })} />
                  </div>
                </details>
              </>
            ) : (
              <ImportIdentite commandeId={cidRef.current} mode={modeIdentite} onImporte={importer} />
            )}
          </div>
        )}

        {etape === 2 && (
          <div className="grid h-full min-h-0 grid-cols-1 gap-5 lg:grid-cols-12" data-testid="etape-atelier">
            {/* Grand écran : grille fixe 8/4, la file ne se re-fluide jamais quand l'inspecteur s'ouvre.
                Petit écran : la file prend toute la largeur et l'inspecteur / le catalogue s'ouvrent en feuille par-dessus. */}
            <div className="min-h-0 lg:col-span-8">
              <AtelierSources
                sources={commande.sources}
                catalogue={catalogue}
                sourceActiveId={sourceActiveId}
                onSelect={setSourceActiveId}
                selLot={selLot}
                setSelLot={setSelLot}
                onTester={tester}
                onOuvrirTiroir={() => setTiroirOuvert(true)}
              />
            </div>
            {(tiroirOuvert || sourceActive) && <div className="fixed inset-0 z-30 bg-black/50 lg:hidden" onClick={() => { setTiroirOuvert(false); setSourceActiveId(null); }} aria-hidden="true" data-testid="feuille-fond" />}
            <div className={`${tiroirOuvert || sourceActive ? "fixed inset-x-0 bottom-0 z-40 max-h-[85dvh] overflow-y-auto rounded-t-2xl border-t border-[rgba(148,163,184,0.2)] bg-[#0B1522] p-3 shadow-2xl" : "hidden"} min-h-0 lg:static lg:col-span-4 lg:block lg:max-h-none lg:overflow-visible lg:rounded-none lg:border-0 lg:bg-transparent lg:p-0 lg:shadow-none`} data-testid="feuille-panneau">
              {tiroirOuvert ? (
                <CatalogueTiroir
                  catalogue={catalogue}
                  sources={commande.sources}
                  onAjoute={ajouterDepuisCatalogue}
                  onFermer={() => setTiroirOuvert(false)}
                />
              ) : (
                <InspecteurSource source={sourceActive} connecteur={connecteurActif} onChange={majSource} onTester={tester} onFermer={() => setSourceActiveId(null)} />
              )}
            </div>
          </div>
        )}

        {etape === 3 && <PlanDecouverte sources={commande.sources} catalogue={catalogue} />}
        {etape === 4 && (
          <Verification
            commande={commande}
            catalogue={catalogue}
            onLancer={lancer}
            lancement={lancement}
            onCorriger={(sid) => { setSourceActiveId(sid); maj({ etape: 2 }); }}
          />
        )}

        <div className="mt-6 flex justify-end">
          {etape < 4 && (
            <button onClick={() => maj({ etape: etape + 1 })} disabled={!peutContinuer} data-testid="etape-suivante-btn" className="flex items-center gap-1.5 rounded-md bg-[#60A5FA] px-4 py-2 text-xs font-semibold text-[#071019] transition-colors hover:bg-[#93C5FD] disabled:opacity-30">
              Continuer <ArrowRight size={14} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
