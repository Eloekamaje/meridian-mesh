# Méridian — Backlog priorisé et prochaines tâches

## Backlog priorisé
- **P0** : — (rien de bloquant).
- **P1** : Polaris Lot 3 (scénarios Ligne d'affaires « traite en succursale » + Architecte « décommissionner MD2 ») et Lot 4 (Support TI + Développeur) — mêmes patterns que le Gestionnaire (fixtures + scénario + scènes, zéro nouveau composant UI) ; Flore sur vrai LLM via clé universelle Emergent (utilisateur : « mime le LLM pour le moment ») ; auto-régénération de la « Compréhension actuelle » quand un travail passe « À revoir » ; valider manuellement le lasso en union sur un vrai navigateur.
- **P2** : Polaris Lot 5 (responsive <1200 px du kiosque, tests limites) ; « Expliquer cette carte » (accessibilité WCAG : résumé textuel structuré de la vue courante) ; rejeu temporel complet de l'Atlas (Direct/Pause/Replay historique, distinct de Polaris) ; surfaces génératives dynamiques dans les Travaux (fragment Atlas intégré, matrice d'impact, avant/après, scénarios nommables/partageables) ; investigation agentique observable ; split de seed_data.py ; migration `on_event` → lifespan FastAPI ; durcissement CORS production ; persistance sessionStorage du contexte Flore.
- **P3** : rapport « Aperçu » d'un travail exportable/partageable (lien public en lecture seule ou PDF).
- **Si vraie IA un jour** : brancher Flore sur un LLM via la clé universelle Emergent (budget : Profile → Manage plan → Universal Key).

## Prochaines tâches
1. Faire valider par l'utilisateur le kiosque Polaris réel (parcours Gestionnaire de bout en bout : `/demo` → Gestionnaire).
2. Polaris Lot 3 : scénarios Ligne d'affaires + Architecte (fixtures + scènes, aucune nouvelle UI).
3. Flore LLM réel (P1) si l'utilisateur valide.
