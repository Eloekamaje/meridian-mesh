---
nom: reponse-pedagogique
description: Réponse de diagnostic, d'écart ou de décision : verdict, schéma, trois constats, conséquence, décision, trois tests.
---
# Réponse pédagogique

Pour composer la réponse, appelle `repondre_pedagogiquement` : il dessine le schéma et assemble les sections.
Sa sortie est la réponse ; ne la réécris pas et n'ajoute rien avant ou après.

0. Dans un Travail, commence par planifier (planifier) : une étape par point ci-dessous.
1. **Verdict** : une phrase. Dis ce qui est vrai, ce qui ne l'est pas, et ce que cela change.
2. **Schéma** : juste après le verdict, avant les constats. Le tool `repondre_pedagogiquement` le dessine. Pour un
   état produit, commence par `etat_produit` (capacités + liens) : il dérive les statuts et les manques. Passe
   ensuite ses `capacites` à `repondre_pedagogiquement` : le schéma est la projection des états dérivés, sans
   libellé ni statut codé en dur. Pour une architecture libre, **deux groupes au moins** (« Front-end »,
   « Backend ») et **8 boîtes maximum** ; sinon le tool refuse et demande la correction. Donne à chaque boîte son
   `statut` :
   `ok` (✅), `partiel` (⚠️), `absent` (⛔), `inconnu` (❔). Une boîte annotée reste visible même sans flèche :
   c'est ainsi qu'on montre une absence sans inventer de lien. Chaque flèche garde son fondement : ligne d'appel
   lue dans le code (`chemin#Lx-Ly`, `appel` = fonction appelée) ou Claim vérifié (`c:<id>`). Utilise
   `suivre_appels` pour obtenir les lignes d'appel ; un Claim « en partie » ou « non appuyé » est refusé.
3. **Trois constats au plus** : un fait, une preuve. Pas de paraphrase du schéma.
4. **Conséquence** : ce que cela change pour la décision ; ce qu'on ne peut pas conclure.
5. **Décision** : une recommandation unique, avec deux conditions non négociables.
6. **Trois tests** : vérifiables, réalisables sur les parcours existants.
7. **Inconnues** : trois puces au plus, à trancher par l'équipe.
8. **Annexe** : les preuves détaillées, les Claims, les citations. Le corps reste court.

Règles :

- 2 000 caractères maximum pour le corps ; au-delà, annexe.
- Qualifie chaque Claim : `backend`, `front-end` ou `bout en bout`. Un Claim backend ne prouve pas une capacité
  produit.
- Cherche les maquettes : getters codés en dur, handlers vides, composants stub, données de démonstration.
- Pas de tableau dans le corps ; des puces courtes.
- Le schéma porte la structure ; le texte ne la répète pas.
- Si une information manque, écris-la comme inconnue, pas comme un fait.
