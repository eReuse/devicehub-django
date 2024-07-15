import xapian

database = xapian.WritableDatabase("db", xapian.DB_CREATE_OR_OPEN)

indexer = xapian.TermGenerator()
stemmer = xapian.Stem("english")
indexer.set_stemmer(stemmer)


def search(qs, offset=0, limit=10):
    query_string = str.join(' ', qs)

    qp = xapian.QueryParser()
    qp.set_stemmer(stemmer)
    qp.set_database(database)
    qp.set_stemming_strategy(xapian.QueryParser.STEM_SOME)
    query = qp.parse_query(query_string)
    enquire = xapian.Enquire(database)
    enquire.set_query(query)
    matches = enquire.get_mset(offset, limit)
    return matches

