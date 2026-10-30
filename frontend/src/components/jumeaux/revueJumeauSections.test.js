// Sections « Interfaces et impacts » et « Promotion » de la revue : elles lisent et écrivent par l'API réelle,
// avec les points d'ancrage que les tests d'écran attendent.
import fs from "fs";
import path from "path";
import {
  estJumeauProvisoire,
  estJumeauReel,
  missionProposeePromotion,
  nomProposePromotion,
  raisonsProvisoire,
} from "@/lib/jumeaux";

const lire = (fichier) => fs.readFileSync(path.join(__dirname, fichier), "utf8");

test("InterfacesJumeau charge l'API et expose contrats, opérations, assertions et dernier run", () => {
  const source = lire("InterfacesJumeau.jsx");
  expect(source).toContain("api.get(`/jumeaux/${encodeURIComponent(jid)}/interfaces`)");
  for (const testid of [
    "interfaces-jumeau", "interfaces-contrat", "interfaces-operation", "interfaces-assertion",
    "interfaces-run", "interfaces-chargement", "interfaces-erreur", "interfaces-vide",
  ]) {
    expect(source).toContain(`data-testid="${testid}"`);
  }
  // Aucun chemin HTML brut : les données d'interface restent du texte rendu par React.
  expect(source).not.toContain("dangerouslySetInnerHTML");
});

test("PromotionJumeau n'est visible que pour un twin provisoire complet et appelle l'API de promotion", () => {
  const source = lire("PromotionJumeau.jsx");
  expect(source).toContain('jumeau.niveau !== "complet"');
  expect(source).toContain("estJumeauProvisoire(jumeau)");
  expect(source).toContain("api.post(`/jumeaux/${encodeURIComponent(identifiant)}/promouvoir`");
  for (const testid of [
    "promotion-jumeau", "promotion-nom", "promotion-mission", "promotion-motif", "promotion-btn",
  ]) {
    expect(source).toContain(`data-testid="${testid}"`);
  }
  for (const statut of ["400", "404", "409"]) expect(source).toContain(`statut === ${statut}`);
  expect(source).toContain("onPromu?.()");
  // Le texte explique que l'id de l'application ne change pas.
  expect(source).toMatch(/identifiant ne change pas/);
  expect(source).not.toContain("dangerouslySetInnerHTML");
});

test("RevueJumeau intègre les deux sections pour un jumeau réel et recharge par setRelecture", () => {
  const source = lire("../../pages/RevueJumeau.jsx");
  expect(source).toContain("InterfacesJumeau");
  expect(source).toContain("PromotionJumeau");
  expect(source).toContain("Interfaces et impacts");
  expect(source).toContain("setRelecture((n) => n + 1)");
  expect(source).toContain("estJumeauReel(jumeau)");
  expect(source).toContain("estJumeauProvisoire(jumeau)");
});

test("un twin est provisoire par sa mission ou son nom, pas par son seul statut d'observation", () => {
  expect(estJumeauProvisoire({ nom: "Nouveau jumeau", mission: "dfggg" })).toBe(true);
  expect(estJumeauProvisoire({ nom: "Paiements", mission: "" })).toBe(true);
  expect(estJumeauProvisoire({ nom: "Paiements", mission: "à confirmer" })).toBe(true);
  expect(estJumeauProvisoire({ nom: "Paiements", mission: "Application Paiements, comprise à partir de son code" })).toBe(true);
  expect(estJumeauProvisoire({ nom: "Paiements", mission: "Traite les paiements des clients", statut: "observation" })).toBe(false);
  expect(raisonsProvisoire({ nom: "Nouveau jumeau", mission: "dfggg" })).toHaveLength(2);
});

test("un jumeau réel se reconnaît à origine, avec le drapeau historique en repli", () => {
  expect(estJumeauReel({ origine: "reel" })).toBe(true);
  expect(estJumeauReel({ reel: true })).toBe(true);
  expect(estJumeauReel({ origine: "demonstration" })).toBe(false);
});

test("la promotion propose un nom lisible et ne recopie jamais un libellé provisoire", () => {
  expect(nomProposePromotion({ nom: "Nouveau jumeau", mission: "dfggg", sources_detail: [{ nom: "Dépôt gsf-mockup · main · abc123" }] }))
    .toBe("gsf-mockup");
  expect(nomProposePromotion({ nom: "Paiements", mission: "Traite les paiements" })).toBe("Paiements");
  expect(nomProposePromotion({ nom: "Nouveau jumeau", mission: "dfggg" })).toBe("");
  expect(missionProposeePromotion({ nom: "Nouveau jumeau", mission: "dfggg" })).toBe("");
  expect(missionProposeePromotion({ nom: "Nouveau jumeau", mission: "dfggg", mission_proposee: "Traite les paiements" }))
    .toBe("Traite les paiements");
});
