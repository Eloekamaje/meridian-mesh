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

-- Maturité calculée, jamais déclarée (Jumeau Sources §5) : M1 sans preuve, M2 une preuve, M3 deux systèmes différents
-- (source.type : deux dépôts Git ne sont pas indépendants), M4 = M3 + revue ACCEPTED. Recalculée à chaque preuve et statut.
CREATE OR REPLACE FUNCTION recalculer_maturite(cid bigint) RETURNS void AS $$
    UPDATE claim SET maturite = CASE
        WHEN s.preuves = 0 THEN 'M1'
        WHEN s.systemes >= 2 AND claim.statut = 'ACCEPTED' THEN 'M4'
        WHEN s.systemes >= 2 THEN 'M3'
        ELSE 'M2' END
    FROM (SELECT count(*) AS preuves, count(DISTINCT so.type) AS systemes
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
CREATE OR REPLACE TRIGGER claim_maturite AFTER INSERT OR UPDATE OF statut ON claim
    FOR EACH ROW EXECUTE FUNCTION maturite_a_recalculer();
CREATE OR REPLACE TRIGGER claim_preuve_maturite AFTER INSERT ON claim_preuve
    FOR EACH ROW EXECUTE FUNCTION maturite_a_recalculer();

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
