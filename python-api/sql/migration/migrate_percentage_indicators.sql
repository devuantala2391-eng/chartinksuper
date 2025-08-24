-- =====================================================
-- MIGRATION SCRIPT: Legacy Percentage Change Indicators
-- =====================================================
-- This script migrates from the old format (daily_pctchg_1) 
-- to the new simplified format (daily_pctchg)
-- =====================================================

CREATE OR REPLACE FUNCTION migrate_percentage_indicators(
    p_timeframe TEXT DEFAULT 'daily'
)
RETURNS TABLE(
    migrated_rows INTEGER,
    status TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_table_name TEXT;
    v_old_key TEXT;
    v_new_key TEXT; 
    v_migrated_count INTEGER := 0;
BEGIN
    v_table_name := p_timeframe || '_candles';
    v_old_key := p_timeframe || '_pctchg_1';
    v_new_key := p_timeframe || '_pctchg';
    
    RAISE NOTICE 'Migrating % indicators from % to % in table %', 
        p_timeframe, v_old_key, v_new_key, v_table_name;
    
    -- Migrate indicators from old format to new format
    EXECUTE format($sql$
        UPDATE %I 
        SET indicators = indicators - $1 || jsonb_build_object($2, indicators->$1),
            updated_at = CURRENT_TIMESTAMP
        WHERE indicators ? $1 
          AND NOT (indicators ? $2)  -- Only migrate if new key doesn't exist
    $sql$, v_table_name)
    USING v_old_key, v_new_key;
    
    GET DIAGNOSTICS v_migrated_count = ROW_COUNT;
    
    RAISE NOTICE 'Migration completed: % rows migrated from % to %', 
        v_migrated_count, v_old_key, v_new_key;
    
    RETURN QUERY SELECT v_migrated_count, 'SUCCESS'::TEXT;
    
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Migration failed: %', SQLERRM;
        RETURN QUERY SELECT 0, format('ERROR: %s', SQLERRM)::TEXT;
END;
$$;

-- Helper function to check migration status
CREATE OR REPLACE FUNCTION check_percentage_migration_status(
    p_timeframe TEXT DEFAULT 'daily'
)
RETURNS TABLE(
    old_format_count BIGINT,
    new_format_count BIGINT, 
    migration_needed BOOLEAN
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_table_name TEXT;
    v_old_key TEXT;
    v_new_key TEXT;
BEGIN
    v_table_name := p_timeframe || '_candles';
    v_old_key := p_timeframe || '_pctchg_1';
    v_new_key := p_timeframe || '_pctchg';
    
    RETURN QUERY EXECUTE format($sql$
        SELECT 
            COUNT(CASE WHEN indicators ? $1 THEN 1 END) as old_format_count,
            COUNT(CASE WHEN indicators ? $2 THEN 1 END) as new_format_count,
            COUNT(CASE WHEN indicators ? $1 AND NOT (indicators ? $2) THEN 1 END) > 0 as migration_needed
        FROM %I
        WHERE indicators IS NOT NULL
    $sql$, v_table_name) USING v_old_key, v_new_key;
END;
$$;