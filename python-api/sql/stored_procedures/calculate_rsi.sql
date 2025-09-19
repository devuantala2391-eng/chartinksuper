-- =====================================================
-- RSI (RELATIVE STRENGTH INDEX) CALCULATION
-- =====================================================
-- Uses Wilder's smoothing method for accurate RSI calculation
-- Follows the same architecture as ATR and SuperTrend
-- =====================================================

-- =====================================================
-- DAILY RSI CALCULATION FOR SINGLE SYMBOL
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_daily_rsi_for_symbol(
    p_symbol TEXT,
    p_period INTEGER DEFAULT 14,
    p_force_recalculate BOOLEAN DEFAULT FALSE
)
RETURNS TABLE(
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT,
    indicator_key TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_updated_rows INTEGER := 0;
    v_indicator_key TEXT;
    v_existing_count INTEGER;
    v_total_count INTEGER;
    rec RECORD;
    v_avg_gain NUMERIC := NULL;
    v_avg_loss NUMERIC := NULL;
    v_alpha NUMERIC;
BEGIN
    -- Generate indicator key
    v_indicator_key := 'daily_rsi_' || p_period;

    -- Wilder's smoothing factor
    v_alpha := 1.0 / p_period;

    RAISE NOTICE 'Processing daily RSI(%) for symbol: %', p_period, p_symbol;

    -- Check if indicator already exists (unless force recalculate)
    IF NOT p_force_recalculate THEN
        SELECT COUNT(*) INTO v_total_count
        FROM daily_candles
        WHERE symbol = p_symbol;

        SELECT COUNT(*) INTO v_existing_count
        FROM daily_candles
        WHERE symbol = p_symbol
        AND indicators ? v_indicator_key
        AND (indicators->v_indicator_key) IS NOT NULL;

        -- If all rows already have the indicator, skip calculation
        IF v_existing_count = v_total_count AND v_total_count > 0 THEN
            RAISE NOTICE 'Indicator % already exists for all % rows of symbol %, skipping calculation',
                v_indicator_key, v_total_count, p_symbol;

            RETURN QUERY SELECT
                0,
                0,
                'ALREADY_EXISTS'::TEXT,
                v_indicator_key;
            RETURN;
        END IF;
    END IF;

    -- Process candles sequentially for RSI calculation
    FOR rec IN
        SELECT
            candle_key_id,
            candle_sequence_number,
            close,
            LAG(close, 1) OVER (ORDER BY candle_sequence_number) as prev_close
        FROM daily_candles
        WHERE symbol = p_symbol
        ORDER BY candle_sequence_number
    LOOP
        DECLARE
            v_change NUMERIC;
            v_gain NUMERIC := 0;
            v_loss NUMERIC := 0;
            v_rs NUMERIC;
            v_rsi NUMERIC;
        BEGIN
            -- Calculate price change
            IF rec.prev_close IS NOT NULL THEN
                v_change := rec.close - rec.prev_close;
                v_gain := GREATEST(v_change, 0);
                v_loss := GREATEST(-v_change, 0);
            END IF;

            -- Initialize averages for the first period (FIXED ORDER)
            IF v_avg_gain IS NULL AND rec.candle_sequence_number >= p_period THEN
                -- Calculate initial averages using CTE to avoid window function in aggregate
                WITH price_changes AS (
                    SELECT
                        c.close - COALESCE(LAG(c.close, 1) OVER (ORDER BY c.candle_sequence_number), c.close) as price_change
                    FROM daily_candles c
                    WHERE c.symbol = p_symbol
                    AND c.candle_sequence_number <= rec.candle_sequence_number
                    AND c.candle_sequence_number > rec.candle_sequence_number - p_period
                )
                SELECT
                    AVG(GREATEST(price_change, 0)),
                    AVG(GREATEST(-price_change, 0))
                INTO v_avg_gain, v_avg_loss
                FROM price_changes
                WHERE price_change IS NOT NULL;

                -- Calculate RSI for the first time
                IF v_avg_loss = 0 THEN
                    v_rsi := 100;
                ELSE
                    v_rs := v_avg_gain / v_avg_loss;
                    v_rsi := 100 - (100 / (1 + v_rs));
                END IF;
            ELSIF v_avg_gain IS NOT NULL THEN
                -- Apply Wilder's smoothing for subsequent periods
                -- Wilder's smoothing: new_avg = old_avg + alpha * (new_value - old_avg)
                v_avg_gain := v_avg_gain + v_alpha * (v_gain - v_avg_gain);
                v_avg_loss := v_avg_loss + v_alpha * (v_loss - v_avg_loss);

                -- Calculate RSI
                IF v_avg_loss = 0 THEN
                    v_rsi := 100;
                ELSE
                    v_rs := v_avg_gain / v_avg_loss;
                    v_rsi := 100 - (100 / (1 + v_rs));
                END IF;
            ELSE
                -- Not enough data yet
                v_rsi := NULL;
            END IF;

            -- Update the candle with RSI value
            UPDATE daily_candles
            SET indicators = COALESCE(indicators, '{}'::jsonb) ||
                jsonb_build_object(v_indicator_key, ROUND(v_rsi, 2)),
                updated_at = CURRENT_TIMESTAMP
            WHERE candle_key_id = rec.candle_key_id
            AND (
                p_force_recalculate OR
                NOT (indicators ? v_indicator_key) OR
                (indicators->v_indicator_key) IS NULL
            );

            IF FOUND THEN
                v_updated_rows := v_updated_rows + 1;
            END IF;
        END;
    END LOOP;

    RAISE NOTICE 'Completed daily RSI calculation for %: % rows updated in % ms',
        p_symbol, v_updated_rows, EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time);

    RETURN QUERY SELECT
        v_updated_rows,
        EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
        'SUCCESS'::TEXT,
        v_indicator_key;

EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Error in calculate_daily_rsi_for_symbol: %', SQLERRM;
        RETURN QUERY SELECT
            0,
            EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
            ('ERROR: ' || SQLERRM)::TEXT,
            v_indicator_key;
END;
$$;

-- =====================================================
-- WEEKLY RSI CALCULATION (MAIN FUNCTION)
-- =====================================================
-- Calculates RSI on actual weekly candles, then updates daily candles via sliding window
CREATE OR REPLACE FUNCTION calculate_weekly_rsi(
    p_period INTEGER DEFAULT 14,
    p_symbol_filter TEXT DEFAULT NULL
)
RETURNS TABLE(
    processed_symbols INTEGER,
    updated_weekly_rows INTEGER,
    updated_daily_rows INTEGER,
    status TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_updated_weekly_rows INTEGER := 0;
    v_updated_daily_rows INTEGER := 0;
    v_processed_symbols INTEGER := 0;
    v_indicator_key TEXT;
    symbol_rec RECORD;
    candle_rec RECORD;
    v_avg_gain NUMERIC := NULL;
    v_avg_loss NUMERIC := NULL;
    v_alpha NUMERIC;
BEGIN
    -- Generate indicator key
    v_indicator_key := 'weekly_rsi_' || p_period;

    -- Wilder's smoothing factor
    v_alpha := 1.0 / p_period;

    RAISE NOTICE 'Calculating weekly RSI(%) with daily updates', p_period;

    -- Process each symbol
    FOR symbol_rec IN
        SELECT DISTINCT symbol FROM weekly_candles
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        v_processed_symbols := v_processed_symbols + 1;
        v_avg_gain := NULL;
        v_avg_loss := NULL;

        -- Calculate RSI for weekly candles
        FOR candle_rec IN
            SELECT
                weekly_candle_key_id,
                week_sequence_number,
                close,
                LAG(close, 1) OVER (ORDER BY week_sequence_number) as prev_close
            FROM weekly_candles
            WHERE symbol = symbol_rec.symbol
            ORDER BY week_sequence_number
        LOOP
            DECLARE
                v_change NUMERIC;
                v_gain NUMERIC := 0;
                v_loss NUMERIC := 0;
                v_rs NUMERIC;
                v_rsi NUMERIC;
            BEGIN
                -- Calculate price change
                IF candle_rec.prev_close IS NOT NULL THEN
                    v_change := candle_rec.close - candle_rec.prev_close;
                    v_gain := GREATEST(v_change, 0);
                    v_loss := GREATEST(-v_change, 0);
                END IF;

                -- Initialize averages for the first period (FIXED ORDER)
                IF v_avg_gain IS NULL AND candle_rec.week_sequence_number >= p_period THEN
                    -- Calculate initial averages using CTE to avoid window function in aggregate
                    WITH price_changes AS (
                        SELECT
                            w.close - COALESCE(LAG(w.close, 1) OVER (ORDER BY w.week_sequence_number), w.close) as price_change
                        FROM weekly_candles w
                        WHERE w.symbol = symbol_rec.symbol
                        AND w.week_sequence_number <= candle_rec.week_sequence_number
                        AND w.week_sequence_number > candle_rec.week_sequence_number - p_period
                    )
                    SELECT
                        AVG(GREATEST(price_change, 0)),
                        AVG(GREATEST(-price_change, 0))
                    INTO v_avg_gain, v_avg_loss
                    FROM price_changes
                    WHERE price_change IS NOT NULL;

                    -- Calculate RSI for the first time
                    IF v_avg_loss = 0 THEN
                        v_rsi := 100;
                    ELSE
                        v_rs := v_avg_gain / v_avg_loss;
                        v_rsi := 100 - (100 / (1 + v_rs));
                    END IF;
                ELSIF v_avg_gain IS NOT NULL THEN
                    -- Apply Wilder's smoothing for subsequent periods
                    v_avg_gain := v_avg_gain + v_alpha * (v_gain - v_avg_gain);
                    v_avg_loss := v_avg_loss + v_alpha * (v_loss - v_avg_loss);

                    -- Calculate RSI
                    IF v_avg_loss = 0 THEN
                        v_rsi := 100;
                    ELSE
                        v_rs := v_avg_gain / v_avg_loss;
                        v_rsi := 100 - (100 / (1 + v_rs));
                    END IF;
                ELSE
                    -- Not enough data yet
                    v_rsi := NULL;
                END IF;

                -- Store in weekly_candles (RSI value + internal states for sliding window performance)
                UPDATE weekly_candles
                SET indicators = COALESCE(indicators, '{}')::jsonb ||
                    jsonb_build_object(
                        v_indicator_key, ROUND(v_rsi, 2),
                        '_' || v_indicator_key || '_avg_gain', ROUND(v_avg_gain, 4),
                        '_' || v_indicator_key || '_avg_loss', ROUND(v_avg_loss, 4)
                    ),
                    updated_at = CURRENT_TIMESTAMP
                WHERE weekly_candle_key_id = candle_rec.weekly_candle_key_id;

                v_updated_weekly_rows := v_updated_weekly_rows + 1;
            END;
        END LOOP;
    END LOOP;

    -- Update daily candles with sliding window RSI
    PERFORM update_daily_weekly_rsi(p_period, p_symbol_filter);
    GET DIAGNOSTICS v_updated_daily_rows = ROW_COUNT;

    RETURN QUERY SELECT
        v_processed_symbols,
        v_updated_weekly_rows,
        v_updated_daily_rows,
        'SUCCESS'::TEXT;

EXCEPTION
    WHEN OTHERS THEN
        RETURN QUERY SELECT
            v_processed_symbols,
            v_updated_weekly_rows,
            v_updated_daily_rows,
            format('ERROR: %s', SQLERRM)::TEXT;
END;
$$;

-- =====================================================
-- MONTHLY RSI CALCULATION (MAIN FUNCTION)
-- =====================================================
-- Calculates RSI on actual monthly candles, then updates daily candles via sliding window
CREATE OR REPLACE FUNCTION calculate_monthly_rsi(
    p_period INTEGER DEFAULT 14,
    p_symbol_filter TEXT DEFAULT NULL
)
RETURNS TABLE(
    processed_symbols INTEGER,
    updated_monthly_rows INTEGER,
    updated_daily_rows INTEGER,
    status TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_updated_monthly_rows INTEGER := 0;
    v_updated_daily_rows INTEGER := 0;
    v_processed_symbols INTEGER := 0;
    v_indicator_key TEXT;
    symbol_rec RECORD;
    candle_rec RECORD;
    v_avg_gain NUMERIC := NULL;
    v_avg_loss NUMERIC := NULL;
    v_alpha NUMERIC;
BEGIN
    -- Generate indicator key
    v_indicator_key := 'monthly_rsi_' || p_period;

    -- Wilder's smoothing factor
    v_alpha := 1.0 / p_period;

    RAISE NOTICE 'Calculating monthly RSI(%) with daily updates', p_period;

    -- Process each symbol
    FOR symbol_rec IN
        SELECT DISTINCT symbol FROM monthly_candles
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        v_processed_symbols := v_processed_symbols + 1;
        v_avg_gain := NULL;
        v_avg_loss := NULL;

        -- Calculate RSI for monthly candles
        FOR candle_rec IN
            SELECT
                monthly_candle_key_id,
                month_sequence_number,
                close,
                LAG(close, 1) OVER (ORDER BY month_sequence_number) as prev_close
            FROM monthly_candles
            WHERE symbol = symbol_rec.symbol
            ORDER BY month_sequence_number
        LOOP
            DECLARE
                v_change NUMERIC;
                v_gain NUMERIC := 0;
                v_loss NUMERIC := 0;
                v_rs NUMERIC;
                v_rsi NUMERIC;
            BEGIN
                -- Calculate price change
                IF candle_rec.prev_close IS NOT NULL THEN
                    v_change := candle_rec.close - candle_rec.prev_close;
                    v_gain := GREATEST(v_change, 0);
                    v_loss := GREATEST(-v_change, 0);
                END IF;

                -- Initialize averages for the first period (FIXED ORDER)
                IF v_avg_gain IS NULL AND candle_rec.month_sequence_number >= p_period THEN
                    -- Calculate initial averages using CTE to avoid window function in aggregate
                    WITH price_changes AS (
                        SELECT
                            m.close - COALESCE(LAG(m.close, 1) OVER (ORDER BY m.month_sequence_number), m.close) as price_change
                        FROM monthly_candles m
                        WHERE m.symbol = symbol_rec.symbol
                        AND m.month_sequence_number <= candle_rec.month_sequence_number
                        AND m.month_sequence_number > candle_rec.month_sequence_number - p_period
                    )
                    SELECT
                        AVG(GREATEST(price_change, 0)),
                        AVG(GREATEST(-price_change, 0))
                    INTO v_avg_gain, v_avg_loss
                    FROM price_changes
                    WHERE price_change IS NOT NULL;

                    -- Calculate RSI for the first time
                    IF v_avg_loss = 0 THEN
                        v_rsi := 100;
                    ELSE
                        v_rs := v_avg_gain / v_avg_loss;
                        v_rsi := 100 - (100 / (1 + v_rs));
                    END IF;
                ELSIF v_avg_gain IS NOT NULL THEN
                    -- Apply Wilder's smoothing for subsequent periods
                    v_avg_gain := v_avg_gain + v_alpha * (v_gain - v_avg_gain);
                    v_avg_loss := v_avg_loss + v_alpha * (v_loss - v_avg_loss);

                    -- Calculate RSI
                    IF v_avg_loss = 0 THEN
                        v_rsi := 100;
                    ELSE
                        v_rs := v_avg_gain / v_avg_loss;
                        v_rsi := 100 - (100 / (1 + v_rs));
                    END IF;
                ELSE
                    -- Not enough data yet
                    v_rsi := NULL;
                END IF;

                -- Store in monthly_candles (RSI value + internal states for sliding window performance)
                UPDATE monthly_candles
                SET indicators = COALESCE(indicators, '{}')::jsonb ||
                    jsonb_build_object(
                        v_indicator_key, ROUND(v_rsi, 2),
                        '_' || v_indicator_key || '_avg_gain', ROUND(v_avg_gain, 4),
                        '_' || v_indicator_key || '_avg_loss', ROUND(v_avg_loss, 4)
                    ),
                    updated_at = CURRENT_TIMESTAMP
                WHERE monthly_candle_key_id = candle_rec.monthly_candle_key_id;

                v_updated_monthly_rows := v_updated_monthly_rows + 1;
            END;
        END LOOP;
    END LOOP;

    -- Update daily candles with sliding window RSI
    PERFORM update_daily_monthly_rsi(p_period, p_symbol_filter);
    GET DIAGNOSTICS v_updated_daily_rows = ROW_COUNT;

    RETURN QUERY SELECT
        v_processed_symbols,
        v_updated_monthly_rows,
        v_updated_daily_rows,
        'SUCCESS'::TEXT;

EXCEPTION
    WHEN OTHERS THEN
        RETURN QUERY SELECT
            v_processed_symbols,
            v_updated_monthly_rows,
            v_updated_daily_rows,
            format('ERROR: %s', SQLERRM)::TEXT;
END;
$$;

-- =====================================================
-- SLIDING WINDOW RSI UPDATE FUNCTIONS
-- =====================================================

-- Update daily candles with weekly RSI sliding window (CORRECTED)
CREATE OR REPLACE FUNCTION update_daily_weekly_rsi(
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
    v_alpha NUMERIC;
    symbol_rec RECORD;
    candle_rec RECORD;
    v_previous_weekly_avg_gain NUMERIC;
    v_previous_weekly_avg_loss NUMERIC;
    v_current_rsi NUMERIC;
BEGIN
    -- Generate indicator key for daily storage
    v_indicator_key := 'weekly_rsi_' || p_period;

    -- Wilder's smoothing factor
    v_alpha := 1.0 / p_period;

    RAISE NOTICE 'Updating daily candles with weekly RSI(%) sliding window using partial week data', p_period;

    -- Process each symbol
    FOR symbol_rec IN
        SELECT DISTINCT symbol FROM daily_candles
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        v_processed_symbols := v_processed_symbols + 1;

        -- Update each daily candle with sliding window weekly RSI
        FOR candle_rec IN
            SELECT
                dc.candle_key_id,
                dc.candle_sequence_number,
                dc.weekly_candle_key_id,
                dc.weekly_open,
                dc.weekly_high,
                dc.weekly_low,
                dc.weekly_close,  -- This is the current partial week's close
                wc.week_sequence_number
            FROM daily_candles dc
            LEFT JOIN weekly_candles wc ON wc.weekly_candle_key_id = dc.weekly_candle_key_id
            WHERE dc.symbol = symbol_rec.symbol
            AND wc.week_sequence_number IS NOT NULL
            ORDER BY dc.candle_sequence_number
        LOOP
            -- Skip candles from first p_period weeks
            IF candle_rec.week_sequence_number <= p_period THEN
                UPDATE daily_candles
                SET indicators = COALESCE(indicators, '{}')::jsonb ||
                    jsonb_build_object(v_indicator_key, NULL),
                    updated_at = CURRENT_TIMESTAMP
                WHERE candle_key_id = candle_rec.candle_key_id;
                v_updated_rows := v_updated_rows + 1;
                CONTINUE;
            END IF;

            -- Get previous week's RSI calculation state (using internal keys)
            SELECT
                wc_prev.indicators->('_weekly_rsi_' || p_period || '_avg_gain'),
                wc_prev.indicators->('_weekly_rsi_' || p_period || '_avg_loss')
            INTO v_previous_weekly_avg_gain, v_previous_weekly_avg_loss
            FROM weekly_candles wc_prev
            WHERE wc_prev.symbol = symbol_rec.symbol
            AND wc_prev.week_sequence_number = candle_rec.week_sequence_number - 1;

            -- Skip if previous week's RSI state is not available
            IF v_previous_weekly_avg_gain IS NULL OR v_previous_weekly_avg_loss IS NULL THEN
                CONTINUE;
            END IF;

            -- Calculate sliding window weekly RSI using current week's data
            DECLARE
                v_week_change NUMERIC;
                v_week_gain NUMERIC := 0;
                v_week_loss NUMERIC := 0;
                v_current_avg_gain NUMERIC;
                v_current_avg_loss NUMERIC;
                v_rs NUMERIC;
                v_previous_week_close NUMERIC;
            BEGIN
                -- Get the previous week's close price to calculate proper week-to-week change
                SELECT close INTO v_previous_week_close
                FROM weekly_candles
                WHERE symbol = symbol_rec.symbol
                AND week_sequence_number = candle_rec.week_sequence_number - 1;

                -- Calculate week-to-week change (same as weekly candle calculation)
                IF v_previous_week_close IS NOT NULL THEN
                    v_week_change := candle_rec.weekly_close - v_previous_week_close;
                    v_week_gain := GREATEST(v_week_change, 0);
                    v_week_loss := GREATEST(-v_week_change, 0);
                END IF;

                -- Apply Wilder's smoothing with current week's data
                v_current_avg_gain := v_previous_weekly_avg_gain + v_alpha * (v_week_gain - v_previous_weekly_avg_gain);
                v_current_avg_loss := v_previous_weekly_avg_loss + v_alpha * (v_week_loss - v_previous_weekly_avg_loss);

                -- Calculate RSI
                IF v_current_avg_loss = 0 THEN
                    v_current_rsi := 100;
                ELSE
                    v_rs := v_current_avg_gain / v_current_avg_loss;
                    v_current_rsi := 100 - (100 / (1 + v_rs));
                END IF;

                -- Store in daily candles
                UPDATE daily_candles
                SET indicators = COALESCE(indicators, '{}')::jsonb ||
                    jsonb_build_object(v_indicator_key, ROUND(v_current_rsi, 2)),
                    updated_at = CURRENT_TIMESTAMP
                WHERE candle_key_id = candle_rec.candle_key_id;

                v_updated_rows := v_updated_rows + 1;
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

-- Update daily candles with monthly RSI sliding window (CORRECTED)
CREATE OR REPLACE FUNCTION update_daily_monthly_rsi(
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
    v_alpha NUMERIC;
    symbol_rec RECORD;
    candle_rec RECORD;
    v_previous_monthly_avg_gain NUMERIC;
    v_previous_monthly_avg_loss NUMERIC;
    v_current_rsi NUMERIC;
BEGIN
    -- Generate indicator key for daily storage
    v_indicator_key := 'monthly_rsi_' || p_period;

    -- Wilder's smoothing factor
    v_alpha := 1.0 / p_period;

    RAISE NOTICE 'Updating daily candles with monthly RSI(%) sliding window using partial month data', p_period;

    -- Process each symbol
    FOR symbol_rec IN
        SELECT DISTINCT symbol FROM daily_candles
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        v_processed_symbols := v_processed_symbols + 1;

        -- Update each daily candle with sliding window monthly RSI
        FOR candle_rec IN
            SELECT
                dc.candle_key_id,
                dc.candle_sequence_number,
                dc.monthly_candle_key_id,
                dc.monthly_open,
                dc.monthly_high,
                dc.monthly_low,
                dc.monthly_close,  -- This is the current partial month's close
                mc.month_sequence_number
            FROM daily_candles dc
            LEFT JOIN monthly_candles mc ON mc.monthly_candle_key_id = dc.monthly_candle_key_id
            WHERE dc.symbol = symbol_rec.symbol
            AND mc.month_sequence_number IS NOT NULL
            ORDER BY dc.candle_sequence_number
        LOOP
            -- Skip candles from first p_period months
            IF candle_rec.month_sequence_number <= p_period THEN
                UPDATE daily_candles
                SET indicators = COALESCE(indicators, '{}')::jsonb ||
                    jsonb_build_object(v_indicator_key, NULL),
                    updated_at = CURRENT_TIMESTAMP
                WHERE candle_key_id = candle_rec.candle_key_id;
                v_updated_rows := v_updated_rows + 1;
                CONTINUE;
            END IF;

            -- Get previous month's RSI calculation state (using internal keys)
            SELECT
                mc_prev.indicators->('_monthly_rsi_' || p_period || '_avg_gain'),
                mc_prev.indicators->('_monthly_rsi_' || p_period || '_avg_loss')
            INTO v_previous_monthly_avg_gain, v_previous_monthly_avg_loss
            FROM monthly_candles mc_prev
            WHERE mc_prev.symbol = symbol_rec.symbol
            AND mc_prev.month_sequence_number = candle_rec.month_sequence_number - 1;

            -- Skip if previous month's RSI state is not available
            IF v_previous_monthly_avg_gain IS NULL OR v_previous_monthly_avg_loss IS NULL THEN
                CONTINUE;
            END IF;

            -- Calculate sliding window monthly RSI using current month's data
            DECLARE
                v_month_change NUMERIC;
                v_month_gain NUMERIC := 0;
                v_month_loss NUMERIC := 0;
                v_current_avg_gain NUMERIC;
                v_current_avg_loss NUMERIC;
                v_rs NUMERIC;
                v_previous_month_close NUMERIC;
            BEGIN
                -- Get the previous month's close price to calculate proper month-to-month change
                SELECT close INTO v_previous_month_close
                FROM monthly_candles
                WHERE symbol = symbol_rec.symbol
                AND month_sequence_number = candle_rec.month_sequence_number - 1;

                -- Calculate month-to-month change (same as monthly candle calculation)
                IF v_previous_month_close IS NOT NULL THEN
                    v_month_change := candle_rec.monthly_close - v_previous_month_close;
                    v_month_gain := GREATEST(v_month_change, 0);
                    v_month_loss := GREATEST(-v_month_change, 0);
                END IF;

                -- Apply Wilder's smoothing with current month's data
                v_current_avg_gain := v_previous_monthly_avg_gain + v_alpha * (v_month_gain - v_previous_monthly_avg_gain);
                v_current_avg_loss := v_previous_monthly_avg_loss + v_alpha * (v_month_loss - v_previous_monthly_avg_loss);

                -- Calculate RSI
                IF v_current_avg_loss = 0 THEN
                    v_current_rsi := 100;
                ELSE
                    v_rs := v_current_avg_gain / v_current_avg_loss;
                    v_current_rsi := 100 - (100 / (1 + v_rs));
                END IF;

                -- Store in daily candles
                UPDATE daily_candles
                SET indicators = COALESCE(indicators, '{}')::jsonb ||
                    jsonb_build_object(v_indicator_key, ROUND(v_current_rsi, 2)),
                    updated_at = CURRENT_TIMESTAMP
                WHERE candle_key_id = candle_rec.candle_key_id;

                v_updated_rows := v_updated_rows + 1;
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

-- Grant permissions
GRANT EXECUTE ON FUNCTION calculate_daily_rsi_for_symbol(TEXT, INTEGER, BOOLEAN) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_weekly_rsi(INTEGER, TEXT) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_monthly_rsi(INTEGER, TEXT) TO PUBLIC;
GRANT EXECUTE ON FUNCTION update_daily_weekly_rsi(INTEGER, TEXT) TO PUBLIC;
GRANT EXECUTE ON FUNCTION update_daily_monthly_rsi(INTEGER, TEXT) TO PUBLIC;