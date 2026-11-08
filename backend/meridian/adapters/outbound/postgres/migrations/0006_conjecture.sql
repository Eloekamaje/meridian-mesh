-- Révision : 0006_conjecture
-- Convergence dev/cognition §2.1 : le type épistémique HYPOTHESIS est renommé
-- CONJECTURE — HYPOTHESIS reste le type du workflow d'exploitation (statuts
-- OPEN/STRENGTHENED/WEAKENED/REJECTED/CONFIRMED, investigation_id obligatoire).
-- Le vocabulaire de statut distingue les deux mondes : seules les lignes dont
-- le statut appartient au vocabulaire épistémique, ou qui portent les champs
-- propres aux conjectures (rival_ids, preuve_discriminante, need_id), migrent.
-- Le mapping inverse n'existe pas : une HYPOTHESIS workflow n'est jamais
-- réécrite. Révision idempotente : une seconde exécution ne sélectionne rien.
UPDATE objet_entreprise
SET type = 'CONJECTURE'
WHERE type = 'HYPOTHESIS'
  AND (
      donnees->>'statut' IN ('EMISE', 'TESTEE', 'RETENUE', 'REFUTEE')
      OR donnees ? 'rival_ids'
      OR donnees ? 'preuve_discriminante'
      OR donnees ? 'need_id'
  );

-- Le lien NEED → conjectures change de clé : donnees.hypothese_ids devient
-- donnees.conjecture_ids. La clé legacy reste lue côté code (rétro-lecture),
-- la migration la consolide pour que la donnée stockée soit canonique.
UPDATE objet_entreprise
SET donnees = (donnees - 'hypothese_ids')
    || jsonb_build_object('conjecture_ids', donnees->'hypothese_ids')
WHERE type = 'NEED'
  AND donnees ? 'hypothese_ids'
  AND NOT donnees ? 'conjecture_ids';
