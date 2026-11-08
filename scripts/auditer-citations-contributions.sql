-- Audit READ-ONLY des citations d'hypothèses des contributions d'expert.
--
-- Depuis C5f, une citation doit exister, être une HYPOTHESIS, appartenir au même
-- tenant et à la même Investigation que la contribution. Les contributions créées
-- avant C5f peuvent porter des citations jamais validées : elles bloquent toute
-- transition de statut (422) tant qu'elles ne sont pas corrigées HORS API.
--
-- Usage :
--   psql "$JUMEAU_PG_DSN" -f scripts/auditer-citations-contributions.sql
--
-- Filtre tenant optionnel (même session psql) :
--   psql "$JUMEAU_PG_DSN" \
--     -c "SET meridian.audit_tenant = 'local'" \
--     -f scripts/auditer-citations-contributions.sql
--
-- Aucune écriture. Une ligne retournée = citation à corriger manuellement.
-- Une sortie vide signifie qu'aucune contribution existante n'est bloquée.

WITH contributions AS (
    SELECT
        c.tenant_id,
        c.id AS contribution_id,
        c.donnees->>'investigation_id' AS investigation_contribution,
        CASE
            WHEN jsonb_typeof(c.donnees->'hypothesis_ids_soutenues') = 'array'
            THEN c.donnees->'hypothesis_ids_soutenues'
            ELSE '[]'::jsonb
        END
        ||
        CASE
            WHEN jsonb_typeof(c.donnees->'hypothesis_ids_contestees') = 'array'
            THEN c.donnees->'hypothesis_ids_contestees'
            ELSE '[]'::jsonb
        END AS citations
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
        contributions.citations
    ) AS cited(value)
    WHERE cited.value IS NOT NULL
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
ORDER BY citations.tenant_id, citations.contribution_id, citations.hypothesis_id;
