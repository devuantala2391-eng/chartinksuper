-- Comprehensive Calculations SQL - PostgreSQL Stored Procedures
-- Creates all required stored procedures for weekly candle generation

-- Drop existing functions first
DROP FUNCTION IF EXISTS generate_weekly_candles_for_symbol(TEXT);
DROP FUNCTION IF EXISTS process_symbol_weekly_only(TEXT);
DROP FUNCTION IF EXISTS process_all_symbols_weekly_only();
DROP FUNCTION IF EXISTS generate_monthly_candles_for_symbol(TEXT);
DROP FUNCTION IF EXISTS process_symbol_monthly_only(TEXT);
DROP FUNCTION IF EXISTS process_all_symbols_monthly_only();
DROP FUNCTION IF EXISTS calculate_all_indicators_for_symbol(TEXT);
DROP FUNCTION IF EXISTS process_symbol_comprehensive(TEXT);

-- Function to generate weekly candles for a single symbol
CREATE OR REPLACE FUNCTION generate_weekly_candles_for_symbol(symbol_param TEXT)
RETURNS TABLE(
    status TEXT,
    generated_weeks INTEGER,
    updated_daily_refs INTEGER,
    execution_time_ms INTEGER
) AS $$
DECLARE
    week_count INTEGER := 0;
    daily_update_count INTEGER := 0;
    start_time TIMESTAMP := CLOCK_TIMESTAMP();
BEGIN
    -- Clear existing weekly candles for this symbol
    DELETE FROM weekly_candles WHERE symbol = symbol_param;
    
    -- Generate weekly candles using a simple INSERT with GROUP BY
    INSERT INTO weekly_candles (
        weekly_candle_key_id,
        symbol,
        week_sequence_number,
        week_start_timestamp,
        week_end_timestamp,
        week_start_datetime,
        week_end_datetime,
        open,
        high,
        low,
        close,
        volume,
        trading_days_count,
        indicators
    )
    SELECT
        symbol_param || '_W' || (ROW_NUMBER() OVER (ORDER BY week_start) - 1) as weekly_candle_key_id,
        symbol_param as symbol,
        ROW_NUMBER() OVER (ORDER BY week_start) - 1 as week_sequence_number,
        MIN(timestamp) as week_start_timestamp,
        MAX(timestamp) as week_end_timestamp,
        week_start as week_start_datetime,
        week_start + INTERVAL '6 days' as week_end_datetime,
        (array_agg(open ORDER BY datetime))[1] as open,
        MAX(high) as high,
        MIN(low) as low,
        (array_agg(close ORDER BY datetime DESC))[1] as close,
        SUM(volume) as volume,
        COUNT(*) as trading_days_count,
        '{}'::jsonb as indicators
    FROM (
        SELECT 
            DATE_TRUNC('week', datetime) as week_start,
            timestamp,
            datetime,
            open,
            high,
            low,
            close,
            volume
        FROM daily_candles
        WHERE symbol = symbol_param
    ) daily_with_weeks
    GROUP BY week_start
    ORDER BY week_start;
    
    GET DIAGNOSTICS week_count = ROW_COUNT;
    
    -- Update daily candles with weekly_candle_key_id
    UPDATE daily_candles dc
    SET weekly_candle_key_id = wc.weekly_candle_key_id
    FROM weekly_candles wc
    WHERE dc.symbol = symbol_param
    AND wc.symbol = symbol_param
    AND DATE_TRUNC('week', dc.datetime) = wc.week_start_datetime;
    
    GET DIAGNOSTICS daily_update_count = ROW_COUNT;
    
    RETURN QUERY SELECT 
        'SUCCESS'::TEXT,
        week_count,
        daily_update_count,
        EXTRACT(EPOCH FROM (CLOCK_TIMESTAMP() - start_time) * 1000)::INTEGER;
END;
$$ LANGUAGE plpgsql;

-- Function to process weekly candles for a single symbol (no indicators)
CREATE OR REPLACE FUNCTION process_symbol_weekly_only(symbol_param TEXT)
RETURNS TABLE(
    status TEXT,
    weekly_candles_generated INTEGER,
    daily_candles_updated INTEGER,
    total_execution_time_ms INTEGER
) AS $$
DECLARE
    result_record RECORD;
BEGIN
    -- Call the weekly candle generation function
    SELECT * INTO result_record
    FROM generate_weekly_candles_for_symbol(symbol_param);
    
    RETURN QUERY SELECT
        result_record.status,
        result_record.generated_weeks,
        result_record.updated_daily_refs,
        result_record.execution_time_ms;
END;
$$ LANGUAGE plpgsql;

-- Function to process all symbols for weekly candles only (batch processing)
CREATE OR REPLACE FUNCTION process_all_symbols_weekly_only()
RETURNS TABLE(
    symbol VARCHAR(20),
    status TEXT,
    weekly_candles INTEGER,
    daily_updated INTEGER,
    execution_time_ms INTEGER
) AS $$
DECLARE
    symbol_record RECORD;
    result_record RECORD;
BEGIN
    -- Process each symbol with daily candles
    FOR symbol_record IN 
        SELECT DISTINCT dc.symbol
        FROM daily_candles dc
        ORDER BY dc.symbol
    LOOP
        BEGIN
            -- Process this symbol
            SELECT * INTO result_record
            FROM process_symbol_weekly_only(symbol_record.symbol);
            
            RETURN QUERY SELECT
                symbol_record.symbol,
                result_record.status,
                result_record.weekly_candles_generated,
                result_record.daily_candles_updated,
                result_record.total_execution_time_ms;
                
        EXCEPTION WHEN OTHERS THEN
            -- Return error status for this symbol
            RETURN QUERY SELECT
                symbol_record.symbol,
                'ERROR: ' || SQLERRM,
                0,
                0,
                0;
        END;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Function to calculate all indicators for a symbol (placeholder)
CREATE OR REPLACE FUNCTION calculate_all_indicators_for_symbol(symbol_param TEXT)
RETURNS TABLE(
    status TEXT,
    indicators_calculated INTEGER,
    execution_time_ms INTEGER
) AS $$
BEGIN
    -- Placeholder function for indicator calculations
    RETURN QUERY SELECT
        'SUCCESS'::TEXT,
        0,
        0;
END;
$$ LANGUAGE plpgsql;

-- Function to generate monthly candles for a single symbol
CREATE OR REPLACE FUNCTION generate_monthly_candles_for_symbol(symbol_param TEXT)
RETURNS TABLE(
    status TEXT,
    generated_months INTEGER,
    updated_daily_refs INTEGER,
    execution_time_ms INTEGER
) AS $$
DECLARE
    month_count INTEGER := 0;
    daily_update_count INTEGER := 0;
    start_time TIMESTAMP := CLOCK_TIMESTAMP();
BEGIN
    -- Clear existing monthly candles for this symbol
    DELETE FROM monthly_candles WHERE symbol = symbol_param;
    
    -- Generate monthly candles using a simple INSERT with GROUP BY
    INSERT INTO monthly_candles (
        monthly_candle_key_id,
        symbol,
        month_sequence_number,
        month_start_timestamp,
        month_end_timestamp,
        month_start_datetime,
        month_end_datetime,
        open,
        high,
        low,
        close,
        volume,
        trading_days_count,
        indicators
    )
    SELECT
        symbol_param || '_M' || (ROW_NUMBER() OVER (ORDER BY month_start) - 1) as monthly_candle_key_id,
        symbol_param as symbol,
        ROW_NUMBER() OVER (ORDER BY month_start) - 1 as month_sequence_number,
        MIN(timestamp) as month_start_timestamp,
        MAX(timestamp) as month_end_timestamp,
        month_start as month_start_datetime,
        (month_start + INTERVAL '1 month' - INTERVAL '1 day') as month_end_datetime,
        (array_agg(open ORDER BY datetime))[1] as open,
        MAX(high) as high,
        MIN(low) as low,
        (array_agg(close ORDER BY datetime DESC))[1] as close,
        SUM(volume) as volume,
        COUNT(*) as trading_days_count,
        '{}'::jsonb as indicators
    FROM (
        SELECT 
            DATE_TRUNC('month', datetime) as month_start,
            timestamp,
            datetime,
            open,
            high,
            low,
            close,
            volume
        FROM daily_candles
        WHERE symbol = symbol_param
    ) daily_with_months
    GROUP BY month_start
    ORDER BY month_start;
    
    GET DIAGNOSTICS month_count = ROW_COUNT;
    
    -- Update daily candles with monthly_candle_key_id
    UPDATE daily_candles dc
    SET monthly_candle_key_id = mc.monthly_candle_key_id
    FROM monthly_candles mc
    WHERE dc.symbol = symbol_param
    AND mc.symbol = symbol_param
    AND DATE_TRUNC('month', dc.datetime) = mc.month_start_datetime;
    
    GET DIAGNOSTICS daily_update_count = ROW_COUNT;
    
    RETURN QUERY SELECT 
        'SUCCESS'::TEXT,
        month_count,
        daily_update_count,
        EXTRACT(EPOCH FROM (CLOCK_TIMESTAMP() - start_time) * 1000)::INTEGER;
END;
$$ LANGUAGE plpgsql;

-- Function to process monthly candles for a single symbol (no indicators)
CREATE OR REPLACE FUNCTION process_symbol_monthly_only(symbol_param TEXT)
RETURNS TABLE(
    status TEXT,
    monthly_candles_generated INTEGER,
    daily_candles_updated INTEGER,
    total_execution_time_ms INTEGER
) AS $$
DECLARE
    result_record RECORD;
BEGIN
    -- Call the monthly candle generation function
    SELECT * INTO result_record
    FROM generate_monthly_candles_for_symbol(symbol_param);
    
    RETURN QUERY SELECT
        result_record.status,
        result_record.generated_months,
        result_record.updated_daily_refs,
        result_record.execution_time_ms;
END;
$$ LANGUAGE plpgsql;

-- Function to process all symbols for monthly candles only (batch processing)
CREATE OR REPLACE FUNCTION process_all_symbols_monthly_only()
RETURNS TABLE(
    symbol VARCHAR(20),
    status TEXT,
    monthly_candles INTEGER,
    daily_updated INTEGER,
    execution_time_ms INTEGER
) AS $$
DECLARE
    symbol_record RECORD;
    result_record RECORD;
BEGIN
    -- Process each symbol with daily candles
    FOR symbol_record IN 
        SELECT DISTINCT dc.symbol
        FROM daily_candles dc
        ORDER BY dc.symbol
    LOOP
        BEGIN
            -- Process this symbol
            SELECT * INTO result_record
            FROM process_symbol_monthly_only(symbol_record.symbol);
            
            RETURN QUERY SELECT
                symbol_record.symbol,
                result_record.status,
                result_record.monthly_candles_generated,
                result_record.daily_candles_updated,
                result_record.total_execution_time_ms;
                
        EXCEPTION WHEN OTHERS THEN
            -- Return error status for this symbol
            RETURN QUERY SELECT
                symbol_record.symbol,
                'ERROR: ' || SQLERRM,
                0,
                0,
                0;
        END;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Function for comprehensive processing (weekly + monthly + indicators)
CREATE OR REPLACE FUNCTION process_symbol_comprehensive(symbol_param TEXT)
RETURNS TABLE(
    status TEXT,
    weekly_candles INTEGER,
    monthly_candles INTEGER,
    indicators_calculated INTEGER,
    total_execution_time_ms INTEGER
) AS $$
DECLARE
    weekly_result RECORD;
    monthly_result RECORD;
    indicator_result RECORD;
    total_time INTEGER := 0;
BEGIN
    -- Generate weekly candles first
    SELECT * INTO weekly_result
    FROM process_symbol_weekly_only(symbol_param);
    
    total_time := weekly_result.total_execution_time_ms;
    
    -- Generate monthly candles
    SELECT * INTO monthly_result
    FROM process_symbol_monthly_only(symbol_param);
    
    total_time := total_time + monthly_result.total_execution_time_ms;
    
    -- Calculate indicators
    SELECT * INTO indicator_result
    FROM calculate_all_indicators_for_symbol(symbol_param);
    
    total_time := total_time + indicator_result.execution_time_ms;
    
    RETURN QUERY SELECT
        CASE 
            WHEN weekly_result.status = 'SUCCESS' AND monthly_result.status = 'SUCCESS' THEN 'SUCCESS'
            ELSE 'PARTIAL_SUCCESS'
        END,
        weekly_result.weekly_candles_generated,
        monthly_result.monthly_candles_generated,
        indicator_result.indicators_calculated,
        total_time;
END;
$$ LANGUAGE plpgsql;