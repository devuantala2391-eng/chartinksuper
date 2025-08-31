-- =====================================================
-- MIGRATE TO PREFIXED INDICATORS
-- =====================================================
-- This procedure removes old format indicators and 
-- recalculates all indicators with proper timeframe prefixes
-- =====================================================

-- Function to remove old format indicators
CREATE OR REPLACE FUNCTION remove_old_format_indicators(
    p_symbol_filter TEXT DEFAULT NULL
)
RETURNS TABLE(
    symbols_processed INTEGER,
    rows_updated INTEGER,
    status TEXT
) 
LANGUAGE plpgsql
AS $$
DECLARE
    v_symbols_processed INTEGER := 0;
    v_rows_updated INTEGER := 0;
    v_batch_count INTEGER;
    symbol_rec RECORD;
BEGIN
    RAISE NOTICE 'Removing old format indicators (without timeframe prefix)...';
    
    -- Process each symbol
    FOR symbol_rec IN 
        SELECT DISTINCT symbol FROM daily_candles 
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        -- Remove old format indicator keys
        UPDATE daily_candles
        SET indicators = indicators 
            - 'supertrend_10_3'
            - 'supertrend_10_3_direction'
            - 'supertrend_10_2'
            - 'supertrend_10_2_direction'
            - 'supertrend_10_2dot5'
            - 'supertrend_10_2dot5_direction'
            - 'pctchg'
            - 'percentage_change',
            updated_at = CURRENT_TIMESTAMP
        WHERE symbol = symbol_rec.symbol
        AND indicators IS NOT NULL
        AND (
            indicators ? 'supertrend_10_3' OR
            indicators ? 'supertrend_10_3_direction' OR
            indicators ? 'supertrend_10_2' OR
            indicators ? 'supertrend_10_2_direction' OR
            indicators ? 'supertrend_10_2dot5' OR
            indicators ? 'supertrend_10_2dot5_direction' OR
            indicators ? 'pctchg' OR
            indicators ? 'percentage_change'
        );
        
        GET DIAGNOSTICS v_batch_count = ROW_COUNT;
        v_rows_updated := v_rows_updated + v_batch_count;
        v_symbols_processed := v_symbols_processed + 1;
        
        IF v_batch_count > 0 THEN
            RAISE NOTICE 'Removed old indicators from % rows for symbol %', v_batch_count, symbol_rec.symbol;
        END IF;
    END LOOP;
    
    RETURN QUERY SELECT 
        v_symbols_processed,
        v_rows_updated,
        'SUCCESS'::TEXT;
        
EXCEPTION
    WHEN OTHERS THEN
        RETURN QUERY SELECT 
            v_symbols_processed,
            v_rows_updated,
            format('ERROR: %s', SQLERRM)::TEXT;
END;
$$;

-- Master migration function
CREATE OR REPLACE FUNCTION migrate_all_indicators_to_prefixed(
    p_symbol_filter TEXT DEFAULT NULL,
    p_remove_old BOOLEAN DEFAULT TRUE
)
RETURNS TABLE(
    step TEXT,
    status TEXT,
    details TEXT
) 
LANGUAGE plpgsql
AS $$
DECLARE
    v_result RECORD;
BEGIN
    -- Step 1: Remove old format indicators if requested
    IF p_remove_old THEN
        SELECT * INTO v_result FROM remove_old_format_indicators(p_symbol_filter);
        
        RETURN QUERY SELECT 
            'Remove Old Format'::TEXT,
            v_result.status,
            format('Processed %s symbols, updated %s rows', v_result.symbols_processed, v_result.rows_updated)::TEXT;
    END IF;
    
    -- Step 2: Calculate daily percentage change
    SELECT * INTO v_result FROM calculate_timeframe_percentage_change('daily', p_symbol_filter);
    
    RETURN QUERY SELECT 
        'Daily Percentage'::TEXT,
        v_result.status,
        format('Updated %s rows', v_result.updated_rows)::TEXT;
    
    -- Step 3: Calculate weekly percentage change  
    SELECT * INTO v_result FROM calculate_timeframe_percentage_change('weekly', p_symbol_filter);
    
    RETURN QUERY SELECT 
        'Weekly Percentage'::TEXT,
        v_result.status,
        format('Updated %s rows', v_result.updated_rows)::TEXT;
    
    -- Step 4: Calculate monthly percentage change
    SELECT * INTO v_result FROM calculate_timeframe_percentage_change('monthly', p_symbol_filter);
    
    RETURN QUERY SELECT 
        'Monthly Percentage'::TEXT,
        v_result.status,
        format('Updated %s rows', v_result.updated_rows)::TEXT;
    
    -- Step 5: Calculate daily SuperTrend
    SELECT * INTO v_result FROM calculate_timeframe_supertrend('daily', 10, 3.0, p_symbol_filter);
    
    RETURN QUERY SELECT 
        'Daily SuperTrend'::TEXT,
        v_result.status,
        format('Updated %s rows, keys: %s, %s', v_result.updated_rows, v_result.indicator_key, v_result.direction_key)::TEXT;
    
    -- Step 6: Calculate weekly SuperTrend
    SELECT * INTO v_result FROM calculate_weekly_monthly_supertrend('weekly', 10, 3.0, p_symbol_filter);
    
    RETURN QUERY SELECT 
        'Weekly SuperTrend'::TEXT,
        v_result.status,
        format('Updated %s rows, keys: %s, %s', v_result.updated_rows, v_result.indicator_key, v_result.direction_key)::TEXT;
    
    -- Step 7: Calculate monthly SuperTrend (if enough data)
    SELECT * INTO v_result FROM calculate_weekly_monthly_supertrend('monthly', 10, 3.0, p_symbol_filter);
    
    RETURN QUERY SELECT 
        'Monthly SuperTrend'::TEXT,
        v_result.status,
        format('Updated %s rows, keys: %s, %s', v_result.updated_rows, v_result.indicator_key, v_result.direction_key)::TEXT;
END;
$$;

-- Function to verify migration
CREATE OR REPLACE FUNCTION verify_indicator_migration(
    p_symbol TEXT DEFAULT '20MICRONS'
)
RETURNS TABLE(
    indicator_key TEXT,
    sample_value TEXT,
    format_type TEXT
) 
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH indicator_list AS (
        SELECT DISTINCT 
            jsonb_object_keys(indicators) as key
        FROM daily_candles
        WHERE symbol = p_symbol
        AND indicators IS NOT NULL
    ),
    categorized AS (
        SELECT 
            key,
            (
                SELECT indicators->key
                FROM daily_candles
                WHERE symbol = p_symbol
                AND indicators ? key
                LIMIT 1
            )::text as value,
            CASE 
                WHEN key LIKE 'daily_%' THEN 'NEW - Daily'
                WHEN key LIKE 'weekly_%' THEN 'NEW - Weekly'
                WHEN key LIKE 'monthly_%' THEN 'NEW - Monthly'
                ELSE 'OLD - No Prefix'
            END as format
        FROM indicator_list
    )
    SELECT 
        key::TEXT,
        value::TEXT,
        format::TEXT
    FROM categorized
    ORDER BY format, key;
END;
$$;

-- Grant permissions
GRANT EXECUTE ON FUNCTION remove_old_format_indicators(TEXT) TO PUBLIC;
GRANT EXECUTE ON FUNCTION migrate_all_indicators_to_prefixed(TEXT, BOOLEAN) TO PUBLIC;
GRANT EXECUTE ON FUNCTION verify_indicator_migration(TEXT) TO PUBLIC;