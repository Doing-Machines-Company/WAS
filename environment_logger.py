from bs4 import BeautifulSoup
from action import Action

class EnvironmentChange:
    change_log = dict()
    def __init__(self, url, html, action_type : Action.Type):
        self.url = self.__normalize_url(url)
        self.html = self.__normalize_html(html)
        self.action_type = action_type

    def __normalize_url(self, url):
        return url

    def __normalize_html(self, html):
        soup = BeautifulSoup(html, 'html.parser')

        for tag in soup.find_all(attrs={"value": True}):
            tag.attrs['value'] = None  # Remove 'value' attribute

        for tag in soup.find_all(attrs={"checked": True}):
            tag.attrs['checked'] = None  # Remove 'checked' attribute

        for tag in soup.find_all(attrs={"class": True}):
            tag.attrs['class'] = None  # Remove 'checked' attribute

        return str(soup)



    def __repr__(self):
        return f"{self.url}, {self.html}, {self.action_type.name}"
    def __hash__(self):
        match self.action_type:
            case Action.Type.STOP: # Should never really ever happen for now
                return hash((self.url, self.action_type))
            case Action.Type.CLICK_LINK:
                return hash((self.action_type, self.html))
            case Action.Type.CLICK_NON_LINK:
                return hash((self.url, self.action_type, self.html))
            case Action.Type.INPUT:
                return hash((self.url, self.action_type, self.html))