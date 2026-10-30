-- Couche cognitive du jumeau, phase 0 (Architecture Jumeau §5).
-- Idempotent, rejoué à chaque ingestion sous verrou consultatif.
-- ponytail: pas de migrations ; elles arrivent avec Aurora en phase 1 (aujourd'hui, réinitialiser la base de dev).

CREATE TABLE IF NOT EXISTS jumeau (
    id          text PRIMARY KEY,
    tenant_id   text NOT NULL,
    nom         text NOT NULL,
    equipe      text NOT NULL,
    cree_le     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS source (
    id          bigserial PRIMARY KEY,
    tenant_id   text NOT NULL,
    jumeau_id   text NOT NULL REFERENCES jumeau(id),
    type        text NOT NULL CHECK (type IN ('GIT', 'DOCUMENTATION')),
    nom         text NOT NULL,
    emplacement text NOT NULL,
    curseur     text,
    UNIQUE (jumeau_id, nom)
);

-- Preuve = Entity W3C PROV ; `activite` = Activity (extracteur, version). Pas de copie du contenu : hash seulement.
CREATE TABLE IF NOT EXISTS preuve (
    id          bigserial PRIMARY KEY,
    tenant_id   text NOT NULL,
    source_id   bigint NOT NULL REFERENCES source(id),
    type        text NOT NULL DEFAULT 'CODE',
    locator     text NOT NULL,
    chemin      text NOT NULL,
    sha         text NOT NULL,
    ligne_debut int  NOT NULL CHECK (ligne_debut >= 1),
    ligne_fin   int  NOT NULL CHECK (ligne_fin >= ligne_debut),
    hash        text NOT NULL,
    activite    jsonb NOT NULL,
    observee_le timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, locator)
);


-- Statut (gouvernance) et maturité (force des preuves) sont deux axes (Architecture Jumeau §7.1).
CREATE TABLE IF NOT EXISTS claim (
    id             bigserial PRIMARY KEY,
    tenant_id      text NOT NULL,
    jumeau_id      text NOT NULL REFERENCES jumeau(id),
    sujet          text NOT NULL,
    predicat       text NOT NULL,
    objet          text NOT NULL,
    type           text NOT NULL,
    statut         text NOT NULL DEFAULT 'PROPOSED'
                   CHECK (statut IN ('PROPOSED', 'ACCEPTED', 'CONTESTED', 'INVALIDATED', 'SUPERSEDED')),
    maturite       text NOT NULL DEFAULT 'M2' CHECK (maturite ~ '^M[0-5]$'),
    confiance      numeric(3, 2) NOT NULL CHECK (confiance BETWEEN 0 AND 1),
    valide_depuis  timestamptz NOT NULL DEFAULT now(),
    valide_jusqua  timestamptz,
    enregistre_le  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (jumeau_id, predicat, objet)
);

CREATE TABLE IF NOT EXISTS claim_preuve (
    claim_id  bigint NOT NULL REFERENCES claim(id),
    preuve_id bigint NOT NULL REFERENCES preuve(id),
    role      text NOT NULL DEFAULT 'SUPPORT' CHECK (role IN ('SUPPORT', 'CONTRE')),
    PRIMARY KEY (claim_id, preuve_id)
);

CREATE TABLE IF NOT EXISTS revue (
    id        bigserial PRIMARY KEY,
    tenant_id text NOT NULL,
    claim_id  bigint NOT NULL REFERENCES claim(id),
    acteur    text NOT NULL,
    decision  text NOT NULL CHECK (decision IN ('ACCEPTED', 'CONTESTED')),
    motif     text,
    le        timestamptz NOT NULL DEFAULT now()
);

-- Phase 0 bis : copie de travail au SHA et index de code persistants (conversation) ; origine des Claims.
ALTER TABLE jumeau ADD COLUMN IF NOT EXISTS domaine text NOT NULL DEFAULT 'À confirmer';
ALTER TABLE jumeau ADD COLUMN IF NOT EXISTS mission text;
ALTER TABLE source ADD COLUMN IF NOT EXISTS copie text;
ALTER TABLE source ADD COLUMN IF NOT EXISTS index_code text;
ALTER TABLE claim ADD COLUMN IF NOT EXISTS origine text NOT NULL DEFAULT 'INGESTION'
    CHECK (origine IN ('INGESTION', 'CONVERSATION'));

-- Fiche vivante : rédigée par le gardien à chaque commit, relue par Flore au début de chaque conversation.
CREATE TABLE IF NOT EXISTS fiche_vivante (
    jumeau_id text NOT NULL REFERENCES jumeau(id),
    sha       text NOT NULL,
    contenu   text NOT NULL,
    cree_le   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (jumeau_id, sha)
);

-- Plusieurs dépôts par jumeau, chacun sur sa branche ; URL et référence du jeton (jamais le jeton) pour le gardien.
ALTER TABLE source ADD COLUMN IF NOT EXISTS branche text;
ALTER TABLE source ADD COLUMN IF NOT EXISTS troncature jsonb;
ALTER TABLE source ADD COLUMN IF NOT EXISTS url text;
ALTER TABLE source ADD COLUMN IF NOT EXISTS secret_ref text;
-- Sources branchées autres que le code (lecteurs) : le CHECK d'origine ne connaît que GIT et DOCUMENTATION.
ALTER TABLE source DROP CONSTRAINT IF EXISTS source_type_check;
ALTER TABLE source ADD CONSTRAINT source_type_check CHECK (type IN ('GIT', 'DOCUMENTATION', 'CONFLUENCE', 'JIRA', 'SERVICENOW', 'DATADOG'));

-- Quelles sources observent encore chaque Claim : il n'est clos que quand plus aucune ne le voit.
CREATE TABLE IF NOT EXISTS claim_source (
    claim_id  bigint NOT NULL REFERENCES claim(id),
    source_id bigint NOT NULL REFERENCES source(id),
    PRIMARY KEY (claim_id, source_id)
);
CREATE INDEX IF NOT EXISTS claim_source_source ON claim_source (source_id);

-- Reprise des Claims créés avant claim_source : rattachés aux sources de leurs preuves, une seule fois (seuls ceux
-- qui n'ont encore aucun rattachement ; un rattachement retiré par une ingestion n'est jamais recréé ici).
INSERT INTO claim_source (claim_id, source_id)
SELECT DISTINCT cp.claim_id, p.source_id
FROM claim_preuve cp JOIN preuve p ON p.id = cp.preuve_id JOIN claim c ON c.id = cp.claim_id
WHERE c.valide_jusqua IS NULL AND c.origine = 'INGESTION'
  AND NOT EXISTS (SELECT 1 FROM claim_source cs WHERE cs.claim_id = c.id)
ON CONFLICT DO NOTHING;

-- Invariant 2 : aucun Claim ACCEPTED sans revue humaine (la revue s'écrit avant le changement de statut).
CREATE OR REPLACE FUNCTION claim_accepte_exige_revue() RETURNS trigger AS $$
BEGIN
    IF NEW.statut = 'ACCEPTED' AND NOT EXISTS (
        SELECT 1 FROM revue WHERE claim_id = NEW.id AND decision = 'ACCEPTED') THEN
        RAISE EXCEPTION 'claim % : ACCEPTED sans revue humaine', NEW.id;
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE OR REPLACE TRIGGER claim_accepte_exige_revue BEFORE INSERT OR UPDATE OF statut ON claim
    FOR EACH ROW EXECUTE FUNCTION claim_accepte_exige_revue();

-- Vérification d'une connaissance (Harness v3 §2), comme on teste : recette déterministe ou juge d'appui, distinct
-- de l'auteur. Ajout seul ; la dernière ligne d'une connaissance fait foi. `empreinte` = ses preuves au moment de la
-- vérification (une preuve est immuable) : une preuve nouvelle rejoue la vérification.
CREATE TABLE IF NOT EXISTS verification (
    id        bigserial PRIMARY KEY,
    claim_id  bigint NOT NULL REFERENCES claim(id),
    etat      text NOT NULL,
    methode   text NOT NULL CHECK (methode IN ('recette', 'juge')),
    systemes  text[] NOT NULL,
    empreinte text NOT NULL,
    raison    text CHECK (length(raison) <= 300),
    le        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS verification_claim ON verification (claim_id, id DESC);
-- « en_partie » (Harness v3 §2) : comme le Check Grounding de Google, une affirmation appuyée en partie n'est pas appuyée.
-- Recette de forme (plan L1bis.2) : 'ok' / 'absente' pour APPLIQUE_REGLE et DETIENT, NULL sinon.
ALTER TABLE verification ADD COLUMN IF NOT EXISTS forme text CHECK (forme IN ('ok', 'absente'));
-- Citations du juge, vérifiées mot pour mot par le harness (Harness v3 §2) : jsonb, liste de passages.
ALTER TABLE verification ADD COLUMN IF NOT EXISTS citations jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE verification DROP CONSTRAINT IF EXISTS verification_etat_check;
-- « en_attente » : toute connaissance naît avec un état explicite (plan de remédiation L1.6). Avant, 50 des 546
-- connaissances n'avaient aucune ligne de vérification, alors que le document affirmait que chacune en avait un.
ALTER TABLE verification ADD CONSTRAINT verification_etat_check
    CHECK (etat IN ('verifie', 'selon', 'recoupe', 'conteste', 'en_partie', 'non_appuye', 'incertain', 'en_attente'));
ALTER TABLE verification DROP CONSTRAINT IF EXISTS verification_methode_check;
ALTER TABLE verification ADD CONSTRAINT verification_methode_check
    CHECK (methode IN ('recette', 'juge', 'aucune'));

-- Maturité calculée, jamais déclarée (Jumeau Sources §5) : M1 sans preuve, M2 une preuve, M3 deux systèmes différents
-- (source.type : deux dépôts Git ne sont pas indépendants) **recoupés** — leurs preuves concordent, selon la dernière
-- vérification (Architecture : « deux sources indépendantes concordantes ») —, M4 = M3 + revue ACCEPTED.
-- Recalculée à chaque preuve, statut et vérification.
-- Le système d'une preuve : le type de sa source (git, confluence, jira, servicenow, datadog). Un fichier Markdown
-- du dépôt n'en est plus un à part : même commit, même équipe, il décrit le code qu'il accompagne — le compter comme
-- second système permettait d'atteindre M3 avec « un README approuve le code » (plan de remédiation L1.3).
-- Même règle que recoupement.systeme_de_preuve.
CREATE OR REPLACE FUNCTION systeme_de_preuve(type_preuve text, chemin text, type_source text) RETURNS text AS $$
    SELECT lower(coalesce(type_source, ''))
$$ LANGUAGE sql IMMUTABLE;
-- Les prédicats que l'ingestion **du code** peut établir (même liste que connaissance.PROUVABLES) : dépendance, route
-- exposée, variable lue, image exécutée. Pour les autres — ce que l'application fait pour le métier, les règles, les
-- acteurs, les échanges — une ligne de code ne dit rien : elle peut citer la phrase, pas l'établir.
-- Cette autorité est celle des sources (Sources v1 §2) : sur ce qu'elle *fait*, le code l'emporte ; sur ce qu'elle
-- *doit faire*, la documentation l'emporte. Une hypothèse prouvée uniquement par du code reste donc M1 ; une
-- connaissance établie par une source documentaire garde toute l'échelle, M3 compris.
CREATE OR REPLACE FUNCTION predicat_prouvable(predicat text) RETURNS boolean AS $$
    SELECT upper(coalesce(predicat, '')) IN ('DEPEND_DE', 'EXPOSE', 'LIT_VARIABLE', 'EXECUTE_IMAGE')
$$ LANGUAGE sql IMMUTABLE;
-- APPLIQUE_REGLE et DETIENT sortent de M1 si la recette de forme est « ok » ET le juge dit « selon » / « recoupe »
-- (même règle que connaissance.etabli_par_la_forme) : la forme seule ou le juge seul ne suffisent pas.
CREATE OR REPLACE FUNCTION etabli_par_la_forme(predicat text, forme text, etat text) RETURNS boolean AS $$
    SELECT upper(coalesce(predicat, '')) IN ('APPLIQUE_REGLE', 'DETIENT') AND coalesce(forme = 'ok', false)
           AND coalesce(etat IN ('selon', 'recoupe'), false)
$$ LANGUAGE sql IMMUTABLE;
CREATE OR REPLACE FUNCTION recalculer_maturite(cid bigint) RETURNS void AS $$
    UPDATE claim SET maturite = CASE
        WHEN s.preuves = 0 THEN 'M1'
        WHEN NOT predicat_prouvable(claim.predicat) AND s.preuves_code = s.preuves
             AND NOT coalesce(etabli_par_la_forme(claim.predicat, s.forme, s.etat_v), false) THEN 'M1'
        WHEN s.systemes >= 2 AND s.recoupe AND claim.statut = 'ACCEPTED' THEN 'M4'
        WHEN s.systemes >= 2 AND s.recoupe THEN 'M3'
        ELSE 'M2' END
    FROM (SELECT count(*) AS preuves, count(*) FILTER (WHERE p.type = 'CODE') AS preuves_code,
                 count(DISTINCT systeme_de_preuve(p.type, p.chemin, so.type)) AS systemes,
                 coalesce((SELECT v.etat = 'recoupe' FROM verification v WHERE v.claim_id = cid
                           ORDER BY v.id DESC LIMIT 1), false) AS recoupe,
                 (SELECT v.forme FROM verification v WHERE v.claim_id = cid ORDER BY v.id DESC LIMIT 1) AS forme,
                 (SELECT v.etat FROM verification v WHERE v.claim_id = cid ORDER BY v.id DESC LIMIT 1) AS etat_v
          FROM claim_preuve cp JOIN preuve p ON p.id = cp.preuve_id JOIN source so ON so.id = p.source_id
          WHERE cp.claim_id = cid AND cp.role = 'SUPPORT') s
    WHERE claim.id = cid;
$$ LANGUAGE sql;
CREATE OR REPLACE FUNCTION maturite_a_recalculer() RETURNS trigger AS $$
BEGIN
    IF TG_TABLE_NAME = 'claim' THEN
        PERFORM recalculer_maturite(NEW.id);
    ELSE
        PERFORM recalculer_maturite(NEW.claim_id);
    END IF;
    RETURN NULL;
END $$ LANGUAGE plpgsql;
-- La clôture d'une connaissance doit aussi rejouer sa maturité : 16 connaissances closes portaient encore M3.
CREATE OR REPLACE TRIGGER claim_maturite AFTER INSERT OR UPDATE OF statut, valide_jusqua ON claim
    FOR EACH ROW EXECUTE FUNCTION maturite_a_recalculer();
CREATE OR REPLACE TRIGGER claim_preuve_maturite AFTER INSERT ON claim_preuve
    FOR EACH ROW EXECUTE FUNCTION maturite_a_recalculer();
CREATE OR REPLACE TRIGGER verification_maturite AFTER INSERT ON verification
    FOR EACH ROW EXECUTE FUNCTION maturite_a_recalculer();

-- Toute connaissance naît avec son état : « non encore vérifiée », jamais rien du tout (L1.6).
CREATE OR REPLACE FUNCTION claim_etat_initial() RETURNS trigger AS $$
BEGIN
    INSERT INTO verification (claim_id, etat, methode, systemes, empreinte)
    VALUES (NEW.id, 'en_attente', 'aucune', '{}', '');
    RETURN NULL;
END $$ LANGUAGE plpgsql;
CREATE OR REPLACE TRIGGER claim_etat_initial AFTER INSERT ON claim
    FOR EACH ROW EXECUTE FUNCTION claim_etat_initial();

-- Deux sources de systèmes différents qui se contredisent : signalée par l'agent (citations vérifiées), tranchée par un humain.
CREATE TABLE IF NOT EXISTS contradiction (
    id          bigserial PRIMARY KEY,
    tenant_id   text NOT NULL,
    jumeau_id   text NOT NULL REFERENCES jumeau(id),
    claim_id    bigint REFERENCES claim(id),
    enonce      text NOT NULL,
    preuve_a    text NOT NULL,
    preuve_b    text NOT NULL,
    systeme_a   text NOT NULL,
    systeme_b   text NOT NULL CHECK (systeme_b <> systeme_a),
    statut      text NOT NULL DEFAULT 'OUVERTE' CHECK (statut IN ('OUVERTE', 'TRANCHEE')),
    signalee_par text NOT NULL,
    signalee_le timestamptz NOT NULL DEFAULT now(),
    tranchee_par text,
    tranchee_le  timestamptz,
    motif        text,
    CHECK (statut = 'OUVERTE' OR tranchee_par IS NOT NULL)
);
ALTER TABLE contradiction ADD COLUMN IF NOT EXISTS verdict text CHECK (verdict IN ('a', 'b', 'aucune'));
-- Une contradiction tranchée est immuable (comme une revue) et porte toujours son verdict ; jamais supprimée.
DO $$ BEGIN
    ALTER TABLE contradiction ADD CONSTRAINT contradiction_verdict_si_tranchee
        CHECK (statut = 'OUVERTE' OR verdict IS NOT NULL);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE OR REPLACE FUNCTION contradiction_immuable() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' OR OLD.statut = 'TRANCHEE' THEN
        RAISE EXCEPTION 'contradiction : décision immuable';
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE OR REPLACE TRIGGER contradiction_immuable BEFORE UPDATE OR DELETE ON contradiction
    FOR EACH ROW EXECUTE FUNCTION contradiction_immuable();
CREATE INDEX IF NOT EXISTS contradiction_jumeau ON contradiction (jumeau_id, statut);

-- Invariant 3 : preuves et revues sont immuables (ligne à ligne et TRUNCATE).
-- ponytail: un propriétaire de table peut désactiver ces triggers ; rôle applicatif sans DDL en phase 1.
CREATE OR REPLACE FUNCTION immuable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '% : enregistrement immuable', TG_TABLE_NAME;
END $$ LANGUAGE plpgsql;
CREATE OR REPLACE TRIGGER preuve_immuable BEFORE UPDATE OR DELETE ON preuve
    FOR EACH ROW EXECUTE FUNCTION immuable();
CREATE OR REPLACE TRIGGER preuve_sans_truncate BEFORE TRUNCATE ON preuve
    FOR EACH STATEMENT EXECUTE FUNCTION immuable();
CREATE OR REPLACE TRIGGER revue_immuable BEFORE UPDATE OR DELETE ON revue
    FOR EACH ROW EXECUTE FUNCTION immuable();
CREATE OR REPLACE TRIGGER revue_sans_truncate BEFORE TRUNCATE ON revue
    FOR EACH STATEMENT EXECUTE FUNCTION immuable();

CREATE INDEX IF NOT EXISTS revue_claim ON revue (claim_id, decision);
CREATE INDEX IF NOT EXISTS preuve_source ON preuve (source_id);
CREATE INDEX IF NOT EXISTS claim_preuve_preuve ON claim_preuve (preuve_id);
CREATE INDEX IF NOT EXISTS claim_valides ON claim (jumeau_id, type, predicat, objet) WHERE valide_jusqua IS NULL;

-- Ancrage : relie une connaissance issue d'une source (Jira, Confluence…) à l'endroit du code qu'elle concerne.
-- Ce n'est pas une preuve : jamais dans claim_preuve, donc jamais comptée dans la maturité.
CREATE TABLE IF NOT EXISTS ancre (
    id          bigserial PRIMARY KEY,
    tenant_id   text NOT NULL,
    claim_id    bigint NOT NULL REFERENCES claim(id),
    source_id   bigint NOT NULL REFERENCES source(id),
    chemin      text NOT NULL,
    ligne_debut int  NOT NULL CHECK (ligne_debut >= 1),
    ligne_fin   int  NOT NULL CHECK (ligne_fin >= ligne_debut),
    locator     text NOT NULL,
    raison      text NOT NULL,
    origine     text NOT NULL CHECK (origine IN ('AGENT', 'HARNESS')),
    cree_le     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (claim_id, locator)
);

-- Consignes de l'équipe (v3 §5) : instructions humaines, écrites avec leur pourquoi. Jamais supprimées ni modifiées ;
-- on les retire (retiree_le), l'historique reste.
CREATE TABLE IF NOT EXISTS consigne (
    id         bigserial PRIMARY KEY,
    tenant_id  text NOT NULL,
    portee     text NOT NULL CHECK (portee IN ('domaine', 'equipe', 'jumeau')),
    cible      text NOT NULL,
    texte      text NOT NULL CHECK (length(btrim(texte)) > 0 AND length(texte) <= 500),
    pourquoi   text NOT NULL CHECK (length(btrim(pourquoi)) > 0 AND length(pourquoi) <= 1000),
    auteur     text NOT NULL,
    origine    text NOT NULL DEFAULT 'HUMAIN' CHECK (origine IN ('HUMAIN', 'CONTESTATION')),
    cree_le    timestamptz NOT NULL DEFAULT now(),
    retiree_le timestamptz
);
CREATE INDEX IF NOT EXISTS consigne_cible ON consigne (tenant_id, portee, cible) WHERE retiree_le IS NULL;
CREATE OR REPLACE FUNCTION consigne_immuable() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' OR OLD.retiree_le IS NOT NULL
       OR (NEW.id, NEW.tenant_id, NEW.portee, NEW.cible, NEW.texte, NEW.pourquoi, NEW.auteur, NEW.origine, NEW.cree_le)
          IS DISTINCT FROM (OLD.id, OLD.tenant_id, OLD.portee, OLD.cible, OLD.texte, OLD.pourquoi, OLD.auteur, OLD.origine, OLD.cree_le) THEN
        RAISE EXCEPTION 'consigne : seul le retrait est permis';
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE OR REPLACE TRIGGER consigne_immuable BEFORE UPDATE OR DELETE ON consigne
    FOR EACH ROW EXECUTE FUNCTION consigne_immuable();

-- Évaluation : une passe du jeu de référence (Jumeau Harness v3 §6), pour suivre la tendance d'un changement de
-- méthode, de charte ou de modèle à l'autre.
CREATE TABLE IF NOT EXISTS evaluation (
    id                bigserial PRIMARY KEY,
    jumeau_id         text NOT NULL REFERENCES jumeau(id),
    quand             timestamptz NOT NULL DEFAULT now(),
    version_methodes  text NOT NULL,
    modele            text NOT NULL,
    scores            jsonb NOT NULL,
    details           jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS evaluation_jumeau ON evaluation (jumeau_id, quand DESC);

-- Graphe d'interfaces : contrats, opérations, points d'accès et assertions, par tenant. Les identifiants sont
-- calculés sur le contenu et ne portent pas le tenant : la clé est donc (tenant_id, id) pour que deux tenants
-- puissent décrire le même contrat sans se le voler ni le voir.
CREATE TABLE IF NOT EXISTS interface_contract (
    id             text NOT NULL,
    tenant_id      text NOT NULL,
    application_id text NOT NULL,
    format         text NOT NULL,
    version        text,
    digest         text NOT NULL,
    locator        text NOT NULL,
    environment    text NOT NULL,
    cree_le        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS interface_operation (
    id          text NOT NULL,
    tenant_id   text NOT NULL,
    contract_id text NOT NULL,
    protocol    text NOT NULL,
    method      text NOT NULL,
    path        text NOT NULL,
    name        text NOT NULL,
    version     text,
    environment text NOT NULL,
    cree_le     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, contract_id) REFERENCES interface_contract (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS interface_binding (
    id          text NOT NULL,
    tenant_id   text NOT NULL,
    protocol    text NOT NULL,
    url         text NOT NULL,
    environment text NOT NULL,
    gateway     text,
    cree_le     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id)
);

-- Une ligne = une preuve : la clé unique distingue le mode et la source, jamais une fusion sémantique.
CREATE TABLE IF NOT EXISTS interface_assertion (
    id          bigserial PRIMARY KEY,
    tenant_id   text NOT NULL,
    subject     text NOT NULL,
    predicate   text NOT NULL,
    object      text NOT NULL,
    mode        text NOT NULL CHECK (mode IN ('declared', 'observed', 'inferred')),
    source      text NOT NULL,
    locator     text NOT NULL,
    environment text NOT NULL,
    confidence  numeric(3, 2) NOT NULL,
    evidence    text NOT NULL,
    observed_at text,
    valid_from  text,
    valid_to    text,
    cree_le     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, subject, predicate, object, mode, source, locator, environment, evidence)
);

CREATE INDEX IF NOT EXISTS interface_contract_tenant ON interface_contract (tenant_id);
CREATE INDEX IF NOT EXISTS interface_contract_application ON interface_contract (tenant_id, application_id);
CREATE INDEX IF NOT EXISTS interface_operation_tenant ON interface_operation (tenant_id);
CREATE INDEX IF NOT EXISTS interface_operation_contract ON interface_operation (tenant_id, contract_id);
CREATE INDEX IF NOT EXISTS interface_binding_tenant ON interface_binding (tenant_id);
CREATE INDEX IF NOT EXISTS interface_assertion_tenant ON interface_assertion (tenant_id);
CREATE INDEX IF NOT EXISTS interface_assertion_subject ON interface_assertion (tenant_id, subject);
CREATE INDEX IF NOT EXISTS interface_assertion_predicate ON interface_assertion (tenant_id, predicate);
