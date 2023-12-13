from ssl import create_default_context

from elasticsearch import Elasticsearch

from elasticsearch_interface.utils import (
    es_bool,
    es_match,
    es_multi_match,
    es_dis_max,
)


class ES:
    """
    Base class to communicate with elasticsearch in the context of the project EPFL Graph.
    """

    def __init__(self, config, index):
        try:
            self.host = config['host']
            self.port = config['port']
            self.username = config['username']
            self.cafile = config['cafile']
            password = config['password']

            context = create_default_context(cafile=self.cafile)
            self.client = Elasticsearch(
                hosts=[f'https://{self.username}:{password}@{self.host}:{self.port}'],
                ssl_context=context,
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

        query = es_bool(
            should=[
                es_multi_match(fields=['all_near_match^10', 'all_near_match_asciifolding^7.5'], text=text),
                es_bool(
                    filter=[
                        es_bool(
                            should=[
                                es_match('all', text=text, operator='and'),
                                es_match('all.plain', text=text, operator='and')
                            ]
                        )
                    ],
                    should=[
                        es_multi_match(fields=['title^3', 'title.plain^1'], text=text, type='most_fields', boost=0.3, minimum_should_match=1),
                        es_multi_match(fields=['category^3', 'category.plain^1'], text=text, type='most_fields', boost=0.05, minimum_should_match=1),
                        es_multi_match(fields=['heading^3', 'heading.plain^1'], text=text, type='most_fields', boost=0.05, minimum_should_match=1),
                        es_multi_match(fields=['auxiliary_text^3', 'auxiliary_text.plain^1'], text=text, type='most_fields', boost=0.05, minimum_should_match=1),
                        es_multi_match(fields=['file_text^3', 'file_text.plain^1'], text=text, type='most_fields', boost=0.5, minimum_should_match=1),
                        es_dis_max([
                            es_multi_match(fields=['redirect^3', 'redirect.plain^1'], text=text, type='most_fields', boost=0.27, minimum_should_match=1),
                            es_multi_match(fields=['suggest'], text=text, type='most_fields', boost=0.2, minimum_should_match=1)
                        ]),
                        es_dis_max([
                            es_multi_match(fields=['text^3', 'text.plain^1'], text=text, type='most_fields', boost=0.6, minimum_should_match=1),
                            es_multi_match(fields=['opening_text^3', 'opening_text.plain^1'], text=text, type='most_fields', boost=0.5, minimum_should_match=1)
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

        query = es_bool(
            should=[
                es_match(field='all_near_match', text=text, boost=10),
                es_bool(
                    filter=[
                        es_match('all', text=text, operator='and')
                    ],
                    should=[
                        es_match(field='title', text=text, boost=0.9),
                        es_match(field='category', text=text, boost=0.15),
                        es_match(field='heading', text=text, boost=0.15),
                        es_match(field='auxiliary_text', text=text, boost=0.15),
                        es_match(field='file_text', text=text, boost=1.5),
                        es_dis_max([
                            es_match(field='redirect', text=text, boost=0.81),
                            es_match(field='suggest', text=text, boost=0.2)
                        ]),
                        es_dis_max([
                            es_match(field='text', text=text, boost=1.8),
                            es_match(field='opening_text', text=text, boost=1.5)
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

        query = es_bool(
            should=[
                es_bool(
                    filter=[
                        es_bool(
                            should=[
                                es_match('title', text=text, operator='and'),
                                es_match('title.plain', text=text, operator='and'),
                                es_match('text', text=text, operator='and'),
                                es_match('text.plain', text=text, operator='and'),
                                es_match('heading', text=text, operator='and'),
                                es_match('heading.plain', text=text, operator='and')
                            ]
                        )
                    ],
                    should=[
                        es_multi_match(fields=['title^3', 'title.plain^1'], text=text, type='most_fields', boost=0.3, minimum_should_match=1),
                        es_multi_match(fields=['heading^3', 'heading.plain^1'], text=text, type='most_fields', boost=0.05, minimum_should_match=1),
                        es_dis_max([
                            es_multi_match(fields=['text^3', 'text.plain^1'], text=text, type='most_fields', boost=0.6, minimum_should_match=1),
                            es_multi_match(fields=['opening_text^3', 'opening_text.plain^1'], text=text, type='most_fields', boost=0.5, minimum_should_match=1)
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

        query = es_bool(
            should=[
                es_bool(
                    filter=[
                        es_bool(
                            should=[
                                es_match('title', text=text, operator='and'),
                                es_match('title.plain', text=text, operator='and'),
                                es_match('text', text=text, operator='and'),
                                es_match('text.plain', text=text, operator='and')
                            ]
                        )
                    ],
                    should=[
                        es_multi_match(fields=['title^3', 'title.plain^1'], text=text, type='most_fields', boost=0.3, minimum_should_match=1),
                        es_multi_match(fields=['text^3', 'text.plain^1'], text=text, type='most_fields', boost=0.6, minimum_should_match=1)
                    ]
                )
            ]
        )

        return self._search(query, limit=limit)

    ################################################################

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
