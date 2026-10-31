-- 25 管理端操作审计（Day 106）
CREATE TABLE IF NOT EXISTS admin_audit_logs (
    id          BIGSERIAL PRIMARY KEY,
    admin_name  VARCHAR(64)  NOT NULL,
    action      VARCHAR(64)  NOT NULL,
    target_type VARCHAR(32),
    target_id   VARCHAR(64),
    detail      VARCHAR(500),
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON admin_audit_logs (created_at DESC);
SELECT count(*) AS admin_audit_logs FROM admin_audit_logs;
