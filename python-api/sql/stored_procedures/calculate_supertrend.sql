-- =====================================================
-- CORRECTED SUPERTREND CALCULATION WITH PROPER ALGORITHM
-- =====================================================
-- Based on manual analysis - uses correct band persistence rules
-- =====================================================

-- Helper function for formatting multiplier values in keys
CREATE OR REPLACE FUNCTION format_decimal_param(value NUMERIC)
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
-- CORRECTED DAILY SUPERTREND CALCULATION FOR SINGLE SYMBOL
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_daily_supertrend_for_symbol(
    p_symbol TEXT,
    p_period INTEGER,
    p_multiplier NUMERIC,
    p_force_recalculate BOOLEAN DEFAULT FALSE
)
RETURNS TABLE(
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT,
    indicator_key TEXT,
    direction_key TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_updated_rows INTEGER := 0;
    v_indicator_key TEXT;
    v_direction_key TEXT;
    v_atr_key TEXT;
    v_existing_count INTEGER;
    v_total_count INTEGER;
    rec RECORD;
    v_final_upper NUMERIC := NULL;
    v_final_lower NUMERIC := NULL;
    v_trend INTEGER := NULL;
BEGIN
    -- Generate indicator keys
    v_indicator_key := 'daily_supertrend_' || p_period || '_' || format_decimal_param(p_multiplier);
    v_direction_key := v_indicator_key || '_direction';
    v_atr_key := 'daily_atr_' || p_period;

    RAISE NOTICE 'Processing CORRECTED daily SuperTrend(%, %) for symbol: %', p_period, p_multiplier, p_symbol;

    -- Check if indicator already exists (unless force recalculate)
    IF NOT p_force_recalculate THEN
        SELECT COUNT(*) INTO v_total_count
        FROM daily_candles
        WHERE symbol = p_symbol;

        SELECT COUNT(*) INTO v_existing_count
        FROM daily_candles
        WHERE symbol = p_symbol
        AND indicators ? v_indicator_key
        AND (indicators->v_indicator_key) IS NOT NULL
        AND indicators ? v_direction_key
        AND (indicators->v_direction_key) IS NOT NULL;

        -- If all rows already have the indicator, skip calculation
        IF v_existing_count = v_total_count AND v_total_count > 0 THEN
            RAISE NOTICE 'Indicator % already exists for all % rows of symbol %, skipping calculation',
                v_indicator_key, v_total_count, p_symbol;

            RETURN QUERY SELECT
                0,
                0,
                'ALREADY_EXISTS'::TEXT,
                v_indicator_key,
                v_direction_key;
            RETURN;
        END IF;
    END IF;

    -- Ensure ATR is calculated for this symbol/period
    IF NOT EXISTS (
        SELECT 1 FROM daily_candles
        WHERE symbol = p_symbol
        AND indicators ? v_atr_key
        AND (indicators->v_atr_key) IS NOT NULL
        LIMIT 1
    ) THEN
        RAISE NOTICE 'Daily ATR(%) not found for %, calculating ATR first', p_period, p_symbol;
        PERFORM * FROM calculate_daily_atr(p_period, p_symbol);
    END IF;

    -- Process candles sequentially with CORRECTED SuperTrend algorithm
    FOR rec IN
        SELECT
            candle_key_id,
            candle_sequence_number,
            high,
            low,
            close,
            (indicators->v_atr_key)::numeric as atr
        FROM daily_candles
        WHERE symbol = p_symbol
        AND indicators ? v_atr_key
        AND (indicators->v_atr_key) IS NOT NULL
        ORDER BY candle_sequence_number
    LOOP
        DECLARE
            v_hl2 NUMERIC := (rec.high + rec.low) / 2.0;
            v_basic_upper NUMERIC := v_hl2 + (p_multiplier * rec.atr);
            v_basic_lower NUMERIC := v_hl2 - (p_multiplier * rec.atr);
            v_supertrend NUMERIC;
            v_direction INTEGER;
        BEGIN
            -- CORRECTED BAND PERSISTENCE RULES
            IF v_final_upper IS NULL THEN
                -- First candle
                v_final_upper := v_basic_upper;
                v_final_lower := v_basic_lower;
            ELSE
                -- CORRECTED BAND PERSISTENCE LOGIC
                IF v_trend IS NULL OR v_trend = 0 THEN
                    -- Downtrend: Upper band can only decrease or stay same
                    IF v_basic_upper < v_final_upper THEN
                        v_final_upper := v_basic_upper;
                    END IF;
                    -- Lower band resets to current basic lower
                    v_final_lower := v_basic_lower;
                ELSE
                    -- Uptrend: Lower band can only increase or stay same
                    IF v_basic_lower > v_final_lower THEN
                        v_final_lower := v_basic_lower;
                    END IF;
                    -- Upper band resets to current basic upper
                    v_final_upper := v_basic_upper;
                END IF;
            END IF;

            -- CORRECTED TREND DETERMINATION
            IF v_trend IS NULL THEN
                -- Initial trend: downtrend if close <= upper band
                v_direction := CASE WHEN rec.close <= v_final_upper THEN 0 ELSE 1 END;
            ELSE
                -- Trend change logic
                IF v_trend = 1 THEN -- Previous uptrend
                    IF rec.close <= v_final_lower THEN
                        v_direction := 0; -- Switch to downtrend
                    ELSE
                        v_direction := 1; -- Continue uptrend
                    END IF;
                ELSE -- Previous downtrend (v_trend = 0)
                    IF rec.close >= v_final_upper THEN
                        v_direction := 1; -- Switch to uptrend
                    ELSE
                        v_direction := 0; -- Continue downtrend
                    END IF;
                END IF;
            END IF;

            -- SuperTrend value based on trend direction
            IF v_direction = 1 THEN
                v_supertrend := ROUND(v_final_lower, 2); -- Uptrend: use lower band
            ELSE
                v_supertrend := ROUND(v_final_upper, 2); -- Downtrend: use upper band
            END IF;

            -- Update the candle with SuperTrend values
            UPDATE daily_candles
            SET indicators = COALESCE(indicators, '{}'::jsonb) ||
                jsonb_build_object(
                    v_indicator_key, v_supertrend,
                    v_direction_key, v_direction
                ),
                updated_at = CURRENT_TIMESTAMP
            WHERE candle_key_id = rec.candle_key_id
            AND (
                p_force_recalculate OR
                NOT (indicators ? v_indicator_key) OR
                (indicators->v_indicator_key) IS NULL OR
                NOT (indicators ? v_direction_key) OR
                (indicators->v_direction_key) IS NULL
            );

            IF FOUND THEN
                v_updated_rows := v_updated_rows + 1;
            END IF;

            -- Store values for next iteration
            v_trend := v_direction;
        END;
    END LOOP;

    RAISE NOTICE 'Completed CORRECTED SuperTrend calculation for %: % rows updated in % ms',
        p_symbol, v_updated_rows, EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time);

    RETURN QUERY SELECT
        v_updated_rows,
        EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
        'SUCCESS'::TEXT,
        v_indicator_key,
        v_direction_key;

EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Error in calculate_daily_supertrend_for_symbol: %', SQLERRM;
        RETURN QUERY SELECT
            0,
            EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
            ('ERROR: ' || SQLERRM)::TEXT,
            v_indicator_key,
            v_direction_key;
END;
$$;

-- =====================================================
-- WEEKLY SUPERTREND CALCULATION (MAIN FUNCTION)
-- =====================================================
-- Calculates SuperTrend on actual weekly candles, then updates daily candles via sliding window
CREATE OR REPLACE FUNCTION calculate_weekly_supertrend(
    p_period INTEGER DEFAULT 10,
    p_multiplier NUMERIC DEFAULT 2.0,
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
    v_direction_key TEXT;
    v_atr_key TEXT;
    symbol_rec RECORD;
    candle_rec RECORD;
    v_final_upper NUMERIC := NULL;
    v_final_lower NUMERIC := NULL;
    v_trend INTEGER := NULL;
BEGIN
    -- Generate indicator keys
    v_indicator_key := 'supertrend_' || p_period || '_' || format_decimal_param(p_multiplier);
    v_direction_key := v_indicator_key || '_direction';
    v_atr_key := 'weekly_atr_' || p_period;

    RAISE NOTICE 'Calculating weekly SuperTrend(%, %) with daily updates', p_period, p_multiplier;

    -- Process each symbol
    FOR symbol_rec IN
        SELECT DISTINCT symbol FROM weekly_candles
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        v_processed_symbols := v_processed_symbols + 1;
        v_final_upper := NULL;
        v_final_lower := NULL;
        v_trend := NULL;

        -- Ensure weekly ATR exists
        IF NOT EXISTS (
            SELECT 1 FROM weekly_candles
            WHERE symbol = symbol_rec.symbol
            AND indicators ? v_atr_key
            AND (indicators->v_atr_key) IS NOT NULL
            LIMIT 1
        ) THEN
            RAISE NOTICE 'Weekly ATR(%) not found for %, calculating ATR first', p_period, symbol_rec.symbol;
            PERFORM * FROM calculate_weekly_atr(p_period, symbol_rec.symbol);
        END IF;

        -- Calculate SuperTrend for weekly candles
        FOR candle_rec IN
            SELECT
                weekly_candle_key_id,
                week_sequence_number,
                high,
                low,
                close,
                (indicators->v_atr_key)::numeric as atr
            FROM weekly_candles
            WHERE symbol = symbol_rec.symbol
            AND indicators ? v_atr_key
            AND (indicators->v_atr_key) IS NOT NULL
            ORDER BY week_sequence_number
        LOOP
            DECLARE
                v_hl2 NUMERIC := (candle_rec.high + candle_rec.low) / 2.0;
                v_basic_upper NUMERIC := v_hl2 + (p_multiplier * candle_rec.atr);
                v_basic_lower NUMERIC := v_hl2 - (p_multiplier * candle_rec.atr);
                v_supertrend NUMERIC;
                v_direction INTEGER;
            BEGIN
                -- SuperTrend band persistence logic
                IF v_final_upper IS NULL THEN
                    v_final_upper := v_basic_upper;
                    v_final_lower := v_basic_lower;
                ELSE
                    IF v_trend IS NULL OR v_trend = 0 THEN
                        -- Downtrend: Upper band can only decrease or stay same
                        IF v_basic_upper < v_final_upper THEN
                            v_final_upper := v_basic_upper;
                        END IF;
                        v_final_lower := v_basic_lower;
                    ELSE
                        -- Uptrend: Lower band can only increase or stay same
                        IF v_basic_lower > v_final_lower THEN
                            v_final_lower := v_basic_lower;
                        END IF;
                        v_final_upper := v_basic_upper;
                    END IF;
                END IF;

                -- Trend determination
                IF v_trend IS NULL THEN
                    v_direction := CASE WHEN candle_rec.close <= v_final_upper THEN 0 ELSE 1 END;
                ELSE
                    IF v_trend = 1 THEN
                        IF candle_rec.close <= v_final_lower THEN
                            v_direction := 0;
                        ELSE
                            v_direction := 1;
                        END IF;
                    ELSE
                        IF candle_rec.close >= v_final_upper THEN
                            v_direction := 1;
                        ELSE
                            v_direction := 0;
                        END IF;
                    END IF;
                END IF;

                -- SuperTrend value
                IF v_direction = 1 THEN
                    v_supertrend := ROUND(v_final_lower, 2);
                ELSE
                    v_supertrend := ROUND(v_final_upper, 2);
                END IF;

                -- Store in weekly_candles
                UPDATE weekly_candles
                SET indicators = COALESCE(indicators, '{}')::jsonb ||
                    jsonb_build_object(
                        v_indicator_key, v_supertrend,
                        v_direction_key, v_direction
                    ),
                    updated_at = CURRENT_TIMESTAMP
                WHERE weekly_candle_key_id = candle_rec.weekly_candle_key_id;

                v_updated_weekly_rows := v_updated_weekly_rows + 1;
                v_trend := v_direction;
            END;
        END LOOP;
    END LOOP;

    -- Update daily candles with sliding window SuperTrend
    PERFORM update_daily_weekly_supertrend(p_period, p_multiplier, p_symbol_filter);
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
-- MONTHLY SUPERTREND CALCULATION (MAIN FUNCTION)
-- =====================================================
-- Calculates SuperTrend on actual monthly candles, then updates daily candles via sliding window
CREATE OR REPLACE FUNCTION calculate_monthly_supertrend(
    p_period INTEGER DEFAULT 10,
    p_multiplier NUMERIC DEFAULT 2.0,
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
    v_direction_key TEXT;
    v_atr_key TEXT;
    symbol_rec RECORD;
    candle_rec RECORD;
    v_final_upper NUMERIC := NULL;
    v_final_lower NUMERIC := NULL;
    v_trend INTEGER := NULL;
BEGIN
    -- Generate indicator keys
    v_indicator_key := 'supertrend_' || p_period || '_' || format_decimal_param(p_multiplier);
    v_direction_key := v_indicator_key || '_direction';
    v_atr_key := 'monthly_atr_' || p_period;

    RAISE NOTICE 'Calculating monthly SuperTrend(%, %) with daily updates', p_period, p_multiplier;

    -- Process each symbol
    FOR symbol_rec IN
        SELECT DISTINCT symbol FROM monthly_candles
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        v_processed_symbols := v_processed_symbols + 1;
        v_final_upper := NULL;
        v_final_lower := NULL;
        v_trend := NULL;

        -- Ensure monthly ATR exists
        IF NOT EXISTS (
            SELECT 1 FROM monthly_candles
            WHERE symbol = symbol_rec.symbol
            AND indicators ? v_atr_key
            AND (indicators->v_atr_key) IS NOT NULL
            LIMIT 1
        ) THEN
            RAISE NOTICE 'Monthly ATR(%) not found for %, calculating ATR first', p_period, symbol_rec.symbol;
            PERFORM * FROM calculate_monthly_atr(p_period, symbol_rec.symbol);
        END IF;

        -- Calculate SuperTrend for monthly candles
        FOR candle_rec IN
            SELECT
                monthly_candle_key_id,
                month_sequence_number,
                high,
                low,
                close,
                (indicators->v_atr_key)::numeric as atr
            FROM monthly_candles
            WHERE symbol = symbol_rec.symbol
            AND indicators ? v_atr_key
            AND (indicators->v_atr_key) IS NOT NULL
            ORDER BY month_sequence_number
        LOOP
            DECLARE
                v_hl2 NUMERIC := (candle_rec.high + candle_rec.low) / 2.0;
                v_basic_upper NUMERIC := v_hl2 + (p_multiplier * candle_rec.atr);
                v_basic_lower NUMERIC := v_hl2 - (p_multiplier * candle_rec.atr);
                v_supertrend NUMERIC;
                v_direction INTEGER;
            BEGIN
                -- SuperTrend band persistence logic
                IF v_final_upper IS NULL THEN
                    v_final_upper := v_basic_upper;
                    v_final_lower := v_basic_lower;
                ELSE
                    IF v_trend IS NULL OR v_trend = 0 THEN
                        -- Downtrend: Upper band can only decrease or stay same
                        IF v_basic_upper < v_final_upper THEN
                            v_final_upper := v_basic_upper;
                        END IF;
                        v_final_lower := v_basic_lower;
                    ELSE
                        -- Uptrend: Lower band can only increase or stay same
                        IF v_basic_lower > v_final_lower THEN
                            v_final_lower := v_basic_lower;
                        END IF;
                        v_final_upper := v_basic_upper;
                    END IF;
                END IF;

                -- Trend determination
                IF v_trend IS NULL THEN
                    v_direction := CASE WHEN candle_rec.close <= v_final_upper THEN 0 ELSE 1 END;
                ELSE
                    IF v_trend = 1 THEN
                        IF candle_rec.close <= v_final_lower THEN
                            v_direction := 0;
                        ELSE
                            v_direction := 1;
                        END IF;
                    ELSE
                        IF candle_rec.close >= v_final_upper THEN
                            v_direction := 1;
                        ELSE
                            v_direction := 0;
                        END IF;
                    END IF;
                END IF;

                -- SuperTrend value
                IF v_direction = 1 THEN
                    v_supertrend := ROUND(v_final_lower, 2);
                ELSE
                    v_supertrend := ROUND(v_final_upper, 2);
                END IF;

                -- Store in monthly_candles
                UPDATE monthly_candles
                SET indicators = COALESCE(indicators, '{}')::jsonb ||
                    jsonb_build_object(
                        v_indicator_key, v_supertrend,
                        v_direction_key, v_direction
                    ),
                    updated_at = CURRENT_TIMESTAMP
                WHERE monthly_candle_key_id = candle_rec.monthly_candle_key_id;

                v_updated_monthly_rows := v_updated_monthly_rows + 1;
                v_trend := v_direction;
            END;
        END LOOP;
    END LOOP;

    -- Update daily candles with sliding window SuperTrend
    PERFORM update_daily_monthly_supertrend(p_period, p_multiplier, p_symbol_filter);
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
-- FIXED SLIDING WINDOW SUPERTREND UPDATE FUNCTIONS
-- =====================================================

-- Update daily candles with weekly SuperTrend sliding window (CORRECTED)
CREATE OR REPLACE FUNCTION update_daily_weekly_supertrend(
    p_period INTEGER DEFAULT 10,
    p_multiplier NUMERIC DEFAULT 2.0,
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
    v_direction_key TEXT;
    v_atr_key TEXT;
    symbol_rec RECORD;
    candle_rec RECORD;
    v_previous_weekly_supertrend NUMERIC;
    v_previous_weekly_direction INTEGER;
    v_final_upper NUMERIC;
    v_final_lower NUMERIC;
    v_current_supertrend NUMERIC;
    v_current_direction INTEGER;
BEGIN
    -- Generate indicator keys for daily storage
    v_indicator_key := 'weekly_supertrend_' || p_period || '_' || format_decimal_param(p_multiplier);
    v_direction_key := v_indicator_key || '_direction';
    v_atr_key := 'weekly_atr_' || p_period;

    RAISE NOTICE 'Updating daily candles with CORRECTED weekly SuperTrend(%, %) sliding window', p_period, p_multiplier;

    -- Process each symbol
    FOR symbol_rec IN
        SELECT DISTINCT symbol FROM daily_candles
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        v_processed_symbols := v_processed_symbols + 1;

        -- Update each daily candle with weekly SuperTrend
        FOR candle_rec IN
            SELECT
                dc.candle_key_id,
                dc.candle_sequence_number,
                dc.weekly_candle_key_id,
                dc.weekly_close as close,  -- Use weekly_close for trend determination
                dc.weekly_high,
                dc.weekly_low,
                wc.week_sequence_number,
                wc.indicators->v_atr_key as weekly_atr_value
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
                    jsonb_build_object(
                        v_indicator_key, NULL,
                        v_direction_key, NULL
                    ),
                    updated_at = CURRENT_TIMESTAMP
                WHERE candle_key_id = candle_rec.candle_key_id;
                v_updated_rows := v_updated_rows + 1;
                CONTINUE;
            END IF;

            -- Get previous week's SuperTrend values
            SELECT
                wc_prev.indicators->('supertrend_' || p_period || '_' || format_decimal_param(p_multiplier)),
                wc_prev.indicators->(('supertrend_' || p_period || '_' || format_decimal_param(p_multiplier)) || '_direction')
            INTO v_previous_weekly_supertrend, v_previous_weekly_direction
            FROM weekly_candles wc_prev
            WHERE wc_prev.symbol = symbol_rec.symbol
            AND wc_prev.week_sequence_number = candle_rec.week_sequence_number - 1;

            -- Skip if previous week's SuperTrend is not available
            IF v_previous_weekly_supertrend IS NULL THEN
                CONTINUE;
            END IF;

            -- Calculate sliding window SuperTrend using current week's partial data
            DECLARE
                v_hl2 NUMERIC := (candle_rec.weekly_high + candle_rec.weekly_low) / 2.0;
                v_basic_upper NUMERIC := v_hl2 + (p_multiplier * candle_rec.weekly_atr_value::NUMERIC);
                v_basic_lower NUMERIC := v_hl2 - (p_multiplier * candle_rec.weekly_atr_value::NUMERIC);
            BEGIN
                -- FIXED: Apply proper SuperTrend band persistence logic WITHOUT close price conditions
                IF v_previous_weekly_direction::INTEGER = 1 THEN
                    -- Previous was uptrend
                    -- Lower band can only increase or stay same
                    IF v_basic_lower > v_previous_weekly_supertrend THEN
                        v_final_lower := v_basic_lower;
                    ELSE
                        v_final_lower := v_previous_weekly_supertrend;
                    END IF;
                    -- Upper band resets to current basic upper
                    v_final_upper := v_basic_upper;
                ELSE
                    -- Previous was downtrend
                    -- Upper band can only decrease or stay same
                    IF v_basic_upper < v_previous_weekly_supertrend THEN
                        v_final_upper := v_basic_upper;
                    ELSE
                        v_final_upper := v_previous_weekly_supertrend;
                    END IF;
                    -- Lower band resets to current basic lower
                    v_final_lower := v_basic_lower;
                END IF;

                -- Determine current direction based on close vs bands
                IF v_previous_weekly_direction::INTEGER = 1 THEN
                    -- Previous was uptrend
                    IF candle_rec.close <= v_final_lower THEN
                        v_current_direction := 0; -- Switch to downtrend
                    ELSE
                        v_current_direction := 1; -- Continue uptrend
                    END IF;
                ELSE
                    -- Previous was downtrend
                    IF candle_rec.close >= v_final_upper THEN
                        v_current_direction := 1; -- Switch to uptrend
                    ELSE
                        v_current_direction := 0; -- Continue downtrend
                    END IF;
                END IF;

                -- Set SuperTrend value based on direction
                IF v_current_direction = 1 THEN
                    v_current_supertrend := ROUND(v_final_lower, 2); -- Uptrend: use lower band
                ELSE
                    v_current_supertrend := ROUND(v_final_upper, 2); -- Downtrend: use upper band
                END IF;

                -- Store in daily candles
                UPDATE daily_candles
                SET indicators = COALESCE(indicators, '{}')::jsonb ||
                    jsonb_build_object(
                        v_indicator_key, v_current_supertrend,
                        v_direction_key, v_current_direction
                    ),
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

-- Update daily candles with monthly SuperTrend sliding window (CORRECTED)
CREATE OR REPLACE FUNCTION update_daily_monthly_supertrend(
    p_period INTEGER DEFAULT 10,
    p_multiplier NUMERIC DEFAULT 2.0,
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
    v_direction_key TEXT;
    v_atr_key TEXT;
    symbol_rec RECORD;
    candle_rec RECORD;
    v_previous_monthly_supertrend NUMERIC;
    v_previous_monthly_direction INTEGER;
    v_final_upper NUMERIC;
    v_final_lower NUMERIC;
    v_current_supertrend NUMERIC;
    v_current_direction INTEGER;
BEGIN
    -- Generate indicator keys for daily storage
    v_indicator_key := 'monthly_supertrend_' || p_period || '_' || format_decimal_param(p_multiplier);
    v_direction_key := v_indicator_key || '_direction';
    v_atr_key := 'monthly_atr_' || p_period;

    RAISE NOTICE 'Updating daily candles with CORRECTED monthly SuperTrend(%, %) sliding window', p_period, p_multiplier;

    -- Process each symbol
    FOR symbol_rec IN
        SELECT DISTINCT symbol FROM daily_candles
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        v_processed_symbols := v_processed_symbols + 1;

        -- Update each daily candle with monthly SuperTrend
        FOR candle_rec IN
            SELECT
                dc.candle_key_id,
                dc.candle_sequence_number,
                dc.monthly_candle_key_id,
                dc.monthly_close as close,  -- Use monthly_close for trend determination
                dc.monthly_high,
                dc.monthly_low,
                mc.month_sequence_number,
                mc.indicators->v_atr_key as monthly_atr_value
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
                    jsonb_build_object(
                        v_indicator_key, NULL,
                        v_direction_key, NULL
                    ),
                    updated_at = CURRENT_TIMESTAMP
                WHERE candle_key_id = candle_rec.candle_key_id;
                v_updated_rows := v_updated_rows + 1;
                CONTINUE;
            END IF;

            -- Get previous month's SuperTrend values
            SELECT
                mc_prev.indicators->('supertrend_' || p_period || '_' || format_decimal_param(p_multiplier)),
                mc_prev.indicators->(('supertrend_' || p_period || '_' || format_decimal_param(p_multiplier)) || '_direction')
            INTO v_previous_monthly_supertrend, v_previous_monthly_direction
            FROM monthly_candles mc_prev
            WHERE mc_prev.symbol = symbol_rec.symbol
            AND mc_prev.month_sequence_number = candle_rec.month_sequence_number - 1;

            -- Skip if previous month's SuperTrend is not available
            IF v_previous_monthly_supertrend IS NULL THEN
                CONTINUE;
            END IF;

            -- Calculate sliding window SuperTrend using current month's partial data
            DECLARE
                v_hl2 NUMERIC := (candle_rec.monthly_high + candle_rec.monthly_low) / 2.0;
                v_basic_upper NUMERIC := v_hl2 + (p_multiplier * candle_rec.monthly_atr_value::NUMERIC);
                v_basic_lower NUMERIC := v_hl2 - (p_multiplier * candle_rec.monthly_atr_value::NUMERIC);
            BEGIN
                -- FIXED: Apply proper SuperTrend band persistence logic WITHOUT close price conditions
                IF v_previous_monthly_direction::INTEGER = 1 THEN
                    -- Previous was uptrend
                    -- Lower band can only increase or stay same
                    IF v_basic_lower > v_previous_monthly_supertrend THEN
                        v_final_lower := v_basic_lower;
                    ELSE
                        v_final_lower := v_previous_monthly_supertrend;
                    END IF;
                    -- Upper band resets to current basic upper
                    v_final_upper := v_basic_upper;
                ELSE
                    -- Previous was downtrend
                    -- Upper band can only decrease or stay same
                    IF v_basic_upper < v_previous_monthly_supertrend THEN
                        v_final_upper := v_basic_upper;
                    ELSE
                        v_final_upper := v_previous_monthly_supertrend;
                    END IF;
                    -- Lower band resets to current basic lower
                    v_final_lower := v_basic_lower;
                END IF;

                -- Determine current direction based on close vs bands
                IF v_previous_monthly_direction::INTEGER = 1 THEN
                    -- Previous was uptrend
                    IF candle_rec.close <= v_final_lower THEN
                        v_current_direction := 0; -- Switch to downtrend
                    ELSE
                        v_current_direction := 1; -- Continue uptrend
                    END IF;
                ELSE
                    -- Previous was downtrend
                    IF candle_rec.close >= v_final_upper THEN
                        v_current_direction := 1; -- Switch to uptrend
                    ELSE
                        v_current_direction := 0; -- Continue downtrend
                    END IF;
                END IF;

                -- Set SuperTrend value based on direction
                IF v_current_direction = 1 THEN
                    v_current_supertrend := ROUND(v_final_lower, 2); -- Uptrend: use lower band
                ELSE
                    v_current_supertrend := ROUND(v_final_upper, 2); -- Downtrend: use upper band
                END IF;

                -- Store in daily candles
                UPDATE daily_candles
                SET indicators = COALESCE(indicators, '{}')::jsonb ||
                    jsonb_build_object(
                        v_indicator_key, v_current_supertrend,
                        v_direction_key, v_current_direction
                    ),
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
GRANT EXECUTE ON FUNCTION format_decimal_param(NUMERIC) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_daily_supertrend_for_symbol(TEXT, INTEGER, NUMERIC, BOOLEAN) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_weekly_supertrend(INTEGER, NUMERIC, TEXT) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_monthly_supertrend(INTEGER, NUMERIC, TEXT) TO PUBLIC;
GRANT EXECUTE ON FUNCTION update_daily_weekly_supertrend(INTEGER, NUMERIC, TEXT) TO PUBLIC;
GRANT EXECUTE ON FUNCTION update_daily_monthly_supertrend(INTEGER, NUMERIC, TEXT) TO PUBLIC;