from smartnews_common.messaging.connection import (
    HEARTBEAT_SECONDS,
    connection_parameters,
)


def test_connection_parameters_use_a_long_heartbeat_so_slow_llm_calls_keep_the_connection() -> None:
    parameters = connection_parameters("amqp://user:secret@rabbitmq:5672/%2F")

    assert parameters.heartbeat == HEARTBEAT_SECONDS == 600
    assert (parameters.host, parameters.port) == ("rabbitmq", 5672)
