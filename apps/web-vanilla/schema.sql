CREATE TABLE IF NOT EXISTS incidents (
  id TEXT PRIMARY KEY,
  reference_code TEXT NOT NULL UNIQUE,
  description TEXT NOT NULL,
  location TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'RECEIVED',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_incidents_reference_code ON incidents (reference_code);
