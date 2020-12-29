CREATE TABLE IF NOT EXISTS scores (
    -- Unique score id
    id SERIAL PRIMARY KEY,

    -- Message content
    scanned_content TEXT NOT NULL,

    -- Scores
    insult REAL NOT NULL,
    severe_toxic REAL NOT NULL,
    identity_hate REAL NOT NULL,
    threat REAL NOT NULL,
    nsfw REAL NOT NULL,

    -- Date created
    date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scan_channels (
    -- Discord channel ID
    channel_id BIGINT PRIMARY KEY,
    UNIQUE(channel_id)
    -- Discord server ID
    server_id BIGINT NOT NULL,

    -- Whether this channel is being scanned
    active BOOLEAN DEFAULT true,

    -- Date channel was added for scanning
    date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS infractions (
    -- Infraction ID
    id SERIAL PRIMARY KEY,

    -- User's Discord ID
    user_id BIGINT NOT NULL,

    -- Discord server ID
    server_id BIGINT NOT NULL,

    -- Discord channel ID
    channel_id BIGINT NOT NULL REFERENCES scan_channels ON DELETE CASCADE,

    -- Discord message ID
    message_id BIGINT NOT NULL,

    -- Score ID
    score_id BIGINT NOT NULL REFERENCES scores ON DELETE SET NULL,

    -- Date infraction was created
    date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS reviewers (
    -- User's Discord ID
    user_id BIGINT PRIMARY KEY,

    -- Whether this reviwer is active
    active BOOLEAN DEFAULT true,

    -- The review channel the user is connected to
    channel_id BIGINT,

    -- Date this reviwer was created
    date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS review_messages (
    -- Review ID
    id SERIAL PRIMARY KEY,

    -- Score ID
    score_id BIGINT NOT NULL REFERENCES scores ON DELETE SET NULL,

    -- Content after sanitized
    clean_content TEXT NOT NULL, 

    -- If this content is still in queue
    active BOOLEAN DEFAULT true,

    -- Number of votes collected
    votes SMALLINT DEFAULT 0,

    -- Date created
    date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS review_log (
    -- Review ID
    review_id BIGINT NOT NULL REFERENCES review_messages ON DELETE CASCADE,
    
    -- User reviewed/reviewing
    user_id BIGINT NOT NULL REFERENCES reviewers ON DELETE CASCADE,

    -- Review Discord message ID
    message_id BIGINT,

    -- Voted scores
    insult SMALLINT,
    severe_toxic SMALLINT,
    identity_hate SMALLINT,
    threat SMALLINT,
    nsfw SMALLINT,

    -- If content is being voted on
    active BOOLEAN DEFAULT true,

    -- Date created
    date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);