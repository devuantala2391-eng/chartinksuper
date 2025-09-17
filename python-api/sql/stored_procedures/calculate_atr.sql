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

    -- After weekly ATR calculation is complete, update daily candles
    DECLARE
        daily_update_result RECORD;
    BEGIN
        RAISE NOTICE 'Weekly ATR calculation complete. Updating daily candles...';

        -- Call the daily update function
        SELECT * INTO daily_update_result
        FROM update_daily_weekly_atr(p_period, p_symbol_filter);

        RAISE NOTICE 'Daily weekly ATR update: % symbols, % rows updated',
            daily_update_result.processed_symbols, daily_update_result.updated_rows;
    END;

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

    -- After monthly ATR calculation is complete, update daily candles
    DECLARE
        daily_update_result RECORD;
    BEGIN
        RAISE NOTICE 'Monthly ATR calculation complete. Updating daily candles...';

        -- Call the daily update function
        SELECT * INTO daily_update_result
        FROM update_daily_monthly_atr(p_period, p_symbol_filter);

        RAISE NOTICE 'Daily monthly ATR update: % symbols, % rows updated',
            daily_update_result.processed_symbols, daily_update_result.updated_rows;
    END;

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
-- UPDATE DAILY CANDLES WITH WEEKLY ATR
-- =====================================================
CREATE OR REPLACE FUNCTION update_daily_weekly_atr(
    p_period INTEGER DEFAULT 14,
    p_symbol_filter TEXT DEFAULT NULL
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
    v_previous_weekly_atr NUMERIC;
    v_previous_weekly_close NUMERIC;
    v_current_tr NUMERIC;
    v_daily_weekly_atr NUMERIC;
BEGIN
    -- Generate indicator key for daily storage of weekly ATR
    v_indicator_key := 'weekly_atr_' || p_period;

    RAISE NOTICE 'Updating daily candles with weekly ATR(%) values', p_period;

    -- Process each symbol
    FOR symbol_rec IN
        SELECT DISTINCT symbol FROM daily_candles
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        v_processed_symbols := v_processed_symbols + 1;

        -- Update each daily candle with weekly ATR
        FOR candle_rec IN
            SELECT
                dc.candle_key_id,
                dc.candle_sequence_number,
                dc.weekly_candle_key_id,
                dc.close,
                dc.weekly_high,
                dc.weekly_low,
                wc.week_sequence_number,
                wc.indicators->>v_indicator_key as weekly_atr_value
            FROM daily_candles dc
            LEFT JOIN weekly_candles wc ON wc.weekly_candle_key_id = dc.weekly_candle_key_id
            WHERE dc.symbol = symbol_rec.symbol
            AND wc.week_sequence_number IS NOT NULL
            ORDER BY dc.candle_sequence_number
        LOOP
            -- Skip candles from first p_period weeks (should be NULL)
            IF candle_rec.week_sequence_number <= p_period THEN
                -- Set NULL for insufficient data period
                UPDATE daily_candles
                SET indicators = COALESCE(indicators, '{}')::jsonb ||
                    jsonb_build_object(v_indicator_key, NULL),
                    updated_at = CURRENT_TIMESTAMP
                WHERE candle_key_id = candle_rec.candle_key_id
                AND (
                    NOT (indicators ? v_indicator_key) OR
                    (indicators->v_indicator_key) IS NULL
                );
                v_updated_rows := v_updated_rows + 1;
                CONTINUE;
            END IF;

            -- Get previous week's ATR and close price
            SELECT
                wc_prev.indicators->>v_indicator_key,
                wc_prev.close
            INTO v_previous_weekly_atr, v_previous_weekly_close
            FROM weekly_candles wc_prev
            WHERE wc_prev.symbol = symbol_rec.symbol
            AND wc_prev.week_sequence_number = candle_rec.week_sequence_number - 1;

            -- Skip if previous week's ATR is not available
            IF v_previous_weekly_atr IS NULL THEN
                CONTINUE;
            END IF;

            -- Calculate current week's True Range using sliding window
            -- (partial week data up to current day)
            v_current_tr := GREATEST(
                candle_rec.weekly_high - candle_rec.weekly_low,
                ABS(candle_rec.weekly_high - v_previous_weekly_close),
                ABS(candle_rec.weekly_low - v_previous_weekly_close)
            );

            -- Apply Wilder's smoothing formula
            v_daily_weekly_atr := ((p_period - 1) * v_previous_weekly_atr::NUMERIC + v_current_tr) / p_period;

            -- Store in daily candles
            UPDATE daily_candles
            SET indicators = COALESCE(indicators, '{}')::jsonb ||
                jsonb_build_object(v_indicator_key, ROUND(v_daily_weekly_atr::numeric, 2)),
                updated_at = CURRENT_TIMESTAMP
            WHERE candle_key_id = candle_rec.candle_key_id;

            v_updated_rows := v_updated_rows + 1;
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
-- UPDATE DAILY CANDLES WITH MONTHLY ATR
-- =====================================================
CREATE OR REPLACE FUNCTION update_daily_monthly_atr(
    p_period INTEGER DEFAULT 14,
    p_symbol_filter TEXT DEFAULT NULL
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
    v_previous_monthly_atr NUMERIC;
    v_previous_monthly_close NUMERIC;
    v_current_tr NUMERIC;
    v_daily_monthly_atr NUMERIC;
BEGIN
    -- Generate indicator key for daily storage of monthly ATR
    v_indicator_key := 'monthly_atr_' || p_period;

    RAISE NOTICE 'Updating daily candles with monthly ATR(%) values', p_period;

    -- Process each symbol
    FOR symbol_rec IN
        SELECT DISTINCT symbol FROM daily_candles
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        v_processed_symbols := v_processed_symbols + 1;

        -- Update each daily candle with monthly ATR
        FOR candle_rec IN
            SELECT
                dc.candle_key_id,
                dc.candle_sequence_number,
                dc.monthly_candle_key_id,
                dc.close,
                dc.monthly_high,
                dc.monthly_low,
                mc.month_sequence_number,
                mc.indicators->>v_indicator_key as monthly_atr_value
            FROM daily_candles dc
            LEFT JOIN monthly_candles mc ON mc.monthly_candle_key_id = dc.monthly_candle_key_id
            WHERE dc.symbol = symbol_rec.symbol
            AND mc.month_sequence_number IS NOT NULL
            ORDER BY dc.candle_sequence_number
        LOOP
            -- Skip candles from first p_period months (should be NULL)
            IF candle_rec.month_sequence_number <= p_period THEN
                -- Set NULL for insufficient data period
                UPDATE daily_candles
                SET indicators = COALESCE(indicators, '{}')::jsonb ||
                    jsonb_build_object(v_indicator_key, NULL),
                    updated_at = CURRENT_TIMESTAMP
                WHERE candle_key_id = candle_rec.candle_key_id
                AND (
                    NOT (indicators ? v_indicator_key) OR
                    (indicators->v_indicator_key) IS NULL
                );
                v_updated_rows := v_updated_rows + 1;
                CONTINUE;
            END IF;

            -- Get previous month's ATR and close price
            SELECT
                mc_prev.indicators->>v_indicator_key,
                mc_prev.close
            INTO v_previous_monthly_atr, v_previous_monthly_close
            FROM monthly_candles mc_prev
            WHERE mc_prev.symbol = symbol_rec.symbol
            AND mc_prev.month_sequence_number = candle_rec.month_sequence_number - 1;

            -- Skip if previous month's ATR is not available
            IF v_previous_monthly_atr IS NULL THEN
                CONTINUE;
            END IF;

            -- Calculate current month's True Range using sliding window
            -- (partial month data up to current day)
            v_current_tr := GREATEST(
                candle_rec.monthly_high - candle_rec.monthly_low,
                ABS(candle_rec.monthly_high - v_previous_monthly_close),
                ABS(candle_rec.monthly_low - v_previous_monthly_close)
            );

            -- Apply Wilder's smoothing formula
            v_daily_monthly_atr := ((p_period - 1) * v_previous_monthly_atr::NUMERIC + v_current_tr) / p_period;

            -- Store in daily candles
            UPDATE daily_candles
            SET indicators = COALESCE(indicators, '{}')::jsonb ||
                jsonb_build_object(v_indicator_key, ROUND(v_daily_monthly_atr::numeric, 2)),
                updated_at = CURRENT_TIMESTAMP
            WHERE candle_key_id = candle_rec.candle_key_id;

            v_updated_rows := v_updated_rows + 1;
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
GRANT EXECUTE ON FUNCTION update_daily_weekly_atr(INTEGER, TEXT) TO PUBLIC;
GRANT EXECUTE ON FUNCTION update_daily_monthly_atr(INTEGER, TEXT) TO PUBLIC;