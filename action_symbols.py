from action import Action

class ActionSymbol:
    def __init__(self, name=None, description=None, page_action_type: Action.Type = None, object_description=None,
                 ):
        '''
        self.object_description
        a string description of the object(s) this action acts on, could be one could be arbitrarily many
        this is because the exact object(s) and amount of objects are opaque

        self.action_description
        a string description of the action
        INCLUDES ACTION's EFFECTS

        self.name
        what we name the action, just use HTML visible text, so we know what we're talking about

        self.page_action_type
        we need these symbols to be discrete in out ability to either complete or fail them
        the easiest way to do this would be to associate them with some landmarked page element

        :param name:
        :param description:
        '''
        self.name = name
        self.action_description = description
        self.page_action_type = page_action_type # some relation to actual page actions would be good?
        self.object_description_hidden = None # for task memory
        self.object_description_visible = None # for planning
        self.candidate_HTML = None

    def get_info(self):
        return self.name, self.action_description