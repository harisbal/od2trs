from multiprocessing import Value


class Counter(object):
    def __init__(self, init=0):
        self.val = Value('i', init)

    def increment(self, n=1):
        with self.val.get_lock():
            self.val.value += n
        return self

    @property
    def value(self):
        return self.val.value
