'''

We need a good action space built of symbols

we need to generate this action space via a scrape

every action should be planned using (action, object) types, with action and object as types

on the larger scale, every action should happen on an element of a set of an equivalence class, representing a unique action space class

this action space class has specific ascriptions (like product page for food vs electronics), but have a very similar set of actions ()

we repeat searching for action spaces then performing the planned action on that space, until the set of completed discrete symbol chains is evaluated to be complete



'''


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