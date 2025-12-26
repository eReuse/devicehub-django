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
  and not d.devicehub_id is null
) to '/var/postgresql/dhids.csv'
with (format csv, header, delimiter ';', quote '"');


-- save devices in lots
copy(
select distinct l.name as lot_name, d2.devicehub_id as dhid,
t.user_to_id as incoming, t.user_from_id as outgoing
from usody.action_with_one_device as one
  join usody.action as ac on ac.id=one.id
  join usody.device as d on d.id=one.device_id
  join usody.snapshot as sp on sp.id=one.id
  join common.user as u on u.id=ac.author_id
  join usody.placeholder as p on p.binding_id=d.id
  join usody.device as d2 on d2.id=p.device_id
  join usody.lot_device as ld on ld.device_id=d2.id
  join usody.lot as l on ld.lot_id=l.id
  left join usody.transfer as t on t.lot_id=l.id
where u.email=:'email'
  and not sp.uuid is null
  and not d2.devicehub_id is null
  and not d.devicehub_id is null
) to '/var/postgresql/devices-lots.csv'
with (format csv, header, delimiter ';', quote '"');
