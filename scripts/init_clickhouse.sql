-- Run once to set up the bronze layer in your existing ClickHouse instance.
-- If your ClickHouse user has access_management=1, uncomment the user/grant lines below.

CREATE DATABASE IF NOT EXISTS bronze;

-- CREATE USER IF NOT EXISTS hs2ch IDENTIFIED BY 'changeme';
-- GRANT SELECT, INSERT, CREATE TABLE ON bronze.* TO hs2ch;

CREATE TABLE IF NOT EXISTS bronze.hs_contacts
    (_record_id String, _extracted_at DateTime DEFAULT now(), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

CREATE TABLE IF NOT EXISTS bronze.hs_companies
    (_record_id String, _extracted_at DateTime DEFAULT now(), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

CREATE TABLE IF NOT EXISTS bronze.hs_deals
    (_record_id String, _extracted_at DateTime DEFAULT now(), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

CREATE TABLE IF NOT EXISTS bronze.hs_leads
    (_record_id String, _extracted_at DateTime DEFAULT now(), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

CREATE TABLE IF NOT EXISTS bronze.hs_calls
    (_record_id String, _extracted_at DateTime DEFAULT now(), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

CREATE TABLE IF NOT EXISTS bronze.hs_meetings
    (_record_id String, _extracted_at DateTime DEFAULT now(), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

CREATE TABLE IF NOT EXISTS bronze.hs_engagement_emails
    (_record_id String, _extracted_at DateTime DEFAULT now(), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

CREATE TABLE IF NOT EXISTS bronze.hs_notes
    (_record_id String, _extracted_at DateTime DEFAULT now(), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

CREATE TABLE IF NOT EXISTS bronze.hs_tasks
    (_record_id String, _extracted_at DateTime DEFAULT now(), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

CREATE TABLE IF NOT EXISTS bronze.hs_campaigns
    (_record_id String, _extracted_at DateTime DEFAULT now(), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

CREATE TABLE IF NOT EXISTS bronze.hs_forms
    (_record_id String, _extracted_at DateTime DEFAULT now(), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

CREATE TABLE IF NOT EXISTS bronze.hs_ads
    (_record_id String, _extracted_at DateTime DEFAULT now(), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);

CREATE TABLE IF NOT EXISTS bronze.hs_marketing_emails
    (_record_id String, _extracted_at DateTime DEFAULT now(), _raw String)
    ENGINE = ReplacingMergeTree(_extracted_at) ORDER BY (_record_id);
