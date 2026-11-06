import { useState } from "react";
import { UploadSimple, FileText } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { TYPES_TWIN, applicationIdDe, candidatDe, genererTwinId, identifiantMetier, identifiantsDe, twinIdDe, typeTwin } from "@/lib/sources";

const TEXTES = {
  cmdb: "Collez ou déposez un export CMDB JSON/CSV : type, twin_id, application_id, resource_id, supplier_id, team_id, nom, proprietaire, perimetre, identifiants.",
  manifeste: "Collez ou déposez un manifeste JSON : { jumeau: { type, twin_id, application_id, resource_id, supplier_id, team_id, nom, proprietaire, perimetre, identifiants }, sources: [...] }.",
};

const CHAMPS_SECRETS = new Set(["secret", "token", "jeton", "password", "passwd", "mot_de_passe", "api_key", "apikey", "authorization", "bearer"]);
const estObjet = (valeur) => Boolean(valeur) && typeof valeur === "object" && !Array.isArray(valeur);
const normaliserCle = (valeur) => String(valeur ?? "")
  .normalize("NFD")
  .replace(/[\u0300-\u036f]/g, "")
  .trim()
  .toLowerCase()
  .replace(/[^a-z0-9]+/g, "_")
  .replace(/^_+|_+$/g, "");
const premiere = (ligne, cles) => {
  for (const cle of cles) {
    const valeur = ligne?.[cle];
    if (valeur !== undefined && valeur !== null && String(valeur).trim()) return String(valeur).trim();
  }
  return "";
};

function objetNormalise(objet) {
  return Object.fromEntries(Object.entries(objet).map(([cle, valeur]) => [normaliserCle(cle), valeur]));
}

function sansSecrets(valeur) {
  if (Array.isArray(valeur)) return valeur.map(sansSecrets);
  if (!estObjet(valeur)) return valeur;
  return Object.fromEntries(Object.entries(valeur)
    .filter(([cle]) => !CHAMPS_SECRETS.has(normaliserCle(cle)))
    .map(([cle, contenu]) => [cle, sansSecrets(contenu)]));
}

function lireBooleen(valeur) {
  if (typeof valeur === "boolean") return valeur;
  return ["1", "true", "oui", "yes", "o"].includes(String(valeur ?? "").trim().toLowerCase());
}

function lireIdentifiants(valeur) {
  if (estObjet(valeur)) return valeur;
  if (!valeur) return null;
  const texte = String(valeur).trim();
  if (!texte) return null;
  try {
    const parse = JSON.parse(texte);
    if (estObjet(parse)) return parse;
  } catch {
    if (!texte.includes("=")) return null;
  }
  if (!texte.includes("=")) return null;
  const identifiants = {};
  texte.split(/[;,]/).forEach((paire) => {
    const separateur = paire.indexOf("=");
    if (separateur <= 0) return;
    const cle = paire.slice(0, separateur).trim();
    const contenu = paire.slice(separateur + 1).trim();
    if (cle) identifiants[cle] = contenu;
  });
  return Object.keys(identifiants).length ? identifiants : null;
}

function delimiterCsv(texte) {
  const premiereLigne = texte.split(/\r?\n/, 1)[0] || "";
  let meilleur = ",";
  let maximum = -1;
  for (const candidat of [",", ";", "\t"]) {
    let nombre = 0;
    let entreGuillemets = false;
    for (let i = 0; i < premiereLigne.length; i += 1) {
      const caractere = premiereLigne[i];
      if (caractere === '"') entreGuillemets = !entreGuillemets;
      else if (!entreGuillemets && caractere === candidat) nombre += 1;
    }
    if (nombre > maximum) {
      maximum = nombre;
      meilleur = candidat;
    }
  }
  return meilleur;
}

function decouperCsv(texte) {
  const separateur = delimiterCsv(texte);
  const lignes = [];
  let ligne = [];
  let champ = "";
  let entreGuillemets = false;
  for (let i = 0; i < texte.length; i += 1) {
    const caractere = texte[i];
    if (entreGuillemets) {
      if (caractere === '"' && texte[i + 1] === '"') {
        champ += '"';
        i += 1;
      } else if (caractere === '"') {
        entreGuillemets = false;
      } else {
        champ += caractere;
      }
    } else if (caractere === '"') {
      entreGuillemets = true;
    } else if (caractere === separateur) {
      ligne.push(champ);
      champ = "";
    } else if (caractere === "\n") {
      ligne.push(champ);
      lignes.push(ligne);
      ligne = [];
      champ = "";
    } else if (caractere !== "\r") {
      champ += caractere;
    }
  }
  if (champ !== "" || ligne.length > 0) {
    ligne.push(champ);
    lignes.push(ligne);
  }
  return lignes;
}

function lignesCsv(texte) {
  const lignes = decouperCsv(texte);
  if (lignes.length < 2) return [];
  const entetes = lignes[0].map(normaliserCle);
  return lignes.slice(1)
    .filter((ligne) => ligne.some((cellule) => String(cellule || "").trim()))
    .map((ligne) => Object.fromEntries(entetes.map((entete, index) => [entete, String(ligne[index] ?? "").trim()])));
}

function lignesImport(contenu) {
  const texte = String(contenu || "").trim();
  if (!texte) return [];
  if (texte.startsWith("{") || texte.startsWith("[")) {
    const charge = JSON.parse(texte);
    if (Array.isArray(charge)) {
      return charge.filter(estObjet).map((entree) => {
        const ligne = objetNormalise(entree);
        if (entree.sources !== undefined) ligne.sources = entree.sources;
        if (entree.config !== undefined) ligne.config = entree.config;
        return ligne;
      });
    }
    if (!estObjet(charge)) return [];
    if (estObjet(charge.jumeau)) {
      return [{
        ...objetNormalise(charge.jumeau),
        sources: charge.sources ?? charge.jumeau.sources ?? [],
      }];
    }
    return [objetNormalise(charge)];
  }
  return lignesCsv(texte);
}

function identiteDepuisLigne(ligne) {
  const typeBrut = premiere(ligne, ["type", "type_twin", "twin_type", "type_de_twin"]).toUpperCase();
  if (typeBrut && !TYPES_TWIN.includes(typeBrut)) return null;
  const type = typeBrut || "APPLICATION";
  const identite = {};
  if (typeBrut) identite.type = type;

  const applicationId = premiere(ligne, ["application_id", "applicationid", "app_id", "app"]);
  const twinId = premiere(ligne, ["twin_id", "twinid"]);
  const resourceId = premiere(ligne, ["resource_id", "resourceid"]);
  const supplierId = premiere(ligne, ["supplier_id", "supplierid"]);
  const teamId = premiere(ligne, ["team_id", "teamid"]);
  const nom = premiere(ligne, ["nom", "name", "libelle", "label"]);
  const proprietaire = premiere(ligne, ["proprietaire", "owner", "responsable"]);
  const perimetre = premiere(ligne, ["perimetre", "perimeter", "scope"]);
  const candidat = premiere(ligne, ["candidat", "application_candidate", "mode_candidat", "candidate"]);

  if (twinId) identite.twin_id = twinId;
  if (type === "APPLICATION" && applicationId) identite.application_id = applicationId;
  if (resourceId) identite.resource_id = resourceId;
  if (supplierId) identite.supplier_id = supplierId;
  if (teamId) identite.team_id = teamId;
  if (nom) identite.nom = nom;
  if (proprietaire) identite.proprietaire = proprietaire;
  if (perimetre) identite.perimetre = perimetre;

  const identifiants = lireIdentifiants(ligne.identifiants);
  if (identifiants) identite.identifiants = identifiants;
  if (candidat) identite.candidat = lireBooleen(candidat);
  return Object.keys(identite).length ? identite : null;
}

function sourcesDepuisLigne(ligne) {
  let sources = ligne.sources;
  if (typeof sources === "string") {
    try {
      sources = JSON.parse(sources);
    } catch {
      return [];
    }
  }
  if (estObjet(sources)) sources = [sources];
  if (!Array.isArray(sources)) return [];
  return sources.filter(estObjet).map((source) => {
    const normalise = objetNormalise(source);
    const connecteur = premiere(normalise, ["connecteur", "connector"]);
    if (!connecteur) return null;
    const config = estObjet(source.config) ? source.config : estObjet(normalise.config) ? normalise.config : {};
    return {
      connecteur,
      nom: premiere(normalise, ["nom", "name"]) || connecteur,
      environnement: premiere(normalise, ["environnement", "environment"]) || "production",
      perimetre: premiere(normalise, ["perimetre", "perimeter"]),
      proprietaire: premiere(normalise, ["proprietaire", "owner"]),
      config: sansSecrets(config),
    };
  }).filter(Boolean);
}

function completerTwinId(identite) {
  if (!estObjet(identite) || twinIdDe(identite)) return identite;
  const type = typeTwin(identite);
  if (type === "APPLICATION" && !applicationIdDe(identite) && !candidatDe(identite)) return identite;
  return { ...identite, twin_id: genererTwinId(type) };
}

function apercuLocal(contenu, mode) {
  const lignes = lignesImport(contenu);
  if (!lignes.length) return null;
  const ligne = lignes[0];
  const identite = identiteDepuisLigne(ligne);
  if (!identite) return null;
  return { mode, detectees: 1, identite: completerTwinId(identite), nouvelles: sourcesDepuisLigne(ligne), ignorees: [], presentes: [] };
}

function lireApercuLocal(contenu, mode) {
  try {
    return apercuLocal(contenu, mode);
  } catch {
    return null;
  }
}

function fusionnerIdentite(distante, locale) {
  if (!estObjet(locale)) return distante;
  return { ...(estObjet(distante) ? distante : {}), ...locale };
}

function importNouveauType(local) {
  const identite = local?.identite;
  if (!identite) return false;
  const type = typeTwin(identite);
  if (identite.type && type !== "APPLICATION") return true;
  return Boolean(identite.twin_id || identite.resource_id || identite.supplier_id || identite.team_id
    || identite.candidat || identite.identifiants);
}

function identiteImportable(identite) {
  if (!estObjet(identite)) return false;
  const type = typeTwin(identite);
  if (!String(identite.nom || "").trim() || !String(identite.proprietaire || "").trim()) return false;
  if (type === "APPLICATION" && !applicationIdDe(identite) && !candidatDe(identite)) return false;
  return true;
}

export default function ImportIdentite({ commandeId, mode, onImporte }) {
  const [contenu, setContenu] = useState("");
  const [apercu, setApercu] = useState(null);
  const [chargement, setChargement] = useState(false);

  const analyser = async () => {
    if (!contenu.trim()) {
      toast.error("Ajoutez un contenu JSON ou CSV.");
      return;
    }
    setChargement(true);
    const local = lireApercuLocal(contenu, mode);
    try {
      const { data } = await api.post(`/commandes/${commandeId}/import/apercu`, { mode, contenu });
      setApercu({ ...data, identite: completerTwinId(fusionnerIdentite(data?.identite, local?.identite)) });
    } catch (e) {
      if (importNouveauType(local) && identiteImportable(local.identite)) {
        setApercu(local);
      } else {
        toast.error(e.response?.data?.detail || "Analyse impossible");
      }
    } finally {
      setChargement(false);
    }
  };

  const lireFichier = (evenement) => {
    const fichier = evenement.target.files?.[0];
    if (!fichier) return;
    const lecteur = new FileReader();
    lecteur.onload = () => { setContenu(String(lecteur.result || "")); setApercu(null); };
    lecteur.readAsText(fichier);
  };

  const identite = apercu?.identite || {};
  const type = typeTwin(identite);
  const twinId = twinIdDe(identite);
  const identifiant = identifiantMetier(identite);
  const identifiants = Object.entries(identifiantsDe(identite));

  return (
    <div className="rounded-lg border border-[rgba(96,165,250,0.22)] bg-[rgba(96,165,250,0.04)] p-3" data-testid={`identite-import-${mode}`}>
      <p className="flex items-center gap-2 text-[11px] leading-relaxed text-[#94A3B8]">
        <FileText size={14} className="shrink-0 text-[#93C5FD]" /> {TEXTES[mode]}
      </p>
      <input type="file" accept=".json,.csv,text/csv,application/json" onChange={lireFichier} data-testid="import-fichier" className="mt-2 block w-full text-[11px] text-[#94A3B8] file:mr-3 file:rounded-md file:border-0 file:bg-[#17324A] file:px-3 file:py-2 file:text-[11px] file:text-[#BFDBFE]" />
      <textarea value={contenu} onChange={(e) => { setContenu(e.target.value); setApercu(null); }} rows={8} data-testid="import-contenu" placeholder="JSON ou CSV…" className="mt-2 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-3 py-2 font-code text-[11px] text-[#D8E2EA] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/60 focus:outline-none" />
      {!apercu ? (
        <button type="button" onClick={analyser} disabled={chargement} data-testid="import-analyser-btn" className="mt-2 flex items-center gap-1.5 rounded-md bg-[#60A5FA] px-4 py-2 text-xs font-semibold text-[#071019] hover:bg-[#93C5FD] disabled:opacity-40">
          <UploadSimple size={13} /> {chargement ? "Analyse…" : "Analyser"}
        </button>
      ) : (
        <div className="mt-3" data-testid="import-apercu">
          <p className="text-[11px] text-[#D8E2EA]">
            <strong>{identite.nom || applicationIdDe(identite) || twinId || "Identité importée"}</strong>
            <span className="font-code text-[#7C93A8]">
              {" · "}<span data-testid="import-type">{type}</span>
              {twinId && <> · Twin <span data-testid="import-twin-id">{twinId}</span></>}
              {type === "APPLICATION" && <> · App ID <span data-testid="import-app-id">{applicationIdDe(identite) || (candidatDe(identite) ? "candidat" : "à définir")}</span></>}
              {" · "}{apercu.nouvelles.length} nouvelle(s) · {(apercu.ignorees || []).length} déjà présente(s)
            </span>
          </p>
          {identifiant && type !== "APPLICATION" && (
            <p className="mt-1 font-code text-[10px] text-[#93C5FD]" data-testid="import-identifiant">
              {identifiant.label} : {identifiant.valeur || "—"}
            </p>
          )}
          {identite.perimetre && <p className="mt-1 text-[10px] text-[#94A3B8]" data-testid="import-perimetre">Périmètre : {identite.perimetre}</p>}
          {identifiants.length > 0 && (
            <p className="mt-1 font-code text-[10px] text-[#94A3B8]" data-testid="import-identifiants">
              {identifiants.map(([cle, valeur]) => `${cle}=${valeur}`).join(" · ")}
            </p>
          )}
          {apercu.nouvelles.length > 0 && (
            <ul className="mt-2 max-h-32 space-y-1 overflow-y-auto" data-testid="import-nouvelles">
              {apercu.nouvelles.map((s, i) => (
                <li key={`${s.connecteur}-${s.nom}-${i}`} className="rounded-md border border-[rgba(148,163,184,0.16)] px-3 py-1.5 text-[11px] text-[#D8E2EA]">
                  {s.nom} <span className="font-code text-[9px] text-[#7C93A8]">· {s.connecteur} · {s.environnement}</span>
                </li>
              ))}
            </ul>
          )}
          {(apercu.ignorees || []).length > 0 && (
            <p className="mt-2 text-[10px] text-[#F2B84B]" data-testid="import-ignorees">
              {(apercu.ignorees || []).length} source(s) déjà dans la commande seront ignorées.
            </p>
          )}
          {apercu.nouvelles.length === 0 && (
            <p className="mt-2 text-[10px] text-[#7C93A8]">Aucune nouvelle source : seule l'identité sera mise à jour.</p>
          )}
          <button type="button" onClick={() => onImporte(apercu)} data-testid="import-confirmer-btn" className="mt-2 rounded-md bg-[#34D399] px-4 py-2 text-xs font-semibold text-[#071019] hover:bg-[#065F46]">
            Utiliser cette identité
          </button>
        </div>
      )}
    </div>
  );
}
