-- Run once to set up the bronze layer in your existing ClickHouse instance.
-- If your ClickHouse user has access_management=1, uncomment the user/grant lines below.

CREATE DATABASE IF NOT EXISTS bronze;

-- CREATE USER IF NOT EXISTS hs2ch IDENTIFIED BY 'changeme';
-- GRANT SELECT, INSERT, CREATE TABLE ON bronze.* TO hs2ch;

CREATE TABLE IF NOT EXISTS bronze.hs_contacts
    (_record_id String, _extracted_at DateTime DEFAULT now(), properties Map(String, String), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

CREATE TABLE IF NOT EXISTS bronze.hs_companies
    (_record_id String, _extracted_at DateTime DEFAULT now(), properties Map(String, String), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

CREATE TABLE IF NOT EXISTS bronze.hs_deals
    (_record_id String, _extracted_at DateTime DEFAULT now(), properties Map(String, String), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

CREATE TABLE IF NOT EXISTS bronze.hs_leads
    (_record_id String, _extracted_at DateTime DEFAULT now(), properties Map(String, String), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

CREATE TABLE IF NOT EXISTS bronze.hs_calls
    (_record_id String, _extracted_at DateTime DEFAULT now(), properties Map(String, String), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

CREATE TABLE IF NOT EXISTS bronze.hs_meetings
    (_record_id String, _extracted_at DateTime DEFAULT now(), properties Map(String, String), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

CREATE TABLE IF NOT EXISTS bronze.hs_engagement_emails
    (_record_id String, _extracted_at DateTime DEFAULT now(), properties Map(String, String), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

CREATE TABLE IF NOT EXISTS bronze.hs_notes
    (_record_id String, _extracted_at DateTime DEFAULT now(), properties Map(String, String), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

CREATE TABLE IF NOT EXISTS bronze.hs_tasks
    (_record_id String, _extracted_at DateTime DEFAULT now(), properties Map(String, String), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

CREATE TABLE IF NOT EXISTS bronze.hs_campaigns
    (_record_id String, _extracted_at DateTime DEFAULT now(), properties Map(String, String), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

CREATE TABLE IF NOT EXISTS bronze.hs_forms
    (_record_id String, _extracted_at DateTime DEFAULT now(), properties Map(String, String), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

CREATE TABLE IF NOT EXISTS bronze.hs_ads
    (_record_id String, _extracted_at DateTime DEFAULT now(), properties Map(String, String), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

CREATE TABLE IF NOT EXISTS bronze.hs_marketing_emails
    (_record_id String, _extracted_at DateTime DEFAULT now(), properties Map(String, String), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

CREATE TABLE IF NOT EXISTS bronze.hs_pipelines
    (_record_id String, _extracted_at DateTime DEFAULT now(), properties Map(String, String), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

-- Silver database
CREATE DATABASE IF NOT EXISTS silver;

-- Association tables: CRM ↔ CRM
CREATE TABLE IF NOT EXISTS bronze.hs_assoc_contact_company
    (_from_id String, _to_id String, _association_type String, _extracted_at DateTime DEFAULT now())
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_from_id, _to_id, _association_type);

CREATE TABLE IF NOT EXISTS bronze.hs_assoc_contact_deal
    (_from_id String, _to_id String, _association_type String, _extracted_at DateTime DEFAULT now())
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_from_id, _to_id, _association_type);

CREATE TABLE IF NOT EXISTS bronze.hs_assoc_deal_company
    (_from_id String, _to_id String, _association_type String, _extracted_at DateTime DEFAULT now())
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_from_id, _to_id, _association_type);

CREATE TABLE IF NOT EXISTS bronze.hs_assoc_lead_contact
    (_from_id String, _to_id String, _association_type String, _extracted_at DateTime DEFAULT now())
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_from_id, _to_id, _association_type);

CREATE TABLE IF NOT EXISTS bronze.hs_assoc_deal_lead
    (_from_id String, _to_id String, _association_type String, _extracted_at DateTime DEFAULT now())
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_from_id, _to_id, _association_type);

CREATE TABLE IF NOT EXISTS bronze.hs_assoc_lead_company
    (_from_id String, _to_id String, _association_type String, _extracted_at DateTime DEFAULT now())
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_from_id, _to_id, _association_type);

-- Association tables: Activity ↔ Contacts
CREATE TABLE IF NOT EXISTS bronze.hs_assoc_call_contact
    (_from_id String, _to_id String, _association_type String, _extracted_at DateTime DEFAULT now())
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_from_id, _to_id, _association_type);

CREATE TABLE IF NOT EXISTS bronze.hs_assoc_meeting_contact
    (_from_id String, _to_id String, _association_type String, _extracted_at DateTime DEFAULT now())
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_from_id, _to_id, _association_type);

CREATE TABLE IF NOT EXISTS bronze.hs_assoc_email_contact
    (_from_id String, _to_id String, _association_type String, _extracted_at DateTime DEFAULT now())
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_from_id, _to_id, _association_type);

CREATE TABLE IF NOT EXISTS bronze.hs_assoc_note_contact
    (_from_id String, _to_id String, _association_type String, _extracted_at DateTime DEFAULT now())
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_from_id, _to_id, _association_type);

CREATE TABLE IF NOT EXISTS bronze.hs_assoc_task_contact
    (_from_id String, _to_id String, _association_type String, _extracted_at DateTime DEFAULT now())
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_from_id, _to_id, _association_type);

-- Association tables: Activity ↔ Companies
CREATE TABLE IF NOT EXISTS bronze.hs_assoc_call_company
    (_from_id String, _to_id String, _association_type String, _extracted_at DateTime DEFAULT now())
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_from_id, _to_id, _association_type);

CREATE TABLE IF NOT EXISTS bronze.hs_assoc_meeting_company
    (_from_id String, _to_id String, _association_type String, _extracted_at DateTime DEFAULT now())
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_from_id, _to_id, _association_type);

CREATE TABLE IF NOT EXISTS bronze.hs_assoc_email_company
    (_from_id String, _to_id String, _association_type String, _extracted_at DateTime DEFAULT now())
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_from_id, _to_id, _association_type);

CREATE TABLE IF NOT EXISTS bronze.hs_assoc_note_company
    (_from_id String, _to_id String, _association_type String, _extracted_at DateTime DEFAULT now())
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_from_id, _to_id, _association_type);

CREATE TABLE IF NOT EXISTS bronze.hs_assoc_task_company
    (_from_id String, _to_id String, _association_type String, _extracted_at DateTime DEFAULT now())
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_from_id, _to_id, _association_type);

-- Association tables: Activity ↔ Deals
CREATE TABLE IF NOT EXISTS bronze.hs_assoc_call_deal
    (_from_id String, _to_id String, _association_type String, _extracted_at DateTime DEFAULT now())
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_from_id, _to_id, _association_type);

CREATE TABLE IF NOT EXISTS bronze.hs_assoc_meeting_deal
    (_from_id String, _to_id String, _association_type String, _extracted_at DateTime DEFAULT now())
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_from_id, _to_id, _association_type);

CREATE TABLE IF NOT EXISTS bronze.hs_assoc_email_deal
    (_from_id String, _to_id String, _association_type String, _extracted_at DateTime DEFAULT now())
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_from_id, _to_id, _association_type);

CREATE TABLE IF NOT EXISTS bronze.hs_assoc_note_deal
    (_from_id String, _to_id String, _association_type String, _extracted_at DateTime DEFAULT now())
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_from_id, _to_id, _association_type);

CREATE TABLE IF NOT EXISTS bronze.hs_assoc_task_deal
    (_from_id String, _to_id String, _association_type String, _extracted_at DateTime DEFAULT now())
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_from_id, _to_id, _association_type);

-- Gold database
CREATE DATABASE IF NOT EXISTS gold;
