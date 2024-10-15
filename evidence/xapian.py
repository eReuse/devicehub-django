import xapian

# database = xapian.WritableDatabase("db", xapian.DB_CREATE_OR_OPEN)

# Read Only
# database = xapian.Database("db")

# indexer = xapian.TermGenerator()
# stemmer = xapian.Stem("english")
# indexer.set_stemmer(stemmer)


def search(institution, qs, offset=0, limit=10):
    database = xapian.Database("db")

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
    matches = enquire.get_mset(offset, limit)
    return matches


def index(institution, uuid, snap):
    uuid = 'uuid:"{}"'.format(uuid)
    try:
        matches = search(institution, uuid, limit=1)
        if matches.size() > 0:
            return
    except (xapian.DatabaseNotFoundError, xapian.DatabaseOpeningError):
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
    institution_term = "U{}".format(institution.id)
    doc.add_term(institution_term)

    database.add_document(doc)
