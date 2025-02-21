-- Defined the email of user
\set email 'user@example.org'

-- save dhids and uuids of snapshots
copy(
select d.devicehub_id as dhid, sp.uuid as uuid from usody.placeholder as p
  join common.user as u on u.id=owner_id
  join usody.computer as c on c.id=p.binding_id
  join usody.device as d on d.id=p.device_id
  join usody.action_with_one_device as one on p.binding_id=one.device_id
  join usody.snapshot as sp on sp.id=one.id
where u.email=:'email'
  and not p.binding_id is null
) to '/var/lib/postgresql/dhids.csv'
with (format csv, header, delimiter ';', quote '"');


-- save lots and types
copy(
select distinct l.name as lot_name, 'Incoming' as type from usody.transfer as t
  join usody.lot as l on l.id=t.lot_id
  join common.user as u on u.id=l.owner_id
where u.email=:'email' and
    t.user_to_id=u.id and
    l.owner_id=u.id
) to '/var/lib/postgresql/lot_incoming.csv'
with (format csv, header, delimiter ';', quote '"');

copy(
select distinct l.name as lot_name, 'Outgoing' as type from usody.transfer as t
  join usody.lot as l on l.id=t.lot_id
  join common.user as u on u.id=l.owner_id
where u.email=:'email' and
    t.user_from_id=u.id and
    l.owner_id=u.id
) to '/var/lib/postgresql/lot_outgoing.csv'
with (format csv, header, delimiter ';', quote '"');

copy(
select distinct l.name as lot_name, 'Temporary' as type from usody.lot as l
  left join usody.transfer as t on t.lot_id=l.id
  join common.user as u on u.id=l.owner_id
where u.email=:'email' and
  l.owner_id=u.id and
  t.lot_id is null
) to '/var/lib/postgresql/lot_temporary.csv'
with (format csv, header, delimiter ';', quote '"');

-- save devices in lots
copy(
select l.name as lot_name, d.devicehub_id as dhid from usody.lot_device as ld
  join usody.lot as l on l.id=ld.lot_id
  join usody.device as d on d.id=ld.device_id
  join common.user as u on u.id=ld.author_id
  join usody.placeholder as p on p.device_id=d.id
where u.email=:'email'
  and not p.binding_id is null
) to '/var/lib/postgresql/devices-lots.csv'
with (format csv, header, delimiter ';', quote '"');
