
from twisted.application.service import Service
from twisted.internet.task import SchedulerStopped, Cooperator, coiterate

def iterateInReactor(i, delay=None):
    """
    Cooperatively iterate over the given iterator.

    @see: L{twisted.internet.task.coiterate}.
    """
    return coiterate(i)


class SchedulingService(Service):
    """
    Simple L{IService} implementation.
    """
    def __init__(self):
        self.coop = Cooperator(started=False)

    def addIterator(self, iterator):
        return self.coop.coiterate(iterator)

    def startService(self):
        self.coop.start()

    def stopService(self):
        self.coop.stop()

__all__ = [
    'SchedulerStopped', 'Cooperator',
    'SchedulingService', 'iterateInReactor']
