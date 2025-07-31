def bool_query(must=None, must_not=None, should=None, filter=None, minimum_should_match=None):
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

    if minimum_should_match is not None:
        query['bool']['minimum_should_match'] = minimum_should_match

    return query


def match_query(field, text, boost=None, operator=None):
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


def match_all_query():
    query = {
        'match_all': {}
    }
    return query


def term_query(term, text, boost=None):
    """
    Build elasticsearch term clause with given arguments.

    Returns:
        dict
    """

    query = {
        'term': {
            term: {
                'value': text
            }
        }
    }

    if boost is not None:
        query['term'][term]['boost'] = boost

    return query


def multi_match_query(fields, text, type=None, boost=None, minimum_should_match=None, operator=None):
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


def dis_max_query(queries):
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


def term_based_filter(term_to_values_dict):
    results = list()
    for term, value in term_to_values_dict.items():
        if value is None:
            continue
        if isinstance(value, list):
            results.append({
                "terms": {term: value}
            })
        else:
            results.append({
                "term": {term: value}
            })
    return results


def date_based_filter(term_to_values_dict, null_as_open=True):
    results = list()
    for term, value in term_to_values_dict.items():
        if value is None or not isinstance(value, dict):
            continue
        value = {k: v for k, v in value.items() if k in ['gte', 'lte']}
        if null_as_open:
            results.append(bool_query(should=[
                {"range": {term: value}},
                bool_query(must_not={"exists": {"field": term}})
            ], minimum_should_match=1
            ))
        else:
            results.append({"range": {term: value}})
    return results


SCORE_FUNCTIONS = [
    {
        "field_value_factor": {"field": "DegreeScore"}
    },
    {
        "filter": {"term": {"NodeType.keyword": "Concept"}},
        "weight": 512
    },
    {
        "filter": {"term": {"NodeType.keyword": "Person"}},
        "weight": 128
    },
    {
        "filter": {"term": {"NodeType.keyword": "Course"}},
        "weight": 128
    },
    {
        "filter": {"term": {"NodeType.keyword": "Unit"}},
        "weight": 64
    },
    {
        "filter": {"term": {"NodeType.keyword": "MOOC"}},
        "weight": 64
    },
    {
        "filter": {"term": {"NodeType.keyword": "Publication"}},
        "weight": 1
    }
]


def include_or_exclude_scores(hits, return_scores=False):
    if return_scores:
        hits = [{**hit['_source'], 'score': hit['_score']} for hit in hits]
    else:
        hits = [hit['_source'] for hit in hits]
    return hits


def include_or_exclude_embeddings(hits, return_embeddings=False):
    if not return_embeddings:
        hits = [{k: v for k, v in hit.items() if k != 'embedding'} for hit in hits]
    return hits
