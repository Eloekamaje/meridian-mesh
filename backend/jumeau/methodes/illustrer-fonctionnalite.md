---
nom: illustrer-fonctionnalite
description: On demande un schéma, un diagramme, une illustration, ou comment fonctionne une fonctionnalité (« que se passe-t-il quand… »).
---
# Illustrer une fonctionnalité

0. Dans un Travail, commencez par planifier (planifier) : une étape par point ci-dessous.
1. Reformulez la question en une fonctionnalité précise (« publier un article », « s'inscrire »).
2. Trouvez son point d'entrée : la route ou le bouton qui la déclenche (mes_connaissances, famille EXPOSE ;
   sinon chercher_symbole), puis la fonction qui la traite.
3. Suivez l'enchaînement avec suivre_appels depuis cette fonction (profondeur 3). Chaque flèche rendue a sa ligne
   d'appel : c'est son fondement. Lisez avec lire_code les étapes qui comptent pour comprendre ce qu'elles font
   (une règle, une vérification, une erreur renvoyée).
4. Choisissez le schéma selon la question :
   - « que se passe-t-il quand… », « comment fonctionne… » : sequence ;
   - « de quoi est-elle faite », « avec qui échange-t-elle » : architecture (flèches fondées sur des connaissances
     c:<id> ou des relations r:<id>) ;
   - un parcours d'étapes : flux.
5. Dessinez avec dessiner_schema : 5 à 9 boîtes, nommées dans les mots du métier (« Fabrication de l'adresse de
   l'article », pas get_slug_for_article). Regroupez ce qui est trop détaillé ; laissez de côté les utilitaires
   (journal, conversions, erreurs techniques). Chaque flèche reprend tel quel le fondement rendu par suivre_appels,
   avec appel = la fonction appelée. Si le compte rendu écarte des flèches, corrigez-les une fois.
6. Dans votre réponse : une ou deux phrases qui disent ce que fait la fonctionnalité, puis ce que le schéma montre
   en trois puces au plus. Ne recopiez pas le schéma : il s'affiche de lui-même.
7. Dites ce que le schéma ne montre pas : les cas d'erreur (souvent oubliés), ce qui se passe hors du code (volumes,
   exploitation), et ce que vous n'avez pas pu prouver.
