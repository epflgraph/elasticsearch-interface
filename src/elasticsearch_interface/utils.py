def es_bool(must=None, must_not=None, should=None, filter=None):
    """
    Build elasticsearch bool clause with given arguments.

    Returns:
        dict
    """

    query = {
        'bool': {}
    }

    if must is not None:
        query['bool']['must'] = must

    if must_not is not None:
        query['bool']['must_not'] = must_not

    if should is not None:
        query['bool']['should'] = should

    if filter is not None:
        query['bool']['filter'] = filter

    return query


def es_match(field, text, boost=None, operator=None):
    """
    Build elasticsearch match clause with given arguments.

    Returns:
        dict
    """

    query = {
        'match': {
            field: {
                'query': text
            }
        }
    }

    if boost is not None:
        query['match'][field]['boost'] = boost

    if operator is not None:
        query['match'][field]['operator'] = operator

    return query


def es_multi_match(fields, text, type=None, boost=None, minimum_should_match=None, operator=None):
    """
    Build elasticsearch multi_match clause with given arguments.

    Returns:
        dict
    """

    query = {
        'multi_match': {
            'fields': fields,
            'query': text
        }
    }

    if type is not None:
        query['multi_match']['type'] = type

    if boost is not None:
        query['multi_match']['boost'] = boost

    if minimum_should_match is not None:
        query['multi_match']['minimum_should_match'] = minimum_should_match

    if operator is not None:
        query['multi_match']['operator'] = operator

    return query


def es_dis_max(queries):
    """
    Build elasticsearch dis_max clause with given arguments.

    Returns:
        dict
    """

    query = {
        'dis_max': {
            'queries': queries
        }
    }

    return query
