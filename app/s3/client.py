from typing import BinaryIO

import urllib3
from minio import Minio
from minio.error import S3Error

from app.config import settings
from app.utils.helpers import remove_all_spec_chars


class S3Client:
    def __init__(self, access_key: str, secret_key: str, endpoint_url: str, bucket_name: str):
        self.config = {
            "access_key": access_key,
            "secret_key": secret_key,
            "endpoint_url": endpoint_url,
        }
        self.bucket_name = bucket_name
        self.client = Minio(
            endpoint_url.replace("http://", "").replace("https://", ""),
            access_key=access_key,
            secret_key=secret_key,
            secure=True,
            http_client=urllib3.PoolManager(cert_reqs='CERT_NONE')
        )

        # Создаем бакет, если его нет
        if not self.client.bucket_exists(bucket_name):
            self.client.make_bucket(bucket_name)


    def upload_file(self, key: str, body: BinaryIO, size:int, folder: str = None, extension: str = "") -> str:
        """Загружает файл в Minio и возвращает его URL"""

        object_name = remove_all_spec_chars(key) + extension
        if folder:
            object_name = remove_all_spec_chars(folder) + "/" + object_name

        try:
            result = self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                data=body,
                length=size,
            )
            return f"{self.config['endpoint_url']}/{self.bucket_name}/{result.object_name}"
        except S3Error as err:
            print(f"Ошибка при загрузке файла: {err}")
            return ""


    def get_file(self, key):
        """Получает файл из Minio"""
        try:
            response = self.client.get_object(self.bucket_name, self._repair_key(key))
            return response.read()  # Читаем содержимое файла
        except S3Error as err:
            print(f"Ошибка при получении файла: {err}")
            return None



s3_client = S3Client(
    access_key=settings.S3_ACCESS_KEY,
    secret_key=settings.S3_SECRET_KEY,
    endpoint_url=settings.S3_ENDPOINT_URL,
    bucket_name=settings.S3_BUCKET_NAME
)
