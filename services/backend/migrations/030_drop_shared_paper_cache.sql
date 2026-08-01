-- 030_drop_shared_paper_cache.sql
-- Removes the global shared paper cache. Analysis must be scoped to the
-- active draft/project run and must not reuse cross-user cached paper analyses.

DO $$
DECLARE
    fn record;
BEGIN
    FOR fn IN
        SELECT oid::regprocedure AS signature
        FROM pg_proc
        WHERE pronamespace = 'public'::regnamespace
          AND proname = 'match_shared_papers'
    LOOP
        EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', fn.signature);
    END LOOP;
END $$;

DROP TABLE IF EXISTS public.shared_papers CASCADE;
