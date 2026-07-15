-- Migration: Add claude_md_files and skills_md_files columns to governance_responses table
-- Date: 2026-05-10
-- Description: Adds JSON columns to store claude.md and skills.md files for projects

-- Add claude_md_files column (always loaded for all agents)
ALTER TABLE governance_responses 
ADD COLUMN IF NOT EXISTS claude_md_files JSON;

-- Add skills_md_files column (selectively loaded based on task relevance)
ALTER TABLE governance_responses 
ADD COLUMN IF NOT EXISTS skills_md_files JSON;

-- Add comments for documentation
COMMENT ON COLUMN governance_responses.claude_md_files IS 'Array of claude.md files: [{name, content, uploadedAt}]. Always loaded for all agents as mandatory context.';
COMMENT ON COLUMN governance_responses.skills_md_files IS 'Array of skills.md files: [{name, content, uploadedAt}]. Selectively loaded by master agent based on task relevance.';
