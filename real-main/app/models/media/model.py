import logging

logger = logging.getLogger()


class Media:

    def __init__(self, item, media_dynamo):
        self.dynamo = media_dynamo
        self.item = item
        self.id = item['mediaId']

    def refresh_item(self, strongly_consistent=False):
        self.item = self.dynamo.get_media(self.id, strongly_consistent=strongly_consistent)
        return self
