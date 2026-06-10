-- Add content_json column to analysis_jobs table for VLM JSON extraction
ALTER TABLE analysis_jobs ADD COLUMN content_json TEXT;
