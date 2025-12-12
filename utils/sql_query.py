from django.db import connection

def queryset_SQL(institution_id, offset=0, limit=None):
    # Search roots in RootAlias than not exist in Systemproperty
    qry1 = f"""
        select distinct root from evidence_rootalias as al
        where al.owner_id = {institution_id} and not exists (
            select 1
            from evidence_systemproperty as sp
            where al.root = sp.value and sp.owner_id = {institution_id}
            and al.owner_id = {institution_id}
        )
    """
    # Search the first entry alias for every one root of qry1
    qry2 = f"""
        select alias from (
            select alias, root, row_number() over (
                partition by root order by id asc
            ) as row_num from evidence_rootalias as _root
            where _root.owner_id = {institution_id}
        ) as subquery
        where row_num = 1 and root in ({qry1})
    """
    # Search all alias in RootAlias than not exists in qry2
    qry3 = f"""
        select distinct ali.alias from evidence_rootalias as ali
        where ali.alias not in ({qry2}) and ali.owner_id = {institution_id}
    """
    # Search all values in Systemproperty than not exists in qry3
    sql = f"""
        select distinct sp.value from evidence_systemproperty as sp
        where sp.value not in ({qry3}) and sp.owner_id = {institution_id}
    """

    if limit:
        sql += " limit {} offset {}".format(int(limit), int(offset))

    sql += ";"

    annotations = []
    with connection.cursor() as cursor:
        cursor.execute(sql)
        annotations = cursor.fetchall()

    return annotations


def queryset_SQL_count(institution_id):

    # Search roots in RootAlias than not exist in Systemproperty
    qry1 = f"""
        select distinct root from evidence_rootalias as al
        where al.owner_id = {institution_id} and not exists (
            select 1
            from evidence_systemproperty as sp
            where al.root = sp.value and sp.owner_id = {institution_id}
            and al.owner_id = {institution_id}
        )
    """
    # Search the first entry alias for every one root of qry1
    qry2 = f"""
        select alias from (
            select alias, root, row_number() over (
                partition by root order by id asc
            ) as row_num from evidence_rootalias as _root
            where _root.owner_id = {institution_id}
        ) as subquery
        where row_num = 1 and root in ({qry1})
    """
    # Search all alias in RootAlias than not exists in qry2
    qry3 = f"""
        select distinct ali.alias from evidence_rootalias as ali
        where ali.alias not in ({qry2}) and ali.owner_id = {institution_id}
    """
    # Search all values in Systemproperty than not exists in qry3
    sql = f"""
     select count(distinct sp.value) from evidence_systemproperty as sp
        where sp.value not in ({qry3}) and sp.owner_id = {institution_id};
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        return cursor.fetchall()[0][0]


def queryset_SQL_unassigned(institution_id, offset=0, limit=None):

    # Search roots in RootAlias than not exist in Systemproperty
    qry1 = f"""
        select distinct root from evidence_rootalias as al
        where al.owner_id = {institution_id} and not exists (
            select 1
            from evidence_systemproperty as sp
            where al.root = sp.value and sp.owner_id = {institution_id}
            and al.owner_id = {institution_id}
        )
    """
    # Search the first entry alias for every one root of qry1
    qry2 = f"""
        select alias from (
            select alias, root, row_number() over (
                partition by root order by id asc
            ) as row_num from evidence_rootalias as _root
            where _root.owner_id = {institution_id}
        ) as subquery
        where row_num = 1 and root in ({qry1})
    """
    # Search all alias in RootAlias than not exists in qry2
    qry3 = f"""
        select distinct ali.alias from evidence_rootalias as ali
        where ali.alias not in ({qry2}) and ali.owner_id = {institution_id}
    """
    device_lots = f"""
        select device_id from lot_devicelot as ld left join lot_lot as lot on ld.lot_id=lot.id
          where lot.owner_id = {institution_id}
    """
    alias_of_hids_in_lots = f"""
        select mp.alias from evidence_rootalias as mp
          where mp.owner_id={institution_id} and mp.root in (
            select distinct root from evidence_rootalias as ra
              where ra.owner_id={institution_id} and (ra.alias in (
                select device_id from lot_devicelot as ld
                  left join lot_lot as lot on ld.lot_id=lot.id
                where lot.owner_id = {institution_id}
              ) or ra.root in (
                select device_id from lot_devicelot as ld
                  left join lot_lot as lot on ld.lot_id=lot.id
                where lot.owner_id = {institution_id}
              )
            )
        )
    """
    roots_of_hids_in_lots = f"""
        select mp.root from evidence_rootalias as mp
          where mp.owner_id={institution_id} and mp.root in (
            select distinct root from evidence_rootalias as ra
              where ra.owner_id={institution_id} and (ra.alias in (
                select device_id from lot_devicelot as ld
                  left join lot_lot as lot on ld.lot_id=lot.id
                where lot.owner_id = {institution_id}
              ) or ra.root in (
                select device_id from lot_devicelot as ld
                  left join lot_lot as lot on ld.lot_id=lot.id
                where lot.owner_id = {institution_id}
              )
            )
        )
    """
    # Search all values in Systemproperty than not exists in qry3
    sql = f"""
        select distinct sp.value from evidence_systemproperty as sp
        where
          sp.value not in ({qry3}) and
          sp.value not in ({device_lots}) and
          sp.value not in ({alias_of_hids_in_lots}) and
          sp.value not in ({roots_of_hids_in_lots}) and
          sp.owner_id = {institution_id}
    """
    if limit:
        sql += " limit {} offset {}".format(int(limit), int(offset))

    sql += ";"

    annotations = []
    with connection.cursor() as cursor:
        cursor.execute(sql)
        annotations = cursor.fetchall()

    return annotations


def queryset_SQL_unassigned_count(institution_id):

    # Search roots in RootAlias than not exist in Systemproperty
    qry1 = f"""
        select distinct root from evidence_rootalias as al
        where al.owner_id = {institution_id} and not exists (
            select 1
            from evidence_systemproperty as sp
            where al.root = sp.value and sp.owner_id = {institution_id}
            and al.owner_id = {institution_id}
        )
    """
    # Search the first entry alias for every one root of qry1
    qry2 = f"""
        select alias from (
            select alias, root, row_number() over (
                partition by root order by id asc
            ) as row_num from evidence_rootalias as _root
            where _root.owner_id = {institution_id}
        ) as subquery
        where row_num = 1 and root in ({qry1})
    """
    # Search all alias in RootAlias than not exists in qry2
    qry3 = f"""
        select distinct ali.alias from evidence_rootalias as ali
        where ali.alias not in ({qry2}) and ali.owner_id = {institution_id}
    """
    device_lots = f"""
        select device_id from lot_devicelot as ld left join lot_lot as lot on ld.lot_id=lot.id
          where lot.owner_id = {institution_id}
    """
    alias_of_hids_in_lots = f"""
        select mp.alias from evidence_rootalias as mp
          where mp.owner_id={institution_id} and mp.root in (
            select distinct root from evidence_rootalias as ra
              where ra.owner_id={institution_id} and (ra.alias in (
                select device_id from lot_devicelot as ld
                  left join lot_lot as lot on ld.lot_id=lot.id
                where lot.owner_id = {institution_id}
              ) or ra.root in (
                select device_id from lot_devicelot as ld
                  left join lot_lot as lot on ld.lot_id=lot.id
                where lot.owner_id = {institution_id}
              )
            )
        )
    """
    roots_of_hids_in_lots = f"""
        select mp.root from evidence_rootalias as mp
          where mp.owner_id={institution_id} and mp.root in (
            select distinct root from evidence_rootalias as ra
              where ra.owner_id={institution_id} and (ra.alias in (
                select device_id from lot_devicelot as ld
                  left join lot_lot as lot on ld.lot_id=lot.id
                where lot.owner_id = {institution_id}
              ) or ra.root in (
                select device_id from lot_devicelot as ld
                  left join lot_lot as lot on ld.lot_id=lot.id
                where lot.owner_id = {institution_id}
              )
            )
        )
    """
    # Search all values in Systemproperty than not exists in qry3
    sql = f"""
        select count(distinct sp.value) from evidence_systemproperty as sp
        where
          sp.value not in ({qry3}) and
          sp.value not in ({device_lots}) and
          sp.value not in ({alias_of_hids_in_lots}) and
          sp.value not in ({roots_of_hids_in_lots}) and
          sp.owner_id = {institution_id};
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        return cursor.fetchall()[0][0]
