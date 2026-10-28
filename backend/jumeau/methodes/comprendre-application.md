---
nom: comprendre-application
description: Il faut comprendre une application en profondeur, ou rédiger sa fiche vivante : à quoi elle sert, pour qui, ce qu'elle détient, ses règles, ses échanges, comment elle vit, ce qu'on ignore.
---
# Comprendre une application

Comprendre une application, c'est pouvoir répondre, preuves à l'appui, à sept questions d'entreprise. Le code
est la preuve, jamais le propos : pas de nom de route, de bibliothèque ni de variable dans les réponses.

## Enquêter

1. Commencez par mes_connaissances : reprenez mot pour mot les formulations déjà établies (surtout celles
   validées par l'équipe) au lieu d'en créer de nouvelles qui diraient la même chose. Si deux connaissances
   disent déjà la même chose, fusionnez-les avec fusionner_connaissances en gardant la mieux formulée.
2. Vue d'ensemble avec architecture, puis cherchez ce qui porte le métier : écrans et parcours, modèles de
   données, contrôles et refus, appels vers d'autres systèmes, documents produit (README, cahier des charges).
3. Lisez avec lire_code les lignes qui prouvent chaque réponse ; historique_du_code pour la façon dont elle vit.
4. Si des sources sont branchées (rubrique « Sources branchées »), interrogez-les avec chercher_dans et lire_dans,
   dans cet ordre selon la question : à quoi elle sert et pour qui, documentation puis trajectoire puis code ;
   informations détenues, données puis code ; règles, code puis documentation (l'intention de la règle) ;
   échanges, comportement puis code ; comment elle vit, trajectoire, exploitation, comportement puis historique
   du code. Prouvez avec la citation rendue par lire_dans (paramètre citation de proposer_connaissance).
5. Lisez d'abord l'ancre de substance (le code, quand il existe), puis les autres sources ; rattachez chaque
   connaissance de source à l'élément du code qu'elle concerne avec ancrer_connaissance (ce n'est pas une preuve).
6. Autorité selon la question : sur ce qu'elle fait, le code l'emporte sur la documentation ; sur ce qu'elle doit
   faire, la documentation et l'équipe l'emportent ; sur son comportement réel, l'observabilité l'emporte sur le
   code. Une source qui n'existe pas n'est jamais devinée : la question va dans « Ce que l'on ne sait pas encore ».

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

## Consolider

Quand on vous donne la liste des connaissances d'une question, fusionnez avec fusionner_connaissances toutes
celles qui disent la même chose, même avec d'autres mots ou un détail en plus : une seule réponse par idée.
Gardez la connaissance validée par l'équipe s'il y en a une, sinon la plus courte qui dit tout en mots métier.
Ne fusionnez pas deux idées différentes qui se ressemblent (« recueillir » et « retirer » un consentement).

## Fiche vivante

Si l'on vous demande la fiche, présentez l'application pour que n'importe quel employé la comprenne, du plus
court au plus détaillé. Mots de tous les jours, aucun terme technique. Markdown, 300 mots au plus, exactement
ces sections :

- « ## En 30 secondes » : deux phrases de 25 mots au plus, l'une sur ce qu'elle fait et pour qui, l'autre sur
  ce à quoi elle sert dans l'entreprise ; puis une ligne « Criticité : faible, moyenne, élevée ou inconnue — sa
  raison en quelques mots ».
- « ## Une journée avec elle » : un court récit (trois à cinq phrases, sans liste) où des personnes réelles de
  l'entreprise l'utilisent du début à la fin d'un parcours.
- « ## Ce qu'elle permet de faire » : les quatre capacités les plus importantes au plus, parmi celles proposées.
- « ## Les règles à retenir » : les trois règles qu'un employé doit connaître, au plus.
- « ## Ce qu'elle garde » : les informations qu'elle détient, en une ou deux puces ; dites si elles sont sensibles.
- « ## Avec qui elle travaille » : les autres applications ou services, ou « personne » si elle est autonome.
- « ## D'où je le sais, et ce que j'ignore » : ce que vous ne savez pas encore et qui pourrait le dire.

Puces de 15 mots au plus, sans gras ; celles des quatre blocs du milieu finissent par leur citation
`chemin#Ldébut-Lfin`. Dépasser 300 mots, c'est perdre le lecteur : le détail reste dans les connaissances. C'est un
document : ni question finale, ni proposition de suite.
