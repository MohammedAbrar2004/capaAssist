-- Postgres mirror of the relevant subset of the real Oracle SoapBox.Cloud
-- CAPA schema (see version2/schema.csv + phases/phase1.md for the full
-- triage/decisions). Real Oracle table/column names, VARCHAR string IDs,
-- TENANT_ID scoping. Idempotent — safe to re-run.
--
-- Dropped at column level (not just table level), per phase1.md type mapping:
--   BLOB (evidence files), SDO_GEOMETRY (kept LATITUDE/LONGITUDE instead).
-- MSTR_USERS_METADATA: auth/session-only columns dropped (PASSWORD_HASH,
-- PASSWORD_SALT, MFA_*, LOCKED_UNTIL, FAILED_LOGIN_ATTEMPTS, IS_LOCKED,
-- EMAIL_VERIFIED) — same "skip auth plumbing" principle as Tier 5, applied
-- at column granularity since the table itself is Tier 2.

-- =========================================================================
-- Tier 2 — Master / lookup tables (no FK dependencies among themselves
-- except where noted)
-- =========================================================================

CREATE TABLE IF NOT EXISTS MSTR_TENANT_METADATA (
    TENANT_ID         VARCHAR(50)  PRIMARY KEY,
    TENANT_NAME       VARCHAR(255) NOT NULL,
    DOMAIN            VARCHAR(255) NOT NULL,
    STATUS_ID         VARCHAR(50)  NOT NULL,
    CREATED_DATE      TIMESTAMPTZ,
    CREATED_BY        VARCHAR(320),
    LAST_UPDATED      TIMESTAMPTZ,
    LAST_UPDATED_BY   VARCHAR(100),
    CONTACT_NAME      VARCHAR(100) NOT NULL,
    CONTACT_EMAIL     VARCHAR(320) NOT NULL,
    CONTACT_PHONE     VARCHAR(20),
    TENANT_ADDRESS    VARCHAR(255),
    TIMEZONE          VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS MSTR_TENANT_SITES (
    SITE_ID         VARCHAR(50)  PRIMARY KEY,
    TENANT_ID       VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_METADATA(TENANT_ID),
    SITE_NAME       VARCHAR(255) NOT NULL,
    LATITUDE        NUMERIC,
    LONGITUDE       NUMERIC,
    SITE_MANAGER    VARCHAR(320),
    STATUS_ID       VARCHAR(50)  NOT NULL,
    CREATED_AT      TIMESTAMPTZ,
    CREATED_BY      VARCHAR(320),
    LAST_UPDATED    TIMESTAMPTZ,
    LAST_UPDATED_BY VARCHAR(100),
    SITE_ADDRESS    TEXT,
    CONTACT_EMAIL   VARCHAR(320),
    CONTACT_PHONE   VARCHAR(20),
    META            TEXT
);

CREATE TABLE IF NOT EXISTS MSTR_TENANT_GROUPS (
    GROUP_ID            VARCHAR(50)  PRIMARY KEY,
    TENANT_ID            VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_METADATA(TENANT_ID),
    GROUP_NAME           VARCHAR(100) NOT NULL,
    GROUP_DESCRIPTION    TEXT         NOT NULL,
    GROUP_MANAGER_EMAIL  VARCHAR(320),
    STATUS_ID            VARCHAR(50)  NOT NULL,
    CREATED_DATE         TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS MSTR_TENANT_SITE_GROUPS (
    TENANT_ID  VARCHAR(50) NOT NULL REFERENCES MSTR_TENANT_METADATA(TENANT_ID),
    SITE_ID    VARCHAR(50) NOT NULL REFERENCES MSTR_TENANT_SITES(SITE_ID),
    GROUP_ID   VARCHAR(50) NOT NULL REFERENCES MSTR_TENANT_GROUPS(GROUP_ID),
    CREATED_AT TIMESTAMPTZ,
    PRIMARY KEY (SITE_ID, GROUP_ID)
);

CREATE TABLE IF NOT EXISTS MSTR_USERS_METADATA (
    USER_EMAIL  VARCHAR(320) PRIMARY KEY,
    TENANT_ID   VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_METADATA(TENANT_ID),
    FULL_NAME   VARCHAR(100) NOT NULL,
    STATUS_ID   VARCHAR(50)  NOT NULL,
    EXTERNAL_ID VARCHAR(255),
    PROFILE     TEXT,
    CREATED_AT  TIMESTAMPTZ,
    CREATED_BY  VARCHAR(320),
    GROUP_ID    VARCHAR(50) REFERENCES MSTR_TENANT_GROUPS(GROUP_ID),
    META        TEXT,
    PHONE_NUMBER VARCHAR(20),
    LAST_UPDATED TIMESTAMPTZ,
    LAST_UPDATED_BY VARCHAR(320)
);

-- Assumed schema (not in schema.csv dump, confirmed by user to exist in
-- production) — employee/org-directory record, distinct from
-- MSTR_USERS_METADATA's login-identity fields. See phase2.md decision 1.
CREATE TABLE IF NOT EXISTS MSTR_TENANT_EMP (
    EMP_ID            VARCHAR(50)  PRIMARY KEY,
    TENANT_ID         VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_METADATA(TENANT_ID),
    SITE_ID           VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_SITES(SITE_ID),
    GROUP_ID          VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_GROUPS(GROUP_ID),
    USER_EMAIL        VARCHAR(320) REFERENCES MSTR_USERS_METADATA(USER_EMAIL),
    FULL_NAME         VARCHAR(150) NOT NULL,
    ROLE_TITLE        VARCHAR(100),
    ROLE_DESCRIPTION  TEXT,
    STATUS_ID         VARCHAR(50)  NOT NULL,
    CREATED_DATE      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS MSTR_SEVERITY_MASTER (
    SEVERITY_ID    VARCHAR(50) PRIMARY KEY,
    SEVERITY_NAME  VARCHAR(50) NOT NULL,
    SEVERITY_LEVEL INTEGER     NOT NULL,
    DESCRIPTION    TEXT,
    DISPLAY_ORDER  INTEGER,
    COLOR_CODE     VARCHAR(7),
    IS_ACTIVE      CHAR(1) DEFAULT 'Y',
    CREATED_AT     TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS MSTR_PRIORITY_MASTER (
    PRIORITY_ID    VARCHAR(50) PRIMARY KEY,
    PRIORITY_LEVEL VARCHAR(50) NOT NULL,
    DESCRIPTION    TEXT,
    DISPLAY_ORDER  INTEGER,
    COLOR_CODE     VARCHAR(7),
    IS_ACTIVE      CHAR(1) DEFAULT 'Y',
    CREATED_AT     TIMESTAMPTZ
);

-- MSTR_STATUS_MASTER (generic, tenant-agnostic) and CAPA_STATUS_MASTER
-- (tenant-scoped override) both exist in production; mirror both, CAPA/
-- CAPA_ACTIONS etc. resolve STATUS_ID against whichever is in scope.
CREATE TABLE IF NOT EXISTS MSTR_STATUS_MASTER (
    STATUS_ID          VARCHAR(50) PRIMARY KEY,
    STATUS              VARCHAR(50)  NOT NULL,
    STATUS_DESCRIPTION  VARCHAR(255) NOT NULL,
    SOURCE_TABLE        VARCHAR(50)  NOT NULL
);

CREATE TABLE IF NOT EXISTS CAPA_STATUS_MASTER (
    STATUS_ID          VARCHAR(50) PRIMARY KEY,
    TENANT_ID           VARCHAR(50) REFERENCES MSTR_TENANT_METADATA(TENANT_ID),
    STATUS              VARCHAR(50)  NOT NULL,
    STATUS_DESCRIPTION  VARCHAR(255) NOT NULL,
    SOURCE_TABLE        VARCHAR(50)  NOT NULL,
    IS_ACTIVE           CHAR(1) DEFAULT 'Y',
    CREATED_AT          TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS CAPA_TYPE_MASTER (
    CAPA_TYPE_ID          VARCHAR(50) PRIMARY KEY,
    TENANT_ID              VARCHAR(50) REFERENCES MSTR_TENANT_METADATA(TENANT_ID),
    CAPA_TYPE_NAME         VARCHAR(50) NOT NULL,
    CAPA_TYPE_DESCRIPTION  TEXT,
    IS_ACTIVE              CHAR(1) DEFAULT 'Y',
    CREATED_AT             TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS CAPA_CATEGORIES (
    CATEGORY_ID           VARCHAR(50) PRIMARY KEY,
    TENANT_ID              VARCHAR(50) NOT NULL REFERENCES MSTR_TENANT_METADATA(TENANT_ID),
    PARENT_CATEGORY_ID     VARCHAR(50) REFERENCES CAPA_CATEGORIES(CATEGORY_ID),
    CATEGORY_NAME          VARCHAR(100) NOT NULL,
    CATEGORY_DESCRIPTION   TEXT,
    CATEGORY_COLOR         VARCHAR(20),
    CATEGORY_ICON          VARCHAR(50),
    DISPLAY_ORDER          INTEGER,
    IS_ACTIVE              INTEGER,
    CREATED_BY             VARCHAR(320) NOT NULL,
    CREATED_DATE           TIMESTAMP
);

CREATE TABLE IF NOT EXISTS CAPA_SUBCATEGORIES (
    SUBCATEGORY_ID         VARCHAR(50) PRIMARY KEY,
    CATEGORY_ID            VARCHAR(50)  NOT NULL REFERENCES CAPA_CATEGORIES(CATEGORY_ID),
    TENANT_ID               VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_METADATA(TENANT_ID),
    SUBCATEGORY_NAME        VARCHAR(100) NOT NULL,
    SUBCATEGORY_DESCRIPTION TEXT,
    SUBCATEGORY_COLOR       VARCHAR(20),
    SUBCATEGORY_ICON        VARCHAR(50),
    DISPLAY_ORDER           INTEGER,
    IS_ACTIVE               INTEGER,
    CREATED_BY              VARCHAR(320) NOT NULL,
    CREATED_DATE            TIMESTAMP
);

CREATE TABLE IF NOT EXISTS CAPA_ESCALATION_LEVELS (
    ESCALATION_LEVEL_ID    VARCHAR(50) PRIMARY KEY,
    TENANT_ID               VARCHAR(50) REFERENCES MSTR_TENANT_METADATA(TENANT_ID),
    ESCALATION_LEVEL_NAME   VARCHAR(50) NOT NULL,
    DESCRIPTION             TEXT,
    ESCALATION_HOURS        INTEGER,
    ESCALATION_TO_ROLE      VARCHAR(100),
    IS_ACTIVE               CHAR(1) DEFAULT 'Y',
    CREATED_AT              TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS CAPA_SLA_RULES (
    SLA_RULE_ID                 VARCHAR(50) PRIMARY KEY,
    TENANT_ID                    VARCHAR(50) NOT NULL REFERENCES MSTR_TENANT_METADATA(TENANT_ID),
    SITE_ID                      VARCHAR(50) REFERENCES MSTR_TENANT_SITES(SITE_ID),
    RULE_NAME                    VARCHAR(100) NOT NULL,
    CAPA_TYPE_ID                 VARCHAR(50) REFERENCES CAPA_TYPE_MASTER(CAPA_TYPE_ID),
    SEVERITY_ID                  VARCHAR(50) REFERENCES MSTR_SEVERITY_MASTER(SEVERITY_ID),
    PRIORITY_ID                  VARCHAR(50) REFERENCES MSTR_PRIORITY_MASTER(PRIORITY_ID),
    RESPONSE_TIME_HOURS           INTEGER NOT NULL,
    RESOLUTION_TIME_HOURS         INTEGER NOT NULL,
    WARNING_THRESHOLD_PERCENT     INTEGER,
    CRITICAL_THRESHOLD_PERCENT    INTEGER,
    BREACH_ESCALATION_LEVEL_ID    VARCHAR(50) REFERENCES CAPA_ESCALATION_LEVELS(ESCALATION_LEVEL_ID),
    INCLUDE_WEEKENDS              INTEGER,
    INCLUDE_HOLIDAYS               INTEGER,
    STATUS_ID                     VARCHAR(50) NOT NULL,
    CREATED_BY                    VARCHAR(320) NOT NULL,
    CREATED_DATE                  TIMESTAMP
);

CREATE TABLE IF NOT EXISTS MSTR_HOLIDAY_CALENDAR (
    HOLIDAY_ID    VARCHAR(50) PRIMARY KEY,
    TENANT_ID      VARCHAR(50) NOT NULL REFERENCES MSTR_TENANT_METADATA(TENANT_ID),
    SITE_ID        VARCHAR(50) REFERENCES MSTR_TENANT_SITES(SITE_ID),
    HOLIDAY_DATE   DATE NOT NULL,
    HOLIDAY_NAME   VARCHAR(100) NOT NULL,
    IS_RECURRING   CHAR(1) DEFAULT 'N',
    CREATED_AT     TIMESTAMPTZ,
    CREATED_BY     VARCHAR(320)
);

-- =========================================================================
-- Tier 1 — Core CAPA domain
-- =========================================================================

CREATE TABLE IF NOT EXISTS CAPA (
    CAPA_ID                 VARCHAR(50)  PRIMARY KEY,
    TENANT_ID                 VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_METADATA(TENANT_ID),
    SITE_ID                   VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_SITES(SITE_ID),
    SOURCE_MODULE             VARCHAR(100) NOT NULL,
    SOURCE_RECORD_ID          VARCHAR(50)  NOT NULL,
    OWNER_GROUP_ID            VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_GROUPS(GROUP_ID),
    CAPA_TITLE                VARCHAR(255) NOT NULL,
    CAPA_DESCRIPTION          TEXT         NOT NULL,
    RCA_METHOD_ID             VARCHAR(50),
    ROOT_CAUSE                TEXT,
    PRIORITY_ID               VARCHAR(50)  NOT NULL REFERENCES MSTR_PRIORITY_MASTER(PRIORITY_ID),
    SEVERITY_ID               VARCHAR(50)  NOT NULL REFERENCES MSTR_SEVERITY_MASTER(SEVERITY_ID),
    CAPA_TYPE_ID              VARCHAR(50)  NOT NULL REFERENCES CAPA_TYPE_MASTER(CAPA_TYPE_ID),
    STATUS_ID                 VARCHAR(50)  NOT NULL REFERENCES CAPA_STATUS_MASTER(STATUS_ID),
    CREATED_BY                VARCHAR(320) NOT NULL,
    ASSIGNED_TO               VARCHAR(320),
    CREATED_DATE              TIMESTAMPTZ,
    DUE_DATE                  DATE         NOT NULL,
    COMPLETED_DATE            DATE,
    CAPA_CLOSURE_DATE         DATE,
    CLOSURE_COMMENTS          TEXT,
    RECURRENCE_COUNT          INTEGER DEFAULT 0,
    LINKED_CAPA_IDS           VARCHAR(1000),
    RISK_LEVEL                VARCHAR(50),
    ESTIMATED_COST            NUMERIC,
    ACTUAL_COST               NUMERIC,
    BUSINESS_IMPACT           TEXT,
    EXTERNAL_REFERENCE        VARCHAR(255),
    REGULATORY_REQUIREMENT    VARCHAR(255),
    IS_RECURRING              INTEGER DEFAULT 0,
    LAST_UPDATED_AT           TIMESTAMPTZ,
    LAST_UPDATED_BY           VARCHAR(320)
);

CREATE TABLE IF NOT EXISTS CAPA_ACTIONS (
    ACTION_ID               VARCHAR(50)  PRIMARY KEY,
    CAPA_ID                  VARCHAR(50)  NOT NULL REFERENCES CAPA(CAPA_ID),
    TENANT_ID                 VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_METADATA(TENANT_ID),
    SITE_ID                   VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_SITES(SITE_ID),
    ACTION_TITLE              VARCHAR(255) NOT NULL,
    ACTION_DESCRIPTION        TEXT         NOT NULL,
    PRIORITY_ID                VARCHAR(50)  NOT NULL REFERENCES MSTR_PRIORITY_MASTER(PRIORITY_ID),
    CAPA_TYPE_ID               VARCHAR(50)  NOT NULL REFERENCES CAPA_TYPE_MASTER(CAPA_TYPE_ID),
    SEVERITY_ID                VARCHAR(50)  NOT NULL REFERENCES MSTR_SEVERITY_MASTER(SEVERITY_ID),
    CREATED_DATE               TIMESTAMPTZ,
    CREATED_BY                 VARCHAR(320),
    ASSIGNED_TO                VARCHAR(320) NOT NULL,
    STATUS_ID                  VARCHAR(50)  NOT NULL REFERENCES CAPA_STATUS_MASTER(STATUS_ID),
    DUE_DATE                   DATE         NOT NULL,
    UPDATED_BY                 VARCHAR(320),
    UPDATED_DATE                TIMESTAMPTZ,
    COMPLETION_COMMENTS         TEXT,
    COMPLETION_DATE              DATE,
    ESTIMATED_HOURS              NUMERIC,
    ACTUAL_HOURS                 NUMERIC,
    BLOCKED_BY                   VARCHAR(50) REFERENCES CAPA_ACTIONS(ACTION_ID),
    DEPENDENCY_TYPE              VARCHAR(50),
    VERIFICATION_REQUIRED         INTEGER DEFAULT 0,
    VERIFIED_BY                   VARCHAR(320),
    VERIFIED_DATE                  TIMESTAMPTZ,
    EVIDENCE_REQUIRED               TEXT[]
);

CREATE TABLE IF NOT EXISTS CAPA_ACTION_PLAN (
    ACTION_PLAN_ID           VARCHAR(50)  PRIMARY KEY,
    CAPA_ID                   VARCHAR(50)  NOT NULL REFERENCES CAPA(CAPA_ID),
    TENANT_ID                  VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_METADATA(TENANT_ID),
    SITE_ID                    VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_SITES(SITE_ID),
    ACTION_ID                  VARCHAR(50)  NOT NULL REFERENCES CAPA_ACTIONS(ACTION_ID),
    ACTION_PLAN_DESCRIPTION     TEXT         NOT NULL,
    PLANNED_START_DATE          DATE NOT NULL,
    PLANNED_END_DATE             DATE NOT NULL,
    ACTUAL_START_DATE            DATE,
    ACTUAL_END_DATE               DATE,
    OWNED_BY                     VARCHAR(320) NOT NULL,
    CREATED_DATE                  TIMESTAMPTZ,
    CREATED_BY                    VARCHAR(320),
    UPDATED_BY                    VARCHAR(320),
    UPDATED_DATE                   TIMESTAMPTZ,
    STATUS_ID                     VARCHAR(50) REFERENCES CAPA_STATUS_MASTER(STATUS_ID)
);

CREATE TABLE IF NOT EXISTS CAPA_INVESTIGATIONS (
    INVESTIGATION_ID            VARCHAR(50)  PRIMARY KEY,
    CAPA_ID                      VARCHAR(50)  NOT NULL REFERENCES CAPA(CAPA_ID),
    TENANT_ID                     VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_METADATA(TENANT_ID),
    SITE_ID                       VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_SITES(SITE_ID),
    INVESTIGATION_TITLE            VARCHAR(255) NOT NULL,
    INVESTIGATION_DESCRIPTION      TEXT         NOT NULL,
    INVESTIGATION_DATE              TIMESTAMPTZ,
    INVESTIGATOR_EMAIL              VARCHAR(320) NOT NULL,
    INVESTIGATION_OUTCOME           VARCHAR(50)  NOT NULL,
    CREATED_AT                       TIMESTAMPTZ,
    LAST_UPDATED                     TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS CAPA_REVIEWS (
    REVIEW_ID            VARCHAR(50)  PRIMARY KEY,
    CAPA_ID               VARCHAR(50)  NOT NULL REFERENCES CAPA(CAPA_ID),
    TENANT_ID              VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_METADATA(TENANT_ID),
    SITE_ID                 VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_SITES(SITE_ID),
    REVIEWED_BY              VARCHAR(320) NOT NULL,
    REVIEW_OUTCOME           VARCHAR(50)  NOT NULL,
    REVIEW_ITERATION          INTEGER,
    REVIEWER_COMMENTS          TEXT         NOT NULL,
    REVIEW_DATE                 TIMESTAMPTZ,
    REVIEW_TYPE                  VARCHAR(50),
    NEXT_REVIEW_DATE              DATE,
    RECURRING_REVIEW               INTEGER,
    REVIEW_STATUS_ID                VARCHAR(50) REFERENCES CAPA_STATUS_MASTER(STATUS_ID)
);

CREATE TABLE IF NOT EXISTS CAPA_REVIEW_HISTORY (
    REVIEW_HISTORY_ID    VARCHAR(50)  PRIMARY KEY,
    REVIEW_ID             VARCHAR(50)  NOT NULL REFERENCES CAPA_REVIEWS(REVIEW_ID),
    TENANT_ID               VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_METADATA(TENANT_ID),
    REVIEW_ITERATION         INTEGER,
    REVIEW_DATE               TIMESTAMPTZ,
    REVIEWED_BY                VARCHAR(320) NOT NULL,
    REVIEW_OUTCOME              VARCHAR(50)  NOT NULL,
    REVIEWER_COMMENTS            TEXT         NOT NULL
);

CREATE TABLE IF NOT EXISTS CAPA_REVIEW_TASKS (
    REVIEW_TASK_ID    VARCHAR(50)  PRIMARY KEY,
    REVIEW_ID          VARCHAR(50)  NOT NULL REFERENCES CAPA_REVIEWS(REVIEW_ID),
    TENANT_ID           VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_METADATA(TENANT_ID),
    TASK_DESCRIPTION     TEXT         NOT NULL,
    STATUS_ID             VARCHAR(50)  NOT NULL REFERENCES CAPA_STATUS_MASTER(STATUS_ID),
    ASSIGNED_TO            VARCHAR(320) NOT NULL,
    DUE_DATE                DATE         NOT NULL,
    CREATED_AT               TIMESTAMPTZ,
    UPDATED_AT                TIMESTAMPTZ,
    TASK_NAME                  VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS CAPA_CLOSURE (
    CLOSURE_ID         VARCHAR(50)  PRIMARY KEY,
    CAPA_ID             VARCHAR(50)  NOT NULL REFERENCES CAPA(CAPA_ID),
    TENANT_ID            VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_METADATA(TENANT_ID),
    SITE_ID               VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_SITES(SITE_ID),
    CLOSED_BY              VARCHAR(320) NOT NULL,
    CLOSURE_DATE             TIMESTAMPTZ,
    CLOSURE_STATUS            VARCHAR(50),
    APPROVAL_STATUS            VARCHAR(50),
    APPROVED_BY                 VARCHAR(320),
    CLOSURE_COMMENTS             TEXT,
    COMMENTED_BY                  VARCHAR(320) NOT NULL,
    COMMENTED_DATE                  TIMESTAMP
);

CREATE TABLE IF NOT EXISTS CAPA_APPROVALS (
    APPROVAL_ID       VARCHAR(50)  PRIMARY KEY,
    CAPA_ID            VARCHAR(50)  NOT NULL REFERENCES CAPA(CAPA_ID),
    TENANT_ID           VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_METADATA(TENANT_ID),
    SITE_ID              VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_SITES(SITE_ID),
    APPROVER_EMAIL        VARCHAR(320) NOT NULL,
    APPROVAL_STATUS        VARCHAR(50)  NOT NULL,
    APPROVAL_DATE            TIMESTAMPTZ,
    COMMENTS                  TEXT
);

-- =========================================================================
-- Tier 4 — AI-service-specific (do not exist in production Oracle schema)
-- =========================================================================

-- Isolated AI-side extension: holds root-cause-analysis fields with no
-- column in the real Oracle schema. Deletable as a single file later if
-- the real system can't supply these fields — see phase1.md "RCA table".
CREATE TABLE IF NOT EXISTS CAPA_RCA (
    RCA_ID                VARCHAR(50)  PRIMARY KEY,
    CAPA_ID                VARCHAR(50)  NOT NULL REFERENCES CAPA(CAPA_ID),
    TENANT_ID                VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_METADATA(TENANT_ID),
    CONTRIBUTING_FACTORS       TEXT[],
    FAILED_CONTROLS              TEXT[],
    MISSING_CONTROLS               TEXT[],
    ROOT_CAUSE_CATEGORY              VARCHAR(50) REFERENCES CAPA_CATEGORIES(CATEGORY_ID),
    CREATED_AT                         TIMESTAMPTZ DEFAULT now()
);

-- Isolated AI-side extension (Phase 3): action_type x theme combinations
-- used only to steer the Generator agent's variety. Not present in the real
-- Oracle schema and not the same as CAPA_CATEGORIES (root-cause categories) —
-- see phases/phase3.md decision 2. Global controlled vocabulary, no TENANT_ID.
CREATE TABLE IF NOT EXISTS CAPA_AI_ACTION_TAXONOMY (
    ACTION_TAXONOMY_ID  VARCHAR(50) PRIMARY KEY,
    ACTION_TYPE         VARCHAR(50) NOT NULL,
    THEME               VARCHAR(100) NOT NULL,
    DESCRIPTION         TEXT
);

INSERT INTO CAPA_AI_ACTION_TAXONOMY (ACTION_TAXONOMY_ID, ACTION_TYPE, THEME, DESCRIPTION) VALUES
('AT_001', 'Containment', 'SOP Update', 'Immediate temporary procedure change to isolate the hazard while a permanent corrective action is developed and implemented.'),
('AT_002', 'Containment', 'Engineering Control', 'Immediate physical barrier, lock-out, or equipment removal from service to prevent recurrence until the root cause is corrected.'),
('AT_003', 'Containment', 'Signage', 'Temporary hazard warning signs, barriers, or exclusion zones erected immediately after the incident to protect workers from the identified risk.'),
('AT_004', 'Containment', 'PPE', 'Issue of enhanced or additional PPE as an immediate interim measure while engineering or process controls are being implemented.'),
('AT_005', 'Corrective', 'SOP Update', 'Revision of a work procedure, standard, or control document to prevent recurrence of the identified failure mode. Must be communicated and trained to affected staff.'),
('AT_006', 'Corrective', 'Engineering Control', 'Physical modification, repair, or upgrade of equipment or infrastructure to eliminate or reduce the hazard at source.'),
('AT_007', 'Corrective', 'Training', 'Targeted training to address a confirmed knowledge or skill deficit identified as a root cause. Must specify content, method, assessment, and record.'),
('AT_008', 'Corrective', 'Inspection Cadence', 'Increase in inspection frequency or improvement in inspection quality for the specific asset, area, or process involved in the incident.'),
('AT_009', 'Corrective', 'Maintenance Schedule', 'Update to preventive maintenance schedule to address the equipment failure mode identified as root cause; must include frequency, method, and acceptance criteria.'),
('AT_010', 'Corrective', 'Process Change', 'Redesign of a work process to eliminate a step that introduced risk, simplify the method, or add a verification step that was previously absent.'),
('AT_011', 'Corrective', 'Personnel Change', 'Role reassignment, additional supervision, or fitness-for-work assessment where individual capability contributed to the incident.'),
('AT_012', 'Preventive', 'SOP Update', 'Proactive revision of related procedures to prevent the identified failure mode from occurring in similar operations at this or other sites.'),
('AT_013', 'Preventive', 'Engineering Control', 'Proactive installation of physical safeguards in similar equipment or locations where the same failure mode could occur but has not yet done so.'),
('AT_014', 'Preventive', 'Training', 'Proactive training programme targeting job roles exposed to the identified hazard across the site or organisation, beyond those directly involved.'),
('AT_015', 'Preventive', 'Inspection Cadence', 'Proactive extension of an improved inspection regime to all similar equipment, not just the specific asset involved in the incident.'),
('AT_016', 'Preventive', 'System/Software Control', 'Implementation of automated checks, interlocks, or system-enforced controls to prevent the failure mode from occurring without human intervention.'),
('AT_017', 'Preventive', 'Maintenance Schedule', 'Proactive revision of PM schedule for a class of similar equipment across the site or multiple sites, based on failure mode analysis from the incident.'),
('AT_018', 'Risk Mitigation', 'Engineering Control', 'Reduction of the severity or probability of harm from a known residual risk through physical controls, where complete elimination is not practicable.'),
('AT_019', 'Risk Mitigation', 'PPE', 'Specification and enforcement of appropriate PPE as a residual risk control, supported by a hierarchy of controls assessment.'),
('AT_020', 'Risk Mitigation', 'Signage', 'Installation of permanent hazard warning signs, safety labels, or visual management to reinforce awareness of a residual risk.'),
('AT_021', 'Risk Mitigation', 'Inspection Cadence', 'Increased monitoring or surveillance of a known risk area to detect early warning signs and allow intervention before an incident occurs.'),
('AT_022', 'Risk Mitigation', 'Process Change', 'Modification to work method to reduce exposure time, frequency, or severity of a residual risk that cannot be fully eliminated.')
ON CONFLICT (ACTION_TAXONOMY_ID) DO NOTHING;

CREATE TABLE IF NOT EXISTS capa_ai_evaluations (
    eval_id            VARCHAR(50)  PRIMARY KEY,
    action_id           VARCHAR(50)  NOT NULL REFERENCES CAPA_ACTIONS(ACTION_ID),
    tenant_id            VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_METADATA(TENANT_ID),
    score                  NUMERIC NOT NULL,
    weakness_level           VARCHAR(50) NOT NULL,
    dimension_results          JSONB NOT NULL,
    model_version                VARCHAR(100),
    created_at                     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS capa_ai_audit_trail (
    request_id      VARCHAR(50)  PRIMARY KEY,
    tenant_id         VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_METADATA(TENANT_ID),
    agent              VARCHAR(100) NOT NULL,
    input_payload        JSONB NOT NULL,
    output_payload         JSONB NOT NULL,
    user_decision             VARCHAR(50),
    model_version               VARCHAR(100),
    created_at                    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS capa_ai_context_packages (
    context_id     VARCHAR(50)  PRIMARY KEY,
    request_id       VARCHAR(50)  NOT NULL REFERENCES capa_ai_audit_trail(request_id),
    tenant_id          VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_METADATA(TENANT_ID),
    capa_id              VARCHAR(50) REFERENCES CAPA(CAPA_ID),
    package_payload         JSONB NOT NULL,
    created_at                TIMESTAMPTZ DEFAULT now()
);
