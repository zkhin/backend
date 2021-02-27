import json
import logging
import os

from .s3 import S3Client

S3_PROMO_CODES_BUCKET = os.environ.get('S3_PROMO_CODES_BUCKET')
logger = logging.getLogger()


class RedeemPromotionClient:
    def __init__(self, bucket_name=S3_PROMO_CODES_BUCKET):
        self.s3_promo_codes = S3Client(bucket_name if bucket_name else 'real-test-promo-codes')
        self.file_name = 'promo_codes.json'

    def get_promo_information(self, promotion_code):
        try:
            fh = self.s3_promo_codes.get_object_data_stream(self.file_name)
        except Exception as err:
            logger.warning(str(err))
            raise err

        data = json.loads(fh.read().decode())
        promo_codes = {key.lower(): data[key] for key in data.keys()}

        return promo_codes.get(promotion_code.lower())
