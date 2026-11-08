-- Audit READ-ONLY des citations d'hypothèses des contributions d'expert.
--
-- Depuis C5f, une citation doit exister, être une HYPOTHESIS, appartenir au même
-- tenant et à la même Investigation que la contribution. Les contributions créées
-- avant C5f peuvent porter des citations jamais validées : elles bloquent toute
-- transition de statut (422) tant qu'elles ne sont pas corrigées HORS API.
--
-- L'audit couvre deux familles :
--   1. les tableaux de citations dont un identifiant est absent, d'un autre tenant,
--      d'un mauvais type ou d'une autre Investigation ;
--   2. les formes scalaires non nulles (chaîne, nombre, booléen, objet) qui ne sont
--      pas des tableaux : la transition les refuse aussi en 422.
--
-- Usage :
--   psql "$JUMEAU_PG_DSN" -f scripts/auditer-citations-contributions.sql
--
-- Filtre tenant optionnel (même session psql) :
--   psql "$JUMEAU_PG_DSN" \
--     -c "SET meridian.audit_tenant = 'local'" \
--     -f scripts/auditer-citations-contributions.sql
--
-- Aucune écriture. Une ligne retournée = citation ou forme à corriger manuellement.
-- Une sortie vide signifie qu'aucune contribution tableau/forme scalaire connue
-- n'est bloquée.

WITH contributions AS (
    SELECT
        c.tenant_id,
        c.id AS contribution_id,
        c.donnees->>'investigation_id' AS investigation_contribution,
        c.donnees->'hypothesis_ids_soutenues' AS soutenues,
        c.donnees->'hypothesis_ids_contestees' AS contestees
    FROM objet_entreprise AS c
    WHERE c.type = 'EXPERT_CONTRIBUTION'
      AND (
          NULLIF(current_setting('meridian.audit_tenant', true), '') IS NULL
          OR c.tenant_id = current_setting('meridian.audit_tenant', true)
      )
),
citations AS (
    SELECT
        contributions.tenant_id,
        contributions.contribution_id,
        contributions.investigation_contribution,
        cited.value AS hypothesis_id
    FROM contributions
    CROSS JOIN LATERAL jsonb_array_elements_text(
        CASE
            WHEN jsonb_typeof(contributions.soutenues) = 'array'
            THEN contributions.soutenues
            ELSE '[]'::jsonb
        END
        ||
        CASE
            WHEN jsonb_typeof(contributions.contestees) = 'array'
            THEN contributions.contestees
            ELSE '[]'::jsonb
        END
    ) AS cited(value)
    WHERE cited.value IS NOT NULL
),
formes_invalides AS (
    SELECT
        tenant_id,
        contribution_id,
        investigation_contribution,
        soutenues #>> '{}' AS hypothesis_id,
        'forme invalide (hypothesis_ids_soutenues)'::text AS motif_refus
    FROM contributions
    WHERE jsonb_typeof(soutenues) NOT IN ('array', 'null')
    UNION ALL
    SELECT
        tenant_id,
        contribution_id,
        investigation_contribution,
        contestees #>> '{}' AS hypothesis_id,
        'forme invalide (hypothesis_ids_contestees)'::text AS motif_refus
    FROM contributions
    WHERE jsonb_typeof(contestees) NOT IN ('array', 'null')
)
SELECT
    citations.tenant_id,
    citations.contribution_id,
    citations.hypothesis_id,
    citations.investigation_contribution,
    h.type AS type_trouve,
    h.tenant_id AS tenant_hypothese,
    h.donnees->>'investigation_id' AS investigation_hypothese,
    CASE
        WHEN h.id IS NULL THEN 'hypothèse absente, autre tenant ou mauvais type'
        ELSE 'investigation différente'
    END AS motif_refus
FROM citations
LEFT JOIN objet_entreprise AS h
    ON h.tenant_id = citations.tenant_id
   AND h.id = citations.hypothesis_id
   AND h.type = 'HYPOTHESIS'
WHERE h.id IS NULL
   OR h.donnees->>'investigation_id'
      IS DISTINCT FROM citations.investigation_contribution
UNION ALL
SELECT
    formes_invalides.tenant_id,
    formes_invalides.contribution_id,
    formes_invalides.hypothesis_id,
    formes_invalides.investigation_contribution,
    NULL::text AS type_trouve,
    NULL::text AS tenant_hypothese,
    NULL::text AS investigation_hypothese,
    formes_invalides.motif_refus
FROM formes_invalides
ORDER BY tenant_id, contribution_id, hypothesis_id;
