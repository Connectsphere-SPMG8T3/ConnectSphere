-- CR-103/104/108: run ONLY after the safety migrations (through 20261103120000) are applied, as postgres.
-- psql --set ON_ERROR_STOP=1 -f supabase/verification/safety_decision_checks.sql
-- All fixtures are new, randomly identified records; no shared fixtures change.
-- Live booking inserts invoke populate_booking_space_request automatically.
begin;

-- Read-only preflight doubles as the pre-migration RED check.
do $$
begin
    if to_regclass('public.event_safety_decisions') is null
       or to_regclass('public.event_safety_checklist_items') is null
       or to_regprocedure('public.safety_approve_event(uuid,uuid,integer,jsonb,text,text,text,text)') is null
       or to_regprocedure('public.safety_return_event(uuid,uuid,integer,text,jsonb,text,text,uuid[],uuid[],text)') is null
       or to_regprocedure('private.safety_checklist_problem(uuid,jsonb,text)') is null
       or to_regprocedure('public.return_event_to_planning(uuid,integer,text,text,text,text)') is null
       or to_regprocedure('public.mark_safety_revision(uuid,uuid,text)') is null
       or not exists (select 1 from pg_enum e join pg_type t on t.oid=e.enumtypid
                      where t.typnamespace='public'::regnamespace and t.typname='venue_booking_flag' and e.enumlabel='safety_rejected') then
        raise exception 'SAFETY FAIL: Task 1 table/RPC interfaces are missing';
    end if;
end $$;

create temporary table safety_fixture (key text primary key, id uuid not null) on commit drop;
insert into safety_fixture select key, gen_random_uuid() from unnest(array[
    'organiser','coordinator','officer','other_coordinator','staff','equipment',
    'replace_event','booking_replace_old','booking_replace_new','replace_venue_new','booking_plain',
    'approve','held','empty','stale','changes','reject','invalid','cl_event','booking_cl_a','booking_cl_b','withdraw_review','withdraw_confirmed','withdraw_preparation',
    'booking_approve','booking_held','booking_stale','booking_changes','booking_unticked',
    'booking_reject','reject_multi','reject_held','reject_flagged','booking_multi_a','booking_multi_b','booking_reject_held','booking_reject_flagged','booking_invalid','booking_inactive','booking_withdraw_review','booking_withdraw_confirmed','line_changes','line_unticked','line_reject','line_foreign','line_inactive','line_withdraw_review','line_withdraw_confirmed'
]) key;

-- Auth trigger creates attendee profiles; staff roles are granted explicitly.
insert into auth.users (id, email, raw_user_meta_data, raw_app_meta_data)
select id, 'safety-check+' || id || '@example.invalid',
       jsonb_build_object('full_name', 'Safety verification ' || key), '{}'::jsonb
from safety_fixture where key in ('organiser','coordinator','officer','other_coordinator','staff');
insert into public.user_roles (profile_id, role)
select f.id, r.role::public.user_role from safety_fixture f join (values
    ('organiser','event_organiser'), ('organiser','venue_staff'),
    ('coordinator','event_coordinator'), ('coordinator','venue_staff'), ('coordinator','tech_support'),
    ('officer','safety_officer'), ('officer','venue_staff'),
    ('other_coordinator','event_coordinator'), ('staff','venue_staff'), ('staff','tech_support')
) r(key,role) using (key) on conflict do nothing;
update public.profiles p set role = r.role::public.user_role
from safety_fixture f join (values
    ('organiser','event_organiser'), ('coordinator','event_coordinator'),
    ('officer','safety_officer'), ('other_coordinator','event_coordinator'), ('staff','venue_staff')
) r(key,role) using (key) where p.id=f.id;
insert into public.equipment (id,name,equipment_type,total_quantity)
select id,'Safety fixture','Verification',10 from safety_fixture where key='equipment';
insert into public.events (id,organiser_id,coordinator_id,status,name,starts_at,ends_at)
select f.id,o.id,c.id,case f.key when 'withdraw_confirmed' then 'confirmed' when 'withdraw_preparation' then 'preparation' else 'safety_review' end::public.event_status,
       'Safety fixture ' || f.key, '2099-01-01 10:00+00','2099-01-01 12:00+00'
from safety_fixture f cross join safety_fixture o cross join safety_fixture c
where o.key='organiser' and c.key='coordinator'
  and f.key in ('replace_event','cl_event','approve','held','empty','stale','changes','reject','reject_multi','reject_held','reject_flagged','invalid','withdraw_review','withdraw_confirmed','withdraw_preparation');
-- Each booking gets its own venue and explicit space; all periods match the event.
-- Requires the live event_space_requests migrations (20261008100000/20261009100000).
do $$
declare r record; venue uuid; space uuid;
begin
    for r in
        select b.id booking_id,e.id event_id,x.status
        from (values ('booking_approve','approve','approved'),('booking_held','held','held'),
         ('booking_stale','stale','approved'),('booking_changes','changes','approved'),
         ('booking_unticked','changes','approved'),('booking_reject','reject','approved'),
         ('booking_multi_a','reject_multi','approved'),('booking_multi_b','reject_multi','approved'),
         ('booking_reject_held','reject_held','held'),('booking_reject_flagged','reject_flagged','approved'),
         ('booking_invalid','invalid','approved'),('booking_inactive','reject','released'),
         ('booking_withdraw_review','withdraw_review','approved'),('booking_withdraw_confirmed','withdraw_confirmed','approved'),
         ('booking_cl_a','cl_event','approved'),('booking_cl_b','cl_event','approved')) x(booking,event,status)
        join safety_fixture b on b.key=x.booking join safety_fixture e on e.key=x.event
    loop
        venue := gen_random_uuid(); space := gen_random_uuid();
        insert into public.venues(id,name,location,capacity,opens_at,closes_at)
        values(venue,'Safety fixture '||venue,'Verification',100,'08:00','23:00');
        insert into public.event_space_requests(id,event_id,label,starts_at,ends_at)
        values(space,r.event_id,'Safety fixture '||space,'2099-01-01 10:00+00','2099-01-01 12:00+00');
        insert into public.venue_bookings(id,event_id,venue_id,event_space_request_id,occupied_period,status)
        values(r.booking_id,r.event_id,venue,space,
               tstzrange('2099-01-01 10:00+00','2099-01-01 12:00+00','[)'),r.status::public.venue_booking_status);
    end loop;
end $$;
insert into public.equipment_requests (id,event_id,equipment_id,submission_id,quantity,status,requested_by)
select l.id,e.id,q.id,gen_random_uuid(),1,r.status::public.equipment_request_status,c.id
from (values ('line_changes','changes','reserved'),('line_unticked','changes','pending'),
 ('line_reject','reject','pending'),('line_foreign','approve','pending'),('line_inactive','reject','released'),
 ('line_withdraw_review','withdraw_review','reserved'),('line_withdraw_confirmed','withdraw_confirmed','reserved')) r(line,event,status)
join safety_fixture l on l.key=r.line join safety_fixture e on e.key=r.event
cross join safety_fixture q cross join safety_fixture c where q.key='equipment' and c.key='coordinator';

-- Snapshot every relevant row on one event, including fixture-created history.
create function pg_temp.snapshot(e uuid) returns jsonb language sql as $$
select jsonb_build_object('event',(select to_jsonb(x) from public.events x where id=e),
 'history',(select jsonb_agg(to_jsonb(x) order by id) from public.event_status_history x where event_id=e),
 'decisions',(select jsonb_agg(to_jsonb(x) order by id) from public.event_safety_decisions x where event_id=e),
 'checklist',(select jsonb_agg(to_jsonb(x) order by id) from public.event_safety_checklist_items x where event_id=e),
 'notifications',(select jsonb_agg(to_jsonb(x) order by id) from public.notifications x where event_id=e),
 'bookings',(select jsonb_agg(to_jsonb(x) order by id) from public.venue_bookings x where event_id=e),
 'booking_history',(select jsonb_agg(to_jsonb(x) order by x.id) from public.venue_booking_history x join public.venue_bookings b on b.id=x.booking_id where b.event_id=e),
 'equipment',(select jsonb_agg(to_jsonb(x) order by id) from public.equipment_requests x where event_id=e));
$$;
create function pg_temp.assert(ok boolean, label text) returns void language plpgsql as $$
begin if ok is distinct from true then raise exception 'SAFETY FAIL: %', label; end if; end $$;

-- CR-108 AC1/AC2: the five venue factors for every active booking, then equipment placement once.
create function pg_temp.full_checklist(e uuid, rating text default 'satisfactory') returns jsonb language sql as $$
select coalesce(jsonb_agg(m order by ord), '[]'::jsonb) from (
    select 1 ord, jsonb_build_object('factor', f, 'booking_id', b.id, 'rating', rating) m
    from public.venue_bookings b
    cross join unnest(array['attendance_capacity','layout','emergency_access','accessibility','venue_restrictions']) f
    where b.event_id = e and b.status in ('held','approved','re_review')
    union all
    select 2, jsonb_build_object('factor', 'equipment_placement', 'booking_id', null, 'rating', rating)
) x;
$$;
-- The checks below predate CR-108, so they call these with the old argument order (the officer's
-- text stays the 5th/4th argument); the checklist is always complete and the other text is fixed.
create function pg_temp.approve(e uuid, actor uuid, v integer, pnote text, omsg text, smsg text)
returns setof public.events language sql as $$
select * from public.safety_approve_event(e, actor, v, pg_temp.full_checklist(e), 'Organiser comment', pnote, omsg, smsg);
$$;
create function pg_temp.ret(e uuid, actor uuid, v integer, decision_kind text, ocomment text, bookings uuid[], lines uuid[], cmsg text)
returns setof public.events language sql as $$
select * from public.safety_return_event(e, actor, v, decision_kind, pg_temp.full_checklist(e), ocomment, 'PRIVATE-NOTE-CR108', bookings, lines, cmsg);
$$;

do $$
declare
    e uuid; actor uuid := (select id from safety_fixture where key='officer');
    organiser uuid := (select id from safety_fixture where key='organiser');
    coordinator uuid := (select id from safety_fixture where key='coordinator');
    b uuid; line uuid; v integer; h integer; n integer; before_state jsonb;
    result public.events; source text; k text; bad uuid; sig text; role_name text;
    marker text := 'PRIVATE-OFFICER-COMMENT-CR104';
begin
    e := (select id from safety_fixture where key='approve');
    select version into v from public.events where id=e;
    select count(*) into h from public.event_status_history where event_id=e;
    select * into result from pg_temp.approve(e,actor,v,marker,'Fixed organiser','Fixed staff');
    perform pg_temp.assert(result.status='confirmed' and result.version=v+1,'approve transition');
    perform pg_temp.assert((select count(*) from public.event_status_history where event_id=e)=h+1,'one approve history');
    perform pg_temp.assert((select count(*) from public.event_status_history where event_id=e and from_status='safety_review' and to_status='confirmed' and actor_id=actor and reason is null)=1,'approve history shape');
    perform pg_temp.assert((select count(*) from public.event_safety_decisions where event_id=e and decision='approved' and comment=marker and organiser_comment='Organiser comment' and decided_by=actor)=1,'one approve decision');
    perform pg_temp.assert((select count(*) from public.event_safety_checklist_items i join public.event_safety_decisions d on d.id=i.decision_id where d.event_id=e)=6,'approve records its six marks');
    perform pg_temp.assert(not exists(select 1 from public.notifications where event_id=e and recipient_id=actor),'no actor notification');
    perform pg_temp.assert(not exists(select 1 from public.notifications where event_id=e group by recipient_id having count(*)>1),'deduplicated recipients');
    perform pg_temp.assert((select count(*) from public.notifications where event_id=e and recipient_id=organiser and message='Fixed organiser' and type='event_safety_approved')=1,'organiser once');
    perform pg_temp.assert(not exists(
        select recipient from (select coordinator recipient union select profile_id from public.user_roles where role in ('venue_staff','tech_support')) recipients
        where recipient not in (actor,organiser) and not exists(select 1 from public.notifications where event_id=e and recipient_id=recipient and message='Fixed staff' and type='event_safety_approved')),'all staff recipients');
    -- Sequential losing decision verifies the lock/version backstop; concurrency needs two sessions.
    before_state := pg_temp.snapshot(e);
    select count(*) into n from pg_temp.ret(e,actor,v,'changes_requested',marker,'{}','{}','Fixed coordinator');
    perform pg_temp.assert(n=0 and pg_temp.snapshot(e)=before_state,'second officer loses without writes');

    foreach k in array array['held','empty','stale'] loop
        e := (select id from safety_fixture where key=k);
        select version into v from public.events where id=e;
        before_state := pg_temp.snapshot(e);
        select count(*) into n from pg_temp.approve(e,actor,v-case when k='stale' then 1 else 0 end,marker,'Fixed organiser','Fixed staff');
        perform pg_temp.assert(n=0 and pg_temp.snapshot(e)=before_state,'approve refused: '||k);
    end loop;
    e := (select id from safety_fixture where key='held');
    update public.venue_bookings set status='re_review' where event_id=e;
    before_state := pg_temp.snapshot(e);
    select count(*) into n from pg_temp.approve(e,actor,(select version from public.events where id=e),marker,'Fixed organiser','Fixed staff');
    perform pg_temp.assert(n=0 and pg_temp.snapshot(e)=before_state,'approve re_review refused');

    e := (select id from safety_fixture where key='invalid');
    select version into v from public.events where id=e;
    before_state := pg_temp.snapshot(e);
    foreach bad in array array[(select id from safety_fixture where key='booking_approve'),gen_random_uuid(),null::uuid] loop
        select count(*) into n from pg_temp.ret(e,actor,v,'changes_requested',marker,array[bad],'{}','Fixed coordinator');
        perform pg_temp.assert(n=0 and pg_temp.snapshot(e)=before_state,'foreign/unknown/null booking refused');
    end loop;
    foreach bad in array array[(select id from safety_fixture where key='line_foreign'),gen_random_uuid(),null::uuid] loop
        select count(*) into n from pg_temp.ret(e,actor,v,'changes_requested',marker,'{}',array[bad],'Fixed coordinator');
        perform pg_temp.assert(n=0 and pg_temp.snapshot(e)=before_state,'foreign/unknown/null equipment refused');
    end loop;
    foreach k in array array['approved','withdrawn','invalid',null::text] loop
        begin
            perform pg_temp.ret(e,actor,v,k,marker,'{}','{}','Fixed coordinator');
            raise exception 'SAFETY FAIL: invalid decision accepted';
        exception when invalid_parameter_value then null; end;
        perform pg_temp.assert(pg_temp.snapshot(e)=before_state,'invalid decision unchanged');
    end loop;
    -- CR-108 AC4: a return needs an organiser comment of 1-1000 characters.
    foreach k in array array['','   ',repeat('x',1001),null::text] loop
        begin
            perform pg_temp.ret(e,actor,v,'changes_requested',k,'{}','{}','Fixed coordinator');
            raise exception 'SAFETY FAIL: invalid organiser comment accepted';
        exception when invalid_parameter_value then null; end;
        perform pg_temp.assert(pg_temp.snapshot(e)=before_state,'invalid organiser comment writes nothing');
    end loop;
    select count(*) into n from pg_temp.ret(e,actor,v-1,'changes_requested',marker,'{}','{}','Fixed coordinator');
    perform pg_temp.assert(n=0 and pg_temp.snapshot(e)=before_state,'stale return unchanged');

    foreach k in array array['changes','reject'] loop
        e := (select id from safety_fixture where key=k);
        b := (select id from safety_fixture where key=case when k='changes' then 'booking_changes' else 'booking_reject' end);
        line := (select id from safety_fixture where key=case when k='changes' then 'line_changes' else 'line_reject' end);
        select version into v from public.events where id=e;
        select count(*) into h from public.event_status_history where event_id=e;
        before_state := pg_temp.snapshot(e);
        select * into result from pg_temp.ret(e,actor,v,case when k='changes' then 'changes_requested' else 'arrangement_rejected' end,
          '  '||marker||'  ',array[b,b],case when k='changes' then array[line,line] else '{}'::uuid[] end,'Fixed coordinator');
        perform pg_temp.assert(result.status='planning' and result.version=v+1,'return transition '||k);
        perform pg_temp.assert((select count(*) from public.event_status_history where event_id=e)=h+1,'one return history');
        perform pg_temp.assert((select status from public.venue_bookings where id=b)='approved','booking remains approved');
        perform pg_temp.assert((select status::text from public.equipment_requests where id=line)=case when k='changes' then 'reserved' else 'pending' end,'equipment unchanged');
        perform pg_temp.assert((select count(*) from public.event_safety_decisions where event_id=e and affected_booking_ids=array[b]
          and affected_equipment_request_ids=case when k='changes' then array[line] else '{}'::uuid[] end
          and organiser_comment=marker and comment='PRIVATE-NOTE-CR108' and decided_by=actor)=1,'decision concerned ids deduplicated');
        perform pg_temp.assert((pg_temp.snapshot(e)->'equipment') is not distinct from (before_state->'equipment'),'all equipment fields unchanged');
        if k='reject' then
            perform pg_temp.assert((select flag='safety_rejected' and flag_reason=marker and flagged_at is not null from public.venue_bookings where id=b),'rejected booking flag and trimmed reason');
            perform pg_temp.assert((select count(*) from public.venue_booking_history where booking_id=b and action='safety_rejected' and actor_id=actor and from_status='approved' and to_status='approved')=1,'rejection history');
            perform pg_temp.assert((select rejected_venue_ids from public.event_safety_decisions where event_id=e)=array[(select venue_id from public.venue_bookings where id=b)],'rejected venue ids');
        else
            perform pg_temp.assert((pg_temp.snapshot(e)->'bookings') is not distinct from (before_state->'bookings') and (pg_temp.snapshot(e)->'booking_history') is not distinct from (before_state->'booking_history'),'all booking fields and history unchanged on request changes');
            perform pg_temp.assert((select rejected_venue_ids from public.event_safety_decisions where event_id=e)='{}'::uuid[],'changes rejects no venues');
            perform pg_temp.assert((select flag is null from public.venue_bookings where id=b),'changes sets no flag');
            perform pg_temp.assert((select status from public.venue_bookings where id=(select id from safety_fixture where key='booking_unticked'))='approved','unticked booking unchanged');
        end if;
        perform pg_temp.assert((select count(*) from public.notifications where event_id=e)=1 and
          (select recipient_id=coordinator and message='Fixed coordinator' and type=case when k='changes' then 'event_safety_changes_requested' else 'event_safety_arrangement_rejected' end from public.notifications where event_id=e),'coordinator only');
    end loop;

    -- TC-SDEC-024/025: refuse held/flagged bookings without any side effects.
    foreach k in array array['reject_held','reject_flagged','reject_multi'] loop
        e := (select id from safety_fixture where key=k);
        b := (select id from safety_fixture where key=case k when 'reject_multi' then 'booking_multi_a' when 'reject_held' then 'booking_reject_held' else 'booking_reject_flagged' end);
        select version into v from public.events where id=e;
        if k='reject_flagged' then
            update public.venue_bookings set flag='affected',flag_reason='Unavailable',flagged_at=now() where id=b;
        end if;
        before_state := pg_temp.snapshot(e);
        if k='reject_multi' then
            begin
                perform pg_temp.ret(e,actor,v,'arrangement_rejected',marker,array[b,(select id from safety_fixture where key='booking_multi_b')],'{}','Fixed coordinator');
                raise exception 'SAFETY FAIL: two rejected bookings accepted';
            exception when invalid_parameter_value then null; end;
            perform pg_temp.assert(pg_temp.snapshot(e)=before_state,'invalid cardinality unchanged');
            perform pg_temp.ret(e,actor,v,'arrangement_rejected',marker,array[b],'{}','Fixed coordinator');
            perform pg_temp.assert((select status='approved' and flag is null from public.venue_bookings where id=(select id from safety_fixture where key='booking_multi_b')),'other space remains ready');
        else
            select count(*) into n from pg_temp.ret(e,actor,v,'arrangement_rejected',marker,array[b],'{}','Fixed coordinator');
            perform pg_temp.assert(n=0 and pg_temp.snapshot(e)=before_state,'reject refused unchanged: '||k);
        end if;
    end loop;

    e := (select id from safety_fixture where key='reject');
    b := (select id from safety_fixture where key='booking_reject');
    before_state := pg_temp.snapshot(e);
    perform pg_temp.assert(public.mark_safety_revision(gen_random_uuid(),coordinator,'Moved the barriers')='booking_not_found','revision missing');
    perform pg_temp.assert(public.mark_safety_revision(b,(select id from safety_fixture where key='other_coordinator'),'Moved the barriers')='not_assigned','revision assignment');
    perform pg_temp.assert(pg_temp.snapshot(e)=before_state,'unassigned revision unchanged');
    foreach source in array array['safety_review','confirmed'] loop
        update public.events set status=source::public.event_status where id=e;
        before_state := pg_temp.snapshot(e);
        perform pg_temp.assert(public.mark_safety_revision(b,coordinator,'Moved the barriers')='not_planning','revision only planning: '||source);
        perform pg_temp.assert(pg_temp.snapshot(e)=before_state,'nonplanning revision unchanged');
    end loop;
    update public.events set status='planning' where id=e;
    select version into v from public.events where id=e;
    select count(*) into n from public.notifications where event_id=e;
    perform pg_temp.assert(public.mark_safety_revision(b,coordinator,'Moved the barriers')='ok','revision succeeds');
    perform pg_temp.assert((select reason from public.venue_booking_history where booking_id=b and action='safety_revised')='Moved the barriers','revision note stored');
    perform pg_temp.assert((select flag is null and flag_reason is null and flagged_at is null and status='approved' from public.venue_bookings where id=b),'revision clears all flag columns');
    perform pg_temp.assert((select count(*) from public.venue_booking_history where booking_id=b and action='safety_revised' and actor_id=coordinator and from_status='approved' and to_status='approved')=1,'revision history');
    perform pg_temp.assert((select version from public.events where id=e)=v and (select count(*) from public.notifications where event_id=e)=n,'revision no version bump or notification');
    before_state := pg_temp.snapshot(e);
    perform pg_temp.assert(public.mark_safety_revision(b,coordinator,'Moved the barriers')='not_safety_rejected','revision twice refused');
    perform pg_temp.assert(pg_temp.snapshot(e)=before_state,'second revision unchanged');

    -- D71: an event in Preparation returns too, like a Confirmed one (§6.7 approved_change).
    foreach source in array array['safety_review','confirmed','preparation'] loop
        e := (select id from safety_fixture where key=case source when 'safety_review' then 'withdraw_review' when 'confirmed' then 'withdraw_confirmed' else 'withdraw_preparation' end);
        select version into v from public.events where id=e;
        select count(*) into h from public.event_status_history where event_id=e;
        before_state := pg_temp.snapshot(e);
        select count(*) into n from public.return_event_to_planning(e,v-1,source,'booking_cancelled','Fixed coordinator','Fixed officer');
        perform pg_temp.assert(n=0 and pg_temp.snapshot(e)=before_state,'stale withdrawal unchanged');
        select * into result from public.return_event_to_planning(e,v,source,'booking_cancelled','Fixed coordinator','Fixed officer');
        perform pg_temp.assert(result.status='planning' and result.version=v+1,'withdraw transition '||source);
        perform pg_temp.assert((select count(*) from public.event_status_history where event_id=e)=h+1,'one withdraw history');
        perform pg_temp.assert((select count(*) from public.event_status_history where event_id=e and from_status::text=source and to_status='planning' and actor_id is null and reason is null)=1,'withdraw history actor and reason');
        perform pg_temp.assert((select count(*) from public.event_safety_decisions where event_id=e and decision='withdrawn' and reason_code='booking_cancelled' and decided_by is null and comment is null)=1,'system withdrawal');
        perform pg_temp.assert((pg_temp.snapshot(e)->'bookings') is not distinct from (before_state->'bookings') and (pg_temp.snapshot(e)->'equipment') is not distinct from (before_state->'equipment'),'withdraw arrangements unchanged');
        perform pg_temp.assert((select count(*) from public.notifications where event_id=e and recipient_id=coordinator and message='Fixed coordinator' and type='event_returned_to_planning')=1,'withdraw coordinator');
        perform pg_temp.assert(not exists(select 1 from public.notifications where event_id=e group by recipient_id having count(*)>1),'withdraw recipients deduplicated');
        if source='safety_review' then
            perform pg_temp.assert(not exists(select 1 from public.user_roles ur where role='safety_officer' and not exists(select 1 from public.notifications where event_id=e and recipient_id=ur.profile_id and message='Fixed officer')),'withdraw all officers');
        else
            perform pg_temp.assert((select count(*) from public.notifications where event_id=e)=1,source||': no officers');
        end if;
        before_state := pg_temp.snapshot(e);
        select count(*) into n from public.return_event_to_planning(e,result.version,source,'booking_cancelled','Fixed coordinator','Fixed officer');
        perform pg_temp.assert(n=0 and pg_temp.snapshot(e)=before_state,'wrong source status unchanged');
    end loop;
    foreach source in array array['draft','submitted','under_review','returned','planning','rejected',null::text] loop
        begin
            perform public.return_event_to_planning(e,0,source,'booking_cancelled','Fixed coordinator','Fixed officer');
            raise exception 'SAFETY FAIL: invalid source accepted';
        exception when invalid_parameter_value then null; end;
    end loop;
    perform pg_temp.assert(not exists(select 1 from public.event_status_history where event_id in (select id from safety_fixture) and reason is not null),'no history reasons');
    perform pg_temp.assert(not exists(select 1 from public.notifications where event_id in (select id from safety_fixture) and position(marker in message)>0),'no comment leakage');
    perform pg_temp.assert((select relrowsecurity from pg_class where oid='public.event_safety_decisions'::regclass),'RLS enabled');
    perform pg_temp.assert(not exists(select 1 from pg_policies where schemaname='public' and tablename='event_safety_decisions' and cmd<>'SELECT'),'no write policies');
    foreach role_name in array array['anon','authenticated'] loop
        perform pg_temp.assert(not has_table_privilege(role_name,'public.event_safety_decisions','INSERT')
            and not has_table_privilege(role_name,'public.event_safety_decisions','UPDATE')
            and not has_table_privilege(role_name,'public.event_safety_decisions','DELETE'),'no direct writes '||role_name);
    end loop;
    begin
        insert into public.event_safety_decisions(event_id,decision,reason_code) values(e,'approved','booking_cancelled');
        raise exception 'SAFETY FAIL: reason allowed on non-withdrawal';
    exception when check_violation then null; end;
    begin
        insert into public.event_safety_decisions(event_id,decision) values(e,'withdrawn');
        raise exception 'SAFETY FAIL: withdrawal without reason accepted';
    exception when check_violation then null; end;
    foreach sig in array array['public.safety_approve_event(uuid,uuid,integer,jsonb,text,text,text,text)',
        'public.safety_return_event(uuid,uuid,integer,text,jsonb,text,text,uuid[],uuid[],text)',
        'public.return_event_to_planning(uuid,integer,text,text,text,text)',
        'public.mark_safety_revision(uuid,uuid,text)'] loop
        foreach role_name in array array['anon','authenticated'] loop
            perform pg_temp.assert(not has_function_privilege(role_name,sig,'EXECUTE'),'RPC denied: '||role_name||' '||sig);
        end loop;
        perform pg_temp.assert(has_function_privilege('service_role',sig,'EXECUTE'),'service RPC permitted');
    end loop;
end $$;

-- CR-108 (QA3-17): the checklist. cl_event has two approved bookings, so the venue factors are
-- answered per booking (AC2), and a missing mark for either one refuses the decision (AC3).
do $$
declare
    e uuid := (select id from safety_fixture where key='cl_event');
    a uuid := (select id from safety_fixture where key='booking_cl_a');
    other uuid := (select id from safety_fixture where key='booking_approve');
    actor uuid := (select id from safety_fixture where key='officer');
    coordinator uuid := (select id from safety_fixture where key='coordinator');
    v integer; cl jsonb; k text; before_state jsonb; result public.events; d uuid; role_name text; sig text;
begin
    select version into v from public.events where id=e;
    before_state := pg_temp.snapshot(e);
    foreach k in array array['empty','missing_venue_factor','missing_equipment','duplicate','foreign_booking',
                             'bad_rating','equipment_with_booking','venue_without_booking','long_note','concern'] loop
        cl := pg_temp.full_checklist(e);
        case k
            when 'empty' then cl := '[]'::jsonb;
            when 'missing_venue_factor' then
                cl := (select jsonb_agg(m) from jsonb_array_elements(cl) m
                       where not (m->>'factor'='layout' and m->>'booking_id'=a::text));
            when 'missing_equipment' then
                cl := (select jsonb_agg(m) from jsonb_array_elements(cl) m where m->>'factor'<>'equipment_placement');
            when 'duplicate' then cl := cl || jsonb_build_array(cl->0);
            when 'foreign_booking' then
                cl := cl || jsonb_build_array(jsonb_build_object('factor','layout','booking_id',other,'rating','satisfactory'));
            when 'bad_rating' then cl := jsonb_set(cl,'{0,rating}','"fine"');
            when 'equipment_with_booking' then
                cl := (select jsonb_agg(case when m->>'factor'='equipment_placement' then m || jsonb_build_object('booking_id',a) else m end)
                       from jsonb_array_elements(cl) m);
            when 'venue_without_booking' then cl := jsonb_set(cl,'{0,booking_id}','null'::jsonb);
            when 'long_note' then cl := jsonb_set(cl,'{0,note}',to_jsonb(repeat('x',1001)));
            when 'concern' then cl := jsonb_set(cl,'{0,rating}','"concern"');
        end case;
        -- A Concern blocks an approval only; the same checklist is fine for a return.
        if k <> 'concern' then
            begin
                perform public.safety_return_event(e,actor,v,'changes_requested',cl,'Fix it','note',array[a],'{}','Fixed coordinator');
                raise exception 'SAFETY FAIL: return accepted a bad checklist: %', k;
            exception when invalid_parameter_value then null; end;
        end if;
        begin
            perform public.safety_approve_event(e,actor,v,cl,null,null,'Fixed organiser','Fixed staff');
            raise exception 'SAFETY FAIL: approval accepted a bad checklist: %', k;
        exception when invalid_parameter_value then null; end;
        perform pg_temp.assert(pg_temp.snapshot(e)=before_state,'refused checklist writes nothing: '||k);
    end loop;

    -- AC1, AC4, AC6: a return records every mark, both texts and the officer; a Concern may go with it.
    cl := (select jsonb_agg(case when m->>'factor'='layout' and m->>'booking_id'=a::text
                                 then m || '{"rating":"concern","note":"Aisle too narrow"}'::jsonb else m end)
           from jsonb_array_elements(pg_temp.full_checklist(e)) m);
    select * into result from public.safety_return_event(e,actor,v,'changes_requested',cl,'  Widen the aisle  ','  officer only  ',array[a],'{}','Fixed coordinator');
    perform pg_temp.assert(result.status='planning' and result.version=v+1,'checklist return transitions');
    select id into d from public.event_safety_decisions where event_id=e;
    perform pg_temp.assert((select organiser_comment='Widen the aisle' and comment='officer only' and decided_by=actor
                            from public.event_safety_decisions where id=d),'both texts trimmed and kept apart');
    perform pg_temp.assert((select count(*) from public.event_safety_checklist_items where decision_id=d)=11,'ten venue marks and one equipment mark');
    perform pg_temp.assert((select count(*) from public.event_safety_checklist_items
        where decision_id=d and factor='layout' and booking_id=a and rating='concern' and note='Aisle too narrow')=1,'the concern and its note are recorded for that venue');
    perform pg_temp.assert((select count(*) from public.event_safety_checklist_items
        where decision_id=d and factor='equipment_placement' and booking_id is null)=1,'equipment placement is marked once, for the event');
    perform pg_temp.assert((select count(*) from public.notifications where event_id=e)=1
        and not exists(select 1 from public.notifications where event_id=e and (position('Widen' in message)>0 or position('officer only' in message)>0)),
        'neither text reaches a notification');

    -- The marks are history: no edit, no delete (the event's own cascade still works).
    begin
        update public.event_safety_checklist_items set rating='satisfactory' where decision_id=d;
        raise exception 'SAFETY FAIL: checklist edited';
    exception when object_not_in_prerequisite_state then null; end;
    begin
        delete from public.event_safety_checklist_items where decision_id=d;
        raise exception 'SAFETY FAIL: checklist deleted';
    exception when object_not_in_prerequisite_state then null; end;

    -- A return without an organiser comment is refused by the table too, not only the function.
    begin
        insert into public.event_safety_decisions(event_id,decision,comment) values(e,'changes_requested','only a private note');
        raise exception 'SAFETY FAIL: return recorded without an organiser comment';
    exception when check_violation then null; end;

    -- Direct access: select-only RLS, no signed-in write path, helper functions not callable.
    perform pg_temp.assert((select relrowsecurity from pg_class where oid='public.event_safety_checklist_items'::regclass),'checklist RLS enabled');
    perform pg_temp.assert(not exists(select 1 from pg_policies where schemaname='public' and tablename='event_safety_checklist_items' and cmd<>'SELECT'),'checklist has no write policies');
    foreach role_name in array array['anon','authenticated'] loop
        perform pg_temp.assert(not has_table_privilege(role_name,'public.event_safety_checklist_items','INSERT')
            and not has_table_privilege(role_name,'public.event_safety_checklist_items','UPDATE')
            and not has_table_privilege(role_name,'public.event_safety_checklist_items','DELETE'),'no direct checklist writes '||role_name);
        foreach sig in array array['private.safety_checklist_problem(uuid,jsonb,text)','private.record_safety_checklist(uuid,uuid,jsonb)'] loop
            perform pg_temp.assert(not has_function_privilege(role_name,sig,'EXECUTE'),'helper denied: '||role_name||' '||sig);
        end loop;
    end loop;
    perform pg_temp.assert(not exists(select 1 from public.notifications where event_id in (select id from safety_fixture)
        and (position('PRIVATE-NOTE-CR108' in message)>0 or position('Organiser comment' in message)>0)),'no CR-108 text leaks into any notification');
end $$;

-- Explicit sessions test active roles, including an officer acting as staff.
create temporary table safety_sessions as
select gen_random_uuid() session_id,f.id profile_id,r.role::public.user_role role,r.expected
from (values ('organiser','event_organiser',0),('coordinator','event_coordinator',1),
 ('other_coordinator','event_coordinator',0),('staff','venue_staff',0),
 ('officer','safety_officer',1),('officer','venue_staff',0),('coordinator','venue_staff',0)) r(key,role,expected)
join safety_fixture f using(key);
insert into auth.sessions (id,user_id,created_at,updated_at)
select session_id,profile_id,now(),now() from safety_sessions;
insert into public.session_active_roles (session_id,profile_id,role)
select session_id,profile_id,role from safety_sessions;
grant select on safety_sessions,safety_fixture to authenticated;

do $$
declare s record; n integer; m integer; e uuid := (select id from safety_fixture where key='approve');
        cl uuid := (select id from safety_fixture where key='cl_event');
begin
    for s in select * from safety_sessions loop
        perform set_config('request.jwt.claims',jsonb_build_object('sub',s.profile_id,'role','authenticated','session_id',s.session_id)::text,true);
        set local role authenticated;
        select count(*) into n from public.event_safety_decisions where event_id=e;
        select count(*) into m from public.event_safety_checklist_items where event_id=cl;
        reset role;
        perform pg_temp.assert(n=s.expected,'RLS active role '||s.role||' profile '||s.profile_id);
        perform pg_temp.assert((m>0)=(s.expected=1),'RLS checklist active role '||s.role||' profile '||s.profile_id);
    end loop;
end $$;
do $$
declare coordinator uuid := (select id from safety_fixture where key='coordinator');
        e uuid := (select id from safety_fixture where key='replace_event');
        old_b uuid := (select id from safety_fixture where key='booking_replace_old');
        plain uuid := (select id from safety_fixture where key='booking_plain');
        new_venue uuid := (select id from safety_fixture where key='replace_venue_new');
        space uuid := gen_random_uuid(); old_venue uuid := gen_random_uuid();
        outcome text; new_id uuid;
begin
    update public.events set status='planning' where id=e;
    insert into public.venues(id,name,location,capacity,opens_at,closes_at) values
        (old_venue,'Safety fixture old '||old_venue,'Verification',100,'08:00','23:00'),
        (new_venue,'Safety fixture new '||new_venue,'Verification',100,'08:00','23:00');
    insert into public.event_space_requests(id,event_id,label,starts_at,ends_at)
        values(space,e,'Safety fixture replace','2099-01-01 10:00+00','2099-01-01 12:00+00');
    insert into public.venue_bookings(id,event_id,venue_id,event_space_request_id,occupied_period,status,flag,flag_reason,flagged_at)
        values(old_b,e,old_venue,space,tstzrange('2099-01-01 10:00+00','2099-01-01 12:00+00','[)'),'approved','safety_rejected','Exits blocked',now());

    -- F1: blank and over-long notes refused, nothing changed.
    perform pg_temp.assert(public.mark_safety_revision(old_b,coordinator,null)='note_required','note null');
    perform pg_temp.assert(public.mark_safety_revision(old_b,coordinator,'   ')='note_required','note blank');
    begin
        perform public.mark_safety_revision(old_b,coordinator,repeat('x',1001));
        raise exception 'SAFETY FAIL: 1001-char note accepted';
    exception when check_violation then null; end;
    perform pg_temp.assert((select flag from public.venue_bookings where id=old_b)='safety_rejected','refused note leaves flag');

    -- F3: a Safety-rejected booking can be replaced; the index lets the replacement sit beside it.
    select o.outcome, o.booking_id into outcome, new_id
      from public.request_venue_booking_for_space(space,new_venue,coordinator,null,'msg',old_b) o;
    perform pg_temp.assert(outcome='ok','replacement of safety_rejected accepted: '||coalesce(outcome,'null'));
    perform pg_temp.assert((select replaces_booking_id from public.venue_bookings where id=new_id)=old_b,'replacement links');

    -- F4: revision refused while the replacement is live; allowed once it is rejected.
    perform pg_temp.assert(public.mark_safety_revision(old_b,coordinator,'Kept it')='replacement_pending','pending blocks revision');
    update public.venue_bookings set status='rejected' where id=new_id;
    perform pg_temp.assert(public.mark_safety_revision(old_b,coordinator,repeat('y',1000))='ok','1000-char note after replacement rejected');

    -- Null-flag trap: an unflagged approved booking is still not replaceable.
    -- It gets its own space: old_b is now an unflagged live booking on `space`,
    -- so a second live booking there would break the unique index.
    -- Its own venue too: DB-1 refuses two live bookings on one venue at once.
    space := gen_random_uuid(); old_venue := gen_random_uuid();
    insert into public.venues(id,name,location,capacity,opens_at,closes_at)
        values(old_venue,'Safety fixture plain '||old_venue,'Verification',100,'08:00','23:00');
    insert into public.event_space_requests(id,event_id,label,starts_at,ends_at)
        values(space,e,'Safety fixture plain','2099-01-01 10:00+00','2099-01-01 12:00+00');
    insert into public.venue_bookings(id,event_id,venue_id,event_space_request_id,occupied_period,status)
        values(plain,e,old_venue,space,tstzrange('2099-01-01 10:00+00','2099-01-01 12:00+00','[)'),'approved');
    select o.outcome into outcome from public.request_venue_booking_for_space(space,new_venue,coordinator,null,'msg',plain) o;
    perform pg_temp.assert(outcome='replaced_booking_invalid','unflagged booking not replaceable: '||coalesce(outcome,'null'));
end $$;

select 'SAFETY DECISION CHECKS PASSED' as result;
rollback;
