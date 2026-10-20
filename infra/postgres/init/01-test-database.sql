-- Runs once, when the db volume is first created. The test suite uses its own database.
CREATE DATABASE rafiq_test OWNER rafiq;
\connect rafiq_test
CREATE EXTENSION IF NOT EXISTS vector;
