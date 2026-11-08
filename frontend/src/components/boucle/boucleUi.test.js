import {
  actionsPourObjet,
  cleIdempotence,
  configurationAction,
  construireCorps,
  decisionEstTranchee,
  detailSourceApresTransition,
  fusionnerObjet,
  idObjet,
  messageErreurTransition,
  statutObjet,
  statutsSuivants,
  titreObjet,
  TRANSITIONS_OPPORTUNITE,
  TRANSITIONS_RISQUE,
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

const expressionProposee = {
  id: "expr-1",
  type: "EXPRESSION",
  famille: "emergence",
  titre: "Automatiser la ressaisie",
  donnees: {
    statut: "PROPOSED",
    situation_id: "sit-1",
    type_expression: "OPPORTUNITE",
    formulation: "Automatiser la ressaisie",
  },
};

const opportunite = {
  id: "opportunity-1",
  type: "OPPORTUNITY",
  famille: "emergence",
  titre: "Automatiser la ressaisie",
  donnees: {
    statut: "DETECTED",
    valeur_potentielle: 12000,
    probabilite: 0.7,
    impact: "Deux ETP libérés",
    horizon: "90 jours",
    criteres: ["faisable", "mesurable"],
  },
};

const risque = {
  id: "risk-1",
  type: "RISK",
  famille: "emergence",
  titre: "Dépendance fournisseur",
  donnees: {
    statut: "DETECTED",
    probabilite: 0.4,
    impact: "Arrêt des paiements",
    horizon: "6 mois",
    criteres: ["criticité"],
  },
};

describe("statutObjet", () => {
  test("normalise le statut porté par donnees et retire les accents", () => {
    expect(statutObjet({ donnees: { statut: "Décidée" } })).toBe("DECIDEE");
    expect(statutObjet({ statut: "en cours" })).toBe("EN_COURS");
    expect(statutObjet({})).toBe("");
  });
});

describe("identifiants et titres", () => {
  test("idObjet retourne null pour un identifiant vide, sans confondre 0", () => {
    expect(idObjet("")).toBeNull();
    expect(idObjet("   ")).toBeNull();
    expect(idObjet({ id: "" })).toBeNull();
    expect(idObjet({ id: "  " })).toBeNull();
    expect(idObjet("sit-1")).toBe("sit-1");
    expect(idObjet({ id: 0 })).toBe("0");
  });

  test("titreObjet tolère un tableau et retombe sur l'identifiant", () => {
    expect(titreObjet({ titre: ["Latence", { ignore: true }, "paiements"] })).toBe("Latence, paiements");
    expect(titreObjet({ id: "sit-1" })).toBe("sit-1");
    expect(titreObjet("")).toBe("Objet sans titre");
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
  test("une situation non exprimée ouvre une investigation et peut être exprimée", () => {
    expect(actionsPourObjet(situation).map((action) => action.id))
      .toEqual(["ouvrir_investigation", "creer_expression"]);
  });

  test("une situation déjà exprimée ne propose plus l'action Exprimer", () => {
    expect(actionsPourObjet({
      ...situation,
      donnees: { ...situation.donnees, expression_id: "expr-1" },
    }).map((action) => action.id)).toEqual(["ouvrir_investigation"]);
  });

  test("une investigation ouverte propose une décision, un scénario et un learning", () => {
    expect(actionsPourObjet(investigation).map((action) => action.id))
      .toEqual(["proposer_decision", "creer_scenario", "capitaliser_learning"]);
  });

  test("une investigation fermée permet encore de décrire un scénario", () => {
    expect(actionsPourObjet({ ...investigation, donnees: { statut: "CLOSED" } }).map((action) => action.id))
      .toEqual(["creer_scenario", "capitaliser_learning"]);
  });

  test("une décision proposée se tranche et peut porter un scénario", () => {
    expect(actionsPourObjet(decisionProposee).map((action) => action.id))
      .toEqual(["trancher_decision", "creer_scenario"]);
  });

  test("une décision tranchée lance une initiative et peut porter un scénario", () => {
    expect(actionsPourObjet(decisionTranchee).map((action) => action.id))
      .toEqual(["lancer_initiative", "creer_scenario"]);
  });

  test("une décision déjà reliée à une initiative garde la création de scénario", () => {
    expect(actionsPourObjet({
      ...decisionTranchee,
      donnees: { ...decisionTranchee.donnees, initiative_id: "ini-1" },
    }).map((action) => action.id)).toEqual(["creer_scenario"]);
  });

  test("une décision rejetée ne propose aucune action", () => {
    expect(actionsPourObjet({ ...decisionProposee, donnees: { ...decisionProposee.donnees, statut: "REJECTED" } }))
      .toEqual([]);
  });

  test("une initiative mesure un outcome, un outcome capitalise un learning", () => {
    expect(actionsPourObjet(initiative).map((action) => action.id)).toEqual(["mesurer_outcome"]);
    expect(actionsPourObjet(outcome).map((action) => action.id)).toEqual(["capitaliser_learning"]);
  });

  test("une expression proposée peut être qualifiée en opportunité ou en risque", () => {
    expect(actionsPourObjet(expressionProposee).map((action) => action.id))
      .toEqual(["qualifier_opportunite", "qualifier_risque"]);
  });

  test("une expression rejetée ou archivée ne propose plus de qualification", () => {
    for (const statut of ["REJECTED", "ARCHIVED"]) {
      expect(actionsPourObjet({
        ...expressionProposee,
        donnees: { ...expressionProposee.donnees, statut },
      })).toEqual([]);
    }
  });

  test("une opportunité propose ses transitions de statut, un risk aussi", () => {
    expect(actionsPourObjet(opportunite).map((action) => action.id))
      .toEqual(["changer_statut_opportunite"]);
    expect(actionsPourObjet(risque).map((action) => action.id))
      .toEqual(["changer_statut_risque"]);
    expect(actionsPourObjet({
      ...opportunite,
      donnees: { ...opportunite.donnees, statut: "LEARNED" },
    })).toEqual([]);
  });

  test("un learning clôt la boucle et un type inconnu n'offre rien", () => {
    expect(actionsPourObjet(learning)).toEqual([]);
    expect(actionsPourObjet({ type: "TWIN" })).toEqual([]);
    expect(actionsPourObjet(null)).toEqual([]);
  });
});

describe("tables de transitions", () => {
  test("les tables sont explicites, copiées et synchronisées", () => {
    const attendu = {
      DETECTED: ["MATURING", "QUALIFIED", "REJECTED", "DORMANT"],
      MATURING: ["QUALIFIED", "REJECTED", "DORMANT"],
      QUALIFIED: ["INVESTIGATING", "SCENARIOS_AVAILABLE", "REJECTED", "DORMANT"],
      INVESTIGATING: ["SCENARIOS_AVAILABLE", "DECIDED", "REJECTED", "DORMANT"],
      SCENARIOS_AVAILABLE: ["DECIDED", "REJECTED", "DORMANT"],
      DECIDED: ["INITIATED", "REJECTED", "DORMANT"],
      INITIATED: ["MEASURED", "REJECTED"],
      MEASURED: ["LEARNED"],
      LEARNED: [],
      REJECTED: [],
      DORMANT: ["MATURING", "REJECTED"],
    };
    expect(TRANSITIONS_OPPORTUNITE).toEqual(attendu);
    expect(TRANSITIONS_RISQUE).toEqual(attendu);
    expect(TRANSITIONS_RISQUE).not.toBe(TRANSITIONS_OPPORTUNITE);
  });
});

describe("statutsSuivants", () => {
  test("reprend le cycle canonique et rend une liste vide pour un état terminal", () => {
    expect(statutsSuivants("OPPORTUNITY", "DETECTED"))
      .toEqual(["MATURING", "QUALIFIED", "REJECTED", "DORMANT"]);
    expect(statutsSuivants("RISK", "LEARNED")).toEqual([]);
    expect(statutsSuivants("OPPORTUNITY", "")).toEqual([]);
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
    expect(action.champs.some((champ) => champ.nom === "acteur")).toBe(false);
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

  test("la création de situation racine ne dépend d'aucun objet source", () => {
    const action = configurationAction("creer_situation", null);

    expect(action.api).toBe("creerSituation");
    expect(action.typeSource).toBe("");
    expect(action.champs.map((champ) => champ.nom)).toEqual([
      "titre", "description", "resume", "priorite", "twin_ids", "mode",
    ]);
    expect(action.champs.find((champ) => champ.nom === "mode").options.map((option) => option.value))
      .toEqual(["DECLARED", "OBSERVED", "INFERRED", "PROPOSED", "CONFIRMED"]);
  });

  test("l'expression expose formulation, type, canal, auteur, inconnues et confiance", () => {
    const action = configurationAction("creer_expression", situation);

    expect(action.api).toBe("creerExpression");
    expect(action.typeSource).toBe("SITUATION");
    expect(action.champs.map((champ) => champ.nom)).toEqual([
      "formulation", "type_expression", "canal", "auteur", "inconnues", "confiance",
    ]);
    expect(action.champs.find((champ) => champ.nom === "formulation").requis).toBe(true);
    expect(action.champs.find((champ) => champ.nom === "type_expression").options)
      .toContain("OPPORTUNITE");
  });

  test("la création de scénario expose les métriques et listes attendues", () => {
    const action = configurationAction("creer_scenario", investigation);

    expect(action.api).toBe("creerScenario");
    expect(action.typeSource).toBe("INVESTIGATION");
    expect(action.champs.map((champ) => champ.nom)).toEqual([
      "titre", "description", "hypothesis_ids", "actions", "valeur_estimee",
      "cout_estime", "delai_jours", "risque", "complexite", "confiance",
      "dependances", "impacts", "preuves", "reversibilite", "statut",
    ]);
    expect(action.champs.find((champ) => champ.nom === "reversibilite").options)
      .toEqual(["REVERSIBLE", "PARTIELLE", "IRREVERSIBLE"]);
    expect(action.champs.find((champ) => champ.nom === "statut").options)
      .toEqual(["DRAFT", "PROPOSED", "EVALUATED", "SELECTED", "REJECTED", "ARCHIVED"]);
  });

  test("la qualification d'une opportunité expose les champs C5b", () => {
    const action = configurationAction("qualifier_opportunite", expressionProposee);

    expect(action.api).toBe("creerOpportunite");
    expect(action.typeSource).toBe("EXPRESSION");
    expect(action.champs.map((champ) => champ.nom)).toEqual([
      "titre", "description", "valeur_potentielle", "probabilite", "impact",
      "horizon", "criteres", "preuves", "confiance", "type_opportunite",
    ]);
    expect(action.champs.find((champ) => champ.nom === "titre").requis).toBe(true);
    expect(action.champs.find((champ) => champ.nom === "type_opportunite").options)
      .toContain("AUTOMATION");
  });

  test("la qualification d'un risque expose le même contrat", () => {
    const action = configurationAction("qualifier_risque", expressionProposee);

    expect(action.api).toBe("creerRisque");
    expect(action.typeSource).toBe("EXPRESSION");
    expect(action.champs.map((champ) => champ.nom)).toEqual([
      "titre", "description", "valeur_potentielle", "probabilite", "impact",
      "horizon", "criteres", "preuves", "confiance", "type_risque", "severite",
    ]);
    expect(action.champs.find((champ) => champ.nom === "type_risque").options)
      .toContain("FOURNISSEUR");
    expect(action.champs.find((champ) => champ.nom === "severite").options)
      .toEqual(["FAIBLE", "MOYENNE", "HAUTE", "CRITIQUE"]);
  });

  test("le changement de statut ne propose que les transitions autorisées", () => {
    const action = configurationAction("changer_statut_opportunite", opportunite);

    expect(action.api).toBe("changerStatutOpportunite");
    expect(action.typeSource).toBe("OPPORTUNITY");
    expect(action.champs.find((champ) => champ.nom === "statut").type).toBe("select");
    expect(action.champs.find((champ) => champ.nom === "statut").options)
      .toEqual(["MATURING", "QUALIFIED", "REJECTED", "DORMANT"]);
    expect(configurationAction("changer_statut_risque", risque).api)
      .toBe("changerStatutRisque");
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

  test("tranche avec un choix et un motif optionnel, sans acteur envoyé", () => {
    expect(construireCorps("trancher_decision", {}, decisionProposee).erreur).toContain("choix");
    expect(construireCorps("trancher_decision", { choix: "Autre" }, decisionProposee).erreur)
      .toContain("options");
    const resultat = construireCorps("trancher_decision", {
      choix: "Automatiser",
      motif: " Réduire le délai ",
    }, decisionProposee);
    expect(resultat.corps).toEqual({
      choix: "Automatiser",
      motif: "Réduire le délai",
    });
    expect(resultat.corps).not.toHaveProperty("acteur");
  });

  test("exprime une situation avec les champs C5a, sans statut client", () => {
    expect(construireCorps("creer_expression", {}).erreur).toContain("formulation");
    expect(construireCorps("creer_expression", { formulation: "   " }).erreur)
      .toContain("formulation");

    const resultat = construireCorps("creer_expression", {
      formulation: "  Automatiser la ressaisie  ",
      type_expression: "opportunite",
      canal: "  entretien  ",
      auteur: "  Alice  ",
      inconnues: "volume réel\ncharge de fin de mois",
      confiance: "0,8",
      statut: "CONFIRMED",
    });
    expect(resultat.corps).toEqual({
      formulation: "Automatiser la ressaisie",
      type_expression: "OPPORTUNITE",
      canal: "entretien",
      auteur: "Alice",
      inconnues: ["volume réel", "charge de fin de mois"],
      confiance: 0.8,
    });
    expect(resultat.corps).not.toHaveProperty("statut");
  });

  test("refuse un type d'expression inconnu et une confiance hors bornes", () => {
    expect(construireCorps("creer_expression", {
      formulation: "Valide", type_expression: "MAGIQUE",
    }).erreur).toContain("type d'expression");
    expect(construireCorps("creer_expression", {
      formulation: "Valide", confiance: "1.2",
    }).erreur).toContain("confiance");
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
      preuves: "preuve-1, preuve-2",
    }).corps).toEqual({
      mesure: { metrique: "p95", valeur: 180.5, unite: "ms", source: "suivi-cartes" },
      valeur_attendue: 200,
      periode: "2026-10",
      interpretation: "La latence baisse",
      preuves: ["preuve-1", "preuve-2"],
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

  test("crée une situation racine avec au moins un texte et convertit twin_ids", () => {
    expect(construireCorps("creer_situation", {}).erreur)
      .toContain("titre, une description ou un résumé");
    expect(construireCorps("creer_situation", { titre: "   ", description: "\n" }).erreur)
      .toContain("titre, une description ou un résumé");

    const resultat = construireCorps("creer_situation", {
      titre: "  Latence des paiements  ",
      description: "  Les paiements ralentissent depuis R-118.  ",
      resume: "  Trois flux concernés.  ",
      priorite: "  haute  ",
      twin_ids: " app-paiement, process-controle ,, ",
      mode: "OBSERVED",
    });
    expect(resultat.corps).toEqual({
      titre: "Latence des paiements",
      description: "Les paiements ralentissent depuis R-118.",
      resume: "Trois flux concernés.",
      priorite: "haute",
      twin_ids: ["app-paiement", "process-controle"],
      mode: "OBSERVED",
    });
  });

  test("accepte une situation décrite sans titre, comme le backend", () => {
    expect(construireCorps("creer_situation", {
      titre: "",
      description: "  Un phénomène observé.  ",
    }).corps).toEqual({ description: "Un phénomène observé." });
  });

  test("crée un scénario depuis une investigation avec métriques et listes CSV", () => {
    expect(construireCorps("creer_scenario", {}, investigation).erreur).toContain("titre");
    const resultat = construireCorps("creer_scenario", {
      titre: "  Automatiser la pièce  ",
      description: "  Supprimer la ressaisie  ",
      hypothesis_ids: " hyp-1, hyp-2 ,, ",
      actions: " Automatiser \n Contrôler ",
      valeur_estimee: "12000",
      cout_estime: "4500,5",
      delai_jours: "30",
      risque: "0,2",
      complexite: "0,4",
      confiance: "0,8",
      dependances: "api-paiement, equipe-cartes",
      impacts: "client=baisse, risque=mitige",
      preuves: "preuve-1, preuve-2",
      reversibilite: "PARTIELLE",
      statut: "PROPOSED",
    }, investigation);

    expect(resultat.corps).toEqual({
      titre: "Automatiser la pièce",
      description: "Supprimer la ressaisie",
      investigation_id: "inv-1",
      hypothesis_ids: ["hyp-1", "hyp-2"],
      actions: ["Automatiser", "Contrôler"],
      valeur_estimee: 12000,
      cout_estime: 4500.5,
      delai_jours: 30,
      risque: 0.2,
      complexite: 0.4,
      confiance: 0.8,
      dependances: ["api-paiement", "equipe-cartes"],
      impacts: { client: "baisse", risque: "mitige" },
      preuves: ["preuve-1", "preuve-2"],
      reversibilite: "PARTIELLE",
      statut: "PROPOSED",
    });
  });

  test("crée un scénario depuis une décision et valide les bornes", () => {
    expect(construireCorps("creer_scenario", { titre: "Réorganiser" }, decisionProposee).corps)
      .toEqual({ titre: "Réorganiser", decision_id: "dec-1" });
    expect(construireCorps("creer_scenario", {
      titre: "Scénario", valeur_estimee: "beaucoup",
    }, investigation).erreur).toContain("valeur");
    expect(construireCorps("creer_scenario", {
      titre: "Scénario", cout_estime: "-1",
    }, investigation).erreur).toContain("coût");
    expect(construireCorps("creer_scenario", {
      titre: "Scénario", delai_jours: "1.5",
    }, investigation).erreur).toContain("délai");
    expect(construireCorps("creer_scenario", {
      titre: "Scénario", risque: "1.2",
    }, investigation).erreur).toContain("risque");
    expect(construireCorps("creer_scenario", {
      titre: "Scénario", complexite: "1.2",
    }, investigation).erreur).toContain("complexité");
    expect(construireCorps("creer_scenario", {
      titre: "Scénario", confiance: "1.2",
    }, investigation).erreur).toContain("confiance");
    expect(construireCorps("creer_scenario", {
      titre: "Scénario", impacts: "client",
    }, investigation).erreur).toContain("impact");
    expect(construireCorps("creer_scenario", {
      titre: "Scénario", reversibilite: "PEUT_ETRE",
    }, investigation).erreur).toContain("réversibilité");
    expect(construireCorps("creer_scenario", {
      titre: "Scénario", statut: "INCONNU",
    }, investigation).erreur).toContain("statut");
  });

  test("refuse un scénario sans investigation ni décision", () => {
    expect(construireCorps("creer_scenario", { titre: "Sans parent" }, {}).erreur)
      .toContain("investigation ou une décision");
  });

  test("qualifie une opportunité avec les champs C5b, sans statut ni lien client", () => {
    expect(construireCorps("qualifier_opportunite", {}).erreur)
      .toContain("titre de l'opportunité");

    const resultat = construireCorps("qualifier_opportunite", {
      titre: "  Automatiser la ressaisie  ",
      description: "  Supprimer la double saisie.  ",
      valeur_potentielle: "12000",
      probabilite: "0,7",
      impact: "Deux ETP libérés",
      horizon: " 90 jours ",
      criteres: "faisable\nmesurable",
      preuves: "preuve-1, preuve-2",
      confiance: "0,6",
      type_opportunite: "automation",
      type_risque: "FOURNISSEUR",
      severite: "HAUTE",
      statut: "CONFIRMED",
    });

    expect(resultat.corps).toEqual({
      titre: "Automatiser la ressaisie",
      description: "Supprimer la double saisie.",
      valeur_potentielle: 12000,
      probabilite: 0.7,
      impact: "Deux ETP libérés",
      horizon: "90 jours",
      criteres: ["faisable", "mesurable"],
      preuves: ["preuve-1", "preuve-2"],
      confiance: 0.6,
      type_opportunite: "AUTOMATION",
    });
    expect(resultat.corps).not.toHaveProperty("statut");
    expect(resultat.corps).not.toHaveProperty("expression_id");
    expect(resultat.corps).not.toHaveProperty("situation_id");
    expect(resultat.corps).not.toHaveProperty("type_risque");
    expect(resultat.corps).not.toHaveProperty("severite");
  });

  test("qualifie un risque et valide les bornes", () => {
    const resultat = construireCorps("qualifier_risque", {
      titre: "Dépendance",
      probabilite: "0,4",
      valeur_potentielle: "50000",
      impact: "Arrêt des paiements",
      horizon: "6 mois",
      criteres: "criticité, réversibilité",
      type_risque: "fournisseur",
      severite: "haute",
      type_opportunite: "AUTOMATION",
    });
    expect(resultat.corps).toEqual({
      titre: "Dépendance",
      probabilite: 0.4,
      valeur_potentielle: 50000,
      impact: "Arrêt des paiements",
      horizon: "6 mois",
      criteres: ["criticité", "réversibilité"],
      type_risque: "FOURNISSEUR",
      severite: "HAUTE",
    });
    expect(resultat.corps).not.toHaveProperty("type_opportunite");

    for (const champs of [
      { probabilite: "1.2" },
      { confiance: "-0.1" },
      { valeur_potentielle: "-1" },
      { type_risque: "MAGIQUE" },
      { severite: "MAGIQUE" },
    ]) {
      expect(construireCorps("qualifier_risque", {
        titre: "Risque", ...champs,
      }).erreur).toBeTruthy();
    }
    expect(construireCorps("qualifier_opportunite", {
      titre: "Opportunité", type_opportunite: "MAGIQUE",
    }).erreur).toContain("type d'opportunité");
  });

  test("change un statut seulement vers une transition autorisée", () => {
    expect(construireCorps("changer_statut_opportunite", {}, opportunite).erreur)
      .toContain("statut");
    expect(construireCorps("changer_statut_opportunite", {
      statut: "LEARNED",
    }, opportunite).erreur).toContain("transition");

    expect(construireCorps("changer_statut_opportunite", {
      statut: "QUALIFIED",
      motif: "  Preuves suffisantes  ",
      preuves: "preuve-2, preuve-3",
    }, opportunite).corps).toEqual({
      statut: "QUALIFIED",
      motif: "Preuves suffisantes",
      preuves: ["preuve-2", "preuve-3"],
    });

    expect(construireCorps("changer_statut_risque", {
      statut: "MATURING",
    }, risque).corps).toEqual({ statut: "MATURING" });
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

  test("explique les 400 et 503 sans détail exploitable", () => {
    expect(messageErreurTransition({ response: { status: 400 } }))
      .toBe("Les données envoyées sont invalides. Vérifiez le formulaire.");
    expect(messageErreurTransition({ response: { status: 503 } }))
      .toContain("indisponible");
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

describe("detailSourceApresTransition", () => {
  const ancienDetail = {
    chaine: [situation, investigation, decisionProposee],
    historique: [{ version: 3, maj_le: "2026-10-30T10:00:00Z" }],
  };

  test("conserve l'ancienne chaîne si la réponse n'en contient pas la source", () => {
    for (const chaine of [[], [situation, investigation], null, undefined]) {
      const resultat = detailSourceApresTransition({
        identifiant: "dec-1",
        nouvelObjet: decisionTranchee,
        nouvelleChaine: chaine,
        nouvelHistorique: [{ version: 9 }],
        ancienDetail,
      });
      expect(resultat.source.id).toBe("dec-1");
      expect(resultat.chaine).toEqual(ancienDetail.chaine);
      expect(resultat.historique).toEqual([{ version: 9 }]);
    }
  });

  test("ne fabrique pas de source ni de chaîne quand l'enfant n'a pas de chaîne source", () => {
    const enfant = { id: "ini-2", type: "INITIATIVE", titre: "Initiative" };
    for (const chaine of [[], [situation, investigation], null, undefined]) {
      const resultat = detailSourceApresTransition({
        identifiant: "dec-1",
        nouvelObjet: enfant,
        nouvelleChaine: chaine,
        nouvelHistorique: [{ version: 1 }],
        ancienDetail,
      });
      expect(resultat.source).toBeNull();
      expect(resultat.chaine).toEqual(ancienDetail.chaine);
      expect(resultat.historique).toEqual(ancienDetail.historique);
    }
  });

  test("coupe la chaîne à la source et conserve son historique quand un enfant est créé", () => {
    const enfant = { id: "ini-2", type: "INITIATIVE", titre: "Initiative" };
    const source = {
      ...decisionTranchee,
      donnees: { ...decisionTranchee.donnees, initiative_id: "ini-2" },
    };
    const resultat = detailSourceApresTransition({
      identifiant: "dec-1",
      nouvelObjet: enfant,
      nouvelleChaine: [situation, investigation, source, enfant],
      nouvelHistorique: [{ version: 1 }],
      ancienDetail,
    });
    expect(resultat.source).toEqual(source);
    expect(resultat.chaine).toEqual([situation, investigation, source]);
    expect(resultat.historique).toEqual(ancienDetail.historique);
  });
});
