PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS keyword (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL UNIQUE,
    domain TEXT,
    description TEXT,
    source TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS intermediary_keyword (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seed_keyword TEXT NOT NULL,
    mediator_keyword TEXT NOT NULL,
    support_count INTEGER NOT NULL DEFAULT 0,
    query_count INTEGER NOT NULL DEFAULT 0,
    global_frequency INTEGER NOT NULL DEFAULT 0,
    weight REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(seed_keyword, mediator_keyword),
    FOREIGN KEY(seed_keyword) REFERENCES keyword(keyword) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_intermediary_seed ON intermediary_keyword(seed_keyword);
CREATE INDEX IF NOT EXISTS idx_intermediary_weight ON intermediary_keyword(seed_keyword, weight DESC);

CREATE TABLE IF NOT EXISTS competition_result (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seed_keyword TEXT NOT NULL,
    candidate_keyword TEXT NOT NULL,
    competition_score REAL NOT NULL DEFAULT 0,
    rank_no INTEGER NOT NULL DEFAULT 0,
    evidence_source TEXT,
    computed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(seed_keyword, candidate_keyword),
    FOREIGN KEY(seed_keyword) REFERENCES keyword(keyword) ON DELETE CASCADE,
    FOREIGN KEY(candidate_keyword) REFERENCES keyword(keyword) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_competition_seed ON competition_result(seed_keyword);
CREATE INDEX IF NOT EXISTS idx_competition_score ON competition_result(seed_keyword, competition_score DESC);

CREATE TABLE IF NOT EXISTS search_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_text TEXT NOT NULL,
    matched_seed TEXT,
    token_count INTEGER NOT NULL DEFAULT 0,
    query_time TEXT,
    latency_ms REAL,
    source_file TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_search_log_seed ON search_log(matched_seed);
CREATE INDEX IF NOT EXISTS idx_search_log_query ON search_log(query_text);

CREATE TABLE IF NOT EXISTS user_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seed_keyword TEXT NOT NULL,
    candidate_keyword TEXT NOT NULL,
    feedback_score INTEGER NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 0,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(seed_keyword) REFERENCES keyword(keyword) ON DELETE CASCADE,
    FOREIGN KEY(candidate_keyword) REFERENCES keyword(keyword) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_feedback_seed ON user_feedback(seed_keyword);
CREATE INDEX IF NOT EXISTS idx_feedback_candidate ON user_feedback(candidate_keyword);
