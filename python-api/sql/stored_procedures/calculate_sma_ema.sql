-- =====================================================
-- SMA AND EMA INDICATOR CALCULATION STORED PROCEDURES
-- =====================================================
-- Calculates Simple Moving Average (SMA) and Exponential Moving Average (EMA)
-- For all timeframes: daily, weekly, monthly
-- Stores values with 2 decimal precision
-- =====================================================

-- =====================================================
-- DAILY SMA CALCULATION FOR SINGLE SYMBOL
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_daily_sma_for_symbol(
    p_symbol TEXT,
    p_period INTEGER,
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
    v_end_time TIMESTAMP;
    v_updated_rows INTEGER := 0;
    v_indicator_key TEXT;
    v_existing_count INTEGER;
    v_total_count INTEGER;
BEGIN
    -- Generate indicator key
    v_indicator_key := 'sma_' || p_period;
    
    RAISE NOTICE 'Processing SMA(%) for symbol: %', p_period, p_symbol;
    
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
    
    -- Calculate SMA using window function
    WITH sma_calc AS (
        SELECT 
            candle_key_id,
            candle_sequence_number,
            -- Calculate SMA using AVG over window
            ROUND(AVG(close) OVER (
                ORDER BY candle_sequence_number 
                ROWS BETWEEN (p_period - 1) PRECEDING AND CURRENT ROW
            )::numeric, 2) as sma_value,
            -- Check if we have enough data points
            COUNT(*) OVER (
                ORDER BY candle_sequence_number 
                ROWS BETWEEN (p_period - 1) PRECEDING AND CURRENT ROW
            ) as data_points
        FROM daily_candles
        WHERE symbol = p_symbol
        ORDER BY candle_sequence_number
    )
    -- Update the indicators JSONB column
    UPDATE daily_candles dc
    SET indicators = COALESCE(dc.indicators, '{}')::jsonb || 
        jsonb_build_object(v_indicator_key, sc.sma_value),
        updated_at = CURRENT_TIMESTAMP
    FROM sma_calc sc
    WHERE dc.candle_key_id = sc.candle_key_id
    AND sc.data_points = p_period  -- Only update when we have full period data
    AND sc.sma_value IS NOT NULL
    AND (
        -- Only update if indicator doesn't exist or force recalculate
        p_force_recalculate OR
        NOT (dc.indicators ? v_indicator_key) OR 
        (dc.indicators->v_indicator_key) IS NULL
    );
    
    GET DIAGNOSTICS v_updated_rows = ROW_COUNT;
    
    v_end_time := clock_timestamp();
    
    RAISE NOTICE 'Completed SMA(%) calculation for %: % rows updated in % ms',
        p_period, p_symbol, v_updated_rows, EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER;
    
    RETURN QUERY SELECT 
        v_updated_rows,
        EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER,
        'SUCCESS'::TEXT,
        v_indicator_key;
        
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Error in calculate_daily_sma_for_symbol: %', SQLERRM;
        RETURN QUERY SELECT 
            0,
            EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
            ('ERROR: ' || SQLERRM)::TEXT,
            v_indicator_key;
END;
$$;

-- =====================================================
-- DAILY EMA CALCULATION FOR SINGLE SYMBOL
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_daily_ema_for_symbol(
    p_symbol TEXT,
    p_period INTEGER,
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
    v_end_time TIMESTAMP;
    v_updated_rows INTEGER := 0;
    v_indicator_key TEXT;
    v_existing_count INTEGER;
    v_total_count INTEGER;
    v_alpha NUMERIC;
BEGIN
    -- Generate indicator key
    v_indicator_key := 'ema_' || p_period;
    
    -- Calculate smoothing factor (alpha)
    v_alpha := 2.0 / (p_period + 1);
    
    RAISE NOTICE 'Processing EMA(%) for symbol: %', p_period, p_symbol;
    
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
    
    -- Calculate EMA using recursive CTE
    WITH RECURSIVE ordered_candles AS (
        SELECT 
            candle_key_id,
            candle_sequence_number,
            close,
            ROW_NUMBER() OVER (ORDER BY candle_sequence_number) as rn
        FROM daily_candles
        WHERE symbol = p_symbol
        ORDER BY candle_sequence_number
    ),
    -- First calculate SMA for the initial EMA value
    initial_sma AS (
        SELECT 
            AVG(close) as sma_value
        FROM ordered_candles
        WHERE rn <= p_period
    ),
    -- Recursive EMA calculation
    ema_calc AS (
        -- Base case: use SMA for the first EMA value
        SELECT 
            oc.candle_key_id,
            oc.candle_sequence_number,
            oc.close,
            oc.rn,
            CASE 
                WHEN oc.rn < p_period THEN NULL
                WHEN oc.rn = p_period THEN ROUND(isma.sma_value::numeric, 2)
                ELSE NULL
            END as ema_value
        FROM ordered_candles oc
        CROSS JOIN initial_sma isma
        WHERE oc.rn = p_period
        
        UNION ALL
        
        -- Recursive case: calculate EMA based on previous EMA
        SELECT 
            oc.candle_key_id,
            oc.candle_sequence_number,
            oc.close,
            oc.rn,
            ROUND((oc.close * v_alpha + ec.ema_value * (1 - v_alpha))::numeric, 2) as ema_value
        FROM ordered_candles oc
        INNER JOIN ema_calc ec ON oc.rn = ec.rn + 1
        WHERE oc.rn > p_period
    )
    -- Update the indicators JSONB column
    UPDATE daily_candles dc
    SET indicators = COALESCE(dc.indicators, '{}')::jsonb || 
        jsonb_build_object(v_indicator_key, ec.ema_value),
        updated_at = CURRENT_TIMESTAMP
    FROM ema_calc ec
    WHERE dc.candle_key_id = ec.candle_key_id
    AND ec.ema_value IS NOT NULL
    AND (
        -- Only update if indicator doesn't exist or force recalculate
        p_force_recalculate OR
        NOT (dc.indicators ? v_indicator_key) OR 
        (dc.indicators->v_indicator_key) IS NULL
    );
    
    GET DIAGNOSTICS v_updated_rows = ROW_COUNT;
    
    v_end_time := clock_timestamp();
    
    RAISE NOTICE 'Completed EMA(%) calculation for %: % rows updated in % ms',
        p_period, p_symbol, v_updated_rows, EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER;
    
    RETURN QUERY SELECT 
        v_updated_rows,
        EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER,
        'SUCCESS'::TEXT,
        v_indicator_key;
        
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Error in calculate_daily_ema_for_symbol: %', SQLERRM;
        RETURN QUERY SELECT 
            0,
            EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
            ('ERROR: ' || SQLERRM)::TEXT,
            v_indicator_key;
END;
$$;

-- =====================================================
-- WEEKLY SMA AND EMA CALCULATION
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_weekly_sma_ema(
    p_indicator_type TEXT,  -- 'sma' or 'ema'
    p_period INTEGER,
    p_symbol_filter TEXT DEFAULT NULL,
    p_force_recalculate BOOLEAN DEFAULT FALSE
)
RETURNS TABLE(
    processed_symbols INTEGER,
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT,
    indicator_key TEXT
) 
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_total_updated_rows INTEGER := 0;
    v_processed_symbols INTEGER := 0;
    v_indicator_key TEXT;
    v_alpha NUMERIC;
    v_symbol_updated_rows INTEGER;
    symbol_rec RECORD;
BEGIN
    -- Set indicator key with timeframe prefix
    v_indicator_key := 'weekly_' || p_indicator_type || '_' || p_period;
    
    -- Calculate smoothing factor for EMA
    IF p_indicator_type = 'ema' THEN
        v_alpha := 2.0 / (p_period + 1);
    END IF;
    
    RAISE NOTICE 'Calculating weekly %(%) for symbols', p_indicator_type, p_period;
    
    -- Process each symbol
    FOR symbol_rec IN 
        SELECT DISTINCT symbol FROM daily_candles 
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        v_processed_symbols := v_processed_symbols + 1;
        
        IF p_indicator_type = 'sma' THEN
            -- Weekly SMA calculation
            WITH weekly_data AS (
                -- Get unique weekly data (latest daily candle per week)
                SELECT DISTINCT ON (dc.weekly_candle_key_id)
                    dc.candle_key_id,
                    dc.weekly_candle_key_id,
                    wc.week_sequence_number,
                    dc.weekly_close as close
                FROM daily_candles dc
                LEFT JOIN weekly_candles wc ON wc.weekly_candle_key_id = dc.weekly_candle_key_id
                WHERE dc.symbol = symbol_rec.symbol
                AND dc.weekly_close IS NOT NULL
                AND wc.week_sequence_number IS NOT NULL
                ORDER BY dc.weekly_candle_key_id, dc.candle_sequence_number DESC
            ),
            weekly_sma AS (
                SELECT 
                    weekly_candle_key_id,
                    ROUND(AVG(close) OVER (
                        ORDER BY week_sequence_number 
                        ROWS BETWEEN (p_period - 1) PRECEDING AND CURRENT ROW
                    )::numeric, 2) as sma_value,
                    COUNT(*) OVER (
                        ORDER BY week_sequence_number 
                        ROWS BETWEEN (p_period - 1) PRECEDING AND CURRENT ROW
                    ) as data_points
                FROM weekly_data
            )
            -- Update all daily candles in the same week
            UPDATE daily_candles AS target
            SET indicators = COALESCE(target.indicators, '{}'::jsonb) || 
                jsonb_build_object(v_indicator_key, ws.sma_value),
                updated_at = CURRENT_TIMESTAMP
            FROM weekly_sma ws
            WHERE target.symbol = symbol_rec.symbol
            AND target.weekly_candle_key_id = ws.weekly_candle_key_id
            AND ws.data_points = p_period
            AND ws.sma_value IS NOT NULL
            AND (
                p_force_recalculate OR
                NOT (target.indicators ? v_indicator_key) OR 
                (target.indicators->v_indicator_key) IS NULL
            );
            
            GET DIAGNOSTICS v_symbol_updated_rows = ROW_COUNT;
            v_total_updated_rows := v_total_updated_rows + v_symbol_updated_rows;
            
        ELSIF p_indicator_type = 'ema' THEN
            -- Weekly EMA calculation
            WITH RECURSIVE weekly_data AS (
                -- Get unique weekly data (latest daily candle per week)
                SELECT DISTINCT ON (dc.weekly_candle_key_id)
                    dc.candle_key_id,
                    dc.weekly_candle_key_id,
                    wc.week_sequence_number,
                    dc.weekly_close as close,
                    ROW_NUMBER() OVER (ORDER BY wc.week_sequence_number) as rn
                FROM daily_candles dc
                LEFT JOIN weekly_candles wc ON wc.weekly_candle_key_id = dc.weekly_candle_key_id
                WHERE dc.symbol = symbol_rec.symbol
                AND dc.weekly_close IS NOT NULL
                AND wc.week_sequence_number IS NOT NULL
                ORDER BY dc.weekly_candle_key_id, dc.candle_sequence_number DESC
            ),
            -- Initial SMA for first EMA
            initial_sma AS (
                SELECT AVG(close) as sma_value
                FROM weekly_data
                WHERE rn <= p_period
            ),
            -- Recursive EMA calculation
            weekly_ema AS (
                -- Base case
                SELECT 
                    wd.weekly_candle_key_id,
                    wd.week_sequence_number,
                    wd.close,
                    wd.rn,
                    CASE 
                        WHEN wd.rn < p_period THEN NULL
                        WHEN wd.rn = p_period THEN ROUND(isma.sma_value::numeric, 2)
                        ELSE NULL
                    END as ema_value
                FROM weekly_data wd
                CROSS JOIN initial_sma isma
                WHERE wd.rn = p_period
                
                UNION ALL
                
                -- Recursive case
                SELECT 
                    wd.weekly_candle_key_id,
                    wd.week_sequence_number,
                    wd.close,
                    wd.rn,
                    ROUND((wd.close * v_alpha + we.ema_value * (1 - v_alpha))::numeric, 2) as ema_value
                FROM weekly_data wd
                INNER JOIN weekly_ema we ON wd.rn = we.rn + 1
                WHERE wd.rn > p_period
            )
            -- Update all daily candles in the same week
            UPDATE daily_candles AS target
            SET indicators = COALESCE(target.indicators, '{}'::jsonb) || 
                jsonb_build_object(v_indicator_key, we.ema_value),
                updated_at = CURRENT_TIMESTAMP
            FROM weekly_ema we
            WHERE target.symbol = symbol_rec.symbol
            AND target.weekly_candle_key_id = we.weekly_candle_key_id
            AND we.ema_value IS NOT NULL
            AND (
                p_force_recalculate OR
                NOT (target.indicators ? v_indicator_key) OR 
                (target.indicators->v_indicator_key) IS NULL
            );
            
            GET DIAGNOSTICS v_symbol_updated_rows = ROW_COUNT;
            v_total_updated_rows := v_total_updated_rows + v_symbol_updated_rows;
        END IF;
    END LOOP;
    
    RAISE NOTICE 'Completed weekly %(%) calculation: % symbols, % rows updated',
        p_indicator_type, p_period, v_processed_symbols, v_total_updated_rows;
    
    RETURN QUERY SELECT 
        v_processed_symbols,
        v_total_updated_rows,
        EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
        'SUCCESS'::TEXT,
        v_indicator_key;
        
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Error in calculate_weekly_sma_ema: %', SQLERRM;
        RETURN QUERY SELECT 
            v_processed_symbols,
            v_total_updated_rows,
            EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
            ('ERROR: ' || SQLERRM)::TEXT,
            v_indicator_key;
END;
$$;

-- =====================================================
-- MONTHLY SMA AND EMA CALCULATION
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_monthly_sma_ema(
    p_indicator_type TEXT,  -- 'sma' or 'ema'
    p_period INTEGER,
    p_symbol_filter TEXT DEFAULT NULL,
    p_force_recalculate BOOLEAN DEFAULT FALSE
)
RETURNS TABLE(
    processed_symbols INTEGER,
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT,
    indicator_key TEXT
) 
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_total_updated_rows INTEGER := 0;
    v_processed_symbols INTEGER := 0;
    v_indicator_key TEXT;
    v_alpha NUMERIC;
    v_symbol_updated_rows INTEGER;
    symbol_rec RECORD;
BEGIN
    -- Set indicator key with timeframe prefix
    v_indicator_key := 'monthly_' || p_indicator_type || '_' || p_period;
    
    -- Calculate smoothing factor for EMA
    IF p_indicator_type = 'ema' THEN
        v_alpha := 2.0 / (p_period + 1);
    END IF;
    
    RAISE NOTICE 'Calculating monthly %(%) for symbols', p_indicator_type, p_period;
    
    -- Process each symbol
    FOR symbol_rec IN 
        SELECT DISTINCT symbol FROM daily_candles 
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        v_processed_symbols := v_processed_symbols + 1;
        
        IF p_indicator_type = 'sma' THEN
            -- Monthly SMA calculation
            WITH monthly_data AS (
                -- Get unique monthly data (latest daily candle per month)
                SELECT DISTINCT ON (dc.monthly_candle_key_id)
                    dc.candle_key_id,
                    dc.monthly_candle_key_id,
                    mc.month_sequence_number,
                    dc.monthly_close as close
                FROM daily_candles dc
                LEFT JOIN monthly_candles mc ON mc.monthly_candle_key_id = dc.monthly_candle_key_id
                WHERE dc.symbol = symbol_rec.symbol
                AND dc.monthly_close IS NOT NULL
                AND mc.month_sequence_number IS NOT NULL
                ORDER BY dc.monthly_candle_key_id, dc.candle_sequence_number DESC
            ),
            monthly_sma AS (
                SELECT 
                    monthly_candle_key_id,
                    ROUND(AVG(close) OVER (
                        ORDER BY month_sequence_number 
                        ROWS BETWEEN (p_period - 1) PRECEDING AND CURRENT ROW
                    )::numeric, 2) as sma_value,
                    COUNT(*) OVER (
                        ORDER BY month_sequence_number 
                        ROWS BETWEEN (p_period - 1) PRECEDING AND CURRENT ROW
                    ) as data_points
                FROM monthly_data
            )
            -- Update all daily candles in the same month
            UPDATE daily_candles AS target
            SET indicators = COALESCE(target.indicators, '{}'::jsonb) || 
                jsonb_build_object(v_indicator_key, ms.sma_value),
                updated_at = CURRENT_TIMESTAMP
            FROM monthly_sma ms
            WHERE target.symbol = symbol_rec.symbol
            AND target.monthly_candle_key_id = ms.monthly_candle_key_id
            AND ms.data_points = p_period
            AND ms.sma_value IS NOT NULL
            AND (
                p_force_recalculate OR
                NOT (target.indicators ? v_indicator_key) OR 
                (target.indicators->v_indicator_key) IS NULL
            );
            
            GET DIAGNOSTICS v_symbol_updated_rows = ROW_COUNT;
            v_total_updated_rows := v_total_updated_rows + v_symbol_updated_rows;
            
        ELSIF p_indicator_type = 'ema' THEN
            -- Monthly EMA calculation
            WITH RECURSIVE monthly_data AS (
                -- Get unique monthly data (latest daily candle per month)
                SELECT DISTINCT ON (dc.monthly_candle_key_id)
                    dc.candle_key_id,
                    dc.monthly_candle_key_id,
                    mc.month_sequence_number,
                    dc.monthly_close as close,
                    ROW_NUMBER() OVER (ORDER BY mc.month_sequence_number) as rn
                FROM daily_candles dc
                LEFT JOIN monthly_candles mc ON mc.monthly_candle_key_id = dc.monthly_candle_key_id
                WHERE dc.symbol = symbol_rec.symbol
                AND dc.monthly_close IS NOT NULL
                AND mc.month_sequence_number IS NOT NULL
                ORDER BY dc.monthly_candle_key_id, dc.candle_sequence_number DESC
            ),
            -- Initial SMA for first EMA
            initial_sma AS (
                SELECT AVG(close) as sma_value
                FROM monthly_data
                WHERE rn <= p_period
            ),
            -- Recursive EMA calculation
            monthly_ema AS (
                -- Base case
                SELECT 
                    md.monthly_candle_key_id,
                    md.month_sequence_number,
                    md.close,
                    md.rn,
                    CASE 
                        WHEN md.rn < p_period THEN NULL
                        WHEN md.rn = p_period THEN ROUND(isma.sma_value::numeric, 2)
                        ELSE NULL
                    END as ema_value
                FROM monthly_data md
                CROSS JOIN initial_sma isma
                WHERE md.rn = p_period
                
                UNION ALL
                
                -- Recursive case
                SELECT 
                    md.monthly_candle_key_id,
                    md.month_sequence_number,
                    md.close,
                    md.rn,
                    ROUND((md.close * v_alpha + me.ema_value * (1 - v_alpha))::numeric, 2) as ema_value
                FROM monthly_data md
                INNER JOIN monthly_ema me ON md.rn = me.rn + 1
                WHERE md.rn > p_period
            )
            -- Update all daily candles in the same month
            UPDATE daily_candles AS target
            SET indicators = COALESCE(target.indicators, '{}'::jsonb) || 
                jsonb_build_object(v_indicator_key, me.ema_value),
                updated_at = CURRENT_TIMESTAMP
            FROM monthly_ema me
            WHERE target.symbol = symbol_rec.symbol
            AND target.monthly_candle_key_id = me.monthly_candle_key_id
            AND me.ema_value IS NOT NULL
            AND (
                p_force_recalculate OR
                NOT (target.indicators ? v_indicator_key) OR 
                (target.indicators->v_indicator_key) IS NULL
            );
            
            GET DIAGNOSTICS v_symbol_updated_rows = ROW_COUNT;
            v_total_updated_rows := v_total_updated_rows + v_symbol_updated_rows;
        END IF;
    END LOOP;
    
    RAISE NOTICE 'Completed monthly %(%) calculation: % symbols, % rows updated',
        p_indicator_type, p_period, v_processed_symbols, v_total_updated_rows;
    
    RETURN QUERY SELECT 
        v_processed_symbols,
        v_total_updated_rows,
        EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
        'SUCCESS'::TEXT,
        v_indicator_key;
        
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Error in calculate_monthly_sma_ema: %', SQLERRM;
        RETURN QUERY SELECT 
            v_processed_symbols,
            v_total_updated_rows,
            EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
            ('ERROR: ' || SQLERRM)::TEXT,
            v_indicator_key;
END;
$$;

-- =====================================================
-- BATCH CALCULATION FOR ALL SYMBOLS
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_sma_ema_for_all_symbols(
    p_indicator_type TEXT,  -- 'sma' or 'ema'
    p_period INTEGER,
    p_timeframe TEXT DEFAULT 'daily',  -- 'daily', 'weekly', 'monthly'
    p_force_recalculate BOOLEAN DEFAULT FALSE
)
RETURNS TABLE(
    total_symbols INTEGER,
    successful_symbols INTEGER,
    failed_symbols INTEGER,
    total_execution_time_ms INTEGER,
    indicator_key TEXT,
    status TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_symbol_record RECORD;
    v_result RECORD;
    v_success_count INTEGER := 0;
    v_fail_count INTEGER := 0;
    v_total_count INTEGER := 0;
    v_indicator_key TEXT;
BEGIN
    -- Generate indicator key based on timeframe
    IF p_timeframe = 'daily' THEN
        v_indicator_key := p_indicator_type || '_' || p_period;
    ELSE
        v_indicator_key := p_timeframe || '_' || p_indicator_type || '_' || p_period;
    END IF;
    
    RAISE NOTICE 'Starting batch % %(%) calculation for timeframe: %', 
        p_timeframe, p_indicator_type, p_period, p_timeframe;
    
    IF p_timeframe = 'daily' THEN
        -- Process each symbol for daily
        FOR v_symbol_record IN 
            SELECT DISTINCT symbol 
            FROM daily_candles 
            ORDER BY symbol
        LOOP
            v_total_count := v_total_count + 1;
            
            -- Calculate indicator for this symbol
            IF p_indicator_type = 'sma' THEN
                SELECT * INTO v_result 
                FROM calculate_daily_sma_for_symbol(v_symbol_record.symbol, p_period, p_force_recalculate);
            ELSE
                SELECT * INTO v_result 
                FROM calculate_daily_ema_for_symbol(v_symbol_record.symbol, p_period, p_force_recalculate);
            END IF;
            
            IF v_result.status = 'SUCCESS' AND v_result.updated_rows > 0 THEN
                v_success_count := v_success_count + 1;
            ELSIF v_result.status LIKE 'ERROR%' THEN
                v_fail_count := v_fail_count + 1;
                RAISE NOTICE 'Failed for symbol %: %', v_symbol_record.symbol, v_result.status;
            END IF;
            
            -- Log progress every 100 symbols
            IF v_total_count % 100 = 0 THEN
                RAISE NOTICE 'Progress: % symbols processed (% success, % failed)', 
                    v_total_count, v_success_count, v_fail_count;
            END IF;
        END LOOP;
        
    ELSIF p_timeframe = 'weekly' THEN
        -- Calculate weekly for all symbols at once
        SELECT * INTO v_result
        FROM calculate_weekly_sma_ema(p_indicator_type, p_period, NULL, p_force_recalculate);
        
        v_total_count := v_result.processed_symbols;
        IF v_result.status = 'SUCCESS' THEN
            v_success_count := v_result.processed_symbols;
        ELSE
            v_fail_count := v_result.processed_symbols;
        END IF;
        
    ELSIF p_timeframe = 'monthly' THEN
        -- Calculate monthly for all symbols at once
        SELECT * INTO v_result
        FROM calculate_monthly_sma_ema(p_indicator_type, p_period, NULL, p_force_recalculate);
        
        v_total_count := v_result.processed_symbols;
        IF v_result.status = 'SUCCESS' THEN
            v_success_count := v_result.processed_symbols;
        ELSE
            v_fail_count := v_result.processed_symbols;
        END IF;
    END IF;
    
    RAISE NOTICE 'Batch % %(%) calculation complete:', p_timeframe, p_indicator_type, p_period;
    RAISE NOTICE '  Total symbols: %', v_total_count;
    RAISE NOTICE '  Successful: %', v_success_count;
    RAISE NOTICE '  Failed: %', v_fail_count;
    RAISE NOTICE '  Execution time: % ms', EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER;
    
    RETURN QUERY SELECT 
        v_total_count,
        v_success_count,
        v_fail_count,
        EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
        v_indicator_key,
        CASE 
            WHEN v_fail_count = 0 AND v_success_count > 0 THEN 'SUCCESS'::TEXT
            WHEN v_success_count > 0 THEN 'PARTIAL_SUCCESS'::TEXT
            ELSE 'FAILED'::TEXT
        END;
END;
$$;

-- =====================================================
-- DYNAMIC INDICATOR HANDLER (Called from Python)
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_dynamic_sma_ema(
    p_indicator_name TEXT  -- e.g., 'sma_20', 'weekly_ema_50', 'monthly_sma_10'
)
RETURNS TABLE(
    success BOOLEAN,
    message TEXT,
    indicator_key TEXT,
    symbols_processed INTEGER,
    symbols_updated INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_parts TEXT[];
    v_timeframe TEXT;
    v_indicator_type TEXT;
    v_period INTEGER;
    v_result RECORD;
BEGIN
    -- Parse the indicator name
    v_parts := string_to_array(p_indicator_name, '_');
    
    -- Check format: could be 'sma_20' or 'weekly_sma_20'
    IF array_length(v_parts, 1) = 2 THEN
        -- Daily indicator (e.g., 'sma_20', 'ema_50')
        v_timeframe := 'daily';
        v_indicator_type := v_parts[1];
        v_period := v_parts[2]::INTEGER;
    ELSIF array_length(v_parts, 1) = 3 THEN
        -- Weekly/Monthly indicator (e.g., 'weekly_sma_20', 'monthly_ema_50')
        v_timeframe := v_parts[1];
        v_indicator_type := v_parts[2];
        v_period := v_parts[3]::INTEGER;
    ELSE
        RETURN QUERY SELECT 
            FALSE,
            'Invalid indicator name format. Expected: [timeframe_]type_period',
            NULL::TEXT,
            0,
            0;
        RETURN;
    END IF;
    
    -- Validate indicator type
    IF v_indicator_type NOT IN ('sma', 'ema') THEN
        RETURN QUERY SELECT 
            FALSE,
            'Invalid indicator type. Must be sma or ema',
            NULL::TEXT,
            0,
            0;
        RETURN;
    END IF;
    
    -- Validate timeframe
    IF v_timeframe NOT IN ('daily', 'weekly', 'monthly') THEN
        RETURN QUERY SELECT 
            FALSE,
            'Invalid timeframe. Must be daily, weekly, or monthly',
            NULL::TEXT,
            0,
            0;
        RETURN;
    END IF;
    
    RAISE NOTICE 'Parsed % request: timeframe=%, type=%, period=%', 
        p_indicator_name, v_timeframe, v_indicator_type, v_period;
    
    -- Calculate indicator for all symbols
    SELECT * INTO v_result 
    FROM calculate_sma_ema_for_all_symbols(v_indicator_type, v_period, v_timeframe, FALSE);
    
    -- Return results
    RETURN QUERY SELECT 
        (v_result.status IN ('SUCCESS', 'PARTIAL_SUCCESS'))::BOOLEAN as success,
        format('Processed %s symbols: %s successful, %s failed', 
            v_result.total_symbols, 
            v_result.successful_symbols,
            v_result.failed_symbols) as message,
        v_result.indicator_key,
        v_result.total_symbols as symbols_processed,
        v_result.successful_symbols as symbols_updated;
END;
$$;

-- =====================================================
-- GRANT PERMISSIONS
-- =====================================================
GRANT EXECUTE ON FUNCTION calculate_daily_sma_for_symbol(TEXT, INTEGER, BOOLEAN) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_daily_ema_for_symbol(TEXT, INTEGER, BOOLEAN) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_weekly_sma_ema(TEXT, INTEGER, TEXT, BOOLEAN) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_monthly_sma_ema(TEXT, INTEGER, TEXT, BOOLEAN) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_sma_ema_for_all_symbols(TEXT, INTEGER, TEXT, BOOLEAN) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_dynamic_sma_ema(TEXT) TO PUBLIC;