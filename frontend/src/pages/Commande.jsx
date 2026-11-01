import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowRight } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import { useContexte } from "@/lib/contexte";
import { APPLICATION_ID, nouvelleInstance, statutCalcule } from "@/lib/sources";
import EnteteCommande from "@/components/commande/EnteteCommande";
import AtelierSources from "@/components/commande/AtelierSources";
import InspecteurSource from "@/components/commande/InspecteurSource";
import CatalogueTiroir from "@/components/commande/CatalogueTiroir";
import ImportIdentite from "@/components/commande/ImportIdentite";
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
  const [modeIdentite, setModeIdentite] = useState("formulaire");
  const [lancement, setLancement] = useState(false);
  const premiereCharge = useRef(true);
  const commandeRef = useRef(null);
  const sale = useRef(false);

  useEffect(() => {
    Promise.all([api.get(`/commandes/${cid}`), api.get("/connecteurs")])
      .then(([c, x]) => setTimeout(() => { setCommande(c.data); setCatalogue(x.data); }, 0))
      .catch(() => { toast.error("Commande introuvable"); navigate("/jumeaux"); });
  }, [cid]);

  useEffect(() => {
    if (commande) commandeRef.current = commande;
  }, [commande]);

  const sauvegarder = async (etat = commandeRef.current) => {
    if (!etat) return;
    setSauvegarde("encours");
    try {
      await api.patch(`/commandes/${cid}`, { jumeau: etat.jumeau, etape: etat.etape, sources: etat.sources });
      if (commandeRef.current === etat) sale.current = false;
      setSauvegarde(new Date().toISOString());
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
  }, [commande, cid]);

  useEffect(() => () => {
    if (sale.current && commandeRef.current) {
      api.patch(`/commandes/${cid}`, {
        jumeau: commandeRef.current.jumeau,
        etape: commandeRef.current.etape,
        sources: commandeRef.current.sources,
      }).catch(() => {});
    }
  }, [cid]);

  const maj = (patch) => setCommande((c) => ({ ...c, ...patch }));
  const majJumeau = (patch) => maj({ jumeau: { ...commande.jumeau, ...patch } });
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
    if (apercu?.identite) majJumeau(apercu.identite);
    const avecIds = instances.map((s, i) => avecStatut(
      { statut: "a_configurer", erreur: null, dernier_test: null, ...s, id: `src-imp-${Date.now().toString(36)}-${i}` },
    ));
    if (avecIds.length) ajouterSources(avecIds);
    setModeIdentite("formulaire");
    setTiroirOuvert(false);
    toast.success(`${avecIds.length} instance(s) importée(s) dans la file${apercu?.identite ? " avec l'identité" : ""}`);
  };

  const quitter = async () => {
    try {
      await sauvegarder(commande);
      toast.success("Brouillon enregistré — reprenez quand vous voulez");
      navigate("/jumeaux");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Sauvegarde impossible — réessayez avant de quitter");
    }
  };

  const tester = async (ids) => {
    try {
      await sauvegarder(commande);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Sauvegarde impossible avant le test");
      return;
    }
    maj({ sources: commande.sources.map((s) => (ids.includes(s.id) ? { ...s, statut: "test_en_cours" } : s)) });
    try {
      const { data } = await api.post(`/commandes/${cid}/tester`, { ids });
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
      const { data } = await api.post(`/commandes/${cid}/lancer`);
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
  const appId = (commande.jumeau.application_id || "").trim();
  const appIdValide = APPLICATION_ID.test(appId);
  const peutContinuer = etape === 1
    ? appIdValide && (commande.jumeau.nom || "").trim() && (commande.jumeau.proprietaire || "").trim()
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
                {[
                  ["application_id", "App ID", "Ex. remboursements"],
                  ["nom", "Nom de l'application", "Ex. Remboursements"],
                  ["proprietaire", "Propriétaire", "Ex. Équipe Paiements — L. Marchand"],
                ].map(([cle, label, ph]) => (
                  <div key={cle}>
                    <label className="font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">{label}</label>
                    <input
                      value={commande.jumeau[cle] || ""}
                      onChange={(e) => majJumeau({ [cle]: e.target.value })}
                      placeholder={ph}
                      maxLength={cle === "application_id" ? 128 : 200}
                      aria-invalid={cle === "application_id" && appId.length > 0 && !appIdValide}
                      data-testid={`identite-${cle}`}
                      className={`mt-1.5 w-full rounded-md border bg-[#0F1D28] px-3 py-2.5 text-sm text-[#F2F6F8] placeholder:text-[#7C93A8] focus:outline-none ${cle === "application_id" && appId.length > 0 && !appIdValide ? "border-[#F87171]/60 focus:border-[#F87171]" : "border-[rgba(148,163,184,0.16)] focus:border-[#60A5FA]/60"}`}
                    />
                    {cle === "application_id" && (
                      <p className={`mt-1 text-[10px] ${appId.length > 0 && !appIdValide ? "text-[#F87171]" : "text-[#7C93A8]"}`} data-testid="identite-application_id-aide">
                        {appId.length > 0 && !appIdValide
                          ? "Identifiant invalide — minuscules, chiffres, point, tiret ou underscore."
                          : "Identifiant stable et unique, en minuscules."}
                      </p>
                    )}
                  </div>
                ))}
              </>
            ) : (
              <ImportIdentite commandeId={cid} mode={modeIdentite} onImporte={importer} />
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
