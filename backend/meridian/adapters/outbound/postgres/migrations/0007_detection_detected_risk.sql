-- Révision : 0007_detection_detected_risk
-- Convergence dev/cognition §2.2, phase 2 : le détecteur écrit désormais
-- statut=DETECTED (premier état du cycle d'émergence canonique) et type ses
-- risques en RISK au lieu de les stocker comme OPPORTUNITY.
--
-- 1) OPPORTUNITY de détecteur : PROPOSED → DETECTED. Seules les lignes portant
--    une ``signature`` de détecteur bougent ; une OPPORTUNITY humaine garde son
--    statut. Le vocabulaire cible est celui de STATUTS_OPPORTUNITE — PROPOSED
--    n'en faisait pas partie, l'objet était gelé pour les transitions.
UPDATE objet_entreprise
SET donnees = donnees || jsonb_build_object('statut', 'DETECTED')
WHERE type = 'OPPORTUNITY'
  AND donnees ? 'signature'
  AND donnees->>'statut' = 'PROPOSED';

-- 2) Les signatures de risque deviennent de vrais RISK. ``type_risque`` prend
--    la valeur canonique : un point unique de défaillance est un risque de
--    CONTINUITE, une dette critique un risque TECHNIQUE ; la clé legacy
--    ``type_opportunite`` est consolidée. La severite ELEVEE (hors vocabulaire
--    SEVERITES_RISQUE) est ramenée à HAUTE.
UPDATE objet_entreprise
SET type = 'RISK',
    donnees = (donnees - 'type_opportunite')
        || jsonb_build_object(
            'type_risque',
            CASE donnees->>'signature'
                WHEN 'concentration_risque' THEN 'CONTINUITE'
                ELSE 'TECHNIQUE'
            END)
        || CASE WHEN donnees->>'severite' = 'ELEVEE'
                THEN jsonb_build_object('severite', 'HAUTE')
                ELSE '{}'::jsonb
           END
WHERE type = 'OPPORTUNITY'
  AND donnees->>'signature' IN ('concentration_risque', 'dette_vs_usage');

-- Révision idempotente : une seconde exécution ne sélectionne rien (plus de
-- PROPOSED à signature, plus d'OPPORTUNITY aux signatures de risque).
