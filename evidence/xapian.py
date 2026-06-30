import xapian
from django.conf import settings

# database = xapian.WritableDatabase("db", xapian.DB_CREATE_OR_OPEN)

# Read Only
# database = xapian.Database("db")

# indexer = xapian.TermGenerator()
# stemmer = xapian.Stem("english")
# indexer.set_stemmer(stemmer)

def search(institution, qs, offset=0, limit=10):
    try:
        database = xapian.Database(settings.EVIDENCES_DIR)
    except (xapian.DatabaseNotFoundError, xapian.DatabaseOpeningError):
        return

    qp = xapian.QueryParser()
    qp.set_database(database)
    qp.set_stemmer(xapian.Stem("english"))
    qp.set_stemming_strategy(xapian.QueryParser.STEM_SOME)

    # AND operator so search doesnt return thousands of results
    qp.set_default_op(xapian.Query.OP_AND)

    qp.add_prefix("uuid", "uuid")

    flags = (
        xapian.QueryParser.FLAG_BOOLEAN |
        xapian.QueryParser.FLAG_PHRASE |
        xapian.QueryParser.FLAG_PARTIAL |
        xapian.QueryParser.FLAG_LOVEHATE
    )

    query = qp.parse_query(qs, flags)

    if institution:
        institution_term = "U{}".format(institution.id)
        final_query = xapian.Query(
            xapian.Query.OP_AND, query, xapian.Query(institution_term)
        )
    else:
        final_query = xapian.Query(query)

    enquire = xapian.Enquire(database)

    # sort by weight first
    enquire.set_weighting_scheme(xapian.BM25Weight())
    enquire.set_query(final_query)

    matches = enquire.get_mset(offset, limit)
    return matches

def index(institution, uuid, snap):
    uuid = 'uuid:"{}"'.format(uuid)
    matches = search(institution, uuid, limit=1)
    if matches and matches.size() > 0:
        return

    database = xapian.WritableDatabase(settings.EVIDENCES_DIR, xapian.DB_CREATE_OR_OPEN)
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
