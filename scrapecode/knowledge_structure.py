class EquivalenceClass:
    def __init__(self, name, description):
        self.name = name # for human reference only
        self.description = description # for human reference only
        self.action_space = None

class ActionSpace:
    def __init__(self, name, description):
        self.name = name # for human reference only
        self.description = description # for human reference only
        self.actions = []

class ScrapeAction:
    def __init__(self, name, description):
        self.name = name # for human reference only
        self.description = description # for human reference only
        self.action = None # some relation to actual page actions would be good?