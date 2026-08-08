-- Migration: AI pipeline persistence tables (Phase 8 / Task 4)
-- Mirrors the in-memory stores: ScanFeedbackStore, ScanMetricsStore, TrainingJobsStore

-- 1. Scan feedback (disagreement reviews between YOLO & Gemini)
CREATE TABLE IF NOT EXISTS public.scan_feedback (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    image_ref   TEXT,
    yolo_label  TEXT,
    yolo_confidence DOUBLE PRECISION,
    gemini_label    TEXT,
    gemini_agrees   BOOLEAN,
    reasoning       TEXT,
    reviewed        BOOLEAN DEFAULT FALSE,
    confirmed_label TEXT,
    created_at  TIMESTAMPTZ DEFAULT now(),
    reviewed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_scan_feedback_reviewed
    ON public.scan_feedback (reviewed);

-- 2. Scan metrics (inference latency telemetry)
CREATE TABLE IF NOT EXISTS public.scan_metrics (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    inference_ms    DOUBLE PRECISION NOT NULL,
    model_source    TEXT,
    image_size      JSONB,
    recorded_at     TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_scan_metrics_recorded
    ON public.scan_metrics (recorded_at DESC);

-- 3. Training jobs (retrain orchestration state)
CREATE TABLE IF NOT EXISTS public.training_jobs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_batch_ids   JSONB DEFAULT '[]'::jsonb,
    target              TEXT DEFAULT 'local',
    status              TEXT DEFAULT 'queued',
    metrics_before      JSONB,
    metrics_before_note TEXT,
    metrics_after       JSONB,
    weights_url         TEXT,
    error_message       TEXT,
    created_at          TIMESTAMPTZ DEFAULT now(),
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_training_jobs_status
    ON public.training_jobs (status);
