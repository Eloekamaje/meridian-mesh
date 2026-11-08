import {
  ACTIONS_BOUCLE,
  TRANSITIONS_CONTRIBUTION,
  TYPES_LECTURE,
  actionsPourObjet,
  configurationAction,
  construireCorps,
  statutsSuivants,
} from "./boucleUi";

const investigation = {
  id: "inv-1",
  type: "INVESTIGATION",
  famille: "investigation",
  mode: "DECLARED",
  titre: "Comprendre la latence",
  donnees: { statut: "OPEN", expert_ids: [] },
};

const hypothese = {
  id: "hypothesis-1",
  type: "HYPOTHESIS",
  famille: "investigation",
  mode: "PROPOSED",
  titre: "Le contrôle synchrone bloque",
  donnees: { statut: "OPEN", investigation_id: "inv-1" },
};

const contribution = {
  id: "contribution-1",
  type: "EXPERT_CONTRIBUTION",
  famille: "investigation",
  mode: "DECLARED",
  titre: "La règle est contournée",
  donnees: {
    statut: "PROPOSED",
    expert_id: "expert-1",
    investigation_id: "inv-1",
    contenu: "La règle est contournée",
  },
};

const expert = {
  id: "expert-1",
  type: "EXPERT",
  famille: "investigation",
  mode: "DECLARED",
  titre: "Camille Martin",
  donnees: { nom: "Camille Martin", domaine: "Cartes", statut: "ACTIVE" },
};

describe("C5e — cycle et lecture des experts", () => {
  test("le cycle des contributions est explicite et terminal sur ARCHIVED", () => {
    expect(TRANSITIONS_CONTRIBUTION).toEqual({
      PROPOSED: ["ACCEPTED", "REJECTED", "ARCHIVED"],
      ACCEPTED: ["ARCHIVED"],
      REJECTED: ["ARCHIVED"],
      ARCHIVED: [],
    });
    expect(statutsSuivants("EXPERT_CONTRIBUTION", "PROPOSED")).toEqual(
      ["ACCEPTED", "REJECTED", "ARCHIVED"]);
    expect(statutsSuivants("EXPERT_CONTRIBUTION", "ACCEPTED")).toEqual(["ARCHIVED"]);
    expect(statutsSuivants("EXPERT_CONTRIBUTION", "ARCHIVED")).toEqual([]);
  });

  test("TYPES_LECTURE contient EXPERT et EXPERT_CONTRIBUTION", () => {
    expect(TYPES_LECTURE).toContain("EXPERT");
    expect(TYPES_LECTURE).toContain("EXPERT_CONTRIBUTION");
  });

  test("une investigation ouverte et une hypothèse proposent de solliciter un expert", () => {
    expect(actionsPourObjet(investigation).map((action) => action.id))
      .toContain("solliciter_expert");
    expect(actionsPourObjet(hypothese).map((action) => action.id))
      .toContain("solliciter_expert");
    expect(actionsPourObjet({
      ...investigation,
      donnees: { ...investigation.donnees, statut: "CLOSED" },
    }).map((action) => action.id)).not.toContain("solliciter_expert");
  });

  test("une contribution propose ses transitions de statut, un expert aucune", () => {
    expect(actionsPourObjet(contribution).map((action) => action.id)).toEqual(
      ["changer_statut_contribution"]);
    expect(actionsPourObjet(contribution).map((action) => action.testid)).toEqual(
      ["boucle-action-statut-contribution"]);
    expect(actionsPourObjet(expert)).toEqual([]);
    expect(actionsPourObjet({
      ...contribution,
      donnees: { ...contribution.donnees, statut: "ARCHIVED" },
    })).toEqual([]);
  });
});

describe("C5e — configuration des actions", () => {
  test("l'inscription d'un expert est globale et n'expose que les champs du registre", () => {
    const action = configurationAction("inscrire_expert", null);

    expect(action.api).toBe("creerExpert");
    expect(action.champs.map((champ) => champ.nom)).toEqual([
      "nom", "domaine", "role", "methodes", "responsabilites", "perimetre",
      "sources_autorisees", "outils_autorises", "limites", "preuves", "confiance",
    ]);
    for (const interdit of ["statut", "mode", "id", "tenant_id"]) {
      expect(action.champs.map((champ) => champ.nom)).not.toContain(interdit);
    }
  });

  test("solliciter un expert depuis une investigation utilise la route du parent", () => {
    const action = configurationAction("solliciter_expert", investigation, {
      experts: [{ value: "expert-1", label: "Camille Martin" }],
    });

    expect(action.api).toBe("creerContributionInvestigation");
    expect(action.typeSource).toBe("INVESTIGATION");
    const champExpert = action.champs.find((champ) => champ.nom === "expert_id");
    expect(champExpert.type).toBe("select");
    expect(champExpert.options).toEqual([
      { value: "expert-1", label: "Camille Martin" },
    ]);
  });

  test("solliciter un expert depuis une hypothèse utilise la route de l'hypothèse", () => {
    const action = configurationAction("solliciter_expert", hypothese);

    expect(action.api).toBe("creerContributionHypothese");
    expect(action.typeSource).toBe("HYPOTHESIS");
    expect(action.champs.map((champ) => champ.nom)).not.toContain("hypothesis_id");
    expect(action.champs.map((champ) => champ.nom)).not.toContain("investigation_id");
  });

  test("le changement de statut d'une contribution ne propose que ses transitions", () => {
    const action = configurationAction("changer_statut_contribution", contribution);

    expect(action.api).toBe("changerStatutContribution");
    expect(action.champs.find((champ) => champ.nom === "vers").options).toEqual(
      ["ACCEPTED", "REJECTED", "ARCHIVED"]);
    expect(configurationAction("changer_statut_contribution", {
      ...contribution,
      donnees: { ...contribution.donnees, statut: "ARCHIVED" },
    }).api).toBeNull();
  });
});

describe("C5e — construction des corps", () => {
  test("inscrire un expert exige nom et domaine et normalise les listes", () => {
    expect(construireCorps("inscrire_expert", {}).erreur).toContain("nom");
    expect(construireCorps("inscrire_expert", { nom: "Camille" }).erreur)
      .toContain("domaine");

    const { corps, erreur } = construireCorps("inscrire_expert", {
      nom: "  Camille Martin  ",
      domaine: "  Cartes bancaires  ",
      role: "  Expert métier  ",
      methodes: "Entretien\nAnalyse de dossier",
      responsabilites: "Valider, Documenter",
      perimetre: "Équipe cartes",
      sources_autorisees: "Confluence, Jira",
      outils_autorises: "lecture",
      limites: "Pas d'accès aux données clients",
      preuves: "preuve-1, preuve-2",
      confiance: "0,7",
    });

    expect(erreur).toBeUndefined();
    expect(corps).toEqual({
      nom: "Camille Martin",
      domaine: "Cartes bancaires",
      role: "Expert métier",
      methodes: ["Entretien", "Analyse de dossier"],
      responsabilites: ["Valider", "Documenter"],
      perimetre: "Équipe cartes",
      sources_autorisees: ["Confluence", "Jira"],
      outils_autorises: ["lecture"],
      limites: ["Pas d'accès aux données clients"],
      preuves: ["preuve-1", "preuve-2"],
      confiance: 0.7,
    });
  });

  test("solliciter un expert exige un expert et un contenu", () => {
    expect(construireCorps("solliciter_expert", { contenu: "Constat" }).erreur)
      .toContain("expert");
    expect(construireCorps("solliciter_expert", {
      expert_id: "expert-1", contenu: "   ",
    }).erreur).toContain("contenu");

    const { corps, erreur } = construireCorps("solliciter_expert", {
      expert_id: "expert-1",
      contenu: "  La règle est contournée  ",
      constats: "Saisie après validation\nDeuxième constat",
      claim_ids_proposes: "claim-3",
      hypothesis_ids_soutenues: "hypothesis-1",
      hypothesis_ids_contestees: "hypothesis-2",
      inconnues: "volume réel",
      contribution_le: " 2026-11-08T10:00:00+00:00 ",
      preuves: "doc://entretien",
      confiance: "0,6",
    });

    expect(erreur).toBeUndefined();
    expect(corps).toEqual({
      expert_id: "expert-1",
      contenu: "La règle est contournée",
      constats: ["Saisie après validation", "Deuxième constat"],
      claim_ids_proposes: ["claim-3"],
      hypothesis_ids_soutenues: ["hypothesis-1"],
      hypothesis_ids_contestees: ["hypothesis-2"],
      inconnues: ["volume réel"],
      contribution_le: "2026-11-08T10:00:00+00:00",
      preuves: ["doc://entretien"],
      confiance: 0.6,
    });
    for (const interdit of ["statut", "mode", "id", "tenant_id", "hypothesis_id"]) {
      expect(corps).not.toHaveProperty(interdit);
    }
  });

  test("changer le statut d'une contribution refuse une transition non autorisée", () => {
    expect(construireCorps("changer_statut_contribution",
      { vers: "PROPOSED" }, contribution).erreur).toContain("refusée");
    expect(construireCorps("changer_statut_contribution", {}, contribution).erreur)
      .toContain("statut");

    const { corps } = construireCorps("changer_statut_contribution", {
      vers: "accepted",
      motif: "  Relecture concordante  ",
      preuves: "preuve-1, preuve-2",
    }, contribution);

    expect(corps).toEqual({
      vers: "ACCEPTED",
      motif: "Relecture concordante",
      preuves: ["preuve-1", "preuve-2"],
    });
  });

  test("les actions C5e sont déclarées avec leurs libellés et testids", () => {
    expect(ACTIONS_BOUCLE.inscrire_expert.testid).toBe("boucle-nouveau-expert");
    expect(ACTIONS_BOUCLE.solliciter_expert.testid)
      .toBe("boucle-action-solliciter-expert");
    expect(ACTIONS_BOUCLE.changer_statut_contribution.testid)
      .toBe("boucle-action-statut-contribution");
  });
});
