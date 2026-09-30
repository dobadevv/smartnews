import signal

import pytest
from smartnews_common.signals import call_on_shutdown_signals


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGINT])
def test_call_on_shutdown_signals_invokes_callback_when_signal_arrives(
    request: pytest.FixtureRequest, signum: signal.Signals
) -> None:
    previous_handlers = {
        sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)
    }
    request.addfinalizer(
        lambda: [signal.signal(sig, handler) for sig, handler in previous_handlers.items()]
    )
    calls: list[str] = []

    call_on_shutdown_signals(lambda: calls.append("stopped"))
    signal.raise_signal(signum)

    assert calls == ["stopped"]
