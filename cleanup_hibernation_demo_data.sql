-- ============================================================================
-- Cleanup Hibernation Demo Data
-- ============================================================================
-- This script removes all demo hibernation data created by the injection script.
--
-- Usage:
--   docker exec spot-optimizer-postgres psql -U postgres -d spot_optimizer -f /path/to/this/file.sql
-- ============================================================================

DO $$
DECLARE
    v_deleted_schedules INT;
    v_deleted_executions INT;
    v_deleted_links INT;
BEGIN
    -- Delete executions for demo schedules
    DELETE FROM hibernation_executions
    WHERE schedule_id IN (
        SELECT id FROM hibernation_schedules
        WHERE name IN ('Business Hours Off', 'Weekend Full Shutdown', 'Dev Nightly')
    );
    GET DIAGNOSTICS v_deleted_executions = ROW_COUNT;

    -- Delete schedule-cluster links
    DELETE FROM hibernation_schedule_clusters
    WHERE schedule_id IN (
        SELECT id FROM hibernation_schedules
        WHERE name IN ('Business Hours Off', 'Weekend Full Shutdown', 'Dev Nightly')
    );
    GET DIAGNOSTICS v_deleted_links = ROW_COUNT;

    -- Delete schedules
    DELETE FROM hibernation_schedules
    WHERE name IN ('Business Hours Off', 'Weekend Full Shutdown', 'Dev Nightly');
    GET DIAGNOSTICS v_deleted_schedules = ROW_COUNT;

    RAISE NOTICE '✓ Deleted % demo schedules', v_deleted_schedules;
    RAISE NOTICE '✓ Deleted % schedule-cluster links', v_deleted_links;
    RAISE NOTICE '✓ Deleted % execution records', v_deleted_executions;
    RAISE NOTICE 'Demo hibernation data cleanup complete!';

END $$;
