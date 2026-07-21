from django import template

register = template.Library()

@register.inclusion_tag('pagination.html')
def render_pagination(page_number, total_pages, limit=10, search=None, sort=None, query_param=None):
    """
    Template tag for render pagination

    Args:
    - page_number: number of actual page
    - total_pages: total pages.
    - query_param: name of the GET parameter holding ``search`` (e.g.
      ``gquery`` or ``lquery``), so pagination links keep the active search.

    Use it template: {% render_pagination page_number total_pages sort%}
    """
    return {
        'page_number': page_number,
        'total_pages': total_pages,
        'limit': limit,
        "search": search,
        "sort": sort,
        "query_param": query_param,
    }
