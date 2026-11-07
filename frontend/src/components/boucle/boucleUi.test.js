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
  titreObjet,
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

  test("une décision proposée se tranche", () => {
    expect(actionsPourObjet(decisionProposee).map((action) => action.id)).toEqual(["trancher_decision"]);
  });

  test("une décision tranchée lance une initiative", () => {
    expect(actionsPourObjet(decisionTranchee).map((action) => action.id)).toEqual(["lancer_initiative"]);
  });

  test("une décision déjà reliée à une initiative ne propose plus de la lancer", () => {
    expect(actionsPourObjet({
      ...decisionTranchee,
      donnees: { ...decisionTranchee.donnees, initiative_id: "ini-1" },
    })).toEqual([]);
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
