-- SCRUM-82: transactional checks; all test changes roll back.
begin;
insert into public.events (id, organiser_id, coordinator_id, status, name)
values ('e0000000-0000-4000-8000-000000000382', 'a0000000-0000-4000-8000-000000000001',
'a0000000-0000-4000-8000-000000000002', 'planning', 'Safety check (rolled back)');
insert into public.user_roles (profile_id, role) values
('a0000000-0000-4000-8000-000000000002','safety_officer'),
('a0000000-0000-4000-8000-000000000003','safety_officer') on conflict do nothing;
do $$
declare
 e uuid := 'e0000000-0000-4000-8000-000000000382';
 actor uuid := 'a0000000-0000-4000-8000-000000000002';
 organiser uuid := 'a0000000-0000-4000-8000-000000000001';
 before_version integer;
 r public.events;
 n integer;
 history_count integer;
 notification_count integer;
begin
 select version into before_version from public.events where id=e;
 select * into r from public.send_event_to_safety_review(e,actor,array['planning'],'safety_review',before_version,'organiser message','officer message');
 if r.status is distinct from 'safety_review' or r.version <> before_version+1 then raise exception 'TC-SAFE-010: transition/version'; end if;
 if (select count(*) from public.event_status_history where event_id=e and from_status='planning' and to_status='safety_review' and actor_id=actor and at is not null) <> 1 then raise exception 'TC-SAFE-010: history'; end if;
 if (select count(*) from public.notifications where event_id=e and recipient_id=organiser and message='organiser message' and type='event_sent_for_safety_check') <> 1 then raise exception 'TC-SAFE-011: organiser'; end if;
 if exists(select 1 from public.notifications where event_id=e and recipient_id=actor) then raise exception 'TC-SAFE-011: self notification'; end if;
 if exists(select 1 from public.user_roles ur where ur.role='safety_officer' and ur.profile_id<>actor and not exists(select 1 from public.notifications n where n.event_id=e and n.recipient_id=ur.profile_id and n.message='officer message' and n.type='event_sent_for_safety_check')) then raise exception 'TC-SAFE-011: officers'; end if;
 select count(*) into history_count from public.event_status_history where event_id=e;
 select count(*) into notification_count from public.notifications where event_id=e;
 select count(*) into n from public.send_event_to_safety_review(e,actor,array['planning'],'safety_review',r.version,'x','y');
 if n<>0 then raise exception 'TC-SAFE-013: wrong status'; end if;
 select count(*) into n from public.send_event_to_safety_review(e,actor,array['safety_review'],'safety_review',r.version-1,'x','y');
 if n<>0 or (select version from public.events where id=e)<>r.version or (select count(*) from public.event_status_history where event_id=e)<>history_count or (select count(*) from public.notifications where event_id=e)<>notification_count then raise exception 'TC-SAFE-013: stale changed data'; end if;
 select count(*) into n from public.add_event_comment(e,actor,'Safety review discussion','comment');
 if n<>1 then raise exception 'TC-SAFE-014: comment rejected'; end if;
 delete from public.user_roles where role='safety_officer';
 update public.events set status='planning' where id=e;
 select version into before_version from public.events where id=e;
 select * into r from public.send_event_to_safety_review(e,actor,array['planning'],'safety_review',before_version,'no officers','officer message');
 if r.status is distinct from 'safety_review' or (select count(*) from public.notifications where event_id=e and recipient_id=organiser and message='no officers')<>1 then raise exception 'TC-SAFE-012: no officer pool'; end if;
end $$;
set local role anon;
do $$ begin
 begin
 perform public.send_event_to_safety_review(null,null,array['planning'],'safety_review',0,'x','y');
 raise exception 'TC-SAFE-015: anon execute permitted';
 exception when insufficient_privilege then null; end;
end $$;
reset role;
set local role authenticated;
do $$ begin
 begin
 perform public.send_event_to_safety_review(null,null,array['planning'],'safety_review',0,'x','y');
 raise exception 'TC-SAFE-015: authenticated execute permitted';
 exception when insufficient_privilege then null; end;
end $$;
reset role;
select 'TC-SAFE-010–015 SAFETY CHECKS PASSED' as result;
rollback;
