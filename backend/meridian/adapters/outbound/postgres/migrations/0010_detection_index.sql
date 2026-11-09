-- Révision : 0010_detection_index
-- Convergence dev/cognition, phase 5 (hygiène) : les détecteurs dédupliquent
-- leurs écritures par ``donnees->>'signature'`` et ``donnees->>'sujet_detection'``
-- (detecteur_opportunites, detecteurs_besoins). Sans index, chaque balayage
-- relit la table entière en filtre jsonb — le coût croît avec le socle.

CREATE INDEX IF NOT EXISTS idx_objet_entreprise_signature
    ON objet_entreprise (tenant_id, (donnees->>'signature'))
    WHERE donnees ? 'signature';

CREATE INDEX IF NOT EXISTS idx_objet_entreprise_sujet_detection
    ON objet_entreprise (tenant_id, (donnees->>'sujet_detection'))
    WHERE donnees ? 'sujet_detection';

-- Révision idempotente : IF NOT EXISTS rend la réexécution sans effet.
