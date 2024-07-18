import xapian

# database = xapian.WritableDatabase("db", xapian.DB_CREATE_OR_OPEN)

# Read Only
# database = xapian.Database("db")

# indexer = xapian.TermGenerator()
# stemmer = xapian.Stem("english")
# indexer.set_stemmer(stemmer)


def search(qs, offset=0, limit=10):
    database = xapian.Database("db")

    qp = xapian.QueryParser()
    qp.set_database(database)
    qp.set_stemmer(xapian.Stem("english"))
    qp.set_stemming_strategy(xapian.QueryParser.STEM_SOME)
    qp.add_prefix("uuid", "uuid")
    # qp.add_prefix("snapshot", "snapshot")
    query = qp.parse_query(qs)
    enquire = xapian.Enquire(database)
    enquire.set_query(query)
    matches = enquire.get_mset(offset, limit)
    return matches


def index(uuid, snap):
    uuid = 'uuid:"{}"'.format(uuid)
    try:
        matches = search(uuid, limit=1)
        if matches.size() > 0:
            return
    except xapian.DatabaseNotFoundError:
        pass

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

    database.add_document(doc)
