from weakref import proxy
import logging
from collections import deque


__all__ = ('EventDispatcher', )

logger = logging.getLogger(__name__)


class EventDispatcher:
    """
    All classes that send or receive events must inherit from this class

    This is not the publish subscribe pattern.  The pub/sub pattern
    dictates that all subscribes will receive messages they are
    subscribed to.  Event dispatchers have a set order in which
    messages are distributed and consumers have the option of
    preventing other consumers from receiving the event.

    TODO:
        implement unschedule (for internal use only?)
        allow consumers to halt propagation of event
        allow arguments to be passed to broadcast (or not)

    names:
        eventually, this psuedo pub/sub will be more like the observer
        pattern, with the queue shoehorned in.  i'd like to keep the names
        'bind and 'dispatch' since they are already in use in popular
        python frameworks and are closer in meaning to the intended function

        event names should follow normal python naming rules
        this will allow for a decorator in the future to decorate
        functions and derive the event name from the function name:

        @window.event
        def on_draw():
            pass

        is the same as, but available in a decorator:
        window.subscribe('on_draw', on_draw)

    concerns:
        how useful is 'setting default arguments when subscribing events'?
    """
    class EventNotRegistered(Exception):
        pass

    class DuplicateEventName(Exception):
        pass

    class NoQueueSetException(Exception):
        pass

    # change to a list or tuple of event names to have them
    # automatically registered when instance is created
    __event_names__ = None

    def __init__(self):
        self._event_types = list()
        self._event_lookup = dict()
        self._subscriptions = list()
        self.queue = None

        event_names = getattr(self, '__events__', None)
        if event_names is not None:
            for event_name in event_names:
                self.register(event_name)

    def enable_queue(self, queue=None):
        if queue is None:
            self.queue = deque()
        else:
            self.queue = queue

    def register(self, event_name, *args):
        """Register an event name for use

        :param event_name:
        :param args:
        :return:
        """
        if event_name in self._event_lookup:
            raise self.DuplicateEventName()

        # TODO: verify that event name follows standard python rules

        id = len(self._event_types)
        self._event_types.append(tuple([proxy(a) for a in args]))
        self._event_lookup[event_name] = id
        self._subscriptions.append(list())
        return id

    def get_handled_events(self):
        """Return a list of event names that is handled

        :return: list of event names
        """
        return self._event_lookup.keys()

    def subscribe(self, event_name, callback):
        """Safer and more convenient

        :param event_name:
        :param callback:
        :return: id of subscribed event
        """
        try:
            id = self._event_lookup[event_name]
        except KeyError:
            raise self.EventNotRegistered(self, event_name)
        else:
            self.subscribe_by_id(id, callback)
            return id

    def subscribe_by_id(self, event_id, callback):
        """Safe and fast

        :param event_id:
        :param callback:
        :return: None
        """
        try:
            self._subscriptions[event_id].append(callback)
        except IndexError:
            raise self.EventNotRegistered(self, event_id)

    def subscribe_internal(self, id, callback):
        """Do not use unless you know what you are doing

        Eventually, this will be used internally to provide
        subscribing without slow checks, useful for automation.

        :param id:
        :param callback:
        :return:
        """
        pass

    def broadcast(self, event_name, **kwargs):
        """Least performant, most convenient, flexible

        :param event_name:
        :param kwargs:
        :return:
        """
        try:
            id = self._event_lookup[event_name]
        except KeyError:
            raise self.EventNotRegistered(self, event_name)
        else:
            self.broadcast_by_id(id, **kwargs)

    def broadcast_by_id(self, id, **kwargs):
        """Best performance, least convenient

        :param id:
        :param kwargs:
        :return:
        """
        if self.queue is None:
            self.broadcast_internal(id, **kwargs)
        else:
            self.queue.append((id, kwargs))

    def broadcast_internal(self, event_id, **kwargs):
        """Do not use this directly unless you are absolutely sure you need to

        :param event_id:
        :param kwargs:
        :return:
        """
        try:
            subscriptions = self._subscriptions[event_id]
        except IndexError:
            raise self.EventNotRegistered(self, event_id)
        else:
            event_type = self._event_types[event_id]
            for subscriber in subscriptions:
                subscriber(*event_type, **kwargs)

    def flush(self):
        """Empty out any queued events
        """
        if self.queue is None:
            raise self.NoQueueSetException()

        while len(self.queue) > 0:
            id, kwargs = self.queue.popleft()
            if kwargs is None:
                self.broadcast_internal(id)
            else:
                self.broadcast_internal(id, **kwargs)

