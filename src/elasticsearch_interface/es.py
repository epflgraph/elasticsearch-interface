from ssl import create_default_context

from abc import ABC, abstractmethod

from elasticsearch import Elasticsearch, helpers

from elasticsearch_interface.utils import (
    bool_query,
    match_query,
    term_query,
    multi_match_query,
    dis_max_query,
    term_based_filter,
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
            None
        """

        if 'id' in doc:
            self.client.index(index=self.index, document=doc, id=doc['id'])
        else:
            self.client.index(index=self.index, document=doc)

    def bulk_index_docs(self, docs, chunk_size=500):
        """
        Index a list of documents.

        Args:
            docs (dict): Documents to index.
            chunk_size: Chunk size for bulk operation (used by helpers.streaming_bulk, which is called by helpers.bulk)
        Returns:
            None
        """
        def yield_docs():
            for current_doc in docs:
                current_op = {
                    '_index': self.index,
                    '_op_type': 'index',
                    '_source': current_doc
                }
                if 'id' in current_doc:
                    current_op['_id'] = current_doc['id']
                yield current_op
        helpers.bulk(self.client, actions=yield_docs(), chunk_size=chunk_size)

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
                    filter=term_based_filter({
                        "doc_institution.keyword": ["EPFL", "Ont"],
                        "doc_type.keyword": node_type
                    }),
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


class ESLex(AbstractESRetriever):
    def _search_lex(self, text, embedding, limit, lang_filter):
        def build_fields(lang):
            return [
                f"content.{lang}",
                f"content.{lang}.keyword",
                f"content.{lang}.raw",
                f"content.{lang}.trigram",
                f"content.{lang}.sayt._2gram",
                f"content.{lang}.sayt._3gram"
            ]

        # The final query does the following
        #   1. Keeps only documents satisfying the language filter.
        #   2. Looks at text matches in en and fr.
        #   3. Looks at embedding-based matches.
        if lang_filter is not None:
            filter_clause = term_based_filter({
                "language.keyword": lang_filter
            })
        else:
            filter_clause = None
        query = bool_query(
            should=[
                dis_max_query([
                    bool_query(
                        should=multi_match_query(build_fields('en'), text),
                        minimum_should_match=1
                    ),
                    bool_query(
                        should=multi_match_query(build_fields('fr'), text),
                        minimum_should_match=1
                    )
                ])
            ],
            filter=filter_clause,
            minimum_should_match=1
        )
        if embedding is not None:
            knn = {
                "field": "embedding",
                "query_vector": embedding,
                "k": 10
            }
        else:
            knn = None

        return self._search(query=query, knn=knn, limit=limit)

    def search(self, text, embedding=None, lang=None, limit=10, return_scores=False, return_embeddings=False):
        hits = self._search_lex(text, embedding, limit, lang)
        if return_scores:
            hits = [{**hit['_source'], 'score': hit['_score']} for hit in hits]
        else:
            hits = [hit['_source'] for hit in hits]
        if not return_embeddings:
            hits = [{k: v for k, v in hit.items() if k != 'embedding'} for hit in hits]
        return hits
