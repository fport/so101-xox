"""Local web dashboard for the tic-tac-toe game: cameras, board, moves, log.

Wiring it into a game loop::

    from xox.state import GameState
    from xox.dashboard import start_dashboard

    state = GameState()
    state.on_stop = stop_event.set          # enables the Stop button
    server = start_dashboard(state)         # http://127.0.0.1:8765/
    ...
    state.set_frame("top", rgb_array)       # any thread, any rate
    state.update(turn="x", phase="arm_moving", target_cell="middle_left")
    ...
    server.stop()

Try it without the robot: ``python -m xox.dashboard --demo``.
"""

from .server import DashboardServer, start_dashboard

__all__ = ["DashboardServer", "start_dashboard"]
