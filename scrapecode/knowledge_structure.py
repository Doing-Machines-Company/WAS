'''

We need a good action space built of symbols

we need to generate this action space via a scrape

every action should be planned using (action, object) types, with action and object as types, these are what we will call 'visible' symbols

visible = we plan using these

we also have invisible symbols, which occasionally help chain visible symbols together

actions should be able to occur over like (action, set of objects in the same class) as well, like (view order, orders in date range)

we perhaps may want to decompose this object set into individual objects, this is tbd

on the larger scale, every action should happen on an element of a set of an equivalence class, representing a unique action space class

this action space class has specific ascriptions (like product page for food vs electronics), but have a very similar set of actions ()

we repeat searching for action spaces then performing the planned action on that space, until the set of completed discrete symbol chains is evaluated to be complete


we know that actions need to be ascribed action effects, this is incredibly important

however some actions may also be effect-dependent on another element of the page, e.g., pagination may be affected by the ordering of the page

i don't know how we search for these beyond brute force. but we may get a better intuition after just building a few of these spaces.

more concretely, we have:

Objects and their equivalence classes

Actions and their equivalence classes

There is a direct relationship between one action equiv class and an object equiv class

Then also Action Spaces and their equiv classes, which incorporate actions and objects, these are what we have called 'page equivalence classes'

To do inference, we need a correspondence between these three types of things and HTML/Webpage features, we need to figure out how to do this.

Then we just extract accordingly via our action space. I think that mapping using just html/acc trees are super hard, but if we can map using multimodal models onto our action space or vice versa, this seems promising


Another idea we can work with is only have actions and action spaces, with the objects that actions act on being loosely defined, which will save us a lot of work

We just hope that the LM can figure this out. We then just ascribe actions to the action space, and pretend the objects exist as expected (if they don't, model throws an error)


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