import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowRight } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import { useContexte } from "@/lib/contexte";
import { nouvelleInstance, statutCalcule } from "@/lib/sources";
import EnteteCommande from "@/components/commande/EnteteCommande";
import AtelierSources from "@/components/commande/AtelierSources";
import InspecteurSource from "@/components/commande/InspecteurSource";
import CatalogueTiroir from "@/components/commande/CatalogueTiroir";
import ImportModal from "@/components/commande/ImportModal";
import PlanDecouverte from "@/components/commande/PlanDecouverte";
import Verification from "@/components/commande/Verification";

export default function Commande() {
  const { cid } = useParams();
  const navigate = useNavigate();
  const { recharger } = useMesh();
  const { setLot } = useContexte();
  const [commande, setCommande] = useState(null);
  const [catalogue, setCatalogue] = useState(null);
  const [sauvegarde, setSauvegarde] = useState(null);
  const [sourceActiveId, setSourceActiveId] = useState(null);
  const [selLot, setSelLot] = useState([]);
  const [tiroirOuvert, setTiroirOuvert] = useState(false);
  const [importOuvert, setImportOuvert] = useState(false);
  const [importMode, setImportMode] = useState("cmdb");
  const [lancement, setLancement] = useState(false);
  const premiereCharge = useRef(true);

  useEffect(() => {
    Promise.all([api.get(`/commandes/${cid}`), api.get("/connecteurs")])
      .then(([c, x]) => setTimeout(() => { setCommande(c.data); setCatalogue(x.data); }, 0))
      .catch(() => { toast.error("Commande introuvable"); navigate("/jumeaux"); });
  }, [cid]);

  // Autosauvegarde (debounce)
  useEffect(() => {
    if (!commande) return;
    if (premiereCharge.current) { premiereCharge.current = false; return; }
    setSauvegarde("encours");
    const t = setTimeout(() => {
      api.patch(`/commandes/${cid}`, { jumeau: commande.jumeau, etape: commande.etape, sources: commande.sources })
        .then(() => setSauvegarde(new Date().toISOString()))
        .catch(() => toast.error("Sauvegarde impossible"));
    }, 900);
    return () => clearTimeout(t);
  }, [commande, cid]);

  const maj = (patch) => setCommande((c) => ({ ...c, ...patch }));
  const majJumeau = (patch) => maj({ jumeau: { ...commande.jumeau, ...patch } });
  const majSource = (sid, patch) => {
    maj({
      sources: commande.sources.map((s) => {
        if (s.id !== sid) return s;
        const fusion = { ...s, ...patch };
        // Cycle de statuts : une correction repasse la source en « à configurer / prête à tester »
        if (patch.config || patch.perimetre !== undefined) {
          const conn = catalogue.connecteurs.find((c) => c.id === fusion.connecteur);
          fusion.statut = statutCalcule({ ...fusion, statut: "a_configurer" }, conn);
          fusion.erreur = null;
        }
        return fusion;
      }),
    });
  };

  const ajouterSources = (instances) => {
    maj({ sources: [...commande.sources, ...instances] });
    const derniere = instances[instances.length - 1];
    if (derniere) setSourceActiveId(derniere.id);
  };

  const ajouterDepuisCatalogue = (connecteur, mode, opts) => {
    const n = commande.sources.filter((s) => s.connecteur === connecteur.id).length + 1;
    let inst = nouvelleInstance(connecteur, n);
    if (mode === "dupliquer" && opts.sourceId) {
      const origine = commande.sources.find((s) => s.id === opts.sourceId);
      if (origine) inst = { ...origine, id: inst.id, nom: `${origine.nom} (copie)`, statut: "a_configurer", erreur: null, dernier_test: null, config: { ...origine.config } };
    }
    if (mode === "profil" && opts.profilId) {
      const p = catalogue.profils.find((x) => x.id === opts.profilId);
      if (p) inst = { ...inst, environnement: p.regles.environnement || inst.environnement, config: { ...inst.config, ...p.regles.config }, proprietaire: inst.proprietaire };
    }
    inst.proprietaire = inst.proprietaire || commande.jumeau.proprietaire || "";
    ajouterSources([inst]);
    setTiroirOuvert(false);
    toast.success(`${inst.nom} ajoutée à la file`);
  };

  const importer = (instances) => {
    const avecIds = instances.map((s, i) => ({ statut: "a_configurer", erreur: null, dernier_test: null, ...s, id: `src-imp-${Date.now().toString(36)}-${i}` }));
    ajouterSources(avecIds);
    setImportOuvert(false);
    setTiroirOuvert(false);
    toast.success(`${avecIds.length} instance(s) importée(s) dans la file`);
  };

  const tester = async (ids) => {
    maj({ sources: commande.sources.map((s) => (ids.includes(s.id) ? { ...s, statut: "test_en_cours" } : s)) });
    try {
      const { data } = await api.post(`/commandes/${cid}/tester`, { ids });
      setTimeout(() => {
        setCommande((c) => ({ ...c, sources: c.sources.map((s) => (data.resultats[s.id] ? { ...s, ...data.resultats[s.id] } : s)) }));
        const echecs = Object.values(data.resultats).filter((r) => r.statut !== "prete").length;
        if (echecs) toast.error(`${echecs} source(s) en échec — voir le détail dans l'inspecteur`);
        else toast.success("Toutes les connexions testées sont prêtes");
      }, 1300);
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
            ? { ...s, environnement: p.regles.environnement || s.environnement, config: { ...s.config, ...p.regles.config } }
            : s
        ),
      });
      toast.success(`Profil « ${p.nom} » appliqué aux instances compatibles`);
      return;
    }
    if (type === "environnement") maj({ sources: commande.sources.map((s) => (selLot.includes(s.id) ? { ...s, environnement: valeur } : s)) });
    if (type === "frequence") maj({ sources: commande.sources.map((s) => (selLot.includes(s.id) ? { ...s, config: { ...s.config, frequence: valeur } } : s)) });
  };

  const lancer = async () => {
    setLancement(true);
    try {
      const { data } = await api.post(`/commandes/${cid}/lancer`);
      toast.success(`Découverte lancée — ${data.sources_lancees} source(s), ${data.sources_reportees} reportée(s)`);
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
    return <div className="flex h-full items-center justify-center font-code text-xs text-[#71716D]" data-testid="commande-chargement">Chargement de la commande…</div>;
  }

  const etape = commande.etape;
  const sourceActive = commande.sources.find((s) => s.id === sourceActiveId) || null;
  const connecteurActif = sourceActive ? catalogue.connecteurs.find((c) => c.id === sourceActive.connecteur) : null;
  const peutContinuer = etape === 1
    ? commande.jumeau.nom.trim() && commande.jumeau.mission.trim() && commande.jumeau.proprietaire.trim()
    : etape === 2 ? commande.sources.length > 0 : true;

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="commande-page">
      <EnteteCommande commande={commande} sauvegarde={sauvegarde} peutContinuer={!!peutContinuer} onQuitter={() => { toast.success("Brouillon enregistré — reprenez quand vous voulez"); navigate("/jumeaux"); }} onEtape={(n) => maj({ etape: n })} />

      <div className="min-h-0 flex-1 overflow-y-auto px-8 py-6 pb-36">
        {etape === 1 && (
          <div className="mx-auto max-w-xl space-y-4" data-testid="etape-identite">
            <h2 className="font-display text-lg font-bold text-[#111110]">Identité du jumeau</h2>
            {[
              ["nom", "Nom de l'application", "Ex. Remboursements"],
              ["domaine", "Domaine", "Ex. Paiement"],
              ["proprietaire", "Propriétaire", "Ex. Équipe Paiements — L. Marchand"],
              ["mission", "Mission métier", "Ex. Traite les demandes de remboursement clients"],
            ].map(([cle, label, ph]) => (
              <div key={cle}>
                <label className="font-code text-[10px] uppercase tracking-[0.2em] text-[#71716D]">{label}</label>
                <input value={commande.jumeau[cle] || ""} onChange={(e) => majJumeau({ [cle]: e.target.value })} placeholder={ph} data-testid={`identite-${cle}`} className="mt-1.5 w-full rounded-md border border-[#E5E5E3] bg-white px-3 py-2.5 text-sm text-[#111110] placeholder:text-[#71716D] focus:border-[#0E7490]/60 focus:outline-none" />
              </div>
            ))}
            <div>
              <label className="font-code text-[10px] uppercase tracking-[0.2em] text-[#71716D]">Environnement</label>
              <select value={commande.jumeau.environnement} onChange={(e) => majJumeau({ environnement: e.target.value })} data-testid="identite-environnement" className="mt-1.5 w-full rounded-md border border-[#E5E5E3] bg-white px-3 py-2.5 text-sm text-[#111110] focus:outline-none">
                {["production", "préproduction", "recette", "développement"].map((e) => <option key={e} value={e}>{e}</option>)}
              </select>
            </div>
          </div>
        )}

        {etape === 2 && (
          <div className="grid h-full min-h-0 grid-cols-12 gap-5" data-testid="etape-atelier">
            {/* Grille fixe 8/4 : la file ne se re-fluide jamais quand l'inspecteur s'ouvre */}
            <div className="col-span-8 min-h-0">
              <AtelierSources
                sources={commande.sources}
                catalogue={catalogue}
                sourceActiveId={sourceActiveId}
                onSelect={setSourceActiveId}
                selLot={selLot}
                setSelLot={setSelLot}
                onTester={tester}
                onOuvrirTiroir={() => setTiroirOuvert(true)}
                onOuvrirImport={() => { setImportMode("fichier"); setImportOuvert(true); }}
              />
            </div>
            <div className="col-span-4 min-h-0">
              <InspecteurSource source={sourceActive} connecteur={connecteurActif} onChange={majSource} onTester={tester} onFermer={() => setSourceActiveId(null)} />
            </div>
          </div>
        )}

        {etape === 3 && <PlanDecouverte sources={commande.sources} catalogue={catalogue} />}
        {etape === 4 && <Verification commande={commande} catalogue={catalogue} onLancer={lancer} lancement={lancement} />}

        <div className="mt-6 flex justify-end">
          {etape < 4 && (
            <button onClick={() => maj({ etape: etape + 1 })} disabled={!peutContinuer} data-testid="etape-suivante-btn" className="flex items-center gap-1.5 rounded-md bg-[#3730A3] px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-[#4338CA] disabled:opacity-30">
              Continuer <ArrowRight size={14} />
            </button>
          )}
        </div>
      </div>

      {tiroirOuvert && (
        <CatalogueTiroir
          catalogue={catalogue}
          sources={commande.sources}
          onAjoute={ajouterDepuisCatalogue}
          onImport={(mode) => { setImportMode(mode); setImportOuvert(true); }}
          onFermer={() => setTiroirOuvert(false)}
        />
      )}
      {importOuvert && <ImportModal key={importMode} commandeId={cid} modeInitial={importMode} onImporte={importer} onFermer={() => setImportOuvert(false)} />}
    </div>
  );
}
