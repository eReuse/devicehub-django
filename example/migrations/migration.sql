-- Defined the email of user
\set email 'rodriguez.eduardoj@gmail.com'
--\set email 'user@dhub.com'

-- save dhids and uuids of snapshots
copy(
select distinct d2.devicehub_id as dhid, sp.uuid, ac.created
from usody.action_with_one_device as one
  join usody.action as ac on ac.id=one.id
  join usody.device as d on d.id=one.device_id
  join usody.snapshot as sp on sp.id=one.id
  join common.user as u on u.id=ac.author_id
  join usody.placeholder as p on p.binding_id=d.id
  join usody.device as d2 on d2.id=p.device_id
where u.email=:'email'
  and not sp.uuid is null
  and not d2.devicehub_id is null
) to '/var/postgresql/dhids.csv'
with (format csv, header, delimiter ';', quote '"');


-- save lots and types
copy(
select distinct l.name, 'Incoming' as type from usody.transfer as t
  join usody.lot as l on l.id=t.lot_id
  join common.user as u on u.id=l.owner_id
where u.email=:'email' and
    t.user_to_id=u.id and
    l.owner_id=u.id
) to '/var/postgresql/lot_incoming.csv'
with (format csv, header, delimiter ';', quote '"');

copy(
select distinct l.name, 'Outgoing' as type from usody.transfer as t
  join usody.lot as l on l.id=t.lot_id
  join common.user as u on u.id=l.owner_id
where u.email=:'email' and
    t.user_from_id=u.id and
    l.owner_id=u.id
) to '/var/postgresql/lot_outgoing.csv'
with (format csv, header, delimiter ';', quote '"');

copy(
select distinct l.name, 'Temporary' as type from usody.lot as l
  left join usody.transfer as t on t.lot_id=l.id
  join common.user as u on u.id=l.owner_id
where u.email=:'email' and
  l.owner_id=u.id and
  t.lot_id is null
) to '/var/postgresql/lot_temporary.csv'
with (format csv, header, delimiter ';', quote '"');

-- save devices in lots
copy(
select distinct l.name as lot_name, d.devicehub_id as dhid from usody.lot as l
  join common.user as u on u.id=l.owner_id
  join usody.lot_device as ld on ld.lot_id=l.id
  join usody.device as d on d.id=ld.device_id
  join usody.placeholder as p on p.device_id=d.id
  join usody.device as d2 on d2.id=p.binding_id
where u.email=:'email'
  and not d.devicehub_id is null
) to '/var/postgresql/devices-lots.csv'
with (format csv, header, delimiter ';', quote '"');
