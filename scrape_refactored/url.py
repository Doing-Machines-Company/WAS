from urllib.parse import urlparse


class Url:
    def __init__(self, url):
        self.url = url
    def has_same_origin_as(self,url):
        url_obj = urlparse(url)
        return self.url==url_obj.netloc