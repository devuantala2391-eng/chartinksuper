-- =====================================================
-- ATR (Average True Range) CALCULATION - ALL TIMEFRAMES
-- =====================================================
-- Implements Wilder's smoothing method for ATR calculation
-- Supports daily, weekly, and monthly timeframes
-- Stores ATR values in respective table's indicators column
-- =====================================================

-- Helper function for formatting multiplier values in keys
CREATE OR REPLACE FUNCTION format_multiplier_for_key(value NUMERIC)
RETURNS TEXT AS $$
BEGIN
    IF value = FLOOR(value) THEN
        RETURN FLOOR(value)::TEXT;
    ELSE
        RETURN REPLACE(value::TEXT, '.', 'dot');
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- =====================================================
-- DAILY ATR CALCULATION
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_atr(
    p_period INTEGER DEFAULT 14,
    p_symbol_filter TEXT DEFAULT NULL,
    p_limit INTEGER DEFAULT NULL
)
RETURNS TABLE(
    processed_symbols INTEGER,
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_updated_rows INTEGER := 0;
    v_processed_symbols INTEGER := 0;
    v_indicator_key TEXT;
    symbol_rec RECORD;
    candle_rec RECORD;
    v_prev_atr NUMERIC := NULL;
    v_current_atr NUMERIC;
    v_tr_sum NUMERIC := 0;
    v_tr_count INTEGER := 0;
BEGIN
    -- Generate indicator key with daily prefix for consistency
    v_indicator_key := 'daily_atr_' || p_period;

    RAISE NOTICE 'Calculating daily ATR(%) using Wilders smoothing', p_period;

    -- Process each symbol
    FOR symbol_rec IN
        SELECT DISTINCT symbol FROM daily_candles
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
        LIMIT COALESCE(p_limit, 2147483647)
    LOOP
        v_processed_symbols := v_processed_symbols + 1;
        v_prev_atr := NULL;
        v_tr_sum := 0;
        v_tr_count := 0;

        -- Calculate ATR for each candle in sequence
        FOR candle_rec IN
            SELECT
                candle_key_id,
                candle_sequence_number,
                high,
                low,
                close,
                LAG(close, 1) OVER (ORDER BY candle_sequence_number) as prev_close
            FROM daily_candles
            WHERE symbol = symbol_rec.symbol
            ORDER BY candle_sequence_number
        LOOP
            -- Skip first candle (no previous close)
            IF candle_rec.prev_close IS NULL THEN
                CONTINUE;
            END IF;

            -- Calculate True Range for this candle
            DECLARE
                v_true_range NUMERIC;
            BEGIN
                v_true_range := GREATEST(
                    candle_rec.high - candle_rec.low,
                    ABS(candle_rec.high - candle_rec.prev_close),
                    ABS(candle_rec.low - candle_rec.prev_close)
                );

                v_tr_count := v_tr_count + 1;

                IF v_tr_count <= p_period THEN
                    -- Accumulate for initial SMA
                    v_tr_sum := v_tr_sum + v_true_range;

                    IF v_tr_count = p_period THEN
                        -- Calculate first ATR as simple average
                        v_current_atr := v_tr_sum / p_period;
                        v_prev_atr := v_current_atr;

                        -- Store the ATR value
                        UPDATE daily_candles
                        SET indicators = COALESCE(indicators, '{}')::jsonb ||
                            jsonb_build_object(v_indicator_key, ROUND(v_current_atr::numeric, 2)),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE candle_key_id = candle_rec.candle_key_id;

                        v_updated_rows := v_updated_rows + 1;
                    END IF;
                ELSE
                    -- Use Wilder's RMA: ATR = ((n-1) * Previous_ATR + TR) / n
                    v_current_atr := ((p_period - 1) * v_prev_atr + v_true_range) / p_period;
                    v_prev_atr := v_current_atr;

                    -- Store the ATR value
                    UPDATE daily_candles
                    SET indicators = COALESCE(indicators, '{}')::jsonb ||
                        jsonb_build_object(v_indicator_key, ROUND(v_current_atr::numeric, 2)),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE candle_key_id = candle_rec.candle_key_id;

                    v_updated_rows := v_updated_rows + 1;
                END IF;
            END;
        END LOOP;
    END LOOP;

    RETURN QUERY SELECT
        v_processed_symbols,
        v_updated_rows,
        EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
        'SUCCESS'::TEXT;

EXCEPTION
    WHEN OTHERS THEN
        RETURN QUERY SELECT
            v_processed_symbols,
            v_updated_rows,
            EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
            format('ERROR: %s', SQLERRM)::TEXT;
END;
$$;

-- =====================================================
-- WEEKLY ATR CALCULATION
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_weekly_atr(
    p_period INTEGER DEFAULT 14,
    p_symbol_filter TEXT DEFAULT NULL,
    p_limit INTEGER DEFAULT NULL
)
RETURNS TABLE(
    processed_symbols INTEGER,
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_updated_rows INTEGER := 0;
    v_processed_symbols INTEGER := 0;
    v_indicator_key TEXT;
    symbol_rec RECORD;
    candle_rec RECORD;
    v_prev_atr NUMERIC := NULL;
    v_current_atr NUMERIC;
    v_tr_sum NUMERIC := 0;
    v_tr_count INTEGER := 0;
BEGIN
    -- Generate indicator key for weekly ATR
    v_indicator_key := 'weekly_atr_' || p_period;

    RAISE NOTICE 'Calculating weekly ATR(%) using Wilders smoothing', p_period;

    -- Process each symbol
    FOR symbol_rec IN
        SELECT DISTINCT symbol FROM weekly_candles
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
        LIMIT COALESCE(p_limit, 2147483647)
    LOOP
        v_processed_symbols := v_processed_symbols + 1;
        v_prev_atr := NULL;
        v_tr_sum := 0;
        v_tr_count := 0;

        -- Calculate ATR for each weekly candle in sequence
        FOR candle_rec IN
            SELECT
                weekly_candle_key_id,
                week_sequence_number,
                high,
                low,
                close,
                LAG(close, 1) OVER (ORDER BY week_sequence_number) as prev_close
            FROM weekly_candles
            WHERE symbol = symbol_rec.symbol
            ORDER BY week_sequence_number
        LOOP
            -- Skip first candle (no previous close)
            IF candle_rec.prev_close IS NULL THEN
                CONTINUE;
            END IF;

            -- Calculate True Range for this weekly candle
            DECLARE
                v_true_range NUMERIC;
            BEGIN
                v_true_range := GREATEST(
                    candle_rec.high - candle_rec.low,
                    ABS(candle_rec.high - candle_rec.prev_close),
                    ABS(candle_rec.low - candle_rec.prev_close)
                );

                v_tr_count := v_tr_count + 1;

                IF v_tr_count <= p_period THEN
                    -- Accumulate for initial SMA
                    v_tr_sum := v_tr_sum + v_true_range;

                    IF v_tr_count = p_period THEN
                        -- Calculate first ATR as simple average
                        v_current_atr := v_tr_sum / p_period;
                        v_prev_atr := v_current_atr;

                        -- Store the ATR value in weekly_candles
                        UPDATE weekly_candles
                        SET indicators = COALESCE(indicators, '{}')::jsonb ||
                            jsonb_build_object(v_indicator_key, ROUND(v_current_atr::numeric, 2)),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE weekly_candle_key_id = candle_rec.weekly_candle_key_id;

                        v_updated_rows := v_updated_rows + 1;
                    END IF;
                ELSE
                    -- Use Wilder's RMA: ATR = ((n-1) * Previous_ATR + TR) / n
                    v_current_atr := ((p_period - 1) * v_prev_atr + v_true_range) / p_period;
                    v_prev_atr := v_current_atr;

                    -- Store the ATR value in weekly_candles
                    UPDATE weekly_candles
                    SET indicators = COALESCE(indicators, '{}')::jsonb ||
                        jsonb_build_object(v_indicator_key, ROUND(v_current_atr::numeric, 2)),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE weekly_candle_key_id = candle_rec.weekly_candle_key_id;

                    v_updated_rows := v_updated_rows + 1;
                END IF;
            END;
        END LOOP;
    END LOOP;

    RETURN QUERY SELECT
        v_processed_symbols,
        v_updated_rows,
        EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
        'SUCCESS'::TEXT;

EXCEPTION
    WHEN OTHERS THEN
        RETURN QUERY SELECT
            v_processed_symbols,
            v_updated_rows,
            EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
            format('ERROR: %s', SQLERRM)::TEXT;
END;
$$;

-- =====================================================
-- MONTHLY ATR CALCULATION
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_monthly_atr(
    p_period INTEGER DEFAULT 14,
    p_symbol_filter TEXT DEFAULT NULL,
    p_limit INTEGER DEFAULT NULL
)
RETURNS TABLE(
    processed_symbols INTEGER,
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_updated_rows INTEGER := 0;
    v_processed_symbols INTEGER := 0;
    v_indicator_key TEXT;
    symbol_rec RECORD;
    candle_rec RECORD;
    v_prev_atr NUMERIC := NULL;
    v_current_atr NUMERIC;
    v_tr_sum NUMERIC := 0;
    v_tr_count INTEGER := 0;
BEGIN
    -- Generate indicator key for monthly ATR
    v_indicator_key := 'monthly_atr_' || p_period;

    RAISE NOTICE 'Calculating monthly ATR(%) using Wilders smoothing', p_period;

    -- Process each symbol
    FOR symbol_rec IN
        SELECT DISTINCT symbol FROM monthly_candles
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
        LIMIT COALESCE(p_limit, 2147483647)
    LOOP
        v_processed_symbols := v_processed_symbols + 1;
        v_prev_atr := NULL;
        v_tr_sum := 0;
        v_tr_count := 0;

        -- Calculate ATR for each monthly candle in sequence
        FOR candle_rec IN
            SELECT
                monthly_candle_key_id,
                month_sequence_number,
                high,
                low,
                close,
                LAG(close, 1) OVER (ORDER BY month_sequence_number) as prev_close
            FROM monthly_candles
            WHERE symbol = symbol_rec.symbol
            ORDER BY month_sequence_number
        LOOP
            -- Skip first candle (no previous close)
            IF candle_rec.prev_close IS NULL THEN
                CONTINUE;
            END IF;

            -- Calculate True Range for this monthly candle
            DECLARE
                v_true_range NUMERIC;
            BEGIN
                v_true_range := GREATEST(
                    candle_rec.high - candle_rec.low,
                    ABS(candle_rec.high - candle_rec.prev_close),
                    ABS(candle_rec.low - candle_rec.prev_close)
                );

                v_tr_count := v_tr_count + 1;

                IF v_tr_count <= p_period THEN
                    -- Accumulate for initial SMA
                    v_tr_sum := v_tr_sum + v_true_range;

                    IF v_tr_count = p_period THEN
                        -- Calculate first ATR as simple average
                        v_current_atr := v_tr_sum / p_period;
                        v_prev_atr := v_current_atr;

                        -- Store the ATR value in monthly_candles
                        UPDATE monthly_candles
                        SET indicators = COALESCE(indicators, '{}')::jsonb ||
                            jsonb_build_object(v_indicator_key, ROUND(v_current_atr::numeric, 2)),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE monthly_candle_key_id = candle_rec.monthly_candle_key_id;

                        v_updated_rows := v_updated_rows + 1;
                    END IF;
                ELSE
                    -- Use Wilder's RMA: ATR = ((n-1) * Previous_ATR + TR) / n
                    v_current_atr := ((p_period - 1) * v_prev_atr + v_true_range) / p_period;
                    v_prev_atr := v_current_atr;

                    -- Store the ATR value in monthly_candles
                    UPDATE monthly_candles
                    SET indicators = COALESCE(indicators, '{}')::jsonb ||
                        jsonb_build_object(v_indicator_key, ROUND(v_current_atr::numeric, 2)),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE monthly_candle_key_id = candle_rec.monthly_candle_key_id;

                    v_updated_rows := v_updated_rows + 1;
                END IF;
            END;
        END LOOP;
    END LOOP;

    RETURN QUERY SELECT
        v_processed_symbols,
        v_updated_rows,
        EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
        'SUCCESS'::TEXT;

EXCEPTION
    WHEN OTHERS THEN
        RETURN QUERY SELECT
            v_processed_symbols,
            v_updated_rows,
            EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
            format('ERROR: %s', SQLERRM)::TEXT;
END;
$$;

-- Grant permissions for all ATR functions
GRANT EXECUTE ON FUNCTION calculate_atr(INTEGER, TEXT, INTEGER) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_weekly_atr(INTEGER, TEXT, INTEGER) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_monthly_atr(INTEGER, TEXT, INTEGER) TO PUBLIC;