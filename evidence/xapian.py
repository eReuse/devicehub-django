import xapian
from datetime import datetime

# database = xapian.WritableDatabase("db", xapian.DB_CREATE_OR_OPEN)

# Read Only
# database = xapian.Database("db")

# indexer = xapian.TermGenerator()
# stemmer = xapian.Stem("english")
# indexer.set_stemmer(stemmer)


def search(institution, qs, offset=0, limit=10):
    try:
        database = xapian.Database("db")
    except (xapian.DatabaseNotFoundError, xapian.DatabaseOpeningError):
        return

    qp = xapian.QueryParser()
    qp.set_database(database)
    qp.set_stemmer(xapian.Stem("english"))
    qp.set_stemming_strategy(xapian.QueryParser.STEM_SOME)
    qp.add_prefix("uuid", "uuid")
    query = qp.parse_query(qs)
    institution_term = "U{}".format(institution.id)
    final_query = xapian.Query(
        xapian.Query.OP_AND, query, xapian.Query(institution_term)
    )
    enquire = xapian.Enquire(database)
    enquire.set_query(final_query)

    enquire.set_sort_by_value_then_relevance(0, True)

    #colapse key is device_id
    enquire.set_collapse_key(1)

    matches = enquire.get_mset(offset, limit)
    return matches


def index(institution, device_id, uuid, timestamp, snap):
    uuid = 'uuid:"{}"'.format(uuid)
    matches = search(institution, uuid, limit=1)
    if matches and matches.size() > 0:
        return

    database = xapian.WritableDatabase("db", xapian.DB_CREATE_OR_OPEN)
    indexer = xapian.TermGenerator()
    stemmer = xapian.Stem("english")
    indexer.set_stemmer(stemmer)

    doc = xapian.Document()
    doc.set_data(snap)

    indexer.set_document(doc)
    indexer.index_text(snap)
    indexer.index_text(uuid, 10, "uuid")
    # indexer.index_text(snap, 1, "snapshot")

    # store device_id, uuid and timestamp
    doc.add_value(1, device_id)
    doc.add_value(2, str(uuid))

    try:
        timestamp_dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S.%f')
        timestamp_unix = timestamp_dt.timestamp()
        doc.add_value(0, xapian.sortable_serialise(timestamp_unix))
    except ValueError as e:
        print(f"Error parsing timestamp: {e}")

    institution_term = "U{}".format(institution.id)
    doc.add_term(institution_term)

    database.add_document(doc)
