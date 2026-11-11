CREATE TABLE login_rate_limits (key VARCHAR PRIMARY KEY, count INTEGER NOT NULL CHECK (count>=1 AND count<=6), expires DOUBLE PRECISION NOT NULL);
CREATE INDEX ix_login_rate_limits_expires ON login_rate_limits(expires);
