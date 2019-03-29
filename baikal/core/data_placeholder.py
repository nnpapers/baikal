from baikal.core.utils import make_repr


def is_data_placeholder_list(l):
    return all([isinstance(item, DataPlaceholder) for item in l])


class DataPlaceholder:
    def __init__(self, shape, step, name):
        self.shape = shape
        self.step = step
        self.name = name

    def __repr__(self):
        attrs = ['shape', 'step', 'name']
        return make_repr(self, attrs)

    # Make it sortable to aid lru_cache hits in Model._get_required_steps
    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.name < other.name
        return NotImplemented