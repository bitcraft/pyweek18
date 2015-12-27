import collections
import time
from heapq import heappush, heappop, heappushpop
from operator import attrgetter

__all__ = ('ScheduledItem',
           'Scheduler',
           'Clock')


class ScheduledItem:
    """ A class that describes a scheduled callback.

    This class is never created by the user; instead, pygame creates and
    returns an instance of this class when scheduling a callback.

    If you hold on to instance of this class, do not modify any values of it.
    """
    __slots__ = ['func', 'interval', 'last_ts', 'next_ts']

    def __init__(self, func, last_ts, next_ts, interval):
        self.func = func
        self.interval = interval
        self.last_ts = last_ts
        self.next_ts = next_ts

    def __lt__(self, other):
        try:
            return self.next_ts < other.next_ts
        except AttributeError:
            return self.next_ts < other

    def __repr__(self):
        return '<SI: next: %s, interval %s>' % (self.next_ts, self.interval)


class Scheduler:
    """Class for scheduling functions.
    """

    def __init__(self, time_function=time.perf_counter):
        """Initialise a Clock, with optional custom time function.

        :Parameters:
            `time_function` : function
                Function to return the elapsed time of the application,
                in time units.
        """
        self._time = time_function
        self._last_ts = -1
        self._times = collections.deque(maxlen=10)
        self._scheduled_items = list()
        self._next_tick_items = set()
        self._current_executing_item = None
        self._current_executing_item_wants_to_remove = False
        self.cumulative_time = 0.0

    def _get_nearest_ts(self):
        """Schedule from now, unless now is sufficiently close to last_ts, in
        which case use last_ts.  This clusters together scheduled items that
        probably want to be scheduled together.
        """
        last_ts = self._last_ts
        ts = self._time()
        if ts - last_ts > 0.2:
            last_ts = ts
        return last_ts

    def _get_soft_next_ts(self, last_ts, interval):
        def taken(ts, e):
            """Return True if the given time has already got an item
            scheduled nearby.
            """
            # TODO this function is slow and called very often.  optimise it, maybe?
            for item in sorted_items:
                if abs(item.next_ts - ts) <= e:
                    return True
                elif item.next_ts > ts + e:
                    return False

            return False

        # sorted list is required required to produce expected results
        # taken() will iterate through the heap, expecting it to be sorted
        # and will not always catch smallest value, so create a sorted variant here
        # NOTE: do not rewrite as popping from heap, as that is super slow!
        sorted_items = sorted(self._scheduled_items, key=attrgetter('next_ts'))

        next_ts = last_ts + interval
        if not taken(next_ts, interval / 4):
            return next_ts

        dt = interval
        divs = 1
        while True:
            next_ts = last_ts
            for i in range(divs - 1):
                next_ts += dt
                if not taken(next_ts, dt / 4.):
                    return next_ts
            dt /= 2
            divs *= 2

            # Avoid infinite loop in pathological case
            if divs > 16:
                return next_ts

    def schedule(self, func, delay=0.0, repeat=False, soft=False):
        """
        Schedule a function to be run sometime in the future

        The function should have a prototype that includes ``dt`` as the
        first argument, which gives the elapsed time, in time units, since the
        last clock tick.

            def callback(dt):
                pass


        Limitations
        ===========

        There is a hard limit of 10 items that can be scheduled on
        next tick.  This limit reduces the power and performance
        impact of the clock on mobile and battery operated computers.

        A runtime error will be raised if the maximum is reached.


        Unscheduling
        ============

        If callback returns False (not None), then it will not be
        scheduled again.


        Soft Scheduling
        ===============

        This is useful for functions that need to be called regularly,
        but not relative to the initial start time.
        for example: events which need to occur regularly -- if all audio
        updates are scheduled at the same time
        (for example, mixing several tracks of a music score, or playing
        multiple videos back simultaneously), the resulting load on the
        CPU is excessive for those intervals but idle outside.  Using
        the soft interval scheduling, the load is more evenly distributed.


        :param func: Function to be called
        :param delay: Delay in time unit until it is called
        :param repeat: Function will be repeated every 'delay' units
        :param soft: See notes about Soft Scheduling
        :rtype: ScheduledItem
        :return: Reference to scheduled item
        """
        last_ts = self._get_nearest_ts()
        if soft:
            assert (delay > 0.0)
            next_ts = self._get_soft_next_ts(last_ts, delay)
            last_ts = next_ts - delay
        next_ts = last_ts + delay

        interval = delay if repeat else 0.0

        item = ScheduledItem(func, last_ts, next_ts, interval)
        if next_ts == 0.0:
            self._next_tick_items.add(item)
            if len(self._next_tick_items) > 10:
                raise RuntimeError
        else:
            heappush(self._scheduled_items, item)
        return item

    def tick(self):
        """Cause clock to update and call scheduled functions.

        This updates the clock's internal measure of time and returns
        the difference since the last update (or since the clock was created).

        Will call any scheduled functions that have elapsed.

        :rtype: float
        :return: The number of time units since the last "tick", or 0 if this
                 was the first tick.
        """
        delta_t = self.set_time(self._time())
        self._times.append(delta_t)
        self.call_scheduled_functions(delta_t)
        return delta_t

    def get_interval(self):
        """Get the average amount of time passed between each tick.

        Useful for calculating FPS if this clock is used with the display.
        Returned value is averaged from last 10 ticks.

        Value will be 0.0 if before 1st tick.

        :rtype: float
        :return: Average amount of time passed between each tick
        """
        try:
            return sum(self._times) / len(self._times)
        except ZeroDivisionError:
            return 0.0

    def set_time(self, time_stamp):
        """Set the clock manually and do not call scheduled functions.  Return
        the difference in time from the last time clock was updated.

        :Parameters:
            `time_stamp` : float
                This will become the new value of the clock.  Setting the clock
                to negative values will have undefined results.

        :rtype: float
        :return: The number of time units since the last update, or 0.0 if this
                 was the first update.

        """
        # self._last_ts will be -1 before first time set
        if self._last_ts < 0:
            delta_t = 0.0
            self._last_ts = time_stamp
        else:
            delta_t = time_stamp - self._last_ts
        self.cumulative_time += delta_t
        self._last_ts = time_stamp
        return delta_t

    def call_scheduled_functions(self, dt):
        """Call scheduled functions that elapsed on the last `update_time`.

        :Parameters:
            dt : float
                The elapsed time since the last update to pass to each
                scheduled function.

        :rtype: bool
        :return: True if any functions were called, otherwise False.
        """
        scheduled_items = self._scheduled_items
        now = self._last_ts
        result = False

        # handle items scheduled for next tick
        if self._next_tick_items:
            result = True
            for item in list(self._next_tick_items):
                retval = item.func(dt)
                # do not change the following line to "if not retval"!
                # some items will return None, but False is a special value
                if retval == False:
                    self._next_tick_items.remove(item)

        # check the next scheduled item that is not called each tick
        # if it is scheduled in the future, then exit
        try:
            if scheduled_items[0].next_ts > now:
                return result
        except IndexError:
            return result

        # wherever this value is true the current item will be pushed
        # into the heap.  it essentially means that the current
        # scheduled item is important and needs stay scheduled.
        replace = False
        item = None

        get_soft_next_ts = self._get_soft_next_ts
        while scheduled_items:
            # the scheduler will hold onto a reference to an item in
            # case it needs to be rescheduled.  it is more efficient
            # to push and pop the heap at once rather than two operations
            if replace:
                item = heappushpop(scheduled_items, item)
            else:
                item = heappop(scheduled_items)

            # if next item is scheduled in the future then break
            if item.next_ts > now:
                replace = True
                break

            # to keep track of functions that unschedule themselves during update
            # see Scheduler.unschedule
            self._current_executing_item = item

            # call the function associated with the scheduled item
            retval = item.func(now - item.last_ts)

            self._current_executing_item = None

            if item.interval:
                # callbacks can unschedule themselves by returning false
                replace = not retval == False

                item.next_ts = item.last_ts + item.interval
                item.last_ts = now

                # the execution time of this item has already passed
                # so it must be rescheduled
                if item.next_ts <= now:
                    if now - item.next_ts < 0.05:
                        item.next_ts = now + item.interval
                    else:
                        # missed by significant amount, do a soft reschedule
                        # to avoid lumping everything together
                        # in this case, the next dt will not be accurate
                        item.next_ts = get_soft_next_ts(now, item.interval)
                        item.last_ts = item.next_ts - item.interval
            else:
                # not an interval, so this item will not be rescheduled
                replace = False

        # it is possible that the loop exited while an important item
        # was waiting to be pushed into the heap.
        if replace:
            heappush(scheduled_items, item)

        return result

    def get_idle_time(self):
        """Get the time until the next item is scheduled.

        :rtype: float
        :return: Time until the next scheduled event in time units, or ``None``
                 if there is no event scheduled.
        """
        if self._next_tick_items:
            return 0.0

        try:
            next_ts = self._scheduled_items[0].next_ts
            return max(next_ts - self._time(), 0.)
        except IndexError:
            return None

    def unschedule(self, func):
        """Remove a function from the schedule.

        If the function appears in the schedule more than once, all occurrences
        are removed.  If the function was not scheduled, no error is raised.

        :Parameters:
            `func` : function
                The function to remove from the schedule.

        :return: None
        """
        # clever remove item with disturbing the heap:
        # 1. set function to an empty lambda -- original function is not called
        # 2. set interval to 0               -- item will be removed from heap eventually

        # take care of items that unschedule themselves during update
        # must be done, as this item will not exist in heap during update
        if self._current_executing_item:
            if self._current_executing_item.func == func:
                self._current_executing_item.interval = 0
                self._current_executing_item.func = lambda x: x

        # look through all scheduled items
        for item in set(item for item in self._scheduled_items if item.func == func):
            item.interval = 0
            item.func = lambda x: x

        self._next_tick_items = [i for i in self._next_tick_items if i.func is not func]


class Clock(Scheduler):
    """Schedules stuff like a Scheduler, and includes time limiting functions

    WIP
    """
    pass

