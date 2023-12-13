from ssl import create_default_context

from elasticsearch import Elasticsearch

from elasticsearch_interface.utils import (
    bool_query,
    match_query,
    multi_match_query,
    dis_max_query,
    SCORE_FUNCTIONS,
)


class ES:
    """
    Base class to communicate with elasticsearch in the context of the project EPFL Graph.
    """

    def __init__(self, config, index):
        try:
            self.client = Elasticsearch(
                hosts=[f"https://{config['host']}:{config['port']}"],
                basic_auth=(config['username'], config['password']),
                ssl_context=create_default_context(cafile=config['cafile']),
                request_timeout=3600
            )
        except (KeyError, FileNotFoundError):
            print(
                "The elasticsearch configuration that was provided is not valid. "
                "Please make sure to provide a dict with the following keys: host, port, username, cafile, password."
            )
            self.client = None

        self.index = index

    ################################################################

    def _search(self, query, limit=10, source=None, explain=False, rescore=None):
        search = self.client.search(index=self.index, query=query, source=source, rescore=rescore, size=limit, explain=explain, profile=True)

        return search['hits']['hits']

    def _search_mediawiki(self, text, limit=10):
        """
        Perform elasticsearch search query using the mediawiki query structure, skipping the rescore part.

        Args:
            text (str): Query text for the search.
            limit (int): Maximum number of returned results.

        Returns:
            list: A list of the documents that are hits for the search.
        """

        query = bool_query(
            should=[
                multi_match_query(fields=['all_near_match^10', 'all_near_match_asciifolding^7.5'], text=text),
                bool_query(
                    filter=[
                        bool_query(
                            should=[
                                match_query('all', text=text, operator='and'),
                                match_query('all.plain', text=text, operator='and')
                            ]
                        )
                    ],
                    should=[
                        multi_match_query(fields=['title^3', 'title.plain^1'], text=text, type='most_fields', boost=0.3, minimum_should_match=1),
                        multi_match_query(fields=['category^3', 'category.plain^1'], text=text, type='most_fields', boost=0.05, minimum_should_match=1),
                        multi_match_query(fields=['heading^3', 'heading.plain^1'], text=text, type='most_fields', boost=0.05, minimum_should_match=1),
                        multi_match_query(fields=['auxiliary_text^3', 'auxiliary_text.plain^1'], text=text, type='most_fields', boost=0.05, minimum_should_match=1),
                        multi_match_query(fields=['file_text^3', 'file_text.plain^1'], text=text, type='most_fields', boost=0.5, minimum_should_match=1),
                        dis_max_query([
                            multi_match_query(fields=['redirect^3', 'redirect.plain^1'], text=text, type='most_fields', boost=0.27, minimum_should_match=1),
                            multi_match_query(fields=['suggest'], text=text, type='most_fields', boost=0.2, minimum_should_match=1)
                        ]),
                        dis_max_query([
                            multi_match_query(fields=['text^3', 'text.plain^1'], text=text, type='most_fields', boost=0.6, minimum_should_match=1),
                            multi_match_query(fields=['opening_text^3', 'opening_text.plain^1'], text=text, type='most_fields', boost=0.5, minimum_should_match=1)
                        ]),
                    ]
                )
            ]
        )

        return self._search(query, limit=limit)

    def _search_mediawiki_no_plain(self, text, limit=10):
        """
        Perform elasticsearch search query using the mediawiki query structure, restricted to non-plain fields.

        Args:
            text (str): Query text for the search.
            limit (int): Maximum number of returned results.

        Returns:
            list: A list of the documents that are hits for the search.
        """

        query = bool_query(
            should=[
                match_query(field='all_near_match', text=text, boost=10),
                bool_query(
                    filter=[
                        match_query('all', text=text, operator='and')
                    ],
                    should=[
                        match_query(field='title', text=text, boost=0.9),
                        match_query(field='category', text=text, boost=0.15),
                        match_query(field='heading', text=text, boost=0.15),
                        match_query(field='auxiliary_text', text=text, boost=0.15),
                        match_query(field='file_text', text=text, boost=1.5),
                        dis_max_query([
                            match_query(field='redirect', text=text, boost=0.81),
                            match_query(field='suggest', text=text, boost=0.2)
                        ]),
                        dis_max_query([
                            match_query(field='text', text=text, boost=1.8),
                            match_query(field='opening_text', text=text, boost=1.5)
                        ])
                    ]
                )
            ]
        )

        return self._search(query, limit=limit)

    def _search_mediawiki_restrict_4(self, text, limit=10):
        """
        Perform elasticsearch search query using the mediawiki query structure, restricted to the following fields:
        title, text, heading, opening_text

        Args:
            text (str): Query text for the search.
            limit (int): Maximum number of returned results.

        Returns:
            list: A list of the documents that are hits for the search.
        """

        query = bool_query(
            should=[
                bool_query(
                    filter=[
                        bool_query(
                            should=[
                                match_query('title', text=text, operator='and'),
                                match_query('title.plain', text=text, operator='and'),
                                match_query('text', text=text, operator='and'),
                                match_query('text.plain', text=text, operator='and'),
                                match_query('heading', text=text, operator='and'),
                                match_query('heading.plain', text=text, operator='and')
                            ]
                        )
                    ],
                    should=[
                        multi_match_query(fields=['title^3', 'title.plain^1'], text=text, type='most_fields', boost=0.3, minimum_should_match=1),
                        multi_match_query(fields=['heading^3', 'heading.plain^1'], text=text, type='most_fields', boost=0.05, minimum_should_match=1),
                        dis_max_query([
                            multi_match_query(fields=['text^3', 'text.plain^1'], text=text, type='most_fields', boost=0.6, minimum_should_match=1),
                            multi_match_query(fields=['opening_text^3', 'opening_text.plain^1'], text=text, type='most_fields', boost=0.5, minimum_should_match=1)
                        ])
                    ]
                )
            ]
        )

        return self._search(query, limit=limit)

    def _search_mediawiki_restrict_2(self, text, limit=10):
        """
        Perform elasticsearch search query using the mediawiki query structure, restricted to the following fields:
        title, text

        Args:
            text (str): Query text for the search.
            limit (int): Maximum number of returned results.

        Returns:
            list: A list of the documents that are hits for the search.
        """

        query = bool_query(
            should=[
                bool_query(
                    filter=[
                        bool_query(
                            should=[
                                match_query('title', text=text, operator='and'),
                                match_query('title.plain', text=text, operator='and'),
                                match_query('text', text=text, operator='and'),
                                match_query('text.plain', text=text, operator='and')
                            ]
                        )
                    ],
                    should=[
                        multi_match_query(fields=['title^3', 'title.plain^1'], text=text, type='most_fields', boost=0.3, minimum_should_match=1),
                        multi_match_query(fields=['text^3', 'text.plain^1'], text=text, type='most_fields', boost=0.6, minimum_should_match=1)
                    ]
                )
            ]
        )

        return self._search(query, limit=limit)

    def search(self, text, limit=10):
        """
        Perform elasticsearch search query.

        Args:
            text (str): Query text for the search.
            limit (int): Maximum number of returned results.

        Returns:
            list: A list of the documents that are hits for the search.
        """

        return self._search_mediawiki(text, limit=limit)

    ################################################################

    def get_nodeset(self, ids, node_type):
        """Returns nodes based on exact match on the NodeKey field."""

        split_size = 1000

        # Split in two if too many ids
        n = len(ids)
        if n > split_size:
            first_nodeset = self.get_nodeset(ids[: n // 2], node_type)
            last_nodeset = self.get_nodeset(ids[n // 2:], node_type)
            return first_nodeset + last_nodeset

        # Fetch nodes from elasticsearch with the given ids
        query = {
            "bool": {
                "filter": [
                    {"term": {"NodeType.keyword": node_type}},
                    {"terms": {"NodeKey.keyword": ids}}
                ]
            }
        }
        hits = self._search(query, limit=split_size, source=['NodeKey', 'NodeType', 'Title'])
        nodeset = [hit['_source'] for hit in hits]

        # Keep original order
        nodeset = sorted(nodeset, key=lambda node: ids.index(node['NodeKey']))

        return nodeset

    def search_nodes(self, text, node_type):
        """Returns nodes based on a full-text match on the Title field."""
        query = {
            "function_score": {
                "score_mode": "multiply",
                "functions": SCORE_FUNCTIONS,
                "query": {
                    "bool": {
                        "filter": [
                            {
                                "term": {"NodeType.keyword": node_type}
                            }
                        ],
                        "must": [
                            {
                                "multi_match": {
                                    "type": "most_fields",
                                    "operator": "and",
                                    "fields": ["NodeKey", "Title", "Title.raw", "Title.trigram"],
                                    "query": text
                                }
                            }
                        ]
                    }
                }
            }
        }

        # Try to match only Title field
        hits = self._search(query, source=['NodeKey', 'NodeType', 'Title'])
        nodeset = [hit['_source'] for hit in hits]

        # Fallback try to match Content field instead
        if not nodeset:
            query['function_score']['query']['bool']['must'][0]['multi_match']['fields'] = ['Content']
            hits = self._search(query, source=['NodeKey', 'NodeType', 'Title'])
            nodeset = [hit['_source'] for hit in hits]

        return nodeset

    def search_node_contents(self, text, node_type, filter_ids=None):
        """Returns nodes based on a full-text match on the Content field."""

        query = {
            "function_score": {
                "score_mode": "multiply",
                "functions": SCORE_FUNCTIONS,
                "query": {
                    "bool": {
                        "filter": [
                            {
                                "term": {"NodeType.keyword": node_type}
                            }
                        ],
                        "must": [
                            {
                                "match": {
                                    "Content": text
                                }
                            }
                        ]
                    }
                }
            }
        }

        if filter_ids is not None:
            query['function_score']['query']['bool']['filter'].append({"terms": {"NodeKey.keyword": filter_ids}})

        hits = self._search(query, source=['NodeKey', 'NodeType', 'Title'])

        if not hits:
            return []

        # Return only results with a score higher than half of max_score
        max_score = max([hit['_score'] for hit in hits])
        nodeset = [hit['_source'] for hit in hits if hit['_score'] > 0.5 * max_score]

        return nodeset

    ################################################################

    def indices(self):
        """
        Retrieve information about all elasticsearch indices.

        Returns:
            dict: elasticsearch response
        """

        return self.client.cat.indices(index=self.index, format='json', v=True)

    def refresh(self):
        """
        Refresh index.

        Returns:
            dict: elasticsearch response
        """

        self.client.indices.refresh(index=self.index)

    def index_doc(self, doc):
        """
        Index the given document.

        Args:
            doc (dict): Document to index.

        Returns:
            dict: elasticsearch response
        """

        if 'id' in doc:
            self.client.index(index=self.index, document=doc, id=doc['id'])
        else:
            self.client.index(index=self.index, document=doc)

    def create_index(self, settings=None, mapping=None):
        """
        Create index with the given settings and mapping.

        Args:
            settings (dict): Dictionary with elasticsearch settings, in that format.
            mapping (dict): Dictionary with elasticsearch mapping, in that format.

        Returns:
            dict: elasticsearch response
        """

        body = {}

        if settings is not None:
            body['settings'] = settings

        if mapping is not None:
            body['mappings'] = mapping

        if body:
            self.client.indices.create(index=self.index, body=body)
        else:
            self.client.indices.create(index=self.index)

    def delete_index(self):
        """
        Delete index.

        Returns:
            dict: elasticsearch response
        """

        self.client.indices.delete(index=self.index, ignore_unavailable=True)
