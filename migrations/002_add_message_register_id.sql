-- migrations/002_add_message_register_id.sql
-- Adds message_register_id column to plc_profile with proper foreign key constraint
ALTER TABLE plc_profile ADD COLUMN message_register_id INTEGER 
  REFERENCES register_library(id) ON DELETE SET NULL;
