import {
  actionsPourObjet,
  cleIdempotence,
  configurationAction,
  construireCorps,
  decisionEstTranchee,
  fusionnerObjet,
  messageErreurTransition,
  statutObjet,
} from "./boucleUi";

const situation = {
  id: "sit-1",
  type: "SITUATION",
  famille: "emergence",
  titre: "Latence des paiements",
  donnees: { resume: "Les paiements ralentissent." },
};

const investigation = {
  id: "inv-1",
  type: "INVESTIGATION",
  famille: "investigation",
  titre: "Comprendre le goulot",
  donnees: { statut: "OPEN" },
};

const decisionProposee = {
  id: "dec-1",
  type: "DECISION",
  famille: "decision",
  titre: "Automatiser ou réorganiser ?",
  donnees: {
    statut: "PROPOSED",
    options: ["Automatiser", "Réorganiser"],
    criteres: ["coût", "délai"],
  },
};

const decisionTranchee = {
  ...decisionProposee,
  donnees: {
    ...decisionProposee.donnees,
    statut: "DECIDED",
    acteur: "comité-cartes",
    choix: "Automatiser",
  },
};

const initiative = { id: "ini-1", type: "INITIATIVE", famille: "decision", titre: "Automatiser" };
const outcome = { id: "out-1", type: "OUTCOME", famille: "resultat_apprentissage", titre: "Latence basse" };
const learning = { id: "lea-1", type: "LEARNING", famille: "resultat_apprentissage", titre: "Leçon" };

describe("statutObjet", () => {
  test("normalise le statut porté par donnees et retire les accents", () => {
    expect(statutObjet({ donnees: { statut: "Décidée" } })).toBe("DECIDEE");
    expect(statutObjet({ statut: "en cours" })).toBe("EN_COURS");
    expect(statutObjet({})).toBe("");
  });
});

describe("decisionEstTranchee", () => {
  test("reconnaît un statut tranché même porté par donnees", () => {
    expect(decisionEstTranchee(decisionTranchee)).toBe(true);
    expect(decisionEstTranchee(decisionProposee)).toBe(false);
  });

  test("reconnaît une décision avec acteur et choix quand le statut est absent", () => {
    expect(decisionEstTranchee({ donnees: { acteur: "comité", choix: "A" } })).toBe(true);
    expect(decisionEstTranchee({ donnees: { choix: "A" } })).toBe(false);
  });
});

describe("actionsPourObjet", () => {
  test("une situation ouvre une investigation", () => {
    expect(actionsPourObjet(situation).map((action) => action.id)).toEqual(["ouvrir_investigation"]);
  });

  test("une investigation ouverte propose une décision et un learning", () => {
    expect(actionsPourObjet(investigation).map((action) => action.id))
      .toEqual(["proposer_decision", "capitaliser_learning"]);
  });

  test("une investigation fermée ne propose plus de décision", () => {
    expect(actionsPourObjet({ ...investigation, donnees: { statut: "CLOSED" } }).map((action) => action.id))
      .toEqual(["capitaliser_learning"]);
  });

  test("une décision proposée se tranche, une décision tranchée lance une initiative", () => {
    expect(actionsPourObjet(decisionProposee).map((action) => action.id)).toEqual(["trancher_decision"]);
    expect(actionsPourObjet(decisionTranchee).map((action) => action.id)).toEqual(["lancer_initiative"]);
  });

  test("une décision rejetée ne propose aucune action", () => {
    expect(actionsPourObjet({ ...decisionProposee, donnees: { ...decisionProposee.donnees, statut: "REJECTED" } }))
      .toEqual([]);
  });

  test("une initiative mesure un outcome, un outcome capitalise un learning", () => {
    expect(actionsPourObjet(initiative).map((action) => action.id)).toEqual(["mesurer_outcome"]);
    expect(actionsPourObjet(outcome).map((action) => action.id)).toEqual(["capitaliser_learning"]);
  });

  test("un learning clôt la boucle et un type inconnu n'offre rien", () => {
    expect(actionsPourObjet(learning)).toEqual([]);
    expect(actionsPourObjet({ type: "TWIN" })).toEqual([]);
    expect(actionsPourObjet(null)).toEqual([]);
  });
});

describe("configurationAction", () => {
  test("trancher propose les options de la décision dans une liste accessible", () => {
    const action = configurationAction("trancher_decision", decisionProposee);
    const champChoix = action.champs.find((champ) => champ.nom === "choix");

    expect(action.api).toBe("trancherDecision");
    expect(action.typeSource).toBe("DECISION");
    expect(champChoix.type).toBe("select");
    expect(champChoix.options).toEqual(["Automatiser", "Réorganiser"]);
  });

  test("trancher retombe sur une saisie libre sans options connues", () => {
    const action = configurationAction("trancher_decision", { type: "DECISION", donnees: {} });
    expect(action.champs.find((champ) => champ.nom === "choix").type).toBe("text");
  });

  test("le learning choisit la route selon la source", () => {
    expect(configurationAction("capitaliser_learning", outcome).api)
      .toBe("capitaliserLearningDepuisOutcome");
    expect(configurationAction("capitaliser_learning", investigation).api)
      .toBe("capitaliserLearningDepuisInvestigation");
  });
});

describe("construireCorps", () => {
  test("ouvre une investigation en exigeant titre et question", () => {
    expect(construireCorps("ouvrir_investigation", {}).erreur).toContain("titre");
    expect(construireCorps("ouvrir_investigation", { titre: "Comprendre" }).erreur).toContain("question");
    expect(construireCorps("ouvrir_investigation", {
      titre: "  Comprendre  ",
      question: "  Pourquoi ?  ",
      perimetre: "  paiements  ",
    }).corps).toEqual({ titre: "Comprendre", question: "Pourquoi ?", perimetre: "paiements" });
  });

  test("propose une décision avec une option par ligne", () => {
    expect(construireCorps("proposer_decision", { titre: "Décider" }).erreur).toContain("option");
    const resultat = construireCorps("proposer_decision", {
      titre: "Décider",
      options: " Autonomiser \n\n Réorganiser ",
      criteres: "coût\ndélai",
      incertitudes: "volume",
      resume: "Contexte",
    });
    expect(resultat.corps).toEqual({
      titre: "Décider",
      options: ["Autonomiser", "Réorganiser"],
      criteres: ["coût", "délai"],
      incertitudes: ["volume"],
      resume: "Contexte",
    });
  });

  test("tranche avec un acteur, un choix et un motif optionnel", () => {
    expect(construireCorps("trancher_decision", { choix: "A" }, decisionProposee).erreur).toContain("acteur");
    expect(construireCorps("trancher_decision", { acteur: "comité" }, decisionProposee).erreur).toContain("choix");
    expect(construireCorps("trancher_decision", { acteur: "comité", choix: "Autre" }, decisionProposee).erreur)
      .toContain("options");
    expect(construireCorps("trancher_decision", {
      acteur: " comité-cartes ",
      choix: "Automatiser",
      motif: " Réduire le délai ",
    }, decisionProposee).corps).toEqual({
      acteur: "comité-cartes",
      choix: "Automatiser",
      motif: "Réduire le délai",
    });
  });

  test("lance une initiative depuis une décision", () => {
    expect(construireCorps("lancer_initiative", {}).erreur).toContain("titre");
    const resultat = construireCorps("lancer_initiative", {
      titre: "Automatiser la pièce",
      resume: "Déploiement progressif",
      proprietaire: "Alice",
      perimetre: "paiements",
      outcome_attendu_ids: "out-1, out-2",
    });
    expect(resultat.corps).toEqual({
      titre: "Automatiser la pièce",
      resume: "Déploiement progressif",
      proprietaire: "Alice",
      perimetre: "paiements",
      outcome_attendu_ids: ["out-1", "out-2"],
    });
  });

  test("mesure un outcome avec une valeur numérique et une cible optionnelle", () => {
    expect(construireCorps("mesurer_outcome", {}).erreur).toContain("métrique");
    expect(construireCorps("mesurer_outcome", { metrique: "p95" }).erreur).toContain("valeur");
    expect(construireCorps("mesurer_outcome", { metrique: "p95", valeur: "beaucoup" }).erreur).toContain("nombre");
    expect(construireCorps("mesurer_outcome", {
      metrique: "p95",
      valeur: "180,5",
      unite: "ms",
      source: "suivi-cartes",
      cible: "200",
      periode: "2026-10",
      interpretation: "La latence baisse",
      preuve_ids: "preuve-1, preuve-2",
    }).corps).toEqual({
      mesure: { metrique: "p95", valeur: 180.5, unite: "ms", source: "suivi-cartes" },
      valeur_attendue: 200,
      periode: "2026-10",
      interpretation: "La latence baisse",
      preuve_ids: ["preuve-1", "preuve-2"],
    });
  });

  test("refuse une cible non numérique", () => {
    expect(construireCorps("mesurer_outcome", { metrique: "p95", valeur: "180", cible: "vite" }).erreur)
      .toContain("cible");
  });

  test("capitalise un learning depuis un outcome ou une investigation", () => {
    expect(construireCorps("capitaliser_learning", {}).erreur).toContain("énoncé");
    expect(construireCorps("capitaliser_learning", {
      enonce: "  Un contrôle synchrone amplifie les incidents.  ",
      scope: " paiements ",
      conditions_applicabilite: " volume stable \n charge nominale ",
    }).corps).toEqual({
      enonce: "Un contrôle synchrone amplifie les incidents.",
      scope: "paiements",
      conditions_applicabilite: ["volume stable", "charge nominale"],
    });
  });

  test("une action inconnue est refusée sans lever", () => {
    expect(construireCorps("inconnue", {})).toEqual({ corps: null, erreur: "Action de boucle inconnue." });
  });
});

describe("messageErreurTransition", () => {
  test("explique les 404 et 409 avec le détail de l'API", () => {
    expect(messageErreurTransition({ response: { status: 404 } })).toContain("introuvable");
    expect(messageErreurTransition({ response: { status: 409, data: { detail: "déjà tranchée" } } }))
      .toBe("déjà tranchée");
  });

  test("aplatit les erreurs de validation 422", () => {
    const erreur = {
      response: {
        status: 422,
        data: { detail: [{ loc: ["body", "titre"], msg: "Champ requis" }, { msg: "Option invalide" }] },
      },
    };
    expect(messageErreurTransition(erreur)).toBe("titre : Champ requis · Option invalide");
  });

  test("retombe sur un message lisible", () => {
    expect(messageErreurTransition(new Error("réseau"), "Transition impossible.")).toBe("Transition impossible.");
  });
});

describe("fusionnerObjet", () => {
  test("remplace un objet existant sans changer l'ordre et ajoute les nouveaux", () => {
    const misAJour = { ...situation, titre: "Latence corrigée" };
    const liste = fusionnerObjet([situation, investigation], misAJour);
    expect(liste.map((objet) => objet.id)).toEqual(["sit-1", "inv-1"]);
    expect(liste[0].titre).toBe("Latence corrigée");

    const ajoutee = fusionnerObjet(liste, outcome);
    expect(ajoutee.map((objet) => objet.id)).toEqual(["sit-1", "inv-1", "out-1"]);
  });

  test("ignore une réponse sans identifiant", () => {
    const liste = [situation];
    expect(fusionnerObjet(liste, null)).toBe(liste);
    expect(fusionnerObjet(liste, { titre: "Sans id" })).toBe(liste);
  });
});

describe("cleIdempotence", () => {
  test("produit une clé non vide", () => {
    const cle = cleIdempotence();
    expect(typeof cle).toBe("string");
    expect(cle.length).toBeGreaterThan(8);
  });
});
