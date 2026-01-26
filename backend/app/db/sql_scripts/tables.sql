
drop table users;
drop table submissions;
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100),
    subscription_tier VARCHAR(50) DEFAULT 'free', -- 'free', 'pro', 'enterprise'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Optional: Index for faster login lookups
CREATE INDEX idx_users_email ON users(email);


CREATE TABLE submissions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, -- Links to the User table
    filename VARCHAR(255) NOT NULL,
    status VARCHAR(50) DEFAULT 'queued', -- 'queued', 'ocr_processing', 'ai_processing', 'completed'
    mongo_id VARCHAR(255),               -- Stores the MongoDB ObjectId as a string
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for faster lookups by user (e.g., "Show me my history")
CREATE INDEX idx_submissions_user_id ON submissions(user_id);

-- Index for faster status checks (e.g., "Find all stuck jobs")
CREATE INDEX idx_submissions_status ON submissions(status);

