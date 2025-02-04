from ssl import create_default_context

from abc import ABC, abstractmethod

from elasticsearch import Elasticsearch

from elasticsearch_interface.utils import (
    bool_query,
    match_query,
    term_query,
    multi_match_query,
    dis_max_query,
    SCORE_FUNCTIONS,
)


class ESIndexBuilder:
    """
    Class to create, build, and destroy indexes
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

    def recreate_index(self, settings=None, mapping=None):
        self.delete_index()
        self.create_index(settings=settings, mapping=mapping)


class AbstractESRetriever(ABC, ESIndexBuilder):
    """
    Abstract base class to communicate with elasticsearch in the context of the project EPFL Graph.
    """

    def _search(self, query, knn=None, rank=None, limit=10, source=None, explain=False, rescore=None):
        search = self.client.search(index=self.index, query=query, knn=knn, rank=rank, source=source, rescore=rescore, size=limit, explain=explain, profile=True)

        return search['hits']['hits']

    @abstractmethod
    def search(self, text, limit=10):
        pass


class ESConceptDetection(AbstractESRetriever):
    """
    Elasticsearch connector for concept detection
    """

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

    def search_nodes(self, text, node_type, n=10, return_scores=False):
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
        hits = self._search(query, source=['NodeKey', 'NodeType', 'Title'], limit=n)
        if return_scores:
            nodeset = [{**hit['_source'], 'Score': hit['_score']} for hit in hits]
        else:
            nodeset = [hit['_source'] for hit in hits]

        if len(nodeset) > 0:
            return nodeset

        # Fallback try to match Content field instead
        query['function_score']['query']['bool']['must'][0]['multi_match']['fields'] = ['Content']
        hits = self._search(query, source=['NodeKey', 'NodeType', 'Title'], limit=n)
        if return_scores:
            nodeset = [{**hit['_source'], 'Score': hit['_score']} for hit in hits]
        else:
            nodeset = [hit['_source'] for hit in hits]

        return nodeset

    def search_node_contents(self, text, node_type, n=10, return_scores=False, filter_ids=None):
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

        hits = self._search(query, source=['NodeKey', 'NodeType', 'Title'], limit=n)

        if not hits:
            return []

        # Return only results with a score higher than half of max_score
        max_score = max([hit['_score'] for hit in hits])
        hits = [hit for hit in hits if hit['_score'] > 0.5 * max_score]

        if return_scores:
            nodeset = [{**hit['_source'], 'Score': hit['_score']} for hit in hits]
        else:
            nodeset = [hit['_source'] for hit in hits]

        return nodeset


class ESGraphSearch(AbstractESRetriever):
    def _search_graphsearch(self, texts, node_type, limit, return_links):
        def build_fields(lang):
            return [
                f"name.{lang}",
                f"name.{lang}.keyword",
                f"name.{lang}.raw",
                f"name.{lang}.trigram",
                f"name.{lang}.sayt._2gram",
                f"name.{lang}.sayt._3gram",
                f"short_description.{lang}",
                f"long_description.{lang}^0.001"
            ]

        ################################################################
        # Build filter clause                                          #
        ################################################################

        # We use only documents from EPFL or the ontology
        filter_clause = [
            {
                "terms": {"doc_institution.keyword": ["EPFL", "Ont"]}
            },
            # {
            #     "terms": {"links.link_institution.keyword": ["EPFL", "Ont"]}
            # }
        ]

        # And if node_types are specified, we keep only those documents
        if isinstance(node_type, list):
            filter_clause.append(
                {
                    "terms": {"doc_type.keyword": node_type}
                }
            )

        elif isinstance(node_type, str):
            filter_clause.append(
                {
                    "term": {"doc_type.keyword": node_type}
                }
            )

        ################################################################
        # Build final query                                            #
        ################################################################

        # The final query does the following
        #   1. Keeps only documents satisfying the filter
        #   2. Looks at text matches in en and fr, and also exact matches against the id field.
        #   3. Updates match score multiplying by degree score
        query = {
            "function_score": {
                "score_mode": "multiply",
                "functions": [{"field_value_factor": {"field": "degree_score"}}],
                "query": bool_query(
                    should=[
                        term_query("doc_id.keyword", text, boost=10) for text in texts
                    ] + [
                        dis_max_query([
                            bool_query(
                                should=[multi_match_query(build_fields('en'), text) for text in texts],
                                minimum_should_match=1
                            ),
                            bool_query(
                                should=[multi_match_query(build_fields('fr'), text) for text in texts],
                                minimum_should_match=1
                            )
                        ])
                    ],
                    filter=filter_clause,
                    minimum_should_match=1
                )
            }
        }

        ################################################################
        # Build fields                                                 #
        ################################################################

        node_fields = ["doc_type", "doc_id", "name", "short_description"]

        link_fields = ["link_type", "link_id", "link_name", "link_rank", "link_short_description"]

        type_specific_fields = {
            'course': ["latest_academic_year"],
            'lecture': ["video_duration"],
            'mooc': ["level", "domain", "language", "platform"],
            'person': ["gender", "is_at_epfl"],
            'publication': ["year", "publisher", "published_in"],
            'unit': ["is_research_unit", "is_active_unit"],
            'category': ["depth"],
            'concept': [],
            'startup': []
        }

        fields = node_fields + [type_field for _, type_fields in type_specific_fields.items() for type_field in
                                type_fields]

        if return_links:
            fields += ['links']
            fields += [f"links.{link_field}" for link_field in link_fields]
            fields += [f"links.{type_field}" for _, type_fields in type_specific_fields.items() for type_field in
                       type_fields]

        return self._search(query=query, source=fields, limit=limit)

    def search(self, texts, node_type=None, limit=10, return_links=False, return_scores=False):
        # Make texts always a list
        if isinstance(texts, str):
            texts = [texts]
        hits = self._search_graphsearch(texts, node_type, limit, return_links)
        if return_scores:
            hits = [{**hit['_source'], 'score': hit['_score']} for hit in hits]
        else:
            hits = [hit['_source'] for hit in hits]
        return hits
