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
