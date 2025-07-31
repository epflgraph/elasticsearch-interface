from ssl import create_default_context

from abc import ABC, abstractmethod

from elasticsearch import Elasticsearch, helpers

from elasticsearch_interface.utils import (
    bool_query,
    match_query,
    match_all_query,
    multi_match_query,
    dis_max_query,
    term_based_filter,
    include_or_exclude_scores,
    include_or_exclude_embeddings,
    date_based_filter
)


class ESIndexBuilder:
    """
    Class to create, build, and destroy indexes, and add/remove aliases
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

        return self.client.indices.stats()['indices']

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
        """
        Recreates the current index
        Args:
            settings: The settings dictionary
            mapping: The index mappings

        Returns:
            None
        """
        self.delete_index()
        self.create_index(settings=settings, mapping=mapping)

    def add_alias(self, alias):
        """
        Adds an alias to the current index.
        Args:
            alias: The alias to add

        Returns:
            None
        """
        self.client.indices.put_alias(index=self.index, name=alias)

    def remove_alias(self, alias):
        """
        Removes an alias from the current index.
        Args:
            alias: The alias to remove

        Returns:
            None
        """
        self.client.indices.delete_alias(index=self.index, name=alias)

    def eliminate_alias(self, alias):
        """
        Completely removes an alias from any and all indexes. USE WITH CAUTION!
        Args:
            alias: The alias to remove

        Returns:
            None
        """
        self.client.indices.delete_alias(index='*', name=alias)


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
    def _build_query(self, texts, node_type):
        ################################################################
        # Build text match clauses                                     #
        ################################################################

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

        en_clauses = []
        fr_clauses = []
        id_clauses = []
        for text in texts:
            en_clauses.append({
                "multi_match": {
                    "fields": build_fields('en'),
                    "query": text
                }
            })

            fr_clauses.append({
                "multi_match": {
                    "fields": build_fields('fr'),
                    "query": text
                }
            })

            id_clauses.append({
                "term": {
                    "doc_id.keyword": {
                        "boost": 10,
                        "value": text
                    }
                }
            })

        # en_query is an OR between matches against en fields for all texts
        en_query = {
            "bool": {
                "should": en_clauses,
                "minimum_should_match": 1
            }
        }

        # fr_query is an OR between matches against fr fields for all texts
        fr_query = {
            "bool": {
                "should": fr_clauses,
                "minimum_should_match": 1
            }
        }

        # We then take the maximum between the two (otherwise words spelled the same in both languages would be boosted)
        max_en_fr_query = {
            "dis_max": {
                "queries": [en_query, fr_query]
            }
        }

        ################################################################
        # Build filter clause                                          #
        ################################################################

        # # We use only documents from EPFL or the ontology - WAS REMOVED FROM THE INDEX
        # filter_clause = [
        #     {
        #         "terms": {"doc_institution.keyword": ["EPFL", "Ont"]}
        #     },
        #     # {
        #     #     "terms": {"links.link_institution.keyword": ["EPFL", "Ont"]}
        #     # }
        # ]
        filter_clause = []

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
                "query": {
                    "bool": {
                        "filter": filter_clause,
                        "should": id_clauses + [max_en_fr_query],
                        "minimum_should_match": 1
                    }
                }
            }
        }

        return query

    def _build_fields(self, return_links):
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

        fields = node_fields + [type_field for _, type_fields in type_specific_fields.items() for type_field in type_fields]

        if return_links:
            fields += ['links']
            fields += [f"links.{link_field}" for link_field in link_fields]
            fields += [f"links.{type_field}" for _, type_fields in type_specific_fields.items() for type_field in type_fields]

        return fields

    def _search_graphsearch(self, texts, node_type, limit, return_links):
        # Make texts always a list
        if isinstance(texts, str):
            texts = [texts]

        query = self._build_query(texts, node_type)
        fields = self._build_fields(return_links)

        return self._search(query=query, source=fields, limit=limit)

    def search(self, text, node_type=None, limit=10, return_links=False, return_scores=False):
        # Run search
        hits = self._search_graphsearch(text, node_type, limit, return_links)
        hits = include_or_exclude_scores(hits, return_scores)
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
            if filter_clause is not None:
                knn["filter"] = filter_clause
        else:
            knn = None

        return self._search(query=query, knn=knn, limit=limit)

    def search(self, text, embedding=None, lang=None, limit=10, return_scores=False, return_embeddings=False):
        hits = self._search_lex(text, embedding, limit, lang)
        hits = include_or_exclude_scores(hits, return_scores)
        hits = include_or_exclude_embeddings(hits, return_embeddings)
        return hits


class ESServiceDesk(AbstractESRetriever):
    def _search_servicedesk(self, text, embedding, limit, lang_filter, cat_filter):
        def build_fields(lang):
            return [
                f"content.{lang}",
                f"content.{lang}.keyword",
                f"content.{lang}.raw",
                f"content.{lang}.trigram",
                f"content.{lang}.sayt._2gram",
                f"content.{lang}.sayt._3gram",
                f"description.{lang}",
                f"description.{lang}.keyword",
                f"description.{lang}.raw",
                f"description.{lang}.trigram",
            ]

        # The final query does the following
        #   1. Keeps only documents satisfying the language filter.
        #   2. Looks at text matches in en and fr.
        #   3. Looks at embedding-based matches.
        if lang_filter is not None or cat_filter is not None:
            filter_clause = term_based_filter({
                "language.keyword": lang_filter,
                "category.keyword": cat_filter,
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
            if filter_clause is not None:
                knn["filter"] = filter_clause
        else:
            knn = None

        return self._search(query=query, knn=knn, limit=limit)

    def search(self, text, embedding=None, lang=None, category=None,
               limit=10, return_scores=False, return_embeddings=False):
        hits = self._search_servicedesk(text, embedding, limit, lang, category)
        hits = include_or_exclude_scores(hits, return_scores)
        hits = include_or_exclude_embeddings(hits, return_embeddings)
        return hits


class ESGeneralRAG(AbstractESRetriever):
    def _search_general_rag(self, text, embedding, limit, **kwargs):
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
        if kwargs:
            # The way we tell keyword filters apart from date filters is through the name
            # Names of date filters must end in '_date'
            filter_clause = list()

            def get_arg_based_on_val(arg, val):
                if isinstance(val, str) or (isinstance(val, list) and len(val) > 0 and isinstance(val[0], str)):
                    return f"{arg}.keyword"
                return arg
            filter_clause.extend(
                term_based_filter({
                    get_arg_based_on_val(arg, val): val
                    for arg, val in kwargs.items()
                    if not arg.endswith('_date')
                })
            )
            filter_clause.extend(
                date_based_filter(
                    {
                        arg[:-5]: val
                        for arg, val in kwargs.items()
                        if arg.endswith('_date')
                    }
                )
            )
        else:
            filter_clause = None
        if len(text.strip()) > 0:
            # If there is some text, then we add the text to the query
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
        else:
            # If there is no text, we use a match_all query and only do filters
            query = bool_query(
                should=[
                    match_all_query()
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
            if filter_clause is not None:
                knn["filter"] = filter_clause
        else:
            knn = None

        return self._search(query=query, knn=knn, limit=limit)

    def search(self, text, embedding=None, limit=10, return_scores=False, return_embeddings=False, **kwargs):
        hits = self._search_general_rag(text, embedding, limit, **kwargs)
        hits = include_or_exclude_scores(hits, return_scores)
        hits = include_or_exclude_embeddings(hits, return_embeddings)
        return hits


if __name__ == '__main__':
    config = {
        'host': 'localhost',
        'port': 19200,
        'username': '...',
        'password': '...',
        'cafile': '...',
        'index': 'graphsearch_prod',
    }

    es = ESGraphSearch(config, index=config['index'])
    results = es.search(['learning', 'education'], node_type=None, limit=3, return_links=True, return_scores=False)

    print(results)
