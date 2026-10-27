---
nom: comprendre-application
description: Il faut comprendre une application en profondeur, ou rédiger sa fiche vivante : à quoi elle sert, pour qui, ce qu'elle détient, ses règles, ses échanges, comment elle vit, ce qu'on ignore.
---
# Comprendre une application

Comprendre une application, c'est pouvoir répondre, preuves à l'appui, à sept questions d'entreprise. Le code
est la preuve, jamais le propos : pas de nom de route, de bibliothèque ni de variable dans les réponses.

## Enquêter

1. Commencez par mes_connaissances : reprenez mot pour mot les formulations déjà établies (surtout celles
   marquées ✓, validées par l'équipe) au lieu d'en créer de nouvelles qui diraient la même chose.
2. Vue d'ensemble avec architecture, puis cherchez ce qui porte le métier : écrans et parcours, modèles de
   données, contrôles et refus, appels vers d'autres systèmes, documents produit (README, cahier des charges).
3. Lisez avec lire_code les lignes qui prouvent chaque réponse ; historique_du_code pour la façon dont elle vit.

## Les sept questions

Pour chaque réponse des cinq premières questions, appelez proposer_connaissance avec le prédicat indiqué,
un objet d'une ligne (12 mots au plus) et les lignes lues qui le prouvent :

1. **À quoi elle sert** : ses capacités d'affaires, un verbe et un objet métier (« Gérer les dossiers des
   clients »). Prédicat REALISE_CAPACITE, type CAPABILITY.
2. **Pour qui, dans quels parcours** : qui l'utilise et à quelle étape. Prédicat SERT_ACTEUR, type PROCESS_STEP.
3. **Les informations qu'elle détient** : ses objets métier, et si elle en est la référence. Prédicat DETIENT,
   type DATA_FLOW.
4. **Les règles qu'elle applique** : contrôles, limites, approbations. Prédicat APPLIQUE_REGLE, type BUSINESS_RULE.
5. **Avec qui elle échange** : autres applications, services tiers. Prédicat ECHANGE_AVEC, type DATA_FLOW.
6. **Comment elle vit** : maturité, changements récents et leur raison.
7. **Ce que l'on ne sait pas encore** : ce que ni le code ni l'équipe ne disent, et qui pourrait le dire.

Une réponse sans preuve lue ne se propose pas : elle va dans « Ce que l'on ne sait pas encore ».

## Fiche vivante

Si l'on vous demande la fiche, rédigez-la en Markdown, 400 mots au plus, avec exactement ces sections :
« ## À quoi elle sert », « ## Pour qui, dans quels parcours », « ## Les informations qu'elle détient »,
« ## Les règles qu'elle applique », « ## Avec qui elle échange », « ## Comment elle vit »,
« ## Ce que l'on ne sait pas encore ». Des puces d'une ligne, celles des cinq premières sections reprenant les
connaissances proposées, chacune suivie de sa citation `chemin#Ldébut-Lfin`. C'est un document : ni question
finale, ni proposition de suite.
