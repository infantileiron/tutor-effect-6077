-- 002 实际辅导量：签到记录、时长核算、方案观察期与门槛、检验关联核算。
-- 启动仍使用 metadata.create_all（新库自动包含本结构）；已有数据卷需手动执行本文件。
ALTER TABLE plans ADD COLUMN IF NOT EXISTS obs_start VARCHAR(40) NOT NULL DEFAULT '';
ALTER TABLE plans ADD COLUMN IF NOT EXISTS obs_end VARCHAR(40) NOT NULL DEFAULT '';
ALTER TABLE plans ADD COLUMN IF NOT EXISTS threshold_minutes INTEGER NOT NULL DEFAULT 240;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS data_version INTEGER NOT NULL DEFAULT 0;
CREATE TABLE IF NOT EXISTS checkins (
    id SERIAL PRIMARY KEY,
    student_code VARCHAR(50) NOT NULL REFERENCES students(code) ON UPDATE CASCADE,
    start_at VARCHAR(40) NOT NULL,
    end_at VARCHAR(40) NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    note VARCHAR(200) NOT NULL DEFAULT '',
    created_at VARCHAR(40) NOT NULL,
    updated_at VARCHAR(40) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_checkins_student ON checkins(student_code);
CREATE TABLE IF NOT EXISTS calculations (
    id SERIAL PRIMARY KEY,
    plan_id INTEGER NOT NULL REFERENCES plans(id),
    status VARCHAR(20) NOT NULL,
    source_version INTEGER,
    result JSON,
    error TEXT NOT NULL DEFAULT '',
    created_at VARCHAR(40) NOT NULL
);
ALTER TABLE reports ADD COLUMN IF NOT EXISTS calculation_id INTEGER REFERENCES calculations(id);
