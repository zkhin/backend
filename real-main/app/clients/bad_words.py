import json
import logging
import os

from .s3 import S3Client

S3_BAD_WORDS_BUCKET = os.environ.get('S3_BAD_WORDS_BUCKET')
logger = logging.getLogger()


class BadWordsClient:
    def __init__(self, bucket_name=S3_BAD_WORDS_BUCKET):
        self.s3_bad_words = S3Client(bucket_name)
        self.file_name = 'bad_words.json'

    def validate_bad_words_detection(self, text):
        try:
            fh = self.s3_bad_words.get_object_data_stream(self.file_name)
        except Exception as err:
            logger.warning(str(err))
            raise err

        bad_words = json.loads(fh.read().decode())
        words = text.split(' ')
        for word in words:
            if bad_words.get(word, None) == '':
                return True

        return False
