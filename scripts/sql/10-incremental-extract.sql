-- Example incremental extraction boundary.
SELECT record_id, category, amount, updated_at
FROM source_records
WHERE updated_at > :last_successful_watermark
  AND updated_at <= :current_run_watermark
ORDER BY updated_at, record_id;
