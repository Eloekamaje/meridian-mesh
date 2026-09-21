// Instantané du monde produit (GET /api/mesh, 06/2026) : toile de fond de la
// démonstration Polaris — le récit se joue DANS le vrai Atlas (7 domaines, 35 jumeaux),
// pas sur un monde réduit. Aucun appel réseau en mode kiosque : c'est une fixture locale.
export const MONDE_JUMEAUX = [
  {
    "id": "paiements",
    "nom": "Paiements",
    "domaine": "Paiement",
    "statut": "actif",
    "position": {
      "x": 792,
      "y": 365
    },
    "mission": "Orchestre les transactions du parcours de paiement",
    "sante": "dégradé",
    "couverture": 92,
    "fraicheur": "il y a 3 min",
    "strates": {
      "identite": 100,
      "comportement": 94,
      "relations": 82,
      "trajectoire": 90,
      "memoire": 88
    },
    "fraicheur_etat": "a_jour",
    "capacites": [
      "Initier des paiements",
      "Contrôler et valider",
      "Gérer les devises",
      "Vérifier la conformité",
      "Rapprocher et lettrer"
    ],
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": true,
      "incidents": true,
      "documentation": true
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      },
      {
        "cle": "incidents",
        "nom": "ServiceNow",
        "statut": "prete"
      },
      {
        "cle": "documentation",
        "nom": "Confluence",
        "statut": "prete"
      },
      {
        "cle": "evenements",
        "nom": "Splunk",
        "statut": "secret_expire"
      }
    ],
    "proprietaire": "Équipe Checkout — L. Marchand",
    "autonomie": "supervisé",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "facturation",
    "nom": "Facturation",
    "domaine": "Paiement",
    "statut": "actif",
    "position": {
      "x": 500,
      "y": 460
    },
    "mission": "Produit les factures et pilote la clôture quotidienne",
    "sante": "nominal",
    "couverture": 81,
    "fraicheur": "il y a 12 min",
    "strates": {
      "identite": 96,
      "comportement": 78,
      "relations": 70,
      "trajectoire": 85,
      "memoire": 76
    },
    "fraicheur_etat": "a_jour",
    "capacites": [
      "Émettre les factures",
      "Piloter la clôture",
      "Gérer les avoirs"
    ],
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": true,
      "incidents": false,
      "documentation": true
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      },
      {
        "cle": "documentation",
        "nom": "Confluence",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Finance — A. Keita",
    "autonomie": "supervisé",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "comptes",
    "nom": "Comptes",
    "domaine": "Client",
    "statut": "actif",
    "position": {
      "x": 140,
      "y": 240
    },
    "mission": "Gère les comptes clients, leurs soldes et leur historique",
    "sante": "nominal",
    "couverture": 88,
    "fraicheur": "il y a 1 min",
    "strates": {
      "identite": 100,
      "comportement": 90,
      "relations": 80,
      "trajectoire": 88,
      "memoire": 84
    },
    "fraicheur_etat": "a_jour",
    "capacites": [
      "Tenir les soldes",
      "Journaliser les mouvements"
    ],
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": true,
      "incidents": true,
      "documentation": true
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      },
      {
        "cle": "incidents",
        "nom": "ServiceNow",
        "statut": "prete"
      },
      {
        "cle": "documentation",
        "nom": "Confluence",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Client — M. Diallo",
    "autonomie": "supervisé",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "identite",
    "nom": "Identité",
    "domaine": "Client",
    "statut": "actif",
    "position": {
      "x": 180,
      "y": 420
    },
    "mission": "Authentifie les clients et gère leurs sessions",
    "sante": "nominal",
    "couverture": 76,
    "fraicheur": "il y a 25 min",
    "strates": {
      "identite": 92,
      "comportement": 80,
      "relations": 64,
      "trajectoire": 78,
      "memoire": 66
    },
    "fraicheur_etat": "partiel",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": true,
      "incidents": false,
      "documentation": false
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Client — M. Diallo",
    "autonomie": "restreint",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "fraude",
    "nom": "Fraude",
    "domaine": "Risque",
    "statut": "actif",
    "position": {
      "x": 1000,
      "y": 220
    },
    "mission": "Évalue le risque de fraude en temps réel sur chaque transaction",
    "sante": "dégradé",
    "couverture": 84,
    "fraicheur": "il y a 2 min",
    "strates": {
      "identite": 96,
      "comportement": 88,
      "relations": 76,
      "trajectoire": 82,
      "memoire": 72
    },
    "fraicheur_etat": "a_jour",
    "capacites": [
      "Scorer les transactions",
      "Bloquer les parcours à risque"
    ],
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": true,
      "incidents": true,
      "documentation": false
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      },
      {
        "cle": "incidents",
        "nom": "ServiceNow",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Risque — S. Petit",
    "autonomie": "supervisé",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "conformite",
    "nom": "Conformité",
    "domaine": "Risque",
    "statut": "en construction",
    "position": {
      "x": 1080,
      "y": 380
    },
    "mission": "Vérifie les obligations réglementaires des flux financiers",
    "sante": "inconnu",
    "couverture": 43,
    "fraicheur": "il y a 2 h",
    "strates": {
      "identite": 58,
      "comportement": 30,
      "relations": 22,
      "trajectoire": 44,
      "memoire": 35
    },
    "fraicheur_etat": "retard",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": false,
      "observabilite": false,
      "incidents": true,
      "documentation": false
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "incidents",
        "nom": "ServiceNow",
        "statut": "prete"
      },
      {
        "cle": "evenements",
        "nom": "Splunk",
        "statut": "en_retard"
      }
    ],
    "proprietaire": "Équipe Risque — S. Petit",
    "autonomie": "aucune",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "support",
    "nom": "Support",
    "domaine": "Support",
    "statut": "actif",
    "position": {
      "x": 990,
      "y": 570
    },
    "mission": "Gère les demandes, tickets et macros de remboursement clients",
    "sante": "nominal",
    "couverture": 62,
    "fraicheur": "il y a 1 h",
    "strates": {
      "identite": 80,
      "comportement": 66,
      "relations": 48,
      "trajectoire": 62,
      "memoire": 55
    },
    "fraicheur_etat": "partiel",
    "capacites": [
      "Qualifier les demandes",
      "Escalader les incidents"
    ],
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": false,
      "observabilite": true,
      "incidents": true,
      "documentation": false
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      },
      {
        "cle": "incidents",
        "nom": "ServiceNow",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Care — J. Morel",
    "autonomie": "supervisé",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "notifications",
    "nom": "Notifications",
    "domaine": "Support",
    "statut": "actif",
    "position": {
      "x": 1090,
      "y": 690
    },
    "mission": "Envoie les alertes et messages aux clients",
    "sante": "nominal",
    "couverture": 71,
    "fraicheur": "il y a 18 min",
    "strates": {
      "identite": 88,
      "comportement": 74,
      "relations": 56,
      "trajectoire": 70,
      "memoire": 62
    },
    "fraicheur_etat": "partiel",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": true,
      "incidents": false,
      "documentation": false
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Care — J. Morel",
    "autonomie": "restreint",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "commandes",
    "nom": "Commandes",
    "domaine": "Opérations",
    "statut": "actif",
    "position": {
      "x": 140,
      "y": 630
    },
    "mission": "Suit le cycle de vie des commandes de bout en bout",
    "sante": "nominal",
    "couverture": 79,
    "fraicheur": "il y a 7 min",
    "strates": {
      "identite": 94,
      "comportement": 82,
      "relations": 68,
      "trajectoire": 80,
      "memoire": 74
    },
    "fraicheur_etat": "a_jour",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": true,
      "incidents": true,
      "documentation": false
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      },
      {
        "cle": "incidents",
        "nom": "ServiceNow",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Ops — R. Fabre",
    "autonomie": "supervisé",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "logistique",
    "nom": "Logistique",
    "domaine": "Opérations",
    "statut": "observation",
    "position": {
      "x": 240,
      "y": 740
    },
    "mission": "Pilote la préparation et l'expédition des commandes",
    "sante": "inconnu",
    "couverture": 51,
    "fraicheur": "il y a 3 h",
    "strates": {
      "identite": 70,
      "comportement": 46,
      "relations": 30,
      "trajectoire": 52,
      "memoire": 40
    },
    "fraicheur_etat": "retard",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": false,
      "incidents": false,
      "documentation": false
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "a_configurer"
      }
    ],
    "proprietaire": "Équipe Ops — R. Fabre",
    "autonomie": "aucune",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "portail-web",
    "nom": "Portail Web",
    "domaine": "Distribution",
    "statut": "actif",
    "position": {
      "x": 560,
      "y": 30
    },
    "mission": "Expose le parcours d'achat aux clients web",
    "sante": "nominal",
    "couverture": 68,
    "fraicheur": "il y a 33 min",
    "strates": {
      "identite": 86,
      "comportement": 72,
      "relations": 50,
      "trajectoire": 66,
      "memoire": 58
    },
    "fraicheur_etat": "partiel",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": false,
      "observabilite": true,
      "incidents": false,
      "documentation": true
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      },
      {
        "cle": "documentation",
        "nom": "Confluence",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Digital — C. Nguyen",
    "autonomie": "restreint",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "api-gateway",
    "nom": "API Gateway",
    "domaine": "Distribution",
    "statut": "actif",
    "position": {
      "x": 700,
      "y": 35
    },
    "mission": "Point d'entrée unique de toutes les API du SI",
    "sante": "nominal",
    "couverture": 90,
    "fraicheur": "il y a 4 min",
    "strates": {
      "identite": 98,
      "comportement": 92,
      "relations": 84,
      "trajectoire": 86,
      "memoire": 82
    },
    "fraicheur_etat": "a_jour",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": true,
      "incidents": true,
      "documentation": true
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      },
      {
        "cle": "incidents",
        "nom": "ServiceNow",
        "statut": "prete"
      },
      {
        "cle": "documentation",
        "nom": "Confluence",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Plateforme — D. Roy",
    "autonomie": "supervisé",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "prelevements",
    "nom": "Prélèvements",
    "domaine": "Paiement",
    "statut": "actif",
    "position": {
      "x": 750,
      "y": 250
    },
    "mission": "Exécute les prélèvements SEPA et leur rapprochement",
    "sante": "nominal",
    "couverture": 77,
    "fraicheur": "il y a 9 min",
    "strates": {
      "identite": 94,
      "comportement": 80,
      "relations": 66,
      "trajectoire": 78,
      "memoire": 70
    },
    "fraicheur_etat": "a_jour",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": true,
      "incidents": false,
      "documentation": true
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      },
      {
        "cle": "documentation",
        "nom": "Confluence",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Finance — A. Keita",
    "autonomie": "supervisé",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "remboursements",
    "nom": "Remboursements",
    "domaine": "Paiement",
    "statut": "actif",
    "position": {
      "x": 730,
      "y": 470
    },
    "mission": "Ordonne les remboursements et les avoirs clients",
    "sante": "nominal",
    "couverture": 69,
    "fraicheur": "il y a 21 min",
    "strates": {
      "identite": 88,
      "comportement": 70,
      "relations": 58,
      "trajectoire": 72,
      "memoire": 62
    },
    "fraicheur_etat": "partiel",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": false,
      "incidents": true,
      "documentation": false
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "incidents",
        "nom": "ServiceNow",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Checkout — L. Marchand",
    "autonomie": "supervisé",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "preferences",
    "nom": "Préférences",
    "domaine": "Client",
    "statut": "actif",
    "position": {
      "x": 290,
      "y": 320
    },
    "mission": "Centralise préférences et consentements marketing",
    "sante": "nominal",
    "couverture": 64,
    "fraicheur": "il y a 40 min",
    "strates": {
      "identite": 84,
      "comportement": 62,
      "relations": 46,
      "trajectoire": 60,
      "memoire": 52
    },
    "fraicheur_etat": "partiel",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": false,
      "incidents": false,
      "documentation": true
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "documentation",
        "nom": "Confluence",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Client — M. Diallo",
    "autonomie": "restreint",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "fidelite",
    "nom": "Fidélité",
    "domaine": "Client",
    "statut": "actif",
    "position": {
      "x": 110,
      "y": 330
    },
    "mission": "Pilote les points et statuts du programme de fidélité",
    "sante": "nominal",
    "couverture": 73,
    "fraicheur": "il y a 14 min",
    "strates": {
      "identite": 90,
      "comportement": 74,
      "relations": 60,
      "trajectoire": 70,
      "memoire": 64
    },
    "fraicheur_etat": "a_jour",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": true,
      "incidents": false,
      "documentation": false
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Client — M. Diallo",
    "autonomie": "supervisé",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "scoring",
    "nom": "Scoring Crédit",
    "domaine": "Risque",
    "statut": "actif",
    "position": {
      "x": 1190,
      "y": 210
    },
    "mission": "Calcule les scores de risque crédit en continu",
    "sante": "nominal",
    "couverture": 81,
    "fraicheur": "il y a 6 min",
    "strates": {
      "identite": 96,
      "comportement": 84,
      "relations": 70,
      "trajectoire": 80,
      "memoire": 74
    },
    "fraicheur_etat": "a_jour",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": true,
      "incidents": false,
      "documentation": true
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      },
      {
        "cle": "documentation",
        "nom": "Confluence",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Risque — S. Petit",
    "autonomie": "supervisé",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "sanctions",
    "nom": "Filtrage Sanctions",
    "domaine": "Risque",
    "statut": "en construction",
    "position": {
      "x": 1200,
      "y": 350
    },
    "mission": "Filtre les bénéficiaires contre les listes de sanctions",
    "sante": "inconnu",
    "couverture": 38,
    "fraicheur": "il y a 5 h",
    "strates": {
      "identite": 52,
      "comportement": 26,
      "relations": 18,
      "trajectoire": 38,
      "memoire": 30
    },
    "fraicheur_etat": "retard",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": false,
      "observabilite": false,
      "incidents": false,
      "documentation": false
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Risque — S. Petit",
    "autonomie": "aucune",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "stocks",
    "nom": "Stocks",
    "domaine": "Opérations",
    "statut": "actif",
    "position": {
      "x": 330,
      "y": 600
    },
    "mission": "Maintient l'état des stocks en temps quasi réel",
    "sante": "nominal",
    "couverture": 75,
    "fraicheur": "il y a 4 min",
    "strates": {
      "identite": 92,
      "comportement": 78,
      "relations": 62,
      "trajectoire": 74,
      "memoire": 68
    },
    "fraicheur_etat": "a_jour",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": true,
      "incidents": true,
      "documentation": false
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      },
      {
        "cle": "incidents",
        "nom": "ServiceNow",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Ops — R. Fabre",
    "autonomie": "supervisé",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "transporteurs",
    "nom": "Transporteurs",
    "domaine": "Opérations",
    "statut": "observation",
    "position": {
      "x": 110,
      "y": 770
    },
    "mission": "Suit les tournées et les preuves de livraison",
    "sante": "inconnu",
    "couverture": 47,
    "fraicheur": "il y a 2 h",
    "strates": {
      "identite": 66,
      "comportement": 42,
      "relations": 28,
      "trajectoire": 48,
      "memoire": 36
    },
    "fraicheur_etat": "retard",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": false,
      "observabilite": true,
      "incidents": false,
      "documentation": false
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Ops — R. Fabre",
    "autonomie": "aucune",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "base-connaissances",
    "nom": "Base de connaissances",
    "domaine": "Support",
    "statut": "actif",
    "position": {
      "x": 1190,
      "y": 610
    },
    "mission": "Publie les articles d'aide et les macros de réponse",
    "sante": "nominal",
    "couverture": 58,
    "fraicheur": "il y a 1 h",
    "strates": {
      "identite": 78,
      "comportement": 60,
      "relations": 44,
      "trajectoire": 58,
      "memoire": 50
    },
    "fraicheur_etat": "partiel",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": false,
      "observabilite": false,
      "incidents": false,
      "documentation": true
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "documentation",
        "nom": "Confluence",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Care — J. Morel",
    "autonomie": "restreint",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "escalades",
    "nom": "Escalades",
    "domaine": "Support",
    "statut": "actif",
    "position": {
      "x": 1160,
      "y": 750
    },
    "mission": "Route les tickets critiques vers les experts",
    "sante": "nominal",
    "couverture": 66,
    "fraicheur": "il y a 26 min",
    "strates": {
      "identite": 86,
      "comportement": 68,
      "relations": 52,
      "trajectoire": 66,
      "memoire": 58
    },
    "fraicheur_etat": "a_jour",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": true,
      "incidents": true,
      "documentation": false
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      },
      {
        "cle": "incidents",
        "nom": "ServiceNow",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Care — J. Morel",
    "autonomie": "supervisé",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "catalogue",
    "nom": "Catalogue",
    "domaine": "Distribution",
    "statut": "actif",
    "position": {
      "x": 680,
      "y": 125
    },
    "mission": "Expose le référentiel produits et les prix",
    "sante": "nominal",
    "couverture": 83,
    "fraicheur": "il y a 8 min",
    "strates": {
      "identite": 94,
      "comportement": 80,
      "relations": 64,
      "trajectoire": 76,
      "memoire": 70
    },
    "fraicheur_etat": "a_jour",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": true,
      "incidents": false,
      "documentation": true
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      },
      {
        "cle": "documentation",
        "nom": "Confluence",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Digital — C. Nguyen",
    "autonomie": "supervisé",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "recommandations",
    "nom": "Recommandations",
    "domaine": "Distribution",
    "statut": "observation",
    "position": {
      "x": 520,
      "y": 120
    },
    "mission": "Personnalise les suggestions du parcours d'achat",
    "sante": "inconnu",
    "couverture": 55,
    "fraicheur": "il y a 2 h",
    "strates": {
      "identite": 72,
      "comportement": 54,
      "relations": 38,
      "trajectoire": 56,
      "memoire": 46
    },
    "fraicheur_etat": "partiel",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": false,
      "incidents": false,
      "documentation": false
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Digital — C. Nguyen",
    "autonomie": "restreint",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "communications",
    "nom": "Communications",
    "domaine": "Client",
    "statut": "actif",
    "position": {
      "x": 350,
      "y": 400
    },
    "mission": "Orchestre emails, SMS et notifications clients",
    "sante": "nominal",
    "couverture": 79,
    "fraicheur": "il y a 7 min",
    "strates": {
      "identite": 92,
      "comportement": 76,
      "relations": 58,
      "trajectoire": 72,
      "memoire": 66
    },
    "fraicheur_etat": "a_jour",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": true,
      "incidents": false,
      "documentation": false
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Client — M. Diallo",
    "autonomie": "supervisé",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "consentements",
    "nom": "Consentements",
    "domaine": "Client",
    "statut": "actif",
    "position": {
      "x": 240,
      "y": 445
    },
    "mission": "Enregistre les consentements RGPD et leur historique",
    "sante": "nominal",
    "couverture": 71,
    "fraicheur": "il y a 30 min",
    "strates": {
      "identite": 88,
      "comportement": 68,
      "relations": 50,
      "trajectoire": 64,
      "memoire": 58
    },
    "fraicheur_etat": "a_jour",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": false,
      "incidents": true,
      "documentation": true
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "incidents",
        "nom": "ServiceNow",
        "statut": "prete"
      },
      {
        "cle": "documentation",
        "nom": "Confluence",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Client — M. Diallo",
    "autonomie": "restreint",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "onboarding",
    "nom": "Onboarding",
    "domaine": "Client",
    "statut": "actif",
    "position": {
      "x": 75,
      "y": 250
    },
    "mission": "Guide la création de compte et la vérification d'identité",
    "sante": "nominal",
    "couverture": 66,
    "fraicheur": "il y a 18 min",
    "strates": {
      "identite": 86,
      "comportement": 66,
      "relations": 48,
      "trajectoire": 62,
      "memoire": 54
    },
    "fraicheur_etat": "partiel",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": true,
      "incidents": false,
      "documentation": false
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Client — N. Bara",
    "autonomie": "supervisé",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "segments",
    "nom": "Segments",
    "domaine": "Client",
    "statut": "observation",
    "position": {
      "x": 340,
      "y": 235
    },
    "mission": "Calcule les segments marketing à partir des comportements",
    "sante": "inconnu",
    "couverture": 49,
    "fraicheur": "il y a 3 h",
    "strates": {
      "identite": 68,
      "comportement": 46,
      "relations": 30,
      "trajectoire": 50,
      "memoire": 40
    },
    "fraicheur_etat": "retard",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": false,
      "incidents": false,
      "documentation": false
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Data — C. Nguyen",
    "autonomie": "aucune",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "litiges",
    "nom": "Litiges",
    "domaine": "Paiement",
    "statut": "actif",
    "position": {
      "x": 810,
      "y": 350
    },
    "mission": "Instruit les chargebacks et contestations de paiement",
    "sante": "nominal",
    "couverture": 74,
    "fraicheur": "il y a 12 min",
    "strates": {
      "identite": 90,
      "comportement": 72,
      "relations": 54,
      "trajectoire": 68,
      "memoire": 60
    },
    "fraicheur_etat": "a_jour",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": true,
      "incidents": true,
      "documentation": false
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      },
      {
        "cle": "incidents",
        "nom": "ServiceNow",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Finance — A. Keita",
    "autonomie": "supervisé",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "tokens",
    "nom": "Tokenisation",
    "domaine": "Paiement",
    "statut": "actif",
    "position": {
      "x": 555,
      "y": 370
    },
    "mission": "Remplace les PAN par des jetons irréversibles",
    "sante": "nominal",
    "couverture": 85,
    "fraicheur": "il y a 3 min",
    "strates": {
      "identite": 95,
      "comportement": 82,
      "relations": 68,
      "trajectoire": 80,
      "memoire": 74
    },
    "fraicheur_etat": "a_jour",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": true,
      "incidents": false,
      "documentation": true
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      },
      {
        "cle": "documentation",
        "nom": "Confluence",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Plateforme — D. Roy",
    "autonomie": "restreint",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "strong-auth",
    "nom": "Authentification forte",
    "domaine": "Paiement",
    "statut": "actif",
    "position": {
      "x": 610,
      "y": 520
    },
    "mission": "Applique le 3-D Secure selon le risque de la transaction",
    "sante": "nominal",
    "couverture": 68,
    "fraicheur": "il y a 15 min",
    "strates": {
      "identite": 87,
      "comportement": 66,
      "relations": 50,
      "trajectoire": 64,
      "memoire": 56
    },
    "fraicheur_etat": "partiel",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": false,
      "observabilite": true,
      "incidents": true,
      "documentation": false
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      },
      {
        "cle": "incidents",
        "nom": "ServiceNow",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Checkout — L. Marchand",
    "autonomie": "supervisé",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "recherche",
    "nom": "Recherche",
    "domaine": "Distribution",
    "statut": "actif",
    "position": {
      "x": 840,
      "y": 30
    },
    "mission": "Indexe le catalogue et répond aux requêtes de recherche",
    "sante": "nominal",
    "couverture": 88,
    "fraicheur": "il y a 2 min",
    "strates": {
      "identite": 96,
      "comportement": 84,
      "relations": 70,
      "trajectoire": 82,
      "memoire": 76
    },
    "fraicheur_etat": "a_jour",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": true,
      "incidents": false,
      "documentation": true
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      },
      {
        "cle": "documentation",
        "nom": "Confluence",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Digital — C. Nguyen",
    "autonomie": "supervisé",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "promotions",
    "nom": "Promotions",
    "domaine": "Distribution",
    "statut": "actif",
    "position": {
      "x": 830,
      "y": 120
    },
    "mission": "Calcule les prix promo et leur éligibilité panier",
    "sante": "nominal",
    "couverture": 70,
    "fraicheur": "il y a 25 min",
    "strates": {
      "identite": 89,
      "comportement": 68,
      "relations": 52,
      "trajectoire": 66,
      "memoire": 58
    },
    "fraicheur_etat": "partiel",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": false,
      "incidents": false,
      "documentation": false
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Digital — C. Nguyen",
    "autonomie": "supervisé",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "seo-pages",
    "nom": "Pages SEO",
    "domaine": "Distribution",
    "statut": "observation",
    "position": {
      "x": 470,
      "y": 25
    },
    "mission": "Génère les pages statiques optimisées référencement",
    "sante": "inconnu",
    "couverture": 44,
    "fraicheur": "il y a 6 h",
    "strates": {
      "identite": 60,
      "comportement": 38,
      "relations": 24,
      "trajectoire": 44,
      "memoire": 34
    },
    "fraicheur_etat": "retard",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": false,
      "observabilite": false,
      "incidents": false,
      "documentation": false
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Digital — C. Nguyen",
    "autonomie": "aucune",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "retours",
    "nom": "Retours",
    "domaine": "Opérations",
    "statut": "actif",
    "position": {
      "x": 350,
      "y": 730
    },
    "mission": "Pilote les retours clients et leur reconditionnement",
    "sante": "nominal",
    "couverture": 72,
    "fraicheur": "il y a 10 min",
    "strates": {
      "identite": 91,
      "comportement": 70,
      "relations": 52,
      "trajectoire": 68,
      "memoire": 60
    },
    "fraicheur_etat": "a_jour",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": true,
      "incidents": false,
      "documentation": false
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Ops — R. Fabre",
    "autonomie": "supervisé",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "entrepots",
    "nom": "Entrepôts",
    "domaine": "Opérations",
    "statut": "actif",
    "position": {
      "x": 250,
      "y": 810
    },
    "mission": "Synchronise les stocks entre les sites logistiques",
    "sante": "nominal",
    "couverture": 77,
    "fraicheur": "il y a 5 min",
    "strates": {
      "identite": 93,
      "comportement": 76,
      "relations": 60,
      "trajectoire": 72,
      "memoire": 66
    },
    "fraicheur_etat": "a_jour",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": true,
      "incidents": true,
      "documentation": false
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      },
      {
        "cle": "incidents",
        "nom": "ServiceNow",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Ops — R. Fabre",
    "autonomie": "supervisé",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "satisfaction",
    "nom": "Satisfaction",
    "domaine": "Support",
    "statut": "observation",
    "position": {
      "x": 1250,
      "y": 690
    },
    "mission": "Mesure CSAT et NPS après chaque résolution",
    "sante": "inconnu",
    "couverture": 51,
    "fraicheur": "il y a 4 h",
    "strates": {
      "identite": 70,
      "comportement": 50,
      "relations": 34,
      "trajectoire": 54,
      "memoire": 44
    },
    "fraicheur_etat": "retard",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": false,
      "incidents": false,
      "documentation": false
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Care — J. Morel",
    "autonomie": "aucune",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "alertes-risque",
    "nom": "Alertes Risque",
    "domaine": "Risque",
    "statut": "actif",
    "position": {
      "x": 1005,
      "y": 300
    },
    "mission": "Diffuse les alertes de fraude aux équipes concernées",
    "sante": "nominal",
    "couverture": 69,
    "fraicheur": "il y a 8 min",
    "strates": {
      "identite": 88,
      "comportement": 68,
      "relations": 52,
      "trajectoire": 66,
      "memoire": 58
    },
    "fraicheur_etat": "a_jour",
    "capacites": null,
    "candidat": null,
    "sources": {
      "code": true,
      "bdd": true,
      "observabilite": true,
      "incidents": true,
      "documentation": false
    },
    "sources_detail": [
      {
        "cle": "code",
        "nom": "GitHub",
        "statut": "prete"
      },
      {
        "cle": "bdd",
        "nom": "PostgreSQL",
        "statut": "prete"
      },
      {
        "cle": "observabilite",
        "nom": "Datadog",
        "statut": "prete"
      },
      {
        "cle": "incidents",
        "nom": "ServiceNow",
        "statut": "prete"
      }
    ],
    "proprietaire": "Équipe Risque — S. Petit",
    "autonomie": "supervisé",
    "environnement": "production",
    "gouvernance": [
      {
        "action": "Actualiser ses connaissances",
        "niveau": "delegue"
      },
      {
        "action": "Interroger ses voisins",
        "niveau": "delegue"
      },
      {
        "action": "Créer une situation candidate",
        "niveau": "delegue"
      },
      {
        "action": "Publier une actualité",
        "niveau": "delegue"
      },
      {
        "action": "Ouvrir une investigation",
        "niveau": "supervise"
      },
      {
        "action": "Publier dans un système externe",
        "niveau": "supervise"
      },
      {
        "action": "Admettre une connaissance critique",
        "niveau": "supervise"
      },
      {
        "action": "Modifier une permission",
        "niveau": "interdit"
      },
      {
        "action": "Exécuter un changement en production",
        "niveau": "interdit"
      }
    ]
  },
  {
    "id": "cand-agregateur-flux",
    "nom": "Agrégateur de flux ?",
    "domaine": "À confirmer",
    "statut": "observation",
    "position": {
      "x": 1500,
      "y": 150
    },
    "mission": "Service découvert dans les flux sortants de Paiements — nature à confirmer",
    "sante": "inconnue",
    "couverture": 18,
    "fraicheur": "il y a 2 j",
    "strates": {},
    "fraicheur_etat": "ok",
    "capacites": null,
    "candidat": true,
    "sources": {},
    "sources_detail": [],
    "proprietaire": "",
    "autonomie": "non qualifiée",
    "environnement": "production",
    "gouvernance": null
  },
  {
    "id": "cand-passerelle-sepa",
    "nom": "Passerelle SEPA ?",
    "domaine": "À confirmer",
    "statut": "observation",
    "position": {
      "x": 1630,
      "y": 120
    },
    "mission": "Relais de messages SEPA observé dans les logs réseau — non déclaré au référentiel",
    "sante": "inconnue",
    "couverture": 31,
    "fraicheur": "il y a 1 j",
    "strates": {},
    "fraicheur_etat": "ok",
    "capacites": null,
    "candidat": true,
    "sources": {},
    "sources_detail": [],
    "proprietaire": "",
    "autonomie": "non qualifiée",
    "environnement": "production",
    "gouvernance": null
  },
  {
    "id": "cand-relais-notif",
    "nom": "Relais de notifications ?",
    "domaine": "À confirmer",
    "statut": "observation",
    "position": {
      "x": 1560,
      "y": 240
    },
    "mission": "Point de sortie de notifications observé — propriétaire non identifié",
    "sante": "inconnue",
    "couverture": 12,
    "fraicheur": "il y a 3 j",
    "strates": {},
    "fraicheur_etat": "stale",
    "capacites": null,
    "candidat": true,
    "sources": {},
    "sources_detail": [],
    "proprietaire": "",
    "autonomie": "non qualifiée",
    "environnement": "production",
    "gouvernance": null
  }
];

export const MONDE_RELATIONS = [
  {
    "id": "r1",
    "source": "portail-web",
    "cible": "api-gateway",
    "type": "structurante",
    "active": true,
    "etat": "confirmee",
    "decouverte_quand": "il y a 8 mois",
    "source_decouverte": "CMDB + traces",
    "confirmee_par": [
      "Portail Web",
      "API Gateway"
    ],
    "claims": [
      "Tout le trafic web transite par la gateway"
    ],
    "observations_contraires": [],
    "evolution": [
      {
        "quand": "il y a 8 mois",
        "etat": "confirmée"
      }
    ]
  },
  {
    "id": "r2",
    "source": "api-gateway",
    "cible": "paiements",
    "type": "structurante",
    "active": true,
    "etat": "confirmee",
    "decouverte_quand": "il y a 8 mois",
    "source_decouverte": "CMDB + traces",
    "confirmee_par": [
      "API Gateway",
      "Paiements"
    ],
    "claims": [
      "POST /payments est le premier appel du parcours"
    ],
    "observations_contraires": [],
    "evolution": [
      {
        "quand": "il y a 8 mois",
        "etat": "confirmée"
      }
    ]
  },
  {
    "id": "r3",
    "source": "api-gateway",
    "cible": "comptes",
    "type": "structurante",
    "active": false,
    "etat": "confirmee",
    "decouverte_quand": "il y a 8 mois",
    "source_decouverte": "CMDB",
    "confirmee_par": [
      "API Gateway"
    ],
    "claims": [],
    "observations_contraires": [],
    "evolution": []
  },
  {
    "id": "r4",
    "source": "paiements",
    "cible": "comptes",
    "type": "structurante",
    "active": true,
    "etat": "confirmee",
    "decouverte_quand": "il y a 8 mois",
    "source_decouverte": "Traces Datadog",
    "confirmee_par": [
      "Paiements",
      "Comptes"
    ],
    "claims": [
      "Débit/crédit synchrone à chaque transaction"
    ],
    "observations_contraires": [],
    "evolution": []
  },
  {
    "id": "r5",
    "source": "paiements",
    "cible": "fraude",
    "type": "structurante",
    "active": true,
    "etat": "confirmee",
    "decouverte_quand": "il y a 6 mois",
    "source_decouverte": "Code + traces",
    "confirmee_par": [
      "Paiements",
      "Fraude"
    ],
    "claims": [
      "Contrôles synchrones fraud.check à chaque transaction"
    ],
    "observations_contraires": [],
    "evolution": []
  },
  {
    "id": "r6",
    "source": "paiements",
    "cible": "support",
    "type": "decouverte",
    "active": true,
    "etat": "validation",
    "confiance": 82,
    "decouverte_quand": "il y a 2 jours",
    "source_decouverte": "Corrélation comportementale (Splunk + traces)",
    "confirmee_par": [
      "Paiements"
    ],
    "claims": [
      "82 % des ralentissements Paiements précèdent des demandes Support",
      "Délai médian de 7 minutes entre signal et tickets"
    ],
    "observations_contraires": [
      "Aucun appel direct observé dans les traces",
      "Aucune relation déclarée dans la CMDB"
    ],
    "evolution": [
      {
        "quand": "il y a 2 jours",
        "etat": "observée"
      },
      {
        "quand": "il y a 6 h",
        "etat": "supposée"
      },
      {
        "quand": "il y a 1 h",
        "etat": "en validation A2A"
      }
    ]
  },
  {
    "id": "r7",
    "source": "paiements",
    "cible": "facturation",
    "type": "structurante",
    "active": false,
    "etat": "confirmee",
    "decouverte_quand": "il y a 6 mois",
    "source_decouverte": "Événement PaymentSettled",
    "confirmee_par": [
      "Paiements",
      "Facturation"
    ],
    "claims": [],
    "observations_contraires": [],
    "evolution": []
  },
  {
    "id": "r8",
    "source": "commandes",
    "cible": "paiements",
    "type": "structurante",
    "active": false,
    "etat": "confirmee",
    "decouverte_quand": "il y a 6 mois",
    "source_decouverte": "CMDB",
    "confirmee_par": [
      "Commandes"
    ],
    "claims": [],
    "observations_contraires": [],
    "evolution": []
  },
  {
    "id": "r9",
    "source": "commandes",
    "cible": "logistique",
    "type": "structurante",
    "active": true,
    "etat": "observee",
    "decouverte_quand": "il y a 3 jours",
    "source_decouverte": "Traces (Logistique en observation)",
    "confirmee_par": [],
    "claims": [
      "Préparation déclenchée après confirmation de commande"
    ],
    "observations_contraires": [],
    "evolution": [
      {
        "quand": "il y a 3 jours",
        "etat": "observée"
      }
    ]
  },
  {
    "id": "r10",
    "source": "support",
    "cible": "notifications",
    "type": "structurante",
    "active": false,
    "etat": "confirmee",
    "decouverte_quand": "il y a 5 mois",
    "source_decouverte": "Code + traces",
    "confirmee_par": [
      "Support",
      "Notifications"
    ],
    "claims": [],
    "observations_contraires": [],
    "evolution": []
  },
  {
    "id": "r11",
    "source": "comptes",
    "cible": "identite",
    "type": "structurante",
    "active": false,
    "etat": "confirmee",
    "decouverte_quand": "il y a 7 mois",
    "source_decouverte": "CMDB",
    "confirmee_par": [
      "Comptes",
      "Identité"
    ],
    "claims": [],
    "observations_contraires": [],
    "evolution": []
  },
  {
    "id": "r12",
    "source": "fraude",
    "cible": "conformite",
    "type": "structurante",
    "active": false,
    "etat": "supposee",
    "confiance": 64,
    "decouverte_quand": "il y a 1 jour",
    "source_decouverte": "Apprentissage du jumeau Conformité (en construction)",
    "confirmee_par": [],
    "claims": [
      "Les alertes Fraude semblent alimenter les dossiers Conformité"
    ],
    "observations_contraires": [
      "Conformité n'a pas encore confirmé"
    ],
    "evolution": [
      {
        "quand": "il y a 1 jour",
        "etat": "supposée"
      }
    ]
  },
  {
    "id": "r13",
    "source": "facturation",
    "cible": "comptes",
    "type": "structurante",
    "active": false,
    "etat": "obsolete",
    "decouverte_quand": "il y a 11 mois",
    "source_decouverte": "CMDB",
    "confirmee_par": [],
    "claims": [],
    "observations_contraires": [
      "Aucun échange observé depuis 90 jours"
    ],
    "evolution": [
      {
        "quand": "il y a 11 mois",
        "etat": "confirmée"
      },
      {
        "quand": "il y a 12 jours",
        "etat": "obsolète"
      }
    ]
  },
  {
    "id": "r14",
    "source": "identite",
    "cible": "paiements",
    "type": "structurante",
    "active": false,
    "etat": "contestee",
    "decouverte_quand": "il y a 5 jours",
    "source_decouverte": "Analyse statique du code (GitHub)",
    "confirmee_par": [],
    "claims": [
      "Le module identity.session importe payments.client"
    ],
    "observations_contraires": [
      "Aucune trace d'appel en 90 jours",
      "Le chemin de code semble mort depuis la v4"
    ],
    "evolution": [
      {
        "quand": "il y a 5 jours",
        "etat": "supposée"
      },
      {
        "quand": "il y a 2 jours",
        "etat": "contestée"
      }
    ]
  },
  {
    "id": "r15",
    "source": "prelevements",
    "cible": "paiements",
    "type": "structurante",
    "active": false,
    "etat": "confirmee",
    "decouverte_quand": "il y a 7 mois",
    "source_decouverte": "CMDB",
    "confirmee_par": [
      "Prélèvements",
      "Paiements"
    ],
    "claims": [],
    "observations_contraires": [],
    "evolution": []
  },
  {
    "id": "r16",
    "source": "remboursements",
    "cible": "facturation",
    "type": "structurante",
    "active": false,
    "etat": "confirmee",
    "decouverte_quand": "il y a 6 mois",
    "source_decouverte": "Code + traces",
    "confirmee_par": [
      "Remboursements",
      "Facturation"
    ],
    "claims": [],
    "observations_contraires": [],
    "evolution": []
  },
  {
    "id": "r17",
    "source": "remboursements",
    "cible": "support",
    "type": "decouverte",
    "active": true,
    "etat": "observee",
    "decouverte_quand": "il y a 4 jours",
    "source_decouverte": "Traces Datadog",
    "confirmee_par": [],
    "claims": [
      "Chaque remboursement déclenche un ticket de suivi"
    ],
    "observations_contraires": [],
    "evolution": [
      {
        "quand": "il y a 4 jours",
        "etat": "observée"
      }
    ]
  },
  {
    "id": "r18",
    "source": "preferences",
    "cible": "comptes",
    "type": "structurante",
    "active": false,
    "etat": "confirmee",
    "decouverte_quand": "il y a 8 mois",
    "source_decouverte": "CMDB",
    "confirmee_par": [
      "Préférences",
      "Comptes"
    ],
    "claims": [],
    "observations_contraires": [],
    "evolution": []
  },
  {
    "id": "r19",
    "source": "fidelite",
    "cible": "comptes",
    "type": "decouverte",
    "active": true,
    "etat": "observee",
    "decouverte_quand": "il y a 2 jours",
    "source_decouverte": "Événements métier (Splunk)",
    "confirmee_par": [],
    "claims": [
      "Les statuts fidélité se recalculent après chaque mouvement de compte"
    ],
    "observations_contraires": [],
    "evolution": [
      {
        "quand": "il y a 2 jours",
        "etat": "observée"
      }
    ]
  },
  {
    "id": "r20",
    "source": "scoring",
    "cible": "fraude",
    "type": "structurante",
    "active": false,
    "etat": "confirmee",
    "decouverte_quand": "il y a 5 mois",
    "source_decouverte": "Code + traces",
    "confirmee_par": [
      "Scoring Crédit",
      "Fraude"
    ],
    "claims": [],
    "observations_contraires": [],
    "evolution": []
  },
  {
    "id": "r21",
    "source": "sanctions",
    "cible": "conformite",
    "type": "decouverte",
    "active": false,
    "etat": "supposee",
    "confiance": 57,
    "decouverte_quand": "il y a 12 h",
    "source_decouverte": "Apprentissage du jumeau Filtrage Sanctions",
    "confirmee_par": [],
    "claims": [
      "Les rejets de sanctions semblent ouvrir des dossiers Conformité"
    ],
    "observations_contraires": [
      "Conformité n'a pas encore confirmé"
    ],
    "evolution": [
      {
        "quand": "il y a 12 h",
        "etat": "supposée"
      }
    ]
  },
  {
    "id": "r22",
    "source": "stocks",
    "cible": "commandes",
    "type": "structurante",
    "active": false,
    "etat": "confirmee",
    "decouverte_quand": "il y a 7 mois",
    "source_decouverte": "CMDB + traces",
    "confirmee_par": [
      "Stocks",
      "Commandes"
    ],
    "claims": [],
    "observations_contraires": [],
    "evolution": []
  },
  {
    "id": "r23",
    "source": "transporteurs",
    "cible": "logistique",
    "type": "decouverte",
    "active": true,
    "etat": "observee",
    "decouverte_quand": "il y a 3 jours",
    "source_decouverte": "Traces (Transporteurs en observation)",
    "confirmee_par": [],
    "claims": [
      "Les preuves de livraison clôturent les expéditions"
    ],
    "observations_contraires": [],
    "evolution": [
      {
        "quand": "il y a 3 jours",
        "etat": "observée"
      }
    ]
  },
  {
    "id": "r24",
    "source": "base-connaissances",
    "cible": "support",
    "type": "structurante",
    "active": false,
    "etat": "confirmee",
    "decouverte_quand": "il y a 9 mois",
    "source_decouverte": "CMDB",
    "confirmee_par": [
      "Base de connaissances",
      "Support"
    ],
    "claims": [],
    "observations_contraires": [],
    "evolution": []
  },
  {
    "id": "r25",
    "source": "escalades",
    "cible": "support",
    "type": "structurante",
    "active": false,
    "etat": "confirmee",
    "decouverte_quand": "il y a 6 mois",
    "source_decouverte": "Code + traces",
    "confirmee_par": [
      "Escalades",
      "Support"
    ],
    "claims": [],
    "observations_contraires": [],
    "evolution": []
  },
  {
    "id": "r26",
    "source": "catalogue",
    "cible": "api-gateway",
    "type": "structurante",
    "active": false,
    "etat": "confirmee",
    "decouverte_quand": "il y a 8 mois",
    "source_decouverte": "CMDB + traces",
    "confirmee_par": [
      "Catalogue",
      "API Gateway"
    ],
    "claims": [],
    "observations_contraires": [],
    "evolution": []
  },
  {
    "id": "r27",
    "source": "recommandations",
    "cible": "portail-web",
    "type": "decouverte",
    "active": true,
    "etat": "observee",
    "decouverte_quand": "il y a 5 jours",
    "source_decouverte": "Traces (Recommandations en observation)",
    "confirmee_par": [],
    "claims": [
      "Les suggestions sont rendues côté Portail Web à chaque visite"
    ],
    "observations_contraires": [],
    "evolution": [
      {
        "quand": "il y a 5 jours",
        "etat": "observée"
      }
    ]
  },
  {
    "id": "r28",
    "source": "scoring",
    "cible": "paiements",
    "type": "decouverte",
    "active": true,
    "etat": "observee",
    "decouverte_quand": "il y a 1 jour",
    "source_decouverte": "Corrélation comportementale",
    "confirmee_par": [],
    "claims": [
      "Le plafond de transaction varie avec le score risque"
    ],
    "observations_contraires": [],
    "evolution": [
      {
        "quand": "il y a 1 jour",
        "etat": "observée"
      }
    ]
  },
  {
    "id": "r29",
    "source": "communications",
    "cible": "comptes",
    "type": "structurante",
    "active": false,
    "etat": "confirmee",
    "decouverte_quand": "il y a 8 mois",
    "source_decouverte": "CMDB",
    "confirmee_par": [
      "Communications",
      "Comptes"
    ],
    "claims": [],
    "observations_contraires": [],
    "evolution": []
  },
  {
    "id": "r30",
    "source": "communications",
    "cible": "portail-web",
    "type": "decouverte",
    "active": true,
    "etat": "observee",
    "decouverte_quand": "il y a 3 jours",
    "source_decouverte": "Traces Datadog",
    "confirmee_par": [],
    "claims": [
      "Les notifications panier partent après chaque visite du portail"
    ],
    "observations_contraires": [],
    "evolution": [
      {
        "quand": "il y a 3 jours",
        "etat": "observée"
      }
    ]
  },
  {
    "id": "r31",
    "source": "consentements",
    "cible": "identite",
    "type": "structurante",
    "active": false,
    "etat": "confirmee",
    "decouverte_quand": "il y a 10 mois",
    "source_decouverte": "CMDB + code",
    "confirmee_par": [
      "Consentements",
      "Identité"
    ],
    "claims": [],
    "observations_contraires": [],
    "evolution": []
  },
  {
    "id": "r32",
    "source": "onboarding",
    "cible": "comptes",
    "type": "decouverte",
    "active": true,
    "etat": "observee",
    "decouverte_quand": "il y a 2 jours",
    "source_decouverte": "Événements métier (Splunk)",
    "confirmee_par": [],
    "claims": [
      "Chaque création de compte suit le parcours d'onboarding"
    ],
    "observations_contraires": [],
    "evolution": [
      {
        "quand": "il y a 2 jours",
        "etat": "observée"
      }
    ]
  },
  {
    "id": "r33",
    "source": "segments",
    "cible": "preferences",
    "type": "decouverte",
    "active": false,
    "etat": "supposee",
    "confiance": 62,
    "decouverte_quand": "il y a 20 h",
    "source_decouverte": "Apprentissage du jumeau Segments",
    "confirmee_par": [],
    "claims": [
      "Les segments semblent lire les préférences pour exclure les opposés"
    ],
    "observations_contraires": [],
    "evolution": [
      {
        "quand": "il y a 20 h",
        "etat": "supposée"
      }
    ]
  },
  {
    "id": "r34",
    "source": "litiges",
    "cible": "paiements",
    "type": "structurante",
    "active": false,
    "etat": "confirmee",
    "decouverte_quand": "il y a 7 mois",
    "source_decouverte": "CMDB + traces",
    "confirmee_par": [
      "Litiges",
      "Paiements"
    ],
    "claims": [],
    "observations_contraires": [],
    "evolution": []
  },
  {
    "id": "r35",
    "source": "litiges",
    "cible": "support",
    "type": "decouverte",
    "active": true,
    "etat": "observee",
    "decouverte_quand": "il y a 5 jours",
    "source_decouverte": "Traces Datadog",
    "confirmee_par": [],
    "claims": [
      "Les chargebacks ouvrent des tickets côté Support"
    ],
    "observations_contraires": [],
    "evolution": [
      {
        "quand": "il y a 5 jours",
        "etat": "observée"
      }
    ]
  },
  {
    "id": "r36",
    "source": "tokens",
    "cible": "paiements",
    "type": "structurante",
    "active": false,
    "etat": "confirmee",
    "decouverte_quand": "il y a 9 mois",
    "source_decouverte": "Code + traces",
    "confirmee_par": [
      "Tokenisation",
      "Paiements"
    ],
    "claims": [],
    "observations_contraires": [],
    "evolution": []
  },
  {
    "id": "r37",
    "source": "strong-auth",
    "cible": "scoring",
    "type": "decouverte",
    "active": true,
    "etat": "observee",
    "decouverte_quand": "il y a 1 jour",
    "source_decouverte": "Corrélation comportementale",
    "confirmee_par": [],
    "claims": [
      "Le déclenchement 3-D Secure suit le score de risque"
    ],
    "observations_contraires": [],
    "evolution": [
      {
        "quand": "il y a 1 jour",
        "etat": "observée"
      }
    ]
  },
  {
    "id": "r38",
    "source": "recherche",
    "cible": "catalogue",
    "type": "structurante",
    "active": false,
    "etat": "confirmee",
    "decouverte_quand": "il y a 8 mois",
    "source_decouverte": "CMDB",
    "confirmee_par": [
      "Recherche",
      "Catalogue"
    ],
    "claims": [],
    "observations_contraires": [],
    "evolution": []
  },
  {
    "id": "r39",
    "source": "promotions",
    "cible": "catalogue",
    "type": "decouverte",
    "active": true,
    "etat": "observee",
    "decouverte_quand": "il y a 4 jours",
    "source_decouverte": "Traces Datadog",
    "confirmee_par": [],
    "claims": [
      "Les prix affichés combinent catalogue et promotions"
    ],
    "observations_contraires": [],
    "evolution": [
      {
        "quand": "il y a 4 jours",
        "etat": "observée"
      }
    ]
  },
  {
    "id": "r40",
    "source": "seo-pages",
    "cible": "portail-web",
    "type": "structurante",
    "active": false,
    "etat": "confirmee",
    "decouverte_quand": "il y a 11 mois",
    "source_decouverte": "CMDB",
    "confirmee_par": [
      "Pages SEO",
      "Portail Web"
    ],
    "claims": [],
    "observations_contraires": [],
    "evolution": []
  },
  {
    "id": "r41",
    "source": "retours",
    "cible": "logistique",
    "type": "structurante",
    "active": false,
    "etat": "confirmee",
    "decouverte_quand": "il y a 7 mois",
    "source_decouverte": "CMDB + traces",
    "confirmee_par": [
      "Retours",
      "Logistique"
    ],
    "claims": [],
    "observations_contraires": [],
    "evolution": []
  },
  {
    "id": "r42",
    "source": "retours",
    "cible": "remboursements",
    "type": "decouverte",
    "active": true,
    "etat": "observee",
    "decouverte_quand": "il y a 6 jours",
    "source_decouverte": "Traces Datadog",
    "confirmee_par": [],
    "claims": [
      "Chaque retour validé déclenche un remboursement"
    ],
    "observations_contraires": [],
    "evolution": [
      {
        "quand": "il y a 6 jours",
        "etat": "observée"
      }
    ]
  },
  {
    "id": "r43",
    "source": "entrepots",
    "cible": "stocks",
    "type": "structurante",
    "active": false,
    "etat": "confirmee",
    "decouverte_quand": "il y a 6 mois",
    "source_decouverte": "Code + traces",
    "confirmee_par": [
      "Entrepôts",
      "Stocks"
    ],
    "claims": [],
    "observations_contraires": [],
    "evolution": []
  },
  {
    "id": "r44",
    "source": "satisfaction",
    "cible": "support",
    "type": "decouverte",
    "active": true,
    "etat": "observee",
    "decouverte_quand": "il y a 2 jours",
    "source_decouverte": "Événements métier (Splunk)",
    "confirmee_par": [],
    "claims": [
      "Les enquêtes partent à la clôture des tickets"
    ],
    "observations_contraires": [],
    "evolution": [
      {
        "quand": "il y a 2 jours",
        "etat": "observée"
      }
    ]
  },
  {
    "id": "r45",
    "source": "alertes-risque",
    "cible": "fraude",
    "type": "decouverte",
    "active": true,
    "etat": "observee",
    "decouverte_quand": "il y a 8 h",
    "source_decouverte": "Traces Datadog",
    "confirmee_par": [],
    "claims": [
      "Chaque alerte est émise après un score de fraude élevé"
    ],
    "observations_contraires": [],
    "evolution": [
      {
        "quand": "il y a 8 h",
        "etat": "observée"
      }
    ]
  },
  {
    "id": "r-cand-1",
    "active": true,
    "cible": "cand-agregateur-flux",
    "claims": [
      "Appels sortants observés vers un hôte non référencé"
    ],
    "confiance": 41,
    "decouverte_quand": "il y a 2 j",
    "etat": "supposee",
    "evolution": [],
    "observations_contraires": [],
    "source": "paiements",
    "source_decouverte": "traces Datadog",
    "type": "appelle"
  },
  {
    "id": "r-cand-2",
    "active": true,
    "cible": "cand-agregateur-flux",
    "claims": [
      "Flux SEPA transité par un relais non déclaré"
    ],
    "confiance": 34,
    "decouverte_quand": "il y a 1 j",
    "etat": "supposee",
    "evolution": [],
    "observations_contraires": [],
    "source": "cand-passerelle-sepa",
    "source_decouverte": "logs réseau",
    "type": "echange"
  },
  {
    "id": "r-cand-3",
    "active": true,
    "cible": "cand-relais-notif",
    "claims": [
      "Chaîne d'appels sortante prolongée vers un relais de notifications"
    ],
    "confiance": 28,
    "decouverte_quand": "il y a 3 j",
    "etat": "supposee",
    "evolution": [],
    "observations_contraires": [],
    "source": "cand-agregateur-flux",
    "source_decouverte": "traces Datadog",
    "type": "alimente"
  }
];

export const MONDE_REGIONS = [
  {
    "id": "reg-distribution",
    "label": "Distribution",
    "x": 440,
    "y": 0,
    "w": 460,
    "h": 190,
    "couleur": "#F0ABFC",
    "maturite": {
      "niveau": "partiellement découvert",
      "jumeaux": 7,
      "relations_emergentes": 2,
      "zones_inconnues": 1
    }
  },
  {
    "id": "reg-paiement",
    "label": "Paiement",
    "x": 440,
    "y": 230,
    "w": 420,
    "h": 320,
    "couleur": "#3B82F6",
    "maturite": {
      "niveau": "en transformation",
      "jumeaux": 7,
      "relations_emergentes": 2,
      "zones_inconnues": 1
    }
  },
  {
    "id": "reg-client",
    "label": "Client",
    "x": 60,
    "y": 170,
    "w": 340,
    "h": 340,
    "couleur": "#34D399",
    "maturite": {
      "niveau": "bien connu",
      "jumeaux": 8,
      "relations_emergentes": 2,
      "zones_inconnues": 0
    }
  },
  {
    "id": "reg-risque",
    "label": "Risque",
    "x": 960,
    "y": 150,
    "w": 340,
    "h": 320,
    "couleur": "#F87171",
    "maturite": {
      "niveau": "instable",
      "jumeaux": 5,
      "relations_emergentes": 3,
      "zones_inconnues": 1
    }
  },
  {
    "id": "reg-support",
    "label": "Support",
    "x": 940,
    "y": 500,
    "w": 380,
    "h": 290,
    "couleur": "#FB923C",
    "maturite": {
      "niveau": "insuffisamment couvert",
      "jumeaux": 5,
      "relations_emergentes": 2,
      "zones_inconnues": 2
    }
  },
  {
    "id": "reg-operations",
    "label": "Opérations",
    "x": 60,
    "y": 560,
    "w": 340,
    "h": 260,
    "couleur": "#A3E635",
    "maturite": {
      "niveau": "partiellement découvert",
      "jumeaux": 6,
      "relations_emergentes": 1,
      "zones_inconnues": 1
    }
  },
  {
    "id": "reg-a-confirmer",
    "label": "À confirmer",
    "x": 1440,
    "y": 60,
    "w": 320,
    "h": 240,
    "couleur": "#A8A29E",
    "confirme": false,
    "maturite": {
      "niveau": "découvert — non validé",
      "jumeaux": 3,
      "relations_emergentes": 2,
      "zones_inconnues": 3
    }
  }
];
