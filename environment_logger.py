from bs4 import BeautifulSoup
from action import Action

class EnvironmentChange:
    change_log = dict()
    def __init__(self, url, html, action_type : Action.Type):
        self.url = self.__normalize_url(url).strip()
        if html:
            self.html = self.__normalize_html(html).strip()
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


    # def __str__(self):
    #     match self.action_type:
    #         case Action.Type.STOP:  # Should never really ever happen for now
    #             return "STOP"
    #         case Action.Type.CLICK_LINK:
    #             return "Already visited"
    #         case Action.Type.CLICK_GENERAL:
    #             return "Previously attempted"
    #         case Action.Type.CLICK_SELECT:
    #             return ""
    #         case Action.Type.INPUT:
    #             if self in EnvironmentChange.change_log:
    #                 return f"Previously inputted: {EnvironmentChange.change_log[self]}"
    #             return f"INPUT ERROR TRACKING"

    def __str__(self):
        return f"({self.url}, {self.html}, {self.action_type.name})"

    def __eq__(self, other):
        return hash(self) == hash(other)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        match self.action_type:
            case Action.Type.STOP: # Should never really ever happen for now
                return hash(str((self.url, self.action_type.name)))
            case Action.Type.CLICK_LINK:
                return hash(str((self.action_type.name, self.html)))
            case Action.Type.CLICK_SELECT:
                return hash(str((self.url, self.action_type.name, self.html)))
            case Action.Type.CLICK_IMPORTANT:
                return hash(str((self.url, self.action_type.name, self.html)))
            case Action.Type.INPUT:
                return hash(str((self.url, self.action_type.name, self.html)))