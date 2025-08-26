-- =====================================================
-- COMPREHENSIVE CALCULATION STORED PROCEDURES
-- =====================================================
-- This file contains all calculation logic moved from Python to PostgreSQL
-- Single source of truth for all indicators, weekly, and monthly calculations
-- =====================================================

-- Helper function to calculate week key from timestamp
CREATE OR REPLACE FUNCTION calculate_week_key(timestamp_ms BIGINT)
RETURNS INTEGER AS $$
BEGIN
    -- Convert timestamp to date and calculate week number
    -- Using epoch week (weeks since Unix epoch)
    RETURN FLOOR((timestamp_ms / 1000) / 604800);  -- 604800 = seconds in a week
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- =====================================================
-- 1. ROBUST WEEKLY CANDLE GENERATION PROCEDURE WITH EDGE CASE HANDLING
-- =====================================================

-- Helper function to determine if a new week should start
CREATE OR REPLACE FUNCTION should_start_new_week(
    p_current_date DATE,
    p_current_dow INTEGER,
    p_prev_date DATE, 
    p_prev_dow INTEGER
) RETURNS BOOLEAN AS $$
BEGIN
    -- If this is the very first candle, start a new week
    IF p_prev_date IS NULL THEN
        RETURN TRUE;
    END IF;
    
    -- If we have the same day of week twice in a row, start new week from second occurrence
    -- Example: Thu -> Thu (means Fri-Wed missing, complete week on first Thu, start new on second Thu)
    IF p_current_dow = p_prev_dow THEN
        RETURN TRUE;
    END IF;
    
    -- If current day is earlier in week than previous day, new week has started
    -- Example: Friday (5) -> Tuesday (2) means weekend passed, new week started
    IF p_current_dow < p_prev_dow THEN
        RETURN TRUE;
    END IF;
    
    -- If there's a gap of more than 3 days, likely indicates week change
    -- Example: Thursday (4) -> Tuesday (2) of next week
    IF (p_current_date - p_prev_date) > 3 THEN
        RETURN TRUE;
    END IF;
    
    -- If we're on Monday and previous day wasn't Friday/Saturday/Sunday, start new week
    IF p_current_dow = 1 AND p_prev_dow NOT IN (5, 6, 7) THEN
        RETURN TRUE;
    END IF;
    
    -- Otherwise, continue current week
    RETURN FALSE;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION generate_weekly_candles_for_symbol(
    p_symbol TEXT
)
RETURNS TABLE(
    generated_weeks INTEGER,
    updated_daily_refs INTEGER,
    execution_time_ms INTEGER,
    status TEXT
) 
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_end_time TIMESTAMP;
    v_weeks_generated INTEGER := 0;
    v_daily_updated INTEGER := 0;
    v_current_week_number INTEGER := 1;
    v_current_week_candles INTEGER := 0;
    
    -- Week aggregation variables
    v_week_open NUMERIC;
    v_week_high NUMERIC;
    v_week_low NUMERIC;
    v_week_close NUMERIC;
    v_week_volume BIGINT;
    v_week_start_ts BIGINT;
    v_week_end_ts BIGINT;
    v_week_start_dt TIMESTAMP;
    v_week_end_dt TIMESTAMP;
    
    -- Loop variables
    candle_cursor CURSOR FOR 
        SELECT 
            candle_key_id,
            timestamp,
            datetime::DATE as trade_date,
            EXTRACT(DOW FROM datetime) as day_of_week,  -- 0=Sunday, 1=Monday, ..., 6=Saturday
            datetime,
            open, high, low, close, volume
        FROM daily_candles 
        WHERE symbol = p_symbol 
        ORDER BY timestamp ASC;
        
    current_candle RECORD;
    prev_trade_date DATE;
    prev_dow INTEGER;
    should_start_new BOOLEAN;
    
BEGIN
    
    RAISE NOTICE 'Starting robust weekly candle generation for symbol: %', p_symbol;
    
    -- Clean existing weekly candles for this symbol
    DELETE FROM weekly_candles WHERE symbol = p_symbol;
    
    -- Initialize variables
    prev_trade_date := NULL;
    prev_dow := NULL;
    
    -- Process each daily candle
    FOR current_candle IN candle_cursor LOOP
        
        -- Convert Sunday (0) to 7 for easier week logic (1=Mon, 7=Sun)
        current_candle.day_of_week := CASE 
            WHEN current_candle.day_of_week = 0 THEN 7 
            ELSE current_candle.day_of_week 
        END;
        
        -- Determine if we should start a new week
        should_start_new := should_start_new_week(
            current_candle.trade_date,
            current_candle.day_of_week::INTEGER,
            prev_trade_date,
            prev_dow
        );
        
        -- If starting a new week, finalize previous week
        IF should_start_new AND v_current_week_candles > 0 THEN
            
            -- Insert the completed week
            INSERT INTO weekly_candles (
                weekly_candle_key_id,
                symbol,
                week_sequence_number,
                week_start_timestamp,
                week_end_timestamp, 
                week_start_datetime,
                week_end_datetime,
                open, high, low, close, volume,
                trading_days_count
            ) VALUES (
                p_symbol || '_W' || v_current_week_number,
                p_symbol,
                v_current_week_number,
                v_week_start_ts,
                v_week_end_ts,
                v_week_start_dt,
                v_week_end_dt,
                v_week_open,
                v_week_high,
                v_week_low,
                v_week_close,
                v_week_volume,
                v_current_week_candles
            );
            
            v_weeks_generated := v_weeks_generated + 1;
            
            -- Move to next week
            v_current_week_number := v_current_week_number + 1;
            v_current_week_candles := 0;
            
        END IF;
        
        -- Initialize or update current week data
        IF v_current_week_candles = 0 THEN
            -- First candle of the week
            v_week_open := current_candle.open;
            v_week_high := current_candle.high;
            v_week_low := current_candle.low;
            v_week_close := current_candle.close;
            v_week_volume := current_candle.volume;
            v_week_start_ts := current_candle.timestamp;
            v_week_end_ts := current_candle.timestamp;
            v_week_start_dt := current_candle.datetime;
            v_week_end_dt := current_candle.datetime;
            
        ELSE
            -- Update week aggregation
            v_week_high := GREATEST(v_week_high, current_candle.high);
            v_week_low := LEAST(v_week_low, current_candle.low);
            v_week_close := current_candle.close;  -- Last close becomes week close
            v_week_volume := v_week_volume + current_candle.volume;
            v_week_end_ts := current_candle.timestamp;
            v_week_end_dt := current_candle.datetime;
            
        END IF;
        
        v_current_week_candles := v_current_week_candles + 1;
        
        -- Update daily candle with week reference
        UPDATE daily_candles 
        SET 
            weekly_candle_key_id = p_symbol || '_W' || v_current_week_number,
            week_key = v_current_week_number
        WHERE candle_key_id = current_candle.candle_key_id;
        
        v_daily_updated := v_daily_updated + 1;
        
        -- Store for next iteration
        prev_trade_date := current_candle.trade_date;
        prev_dow := current_candle.day_of_week::INTEGER;
        
    END LOOP;
    
    -- Don't forget the final week!
    IF v_current_week_candles > 0 THEN
        INSERT INTO weekly_candles (
            weekly_candle_key_id,
            symbol,
            week_sequence_number,
            week_start_timestamp,
            week_end_timestamp,
            week_start_datetime, 
            week_end_datetime,
            open, high, low, close, volume,
            trading_days_count
        ) VALUES (
            p_symbol || '_W' || v_current_week_number,
            p_symbol,
            v_current_week_number,
            v_week_start_ts,
            v_week_end_ts,
            v_week_start_dt,
            v_week_end_dt,
            v_week_open,
            v_week_high,
            v_week_low,
            v_week_close,
            v_week_volume,
            v_current_week_candles
        );
        
        v_weeks_generated := v_weeks_generated + 1;
    END IF;
    
    v_end_time := clock_timestamp();
    
    RAISE NOTICE 'Completed robust weekly generation for %: % weeks, % daily updated', 
        p_symbol, v_weeks_generated, v_daily_updated;
    
    RETURN QUERY SELECT 
        v_weeks_generated,
        v_daily_updated,
        EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER,
        'SUCCESS'::TEXT;
        
EXCEPTION
    WHEN OTHERS THEN
        v_end_time := clock_timestamp();
        RAISE NOTICE 'Error in robust weekly generation: %', SQLERRM;
        RETURN QUERY SELECT 
            0, 0,
            EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER,
            format('ERROR: %s', SQLERRM)::TEXT;
END;
$$;

-- =====================================================
-- 2. ALL INDICATORS CALCULATION PROCEDURE
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_all_indicators_for_symbol(
    p_symbol TEXT,
    p_batch_size INTEGER DEFAULT 1000
)
RETURNS TABLE(
    updated_rows INTEGER,
    indicators_calculated TEXT[],
    execution_time_ms INTEGER,
    status TEXT
) 
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_end_time TIMESTAMP;
    v_updated_rows INTEGER := 0;
    v_batch_count INTEGER := 0;
    v_indicators TEXT[] := ARRAY['sma_5', 'sma_10', 'sma_20', 'ema_5', 'ema_10', 'ema_20', 'rsi_14', 'macd', 'bollinger_upper', 'bollinger_lower', 'atr_14', 'weekly_pctchg'];
BEGIN
    
    RAISE NOTICE 'Starting comprehensive indicator calculation for symbol: %', p_symbol;
    
    -- Calculate all indicators in a single update operation
    WITH indicator_calculations AS (
        SELECT 
            dc.candle_key_id,
            -- Simple Moving Averages
            AVG(dc.close) OVER (
                PARTITION BY dc.symbol 
                ORDER BY dc.candle_sequence_number 
                ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
            ) as sma_5,
            AVG(dc.close) OVER (
                PARTITION BY dc.symbol 
                ORDER BY dc.candle_sequence_number 
                ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
            ) as sma_10,
            AVG(dc.close) OVER (
                PARTITION BY dc.symbol 
                ORDER BY dc.candle_sequence_number 
                ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) as sma_20,
            
            -- Exponential Moving Averages (simplified calculation)
            AVG(dc.close) OVER (
                PARTITION BY dc.symbol 
                ORDER BY dc.candle_sequence_number 
                ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
            ) as ema_5, -- Simplified as SMA for now
            AVG(dc.close) OVER (
                PARTITION BY dc.symbol 
                ORDER BY dc.candle_sequence_number 
                ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
            ) as ema_10, -- Simplified as SMA for now
            AVG(dc.close) OVER (
                PARTITION BY dc.symbol 
                ORDER BY dc.candle_sequence_number 
                ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) as ema_20, -- Simplified as SMA for now
            
            -- RSI calculation (simplified)
            CASE 
                WHEN dc.close > LAG(dc.close, 14) OVER (PARTITION BY dc.symbol ORDER BY dc.candle_sequence_number)
                THEN 60.0  -- Simplified RSI - price higher than 14 periods ago
                ELSE 40.0
            END as rsi_14,
            
            -- MACD (simplified)
            AVG(dc.close) OVER (
                PARTITION BY dc.symbol 
                ORDER BY dc.candle_sequence_number 
                ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
            ) - AVG(dc.close) OVER (
                PARTITION BY dc.symbol 
                ORDER BY dc.candle_sequence_number 
                ROWS BETWEEN 25 PRECEDING AND CURRENT ROW
            ) as macd,
            
            -- Bollinger Bands (simplified)
            AVG(dc.close) OVER (
                PARTITION BY dc.symbol 
                ORDER BY dc.candle_sequence_number 
                ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) + (dc.high - dc.low) as bollinger_upper,
            
            AVG(dc.close) OVER (
                PARTITION BY dc.symbol 
                ORDER BY dc.candle_sequence_number 
                ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) - (dc.high - dc.low) as bollinger_lower,
            
            -- ATR (simplified)
            AVG(dc.high - dc.low) OVER (
                PARTITION BY dc.symbol 
                ORDER BY dc.candle_sequence_number 
                ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
            ) as atr_14,
            
            -- Weekly Percentage Change (using optimized weekly_candles lookup)
            CASE 
                WHEN current_wc.week_sequence_number > 1 AND prev_wc.close IS NOT NULL AND prev_wc.close > 0 THEN
                    ROUND(((dc.close - prev_wc.close) / prev_wc.close * 100)::numeric, 4)
                ELSE 
                    NULL
            END as weekly_pctchg
            
        FROM daily_candles dc
        -- Join with current week's weekly candle
        LEFT JOIN weekly_candles current_wc 
            ON dc.weekly_candle_key_id = current_wc.weekly_candle_key_id
        -- JOIN with previous week's weekly candle (O(1) lookup!)
        LEFT JOIN weekly_candles prev_wc 
            ON prev_wc.weekly_candle_key_id = (dc.symbol || '_W' || (current_wc.week_sequence_number - 1)::TEXT)
        WHERE dc.symbol = p_symbol
    )
    UPDATE daily_candles AS target_table
    SET indicators = jsonb_build_object(
        'sma_5', calc.sma_5,
        'sma_10', calc.sma_10,
        'sma_20', calc.sma_20,
        'ema_5', calc.ema_5,
        'ema_10', calc.ema_10,
        'ema_20', calc.ema_20,
        'rsi_14', calc.rsi_14,
        'macd', calc.macd,
        'bollinger_upper', calc.bollinger_upper,
        'bollinger_lower', calc.bollinger_lower,
        'atr_14', calc.atr_14,
        'weekly_pctchg', calc.weekly_pctchg
    ),
    updated_at = CURRENT_TIMESTAMP
    FROM indicator_calculations calc
    WHERE target_table.candle_key_id = calc.candle_key_id;
    
    GET DIAGNOSTICS v_updated_rows = ROW_COUNT;
    
    v_end_time := clock_timestamp();
    
    RAISE NOTICE 'Completed indicator calculation for %: % rows updated in % ms',
        p_symbol, v_updated_rows, EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER;
    
    RETURN QUERY SELECT 
        v_updated_rows,
        v_indicators,
        EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER,
        'SUCCESS'::TEXT;
        
EXCEPTION
    WHEN OTHERS THEN
        v_end_time := clock_timestamp();
        RAISE NOTICE 'Error in calculate_all_indicators_for_symbol: %', SQLERRM;
        RETURN QUERY SELECT 
            0,
            ARRAY[]::TEXT[],
            EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER,
            format('ERROR: %s', SQLERRM)::TEXT;
END;
$$;

-- =====================================================
-- 3. WEEKLY CANDLES ONLY PROCESSING (FOR HARD REFRESH)
-- =====================================================
CREATE OR REPLACE FUNCTION process_symbol_weekly_only(
    p_symbol TEXT
)
RETURNS TABLE(
    weekly_candles_generated INTEGER,
    daily_candles_updated INTEGER,
    total_execution_time_ms INTEGER,
    status TEXT
) 
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_end_time TIMESTAMP;
    v_weekly_result RECORD;
BEGIN
    
    RAISE NOTICE 'Starting weekly-only processing for symbol: %', p_symbol;
    
    -- Generate weekly candles ONLY (no indicators)
    SELECT * INTO v_weekly_result FROM generate_weekly_candles_for_symbol(p_symbol);
    
    IF v_weekly_result.status != 'SUCCESS' THEN
        RETURN QUERY SELECT 
            0, 0,
            0, 
            format('Weekly generation failed: %s', v_weekly_result.status)::TEXT;
        RETURN;
    END IF;
    
    v_end_time := clock_timestamp();
    
    RAISE NOTICE 'Completed weekly-only processing for %: % weekly candles, % daily updated in % ms',
        p_symbol, v_weekly_result.generated_weeks, v_weekly_result.updated_daily_refs,
        EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER;
    
    RETURN QUERY SELECT 
        v_weekly_result.generated_weeks,
        v_weekly_result.updated_daily_refs,
        EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER,
        'SUCCESS'::TEXT;
        
EXCEPTION
    WHEN OTHERS THEN
        v_end_time := clock_timestamp();
        RAISE NOTICE 'Error in process_symbol_weekly_only: %', SQLERRM;
        RETURN QUERY SELECT 
            0, 0, 
            EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER,
            format('ERROR: %s', SQLERRM)::TEXT;
END;
$$;

-- =====================================================
-- 4. COMPREHENSIVE PROCESSING PROCEDURE (WITH INDICATORS)
-- =====================================================
CREATE OR REPLACE FUNCTION process_symbol_comprehensive(
    p_symbol TEXT
)
RETURNS TABLE(
    weekly_candles_generated INTEGER,
    daily_candles_updated INTEGER,
    indicators_calculated TEXT[],
    total_execution_time_ms INTEGER,
    status TEXT
) 
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_end_time TIMESTAMP;
    v_weekly_result RECORD;
    v_indicator_result RECORD;
BEGIN
    
    RAISE NOTICE 'Starting comprehensive processing for symbol: %', p_symbol;
    
    -- Step 1: Generate weekly candles
    SELECT * INTO v_weekly_result FROM generate_weekly_candles_for_symbol(p_symbol);
    
    IF v_weekly_result.status != 'SUCCESS' THEN
        RETURN QUERY SELECT 
            0, 0, ARRAY[]::TEXT[], 
            0, 
            format('Weekly generation failed: %s', v_weekly_result.status)::TEXT;
        RETURN;
    END IF;
    
    -- Step 2: Calculate all indicators (including weekly percentage)
    SELECT * INTO v_indicator_result FROM calculate_all_indicators_for_symbol(p_symbol);
    
    IF v_indicator_result.status != 'SUCCESS' THEN
        RETURN QUERY SELECT 
            v_weekly_result.generated_weeks, 
            0, 
            ARRAY[]::TEXT[], 
            v_weekly_result.execution_time_ms,
            format('Indicator calculation failed: %s', v_indicator_result.status)::TEXT;
        RETURN;
    END IF;
    
    v_end_time := clock_timestamp();
    
    RAISE NOTICE 'Completed comprehensive processing for %: % weekly candles, % daily updated, % total time ms',
        p_symbol, v_weekly_result.generated_weeks, v_indicator_result.updated_rows, 
        EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER;
    
    RETURN QUERY SELECT 
        v_weekly_result.generated_weeks,
        v_indicator_result.updated_rows,
        v_indicator_result.indicators_calculated,
        EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER,
        'SUCCESS'::TEXT;
        
EXCEPTION
    WHEN OTHERS THEN
        v_end_time := clock_timestamp();
        RAISE NOTICE 'Error in process_symbol_comprehensive: %', SQLERRM;
        RETURN QUERY SELECT 
            0, 0, ARRAY[]::TEXT[], 
            EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER,
            format('ERROR: %s', SQLERRM)::TEXT;
END;
$$;

-- =====================================================
-- 5. BATCH PROCESSING FOR ALL SYMBOLS - WEEKLY ONLY (FOR HARD REFRESH)
-- =====================================================
CREATE OR REPLACE FUNCTION process_all_symbols_weekly_only()
RETURNS TABLE(
    symbol TEXT,
    weekly_candles INTEGER,
    daily_updated INTEGER,
    execution_time_ms INTEGER,
    status TEXT
) 
LANGUAGE plpgsql
AS $$
DECLARE
    symbol_cursor CURSOR FOR 
        SELECT DISTINCT symbol FROM daily_candles ORDER BY symbol;
    symbol_rec RECORD;
    processing_result RECORD;
BEGIN
    
    RAISE NOTICE 'Starting weekly-only processing for all symbols';
    
    FOR symbol_rec IN symbol_cursor LOOP
        
        SELECT * INTO processing_result FROM process_symbol_weekly_only(symbol_rec.symbol);
        
        RETURN QUERY SELECT 
            symbol_rec.symbol,
            processing_result.weekly_candles_generated,
            processing_result.daily_candles_updated,
            processing_result.total_execution_time_ms,
            processing_result.status;
            
    END LOOP;
    
    RAISE NOTICE 'Completed weekly-only processing for all symbols';
    
END;
$$;

-- =====================================================
-- 6. BATCH PROCESSING FOR ALL SYMBOLS - COMPREHENSIVE (WITH INDICATORS)
-- =====================================================
CREATE OR REPLACE FUNCTION process_all_symbols_comprehensive()
RETURNS TABLE(
    symbol TEXT,
    weekly_candles INTEGER,
    daily_updated INTEGER,
    execution_time_ms INTEGER,
    status TEXT
) 
LANGUAGE plpgsql
AS $$
DECLARE
    symbol_cursor CURSOR FOR 
        SELECT DISTINCT symbol FROM daily_candles ORDER BY symbol;
    symbol_rec RECORD;
    processing_result RECORD;
BEGIN
    
    RAISE NOTICE 'Starting comprehensive processing for all symbols';
    
    FOR symbol_rec IN symbol_cursor LOOP
        
        SELECT * INTO processing_result FROM process_symbol_comprehensive(symbol_rec.symbol);
        
        RETURN QUERY SELECT 
            symbol_rec.symbol,
            processing_result.weekly_candles_generated,
            processing_result.daily_candles_updated,
            processing_result.total_execution_time_ms,
            processing_result.status;
            
    END LOOP;
    
    RAISE NOTICE 'Completed comprehensive processing for all symbols';
    
END;
$$;

-- =====================================================
-- 5. UTILITY FUNCTIONS
-- =====================================================

-- Check system health after processing
CREATE OR REPLACE FUNCTION check_comprehensive_system_health()
RETURNS TABLE(
    total_daily_candles BIGINT,
    total_weekly_candles BIGINT,
    daily_with_indicators BIGINT,
    daily_with_weekly_ref BIGINT,
    indicator_coverage_pct NUMERIC,
    weekly_coverage_pct NUMERIC,
    system_status TEXT
) 
LANGUAGE plpgsql
AS $$
DECLARE
    v_total_daily BIGINT;
    v_total_weekly BIGINT;
    v_daily_with_indicators BIGINT;
    v_daily_with_weekly_ref BIGINT;
    v_indicator_coverage NUMERIC;
    v_weekly_coverage NUMERIC;
    v_status TEXT;
BEGIN
    
    SELECT COUNT(*) INTO v_total_daily FROM daily_candles;
    SELECT COUNT(*) INTO v_total_weekly FROM weekly_candles;
    
    SELECT COUNT(*) INTO v_daily_with_indicators 
    FROM daily_candles 
    WHERE indicators IS NOT NULL 
    AND jsonb_typeof(indicators) = 'object';
    
    SELECT COUNT(*) INTO v_daily_with_weekly_ref
    FROM daily_candles 
    WHERE weekly_candle_key_id IS NOT NULL;
    
    v_indicator_coverage := CASE WHEN v_total_daily > 0 THEN 
        ROUND((v_daily_with_indicators::numeric / v_total_daily::numeric) * 100, 2)
    ELSE 0 END;
    
    v_weekly_coverage := CASE WHEN v_total_daily > 0 THEN 
        ROUND((v_daily_with_weekly_ref::numeric / v_total_daily::numeric) * 100, 2)
    ELSE 0 END;
    
    -- Determine system status
    IF v_indicator_coverage >= 95 AND v_weekly_coverage >= 95 THEN
        v_status := 'EXCELLENT';
    ELSIF v_indicator_coverage >= 80 AND v_weekly_coverage >= 80 THEN
        v_status := 'GOOD';
    ELSIF v_indicator_coverage >= 50 AND v_weekly_coverage >= 50 THEN
        v_status := 'FAIR';
    ELSE
        v_status := 'POOR';
    END IF;
    
    RETURN QUERY SELECT 
        v_total_daily,
        v_total_weekly,
        v_daily_with_indicators,
        v_daily_with_weekly_ref,
        v_indicator_coverage,
        v_weekly_coverage,
        v_status;
        
END;
$$;