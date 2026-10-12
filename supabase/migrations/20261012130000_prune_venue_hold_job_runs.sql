-- CR-99: keep the expiry job's run log bounded. pg_cron records every run of
-- `expire-venue-holds` in cron.job_run_details, about 1,440 rows a day. A
-- daily job deletes that job's entries older than 7 days, at 03:00 Singapore
-- time (19:00 UTC), and leaves other jobs' logs alone.
-- cron.schedule replaces a job of the same name, so this can be re-run.

select cron.schedule(
    'prune-venue-hold-job-runs',
    '0 19 * * *',
    $$delete from cron.job_run_details
       where jobid = (select jobid from cron.job where jobname = 'expire-venue-holds')
         and end_time < now() - interval '7 days'$$
);
