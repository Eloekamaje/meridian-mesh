-- Révision : 0008_decision_parent
-- Convergence dev/cognition §3.2, phase 3 : une DECISION sans investigation_id
-- est un trou de causalité, pas une souplesse. Les orphelines produites par
-- l'ancien chemin ``decision_travail`` (écriture directe hors ``enregistrer_boucle``)
-- sont reprises : rattachées à l'INVESTIGATION de leur épisode quand elle est
-- identifiable sans ambiguïté, sinon marquées ``parent_manquant`` — le chemin
-- boucle refuse déjà leur réécriture sans ``investigation_id``, seul le lien
-- peut les réparer.

-- 1) Rattachement : l'épisode de la DECISION désigne exactement une INVESTIGATION
--    du tenant (donnees.episode_id partagé). Les épisodes ambigus (plusieurs
--    investigations) sont laissés au marquage.
WITH uniques AS (
    SELECT tenant_id, donnees->>'episode_id' AS episode_id,
           count(*) AS n, min(id) AS investigation_id
    FROM objet_entreprise
    WHERE type = 'INVESTIGATION'
      AND COALESCE(donnees->>'episode_id', '') <> ''
    GROUP BY tenant_id, donnees->>'episode_id'
    HAVING count(*) = 1
)
UPDATE objet_entreprise d
SET donnees = d.donnees || jsonb_build_object('investigation_id', u.investigation_id)
FROM uniques u
WHERE d.type = 'DECISION'
  AND d.tenant_id = u.tenant_id
  AND d.donnees->>'episode_id' = u.episode_id
  AND COALESCE(d.donnees->>'investigation_id', '') = '';

-- 2) Marquage : les orphelines irrésolubles portent ``parent_manquant`` — toute
--    mutation hors lien est refusée par ``enregistrer_boucle`` (investigation_id
--    obligatoire), seule la réparation du lien les débloque.
UPDATE objet_entreprise
SET donnees = donnees || jsonb_build_object('parent_manquant', true)
WHERE type = 'DECISION'
  AND COALESCE(donnees->>'investigation_id', '') = ''
  AND NOT donnees ? 'parent_manquant';

-- Révision idempotente : une seconde exécution ne rattache ni ne marque rien.
