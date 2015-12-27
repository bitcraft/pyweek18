from abc import ABCMeta, abstractmethod


class State:
    """ This is a prototype class for States.

    All states should inherit from it. No direct instances of this
    class should be created. get_event and update must be overloaded
    in the child class.

    Overview of Methods:
       startup - Called when added to the state stack
       update - Called each frame.  Do not perform timed functions here
       resume - Called each time state is updated for first time
       pause - Called when state is no longer active, but not destroyed
       shutdown - Called before state is destroyed
    """
    __metaclass__ = ABCMeta

    @abstractmethod
    def draw(self, surface, rect):
        """ Render the state to the surface passed.  Must be overloaded in children

        :param surface: Surface to be rendered onto
        :type surface: pygame.Surface
        :return: None
        """
        pass

    def startup(self):
        """ Called when scene is added to State Stack

        This will be called:
        * after state is pushed and before next update
        * just once during the life of a state

        Example uses: loading images, configuration, sounds.
        """
        pass

    def update(self, dt):
        """ Called each frame of game time

        This will be called:
        * each time game processes new frame/tick
        * before state is asked to draw
        * only while state is active

        Do not do any timing related functions here.  This function
        should not be aware of wall time.  All timing related functions
        should be handled by the global singleton scheduler.
        """
        pass

    def resume(self):
        """ Called before update when state is newly in focus

        This will be called:
        * before update after being pushed to the stack
        * before update after state has been paused
        * state will begin to accept player input
        * could be called several times over lifetime of state

        Example uses: starting music, open menu, starting animations, timers, etc
        """
        pass

    def pause(self):
        """ Called when state is pushed back in the stack, allowed to pause

        This will be called:
        * after update when state is pushed back
        * when state is no longer accepting player input
        * could be called several times over lifetime of state

        Example uses: stopping music, sounds, fading out, making state graphics dim
        """
        pass

    def shutdown(self):
        """ Called when state is removed from stack and will be destroyed

        This will be called:
        * after update when state is popped

        Make sure to release any references to objects that may cause
        cyclical dependencies.
        """
        pass


class StateManager:
    """ Mix-in style class for use with Control class.

    This is currently undergoing a refactor of sorts, API may not be stable
    """

    def __init__(self):
        self.state_stack = list()
        self.state_dict = dict()
        self._current_state_requires_resume = False

    def register_state(self, state):
        """ Add a state class

        :param state: any subclass of core.state.State
        """
        name = state.__name__

        # this tests if a state has already been imported under
        # the same name.  This will happen if importing states
        # to be used as a subclass.  Since the name and state
        # object are the same, just continue without error.
        previously_reg_state = self.state_dict.get(name, None)
        if previously_reg_state == state:
            return

        if previously_reg_state is not None:
            print('Duplicate state detected: {}'.format(name))
            raise RuntimeError

        self.state_dict[name] = state

    def query_all_states(self):
        """ Return a dictionary of all loaded states

        Keys are state names, values are State classes

        :return: dictionary of all loaded states
        """
        return self.state_dict.copy()

    def pop_state(self):
        """ Pop the currently running state.  The previously running state will resume.

        :return:
        """
        try:
            previous = self.state_stack.pop(0)
            previous.shutdown()

            if self.state_stack:
                self.current_state.resume()
            else:
                # TODO: make API for quiting the app main loop
                self.done = True
                self.exit = True

        except IndexError:
            print('Attempted to pop state when no state was active.')
            raise RuntimeError

    def push_state(self, state_name):
        """ Start a state

        New stats will be created if there are none.

        :param state_name: name of state to start
        :param params: dictionary of data used to init the state
        :return: instanced State
        """
        try:
            state = self.state_dict[state_name]
        except KeyError:
            print('Cannot find state: {}'.format(state_name))
            raise RuntimeError

        previous = self.current_state
        if previous is not None:
            previous.pause()

        instance = state()
        instance.controller = self
        instance.startup()

        self._current_state_requires_resume = True
        self.state_stack.insert(0, instance)

        return instance

    @property
    def state_name(self):
        """ Name of state currently running

        TODO: phase this out?

        :return: string
        """
        return self.state_stack[0].__class__.__name__

    @property
    def current_state(self):
        """ The currently running state

        :return: State
        """
        try:
            state = self.state_stack[0]
            if state and self._current_state_requires_resume:
                self._current_state_requires_resume = False
                state.resume()
            return self.state_stack[0]
        except IndexError:
            return None
