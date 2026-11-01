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
-- Configuration d'une source runtime (OTLP) : url, secret_ref, environnement, fréquence ; jamais le secret brut.
ALTER TABLE source ADD COLUMN IF NOT EXISTS configuration jsonb;
-- Sources branchées autres que le code (lecteurs, OTLP) : le CHECK d'origine ne connaît que GIT et DOCUMENTATION.
ALTER TABLE source DROP CONSTRAINT IF EXISTS source_type_check;
ALTER TABLE source ADD CONSTRAINT source_type_check CHECK (type IN ('GIT', 'DOCUMENTATION', 'CONFLUENCE', 'JIRA', 'SERVICENOW', 'DATADOG', 'OTLP'));

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

-- Journal d'une découverte : un run est un processus daté, avec son statut, ses compteurs, ses changements et ses
-- impacts. `changes` et `impacts` gardent la preuve telle qu'elle a été produite, même si une opération disparaît
-- ensuite du graphe courant.
CREATE TABLE IF NOT EXISTS discovery_run (
    id             text PRIMARY KEY,
    tenant_id      text NOT NULL,
    application_id text NOT NULL,
    source         text NOT NULL,
    environment    text NOT NULL,
    started_at     timestamptz NOT NULL,
    ended_at       timestamptz,
    status         text NOT NULL CHECK (status IN ('ok', 'partial', 'error')),
    stats          jsonb NOT NULL DEFAULT '{}'::jsonb,
    changes        jsonb NOT NULL DEFAULT '[]'::jsonb,
    impacts        jsonb NOT NULL DEFAULT '[]'::jsonb,
    error          text,
    cree_le        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS discovery_run_tenant_application
    ON discovery_run (tenant_id, application_id, started_at DESC);

-- Promotion d'un twin provisoire en application : décision humaine, identité de l'application inchangée (même id),
-- trace auditée de ce qui a changé. Aucune auto-promotion : la ligne est écrite par le dépôt d'identité.
CREATE TABLE IF NOT EXISTS identity_decision (
    id         bigserial PRIMARY KEY,
    tenant_id  text NOT NULL,
    jumeau_id  text NOT NULL REFERENCES jumeau(id),
    acteur     text NOT NULL,
    action     text NOT NULL,
    avant      jsonb NOT NULL,
    apres      jsonb NOT NULL,
    preuve     jsonb,
    cree_le    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS identity_decision_tenant_jumeau
    ON identity_decision (tenant_id, jumeau_id);


-- ---------------------------------------------------------------------------
-- Postgres canonique des Claims, preuves, sources, temporalité et recherche.
-- La topologie du Mesh (Twins, relations, domaines, capacités, processus,
-- parcours, situations) est possédée par le graph store (ADR-0007).
-- Aucune projection du même objet entre les deux stores.
-- ---------------------------------------------------------------------------
ALTER TABLE jumeau ADD COLUMN IF NOT EXISTS type text NOT NULL DEFAULT 'APPLICATION'
    CHECK (type IN ('APPLICATION', 'PROCESS', 'CAPABILITY', 'JOURNEY', 'ORGANIZATION', 'PRODUCT', 'DATA_DOMAIN'));
ALTER TABLE claim ADD COLUMN IF NOT EXISTS mode text NOT NULL DEFAULT 'DECLARED'
    CHECK (mode IN ('DECLARED', 'OBSERVED', 'INFERRED', 'PROPOSED', 'CONFIRMED'));

CREATE INDEX IF NOT EXISTS jumeau_texte ON jumeau USING GIN (
    to_tsvector('french', coalesce(nom, '') || ' ' || coalesce(mission, ''))
);
CREATE INDEX IF NOT EXISTS claim_texte ON claim USING GIN (
    to_tsvector('french', coalesce(sujet, '') || ' ' || coalesce(predicat, '') || ' ' || coalesce(objet, ''))
);

-- ---------------------------------------------------------------------------
-- P0-A : socle d'entreprise. Un objet typé appartient à une des huit familles,
-- porte un mode de connaissance et une temporalité, et vit sous son tenant.
-- La clé (tenant_id, id) permet à deux tenants de nommer le même objet sans se
-- le voler ni le voir.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS objet_entreprise (
    id            text NOT NULL,
    tenant_id     text NOT NULL,
    famille       text NOT NULL CHECK (famille IN (
                      'identite_structure', 'sources_preuves', 'connaissance', 'emergence',
                      'investigation', 'decision', 'resultat_apprentissage', 'interaction_gouvernance')),
    type          text NOT NULL,
    mode          text NOT NULL CHECK (mode IN ('DECLARED', 'OBSERVED', 'INFERRED', 'PROPOSED', 'CONFIRMED')),
    titre         text NOT NULL DEFAULT '',
    donnees       jsonb NOT NULL DEFAULT '{}'::jsonb,
    version       int NOT NULL DEFAULT 1 CHECK (version >= 1),
    observe_le    timestamptz NOT NULL DEFAULT now(),
    valide_depuis timestamptz NOT NULL DEFAULT now(),
    valide_jusqua timestamptz,
    cree_le       timestamptz NOT NULL DEFAULT now(),
    maj_le        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id),
    CHECK (valide_jusqua IS NULL OR valide_jusqua >= valide_depuis)
);
CREATE INDEX IF NOT EXISTS objet_entreprise_tenant_famille_type
    ON objet_entreprise (tenant_id, famille, type);
CREATE INDEX IF NOT EXISTS objet_entreprise_tenant_validite
    ON objet_entreprise (tenant_id, valide_depuis, valide_jusqua);

-- ---------------------------------------------------------------------------
-- P0-B : contrat Claim complet. L'unicité (jumeau_id, predicat, objet) reste
-- inchangée ; version et remplace_id ajoutent l'historique de remplacement.
-- ---------------------------------------------------------------------------
ALTER TABLE claim ADD COLUMN IF NOT EXISTS version int NOT NULL DEFAULT 1;
ALTER TABLE claim ADD COLUMN IF NOT EXISTS remplace_id bigint;
DO $$ BEGIN
    ALTER TABLE claim ADD CONSTRAINT claim_version_positive CHECK (version >= 1);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Un Claim ACCEPTED exige une preuve de soutien, en plus de la revue humaine.
-- Le trigger de revue (claim_accepte_exige_revue) reste en place.
CREATE OR REPLACE FUNCTION claim_accepte_exige_preuve() RETURNS trigger AS $$
BEGIN
    IF NEW.statut = 'ACCEPTED' AND NOT EXISTS (
        SELECT 1 FROM claim_preuve WHERE claim_id = NEW.id AND role = 'SUPPORT') THEN
        RAISE EXCEPTION 'claim % : ACCEPTED sans preuve SUPPORT', NEW.id;
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE OR REPLACE TRIGGER claim_accepte_exige_preuve BEFORE INSERT OR UPDATE OF statut ON claim
    FOR EACH ROW EXECUTE FUNCTION claim_accepte_exige_preuve();

-- ---------------------------------------------------------------------------
-- Audit des appels d'outils (ADR-0004) : append-only, tenant-scopé, sans
-- contenu sensible. Une ligne par découverte, chargement ou appel ; jamais de
-- mise à jour ni de suppression. L'idempotence couvre une ligne rejouée avec
-- le même horodatage, pas deux appels distincts.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS outil_audit (
    id         bigserial PRIMARY KEY,
    tenant_id  text NOT NULL,
    outil      text NOT NULL,
    capacite   text,
    acteur     text NOT NULL,
    arguments  jsonb NOT NULL DEFAULT '{}'::jsonb,
    duree_ms   double precision NOT NULL DEFAULT 0 CHECK (duree_ms >= 0),
    statut     text NOT NULL,
    erreur     text,
    quand      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS outil_audit_tenant_quand
    ON outil_audit (tenant_id, quand DESC);
CREATE INDEX IF NOT EXISTS outil_audit_tenant_outil_quand
    ON outil_audit (tenant_id, outil, quand DESC);
CREATE UNIQUE INDEX IF NOT EXISTS outil_audit_idempotence
    ON outil_audit (tenant_id, outil, coalesce(capacite, ''), acteur, md5(arguments::text),
                    duree_ms, statut, coalesce(erreur, ''), quand);
CREATE OR REPLACE TRIGGER outil_audit_immuable BEFORE UPDATE OR DELETE ON outil_audit
    FOR EACH ROW EXECUTE FUNCTION immuable();
CREATE OR REPLACE TRIGGER outil_audit_sans_truncate BEFORE TRUNCATE ON outil_audit
    FOR EACH STATEMENT EXECUTE FUNCTION immuable();

-- ---------------------------------------------------------------------------
-- Value Ledger : valeur attendue, observée, attribuée et réalisée.
-- Bounded context distinct des huit familles d'entreprise (ADR-0009).
-- Une ligne relie une décision/initiative/outcome à une hypothèse de valeur.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS valeur (
    id                  text NOT NULL,
    tenant_id           text NOT NULL,
    type                text NOT NULL,
    libelle             text NOT NULL,
    proprietaire        text NOT NULL,
    beneficiaire        text,
    domaine             text,
    objet_source_type   text,
    objet_source_id     text,
    baseline            jsonb,
    cible               jsonb,
    observe             jsonb,
    unite               text,
    devise              text,
    periode             text,
    attribution         text NOT NULL DEFAULT 'inconnue'
        CHECK (attribution IN ('directe', 'contribution', 'activation', 'inconnue')),
    confiance           double precision NOT NULL DEFAULT 0.5
        CHECK (confiance >= 0 AND confiance <= 1),
    preuves             jsonb NOT NULL DEFAULT '[]',
    fraicheur           jsonb,
    cout                jsonb,
    risque              jsonb,
    statut              text NOT NULL DEFAULT 'hypothese'
        CHECK (statut IN ('hypothese', 'mesuree', 'validee', 'realisee', 'deplacee', 'detruite', 'abandonnee')),
    date_revue          date,
    donnees             jsonb NOT NULL DEFAULT '{}',
    cree_le             timestamptz NOT NULL DEFAULT now(),
    maj_le              timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id)
);
CREATE INDEX IF NOT EXISTS valeur_tenant_statut ON valeur (tenant_id, statut);
CREATE INDEX IF NOT EXISTS valeur_tenant_domaine ON valeur (tenant_id, domaine);
CREATE INDEX IF NOT EXISTS valeur_objet ON valeur (tenant_id, objet_source_type, objet_source_id);

-- ---------------------------------------------------------------------------
-- Mémoire durable : session, préférence, contexte, décision ou apprentissage.
-- Portée explicite, consentement et rétention ; le tenant est la frontière.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memoire_durable (
    id            text NOT NULL,
    tenant_id     text NOT NULL,
    scope         text NOT NULL CHECK (scope IN ('user', 'session', 'twin', 'situation')),
    scope_id      text NOT NULL,
    classe        text NOT NULL CHECK (classe IN ('session', 'preference', 'contexte', 'decision', 'apprentissage')),
    contenu       text NOT NULL,
    provenance    text NOT NULL,
    consentement  boolean NOT NULL DEFAULT false,
    consenti_le   timestamptz,
    expire_le     timestamptz NOT NULL,
    confiance     double precision NOT NULL DEFAULT 0.5 CHECK (confiance >= 0 AND confiance <= 1),
    donnees       jsonb NOT NULL DEFAULT '{}',
    cree_le       timestamptz NOT NULL DEFAULT now(),
    maj_le        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id)
);
CREATE INDEX IF NOT EXISTS memoire_durable_scope ON memoire_durable (tenant_id, scope, scope_id);
CREATE INDEX IF NOT EXISTS memoire_durable_expire ON memoire_durable (tenant_id, expire_le);

-- ---------------------------------------------------------------------------
-- Calibration : confiance annoncée et outcome observé d'une décision.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prediction_calibration (
    id          text NOT NULL,
    tenant_id   text NOT NULL,
    decision_id text NOT NULL,
    confidence  double precision NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    outcome     boolean,
    cree_le     timestamptz NOT NULL DEFAULT now(),
    resolue_le  timestamptz,
    PRIMARY KEY (tenant_id, id)
);
CREATE INDEX IF NOT EXISTS prediction_calibration_decision
    ON prediction_calibration (tenant_id, decision_id);

-- ---------------------------------------------------------------------------
-- Exécution durable : runs, événements, outbox et timers.
-- Postgres est la source de vérité ; Redis n'est qu'un accélérateur.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS execution_run (
    tenant_id          text NOT NULL,
    run_id             text NOT NULL,
    command_id         text NOT NULL,
    type               text NOT NULL,
    idempotency_key    text NOT NULL,
    payload            jsonb NOT NULL DEFAULT '{}',
    payload_empreinte  text,
    etat               text NOT NULL DEFAULT 'QUEUED'
                       CHECK (etat IN ('QUEUED', 'RUNNING', 'WAITING_RETRY', 'WAITING_APPROVAL', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'EXPIRED')),
    priorite           text NOT NULL DEFAULT 'standard'
                       CHECK (priorite IN ('interactive', 'standard', 'batch')),
    acteur             text NOT NULL DEFAULT 'systeme',
    correlation_id     text,
    causation_id       text,
    deadline_at        timestamptz,
    cancel_requested_at timestamptz,
    bail_proprietaire  text,
    bail_jusqu_a       timestamptz,
    fencing_token      bigint NOT NULL DEFAULT 0,
    tentative          int NOT NULL DEFAULT 0 CHECK (tentative >= 0),
    max_tentatives     int NOT NULL DEFAULT 3 CHECK (max_tentatives >= 1),
    resultat           jsonb,
    erreur             text,
    cree_le            timestamptz NOT NULL DEFAULT now(),
    demarre_le         timestamptz,
    fini_le            timestamptz,
    maj_le             timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, run_id),
    UNIQUE (tenant_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS execution_run_file
    ON execution_run (etat, priorite, cree_le);
CREATE INDEX IF NOT EXISTS execution_run_deadline
    ON execution_run (etat, deadline_at);
ALTER TABLE execution_run ADD COLUMN IF NOT EXISTS payload_empreinte text;

CREATE TABLE IF NOT EXISTS execution_evenement (
    id        bigserial PRIMARY KEY,
    tenant_id text NOT NULL,
    run_id    text NOT NULL,
    type      text NOT NULL,
    donnees   jsonb NOT NULL DEFAULT '{}',
    cree_le   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS execution_evenement_run
    ON execution_evenement (tenant_id, run_id, id);

CREATE TABLE IF NOT EXISTS execution_outbox (
    id         bigserial PRIMARY KEY,
    tenant_id  text NOT NULL,
    run_id     text NOT NULL,
    type       text NOT NULL,
    payload    jsonb NOT NULL DEFAULT '{}',
    cree_le    timestamptz NOT NULL DEFAULT now(),
    publie_le  timestamptz,
    tentatives int NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS execution_outbox_a_publier
    ON execution_outbox (publie_le, id);

CREATE TABLE IF NOT EXISTS execution_timer (
    id        bigserial PRIMARY KEY,
    tenant_id text NOT NULL,
    run_id    text NOT NULL,
    type      text NOT NULL,
    due_at     timestamptz NOT NULL,
    payload   jsonb NOT NULL DEFAULT '{}',
    traite_le timestamptz
);
CREATE INDEX IF NOT EXISTS execution_timer_du
    ON execution_timer (traite_le, due_at);


-- Effets gouvernés : un effet par (run, étape, cible, opération). La clé composite rend
-- l'exécution rejouable sans double appel ; le statut trace la décision humaine.
CREATE TABLE IF NOT EXISTS execution_effet (
    tenant_id  text NOT NULL,
    run_id     text NOT NULL,
    etape      text NOT NULL,
    cible      text NOT NULL,
    operation  text NOT NULL,
    outil      text NOT NULL,
    politique  text NOT NULL CHECK (politique IN ('lecture', 'ecriture')),
    statut     text NOT NULL DEFAULT 'PROPOSE'
               CHECK (statut IN ('PROPOSE', 'APPROUVE', 'EXECUTE', 'REJETE')),
    payload    jsonb NOT NULL DEFAULT '{}',
    resultat   jsonb,
    erreur     text,
    tentatives int NOT NULL DEFAULT 0 CHECK (tentatives >= 0),
    cree_le    timestamptz NOT NULL DEFAULT now(),
    maj_le     timestamptz NOT NULL DEFAULT now(),
    execute_le timestamptz,
    PRIMARY KEY (tenant_id, run_id, etape, cible, operation)
);
CREATE INDEX IF NOT EXISTS execution_effet_run
    ON execution_effet (tenant_id, run_id);

-- Demande d'approbation durable : elle survit au redémarrage du worker et porte la
-- décision (acteur, motif, dates) séparément de l'effet qu'elle autorise.
CREATE TABLE IF NOT EXISTS execution_approbation (
    id         bigserial PRIMARY KEY,
    tenant_id  text NOT NULL,
    run_id     text NOT NULL,
    etape      text NOT NULL,
    outil      text NOT NULL,
    cible      text NOT NULL,
    operation  text NOT NULL,
    payload    jsonb NOT NULL DEFAULT '{}',
    statut     text NOT NULL DEFAULT 'PROPOSE'
               CHECK (statut IN ('PROPOSE', 'APPROUVE', 'REJETE')),
    demandeur  text NOT NULL,
    acteur     text,
    motif      text,
    cree_le    timestamptz NOT NULL DEFAULT now(),
    decide_le  timestamptz,
    UNIQUE (tenant_id, run_id, etape, cible, operation)
);
CREATE INDEX IF NOT EXISTS execution_approbation_run
    ON execution_approbation (tenant_id, run_id, statut);

-- Journal d'étapes d'un run multi-étapes. `seq` fixe l'ordre ; `sortie` est le
-- checkpoint relu après un crash pour ne pas rejouer une étape TERMINE.
CREATE TABLE IF NOT EXISTS execution_etape (
    tenant_id  text NOT NULL,
    run_id     text NOT NULL,
    seq        int NOT NULL CHECK (seq >= 0),
    nom        text NOT NULL,
    etat       text NOT NULL DEFAULT 'EN_ATTENTE'
               CHECK (etat IN ('EN_ATTENTE', 'EN_COURS', 'TERMINE', 'ECHEC', 'ANNULE', 'SUSPENDU')),
    entree     jsonb NOT NULL DEFAULT '{}',
    sortie     jsonb,
    erreur     text,
    cree_le    timestamptz NOT NULL DEFAULT now(),
    demarre_le timestamptz,
    fini_le    timestamptz,
    maj_le     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, run_id, seq),
    UNIQUE (tenant_id, run_id, nom)
);
CREATE INDEX IF NOT EXISTS execution_etape_run
    ON execution_etape (tenant_id, run_id, seq);
CREATE INDEX IF NOT EXISTS execution_etape_etat
    ON execution_etape (tenant_id, etat);


-- Nettoyage des tables d'exécution sans consommateur (pilote).
DROP TABLE IF EXISTS execution_inbox;
ALTER TABLE execution_run DROP COLUMN IF EXISTS expected_version;
ALTER TABLE execution_run DROP CONSTRAINT IF EXISTS execution_run_etat_check;
ALTER TABLE execution_run ADD CONSTRAINT execution_run_etat_check
    CHECK (etat IN ('QUEUED', 'RUNNING', 'WAITING_RETRY', 'WAITING_APPROVAL', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'EXPIRED'));


-- Alimentation continue pull-first des jumeaux : chaque source suivie a une échéance durable. Aucun webhook :
-- le worker relit les sources dues, réclame un run sous bail et repousse l'échéance. Le bail et le fencing
-- empêchent deux workers de committer le même run ; `tentative` compte les échecs consécutifs de la source.
CREATE TABLE IF NOT EXISTS source_schedule (
    tenant_id         text NOT NULL,
    source_id         bigint NOT NULL REFERENCES source(id) ON DELETE CASCADE,
    jumeau_id         text NOT NULL REFERENCES jumeau(id),
    intervalle_s      int NOT NULL DEFAULT 3600 CHECK (intervalle_s > 0),
    next_run_at       timestamptz NOT NULL DEFAULT now(),
    last_run_at       timestamptz,
    last_success_at   timestamptz,
    last_error        text,
    etat              text NOT NULL DEFAULT 'active' CHECK (etat IN ('active', 'paused')),
    bail_proprietaire text,
    bail_jusqu_a      timestamptz,
    fencing_token     bigint NOT NULL DEFAULT 0 CHECK (fencing_token >= 0),
    tentative         int NOT NULL DEFAULT 0 CHECK (tentative >= 0),
    max_tentatives    int NOT NULL DEFAULT 5 CHECK (max_tentatives >= 1),
    cree_le           timestamptz NOT NULL DEFAULT now(),
    maj_le            timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, source_id)
);
CREATE INDEX IF NOT EXISTS source_schedule_du
    ON source_schedule (etat, next_run_at);

-- Un run d'ingestion par source suivie. Les états intermédiaires sont observables par l'API ; `previous_sha` et
-- `observed_sha` rendent le changement de version vérifiable sans relire la source. `metriques` est un JSON libre
-- (durée, dépôts, signaux), jamais une URL ni un secret.
CREATE TABLE IF NOT EXISTS ingestion_run (
    id             text PRIMARY KEY,
    tenant_id      text NOT NULL,
    source_id      bigint NOT NULL REFERENCES source(id) ON DELETE CASCADE,
    jumeau_id      text NOT NULL REFERENCES jumeau(id),
    previous_sha   text,
    observed_sha   text,
    etat           text NOT NULL DEFAULT 'QUEUED'
                   CHECK (etat IN ('QUEUED', 'FETCHING', 'INDEXING', 'EXTRACTING', 'PROJECTING',
                                   'SUCCEEDED', 'FAILED', 'RETRY_WAIT', 'CANCELLED')),
    tentative      int NOT NULL DEFAULT 0 CHECK (tentative >= 0),
    max_tentatives int NOT NULL DEFAULT 5 CHECK (max_tentatives >= 1),
    erreur         text,
    cree_le        timestamptz NOT NULL DEFAULT now(),
    demarre_le     timestamptz,
    fini_le        timestamptz,
    maj_le         timestamptz NOT NULL DEFAULT now(),
    next_attempt_at timestamptz,
    bail_proprietaire text,
    bail_jusqu_a   timestamptz,
    fencing_token  bigint NOT NULL DEFAULT 0 CHECK (fencing_token >= 0),
    metriques      jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS ingestion_run_source
    ON ingestion_run (tenant_id, source_id, cree_le DESC);
CREATE INDEX IF NOT EXISTS ingestion_run_file
    ON ingestion_run (etat, next_attempt_at, cree_le);
-- Un seul run vivant par source : un planificateur qui repasse ne crée jamais de doublon.
CREATE UNIQUE INDEX IF NOT EXISTS ingestion_run_actif_par_source
    ON ingestion_run (tenant_id, source_id)
    WHERE etat IN ('QUEUED', 'FETCHING', 'INDEXING', 'EXTRACTING', 'PROJECTING', 'RETRY_WAIT');

-- Travail (fil Aujourd'hui / Actualités) : read model Postgres alimenté depuis Mongo.
-- `donnees` garde le document de cas complet ; `version` ne bouge que si le contenu change,
-- ce qui rend le backfill rejouable. Les écritures restent Mongo tant que le chemin d'écriture
-- n'est pas migré (docs/architecture/travail-migration.md). RLS volontairement non activé ici.
CREATE TABLE IF NOT EXISTS travail (
    id        text NOT NULL,
    tenant_id text NOT NULL,
    donnees   jsonb NOT NULL,
    version   bigint NOT NULL DEFAULT 1,
    maj_le    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id)
);
CREATE INDEX IF NOT EXISTS travail_recents
    ON travail (tenant_id, maj_le DESC, id DESC);
