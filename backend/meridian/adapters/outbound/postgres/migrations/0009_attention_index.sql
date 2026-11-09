-- Révision : 0009_attention_index
-- Convergence dev/cognition §5.5, phase 4 : ``donnees.attention`` devient, avec
-- les intentions ``memoire_prospective`` échues, le store canonique du fil
-- d'attention (``GET /api/boucle/attention``). L'index partiel borne le
-- balayage aux seules lignes signalées — un parcours jsonb complet serait le
-- prix du canal unique sans lui.

CREATE INDEX IF NOT EXISTS idx_objet_entreprise_attention
    ON objet_entreprise (tenant_id, type)
    WHERE donnees ? 'attention';

-- Révision idempotente : IF NOT EXISTS rend la réexécution sans effet.
