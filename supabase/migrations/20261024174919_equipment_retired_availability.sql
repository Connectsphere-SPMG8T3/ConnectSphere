-- 23-R / D57: retired catalogue stock cannot supply new demand.
-- Keep recorded totals and commitments, including existing reservations.
create or replace function public.equipment_availability(
    p_equipment_ids uuid[],
    p_start_at timestamptz,
    p_end_at timestamptz,
    p_exclude_reservation_id uuid default null
)
returns table (
    equipment_id uuid,
    total_quantity integer,
    outage_quantity integer,
    reserved_quantity integer,
    free_quantity integer
)
language sql
stable
security definer
set search_path = ''
as $$
    with commitments as (
        select r.equipment_id, 'reserved'::text as kind, r.quantity, r.start_at, r.end_at
          from public.equipment_reservations r
         where r.equipment_id = any (p_equipment_ids)
           and r.status = 'confirmed'
           and r.start_at < p_end_at and r.end_at > p_start_at
           and r.id is distinct from p_exclude_reservation_id
        union all
        select u.equipment_id, 'outage', u.quantity, u.start_at, u.end_at
          from public.equipment_unavailability u
         where u.equipment_id = any (p_equipment_ids)
           and u.start_at < p_end_at and u.end_at > p_start_at
    ),
    moments as (
        select e.id as equipment_id, p_start_at as at
          from public.equipment e where e.id = any (p_equipment_ids)
        union
        select c.equipment_id, c.start_at from commitments c where c.start_at > p_start_at
    ),
    peaks as (
        select m.equipment_id,
               max(coalesce((select sum(c.quantity) from commitments c
                              where c.equipment_id = m.equipment_id and c.kind = 'outage'
                                and c.start_at <= m.at and c.end_at > m.at), 0))::integer as outage_peak,
               max(coalesce((select sum(c.quantity) from commitments c
                              where c.equipment_id = m.equipment_id and c.kind = 'reserved'
                                and c.start_at <= m.at and c.end_at > m.at), 0))::integer as reserved_peak
          from moments m
         group by m.equipment_id
    )
    select e.id, e.total_quantity, p.outage_peak, p.reserved_peak,
           case when e.status = 'retired' then 0
                else greatest(0, e.total_quantity - p.outage_peak - p.reserved_peak) end
      from public.equipment e
      join peaks p on p.equipment_id = e.id;
$$;

comment on function public.equipment_availability(uuid[], timestamptz, timestamptz, uuid) is
    'Retired stock has zero free units; existing reservations remain held. Free quantity per item over [start, end): total − peak concurrent outage − peak concurrent confirmed reservations (§6.16 AV-R2, D43). Excludes one reservation when re-checking it. API-only.';

